"""thread เรียนรู้จากเงื่อนไขของด่าน (ใช้ทั้งตัวแก้ไขด่านและแท็บด่าน)."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..ai import learn
from ..i18n import tr


class LearnWorker(QThread):
    """เรียนรู้จากเงื่อนไขใน thread แยก (ไม่แตะ widget)."""
    done = Signal(object, object)         # worker, learn.Model

    def __init__(self, level, profile, xy_base, parent=None):
        super().__init__(parent)
        self.level, self.profile, self.xy_base = level, profile, xy_base
        self.cancelled = False

    def run(self):
        try:
            m = learn.train(self.level, self.profile, self.xy_base, lambda: self.cancelled)
        except Exception as e:  # noqa: BLE001 — เงื่อนไขแปลก ๆ ต้องไม่ทำให้โปรแกรมล้ม
            m = learn.Model("error", tr("เรียนรู้ไม่สำเร็จ: {0}", e))
        self.done.emit(self, m)
