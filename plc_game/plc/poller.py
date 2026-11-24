"""อ่านสถานะ PLC เป็นรอบๆ ใน thread แยก แล้วส่ง snapshot ผ่าน Qt Signal.

การเขียนจาก UI จะเข้าคิว และ thread นี้เป็นผู้เขียนเพียงผู้เดียว
(socket SLMP ไม่ควรถูกใช้จากหลาย thread พร้อมกัน)
"""
from __future__ import annotations

import queue
import threading
import time

from PySide6.QtCore import QThread, Signal

from ..panel.watch import WatchBlock
from .base import PLCClient, PLCError
from .device import device_range

DEFAULT_WATCH = [
    WatchBlock("X0", 8, True),
    WatchBlock("Y0", 8, True),
    WatchBlock("M0", 8, True),
    WatchBlock("TS0", 4, True),
    WatchBlock("TN0", 4, False),
    WatchBlock("CS0", 2, True),
    WatchBlock("CN0", 2, False),
]


class PLCPoller(QThread):
    snapshot = Signal(dict, float)   # {"X0": 1, "TN0": 12, ...}, เวลา (วินาที)
    connected = Signal(bool)
    error = Signal(str)

    RECONNECT_S = 2.0

    def __init__(self, client: PLCClient, poll_ms: int = 50, watch=None, xy_base: int = 8, parent=None):
        super().__init__(parent)
        self.client = client
        self.poll_s = poll_ms / 1000.0
        self.xy_base = xy_base
        self._writes: queue.Queue = queue.Queue()
        self._running = False
        self._lock = threading.Lock()
        self._pending_watch = None
        self._apply_watch(list(watch or DEFAULT_WATCH))

    def _apply_watch(self, watch):
        self.watch = watch
        # ชื่อของแต่ละช่องคำนวณไว้ครั้งเดียว
        self._names = {b: [d.name for d in device_range(b.head, b.count, self.xy_base)] for b in watch}

    # เรียกจาก UI thread ได้
    def set_watch(self, watch) -> None:
        """เปลี่ยนชุด address ที่อ่าน — thread poller จะสลับเองที่ต้นรอบถัดไป."""
        with self._lock:
            self._pending_watch = list(watch)

    def write_bit(self, device: str, value: int) -> None:
        self._writes.put((device, [1 if value else 0], False))

    def write_word(self, device: str, value: int) -> None:
        """เขียนค่าตัวเลข 16 บิตแบบมีเครื่องหมาย (-32768..32767) เช่น D10."""
        self._writes.put((device, [max(-32768, min(32767, int(value)))], True))

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def run(self) -> None:
        self._running = True
        t0 = time.monotonic()
        is_up = False
        while self._running:
            if not is_up:
                try:
                    self.client.connect()
                    is_up = True
                    self.connected.emit(True)
                except PLCError as e:
                    self.error.emit(str(e))
                    self._sleep(self.RECONNECT_S)
                    continue
            loop_start = time.monotonic()
            with self._lock:
                if self._pending_watch is not None:
                    self._apply_watch(self._pending_watch)
                    self._pending_watch = None
            try:
                self._flush_writes()
                snap: dict[str, int] = {}
                for b in self.watch:
                    vals = (self.client.read_bits if b.is_bit else self.client.read_words)(b.head, b.count)
                    snap.update(zip(self._names[b], vals))
                # แปะเวลาตอนข้อมูลมาถึง ไม่ใช่ต้นรอบ: GX Simulator3 ตอบ SLMP เป็นช่วง ๆ ทุก ~100 ms
                # คำขอแรกของรอบจึงอาจรอนาน — ถ้าใช้เวลาต้นรอบ เวลาบนกราฟ/ตัวตรวจด่านจะเร็วไป ~0–100 ms แบบสุ่ม
                self.snapshot.emit(snap, time.monotonic() - t0)
            except PLCError as e:
                is_up = False
                self.connected.emit(False)
                self.error.emit(str(e))
                continue
            self._sleep(self.poll_s - (time.monotonic() - loop_start))
        self.client.close()
        self.connected.emit(False)

    def _flush_writes(self):
        while True:
            try:
                dev, vals, is_word = self._writes.get_nowait()
            except queue.Empty:
                return
            (self.client.write_words if is_word else self.client.write_bits)(dev, vals)

    def _sleep(self, seconds: float):
        end = time.monotonic() + max(0.0, seconds)
        while self._running:
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(0.05, left))
