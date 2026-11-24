"""แถบไอคอนข้างจอ (แบบ VS Code): คลิกไอคอน = กางแผง · คลิกซ้ำ = ยุบ · จำสถานะไว้ใน ui_state."""
from __future__ import annotations

from ...i18n import tr

from PySide6.QtCore import QEasingCurve, QVariantAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import state, theme

ANIMATE = True            # test ปิดได้ เพื่อให้ผลทันที
DEFAULT_W = 300


class ActivityBar(QFrame):
    clicked = Signal(str)

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityBar")
        self.setProperty("side", side)
        self.setFixedWidth(52)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 8, 6, 8)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)
        self.buttons: dict[str, QToolButton] = {}
        self._badges: dict[str, QLabel] = {}

    def add(self, key: str, icon: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("Activity")
        b.setText(icon)
        b.setToolTip(tip)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=key: self.clicked.emit(k))
        dot = QLabel(b)
        dot.setFixedSize(9, 9)
        dot.move(29, 3)
        dot.setStyleSheet(f"background:{theme.WARN}; border-radius:4px;")
        dot.hide()
        self._lay.insertWidget(self._lay.count() - 1, b, 0, Qt.AlignHCenter)
        self.buttons[key] = b
        self._badges[key] = dot
        return b

    def set_active(self, key: str | None):
        for k, b in self.buttons.items():
            b.setChecked(k == key)

    def set_badge(self, key: str, on: bool):
        if key in self._badges:
            self._badges[key].setVisible(on)

    def has_badge(self, key: str) -> bool:
        return key in self._badges and not self._badges[key].isHidden()


class SidePane(QFrame):
    close_requested = Signal()

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePane")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 4, 0)
        self.title = QLabel()
        self.title.setObjectName("PaneTitle")
        btn = QToolButton()
        btn.setObjectName("PaneClose")
        btn.setText("«" if side == "left" else "»")
        btn.setToolTip(tr("ยุบแผง"))
        btn.clicked.connect(self.close_requested)
        head.addWidget(self.title, 1)
        head.addWidget(btn)
        v.addLayout(head)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self.pages: dict[str, tuple[str, QWidget]] = {}

    def add(self, key: str, title: str, widget: QWidget):
        self.pages[key] = (title, widget)
        self.stack.addWidget(widget)

    def show_page(self, key: str):
        title, w = self.pages[key]
        self.title.setText(title.upper())
        self.stack.setCurrentWidget(w)


class SideDock:
    """แถบไอคอน + แผง 1 ฝั่ง; แผงอยู่ใน QSplitter ร่วมกับพื้นที่กลาง."""

    def __init__(self, side: str, splitter: QSplitter, index: int):
        self.side = side
        self.splitter = splitter
        self.index = index
        self.bar = ActivityBar(side)
        self.pane = SidePane(side)
        self.pane.setMinimumWidth(0)
        self.pane.close_requested.connect(self.collapse)
        self.bar.clicked.connect(self.toggle)
        self.current: str | None = None
        self.is_open = False
        self.width = DEFAULT_W
        self._anim: QVariantAnimation | None = None
        self.on_change = None          # callback(side, key, open)

    # ---------- หน้า ----------
    def add(self, key: str, icon: str, title: str, widget: QWidget, tip: str = ""):
        self.bar.add(key, icon, tip or title)
        self.pane.add(key, title, widget)
        if self.current is None:
            self.current = key

    def set_page_visible(self, key: str, on: bool):
        """ซ่อน/แสดงไอคอน (เช่น แผงครู) — ถ้ากำลังเปิดหน้านั้นอยู่จะยุบแผง."""
        self.bar.buttons[key].setVisible(on)
        if not on and self.is_open and self.current == key:
            self.collapse()

    # ---------- เปิด/ยุบ ----------
    def open(self, key: str | None = None):
        key = key or self.current
        if key not in self.pane.pages:
            return
        self.current = key
        self.pane.show_page(key)
        self.bar.set_badge(key, False)
        self.bar.set_active(key)
        if not self.is_open:
            self.is_open = True
            self.pane.show()
            self._animate(0, self.width)
        self._changed()

    def collapse(self):
        if not self.is_open:
            return
        cur = self._pane_size()
        if cur > 40:
            self.width = cur
        self.is_open = False
        self.bar.set_active(None)
        self._animate(cur, 0, hide_after=True)
        self._changed()

    def toggle(self, key: str):
        if self.is_open and self.current == key:
            self.collapse()
        else:
            self.open(key)

    def is_showing(self, key: str) -> bool:
        return self.is_open and self.current == key

    # ---------- ความกว้าง ----------
    def _pane_size(self) -> int:
        sizes = self.splitter.sizes()
        return sizes[self.index] if self.index < len(sizes) else 0

    def _set_pane_size(self, w: int):
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            return
        total = sum(sizes)
        sizes[self.index] = int(w)
        mid = 1
        others = sum(s for i, s in enumerate(sizes) if i != mid)
        sizes[mid] = max(100, total - others)
        self.splitter.setSizes(sizes)

    def _animate(self, a: int, b: int, hide_after=False):
        if self._anim:
            self._anim.stop()
        if not ANIMATE or not self.splitter.isVisible():
            self._set_pane_size(b)
            if hide_after:
                self.pane.hide()
            return
        an = QVariantAnimation(self.splitter)
        an.setDuration(150)
        an.setEasingCurve(QEasingCurve.OutCubic)
        an.setStartValue(int(a))
        an.setEndValue(int(b))
        an.valueChanged.connect(lambda v: self._set_pane_size(v))
        if hide_after:
            an.finished.connect(lambda: (not self.is_open) and self.pane.hide())
        self._anim = an
        an.start()

    # ---------- จำสถานะ ----------
    def _changed(self):
        if self.on_change:
            self.on_change(self.side, self.current, self.is_open)

    def save(self):
        w = self._pane_size() if self.is_open else self.width
        state.update(**{f"pane_{self.side}": {"key": self.current, "open": self.is_open,
                                               "w": int(w if w > 40 else self.width)}})

    def restore(self, default_open: bool = True):
        d = state.load().get(f"pane_{self.side}") or {}
        self.width = int(d.get("w", DEFAULT_W)) or DEFAULT_W
        key = d.get("key") if d.get("key") in self.pane.pages else self.current
        self.current = key
        self.is_open = False
        if d.get("open", default_open) and not self.bar.buttons[key].isHidden():
            self.open(key)
        else:
            self.pane.hide()
            self.bar.set_active(None)


class PaneHandle:
    """ทำตัวเหมือน QDockWidget เดิม (show / raise_ / isVisible) เพื่อให้โค้ดเก่าเรียกต่อได้."""

    def __init__(self, dock: SideDock, key: str):
        self.dock = dock
        self.key = key

    def show(self):
        self.dock.open(self.key)

    def raise_(self):
        self.dock.open(self.key)

    def hide(self):
        if self.dock.is_showing(self.key):
            self.dock.collapse()

    def isVisible(self) -> bool:  # noqa: N802 — ชื่อตาม Qt
        return self.dock.is_showing(self.key)

    def widget(self):
        return self.dock.pane.pages[self.key][1]
