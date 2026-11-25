"""เงื่อนไขแบบประโยค ↔ StepRow (ไม่ใช้ Qt).

Action = ประโยคหนึ่งบรรทัดในตัวสร้างเงื่อนไข เช่น "กด Start แล้วปล่อย" (ปุ่ม NC = set 0 / wait / set 1 ให้เอง)
แถวที่ไม่ได้แก้จะเขียนกลับเหมือนเดิมทุกตัวอักษร · แถวที่อ่านไม่ออกเป็น raw (คงข้อความเดิม)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import tr
from ..plc.device import parse_device
from .editor import CaseRow, LevelDraft, StepRow
from .engine import Cond, parse_step

DO = ("press", "down", "up", "word", "wait", "part")          # สิ่งที่ตัวตรวจทำ
CHECK = ("expect", "hold", "waitfor")                          # สิ่งที่ต้องเป็น
KINDS = DO + CHECK
PRESS_S = 0.3


def kind_name(kind: str) -> str:
    return {"press": tr("กดแล้วปล่อย"), "down": tr("กดค้าง / ON"), "up": tr("ปล่อย / OFF"), "word": tr("ตั้งค่าตัวเลข"),
            "wait": tr("รอ"), "part": tr("ปล่อยชิ้นงาน"), "expect": tr("ต้องเป็นภายในเวลา ★"),
            "hold": tr("ต้องคงอยู่ตลอด ★"), "waitfor": tr("รอจนกว่า (ไม่นับคะแนน)"), "raw": tr("คำสั่งเขียนเอง")}[kind]


@dataclass
class Action:
    kind: str
    addr: str = ""
    value: int = 0
    dur: float = 0.0
    arg: str = ""
    conds: list[Cond] = field(default_factory=list)
    msg: str = ""
    hint: str = ""
    extra: dict = field(default_factory=dict)
    rows: list[StepRow] = field(default_factory=list)      # ต้นฉบับ (ใช้เมื่อยังไม่ถูกแก้)

    def touch(self):
        self.rows = []

    @property
    def is_check(self) -> bool:
        return self.kind in ("expect", "hold")


def num(x: float) -> str:
    return f"{x:g}"


def cond_text(c: Cond) -> str:
    return f"{c.addr} {c.op} {'+' if c.rel else ''}{c.value}"


def press_rows(addr: str, dur: float = PRESS_S, nc: bool = False, msg: str = "", hint: str = "") -> list[StepRow]:
    if nc:
        return [StepRow("set", f"{addr} 0", msg, hint), StepRow("wait", num(dur)), StepRow("set", f"{addr} 1")]
    return [StepRow("pulse", f"{addr} {num(dur)}", msg, hint)]


def to_actions(rows: list[StepRow], nc: set[str] = frozenset(), xy_base: int = 8) -> list[Action]:
    out, i = [], 0
    while i < len(rows):
        r = rows[i]
        try:
            s = parse_step(r.to_raw(), xy_base)
        except (ValueError, TypeError):
            out.append(Action("raw", rows=[r]))
            i += 1
            continue
        a = Action(s.op, s.addr, s.value, s.dur, s.arg, list(s.conds), r.msg, r.hint, dict(r.extra), [r])
        if s.op == "pulse":
            if s.addr in nc:                          # pulse = เขียน 1 แล้ว 0 → กับปุ่ม NC ไม่ใช่การกดปล่อย
                a.kind = "raw"
            else:
                a.kind = "press"
        elif s.op == "set":
            rest = rows[i + 1:i + 3]
            if s.addr in nc and s.value == 0 and len(rest) == 2 and not any(x.msg or x.hint or x.extra for x in rest):
                try:
                    w, u = (parse_step(x.to_raw(), xy_base) for x in rest)
                    if w.op == "wait" and w.dur <= 1.0 and u.op == "set" and u.addr == s.addr and u.value == 1:
                        a.kind, a.dur, a.rows = "press", w.dur, [r, *rest]
                        out.append(a)
                        i += 3
                        continue
                except ValueError:
                    pass
            if s.value not in (0, 1):
                a.kind = "raw"
            else:
                a.kind = "down" if s.value == (0 if s.addr in nc else 1) else "up"
        out.append(a)
        i += 1
    return out


def to_rows(actions: list[Action], nc: set[str] = frozenset()) -> list[StepRow]:
    out = []
    for a in actions:
        out += a.rows if a.rows else _make(a, nc)
    return out


def _make(a: Action, nc: set[str]) -> list[StepRow]:
    k, is_nc = a.kind, a.addr in nc
    if k == "press":
        rows = press_rows(a.addr, a.dur or PRESS_S, is_nc, a.msg, a.hint)
        rows[0].extra = dict(a.extra)
        return rows
    if k in ("down", "up"):
        op, text = "set", f"{a.addr} {int((k == 'down') != is_nc)}"
    elif k == "word":
        op, text = "word", f"{a.addr} {a.value}"
    elif k == "wait":
        op, text = "wait", num(a.dur)
    elif k == "part":
        op, text = "part", a.arg or "metal"
    elif k in CHECK:
        word = "for" if k == "hold" else "within"
        op, text = k, " and ".join(cond_text(c) for c in a.conds) + f" {word} {num(a.dur)}"
    else:
        return []
    return [StepRow(op, text, a.msg, a.hint, dict(a.extra))]


def default_action(kind: str, inputs: list[str], outputs: list[str]) -> Action:
    x, y = (inputs or ["X0"])[0], (outputs or ["Y0"])[0]
    if kind in ("press", "down", "up"):
        return Action(kind, addr=x, dur=PRESS_S)
    if kind == "word":
        return Action(kind, addr="D0", value=1)
    if kind == "wait":
        return Action(kind, dur=1.0)
    if kind == "part":
        return Action(kind, arg="metal")
    return Action(kind, conds=[Cond(y, "=", 1)], dur={"expect": 0.5, "hold": 1.0, "waitfor": 5.0}[kind])


# ======================= ประโยคภาษาคน =======================
def device_name(addr: str, names: dict[str, str]) -> str:
    n = names.get(addr, "")
    return f"{n} ({addr})" if n else addr


def cond_sentence(c: Cond, names: dict[str, str]) -> str:
    n = device_name(c.addr, names)
    if c.rel:
        return tr("{0} เพิ่มขึ้น {1} {2}", n, c.op, c.value)
    try:
        bit = parse_device(c.addr, 16).is_bit
    except ValueError:
        bit = False
    if bit and c.op in ("=", "==") and c.value in (0, 1):
        return tr("{0} ติด", n) if c.value else tr("{0} ดับ", n)
    return f"{n} {c.op} {c.value}"


def sentence(a: Action, names: dict[str, str] | None = None) -> str:
    names = names or {}
    n, cs = device_name(a.addr, names), tr(" และ ").join(cond_sentence(c, names) for c in a.conds)
    k = a.kind
    if k == "press":
        return tr("กด {0} แล้วปล่อย", n)
    if k == "down":
        return tr("กด {0} ค้างไว้", n)
    if k == "up":
        return tr("ปล่อย {0}", n)
    if k == "word":
        return tr("ตั้ง {0} = {1}", n, a.value)
    if k == "wait":
        return tr("รอ {0} วินาที", num(a.dur))
    if k == "part":
        return tr("ปล่อยชิ้นงาน {0}", a.arg)
    if k == "expect":
        return tr("{0} ต้องเป็นจริงภายใน {1} วินาที", cs, num(a.dur))
    if k == "hold":
        return tr("{0} ต้องคงอยู่ตลอด {1} วินาที", cs, num(a.dur))
    if k == "waitfor":
        return tr("รอจน {0} (ไม่เกิน {1} วินาที)", cs, num(a.dur))
    return a.rows[0].text if a.rows else ""


# ======================= ข้อมูลจากผัง =======================
def panel_names(rows) -> dict[str, str]:
    """address → ชื่อ (จาก iolist.rows)."""
    out: dict[str, str] = {}
    for r in rows:
        if r.address not in out and not r.is_reference:
            out[r.address] = (r.label or r.device) + (f" · {r.role}" if r.role and r.prop != "address" else "")
    return out


def nc_inputs(rows) -> set[str]:
    return {r.address for r in rows if r.io == "in" and r.contact == "NC"}


USER_KINDS = ("pushbutton", "selector", "selector3", "estop")


def user_inputs(devices, xy_base: int = 8) -> list[tuple[str, bool, str]]:
    """input ที่คนกด: [(address, เป็น NC, ชื่อ)] — ไม่รวมเซนเซอร์ที่อุปกรณ์บนผังส่งเอง."""
    out = []
    for d in devices:
        if d.kind not in USER_KINDS:
            continue
        for prop, io, raw in d.all_io():
            if io != "in" or not raw:
                continue
            try:
                a = parse_device(raw, xy_base).name
            except ValueError:
                continue
            nc = prop == "address" and str(d.props.get("contact", "NO")).upper() == "NC"
            out.append((a, nc, str(d.props.get("label", "") or "")))
    return out


def auto_setup(d: LevelDraft, devices, xy_base: int = 8) -> LevelDraft:
    """เติมค่าพักของทุกปุ่มที่ยังไม่มี และขั้นตอน reset (กด Stop) ถ้ายังว่าง."""
    stop = None
    for a, nc, label in user_inputs(devices, xy_base):
        d.idle.setdefault(a, int(nc))
        low = label.lower()
        if stop is None and ("stop" in low or "หยุด" in low):  # i18n: skip
            stop = (a, nc)
    if stop and not d.reset:
        d.reset = press_rows(stop[0], PRESS_S, stop[1])
    return d


# ======================= แม่แบบ =======================
@dataclass(frozen=True)
class Template:
    key: str
    name: str
    help: str
    roles: tuple = ()           # (key, ชื่อ, "in"/"out")
    params: tuple = ()          # (key, ชื่อ, ค่าเริ่มต้น, ต่ำสุด, สูงสุด, ทศนิยม)


def templates() -> list[Template]:
    start, stop = ("start", tr("ปุ่ม Start"), "in"), ("stop", tr("ปุ่ม Stop"), "in")
    sec = ("sec", tr("เวลา (วินาที)"), 3.0, 1.0, 60.0, 1)
    return [
        Template("selfhold", tr("กดติด – กดดับ"), tr("กด Start ติดค้าง กด Stop ดับ"), (start, stop, ("out", tr("เอาต์พุต"), "out"))),
        Template("ondelay", tr("หน่วงเวลาติด"), tr("กด Start แล้วรอครบเวลาจึงติด"),
                 (start, stop, ("out", tr("เอาต์พุต"), "out")), (sec,)),
        Template("counter", tr("นับจำนวน"), tr("นับครบแล้วติด กด Reset แล้วเริ่มใหม่"),
                 (("sensor", tr("อินพุตที่นับ"), "in"), ("stop", tr("ปุ่ม Reset"), "in"), ("out", tr("เอาต์พุต"), "out")),
                 (("n", tr("จำนวนนับ"), 3, 2, 50, 0),)),
        Template("interlock", tr("สลับทาง (Interlock)"), tr("สองทางทำงานพร้อมกันไม่ได้"),
                 (("start", tr("ปุ่มทางที่ 1"), "in"), ("start2", tr("ปุ่มทางที่ 2"), "in"), stop,
                  ("out", tr("เอาต์พุต 1"), "out"), ("out2", tr("เอาต์พุต 2"), "out"))),
        Template("sequence", tr("ทำงานเป็นลำดับ"), tr("ตัวแรกทำงานครบเวลา แล้วสลับไปตัวที่สอง"),
                 (start, stop, ("out", tr("เอาต์พุต 1"), "out"), ("out2", tr("เอาต์พุต 2"), "out")), (sec,)),
        Template("blank", tr("ว่าง — ใส่เงื่อนไขเอง"), tr("เริ่มจาก 1 ข้อ แล้วเพิ่มเองในตัวแก้ไข")),
    ]


def build_cases(key: str, roles: dict[str, str], params: dict | None = None, nc: set[str] = frozenset()) -> list[CaseRow]:
    """ข้อตรวจเริ่มต้นของแม่แบบ."""
    p = params or {}
    g = roles.get

    def press(role, dur=PRESS_S):
        return press_rows(g(role), dur, g(role) in nc)

    def expect(cond, t=0.5, msg="", hint=""):
        return StepRow("expect", f"{cond} within {num(t)}", msg, hint)

    def hold(cond, t=1.0, msg="", hint=""):
        return StepRow("hold", f"{cond} for {num(t)}", msg, hint)

    y, y2 = g("out", "Y0"), g("out2", "Y1")
    if key == "selfhold":
        return [CaseRow(tr("กด Start แล้วติดค้าง"), [*press("start"), expect(f"{y} = 1", 0.5, tr("กด Start → ติด")),
                                              hold(f"{y} = 1", 1.5, tr("ปล่อย Start แล้วยังติดค้าง"))]),
                CaseRow(tr("กด Stop แล้วดับ"), [*press("start"), expect(f"{y} = 1", 0.5, tr("กด Start → ติด")), *press("stop"),
                                          expect(f"{y} = 0", 0.5, tr("กด Stop → ดับ")),
                                          hold(f"{y} = 0", 1.0, tr("ปล่อย Stop แล้วยังดับอยู่"))]),
                CaseRow(tr("ยังไม่กดอะไร"), [hold(f"{y} = 0", 1.0, tr("ไม่กด Start ต้องไม่ติดเอง"))])]
    if key == "ondelay":
        s = float(p.get("sec", 3))
        early = round(max(0.3, s - 0.6), 2)
        return [CaseRow(tr("ครบเวลาแล้วติด"), [*press("start"), hold(f"{y} = 0", early, tr("ยังไม่ครบเวลาต้องไม่ติด")),
                                           expect(f"{y} = 1", 1.2, tr("ครบเวลาแล้วติด")), hold(f"{y} = 1", 1.0, tr("ติดค้าง"))]),
                CaseRow(tr("กด Stop แล้วดับ"), [*press("start"), expect(f"{y} = 1", s + 1, tr("ครบเวลาแล้วติด")), *press("stop"),
                                          expect(f"{y} = 0", 0.5, tr("กด Stop → ดับ"))]),
                CaseRow(tr("กด Stop ก่อนครบเวลา"), [*press("start"), StepRow("wait", "0.4"), *press("stop"),
                                              hold(f"{y} = 0", s + 0.8, tr("ยกเลิกแล้วต้องไม่ติด"))])]
    if key == "counter":
        n = int(p.get("n", 3))
        one = [*press("sensor"), StepRow("wait", "0.3")]
        return [CaseRow(tr("นับครบแล้วติด"), [*(one * (n - 1)), hold(f"{y} = 0", 0.6, tr("นับยังไม่ครบต้องไม่ติด")), *press("sensor"),
                                          expect(f"{y} = 1", 0.5, tr("นับครบแล้วติด"))]),
                CaseRow(tr("Reset แล้วเริ่มนับใหม่"), [*(one * n), expect(f"{y} = 1", 0.5, tr("นับครบแล้วติด")), *press("stop"),
                                                expect(f"{y} = 0", 0.5, tr("กด Reset → ดับ")), *(one * (n - 1)),
                                                hold(f"{y} = 0", 0.6, tr("เริ่มนับใหม่จากศูนย์"))])]
    if key == "interlock":
        return [CaseRow(tr("ทางที่ 1"), [*press("start"), expect(f"{y} = 1", 0.5, tr("กดปุ่ม 1 → เอาต์พุต 1 ติด")), *press("start2"),
                                      hold(f"{y} = 1 and {y2} = 0", 1.0, tr("กดปุ่ม 2 ซ้อน ต้องไม่สลับ/ไม่ติดพร้อมกัน"))]),
                CaseRow(tr("ทางที่ 2"), [*press("start2"), expect(f"{y2} = 1", 0.5, tr("กดปุ่ม 2 → เอาต์พุต 2 ติด")), *press("start"),
                                      hold(f"{y2} = 1 and {y} = 0", 1.0, tr("กดปุ่ม 1 ซ้อน ต้องไม่สลับ/ไม่ติดพร้อมกัน"))]),
                CaseRow(tr("กด Stop แล้วดับ"), [*press("start"), expect(f"{y} = 1", 0.5, tr("กดปุ่ม 1 → เอาต์พุต 1 ติด")), *press("stop"),
                                          expect(f"{y} = 0 and {y2} = 0", 0.5, tr("กด Stop → ดับ"))])]
    if key == "sequence":
        s = float(p.get("sec", 3))
        return [CaseRow(tr("สลับตามลำดับ"), [*press("start"), expect(f"{y} = 1 and {y2} = 0", 0.5, tr("เริ่มที่เอาต์พุต 1")),
                                         hold(f"{y} = 1 and {y2} = 0", round(max(0.3, s - 0.8), 2), tr("ยังไม่ครบเวลา เอาต์พุต 1 ยังติด")),
                                         expect(f"{y} = 0 and {y2} = 1", 1.6, tr("ครบเวลา → สลับไปเอาต์พุต 2"))]),
                CaseRow(tr("กด Stop แล้วดับ"), [*press("start"), expect(f"{y} = 1", 0.5, tr("เริ่มที่เอาต์พุต 1")), *press("stop"),
                                          expect(f"{y} = 0 and {y2} = 0", 0.5, tr("กด Stop → ดับ"))])]
    x = g("start", "X0")
    return [CaseRow(tr("ข้อ 1"), [*press_rows(x, PRESS_S, x in nc), expect(f"{y} = 1", 0.5)])]
