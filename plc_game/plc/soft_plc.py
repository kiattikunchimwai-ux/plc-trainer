"""PLC ในตัว: รัน ladder ที่เขียน/นำเข้าในโปรแกรม โดยไม่ต้องมี GX Works3 (ใช้หน่วยความจำและ thread ของ MockPLC)."""
from __future__ import annotations

import threading
import time

from ..i18n import tr
from .device import parse_device
from .mock_client import MockPLC

NO_PROGRAM, STOP, RUN, ERROR = "empty", "stop", "run", "error"


class SoftPLC(MockPLC):
    name = "PLC ในตัว"             # i18n: skip (แทนด้วยคำแปลใน __init__)

    def __init__(self, clock=time.monotonic, scan_s: float = 0.01, auto_scan: bool = True, xy_base: int = 8):
        super().__init__(clock=clock, scan_s=scan_s, auto_scan=auto_scan, xy_base=xy_base)
        self.name = tr("PLC ในตัว")
        self.state, self.fault = NO_PROGRAM, ""
        self.fault_k = -1
        self.ladder = None
        self._rt = None
        self._t: float | None = None
        self._ext: set[tuple[str, int]] = set()    # ช่องที่อุปกรณ์บนผังเขียน (ไม่ล้างตอน RESET)
        self.max_scan_ms = 0.0

    # ---------- โปรแกรม ----------
    def load(self, prog, run: bool = True) -> list:
        """เขียน ladder ลง PLC — คืนรายการปัญหา (มีปัญหา = ไม่เปลี่ยนโปรแกรมที่รันอยู่)."""
        from ..ladder.check import check
        from ..ladder.model import Ladder
        L = Ladder(prog, self.xy_base)
        probs = check(L)
        if probs:
            return probs
        with self._lock:
            self.ladder = L
            self._reset()
            self.state = RUN if run else STOP
        return []

    def unload(self) -> None:
        with self._lock:
            self.ladder = None
            self._reset()
            self.state = NO_PROGRAM

    def run_plc(self) -> bool:
        """STOP → RUN (ข้อผิดตอนรันต้อง RESET ก่อน)."""
        with self._lock:
            if self.state != STOP or self.ladder is None:
                return False
            self._fresh()
            self.state = RUN
            return True

    def stop_plc(self) -> None:
        with self._lock:
            if self.state == RUN:
                self.state = STOP
                self._outputs_off()

    def reset_plc(self) -> None:
        with self._lock:
            self._reset()
            if self.ladder is not None:
                self.state = STOP

    def _fresh(self):
        from ..ladder.runtime import Runtime
        self._rt = Runtime(self.ladder, self._mem) if self.ladder is not None else None
        self._t = None

    def _reset(self):
        owned = set()
        if self.ladder is not None:
            from ..ladder.check import number
            owned = {number(n, self.xy_base) for n in self.ladder.written}
        for kind, area in self._mem.items():
            if kind != "X":
                for n in list(area):
                    if (kind, n) not in self._ext or (kind, n) in owned:
                        area[n] = 0
        self.fault, self.fault_k, self.max_scan_ms = "", -1, 0.0
        self._fresh()

    def _outputs_off(self):
        for n in self._mem["Y"]:
            self._mem["Y"][n] = 0

    # ---------- scan ----------
    def scan(self) -> None:
        with self._lock:
            if self.state != RUN:
                self._t = None
                return
            now = self._clock()
            t0 = time.perf_counter()
            try:
                self._rt.scan(0.0 if self._t is None else now - self._t)
            except Exception as e:          # noqa: BLE001 — ladder ผิดต้องไม่ล้ม thread ของ PLC
                self.state, self.fault, self.fault_k = ERROR, str(e) or repr(e), getattr(e, "k", -1)
                self._outputs_off()
                return
            self._t = now
            self.max_scan_ms = max(self.max_scan_ms, (time.perf_counter() - t0) * 1000)

    def _write(self, head, values):
        super()._write(head, values)
        d = parse_device(head, self.xy_base)
        with self._lock:
            self._ext |= {(d.kind, d.number + i) for i in range(len(values))}

    def connect(self) -> None:
        if self._thread and self._stop.is_set():
            self._thread.join(1.0)              # ปิดแล้วเปิดใหม่ทันที: รอ thread เดิมจบก่อน
        super().connect()

    def close(self) -> None:
        super().close()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(1.0)

    # ---------- monitor ----------
    def monitor(self) -> dict:
        """สำเนาสถานะสำหรับวาดหน้าจอ: cv/cond = ค่าหน้าสัมผัส/เงื่อนไขต่อลำดับคำสั่งใน scan ล่าสุด."""
        with self._lock:
            rt = self._rt
            vals = {n: rt.mem[n] for n in {*rt.L.written, *rt.L.read}} if rt else {}
            return {"state": self.state, "fault": self.fault, "fault_k": self.fault_k,
                    "cv": dict(rt.cv) if rt else {}, "cond": dict(rt.cond) if rt else {}, "values": vals}
