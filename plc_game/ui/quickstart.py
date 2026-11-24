"""หน้าเริ่มต้น (Quick Start): ผังล่าสุด + ฉากโรงงานสำเร็จรูป + เลือกการเชื่อมต่อ PLC."""
from __future__ import annotations

from ..i18n import tr, tr_data

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from ..panel import PanelDoc
from . import state, theme

ROOT = Path(__file__).resolve().parents[2]
MANUALS = [(tr("📘 คู่มือการใช้งาน"), ROOT / "docs" / "คู่มือการใช้งาน_PLC_Trainer.pdf"),   # i18n: skip
           (tr("🔌 ตั้งค่า GX Simulator3"), ROOT / "docs" / "คู่มือตั้งค่า_GX_Simulator3.pdf")]   # i18n: skip (คู่มือมีแต่ภาษาไทย)

# (ไฟล์ใน panels/, ระดับ, คำโปรย)
SCENES = [
    ("reversing.plcpanel", tr("พื้นฐาน"), tr("กลับทางหมุนมอเตอร์ + Interlock")),
    ("traffic.plcpanel", tr("พื้นฐาน"), tr("Timer เรียงลำดับไฟจราจร")),
    ("star_delta.plcpanel", tr("พื้นฐาน"), tr("สตาร์ทมอเตอร์แบบสตาร์-เดลต้า")),
    ("parking.plcpanel", tr("พื้นฐาน"), tr("Counter นับรถเข้า-ออก")),
    ("tank.plcpanel", tr("กลาง"), tr("ควบคุมระดับน้ำ + E-Stop")),
    ("garage_door.plcpanel", tr("กลาง"), tr("ประตูม้วน + เซนเซอร์กันหนีบ")),
    ("cylinder_AplusBplus.plcpanel", tr("กลาง"), tr("ลำดับกระบอกสูบนิวแมติก")),
    ("elevator3.plcpanel", tr("ยาก"), tr("ลิฟต์ 3 ชั้น")),
    ("sorting.plcpanel", tr("ยาก"), tr("คัดแยกโลหะ / พลาสติกบนสายพาน")),
    ("mixing.plcpanel", tr("ยาก"), tr("ถังผสม: ระดับ + อุณหภูมิ + ลำดับขั้น")),
    ("vfd_conveyor.plcpanel", tr("ยาก"), tr("Analog → VFD คุมความเร็วสายพาน")),
    ("air_system.plcpanel", tr("กลาง"), tr("ปั๊มลม + สวิตช์ความดัน (hysteresis)")),
    ("pick_place.plcpanel", tr("ยาก"), tr("แขนหยิบ-วาง 2 แกน + สายพาน")),
]
LEVEL_COLOR = {tr("พื้นฐาน"): "#5EE36A", tr("กลาง"): "#F2D648", tr("ยาก"): "#FF7A59"}
THUMB = QSize(232, 136)
MAX_RECENT = 6


def remember_recent(path: Path):
    """เก็บผังที่เปิดล่าสุด (ไม่เกิน 6 ไฟล์) ใน ui_state."""
    p = str(Path(path).resolve())
    rec = [r for r in state.load().get("recent", []) if r != p]
    state.update(recent=[p] + rec[:MAX_RECENT - 1])


def recent_panels() -> list[Path]:
    return [Path(r) for r in state.load().get("recent", []) if Path(r).exists()]


def thumbnail(doc: PanelDoc, size: QSize = THUMB) -> QPixmap:
    """วาดผังลงภาพเล็ก (ใช้ scene จริง จึงหน้าตาเหมือนในโปรแกรม)."""
    from .panel.view import PanelView
    v = PanelView()
    v.load_doc(doc)
    v.set_run_mode(True)
    pm = QPixmap(size)
    pm.fill(QColor(theme.BG_CANVAS))
    r = v.sc.itemsBoundingRect().adjusted(-16, -16, 16, 16)
    if not r.isEmpty():
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.SmoothPixmapTransform)
        v.sc.render(qp, QRectF(0, 0, size.width(), size.height()), r, Qt.KeepAspectRatio)
        qp.end()
    v.deleteLater()
    return pm


class QuickStartDialog(QDialog):
    """ผลลัพธ์: self.path (ผังที่เลือก) หรือ self.action = "new" / "browse" และ self.backend = mock / soft / slmp / None."""

    def __init__(self, parent=None, current_backend="mock"):
        super().__init__(parent)
        self.setWindowTitle(tr("PLC Trainer — เริ่มต้นใช้งาน"))
        self.resize(1120, 760)
        self.path: Path | None = None
        self.action = ""
        self.backend: str | None = None
        self.cards: dict[str, QToolButton] = {}

        root = QHBoxLayout(self)
        # ---------- ซ้าย: เริ่มงาน / เชื่อมต่อ / คู่มือ ----------
        side = QVBoxLayout()
        title = QLabel("PLC Trainer")
        title.setStyleSheet(f"font-size:20pt; font-weight:bold; color:{theme.ACCENT};")
        side.addWidget(title)
        side.addWidget(self._dim(tr("ฝึกเขียน Ladder กับอุปกรณ์จำลอง")))
        side.addSpacing(10)
        b_new = QPushButton(tr("📄  ผังใหม่ (วางอุปกรณ์เอง)"))
        b_new.clicked.connect(lambda: self._done(action="new"))
        b_open = QPushButton(tr("📂  เปิดไฟล์ผัง…"))
        b_open.clicked.connect(lambda: self._done(action="browse"))
        for b in (b_new, b_open):
            b.setMinimumHeight(36)
            side.addWidget(b)
        side.addSpacing(14)
        side.addWidget(self._head(tr("เชื่อมต่อ PLC หลังเปิดผัง")))
        self.grp = QButtonGroup(self)
        for i, (key, text) in enumerate((("mock", tr("Mock PLC (ทดสอบ ไม่ต้องมี GX Works3)")),
                                         ("soft", tr("PLC ในตัว (รัน ladder ไม่ต้องมี GX Works3)")),
                                         ("slmp", "GX Simulator3 (SLMP)"),
                                         ("", tr("ยังไม่เชื่อมต่อ")))):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            rb.setChecked(key == (current_backend or ""))
            self.grp.addButton(rb, i)
            side.addWidget(rb)
        side.addSpacing(14)
        side.addWidget(self._head(tr("คู่มือ")))
        for text, pdf in MANUALS:
            b = QPushButton(text)
            b.setEnabled(pdf.exists())
            b.clicked.connect(lambda _=False, p=pdf: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            side.addWidget(b)
        side.addStretch(1)
        self.cb_show = QCheckBox(tr("แสดงหน้านี้ทุกครั้งที่เปิดโปรแกรม"))
        self.cb_show.setChecked(bool(state.load().get("quickstart", False)))
        self.cb_show.toggled.connect(lambda on: state.update(quickstart=on))
        side.addWidget(self.cb_show)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(290)
        root.addWidget(sw)

        # ---------- ขวา: การ์ดผัง ----------
        body = QWidget()
        grid = QVBoxLayout(body)
        recent = recent_panels()
        if recent:
            grid.addWidget(self._head(tr("ผังล่าสุด")))
            grid.addLayout(self._cards([(p, "", p.parent.name) for p in recent]))
        grid.addWidget(self._head(tr("ฉากโรงงานสำเร็จรูป — คลิกเพื่อเปิด")))
        panels = state.PANEL_DIR
        scenes = [(panels / f, lvl, blurb) for f, lvl, blurb in SCENES if (panels / f).exists()]
        if not scenes:
            grid.addWidget(self._dim(tr("ไม่พบผังตัวอย่าง — รัน tools\\make_example_panels.py")))
        grid.addLayout(self._cards(scenes))
        grid.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(body)
        root.addWidget(sc, 1)

    # ---------- helpers ----------
    @staticmethod
    def _head(text):
        lb = QLabel(text)
        lb.setStyleSheet(f"font-size:11pt; font-weight:bold; color:{theme.TEXT}; padding-top:6px;")
        return lb

    @staticmethod
    def _dim(text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.TEXT_DIM};")
        return lb

    def _cards(self, items) -> QGridLayout:
        g = QGridLayout()
        g.setSpacing(10)
        for i, (path, level, blurb) in enumerate(items):
            try:
                doc = PanelDoc.load(path)
            except (OSError, ValueError):
                continue
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(QIcon(thumbnail(doc)))
            b.setIconSize(THUMB)
            b.setFixedSize(THUMB.width() + 16, THUMB.height() + 62)
            name = tr_data(doc.name) or path.stem
            b.setText(f"{name}\n{level + ' · ' if level else ''}{blurb}")
            b.setToolTip(tr("{0} — {1} อุปกรณ์", path.name, len(doc.devices)))
            col = LEVEL_COLOR.get(level, theme.BORDER)
            b.setStyleSheet(f"QToolButton {{ background:{theme.BG_PANEL_DARK}; border:1px solid {theme.BORDER};"
                            f" border-top:3px solid {col}; border-radius:4px; padding:4px; text-align:left; }}"
                            f"QToolButton:hover {{ border-color:{theme.ACCENT}; background:{theme.BG_PANEL}; }}")
            b.clicked.connect(lambda _=False, p=path: self._done(path=p))
            self.cards[path.name] = b
            g.addWidget(b, i // 3, i % 3)
        return g

    def _done(self, path: Path | None = None, action: str = ""):
        self.path = path
        self.action = action or "open"
        btn = self.grp.checkedButton()
        self.backend = (btn.property("key") or None) if btn else None
        self.accept()
