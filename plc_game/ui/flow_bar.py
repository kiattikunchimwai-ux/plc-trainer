"""แถบขั้นตอน 1-2-3-4 เหนือพื้นที่งาน: บอกว่าทำถึงไหนและขั้นต่อไปคืออะไร (คลิกเพื่อทำขั้นนั้น).

ไม่เก็บสถานะเอง — MainWindow ส่งสถานะจริงมาเป็น list ของ (ข้อความ, คำอธิบาย, เสร็จแล้ว, กดได้)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton

from . import theme


class FlowBar(QFrame):
    clicked = Signal(int)

    def __init__(self, n: int = 4, parent=None):
        super().__init__(parent)
        self.setObjectName("FlowBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(4)
        self.steps: list[QToolButton] = []
        self.next: int | None = None
        self._last = None
        for i in range(n):
            if i:
                arrow = QLabel("›")
                arrow.setStyleSheet(f"color:{theme.TEXT_DIM}; font-weight:bold;")
                h.addWidget(arrow)
            b = QToolButton()
            b.setObjectName("Step")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=i: self.clicked.emit(k))
            h.addWidget(b)
            self.steps.append(b)
        self.hint = QLabel()
        self.hint.setObjectName("FlowHint")
        self.hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # จอแคบ = ยอมโดนตัด ไม่ดันหน้าต่าง
        h.addWidget(self.hint, 1)

    def set_steps(self, rows: list[tuple[str, str, bool, bool]], all_done: str = ""):
        """ขั้นแรกที่ยังไม่เสร็จ = ขั้นต่อไป (ไฮไลต์ + คำแนะนำ)."""
        key = (tuple(rows), all_done)
        if key == self._last:
            return
        self._last = key
        self.next = next((i for i, r in enumerate(rows) if not r[2]), None)
        for i, (b, (text, hint, done, enabled)) in enumerate(zip(self.steps, rows)):
            b.setText(f"{'✔' if done else i + 1}  {text}")
            b.setToolTip(hint)
            b.setEnabled(enabled)
            b.setProperty("st", "done" if done else "next" if i == self.next else "todo")
            b.style().unpolish(b)
            b.style().polish(b)
        self.hint.setText(all_done if self.next is None else rows[self.next][1])
        self.hint.setToolTip(self.hint.text())
