"""layout ที่ตัดบรรทัดเองเมื่อความกว้างไม่พอ (แถบปุ่มบนจอเล็ก)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 4):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):                    # noqa: N802 — ชื่อตาม Qt
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):                        # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):                        # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):              # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):                # noqa: N802
        return True

    def heightForWidth(self, w):                # noqa: N802
        return self._place(QRect(0, 0, w, 0), move=False)

    def setGeometry(self, rect):                # noqa: N802
        super().setGeometry(rect)
        self._place(rect, move=True)

    def sizeHint(self):                         # noqa: N802
        return self.minimumSize()

    def minimumSize(self):                      # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _place(self, rect: QRect, move: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            s = it.sizeHint()
            if x > rect.x() and x + s.width() > rect.x() + rect.width():
                x, y, line = rect.x(), y + line + self.spacing(), 0
            if move:
                it.setGeometry(QRect(QPoint(x, y), s))
            x += s.width() + self.spacing()
            line = max(line, s.height())
        return y + line - rect.y()
