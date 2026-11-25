"""เก็บขยะของ Python เฉพาะใน thread หน้าจอ.

ปกติ gc ทำงานใน thread ไหนก็ได้ที่จองหน่วยความจำ — ถ้าเป็น thread ของ AI/PLC แล้วในขยะมีวัตถุ Qt
(เช่น ผังที่เลิกใช้แล้ว) วัตถุจะถูกลบผิด thread และโปรแกรมปิดตัวเอง (access violation)
"""
from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer


class GuiGC(QObject):
    """ปิด gc อัตโนมัติ แล้วเก็บเองตามเกณฑ์เดิมของ Python ด้วย QTimer ใน thread หน้าจอ."""

    def __init__(self, parent=None, interval_ms: int = 500):
        super().__init__(parent)
        self._limits = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(interval_ms)

    def check(self):
        n0, n1, n2 = gc.get_count()
        t0, t1, t2 = self._limits
        if n0 <= t0:
            return
        gc.collect(2 if n1 > t1 and n2 > t2 else 1 if n1 > t1 else 0)

    def stop(self):
        """เลิกใช้ (ปิดหน้าต่าง หลัง thread จบแล้ว)."""
        self._timer.stop()
        gc.enable()
