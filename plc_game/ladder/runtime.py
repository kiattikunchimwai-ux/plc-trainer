"""รัน ladder จริง (PLC ในตัว): ใช้กฎเดียวกับ Sim แต่ทุกค่ารู้แน่ — ค่าเริ่ม 0, SM จริง, INC นับทุก scan."""
from __future__ import annotations

from collections import defaultdict

from ..i18n import tr
from .check import number
from .model import CALLS, JUMPS, RETS, Ladder, base_func, is_label, is_wide
from .sim import Sim, k_rise

ALWAYS = {"SM400": 1, "SM401": 0, "SM8000": 1, "SM8001": 0}
FIRST = {"SM402": 1, "SM403": 0, "SM8002": 1, "SM8003": 0}
CLOCK = {"SM410": 0.1, "SM411": 0.2, "SM412": 1.0, "SM413": 2.0,
         "SM8012": 0.1, "SM8013": 1.0, "SM8014": 60.0}               # คาบ (วินาที) เปิดครึ่งปิดครึ่ง
MAX_DT = 1.0                                                          # เครื่องหยุดชั่วขณะ: timer ไม่กระโดด


MAX_CALL = 16


class RuntimeFault(Exception):
    def __init__(self, k: int, text: str):
        super().__init__(text)
        self.k = k


class Memory:
    """มองหน่วยความจำ {ชนิด: {เลข: ค่า}} ของ PLC เป็น dict ชื่อ→ค่า (ทุก address มีค่าเสมอ เริ่ม 0)."""

    def __init__(self, areas, base: int):
        self.areas, self.base, self._cell = areas, base, {}

    def cell(self, name: str):
        c = self._cell.get(name)
        if c is None:
            kind, n = number(name, self.base)
            c = self._cell[name] = (self.areas[kind], n)
        return c

    def __getitem__(self, name):
        a, n = self.cell(name)
        return a[n]

    def __setitem__(self, name, v):
        a, n = self.cell(name)
        a[n] = v

    def __contains__(self, name):
        return True

    def get(self, name, default=None):
        return self[name]

    def setdefault(self, name, v):
        return self[name]


class Runtime(Sim):
    def __init__(self, ladder: Ladder, areas=None):
        super().__init__(ladder)
        self.mem = Memory(areas if areas is not None else defaultdict(lambda: defaultdict(int)), ladder.app_base)
        self.elapsed = 0.0
        self.first = True
        self._k = -1
        self.labels = {i.op: k for k, i in enumerate(ladder.instrs) if is_label(i.op)}

    def scan(self, dt: float):
        dt = min(max(dt, 0.0), MAX_DT)
        self.elapsed += dt
        for n, v in ALWAYS.items():
            self.mem[n] = v
        for n, v in FIRST.items():
            self.mem[n] = v if self.first else 1 - v
        for n, p in CLOCK.items():
            self.mem[n] = int(self.elapsed % p >= p / 2)
        super().scan(dt)
        self.first = False

    def _acc_op(self, k):
        return False

    def _jump(self, k, op, st, mps, frames, pc):
        if op in RETS:
            if not frames:
                return pc
            back, s, m = frames.pop()
            st[:], mps[:] = s, m
            return back
        if op not in JUMPS | CALLS:
            return pc
        c = 1
        if op != "JMP":
            c = self.cond[k] = st[-1] if st else 1
            if op in ("CJP", "CALLP"):
                c = k_rise(self._edge((k,), c), c)
        if c != 1:
            return pc
        if op in CALLS:
            if len(frames) >= MAX_CALL:
                raise RuntimeFault(k, tr("{0}: เรียกโปรแกรมย่อยซ้อนเกิน {1} ชั้น", self.L.instrs[k].text, MAX_CALL))
            frames.append((pc, list(st), list(mps)))
        st.clear()
        mps.clear()
        return self.labels[self.L.instrs[k].args[0]] + 1

    def _runaway(self, k):
        raise RuntimeFault(k, tr("ladder วนไม่จบใน 1 scan (ตรวจ CJ/JMP ที่กระโดดย้อนกลับ): {0}", self.L.instrs[k].text))

    def _output(self, k, op, args, c, power, dt):
        self._k = k
        super()._output(k, op, args, c, power, dt)

    def _compute(self, f, args, w):
        out = super()._compute(f, args, w)
        if None in out.values():
            ins = self.L.instrs[self._k]
            base = base_func(ins.op)[0]
            if base in ("/", "D/"):
                text = tr("หารด้วยศูนย์: {0}", ins.text)
            elif base.endswith("BCD"):
                text = tr("{0}: ค่าต้องอยู่ใน 0–{1} จึงแปลงเป็น BCD ได้", ins.text, 99999999 if is_wide(ins.op) else 9999)
            elif base.endswith("BIN"):
                text = tr("{0}: ค่าต้นทางไม่ใช่ BCD (มีหลักที่เกิน 9)", ins.text)
            else:
                text = tr("คำนวณไม่ได้: {0}", ins.text)
            raise RuntimeFault(self._k, text)
        return out
