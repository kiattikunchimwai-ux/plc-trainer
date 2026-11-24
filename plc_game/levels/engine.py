"""Level Engine: โหลดโจทย์จาก levels/*.yaml แล้วตรวจคำตอบด้วยการกด input และดูผล output (black-box).

ขั้นตอน (step) ที่รองรับ — เขียนเป็นข้อความ หรือ dict {do: "...", msg: "...", hint: "..."}
    set X0 1              เขียนบิต (ค่าที่ PLC เห็น — ปุ่ม NC ตอนกดคือ 0)
    pulse X0 0.3          ON 0.3 วินาทีแล้ว OFF (ค่าเริ่มต้น 0.3)
    word D10 50           เขียนค่าตัวเลข
    wait 1.5              รอ
    part metal            ปล่อยชิ้นงานบนสายพาน (metal / plastic)
    expect Y0 = 1 within 0.5          ต้องเป็นจริงภายในเวลาที่กำหนด (ค่าเริ่มต้น 0.5 วินาที)
    expect Y0 = 0 and Y1 = 1 within 3
    expect D0 >= +1 within 2          เครื่องหมาย + = เทียบกับค่าตอนเริ่มข้อ (เพิ่มขึ้นอย่างน้อย 1)
    hold Y0 = 1 for 2                 ต้องเป็นจริงตลอดช่วงเวลา
    waitfor X2 = 1 within 5           รอจนเป็นจริง (ไม่นับคะแนน ใช้รอเครื่องกลับตำแหน่ง)
                                      หมดเวลา = จดไว้ใน runner.notes แล้วทำต่อ
    ตัวเปรียบเทียบ: =  !=  >=  <=  >  <

ทุก "ข้อ" (case) เริ่มด้วยการคืน input เป็นค่าพัก (idle) → ทำขั้นตอน reset ของด่าน → รอ settle วินาที
ถ้าการตรวจในข้อใดไม่ผ่าน การตรวจที่เหลือในข้อนั้นนับว่าไม่ผ่าน แล้วไปข้อถัดไป
หลังเขียน input ตัวตรวจรออ่านกลับตรง + snapshot ใหม่อีก 1 รอบก่อนตัดสิน (SLMP มีความหน่วง)
ข้อมูลขาดช่วง/address อ่านไม่ได้ = ยกเลิก (runner.aborted) ไม่ให้คะแนน
"""
from __future__ import annotations

from ..i18n import pick, tr

import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from ..plc.device import parse_device

from .. import paths

ROOT = paths.app_root()
LEVEL_DIR = paths.levels_dir()

OPS = {"=": operator.eq, "==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le,
       ">": operator.gt, "<": operator.lt}
OP_TH = {"=": "=", "==": "=", "!=": "≠", ">=": "≥", "<=": "≤", ">": ">", "<": "<"}
_COND = re.compile(r"^\s*([A-Za-z]+[0-9A-Fa-f]+)\s*(==|!=|>=|<=|=|>|<)\s*(\+?)(-?\d+)\s*$")
CHECK_OPS = ("expect", "hold")
ECHO_TIMEOUT_S = 0.5       # รออ่านค่า input ที่เพิ่งเขียนกลับมาได้นานสุด
MAX_GAP_S = 1.5            # ข้อมูลจาก PLC ขาดช่วงนานกว่านี้ = ผลตรวจเชื่อไม่ได้ → ยกเลิก
MISSING_S = 2.0            # address ที่ต้องใช้อ่านไม่ได้นานกว่านี้ → ยกเลิก


# ======================= โครงสร้างโจทย์ =======================
@dataclass(frozen=True)
class Cond:
    addr: str
    op: str
    value: int
    rel: bool = False          # "D0 >= +1" = เพิ่มขึ้นจากค่าตอนเริ่มข้ออย่างน้อย 1

    def target(self, base: dict | None) -> int:
        return self.value + (int((base or {}).get(self.addr, 0) or 0) if self.rel else 0)

    def test(self, snap: dict, base: dict | None = None) -> bool:
        return OPS[self.op](int(snap.get(self.addr, 0) or 0), self.target(base))

    def __str__(self):
        if self.rel:
            return tr("{0} เพิ่มขึ้น {1} {2}", self.addr, OP_TH[self.op], self.value)
        return f"{self.addr} {OP_TH[self.op]} {self.value}"


def parse_conds(text: str, xy_base: int = 8) -> list[Cond]:
    out = []
    for part in re.split(r"\s+and\s+|\s*&&\s*", text.strip(), flags=re.I):
        m = _COND.match(part)
        if not m:
            raise ValueError(tr("เงื่อนไขไม่ถูกต้อง: {0!r} (ตัวอย่าง: Y0 = 1)", part))
        addr = parse_device(m.group(1), xy_base).name
        out.append(Cond(addr, m.group(2), int(m.group(4)), rel=m.group(3) == "+"))
    return out


@dataclass
class Step:
    op: str                       # set / pulse / word / wait / part / expect / hold
    addr: str = ""
    value: int = 0
    dur: float = 0.0
    conds: list[Cond] = field(default_factory=list)
    arg: str = ""
    msg: str = ""
    hint: str = ""

    @property
    def is_check(self) -> bool:
        return self.op in CHECK_OPS

    def describe(self) -> str:
        if self.msg:
            return self.msg
        c = tr(" และ ").join(map(str, self.conds))
        if self.op == "expect":
            return tr("{0} ภายใน {1:g} วินาที", c, self.dur)
        if self.op == "hold":
            return tr("{0} ต่อเนื่อง {1:g} วินาที", c, self.dur)
        return self.op


def parse_step(raw, xy_base: int = 8) -> Step:
    msg = hint = ""
    if isinstance(raw, dict):
        msg = pick(str(raw.get("msg", "")), raw.get("msg_en"))
        hint = pick(str(raw.get("hint", "")), raw.get("hint_en"))
        raw = raw.get("do", "")
    text = str(raw).strip()
    op, _, rest = text.partition(" ")
    op, rest = op.lower(), rest.strip()
    try:
        if op in ("set", "word"):
            a, _, v = rest.partition(" ")
            return Step(op, addr=parse_device(a, xy_base).name, value=int(v or 1), msg=msg, hint=hint)
        if op == "pulse":
            a, _, d = rest.partition(" ")
            return Step(op, addr=parse_device(a, xy_base).name, dur=float(d or 0.3), msg=msg, hint=hint)
        if op == "wait":
            return Step(op, dur=float(rest), msg=msg, hint=hint)
        if op == "part":
            return Step(op, arg=rest or "metal", msg=msg, hint=hint)
        if op in ("expect", "waitfor"):
            m = re.match(r"^(.*?)(?:\s+within\s+([\d.]+))?$", rest, re.I)
            return Step(op, conds=parse_conds(m.group(1), xy_base), dur=float(m.group(2) or 0.5), msg=msg, hint=hint)
        if op == "hold":
            m = re.match(r"^(.*?)\s+for\s+([\d.]+)$", rest, re.I)
            if not m:
                raise ValueError(tr("ต้องระบุ for <วินาที>"))
            return Step(op, conds=parse_conds(m.group(1), xy_base), dur=float(m.group(2)), msg=msg, hint=hint)
    except (ValueError, AttributeError) as e:
        raise ValueError(tr("ขั้นตอน {0!r}: {1}", text, e)) from None
    raise ValueError(tr("ไม่รู้จักคำสั่ง {0!r} ในขั้นตอน {1!r}", op, text))


@dataclass
class Case:
    name: str
    steps: list[Step]


@dataclass
class FaultSpec:
    """ด่านหาจุดเสีย: อุปกรณ์ (label บนผัง) + รหัสความผิดปกติที่สุ่มได้ และจำนวนครั้งที่ทายได้."""
    pool: list[tuple[str, tuple[str, ...]]]
    guesses: int = 3


def parse_faults(data, name: str = "") -> FaultSpec | None:
    if not data:
        return None
    pool = []
    for e in data.get("pool") or []:
        dev, codes = str(e.get("device", "")).strip(), e.get("codes") or []
        if not dev or not codes:
            raise ValueError(tr("{0}: faults.pool ต้องมี device และ codes", name))
        pool.append((dev, tuple(str(c).lower() for c in codes)))
    if not pool:
        raise ValueError(tr("{0}: faults.pool ว่าง", name))
    guesses = int(data.get("guesses", 3))
    if guesses < 1:
        raise ValueError(tr("{0}: faults.guesses ต้อง ≥ 1", name))
    return FaultSpec(pool, guesses)


@dataclass
class Level:
    id: str
    title: str
    desc: str
    panel: Path | None
    idle: dict[str, int]
    cases: list[Case]
    settle: float = 0.6
    order: int = 0
    path: Path | None = None
    reset_len: int = 0          # จำนวนขั้นตอน reset ที่ใส่หน้าทุกข้อ
    faults: FaultSpec | None = None

    @property
    def is_fault_hunt(self) -> bool:
        return self.faults is not None

    @property
    def checks(self) -> int:
        return sum(s.is_check for c in self.cases for s in c.steps)

    def addresses(self) -> list[str]:
        """ทุก address ที่ต้องอ่าน/เขียนระหว่างตรวจ (ใช้ตั้ง watch ของ poller)."""
        out = list(self.idle)
        for c in self.cases:
            for s in c.steps:
                if s.addr:
                    out.append(s.addr)
                out += [cd.addr for cd in s.conds]
        return list(dict.fromkeys(out))

    def watch_addresses(self, xy_base: int = 8) -> list[str]:
        """address ของด่าน + X0–X17 / Y0–Y17 (ให้ AI เห็นว่านักเรียนเขียนคอยล์ผิดเลขไหม)."""
        from ..plc.device import device_range
        extra = [d.name for k in ("X0", "Y0") for d in device_range(k, 16, xy_base)]
        return list(dict.fromkeys(self.addresses() + extra))


def load_level(path: Path, xy_base: int = 8) -> Level:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return level_from_data(data, path, xy_base)


def level_from_data(data: dict, path: Path, xy_base: int = 8) -> Level:
    """สร้าง Level จาก dict (เนื้อหา YAML) — path ใช้หาไฟล์ผังแบบ relative และตั้งชื่อ id สำรอง."""
    path = Path(path)
    if not isinstance(data, dict):
        raise ValueError(tr("{0}: รูปแบบไฟล์ไม่ถูกต้อง", path.name))
    settle = float(data.get("settle", 0.6))
    reset = [parse_step(s, xy_base) for s in data.get("reset", [])]
    if any(s.is_check for s in reset):
        raise ValueError(tr("{0}: reset ใช้ expect/hold ไม่ได้ (ใช้ waitfor แทน)", path.name))
    if reset:
        reset.append(Step("wait", dur=settle))
    cases = [Case(pick(str(c.get("name", tr("ข้อ {0}", i + 1))), c.get("name_en")),
                  reset + [parse_step(s, xy_base) for s in c.get("steps", [])])
             for i, c in enumerate(data.get("cases", []))]
    faults = parse_faults(data.get("faults"), path.name)
    if not cases and faults is None:
        raise ValueError(tr("{0}: ไม่มี cases", path.name))
    panel = data.get("panel")
    panel_path = None
    if panel:
        for base in (path.parent, paths.user_root(), ROOT):
            if (base / panel).exists():
                panel_path = (base / panel).resolve()
                break
    idle = {parse_device(str(k), xy_base).name: int(v) for k, v in (data.get("idle") or {}).items()}
    title = pick(str(data.get("title", path.stem)), data.get("title_en"))
    desc = pick(str(data.get("desc", "")), data.get("desc_en")).strip()
    return Level(str(data.get("id", path.stem)), title, desc,
                 panel_path, idle, cases, settle, int(data.get("order", 0)), path, len(reset), faults)


def load_all(folder: Path = LEVEL_DIR, xy_base: int = 8) -> list[Level]:
    levels = [load_level(p, xy_base) for p in sorted(Path(folder).glob("*.yaml"))]
    return sorted(levels, key=lambda lv: (lv.order, lv.id))


def stars_for(score: float) -> int:
    """ผ่านทุกข้อ = 3 ดาว, ≥ 70% = 2, ≥ 40% = 1."""
    if score >= 0.999:
        return 3
    return 2 if score >= 0.7 else 1 if score >= 0.4 else 0


# ======================= ตัวตรวจ =======================
@dataclass
class CheckResult:
    case: str
    case_index: int
    step_index: int
    op: str
    msg: str
    passed: bool
    detail: str = ""
    hint: str = ""
    skipped: bool = False
    t_start: float = 0.0
    t_end: float = 0.0
    conds: list[Cond] = field(default_factory=list)
    dur: float = 0.0
    targets: list[int] = field(default_factory=list)   # ค่าเป้าหมายจริงของแต่ละเงื่อนไข (แปลง +n แล้ว)


# ======================= ค่าคาดหวัง (ใช้วาดเทียบบนกราฟ) =======================
@dataclass(frozen=True)
class Segment:
    t0: float
    t1: float
    value: float          # บิต: 0/1 ที่ต้องเป็น · word: ค่าเป้าหมาย/เกณฑ์
    op: str
    passed: bool
    kind: str             # expect / hold
    msg: str


def _bit_expected(op: str, target: int) -> int | None:
    """บิตต้องเป็นค่าอะไรถึงผ่านเงื่อนไข (None = เป็นได้ทั้ง 0/1 หรือเป็นไม่ได้เลย)."""
    ok = [v for v in (0, 1) if OPS[op](v, target)]
    return ok[0] if len(ok) == 1 else None


def expected_segments(runner: "LevelRunner", is_bit: Callable[[str], bool] | None = None) -> dict[str, list[Segment]]:
    """{address: [Segment]} จากผลตรวจ — hold = ช่วงที่ต้องคงค่า, expect = ช่วงที่ต้องเป็นค่านั้นให้ทันกำหนด.
    การตรวจที่ถูกข้าม (เพราะข้อก่อนหน้าไม่ผ่าน) ไม่มีช่วงเวลาจริงจึงไม่นำมาวาด."""
    if is_bit is None:
        def is_bit(a):
            return parse_device(a).is_bit
    out: dict[str, list[Segment]] = {}
    for r in runner.results:
        if r.skipped:
            continue
        t1 = max(r.t_end, r.t_start + 0.05)
        for c, tgt in zip(r.conds, r.targets or [c.value for c in r.conds]):
            if is_bit(c.addr):
                v = _bit_expected(c.op, tgt)
                if v is None:
                    continue
            else:
                v = tgt
            out.setdefault(c.addr, []).append(Segment(r.t_start, t1, float(v), c.op, r.passed, r.op, r.msg))
    return out


def fail_spans(runner: "LevelRunner") -> list[tuple[float, float, str]]:
    """ช่วงเวลาของการตรวจที่ไม่ผ่านจริง (ไม่รวมข้อที่ถูกข้าม) — ใช้ทำแถบแดงบนกราฟ."""
    return [(r.t_start, max(r.t_end, r.t_start + 0.05), r.msg) for r in runner.results if not r.passed and not r.skipped]


class LevelRunner:
    """state machine ที่ขับด้วย feed(snapshot, t) — ไม่ใช้ Qt จึงทดสอบกับ MockPLC ได้.

    write(addr, value, is_word)  เขียน input ไปยัง PLC (หรือผ่านอุปกรณ์บนผัง)
    action(name, arg)            คำสั่งพิเศษ เช่น ("part", "metal")
    """

    def __init__(self, level: Level, write: Callable[[str, int, bool], None],
                 action: Callable[[str, str], None] | None = None):
        self.level = level
        self.write = write
        self.action = action or (lambda name, arg: None)
        self.results: list[CheckResult] = []
        self.trace: list[tuple[float, dict]] = []     # snapshot เฉพาะตอนที่ค่าเปลี่ยน
        self.events: list[tuple[float, str]] = []     # สิ่งที่ตัวตรวจทำ (ใช้ในการวิเคราะห์)
        self.done = False
        self.t0: float | None = None
        self._ci = 0
        self._si = -1           # -1 = ช่วงคืนค่า idle ต้นข้อ
        self._step_t = 0.0
        self._pulse_on = False
        self._judged = False
        self._carry: float | None = None
        self._last: dict = {}
        self._base: dict = {}       # ค่าตอนเริ่มข้อ (หลัง reset) สำหรับเงื่อนไขแบบ +n
        self._now = 0.0
        self.aborted = ""           # เหตุที่ยกเลิกกลางคัน (ไม่ให้คะแนน)
        self.notes: list[tuple[int, float, str]] = []      # (ลำดับข้อ, เวลา, คำอธิบาย) waitfor ที่หมดเวลา
        self._need = level.addresses()
        self._t_prev: float | None = None
        self._missing_t: float | None = None
        self._n = 0                 # ลำดับ snapshot
        self._echo: dict[str, tuple[int, float]] = {}      # address → (ค่าที่เขียน, เวลา) ที่ยังอ่านกลับไม่ตรง
        self._put_n: dict[str, int] = {}                   # address → snapshot ตอนที่เขียน
        self._fresh_n = 0           # ต้องมี snapshot ลำดับนี้ขึ้นไปจึงตัดสินผลได้

    # ---------- ผลรวม ----------
    @property
    def total(self) -> int:
        return self.level.checks

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def stars(self) -> int:
        return stars_for(self.score)

    @property
    def current_case(self) -> str:
        return self.level.cases[self._ci].name if self._ci < len(self.level.cases) else ""

    # ---------- เดินเครื่อง ----------
    def _log(self, text):
        self.events.append((self._now, text))

    def _put(self, addr, value, is_word=False):
        self._log(f"{addr} ← {value}")
        self.write(addr, int(value), is_word)
        self._put_n[addr] = self._n
        self._echo[addr] = (int(value), self._now)

    def _update_echo(self, snap):
        """ดูว่า input ที่เขียนไปถึง PLC หรือยัง — ถึงแล้วต้องรออีก 1 snapshot ให้ ladder ทำงานทัน."""
        for a, (v, tw) in list(self._echo.items()):
            if a in snap and int(snap[a] or 0) == v and self._n > self._put_n.get(a, 0):
                del self._echo[a]
                self._fresh_n = max(self._fresh_n, self._n + 1)
            elif self._now - tw >= ECHO_TIMEOUT_S:
                del self._echo[a]
                self._log(tr("อ่านค่า {0} กลับมาไม่ตรงกับที่เขียน ({1})", a, v))

    def _settled(self) -> bool:
        return not self._echo and self._n >= self._fresh_n

    def abort(self, reason: str):
        """ยกเลิกเพราะข้อมูลเชื่อไม่ได้ (การเชื่อมต่อหลุด ฯลฯ) — ผลที่ได้ห้ามนำไปให้คะแนน."""
        if self.done:
            return
        self.aborted = reason
        self._log(reason)
        self.stop()

    def stop(self):
        """หยุดกลางคัน: คืน input เป็นค่าพัก."""
        for a, v in self.level.idle.items():
            self.write(a, v, False)
        self.done = True

    def feed(self, snap: dict, t: float) -> bool:
        """ป้อนค่าที่อ่านได้รอบล่าสุด คืน True เมื่อตรวจครบแล้ว."""
        if self.done:
            return True
        self._n += 1
        missing = [a for a in self._need if snap.get(a) is None]
        if missing:
            if self._missing_t is None:
                self._missing_t = t
            limit = MISSING_S if self._t_prev is None else MAX_GAP_S     # ตอนเริ่ม poller อาจยังสลับชุดที่อ่านไม่เสร็จ
            if t - self._missing_t > limit:
                self.abort(tr("อ่านค่าจาก PLC ไม่ได้: {0}", ", ".join(missing[:6])))
            return self.done
        self._missing_t = None
        if self._t_prev is not None and t - self._t_prev > MAX_GAP_S:
            self.abort(tr("ข้อมูลจาก PLC ขาดช่วง {0:.1f} วินาที", t - self._t_prev))
            return True
        self._t_prev = t
        if self.t0 is None:
            self.t0 = t
            self._begin_case(t)
        self._now = t - self.t0
        self._update_echo(snap)
        if snap != self._last:
            self.trace.append((self._now, dict(snap)))
            self._last = dict(snap)
        for _ in range(200):           # ทำขั้นตอนที่ไม่ต้องรอได้หลายขั้นในรอบเดียว
            if self.done or not self._advance(snap, t):
                break
        return self.done

    def _begin_case(self, t):
        self._si = -1
        self._step_t = t
        case = self.level.cases[self._ci]
        self._log(tr("── ข้อ {0}: {1}", self._ci + 1, case.name))
        for a, v in self.level.idle.items():
            self._put(a, v)

    def _next_step(self, t):
        self._si += 1
        self._step_t = t if self._carry is None else self._carry
        self._carry = None
        self._judged = False
        self._pulse_on = False
        if self._si == self.level.reset_len:
            self._base = dict(self._last)
        steps = self.level.cases[self._ci].steps
        if self._si >= len(steps):
            self._ci += 1
            if self._ci >= len(self.level.cases):
                for a, v in self.level.idle.items():
                    self._put(a, v)
                self.done = True
            else:
                self._begin_case(t)

    def _record(self, step, passed, t, detail="", skipped=False):
        self.results.append(CheckResult(
            self.level.cases[self._ci].name, self._ci, self._si, step.op, step.describe(), passed, detail,
            step.hint, skipped, self._step_t - self.t0, t - self.t0, list(step.conds), step.dur,
            [c.target(self._base) for c in step.conds]))
        self._log(("✔ " if passed else "✖ ") + step.describe() + (f" — {detail}" if detail else ""))

    def _fail_rest(self, t):
        """การตรวจที่เหลือในข้อนี้นับว่าไม่ผ่าน แล้วข้ามไปข้อถัดไป."""
        steps = self.level.cases[self._ci].steps
        for i in range(self._si + 1, len(steps)):
            if steps[i].is_check:
                self._si = i
                self._step_t = t
                self._record(steps[i], False, t, tr("ไม่ได้ตรวจ เพราะการตรวจก่อนหน้าในข้อนี้ไม่ผ่าน"), skipped=True)
        self._si = len(steps) - 1      # _next_step จะขึ้นข้อใหม่
        self._next_step(t)

    def _advance(self, snap, t) -> bool:
        """ทำขั้นตอนปัจจุบัน คืน True ถ้าขยับไปขั้นถัดไปแล้ว (ทำต่อได้ทันที)."""
        el = t - self._step_t
        if self._si == -1:                                   # รอให้ค่า idle นิ่ง
            if el >= self.level.settle:
                self._next_step(t)
                return True
            return False
        step = self.level.cases[self._ci].steps[self._si]
        if step.op in ("set", "word"):
            if step.addr in self._echo:                      # ค่าก่อนหน้ายังไปไม่ถึง PLC — เขียนทับตอนนี้ขอบสัญญาณจะหาย
                return False
            self._put(step.addr, step.value, step.op == "word")
        elif step.op == "pulse":
            if not self._pulse_on:
                if step.addr in self._echo:
                    return False
                self._put(step.addr, 1)
                self._pulse_on = True
                self._step_t = t
                return False
            if el < step.dur or step.addr in self._echo:     # คงไว้จน PLC เห็นค่า 1 จริง
                return False
            self._put(step.addr, 0)
        elif step.op == "wait":
            if el < step.dur:
                return False
        elif step.op == "part":
            self._log(tr("ปล่อยชิ้นงาน {0}", step.arg))
            self.action("part", step.arg)
        elif step.op == "waitfor":
            if not self._settled():
                return False
            if not all(c.test(snap, self._base) for c in step.conds):
                if el <= step.dur:
                    return False
                text = tr("รอ {0} ครบ {1:g} วินาทีแล้วยังไม่เป็นจริง — {2}", tr(" และ ").join(map(str, step.conds)), step.dur, self._why(step, snap))
                self.notes.append((self._ci, self._now, text))
                self._log("⚠ " + text)
        elif step.op == "expect":
            if not self._settled():
                return False
            first, self._judged = not self._judged, True
            if all(c.test(snap, self._base) for c in step.conds):
                # จริงตั้งแต่ครั้งแรกที่ตัดสินได้ → เวลาที่รออ่านกลับไม่เลื่อนกำหนดของขั้นถัดไป
                self._carry = self._step_t if first else None
                self._record(step, True, t, tr("เป็นจริงหลัง {0:.2f} วินาที", el))
            elif el > step.dur:
                self._record(step, False, t, self._why(step, snap) + tr(" (รอแล้ว {0:g} วินาที)", step.dur))
                self._fail_rest(t)
                return True
            else:
                return False
        elif step.op == "hold":
            if not self._settled():                          # เวลายังเดินต่อ แต่ยังไม่ตัดสินจากค่าเก่า
                return False
            bad = [c for c in step.conds if not c.test(snap, self._base)]
            if bad:
                self._record(step, False, t, self._why(step, snap) + tr(" หลังผ่านไป {0:.2f} วินาที", el))
                self._fail_rest(t)
                return True
            if el < step.dur:
                return False
            self._record(step, True, t)
        self._next_step(t)
        return True

    def _why(self, step, snap) -> str:
        bad = [c for c in step.conds if not c.test(snap, self._base)]
        return " · ".join(tr("{0} = {1} (ต้อง {2} {3})", c.addr, int(snap.get(c.addr, 0) or 0), OP_TH[c.op], c.target(self._base))
                          for c in bad)
