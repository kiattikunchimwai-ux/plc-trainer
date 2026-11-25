"""อ่านเงื่อนไขของด่านแล้วบอกว่าเป็นงานแบบไหน มีข้อขัดแย้ง/ข้อที่ยังไม่ตรวจไหม (ไม่ใช้ Qt ไม่ใช้อินเทอร์เน็ต).

ดูจากลำดับ "ตัวตรวจทำอะไร → output ต้องเป็นอะไร" เท่านั้น ทุกข้อสรุปมีหลักฐาน (ข้อ, ขั้น)
ถ้าหลักฐานไม่พอจะไม่สรุป — ไม่เดา
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .. import i18n
from ..i18n import tr
from ..levels.conditions import nc_inputs, panel_names, press_rows, user_inputs
from ..levels.editor import CaseRow, StepRow
from ..levels.engine import OPS, Level
from ..panel import iolist
from ..plc.device import parse_device

QUICK_S = 1.0            # expect ที่ให้เวลาไม่เกินนี้ = ต้องเกิดทันที ไม่ใช่หน่วงเวลา


@dataclass
class Fact:
    kind: str                                  # on / off / latch / delay / count / interlock / sequence / blink / word
    out: str = ""
    inp: str = ""
    other: str = ""
    lo: float = 0.0                            # delay: ช่วงเวลาที่เป็นไปได้ · count: จำนวน
    hi: float = 0.0
    at: list[tuple[int, int]] = field(default_factory=list)      # (ข้อ, ขั้น) เริ่มที่ 0 ไม่รวม reset

    @property
    def sure(self) -> bool:
        return len(self.at) >= 2 or self.kind in ("latch", "count", "interlock")


@dataclass
class Issue:
    key: str
    text: str
    level: str = "warn"                        # error / warn / info


@dataclass
class Suggestion:
    key: str                                   # ชนิดคำแนะนำ (ใช้จำว่ารับ/ปฏิเสธ)
    text: str
    case: CaseRow | None = None


@dataclass
class Profile:
    facts: list[Fact] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    nc: set[str] = field(default_factory=set)
    idle: dict[str, int] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    physics: list[str] = field(default_factory=list)      # เหตุที่จำลองโดยไม่มีอุปกรณ์จริงไม่ได้
    hash: str = ""

    def get(self, kind: str, out: str = "") -> list[Fact]:
        return [f for f in self.facts if f.kind == kind and (not out or f.out == out)]

    def features(self) -> list[str]:
        return sorted({f.kind for f in self.facts})


def is_bit(a: str) -> bool:
    try:
        return parse_device(a, 16).is_bit
    except ValueError:
        return False


def spec_hash(level: Level, nc=()) -> str:
    data = [i18n.lang(), sorted(level.idle.items()), level.settle, sorted(nc),
            [[[s.op, s.addr, s.value, s.dur, s.arg, [(c.addr, c.op, c.value, c.rel) for c in s.conds]] for s in c.steps]
             for c in level.cases]]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]


def analyze_spec(level: Level, devices=None, xy_base: int = 8) -> Profile:
    devices = list(devices or [])
    rows = iolist.rows(devices, xy_base)
    p = Profile(names=panel_names(rows), nc=nc_inputs(rows))
    if level.is_fault_hunt:
        return p
    users = user_inputs(devices, xy_base)
    p.idle = {a: int(nc) for a, nc, _ in users} | dict(level.idle)
    p.hash = spec_hash(level, p.nc)
    _walk(level, p)
    _physics(level, p, rows, {a for a, _, _ in users})
    _issues(level, p, rows)
    _suggest(level, p, devices, users)
    return p


# ======================= อ่านเงื่อนไข =======================
def _add(p: Profile, kind, at, **kw) -> Fact:
    for f in p.facts:
        if f.kind == kind and all(getattr(f, k) == v for k, v in kw.items() if k in ("out", "inp", "other")):
            if at not in f.at:
                f.at.append(at)
            if kind == "delay":                # แคบลงตามหลักฐานใหม่
                lo, hi = max(f.lo, kw["lo"]), min(f.hi, kw["hi"])
                if lo < hi:
                    f.lo, f.hi = lo, hi
            return f
    f = Fact(kind, at=[at], **kw)
    p.facts.append(f)
    return f


def _walk(level: Level, p: Profile):
    outs, ins = [], []
    for ci, case in enumerate(level.cases):
        steps = case.steps[level.reset_len:]
        val = dict(p.idle)
        known: dict[str, int] = {}             # ค่า output ที่เพิ่งตรวจ
        press: tuple[str, float] | None = None # (input ที่กดล่าสุด, เวลาที่ผ่านไปหลังกดอย่างน้อย)
        order: list[str] = []                  # input ที่ถูกกด (ขอบ) ในข้อนี้ตามลำดับ
        count: dict[str, int] = {}
        low: dict[str, float] = {}             # output → เวลาหลังกดที่ยังต้องดับอยู่
        low_n: dict[str, int] = {}             # output → จำนวนครั้งที่กดแล้วยังต้องดับ
        since = 0.0
        flips: dict[str, int] = {}
        for si, s in enumerate(steps):
            at = (ci, si)
            if s.op == "pulse" or s.op == "set":
                if s.addr not in ins:
                    ins.append(s.addr)
                base = p.idle.get(s.addr, int(s.addr in p.nc))
                active = s.op == "pulse" or s.value != base
                if active:
                    press, since = s.addr, 0.0
                    order.append(s.addr)
                    count[s.addr] = count.get(s.addr, 0) + 1
                    low.clear()
                    flips.clear()
                val[s.addr] = base if s.op == "pulse" else s.value
                since += s.dur if s.op == "pulse" else 0.0
                continue
            if s.op == "wait":
                since += s.dur
                continue
            if s.op in ("word", "part"):
                press = s.addr or None
                since = 0.0
                low.clear()
                continue
            if not s.conds:
                continue
            for c in s.conds:
                if c.addr.startswith(("Y", "M")) and c.addr not in outs:
                    outs.append(c.addr)
                if not is_bit(c.addr):
                    _add(p, "word", at, out=c.addr)
            bits = {c.addr: c.value for c in s.conds if c.op in ("=", "==") and c.value in (0, 1) and c.addr.startswith("Y")}
            if s.op == "hold":
                for y, v in bits.items():
                    if v == 0 and press:
                        low[y] = max(low.get(y, 0.0), since + s.dur)
                        low_n[y] = count.get(press, 0)
                    released = press is not None and val.get(press) == p.idle.get(press, int(press in p.nc))
                    if v == 1 and known.get(y) == 1 and released and s.dur >= 0.3:
                        _add(p, "latch", at, out=y)
                on = [y for y, v in bits.items() if v == 1]
                off = [y for y, v in bits.items() if v == 0]
                live = on or [y for y, v in known.items() if v == 1 and y not in off]
                if len(set(order)) >= 2 and live and off and known.get(live[0]) == 1 and known.get(off[0]) != 1                         and any(f.inp == press for f in p.get("on", off[0])):
                    a, b = sorted((live[0], off[0]))
                    _add(p, "interlock", at, out=a, other=b)
                known.update(bits)
                since += s.dur
            elif s.op in ("expect", "waitfor"):
                turned = [y for y, v in bits.items() if v == 1 and known.get(y) != 1]
                dropped = [y for y, v in bits.items() if v == 0 and known.get(y) == 1]
                for y, v in bits.items():
                    if known.get(y) is not None and known[y] != v:
                        flips[y] = flips.get(y, 0) + 1
                        if flips[y] >= 3:
                            _add(p, "blink", at, out=y)
                for y in turned:
                    if press is None:
                        continue
                    n = count.get(press, 0)
                    if y in low and low[y] > 0.3 and n == low_n.get(y, n):
                        prev = [q for q in dropped if q != y]
                        if prev:
                            _add(p, "sequence", at, out=prev[0], other=y, inp=press, lo=low.get(y, 0.0), hi=since + s.dur)
                        else:
                            _add(p, "delay", at, out=y, inp=press, lo=low[y], hi=since + s.dur)
                    elif n >= 2 and low_n.get(y) == n - 1 and s.dur <= QUICK_S:
                        _add(p, "count", at, out=y, inp=press, lo=n, hi=n)
                    elif s.dur <= QUICK_S and since <= QUICK_S and (n == 1 or y not in low_n):
                        if n >= 2 and not p.get("on", y):
                            _add(p, "count", at, out=y, inp=press, lo=n, hi=n)
                        elif n == 1:
                            _add(p, "on", at, out=y, inp=press)
                for y in dropped:
                    if press is not None and s.dur <= QUICK_S and since <= QUICK_S:
                        _add(p, "off", at, out=y, inp=press)
                known.update(bits)
                low = {y: t for y, t in low.items() if y not in turned}
    p.outputs, p.inputs = outs, ins


def _physics(level, p: Profile, rows, users: set[str]):
    driven = {r.address for r in rows if r.io in ("in", "wordin") and r.prop != "address"}
    for c in level.cases:
        for s in c.steps:
            if s.op == "part":
                p.physics.append(tr("ใช้ชิ้นงานบนสายพาน"))
            for cd in s.conds:
                if cd.addr.startswith("X"):
                    p.physics.append(tr("รอสัญญาณ {0} จากอุปกรณ์บนผัง", cd.addr))
                elif not is_bit(cd.addr) or cd.rel:
                    p.physics.append(tr("ใช้ค่าตัวเลข {0}", cd.addr))
            if s.op == "word":
                p.physics.append(tr("ใช้ค่าตัวเลข {0}", s.addr))
            if s.addr in driven and s.addr not in users and s.op in ("set", "pulse"):
                p.physics.append(tr("ใช้สัญญาณ {0} จากอุปกรณ์บนผัง", s.addr))
    p.physics = list(dict.fromkeys(p.physics))


# ======================= ตรวจโจทย์ =======================
def _where(ci, si) -> str:
    return tr("ข้อ {0} ขั้น {1}", ci + 1, si + 1)


def _issues(level: Level, p: Profile, rows):
    seen: dict[tuple, list] = {}
    for ci, case in enumerate(level.cases):
        hist: list[tuple] = []
        first = True
        for si, s in enumerate(case.steps[level.reset_len:]):
            if s.op in ("expect", "hold", "waitfor"):
                vals: dict[str, set] = {}
                for c in s.conds:
                    if is_bit(c.addr) and not c.rel and not any(OPS[c.op](v, c.value) for v in (0, 1)):
                        p.issues.append(Issue("impossible", tr("{0}: {1} เป็นไปไม่ได้ — บิตมีค่าแค่ 0 หรือ 1", _where(ci, si), c), "error"))
                    if c.op in ("=", "==") and not c.rel:
                        vals.setdefault(c.addr, set()).add(c.value)
                for a, v in vals.items():
                    if len(v) > 1:
                        p.issues.append(Issue("conflict", tr("{0}: {1} ต้องเป็นสองค่าพร้อมกัน", _where(ci, si), a), "error"))
                if first and s.op in ("expect", "hold"):
                    for a, v in vals.items():
                        if is_bit(a) and len(v) == 1:
                            seen.setdefault((tuple(hist), a), []).append((ci, si, s.op, s.dur, next(iter(v))))
                first = False
            else:
                hist.append((s.op, s.addr, s.value, s.dur, s.arg))
            if s.op == "pulse" and s.addr in p.nc:
                p.issues.append(Issue("nc_pulse", tr("{0}: {1} เป็นปุ่ม NC — pulse จะเขียน 1 แล้ว 0 (กดค้าง) ให้ใช้ 'กดแล้วปล่อย'", _where(ci, si), s.addr)))
    for (_h, a), xs in seen.items():
        for i, (c1, s1, op1, d1, v1) in enumerate(xs):
            for c2, s2, op2, d2, v2 in xs[i + 1:]:
                if v1 == v2 or (op1 == op2 == "expect"):
                    continue
                hold_d = d1 if op1 == "hold" else d2
                if op1 == op2 or (d2 if op1 == "hold" else d1) < hold_d:
                    p.issues.append(Issue("conflict", tr("{0} กับ {1} ขัดกัน: ทำเหมือนกันแต่ {2} ต้องเป็นคนละค่า",
                                                         _where(c1, s1), _where(c2, s2), a), "error"))
    for a in p.nc:
        if level.idle.get(a, 1) == 0:
            p.issues.append(Issue("nc_idle", tr("ค่าพักของ {0} เป็น 0 แต่เป็นปุ่ม NC (ปกติ = 1)", a)))
    if rows:
        have = {r.address for r in rows}
        used = {c.addr for cs in level.cases for s in cs.steps for c in s.conds if c.addr[0] in "XY"}
        used |= {s.addr for cs in level.cases for s in cs.steps if s.addr[:1] == "X"}
        for a in sorted(used - have):
            p.issues.append(Issue("not_on_panel", tr("{0} ไม่มีบนผัง", a)))
        outs = {r.address for r in rows if r.io == "out" and r.address.startswith("Y")}
        free = sorted(outs - used)
        if free:
            p.issues.append(Issue("unchecked", tr("ยังไม่มีข้อไหนตรวจ {0}", ", ".join(free)), "info"))


def _stop_of(p: Profile, y: str, users) -> str:
    off = p.get("off", y) or p.get("off")
    if off:
        return off[0].inp
    for a, _nc, label in users:
        if "stop" in label.lower() or "หยุด" in label:  # i18n: skip
            return a
    return ""


def _suggest(level: Level, p: Profile, devices, users):
    def press(a):
        return press_rows(a, nc=a in p.nc)

    ys = [y for y in p.outputs if y.startswith("Y")]
    started: dict[str, tuple[str, float, int]] = {}
    for f in p.facts:
        if f.kind in ("on", "delay", "count") and f.out not in started:
            started[f.out] = (f.inp, f.hi + 1 if f.kind == "delay" else 0.5, int(f.lo) if f.kind == "count" else 1)
    for y, (x, t, n) in started.items():
        go = []
        for _ in range(n):
            go += press(x) + ([StepRow("wait", "0.3")] if n > 1 else [])
        go.append(StepRow("expect", f"{y} = 1 within {t:g}"))
        name = f"{p.names[y]} ({y})" if p.names.get(y) else y
        if not p.get("off", y):
            stop = _stop_of(p, y, users)
            case = CaseRow(tr("{0} ต้องหยุดได้", name), go + press(stop) + [StepRow("expect", f"{y} = 0 within 0.5")]) if stop and stop != x else None
            p.suggestions.append(Suggestion("stop", tr("ยังไม่ได้ตรวจว่า {0} หยุดได้", name), case))
        only_held = not p.get("latch", y) and not p.get("blink", y) and not p.get("count", y) and not any(y in (f.out, f.other) for f in p.get("sequence"))
        if only_held and p.get("off", y) and p.get("off", y)[0].inp != x:
            p.suggestions.append(Suggestion("latch", tr("ยังไม่ได้ตรวจว่า {0} ติดค้างหลังปล่อยปุ่ม", name),
                                            CaseRow(tr("{0} ติดค้าง", name), go + [StepRow("hold", f"{y} = 1 for 1")])))
    pairs = [(str(d.props.get("address", "")).upper(), str(d.props.get("addr_rev", "")).upper()) for d in devices
             if d.kind in ("motor_rev", "dc_motor")]
    pairs += [(str(d.props.get("addr_star", "")).upper(), str(d.props.get("addr_delta", "")).upper()) for d in devices
              if d.kind == "motor_yd"]
    for a, b in pairs:
        if not (a and b) or any({f.out, f.other} == {a, b} for f in p.get("interlock")):
            continue
        sa, sb = started.get(a), started.get(b)
        case = None
        if sa and sb and sa[2] == sb[2] == 1 and sa[0] != sb[0]:
            case = CaseRow(tr("กดสองทางพร้อมกัน"), press(sa[0]) + [StepRow("expect", f"{a} = 1 within {sa[1]:g}")] + press(sb[0])
                           + [StepRow("hold", f"{a} = 1 and {b} = 0 for 1")])
        p.suggestions.append(Suggestion("interlock", tr("ยังไม่ได้ตรวจว่า {0} กับ {1} ไม่ติดพร้อมกัน", a, b), case))
    idle_ok = any(not any(s.op in ("pulse", "set", "word", "part") for s in c.steps[level.reset_len:]) for c in level.cases)
    if ys and not idle_ok and started:
        conds = " and ".join(f"{y} = 0" for y in ys if y in started)
        p.suggestions.append(Suggestion("idle", tr("ยังไม่ได้ตรวจว่าไม่กดอะไรแล้วต้องไม่ทำงานเอง"),
                                        CaseRow(tr("ยังไม่กดอะไร"), [StepRow("hold", f"{conds} for 1")])))


# ======================= ข้อความ =======================
def fact_text(f: Fact, names: dict[str, str]) -> str:
    def n(a):
        return f"{names[a]} ({a})" if names.get(a) else a
    t = {"on": lambda: tr("{0} ทำให้ {1} ติดทันที", n(f.inp), n(f.out)),
         "off": lambda: tr("{0} ทำให้ {1} ดับ", n(f.inp), n(f.out)),
         "latch": lambda: tr("{0} ติดค้างหลังปล่อยปุ่ม (self-holding)", n(f.out)),
         "delay": lambda: tr("{0} ติดช้ากว่าการกด {1} ประมาณ {2:g}–{3:g} วินาที (Timer)", n(f.out), n(f.inp), f.lo, f.hi),
         "count": lambda: tr("{0} ติดเมื่อ {1} มาครบ {2} ครั้ง (Counter)", n(f.out), n(f.inp), int(f.lo)),
         "interlock": lambda: tr("{0} กับ {1} ห้ามติดพร้อมกัน (Interlock)", n(f.out), n(f.other)),
         "sequence": lambda: tr("{0} ทำงานก่อน แล้วสลับไป {1} (ลำดับขั้น)", n(f.out), n(f.other)),
         "blink": lambda: tr("{0} กระพริบ", n(f.out)),
         "word": lambda: tr("ตรวจค่าตัวเลข {0}", n(f.out))}[f.kind]()
    ev = ", ".join(_where(*a) for a in f.at[:3])
    return f"{t}  [{ev}] " + (tr("มั่นใจสูง") if f.sure else tr("มั่นใจปานกลาง"))


def summary_lines(p: Profile) -> list[str]:
    order = ("on", "off", "latch", "delay", "count", "interlock", "sequence", "blink", "word")
    return [fact_text(f, p.names) for f in sorted(p.facts, key=lambda f: order.index(f.kind))]
