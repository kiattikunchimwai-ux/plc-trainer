"""Tool Palette: รายการอุปกรณ์แยกหมวด — ลากไปวางบนผัง หรือดับเบิลคลิกเพื่อวางกลางจอ."""
from __future__ import annotations

from ...i18n import tr

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ...panel.catalog import CATALOG, CATEGORIES
from ...panel.model import DeviceSpec
from .. import state, theme
from .items import ConveyorItem, make_item
from .view import MIME

ICON = 44


def device_icon(kind: str) -> QIcon:
    spec = DeviceSpec.new(kind)
    if kind == "conveyor":
        spec.props["length"] = 140
    if kind == "sevenseg":
        spec.props["digits"] = 1
    item = make_item(spec)
    sc = QGraphicsScene()
    sc.addItem(item)
    src = item.mapRectToScene(item.body_rect()).adjusted(-2, -2, 2, 2)
    crops = {"cylinder": QRectF(-34, -36, 96, 72),        # เฉพาะตัวกระบอกสูบ
             "setvalue": QRectF(-30, -28, 60, 56),         # เฉพาะช่องตัวเลข
             "tank": QRectF(-50, -60, 100, 120)}
    if kind in crops:
        src = crops[kind]
    elif isinstance(item, ConveyorItem):
        src = item.mapRectToScene(item.body_rect()).adjusted(-4, -36, 4, 4)   # ไม่รวมปุ่ม + ชิ้นงาน
    pm = QPixmap(ICON, ICON)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    side = max(src.width(), src.height())
    tgt = QRectF(0, 0, ICON, ICON)
    sq = QRectF(src.center().x() - side / 2, src.center().y() - side / 2, side, side)
    sc.render(p, tgt, sq)
    p.end()
    return QIcon(pm)


RECENT_MAX = 6
RECENT = "__recent__"


def tooltip_for(info) -> str:
    io = " / ".join(info.prefixes) if info.prefixes else tr("ไม่มี (ใช้ตกแต่ง/อธิบายผัง)")
    t = f"<b>{info.name}</b>"
    if info.desc:
        t += f"<br>{info.desc}"
    return t + f"<br><span style='color:{theme.TEXT_DIM}'>address: {io}</span>"


def search_text(info) -> str:
    return " ".join((info.kind, info.name, info.aliases, info.desc)).lower()


class _Tree(QTreeWidget):
    dropped = Signal(str)

    def startDrag(self, actions):
        it = self.currentItem()
        kind = it.data(0, Qt.UserRole) if it else None
        if not kind:
            return
        md = QMimeData()
        md.setData(MIME, kind.encode())
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.setPixmap(it.icon(0).pixmap(ICON, ICON))
        if drag.exec(Qt.CopyAction) == Qt.CopyAction:
            self.dropped.emit(kind)


class LibraryPanel(QWidget):
    add_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        hint = QLabel(tr("ลากอุปกรณ์ไปวางบนผัง\n(ดับเบิลคลิก = วางกลางจอ)"))
        hint.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        lay.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("🔍 ค้นหา เช่น มอเตอร์, sensor, timer…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        lay.addWidget(self.search)
        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(ICON, ICON))
        self.tree.setDragEnabled(True)
        self.tree.setIndentation(10)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background:{theme.BG_PANEL_DARK}; border:none; }}"
            f"QTreeWidget::item {{ padding:2px; }}"
            f"QTreeWidget::item:hover {{ background:#3B4453; }}"
            f"QTreeWidget::item:selected {{ background:{theme.ACCENT}; }}")
        self._icons = {k: device_icon(k) for k in CATALOG}
        self.cats: dict[str, QTreeWidgetItem] = {}
        ui = state.load()
        collapsed = set(ui.get("palette_collapsed", []))
        self.recent: list[str] = [k for k in ui.get("recent_kinds", []) if k in CATALOG][:RECENT_MAX]
        for cat, title in [(RECENT, tr("★ ใช้ล่าสุด"))] + list(CATEGORIES):
            top = QTreeWidgetItem([title])
            top.setFlags(Qt.ItemIsEnabled)
            top.setData(0, Qt.UserRole + 1, cat)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            self.cats[cat] = top
            if cat != RECENT:
                for info in CATALOG.values():
                    if info.category == cat:
                        top.addChild(self._child(info.kind))
            top.setExpanded(cat not in collapsed)
        self._fill_recent()
        self.tree.itemDoubleClicked.connect(self._dbl)
        self.tree.dropped.connect(self.remember)
        self.tree.itemExpanded.connect(self._save_collapsed)
        self.tree.itemCollapsed.connect(self._save_collapsed)
        lay.addWidget(self.tree, 1)

    def _child(self, kind: str) -> QTreeWidgetItem:
        info = CATALOG[kind]
        ch = QTreeWidgetItem([info.name])
        ch.setData(0, Qt.UserRole, kind)
        ch.setIcon(0, self._icons[kind])
        ch.setToolTip(0, tooltip_for(info))
        return ch

    def _fill_recent(self):
        top = self.cats[RECENT]
        top.takeChildren()
        for k in self.recent:
            top.addChild(self._child(k))
        top.setHidden(not self.recent)

    def remember(self, kind: str):
        self.recent = [kind] + [k for k in self.recent if k != kind]
        self.recent = self.recent[:RECENT_MAX]
        self._fill_recent()
        state.update(recent_kinds=self.recent)
        self.filter(self.search.text())

    def filter(self, text: str = ""):
        """กรองตามชื่อไทย/อังกฤษ/คำอธิบาย — ทุกคำที่พิมพ์ต้องเจอ."""
        words = text.lower().split()
        for cat, top in self.cats.items():
            shown = 0
            for i in range(top.childCount()):
                ch = top.child(i)
                ok = all(w in search_text(CATALOG[ch.data(0, Qt.UserRole)]) for w in words)
                ch.setHidden(not ok)
                shown += ok
            top.setHidden(shown == 0 or (cat == RECENT and bool(words)))
            if words:
                top.setExpanded(True)
        if not words:                 # ล้างคำค้น → กลับไปสถานะพับ/กางที่จำไว้
            collapsed = set(state.load().get("palette_collapsed", []))
            for cat, top in self.cats.items():
                top.setExpanded(cat not in collapsed)

    def visible_kinds(self) -> list[str]:
        out = []
        for cat, top in self.cats.items():
            if top.isHidden() or cat == RECENT:
                continue
            out += [top.child(i).data(0, Qt.UserRole) for i in range(top.childCount()) if not top.child(i).isHidden()]
        return out

    def _save_collapsed(self, _item=None):
        if self.search.text().strip():
            return                    # กางเพราะค้นหา ไม่นับเป็นการตั้งค่าของผู้ใช้
        state.update(palette_collapsed=[c for c, t in self.cats.items() if not t.isExpanded()])

    def _dbl(self, it, col):
        kind = it.data(0, Qt.UserRole)
        if kind:
            self.add_requested.emit(kind)
            self.remember(kind)
