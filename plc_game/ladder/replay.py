"""เล่น ladder ซ้ำกับ I/O ที่วัดได้ตอนตรวจด่าน แล้วชี้หน้าสัมผัสที่ทำให้ข้อนั้นไม่ผ่าน.

ลำดับ: เทียบผลจำลองกับที่วัดได้ก่อน (ไม่ตรง = ไม่สรุป) → หาหน้าสัมผัส → ลองแก้ทีละจุดแล้วเล่นซ้ำ
"""
from __future__ import annotations

import bisect
import re
import time
from dataclasses import dataclass, field

from ..ai.analyzer import Finding, _inputs_info, _name
from ..i18n import tr
from ..levels.engine import OPS
from ..panel.watch import blocks_for
from ..plc.device import device_range, parse_device
from .csvio import Instr, Program
from .model import COMPARE, CONTACT_OPS, KNOWN_FUNC, Ladder, base_func, bit_name, cells, join_op
from .sim import Sim
from .static import _one_shot, _show, is_accumulating, static_findings, where

GRID_S = 0.05
TOL_S = 0.25              # SLMP ของ GX Simulator3 ตอบทุก ~100 ms
BUDGET_S = 8.0
MAX_EXPLAIN = 3
MAX_WATCH = 96
MAX_BLOCKS = 10
MAX_NO = {"X": 1023, "Y": 1023, "M": 7679, "L": 7679, "D": 7999, "TS": 511, "TN": 511, "CS": 255, "CN": 255, "SM": 4094}
_WRITE = re.compile(r"^(\w+) ← (-?\d+)$")


def watch_addresses(L: Ladder) -> list[str]:
    """address ใน ladder ที่ควรอ่านเพิ่มระหว่างตรวจ (SLMP ของโปรแกรมนี้อ่านได้เฉพาะชนิดเหล่านี้)."""
    names = list(dict.fromkeys([*L.written, *L.read]))
    names = [n for n in names if _readable(n, L.app_base)][:MAX_WATCH]
    keep: set[str] = set()                        # ก้อนละ 1 request → จำกัดไว้ ไม่ให้อ่าน PLC ช้าลงมาก
    for b in blocks_for(names, L.app_base)[:MAX_BLOCKS]:
        keep |= {d.name for d in device_range(b.head, b.count, L.app_base)}
    return [n for n in names if n in keep]


def _readable(name: str, base: int) -> bool:
    """อยู่ในช่วงที่ PLC ทุกรุ่นที่ใช้มีจริง — อ่านเกินช่วงทำให้ PLC ตอบ error แล้วหลุด."""
    try:
        d = parse_device(name, base)
    except ValueError:
        return False
    return d.number <= MAX_NO.get(d.kind, -1)


class Recording:
    """สัญญาณที่วัดได้ + การเขียนของตัวตรวจ."""

    def __init__(self, runner):
        self.trace = runner.trace
        self.times = [t for t, _ in self.trace]
        self.names = {n for _, s in self.trace for n in s}
        self.writes = [(t, m.group(1), int(m.group(2))) for t, e in runner.events if (m := _WRITE.match(e))]
        self.end = max([self.times[-1] if self.times else 0.0] + [r.t_end for r in runner.results])
        # จุดเวลาที่ scan: ทุกครั้งที่ค่าเปลี่ยน (ซ้ำอีก 2 scan) + ทุก GRID_S
        pts = {round(i * GRID_S, 4) for i in range(int(self.end / GRID_S) + 5)}
        for t in self.times:
            pts |= {t, t + 0.004, t + 0.008}
        self.points = sorted(pts)

    def at(self, name, t):
        i = bisect.bisect_right(self.times, t + 1e-9) - 1
        return self.trace[max(i, 0)][1].get(name)

    def end_of(self, r) -> float:
        """สิ้นสุดช่วงที่ใช้ดูข้อที่ไม่ผ่าน: เผื่อความหน่วงการอ่าน แต่ไม่ล้ำไปหลัง input เปลี่ยน (ขึ้นข้อถัดไป)."""
        end = r.t_end + TOL_S
        for i in range(bisect.bisect_right(self.times, r.t_end + 1e-9), len(self.times)):
            t, s = self.trace[i]
            if t > end:
                break
            if any(s.get(n) != self.trace[i - 1][1].get(n) for n in s if n.startswith("X")):
                return max(r.t_end, t - 0.005)
        return end

    def settled_from(self, t: float) -> float:
        """เวลาที่ input ซึ่งเพิ่งเขียนก่อน t อ่านกลับได้ตรงแล้ว."""
        out = t
        for tw, a, v in self.writes:
            if t - 0.6 <= tw <= t + 0.01:
                i = bisect.bisect_left(self.times, tw - 1e-9)
                for tt, s in self.trace[i:]:
                    if tt > t + 0.6:
                        break
                    if s.get(a) == v:
                        out = max(out, tt)
                        break
        return out


@dataclass
class Run:
    t: list[float] = field(default_factory=list)
    v: list[dict] = field(default_factory=list)

    def window(self, t0, t1):
        return range(bisect.bisect_left(self.t, t0 - 1e-9), bisect.bisect_right(self.t, t1 + 1e-9))


def simulate(L: Ladder, rec: Recording, track, until: float | None = None, probe=None) -> Run:
    """เล่น ladder ซ้ำ; probe(t, sim) เรียกหลังทุก scan."""
    first = rec.trace[0][1]
    ext = [n for n in rec.names if n not in L.written or n.startswith("X")]
    sim = Sim(L, {n: first.get(n) for n in rec.names})
    run, ti, wi, prev = Run(), 0, 0, None
    forced = [(t, a, v) for t, a, v in rec.writes if a in L.written and not a.startswith("X")]
    for t in rec.points:
        if until is not None and t > until:
            break
        while ti < len(rec.times) and rec.times[ti] <= t + 1e-9:
            snap = rec.trace[ti][1]
            for n in ext:
                sim.mem[n] = snap.get(n)
            ti += 1
        while wi < len(forced) and forced[wi][0] <= t + 1e-9:
            sim.mem[forced[wi][1]] = forced[wi][2]
            wi += 1
        sim.scan(0.0 if prev is None else t - prev)
        prev = t
        run.t.append(t)
        run.v.append({n: sim.mem.get(n, 0) for n in track})
        if probe:
            probe(t, sim)
    return run


# ======================= ตรงกับที่วัดไหม =======================
def mismatches(L: Ladder, rec: Recording, run: Run, until: float) -> list[tuple[str, float, int, int]]:
    """[(address, เวลา, วัดได้, จำลองได้)] — ต้องต่างกันต่อเนื่องเกินความคลาดเคลื่อนของการอ่าน."""
    xs = [t for (t, s), (_, p) in zip(rec.trace[1:], rec.trace)
          if any(s.get(n) != p.get(n) for n in s if n.startswith("X"))]
    out = []
    for n in sorted(rec.names):
        y = n.startswith("Y")
        if not (y or n in L.written and re.match(r"^(M|L|D|CN|CS)\d+$", n)):
            continue
        simv = [d.get(n) for d in run.v] if n in L.written else [0] * len(run.t)
        if _oscillates(run.t, simv, xs):
            continue
        for i, t in enumerate(run.t):
            if t > until - TOL_S:
                break
            m = rec.at(n, t)
            if t < TOL_S or m is None:
                continue
            near = [simv[j] for j in run.window(t - TOL_S, t + TOL_S)]
            if None not in near and all(_same(n, v, m) is False for v in near):
                out.append((n, t, m, simv[i]))
                break
    return sorted(out, key=lambda e: e[1])


def _same(name, a, b) -> bool:
    if name.startswith(("Y", "M", "L", "CS")):
        return bool(a) == bool(b)
    return (int(a) & 0xFFFF) == (int(b) & 0xFFFF)


def _oscillates(ts, vs, xs) -> bool:
    """เปลี่ยนเอง ≥ 4 ครั้งโดย X ไม่เปลี่ยน (ไฟกระพริบ) — เฟสเลื่อนได้ เทียบเวลาตรง ๆ ไม่ได้."""
    count, seg = 0, -1
    for i in range(1, len(vs)):
        s = bisect.bisect_right(xs, ts[i])
        if s != seg:
            seg, count = s, 0
        if vs[i] != vs[i - 1]:
            count += 1
            if count >= 4:
                return True
    return False


# ======================= ตัดสินข้อจากผลจำลอง =======================
def judge(r, rec: Recording, run: Run):
    """ผลของการตรวจข้อ r ในการจำลอง: True / False / None (ไม่รู้)."""
    t0 = rec.settled_from(r.t_start)
    t1 = max(rec.end_of(r) if r.op == "hold" and not r.passed else r.t_end, t0) + 0.02
    idx = run.window(t0 + 0.01, t1)
    vals = []
    for i in idx:
        v = 1
        for c, tgt in zip(r.conds, r.targets):
            x = run.v[i].get(c.addr)
            if c.addr not in run.v[i] or x is None:
                v = None if v else 0
            elif not OPS[c.op](int(x), tgt):
                v = 0
        vals.append(v)
    if not vals:
        return None
    if r.op == "expect":
        # ผ่านเร็วในของจริง = บันทึกสั้นกว่ากำหนด ถ้ายังไม่เป็นจริงในช่วงนั้นจึงยังตัดสินไม่ได้
        return True if 1 in vals else None if None in vals or r.t_end < r.t_start + r.dur - 1e-6 else False
    return False if 0 in vals else None if None in vals else True


# ======================= อธิบาย =======================
def _want(c, tgt):
    ok = [v for v in (0, 1) if OPS[c.op](v, tgt)]
    return ok[0] if len(ok) == 1 else None


def _moment(L, rec, r, addr, want):
    """(เวลา, sim ณ เวลานั้น) ที่ใช้อธิบาย: hold = จังหวะแรกที่ผิด, expect = จังหวะที่เหลือหน้าสัมผัสขวางน้อยสุด."""
    t0 = rec.settled_from(r.t_start)
    ks = [k for k in L.written.get(addr, ()) if L.instrs[k].op in (("SET", "OUT", "OUTH") if want else ("RST", "OUT", "OUTH"))]
    start = t0
    if r.op == "expect":
        near = [t for t, a, v in rec.writes if r.t_start - 0.7 <= t <= r.t_start + 0.01]
        start = min(near + [t0])
    best: list = [None]

    def probe(t, sim):
        if t < start + 0.005 or r.op == "hold" and best[0] is not None:
            return
        val = sim.mem.get(addr)
        if val is None or int(bool(val)) == want:
            return
        opts = []
        for k in ks:
            need = 1 if L.instrs[k].op in ("SET", "RST") else want
            b = sim.blockers(L.tree.get(k), need)
            opts.append((k, need, b))
        n = min((len(b) for _, _, b in opts if b), default=99)
        if best[0] is None or n < best[0][0]:
            best[0] = (n, t, dict(sim.mem), opts, _upstream(L, sim, opts))

    simulate(L, rec, (), max(rec.end_of(r) if r.op == "hold" else r.t_end, t0) + 0.02, probe)
    return best[0]


def _upstream(L, sim, opts) -> dict[str, list[int]]:
    """หน้าสัมผัสที่เป็น M/T/C: ใครทำให้มันเป็นแบบนั้น (หนึ่งชั้น)."""
    out: dict[str, list[int]] = {}
    todo = [k for _, _, b in opts for k in b]
    for _ in range(3):
        nxt = []
        for k in todo:
            a = L.args[k][0] if L.kinds[k] == "contact" and L.args[k] else None
            if not isinstance(a, tuple) or a[0] in ("X", "Y") or bit_name(a) in out:
                continue
            n, on = bit_name(a), bool(sim.mem.get(bit_name(a)))
            outs = [w for w in L.written.get(n, ()) if L.instrs[w].op in ("OUT", "OUTH")]
            if len(outs) == 1:
                b = sim.blockers(L.tree.get(outs[0]), 0 if on else 1) if a[0] not in ("T", "C", "ST") or not on else []
                out[n] = b or outs
                nxt += b
                if a[0] in ("T", "C", "ST"):
                    out[n] = list(dict.fromkeys([*out[n], *outs])) if b else outs
            elif not outs:                           # M ที่ SET/RST: คำสั่งฝั่งตรงข้ามที่ยังไม่ทำงาน
                for w in L.written.get(n, ()):
                    if L.instrs[w].op == ("RST" if on else "SET"):
                        b = sim.blockers(L.tree.get(w), 1)
                        out[n] = list(dict.fromkeys([*out.get(n, []), *(b or [w])]))
                        nxt += b
                    else:                            # ฝั่งที่ทำให้เป็นค่านี้ (อาจทำงานเร็วไป) รวม timer ที่สั่งมัน
                        lv = _leaves(L.tree.get(w))
                        ts = [bit_name(L.args[j][0]) for j in lv if L.kinds[j] == "contact" and L.args[j][0] and L.args[j][0][0] in ("T", "C", "ST")]
                        out.setdefault("~" + n, []).extend([w, *lv, *(x for t in ts for x in L.written.get(t, ()) if L.instrs[x].op != "RST")])
        todo = nxt
    return out


def _external(rec, name) -> bool:
    """ค่าที่อุปกรณ์บนผัง/ตัวตรวจป้อนให้ PLC (ladder ไม่ได้เขียนก็ถูกแล้ว)."""
    return name.startswith("X") or any(a == name for _, a, _ in rec.writes) \
        or not name.startswith("Y") and len({s.get(name) for _, s in rec.trace}) > 1


def _external_hint(L, rec, r) -> Finding | None:
    """ข้อที่รอสัญญาณจากผัง: บอก output ที่ดับไปก่อน (ตัวที่ขับสัญญาณนั้น)."""
    names = [c.addr for c in r.conds]
    if not names or any(n in L.written or not _external(rec, n) for n in names):
        return None
    last = None
    for (t0, a), (t, b) in zip(rec.trace, rec.trace[1:]):
        if r.t_start + 0.02 < t <= r.t_end + 1e-6:
            off = [n for n in b if n.startswith("Y") and n in L.written and a.get(n) and not b.get(n)]
            if off:
                last = (t, off)
                break
    lines = [tr("{0} มาจากอุปกรณ์บนผัง ไม่ได้มาจากคำสั่งใน ladder", ", ".join(dict.fromkeys(names)))]
    step = None
    if last:
        for n in last[1][:2]:
            ks = [k for k in L.written[n] if L.instrs[k].op in ("OUT", "RST")][:2]
            lines.append(tr("{0} ดับที่ {1:.2f} วินาที ก่อนถึงค่าที่ต้องการ — ดู {2}", n, last[0], ", ".join(where(L, k) for k in ks)))
            step = step if step is not None or not ks else L.instrs[ks[0]].step
    return Finding(tr("{0}: {1}", r.case, r.msg), lines, "error" if last else "info", kind="ladder", step=step)


def _repeat_hint(L, r) -> Finding | None:
    """ค่าที่ไม่รู้เพราะ INC/DEC ทุก scan: ชี้คำสั่งนั้น."""
    for k in _cone(L, [c.addr for c in r.conds]):
        if is_accumulating(L, k) and not _one_shot(L, L.tree.get(k)):
            return Finding(tr("{0}: {1} ทำงานซ้ำทุก scan ขณะเงื่อนไขเป็นจริง", r.case, L.instrs[k].text),
                           [where(L, k), tr("ถ้าต้องการให้ทำครั้งเดียวต่อการกด ใช้ขอบขาขึ้น (LDP / คำสั่งลงท้าย P)"),
                            tr("ความมั่นใจ: {0}", tr("น่าจะเป็น"))], "error", kind="ladder", step=L.instrs[k].step)
    return None


def _contact_line(L, k, mem, info) -> str:
    a = L.args[k][0] if L.args[k] else None
    if L.kinds[k] == "contact" and isinstance(a, tuple):
        n = bit_name(a)
        v = mem.get(n)
        return tr("{0} — ขณะนั้น {1} = {2}", where(L, k), _name(info, n) if n in info else _show(n), "?" if v is None else int(bool(v)))
    return where(L, k)


def _explain(L, rec, r, info) -> tuple[Finding | None, set | tuple]:
    for c, tgt in zip(r.conds, r.targets):
        want = _want(c, tgt)
        bit = re.match(r"^(X|Y|M|L|TS|CS)\w+$", c.addr)
        if c.addr not in L.written:
            if c.addr.startswith(("Y", "M", "D", "CN")) and not _external(rec, c.addr) and rec.at(c.addr, r.t_end) is not None \
                    and not OPS[c.op](int(rec.at(c.addr, r.t_end)), tgt):
                return Finding(tr("{0}: ไม่มีคำสั่งเขียน {1} ใน ladder", r.case, c.addr),
                               [tr("โจทย์ตรวจ output นี้ แต่ไม่พบคอยล์/SET ที่ใช้ address นี้ในไฟล์ CSV")], "error", kind="ladder"), ()
            continue
        if not bit or want is None:
            continue
        end = rec.at(c.addr, r.t_end)
        if r.op == "expect" and end is not None and OPS[c.op](int(end), tgt):
            continue                                 # ตัวนี้ได้ตามต้องการแล้ว ตัวอื่นต่างหากที่ไม่ผ่าน
        m = _moment(L, rec, r, c.addr, want)
        if not m:
            continue
        _, t, mem, opts, up = m
        opts = [o for o in opts if o[2]] or opts
        if not opts:
            continue
        lines, seen = [], set()
        for k, need, b in opts[:2]:
            if not b:
                lines.append(tr("{0} กำลังทำงานอยู่ แต่ค่าถูกคำสั่งอื่นเขียนทับ", where(L, k)))
            for j in b[:3]:
                if j in seen:
                    continue
                seen.add(j)
                lines.append(_contact_line(L, j, mem, info))
                a = L.args[j][0] if L.kinds[j] == "contact" and L.args[j] else None
                if isinstance(a, tuple) and bit_name(a) in up:
                    u = up[bit_name(a)][0]
                    n = _show(bit_name(a))
                    lines.append(tr("{0} ทำงานแล้ว: ดู {1}", n, where(L, u)) if mem.get(bit_name(a))
                                 else tr("{0} ยังไม่ทำงาน: ดู {1}", n, where(L, u)))
        writers = [L.instrs[k].op for k in L.written[c.addr]]
        if want:
            title = tr("{0}: {1} ไม่ ON — หน้าสัมผัสที่ตัดวงจร (t={2:.2f} s)", r.case, c.addr, t)
        elif "RST" in writers:
            title = tr("{0}: {1} ไม่ OFF — RST ยังไม่ทำงานหรือถูก SET ซ้ำ (t={2:.2f} s)", r.case, c.addr, t)
        else:
            title = tr("{0}: {1} ไม่ OFF — หน้าสัมผัสที่ยังจ่ายวงจร (t={2:.2f} s)", r.case, c.addr, t)
        focus = {k for k, _, _ in opts} | {j for _, _, b in opts for j in b} | {j for u in up.values() for j in u}
        return Finding(title, lines, "error", kind="ladder", step=L.instrs[opts[0][0]].step), focus
    return None, ()


# ======================= ลองแก้ทีละจุด =======================
@dataclass
class Fix:
    instrs: list[Instr]
    k: int
    kind: str
    arg: str = ""


def _cone(L: Ladder, addrs, depth=4) -> list[int]:
    """output ที่มีผลต่อ address เหล่านี้ (ไล่ย้อนตามหน้าสัมผัส)."""
    todo, seen, outs = list(addrs), set(addrs), []
    for _ in range(depth):
        nxt = []
        for a in todo:
            for k in L.written.get(a, ()):
                if k in outs:
                    continue
                outs.append(k)
                for n in L.effects(k)[1]:            # ค่าต้นทางของ MOV / + − × ÷
                    if n not in seen:
                        seen.add(n)
                        nxt.append(n)
                for j in _leaves(L.tree.get(k)):
                    for x in L.args[j]:
                        if isinstance(x, tuple):
                            for n in ({bit_name(x), *cells(x)} if x[0] != "K" else x[2]):
                                if n not in seen:
                                    seen.add(n)
                                    nxt.append(n)
        todo = nxt
    return outs


def _leaves(node):
    if node is None:
        return []
    return [node.i] if node.kind == "leaf" else [j for x in node.kids for j in _leaves(x)]


@dataclass
class Hints:
    """ข้อมูลจากโจทย์/การวัดที่ใช้เลือกค่าลองแก้."""
    need: set = field(default_factory=set)           # address ที่โจทย์ตรวจ (ไม่ย้ายคอยล์ของมันไปที่อื่น)
    nums: list = field(default_factory=list)         # ตัวเลขในโจทย์
    words: list = field(default_factory=list)        # D ที่ตัวตรวจ/ผังป้อน
    xs: list = field(default_factory=list)           # X ทุกตัวที่วัด


CMP_SWAP = {"<": (">", "<="), ">": ("<", ">="), "<=": (">=", "<"), ">=": ("<=", ">"), "=": ("<>", ">="), "<>": ("=",)}


def fixes(L: Ladder, r, inputs: list[str], hints: Hints | None = None):
    """สร้าง ladder ที่แก้ 1 จุด เรียงจากความผิดที่พบบ่อย (ชื่อใน CSV เป็นฐานของไฟล์เอง)."""
    I, hints = L.instrs, hints or Hints()
    addrs = [c.addr for c in r.conds]
    outs = _cone(L, addrs)
    raw = {}                                         # ชื่อในโปรแกรม → ชื่อในไฟล์
    for row, ins in zip(L.args, I):
        for a, s in zip(row, ins.args):
            if isinstance(a, tuple):
                raw.setdefault(a[1], s)

    def sub(k, *new):
        return [*I[:k], *new, *I[k + 1:]]

    def mk(k, op, *args):
        return Instr(I[k].step, op, tuple(args))

    last = {k for k in outs if not (k + 1 < len(I) and L.kinds[k + 1] == "out")}
    # 1) คอยล์ผิดเลข
    for a in addrs:
        if a.startswith("Y") and a not in L.written:
            for k, ins in enumerate(I):
                if ins.op in ("OUT", "SET") and ins.args and L.args[k][0] and L.args[k][0][0] == "Y" \
                        and L.args[k][0][1] not in addrs and L.args[k][0][1] not in hints.need:
                    yield Fix(sub(k, mk(k, ins.op, _to_file(L, a))), k, "coil")
    # 2) double coil
    for a in addrs:
        dup = [k for k in L.written.get(a, ()) if I[k].op == "OUT"]
        for k in dup if len(dup) > 1 else ():
            yield Fix(sub(k, mk(k, "NOP")), k, "double")
    # 3) ลืม self-holding
    for k in outs:
        if I[k].op == "OUT" and k in last and L.args[k][0] and L.args[k][0][0] in ("Y", "M", "L"):
            lv = _leaves(L.tree.get(k))
            if lv and not any(I[j].args[:1] == I[k].args[:1] for j in lv):
                j = lv[0]
                yield Fix([*I[:j + 1], mk(j, "OR", I[k].args[0]), *I[j + 1:]], k, "hold", I[k].args[0])
    # 4) หน้าสัมผัส: สลับ NO/NC, ขอบสัญญาณ, ตัดออก, address ผิด
    leaves = list(dict.fromkeys(j for k in outs for j in _leaves(L.tree.get(k)) if L.kinds[j] == "contact"))
    for j in leaves:
        head, mod = CONTACT_OPS[I[j].op]
        if mod in ("", "I"):
            yield Fix(sub(j, mk(j, join_op(head, "" if mod else "I"), *I[j].args)), j, "invert")
    # 5) ค่า K
    for k in outs:
        if I[k].op in ("OUT", "OUTH") and len(I[k].args) > 1 and isinstance(L.args[k][1], int):
            kv = L.args[k][1]
            vals = [kv * 10, kv // 10, kv * 2, kv // 2, kv + 1, kv - 1, kv * 3, kv // 3, kv * 5, kv // 5,
                    kv + 10, kv - 10, kv + 20, kv - 20, kv * 3 // 2, kv * 2 // 3]
            for v in dict.fromkeys(vals):
                if 0 < v <= 32767 and v != kv:
                    yield Fix(sub(k, mk(k, I[k].op, I[k].args[0], f"K{v}")), k, "k+" if v > kv else "k-")
    # 5ข) คำสั่งตัวเลข: เครื่องหมายเปรียบเทียบ, ค่า K, D ต้นทาง
    cmps = list(dict.fromkeys(j for k in outs for j in _leaves(L.tree.get(k)) if L.kinds[j] == "compare"))
    for j in cmps:
        head, o = COMPARE.match(I[j].op).groups()
        d = "D" if o[0] == "D" else ""
        for new in CMP_SWAP[o.lstrip("D")]:
            yield Fix(sub(j, mk(j, head + d + new, *I[j].args)), j, "cmp")
    for k in [*outs, *cmps]:
        f = base_func(I[k].op)[0]
        if k not in cmps and f not in KNOWN_FUNC and not (f in ("OUT", "OUTH") and len(I[k].args) == 2):
            continue
        n_src = len(I[k].args) if k in cmps else max(len(I[k].args) - 1, 0)
        for p in range(n_src) if f not in ("OUT", "OUTH") else (1,):
            a = L.args[k][p]
            if isinstance(a, int) and f not in ("OUT", "OUTH"):
                for v in dict.fromkeys([*hints.nums, a + 1, a - 1, a * 10, a // 10]):
                    if v != a and -32768 <= v <= 32767 and not (v == 0 and f == "/"):
                        yield Fix(sub(k, mk(k, I[k].op, *I[k].args[:p], f"K{v}", *I[k].args[p + 1:])), k, "const" if k not in cmps else "k+" if v > a else "k-")
            if isinstance(a, int) or isinstance(a, tuple) and a[0] == "D":
                for n in hints.words:
                    if n != (a[1] if isinstance(a, tuple) else ""):
                        yield Fix(sub(k, mk(k, I[k].op, *I[k].args[:p], n, *I[k].args[p + 1:])), k, "src", n)
    for k in outs:                                   # ลืมกันค่าเกินช่วง
        f, a0 = base_func(I[k].op)[0], (L.args[k][0] if L.args[k] else None)
        if f in ("INC", "DEC") and isinstance(a0, tuple) and k in last:
            lims = ["K0"] if f == "DEC" else [*hints.words, *(f"K{v}" for v in hints.nums)]
            for v in lims:
                if v != a0[1]:
                    yield Fix([*I[:k], mk(k, "AND>" if f == "DEC" else "AND<", I[k].args[0], v), *I[k:]], k, "limit", v)
    for a in addrs:                                  # ลืม RST
        sets = [k for k in L.written.get(a, ()) if I[k].op == "SET"]
        if sets:
            end = next((k for k, i in enumerate(I) if i.op in ("END", "FEND")), len(I))
            for n in hints.xs:
                yield Fix([*I[:end], mk(sets[0], "LD", _to_file(L, n)), mk(sets[0], "RST", I[sets[0]].args[0]), *I[end:]], sets[0], "rst", n)
    for j in leaves:
        head, mod = CONTACT_OPS[I[j].op]
        a = L.args[j][0]
        if not isinstance(a, tuple):
            continue
        if mod == "" and a[0] in ("X", "M"):
            yield Fix(sub(j, mk(j, join_op(head, "P"), *I[j].args)), j, "edge")
        pool = dict.fromkeys([*inputs, *hints.xs]) if a[0] == "X" else []
        for n in pool:
            if n != a[1]:
                yield Fix(sub(j, mk(j, I[j].op, _to_file(L, n))), j, "addr")
    # 6) เพิ่มหน้าสัมผัส (interlock / ปุ่มหยุด)
    ys = [n for n in L.written if n.startswith("Y")] + [n for n in L.written if re.match(r"^M\d+$", n)][:8]
    for k in outs:
        if I[k].op in ("OUT", "SET") and k in last and L.args[k][0] and L.args[k][0][0] in ("Y", "M"):
            used = {I[j].args[0] for j in _leaves(L.tree.get(k)) if I[j].args}
            for n in [*inputs, *ys]:
                f = raw.get(n) or (n if n[0] == "M" else _to_file(L, n))
                if f not in used and f != I[k].args[0]:
                    for op in ("ANI", "AND"):
                        yield Fix([*I[:k], mk(k, op, f), *I[k:]], k, "block", f)
    for j in leaves:
        head, _ = CONTACT_OPS[I[j].op]
        if head != "LD":
            yield Fix(sub(j, mk(j, "NOP")), j, "drop")


def _to_file(L: Ladder, name: str) -> str:
    """ชื่อ X/Y ของโปรแกรม → ฐานเลขของไฟล์ CSV."""
    n = int(name[1:], L.app_base)
    return name[0] + (format(n, "o") if L.prog.xy_base == 8 else format(n, "X"))


def _fix_text(L, f: Fix) -> str:
    w = where(L, f.k)
    return {
        "coil": tr("คอยล์น่าจะผิดเลข — {0}", w),
        "double": tr("คอยล์ซ้ำกันทับค่า — {0}", w),
        "hold": tr("น่าจะขาดหน้าสัมผัสค้างตัวเอง (self-holding) ของ {0} — {1}", f.arg, w),
        "invert": tr("ชนิดหน้าสัมผัส NO/NC น่าจะกลับด้าน — {0}", w),
        "cmp": tr("เครื่องหมายเปรียบเทียบน่าจะผิด — {0}", w),
        "const": tr("ค่า K น่าจะผิด — {0}", w),
        "src": tr("ค่าต้นทางน่าจะเป็น {0} — {1}", f.arg, w),
        "limit": tr("น่าจะขาดเงื่อนไขกันค่าเกินช่วง (เทียบกับ {0}) — {1}", f.arg, w),
        "rst": tr("น่าจะขาดคำสั่ง RST ของ {0} (เช่น เมื่อ {1}) — {2}", L.instrs[f.k].args[0], f.arg, w) if f.kind == "rst" else "",
        "some": tr("น่าจะขาดหน้าสัมผัสในวงจรนี้ (มีหลายตัวที่เป็นไปได้ เช่น {0}) — {1}", f.arg, w),
        "k+": tr("ค่า K น่าจะน้อยเกินไป — {0}", w),
        "k-": tr("ค่า K น่าจะมากเกินไป — {0}", w),
        "edge": tr("น่าจะต้องใช้ขอบขาขึ้น — {0}", w),
        "addr": tr("address ของหน้าสัมผัสน่าจะผิด — {0}", w),
        "block": tr("น่าจะขาดหน้าสัมผัส {0} ในวงจรนี้ — {1}", f.arg, w),
        "drop": tr("หน้าสัมผัสนี้อาจเกินมา — {0}", w),
    }[f.kind]


def search(L: Ladder, rec, results, r, inputs, physics, stop, focus=(), hints=None) -> list[Fix]:
    """ลองแก้ทีละจุด: ข้อ r ต้องผ่าน และข้อที่เคยผ่านต้องไม่เสีย — คืนเรียงตามจำนวนข้อที่แก้ได้
    focus = ลำดับคำสั่งบนเส้นวงจรที่ขัดข้อง: ถ้ามีจุดแก้อยู่ในนี้ ไม่เสนอจุดอื่นที่บังเอิญผ่าน"""
    track = {c.addr for x in results for c in x.conds} | {n for n in L.written if n.startswith("Y")}
    ys = [n for n in track if n in L.written]
    i0 = results.index(r)
    good = [x for i, x in enumerate(results) if x.passed and (i < i0 or not physics)]
    other = [x for x in results if not x.passed and not x.skipped and x is not r and not physics]
    later = []                                        # ในขั้นตอนที่ตามมาของข้อเดียวกัน (ใช้จัดอันดับ ไม่ใช้ตัดสิน)
    for x in results[i0 + 1:] if physics else ():
        if x.case != r.case:
            break
        if x.passed:
            later.append(x)
    until = max(x.t_end for x in [r, *good, *other, *later]) + 0.3
    base = simulate(L, rec, track, until)
    if judge(r, rec, base) is not False:
        return []
    good = [x for x in good if judge(x, rec, base)]
    found = []
    gaps = [(i, t1 - t0) for i, (t0, t1) in enumerate(zip(base.t, base.t[1:])) if t1 <= r.t_start]

    def changed(run) -> int:
        """output เปลี่ยนไปจากเดิมกี่ครึ่งวินาทีในช่วงก่อนข้อที่ไม่ผ่าน (แก้ถูกจุดมักไม่กระทบส่วนที่ดีอยู่)."""
        return int(sum(dt for i, dt in gaps if i < len(run.v) and any(run.v[i].get(y) != base.v[i].get(y) for y in ys)) / 0.5)

    todo = sorted(enumerate(fixes(L, r, inputs, hints)), key=lambda e: e[1].k not in focus and e[1].kind != "rst")
    for n, f in todo:
        if stop():
            break
        L2 = Ladder(L.prog.with_instrs(f.instrs), L.app_base)
        run = simulate(L2, rec, track, r.t_end + 0.3)
        if judge(r, rec, run) is not True:
            continue
        run = simulate(L2, rec, track, until)
        if all(judge(x, rec, run) is not False for x in good):
            found.append((-sum(judge(x, rec, run) is True for x in other), -sum(judge(x, rec, run) is True for x in later),
                          f.k not in focus and f.kind != "rst", changed(run), -sum(judge(x, rec, run) is True for x in good), n, f))
    found.sort(key=lambda e: e[:6])
    return [e[-1] for e in found if e[:4] == found[0][:4]]


# ======================= ทางเข้าหลัก =======================
def diagnose(prog: Program, level, runner, devices=None, app_base: int = 8, budget: float = BUDGET_S,
             cancel=lambda: False) -> list[Finding]:
    """วิเคราะห์ ladder หลังตรวจด่าน (ไม่มีผลต่อคะแนน)."""
    deadline = time.monotonic() + budget

    def stop():
        return cancel() or time.monotonic() > deadline

    L = Ladder(prog, app_base)
    info = _inputs_info(devices or [])
    known = set(level.addresses()) | {str(raw or "").strip().upper() for d in devices or [] for _, _, raw in d.all_io()}
    static = static_findings(L, level, known)
    notes: list[Finding] = []
    if L.unknown_ops:
        names = list(dict.fromkeys(L.instrs[k].text for k in L.unknown_ops))
        notes.append(Finding(tr("อ่านไม่ออก {0} คำสั่งใน ladder — ส่วนที่ขึ้นกับคำสั่งเหล่านี้จะไม่สรุป", len(names)),
                             [", ".join(names[:6])], "info", kind="ladder"))
    if L.flow:
        ops = list(dict.fromkeys(L.instrs[k].op for k in L.flow))
        return [Finding(tr("ladder ใช้คำสั่งกระโดด/โปรแกรมย่อย/SFC ({0}) — จำลองไม่ได้", ", ".join(ops)), [], "info", kind="ladder"),
                *static, *notes]
    if len(runner.trace) < 2 or not runner.results:
        return static + notes
    rec = Recording(runner)
    fails = [r for r in runner.results if not r.passed and not r.skipped]
    track = {n for n in rec.names if n in L.written} | {c.addr for r in runner.results for c in r.conds}
    base = simulate(L, rec, track)
    end = fails[-1].t_end if fails else rec.end
    diff = mismatches(L, rec, base, end)
    if diff:
        n, t, m, s = diff[0]
        stale = Finding(tr("ไฟล์ CSV ไม่ตรงกับโปรแกรมที่รันอยู่ใน PLC"),
                        [tr("{0} ที่ {1:.2f} วินาที: วัดได้ {2} แต่ ladder ในไฟล์ควรได้ {3}", n, t, m, s),
                         tr("Export ไฟล์ใหม่ และ Write โปรแกรมลง PLC ก่อนตรวจอีกครั้ง (หรือมีหลายโปรแกรมในโปรเจกต์)")], "warn", kind="ladder")
        fails = [r for r in fails if r.t_end < t]
        if not fails:
            return [stale, *notes]
        static = []
        notes.insert(0, stale)
    inputs = sorted({a for _, a, _ in rec.writes if a.startswith("X")} | {a for a in level.idle if a.startswith("X")})
    driven = set(inputs)
    physics = any(len({s.get(n) for _, s in rec.trace}) > 1 for n in rec.names
                  if n not in driven and n not in L.written and n.startswith(("X", "D")))
    words = [n for n in dict.fromkeys([*(a for _, a, _ in rec.writes), *sorted(rec.names)])
             if re.match(r"^D\d+$", n) and (n not in L.written and _external(rec, n))][:4]
    words += [n for n in L.written if re.match(r"^D\d+$", n)][:6]
    nums = [t for x in runner.results for c, t in zip(x.conds, x.targets) if c.addr.startswith(("D", "CN"))]
    nums = [int(v) for v in re.findall(r"(?<![A-Za-z0-9.])\d{1,5}(?![0-9.])", str(getattr(level, "desc", "")))] + nums
    hints = Hints({c.addr for x in runner.results for c in x.conds}, [v for v in dict.fromkeys(nums) if 0 < v <= 32767][:14], words,
                  sorted(n for n in rec.names if n.startswith("X")))
    out: list[Finding] = []
    for r in fails[:MAX_EXPLAIN]:
        if cancel():
            return []
        if physics and out:                          # เครื่องค้างผิดสภาพจากข้อแรก: อธิบายข้อถัดไปมักชี้ผิดจุด
            notes.append(Finding(tr("แก้ข้อแรกก่อนแล้วตรวจใหม่ — ข้อถัดไปอาจไม่ผ่านเพราะข้อแรก"), [], "info", kind="ladder"))
            break
        f, focus = _explain(L, rec, r, info)
        hit = search(L, rec, runner.results, r, inputs, physics, stop, focus, hints) if not stop() else []
        if f is None and not hit:
            verdict = judge(r, rec, base)
            hint = _external_hint(L, rec, r) or (_repeat_hint(L, r) if verdict is None else None)
            if hint:
                hint.check = runner.results.index(r)
                out.append(hint)
            elif verdict is None:
                out.append(Finding(tr("{0}: ข้อมูลไม่พอให้สรุปจาก ladder", r.case),
                                   [tr("เลือกไฟล์ CSV ไว้ก่อนกดตรวจ เพื่อให้โปรแกรมอ่านค่า M/T/C/D เพิ่มระหว่างตรวจ")], "info", kind="ladder"))
            elif not diff:
                out.append(Finding(tr("{0}: ยังชี้จุดผิดใน ladder ไม่ได้", r.case),
                                   [tr("จำลองแล้วข้อนี้ผ่าน — อาจเป็นเรื่องจังหวะเวลาสั้น ๆ ให้ดูผลจาก I/O ด้านบน") if verdict
                                    else tr("จำลองแล้วไม่ผ่านเหมือนกัน แต่หาจุดแก้จุดเดียวไม่พบ ให้ดูผลจาก I/O ด้านบน")], "info", kind="ladder"))
            continue
        f = f or Finding(tr("{0}: {1}", r.case, r.msg), [], "error", kind="ladder")
        f.check = runner.results.index(r)
        picks: list[Fix] = []
        for x in hit:
            if x.kind == "src" and any(p.k == x.k for p in picks):
                continue                             # ค่า K ที่แก้แล้วผ่านน่าเชื่อกว่าเปลี่ยนไปใช้ D
            alt = {y.arg for y in hit if (y.k, y.kind) == (x.k, x.kind)}
            if x.kind == "block" and len(alt) > 1:
                x = Fix(x.instrs, x.k, "some", x.arg)
            if all((x.k, x.kind) != (p.k, p.kind) for p in picks):
                picks.append(x)
            if len(picks) == 2:
                break
        if picks:
            f.lines.append(tr("จุดที่น่าแก้ (ลองจำลองแล้วข้อนี้ผ่านและไม่พบว่าข้ออื่นเสีย):"))
            f.lines += [_fix_text(L, p) for p in picks]
            f.step = L.instrs[picks[0].k].step
        f.lines.append(tr("ความมั่นใจ: {0}", tr("ยืนยันด้วยการจำลอง") if picks and not physics and len({x.k for x in hit}) == 1 or picks and len({x.k for x in hit}) == 1 and picks[0].kind == "coil"
                          else tr("น่าจะเป็น")))
        out.append(f)
    return notes[:1] + out + notes[1:] if diff else out + static + notes
