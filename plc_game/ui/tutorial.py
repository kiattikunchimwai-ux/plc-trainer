"""บทเรียนนำทาง: ฉากมืดทั้งหน้าต่าง เจาะช่องที่ widget เป้าหมาย + กล่องคำแนะนำ.

- ช่องที่เจาะคลิกผ่านได้จริง (ใช้ mask ตัดช่องออกจาก overlay) ส่วนอื่นคลิกไม่ได้
- แต่ละขั้นมีเงื่อนไข done() — เมื่อเป็นจริงจะไปขั้นถัดไปเอง (ขั้นที่ไม่มีเงื่อนไขใช้ปุ่ม "ถัดไป")
- ข้ามขั้น / ข้ามบทเรียนได้เสมอ ไม่บังคับ
"""
from __future__ import annotations

from ..i18n import tr

import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

DWELL_S = 0.7          # อยู่ในขั้นอย่างน้อยเท่านี้ก่อนไปขั้นถัดไปเอง (ให้ผู้ใช้เห็นว่าทำสำเร็จ)
PAD = 6                # ระยะเผื่อรอบช่องที่เจาะ


@dataclass
class TStep:
    title: str
    text: str
    target: Callable[[], QWidget | None] | None = None
    done: Callable[[], bool] | None = None
    prepare: Callable[[], None] | None = None


class TutorialOverlay(QWidget):
    finished = Signal(bool)            # True = ทำครบทุกขั้น, False = ข้าม

    def __init__(self, win: QWidget, steps: list[TStep], title: str = ""):
        super().__init__(win)
        self.win = win
        self.steps = steps
        self.title = title or tr("บทเรียนนำทาง")
        self.index = -1
        self.hole = QRect()
        self.completed: list[int] = []
        self._entered = 0.0
        self._ok_since: float | None = None
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.bubble = QFrame(self)
        self.bubble.setObjectName("TutorialBubble")
        self.bubble.setStyleSheet(
            f"#TutorialBubble {{ background:{theme.BG_PANEL}; border:2px solid {theme.ACCENT}; border-radius:12px; }}"
            f"QLabel {{ background:transparent; }}")
        self.bubble.setFixedWidth(400)
        v = QVBoxLayout(self.bubble)
        v.setContentsMargins(16, 12, 16, 12)
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        self.lbl_title = QLabel()
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-size:12pt; font-weight:bold;")
        self.lbl_text = QLabel()
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setTextFormat(Qt.RichText)
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet(f"color:{theme.WARN};")
        for w in (self.lbl_count, self.lbl_title, self.lbl_text, self.lbl_status):
            v.addWidget(w)
        row = QHBoxLayout()
        self.btn_skip_all = QPushButton(tr("ข้ามบทเรียน"))
        self.btn_skip_all.clicked.connect(lambda: self.finish(False))
        self.btn_next = QPushButton(tr("ถัดไป ▶"))
        self.btn_next.setObjectName("Primary")
        self.btn_next.clicked.connect(self.next)
        row.addWidget(self.btn_skip_all)
        row.addStretch(1)
        row.addWidget(self.btn_next)
        v.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._tick)
        win.installEventFilter(self)

    # ---------- ควบคุม ----------
    @property
    def step(self) -> TStep | None:
        return self.steps[self.index] if 0 <= self.index < len(self.steps) else None

    def start(self):
        self.setGeometry(self.win.rect())
        self.show()
        self.raise_()
        self.goto(0)
        self.timer.start()

    def goto(self, i: int):
        if i >= len(self.steps):
            self.finish(True)
            return
        self.index = i
        st = self.steps[i]
        if st.prepare:
            st.prepare()
        self._entered = time.monotonic()
        self._ok_since = None
        self.lbl_count.setText(tr("🎓 {0} · ขั้นที่ {1}/{2}", self.title, i + 1, len(self.steps)))
        self.lbl_title.setText(st.title)
        self.lbl_text.setText(st.text)
        self.lbl_status.setText(tr("👉 ทำตามขั้นนี้ แล้วระบบจะไปขั้นถัดไปเอง") if st.done else "")
        last = i == len(self.steps) - 1
        self.btn_next.setText(tr("เสร็จสิ้น ✔") if last else (tr("ข้ามขั้นนี้ ▶") if st.done else tr("ถัดไป ▶")))
        self.btn_skip_all.setVisible(not last)
        self._relayout()

    def next(self):
        self.goto(self.index + 1)

    def finish(self, completed: bool):
        if self.index < 0 and not self.isVisible():
            return
        self.timer.stop()
        self.win.removeEventFilter(self)
        self.hide()
        self.index = -1
        self.finished.emit(completed)
        self.deleteLater()

    # ---------- เงื่อนไข / ตำแหน่ง ----------
    def _tick(self):
        st = self.step
        if st is None:
            return
        if self.geometry() != self.win.rect():
            self.setGeometry(self.win.rect())
        self.raise_()
        self._relayout()
        if st.done is None:
            return
        try:
            ok = bool(st.done())
        except Exception:      # noqa: BLE001 — เงื่อนไขพังต้องไม่ทำให้โปรแกรมล้ม
            ok = False
        now = time.monotonic()
        if not ok:
            self._ok_since = None
            return
        if self._ok_since is None:
            self._ok_since = now
            self.lbl_status.setText(tr("✔ ทำได้แล้ว!"))
            self.lbl_status.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:bold;")
        if now - self._ok_since >= DWELL_S:
            self.completed.append(self.index)
            self.lbl_status.setStyleSheet(f"color:{theme.WARN};")
            self.next()

    def target_rect(self) -> QRect:
        st = self.step
        w = st.target() if (st and st.target) else None
        if w is None or not w.isVisible() or w.window() is not self.win:
            return QRect()
        top_left = w.mapTo(self.win, QPoint(0, 0))
        return QRect(top_left, w.size()).adjusted(-PAD, -PAD, PAD, PAD).intersected(self.rect())

    def _relayout(self):
        hole = self.target_rect()
        if hole != self.hole or self.mask().isEmpty():
            self.hole = hole
            region = QRegion(self.rect())
            if not hole.isEmpty():
                region = region.subtracted(QRegion(hole))
            self.setMask(region)
            self.update()
        self.bubble.adjustSize()
        bw, bh = self.bubble.width(), self.bubble.height()
        r = self.rect()
        if hole.isEmpty():
            x, y = r.center().x() - bw // 2, r.center().y() - bh // 2
        else:
            x = min(max(hole.center().x() - bw // 2, 12), r.width() - bw - 12)
            if hole.bottom() + 14 + bh < r.height():
                y = hole.bottom() + 14
            elif hole.top() - 14 - bh > 0:
                y = hole.top() - 14 - bh
            else:                               # ช่องใหญ่เกือบเต็มจอ → วางด้านข้าง/มุม
                y = max(12, r.height() - bh - 12)
                x = 12 if hole.center().x() > r.width() // 2 else r.width() - bw - 12
        self.bubble.move(x, y)
        self.bubble.raise_()

    def eventFilter(self, obj, e):
        if obj is self.win and e.type() == QEvent.Resize:
            self.setGeometry(self.win.rect())
            self._relayout()
        return False

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRect(self.rect())
        if not self.hole.isEmpty():
            cut = QPainterPath()
            cut.addRoundedRect(self.hole, 8, 8)
            path = path.subtracted(cut)
        p.fillPath(path, QColor(5, 8, 14, 165))
        if not self.hole.isEmpty():
            p.setPen(QPen(QColor(theme.ACCENT), 3))
            p.drawRoundedRect(self.hole.adjusted(-2, -2, 2, 2), 9, 9)
