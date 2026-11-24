"""ตัววิเคราะห์ในเครื่อง (ไม่ต้องใช้อินเทอร์เน็ต): อ่านผลตรวจด่าน + สัญญาณที่บันทึกไว้ แล้วบอกสาเหตุที่น่าจะเป็น.

ใช้กฎจากความผิดพลาดที่พบบ่อยของผู้เริ่มเขียน ladder เช่น ลืม self-holding, ใช้ NO/NC กลับด้าน,
ไม่มี interlock, ตั้งค่า K ของ Timer/Counter ผิด, นับซ้ำเพราะไม่ใช้คำสั่งขอบขาขึ้น
ทุกข้อสรุปอ้างอิงจากเวลาและค่าที่วัดได้จริง — ไม่ตรวจรูปแบบ ladder
"""
from __future__ import annotations

from ..i18n import tr, tr_data

import re
from dataclasses import dataclass, field

from ..panel.catalog import CATALOG
from ..panel.model import DeviceSpec
from ..plc.device import parse_device

_WRITE = re.compile(r"^(\w+) ← (-?\d+)$")


@dataclass
class Finding:
    title: str
    lines: list[str] = field(default_factory=list)
    level: str = "error"           # error / warn / info / ok
    check: int | None = None       # ลำดับใน runner.results
    kind: str = ""                 # "ladder" = มาจาก CSV ของ GX Works3 (อธิบายเท่านั้น ไม่ให้คะแนน)
    step: int | None = None        # เลข step ใน ladder

    def text(self) -> str:
        return self.title + "".join(f"\n   • {s}" for s in self.lines)


class Trace:
    """ค่าของแต่ละสัญญาณตามเวลา (จาก snapshot ที่บันทึกเฉพาะตอนเปลี่ยน)."""

    def __init__(self, trace: list[tuple[float, dict]], events: list[tuple[float, str]]):
        self.trace = trace
        self.writes = [(t, m.group(1), int(m.group(2))) for t, e in events if (m := _WRITE.match(e))]

    def value_at(self, addr: str, t: float) -> int:
        v = 0
        for tt, snap in self.trace:
            if tt > t + 1e-9:
                break
            v = int(snap.get(addr, 0) or 0)
        return v

    def changes(self, addr: str, t0: float = -1e9, t1: float = 1e9) -> list[tuple[float, int]]:
        out, prev = [], None
        for tt, snap in self.trace:
            v = int(snap.get(addr, 0) or 0)
            if prev is not None and v != prev and t0 <= tt <= t1:
                out.append((tt, v))
            prev = v
        return out

    def ever(self, addr: str, value: int = 1) -> bool:
        return any(int(s.get(addr, 0) or 0) == value for _, s in self.trace)

    def addresses(self) -> set[str]:
        return {a for _, s in self.trace for a in s}

    def last_write_before(self, t: float, window: float = 1e9):
        cand = [w for w in self.writes if t - window <= w[0] <= t + 1e-9]
        return cand[-1] if cand else None

    def rising_writes(self, addr: str, t0: float, t1: float) -> int:
        return sum(1 for t, a, v in self.writes if a == addr and v == 1 and t0 <= t <= t1)


def _inputs_info(devices: list[DeviceSpec]) -> dict[str, tuple[str, bool]]:
    """address → (ชื่ออุปกรณ์, เป็น NC ไหม)."""
    out = {}
    for d in devices:
        name = tr_data(str(d.props.get("label") or "")) or d.kind
        for prop, io_, raw in d.all_io():
            a = str(raw or "").strip().upper()
            if io_ != "in" or not a.startswith("X"):
                continue
            main = prop == "address"
            label = name if main else f"{name} {CATALOG[d.kind].slot(prop).label}"
            if main or a not in out:
                out[a] = (label, main and str(d.props.get("contact", "NO")).upper() == "NC")
    return out


def _pressed(info, addr: str, value: int) -> bool:
    """การเขียนค่านี้คือการ "กด" ไหม (ปุ่ม NC: กด = 0)."""
    return value == (0 if addr in info and info[addr][1] else 1)


def _is_word(addr: str) -> bool:
    try:
        return not parse_device(addr, 16).is_bit
    except ValueError:
        return True


def _name(info, addr) -> str:
    return f"{info[addr][0]} ({addr})" if addr in info else addr


# ======================= วิเคราะห์ผลตรวจด่าน =======================
def analyze(level, runner, devices: list[DeviceSpec] | None = None) -> list[Finding]:
    devices = devices or []
    trc = Trace(runner.trace, runner.events)
    info = _inputs_info(devices)
    out: list[Finding] = []

    danger = _danger_findings(devices, trc.trace)
    if runner.total and runner.passed == runner.total:
        return [Finding(tr("✔ ผ่านทุกข้อ ได้ 3 ดาว"), [tr("ลองใส่ความผิดปกติ (แท็บ ครู) แล้วดูว่าโปรแกรมรับมือได้ไหม")], "ok")] + danger
    if len(runner.trace) < 2:
        return [Finding(tr("ไม่ได้รับข้อมูลจาก PLC ระหว่างตรวจ"),
                        [tr("ตรวจว่ากด เชื่อมต่อ แล้ว และสถานะมุมขวาล่างเป็น ONLINE"),
                         tr("GX Simulator3 ต้องเปิดอยู่ และ PLC อยู่ในโหมด RUN")])]

    # ---- input ไปไม่ถึง PLC ----
    lost = sorted({a for t, a, v in trc.writes if a.startswith("X") and v == 1 and not trc.ever(a, 1)})
    if lost:
        out.append(Finding(tr("ค่า Input ที่ตัวตรวจกดไปไม่ถึง PLC: ") + ", ".join(lost),
                           [tr("ตัวตรวจเขียนค่า 1 แล้ว แต่อ่านกลับได้ 0 ตลอด"),
                            tr("ladder อาจใช้คำสั่ง OUT กับ X นี้ หรือ PLC ไม่ได้อยู่ใน RUN")], "warn"))

    # ---- output ที่ไม่เคยทำงานเลย / ทำงานที่อื่นแทน ----
    need_on = sorted({c.addr for r in runner.results for c in r.conds
                      if c.addr.startswith("Y") and c.op in ("=", "==", ">=") and c.value >= 1})
    never = [a for a in need_on if not trc.ever(a, 1)]
    if never:
        others = sorted(a for a in trc.addresses() if a.startswith("Y") and a not in need_on and trc.ever(a, 1))
        lines = [tr("ตลอดการตรวจ output นี้เป็น 0 ทุกครั้ง"),
                 tr("ตรวจว่าเขียนคอยล์ใช้ address ตรงกับโจทย์ และ Write โปรแกรมลง PLC แล้ว")]
        if others:
            lines.append(tr("แต่มี ") + ", ".join(others) + tr(" ทำงาน — อาจเขียนคอยล์ผิดเลข"))
        out.append(Finding(tr("Output ไม่เคยทำงานเลย: ") + ", ".join(never), lines))

    # ---- FWD/REV พร้อมกัน ----
    out.extend(danger)

    # ---- เครื่องไปไม่ถึงตำแหน่ง/สถานะเริ่มต้นที่ข้อนั้นต้องใช้ ----
    failed_cases = {r.case_index for r in runner.results if not r.passed}
    for ci, t, text in getattr(runner, "notes", []):
        if ci in failed_cases:
            out.append(Finding(tr("{0}: เครื่องยังไม่พร้อมก่อนตรวจ", level.cases[ci].name),
                               [text, tr("ที่เวลา {0:.2f} วินาที — การตรวจหลังจากนี้ในข้อเดียวกันอาจไม่ผ่านตามไปด้วย", t)], "warn"))

    # ---- รายข้อที่ไม่ผ่าน (ข้อที่ถูกข้ามไม่วิเคราะห์ซ้ำ) ----
    first = True
    for i, r in enumerate(runner.results):
        if r.passed or r.skipped:
            continue
        f = _explain_check(r, trc, info, i)
        if first:
            f.title = tr("จุดที่ควรแก้ก่อน → ") + f.title
            first = False
        out.append(f)
    return out


def _danger_findings(devices, history) -> list[Finding]:
    """สัญญาณที่อันตรายต่อเครื่องจริง — เตือนแม้ผ่านครบทุกข้อ."""
    out: list[Finding] = []
    for d in devices:
        if d.kind == "motor_rev":
            a, b = str(d.props.get("address", "")).upper(), str(d.props.get("addr_rev", "")).upper()
            both = [t for t, s in history if s.get(a) and s.get(b)]
            if both:
                out.append(Finding(tr("อันตราย: {0} (หมุนหน้า) กับ {1} (หมุนกลับ) ON พร้อมกัน", a, b),
                                   [tr("เกิดที่เวลา {0:.2f} วินาที — ในงานจริงคือไฟลัดวงจรระหว่างเฟส", both[0]),
                                    tr("ใส่หน้าสัมผัส /{0} หน้าคอยล์ {1} และ /{2} หน้าคอยล์ {3} (Interlock)", b, a, a, b)]))
        if d.kind == "motor_yd":
            out.extend(_yd_findings(d, history))
        if d.kind == "vacuum":
            out.extend(_vac_findings(d, history))
        if d.kind == "dc_motor":
            out.extend(_dc_findings(d, history))
        if d.kind == "stepper":
            out.extend(_step_findings(d, history))
    return out


def _explain_check(r, trc: Trace, info, idx) -> Finding:
    f = Finding(f"{r.case}: {r.msg}", [r.detail] if r.detail else [], "error", idx)
    for c in r.conds:
        a = c.addr
        if _is_word(a):
            _explain_word(f, r, trc, c)
            continue
        want = c.value if c.op in ("=", "==") else None
        if want is None:
            continue
        actual = trc.value_at(a, r.t_end)
        if actual == want:
            continue
        if r.op == "hold":
            ch = trc.changes(a, r.t_start, r.t_end + 0.05)
            t_bad = ch[0][0] if ch else r.t_end
            w = trc.last_write_before(t_bad, 0.4)
            if want == 1 and w and w[1].startswith("X") and not _pressed(info, w[1], w[2]):
                f.lines.append(tr("{0} ดับทันทีหลังปล่อย {1} ({2:.2f} วินาที)", a, _name(info, w[1]), t_bad - w[0]))
                f.lines.append(tr("→ ไม่มีวงจรคงสถานะ: ต่อหน้าสัมผัส {0} ขนานกับ {1} (self-holding)", a, w[1]))
            elif want == 0:
                trig = _last_rising(trc, t_bad, info)
                if trig:
                    d = t_bad - trig[0]
                    f.lines.append(tr("{0} ON หลังกด {1} {2:.2f} วินาที — เร็วกว่าที่โจทย์กำหนด", a, _name(info, trig[1]), d))
                    if d > 0.25:
                        f.lines.append(tr("เวลานี้เท่ากับ Timer ประมาณ K{0} (หน่วย 100 ms) → ตรวจค่า K ของ Timer", round(d * 10)))
                n = max((trc.rising_writes(x, r.t_start - 10, t_bad) for x in _pulsed(trc, r, t_bad)), default=0)
                if n >= 2:
                    f.lines.append(tr("ขณะนั้น input ถูกกด/ผ่านไป {0} ครั้ง → ถ้าเป็น Counter ตรวจค่า K", n))
        else:  # expect
            press = _last_press(trc, info, r.t_start + 0.01, 1.2)
            if want == 1:
                was = trc.changes(a, r.t_start - 3, r.t_end)
                if was and was[-1][1] == 0:
                    f.lines.append(tr("{0} เคยทำงานแล้วดับไปที่ {1:.2f} วินาที ก่อนถึงจุดตรวจ", a, was[-1][0]))
                elif press:
                    _, x, label, _ = press
                    f.lines.append(tr("กด {0} ({1}) แล้ว {2} ไม่ทำงานเลย", label, x, a))
                    f.lines.append(tr("→ ตรวจว่ามีหน้าสัมผัส {0} อยู่ในวงจรของคอยล์ {1} และไม่มีหน้าสัมผัสอื่นตัดวงจรอยู่", x, a))
            else:
                if press:
                    _, x, label, nc = press
                    if nc:
                        f.lines.append(tr("{0} ({1}) บนผังเป็นแบบ NC: ปกติ = 1, ตอนกด = 0", label, x))
                        f.lines.append(tr("→ ใน ladder ต้องใช้หน้าสัมผัส NO ({0}) ต่ออนุกรม ไม่ใช่ /{1}", x, x))
                    else:
                        f.lines.append(tr("กด {0} ({1}) แล้ว {2} ยังไม่ดับ", label, x, a))
                        f.lines.append(tr("→ ใช้หน้าสัมผัส NC (/{0}) ต่ออนุกรมก่อนคอยล์ {1}", x, a))
                if trc.value_at(a, max(0.0, r.t_start - 2.0)) == 1 and not trc.changes(a, r.t_start - 2.0, r.t_end):
                    f.lines.append(tr("{0} ON ค้างตลอด — ถ้าใช้ SET ต้องมี RST ด้วย", a))
    if r.hint:
        f.lines.append(tr("คำแนะนำจากโจทย์: ") + r.hint)
    f.lines = list(dict.fromkeys(f.lines))          # ตัดบรรทัดซ้ำ (หลายเงื่อนไขชี้สาเหตุเดียวกัน)
    return f


def _last_press(trc: Trace, info, t: float, window: float):
    """การ "กด" input ครั้งล่าสุดก่อนเวลา t (ปุ่ม NC: กด = เขียน 0) → (เวลา, address, ชื่อ, เป็น NC)."""
    for tt, a, v in reversed(trc.writes):
        if tt > t:
            continue
        if tt < t - window:
            break
        if a in info:
            label, nc = info[a]
            if v == (0 if nc else 1):
                return tt, a, label, nc
    return None


def _explain_word(f: Finding, r, trc: Trace, c):
    a = c.addr
    v0, v1 = trc.value_at(a, r.t_start - 0.01), trc.value_at(a, r.t_end)
    if v0 == v1 and not trc.changes(a, r.t_start, r.t_end):
        f.lines.append(tr("{0} ไม่เปลี่ยนเลย (= {1}) — ยังไม่ได้เขียนคำสั่งนับ/คำนวณลง {2} หรือเขียนลง D อื่น", a, v1, a))
    else:
        steps = [v for _, v in trc.changes(a, r.t_start - 0.5, r.t_end)]
        jumps = [b - a_ for a_, b in zip([v0] + steps, steps)]
        if any(j > 1 for j in jumps) or len(steps) > 1 and c.rel and c.value <= 1:
            f.lines.append(tr("{0} เพิ่มขึ้นหลายครั้งต่อชิ้นงาน ({1} → {2}) — นับซ้ำทุกรอบ scan", a, v0, v1))
            f.lines.append(tr("→ ใช้คำสั่งแบบขอบขาขึ้น เช่น INCP หรือ PLS/LDP"))


def _pulsed(trc: Trace, r, t_bad):
    return {a for t, a, v in trc.writes if v == 1 and r.t_start - 10 <= t <= t_bad}


def _last_rising(trc: Trace, t: float, info):
    """การกด input ครั้งล่าสุดก่อนเวลา t (ปุ่ม NC: กด = เขียน 0)."""
    w = [(tt, a) for tt, a, v in trc.writes if _pressed(info, a, v) and tt <= t + 1e-9 and a.startswith("X")]
    return w[-1] if w else None


YD_MIN_STAR_S = 2.0      # ต่อสตาร์สั้นกว่านี้ก่อนเข้าเดลต้า = สลับเร็วเกิน


def _yd_findings(d: DeviceSpec, history) -> list[Finding]:
    """สตาร์-เดลต้า: KM2+KM3 พร้อมกัน (ลัดวงจร) และเข้าเดลต้าเร็วเกิน — ดูจากสัญญาณ Y อย่างเดียว."""
    m, y, dl = (str(d.props.get(k, "")).upper() for k in ("address", "addr_star", "addr_delta"))
    out = []
    both = [t for t, s in history if s.get(y) and s.get(dl)]
    if both:
        out.append(Finding(tr("อันตราย: {0} (สตาร์) กับ {1} (เดลต้า) ON พร้อมกัน — ลัดวงจร!", y, dl),
                           [tr("เกิดที่เวลา {0:.2f} วินาที", both[0]),
                            tr("ใส่หน้าสัมผัส /{0} หน้าคอยล์ {1} และ /{2} หน้าคอยล์ {3} (Interlock)", dl, y, y, dl),
                            tr("ปลดสตาร์ก่อน แล้วค่อยต่อเดลต้า (เว้นช่วงสั้น ๆ ด้วย Timer)")]))
    star_since = None
    fast = None
    for t, s in history:
        if s.get(m) and s.get(y):
            star_since = t if star_since is None else star_since
        if s.get(m) and s.get(dl) and not s.get(y):
            if star_since is None or t - star_since < YD_MIN_STAR_S:
                fast = (t, 0.0 if star_since is None else t - star_since)
                break
        if not s.get(m):
            star_since = None
    if fast:
        why = tr("ไม่ผ่านสตาร์เลย (เท่ากับต่อตรง กระแสกระชาก ~6 เท่า)") if star_since is None \
            else tr("ต่อสตาร์แค่ {0:.1f} วินาที รอบมอเตอร์ยังไม่ขึ้น", fast[1])
        out.append(Finding(tr("{0}: เข้าเดลต้าเร็วเกินไป", d.props.get('label', '')),
                           [tr("ที่เวลา {0:.2f} วินาที — {1}", fast[0], why),
                            tr("ใช้ Timer หน่วงช่วงสตาร์ 5–10 วินาที ก่อนสลับเป็นเดลต้า")], "warn"))
    return out


def _dc_findings(d: DeviceSpec, history) -> list[Finding]:
    """มอเตอร์ DC แปรงถ่าน: FWD+REV พร้อมกัน = ลัดวงจร (BLDC ใช้ EN/DIR จึงไม่มีปัญหานี้)."""
    if str(d.props.get("drive", "brushed") or "brushed") == "bldc":
        return []
    a, b = (str(d.props.get(k, "") or "").upper() for k in ("address", "addr_rev"))
    if not a or not b:
        return []
    both = [t for t, s in history if s.get(a) and s.get(b)]
    if not both:
        return []
    return [Finding(tr("อันตราย: {0} (เดินหน้า) กับ {1} (ถอยหลัง) ของมอเตอร์ DC ON พร้อมกัน — ลัดวงจร!", a, b),
                    [tr("เกิดที่เวลา {0:.2f} วินาที — รีเลย์กลับขั้วต่อขั้วบวกชนขั้วลบ", both[0]),
                     tr("ใส่หน้าสัมผัส /{0} หน้าคอยล์ {1} และ /{2} หน้าคอยล์ {3} (Interlock)", b, a, a, b)])]


def _step_findings(d: DeviceSpec, history) -> list[Finding]:
    """Stepper: สั่ง START (ขอบขาขึ้น) ตอน ENA ยังไม่ ON · สั่ง START ใหม่ระหว่าง BUSY."""
    ena, st, busy = (str(d.props.get(k, "") or "").upper() for k in ("address", "addr_start", "addr_busy"))
    if not ena or not st:
        return []
    out, prev = [], 0
    no_ena = during_busy = None
    for t, s in history:
        v = int(bool(s.get(st)))
        if v and not prev:
            if not s.get(ena) and no_ena is None:
                no_ena = t
            elif busy and s.get(busy) and during_busy is None:
                during_busy = t
        prev = v
    if no_ena is not None:
        out.append(Finding(tr("{0}: สั่ง START ({1}) ตอน ENA ({2}) ยังไม่ ON", d.props.get('label', ''), st, ena),
                           [tr("ที่เวลา {0:.2f} วินาที — ไดรฟ์ไม่รับคำสั่ง มอเตอร์ไม่ขยับ", no_ena),
                            tr("เปิด {0} ก่อน (ค้างไว้ตลอดที่ใช้งาน) แล้วค่อยสั่ง START", ena)], "warn"))
    if during_busy is not None:
        out.append(Finding(tr("{0}: สั่ง START ซ้ำขณะยังเคลื่อนอยู่ ({1} = 1)", d.props.get('label', ''), busy),
                           [tr("ที่เวลา {0:.2f} วินาที — ไดรฟ์ไม่รับคำสั่งใหม่จนกว่าจะเคลื่อนเสร็จ", during_busy),
                            tr("รอ {0} ดับก่อนสั่งตำแหน่งถัดไป", busy)], "warn"))
    return out


def _vac_findings(d: DeviceSpec, history) -> list[Finding]:
    """ชุดสุญญากาศ: สั่งยก (addr_lift 0→1) ตอนสวิตช์สุญญากาศ (addr_ok) ยังไม่ ON = ยกก่อนจับแน่น."""
    lift, ok = (str(d.props.get(k, "") or "").upper() for k in ("addr_lift", "addr_ok"))
    if not lift or not ok:
        return []
    prev = 0
    for t, s in history:
        v = int(bool(s.get(lift)))
        if v and not prev and not s.get(ok):
            return [Finding(tr("{0}: ยกถ้วยดูด ({1}) ก่อนสุญญากาศพอ ({2} ยังเป็น 0)", d.props.get('label', ''), lift, ok),
                            [tr("ที่เวลา {0:.2f} วินาที — ชิ้นงานจะไม่ติดขึ้นมาหรือหลุดกลางทาง", t),
                             tr("ใส่หน้าสัมผัส {0} เป็นเงื่อนไขก่อนสั่ง {1} (และตั้ง Timer เฝ้าถ้า OK ไม่มา)", ok, lift)], "warn")]
        prev = v
    return []


# ======================= วิเคราะห์ขณะเล่นเอง (ไม่มีด่าน) =======================
def analyze_live(history: list[tuple[float, dict]], devices: list[DeviceSpec]) -> list[Finding]:
    """ใช้กับสัญญาณที่บันทึกระหว่างนักเรียนกดเล่นเอง: หาอาการผิดปกติที่ชัดเจน."""
    trc = Trace(history, [])
    out = []
    if len(history) < 2:
        return [Finding(tr("ยังไม่มีข้อมูลพอ"), [tr("เชื่อมต่อ PLC แล้วลองกดอุปกรณ์บนผังสักพัก แล้วกดวิเคราะห์อีกครั้ง")], "info")]
    for d in devices:
        if d.kind == "motor_rev":
            a, b = str(d.props.get("address", "")).upper(), str(d.props.get("addr_rev", "")).upper()
            if any(s.get(a) and s.get(b) for _, s in history):
                out.append(Finding(tr("{0} กับ {1} ON พร้อมกัน (ลัดวงจร)", a, b), [tr("ต้องทำ Interlock ระหว่าง FWD/REV")]))
        if d.kind == "motor_yd":
            out.extend(_yd_findings(d, history))
        if d.kind == "vacuum":
            out.extend(_vac_findings(d, history))
        if d.kind == "dc_motor":
            out.extend(_dc_findings(d, history))
        if d.kind == "stepper":
            out.extend(_step_findings(d, history))
        if d.kind in ("cylinder", "pusher"):
            y, a1 = str(d.props.get("address", "")).upper(), str(d.props.get("addr_ext", "")).upper()
            ons = [t for t, v in trc.changes(y) if v == 1]
            if ons and not trc.ever(a1, 1):
                out.append(Finding(tr("สั่ง {0} แล้วแต่ {1} ไม่ถึงปลาย ({2} ไม่เคย ON)", y, d.props.get('label', ''), a1),
                                   [tr("สั่งค้างนานไม่พอ หรือกระบอกสูบมีความผิดปกติ (ลมไม่มา / รีดเสีย)"),
                                    tr("ควรมี Timer เฝ้า: สั่งแล้ว a1 ไม่มาใน 3 วินาที → แจ้งเตือน")], "warn"))
    flick = []
    for a in sorted(trc.addresses()):
        if a.startswith("Y"):
            ch = trc.changes(a)
            fast = sum(1 for (t1, _), (t2, _) in zip(ch, ch[1:]) if t2 - t1 < 0.12)
            if fast >= 4:
                flick.append(a)
    if flick:
        out.append(Finding(tr("Output กระพริบเร็วผิดปกติ: ") + ", ".join(flick),
                           [tr("มักเกิดจากคอยล์เดียวกันถูกเขียนหลายที่ (Double coil) หรือเงื่อนไขขัดกันเอง")], "warn"))
    return out or [Finding(tr("ไม่พบอาการผิดปกติที่ชัดเจน"), [tr("ถ้าต้องการตรวจละเอียด ให้เปิดด่านแล้วกด ▶ ตรวจคำตอบ")], "info")]
