"""PLC จำลอง สำหรับทดสอบโดยไม่ต้องเปิด GX Simulator3.

โปรแกรม ladder ตายตัว (เทียบเท่า):
    Rung 0:  --[X0]--+--[/X1]----------( Y0 )     Self-holding: Start=X0, Stop=X1
             --[Y0]--+
    Rung 1:  --[Y0]-------------------( T0 K30 )  หน่วง 3.0 วินาที (100ms/หน่วย)
    Rung 2:  --[T0]-------------------( Y1 )
    Rung 3:  --[X2]-------------------( C0 K5 )   นับขอบขาขึ้นของ X2
    Rung 4:  --[C0]-------------------( Y2 )
    Rung 5:  --[X3]-------------------( RST C0 )
"""
from __future__ import annotations

from ..i18n import tr

import threading
import time
from collections import defaultdict

from .base import PLCClient, PLCError
from .device import parse_device

TIMER_UNIT_S = 0.1


class MockPLC(PLCClient):
    name = "Mock PLC"

    T0_PRESET = 30  # 3.0 s
    C0_PRESET = 5

    def __init__(self, clock=time.monotonic, scan_s: float = 0.01, auto_scan: bool = True, xy_base: int = 8,
                 program=None):
        """program(mem, now, ctx): ladder อื่นแทนของเดิม — mem["X"][0] ... (เลขจริง ไม่ใช่ฐาน 8),
        ctx = dict ว่างสำหรับเก็บสถานะของโปรแกรม (ใช้ใน test เพื่อจำลองคำตอบของนักเรียน)."""
        self._clock = clock
        self.program = program
        self._ctx: dict = {}
        self.xy_base = xy_base
        self._scan_s = scan_s
        self._auto = auto_scan
        self._mem: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = threading.Lock()
        self._connected = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._t0_start: float | None = None
        self._prev_x2 = 0

    # ---------- PLCClient ----------
    def connect(self) -> None:
        self._connected = True
        if self._auto and not (self._thread and self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def read_bits(self, head: str, count: int) -> list[int]:
        return self._read(head, count)

    def read_words(self, head: str, count: int) -> list[int]:
        return self._read(head, count)

    def write_bits(self, head: str, values: list[int]) -> None:
        self._write(head, [1 if v else 0 for v in values])

    def write_words(self, head: str, values: list[int]) -> None:
        self._write(head, list(values))

    # ---------- memory ----------
    def _check(self):
        if not self._connected:
            raise PLCError(tr("Mock PLC ยังไม่ได้เชื่อมต่อ"))

    def _read(self, head: str, count: int) -> list[int]:
        self._check()
        d = parse_device(head, self.xy_base)
        with self._lock:
            area = self._mem[d.kind]
            return [area[d.number + i] for i in range(count)]

    def _write(self, head: str, values: list[int]) -> None:
        self._check()
        d = parse_device(head, self.xy_base)
        with self._lock:
            area = self._mem[d.kind]
            for i, v in enumerate(values):
                area[d.number + i] = v

    # ---------- scan ----------
    def _run(self):
        while not self._stop.is_set():
            self.scan()
            time.sleep(self._scan_s)

    def scan(self) -> None:
        """ประมวลผล ladder 1 รอบ (เรียกเองได้ใน test)."""
        with self._lock:
            now = self._clock()
            if self.program is not None:
                self.program(self._mem, now, self._ctx)
                return
            X, Y = self._mem["X"], self._mem["Y"]

            # Rung 0: self-holding
            Y[0] = int((X[0] or Y[0]) and not X[1])

            # Rung 1-2: TON T0
            if Y[0]:
                if self._t0_start is None:
                    self._t0_start = now
                tn = min(int((now - self._t0_start) / TIMER_UNIT_S + 1e-6), self.T0_PRESET)
            else:
                self._t0_start = None
                tn = 0
            self._mem["TN"][0] = tn
            self._mem["TS"][0] = int(tn >= self.T0_PRESET)
            Y[1] = self._mem["TS"][0]

            # Rung 3-5: counter C0
            if X[3]:
                self._mem["CN"][0] = 0
            elif X[2] and not self._prev_x2 and self._mem["CN"][0] < self.C0_PRESET:
                self._mem["CN"][0] += 1
            self._prev_x2 = X[2]
            self._mem["CS"][0] = int(self._mem["CN"][0] >= self.C0_PRESET)
            Y[2] = self._mem["CS"][0]
