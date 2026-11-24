"""วาดแบบวงจรต่อสาย PLC (สัญลักษณ์แบบ IEC อย่างง่าย) บนกระดาษขาว + Export PNG/PDF.

ซ้าย: ราง (0V หรือ +24V ตาม S/S) → หน้าสัมผัส/เซนเซอร์ → ขา X · กลาง: PLC · ขวา: ขา Y → โหลด → ราง 0V
"""
from __future__ import annotations

from ..i18n import tr

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
)

from ..panel.wiring import SYM_TH, Wiring
from . import theme

ROW = 48
W = 1300
TOP = 120
PLC_X, PLC_W = 470, 240
INK = QColor("#1B2230")
DIM = QColor("#5B6576")
RED, BLUE, BROWN, BLACK = QColor("#C62828"), QColor("#1565C0"), QColor("#7B4A21"), QColor("#111111")


def diagram_size(w: Wiring) -> QSize:
    rows = max(len(w.inputs), len(w.outputs), 1)
    notes = len(w.warnings) + min(len(w.others), 8) + 3
    return QSize(W, TOP + rows * ROW + 90 + notes * 20)


def _font(p: QPainter, pt: float, bold=False):
    f = QFont("Segoe UI", 1)
    f.setPointSizeF(pt)
    f.setBold(bold)
    p.setFont(f)


def _tag(p: QPainter, x, y, text, col: QColor, left=True):
    """ป้ายปลายสาย เช่น +24V / 0V."""
    _font(p, 8, True)
    fm = p.fontMetrics()
    tw = fm.horizontalAdvance(text) + 10
    r = QRectF(x - tw if left else x, y - 9, tw, 18)
    p.setPen(QPen(col, 1.2))
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(r, 4, 4)
    p.drawText(r, Qt.AlignCenter, text)


def _caption(p, x, y, text, width=200):
    _font(p, 8.5)
    p.setPen(DIM)
    p.drawText(QRectF(x, y - 22, width, 16), Qt.AlignLeft | Qt.AlignVCenter,
               p.fontMetrics().elidedText(text, Qt.ElideRight, width))


def _contact(p, x, y, nc: bool):
    """หน้าสัมผัส: สายเข้า x → ใบสัมผัสเอียง → สายออก x+30."""
    p.setPen(QPen(INK, 2))
    p.drawLine(QPointF(x, y), QPointF(x + 4, y))
    p.drawLine(QPointF(x + 4, y), QPointF(x + 28, y - 11))
    p.drawLine(QPointF(x + 30, y - 6), QPointF(x + 30, y))
    if nc:
        p.drawLine(QPointF(x + 30, y - 6), QPointF(x + 18, y - 6))   # NC: ขีดรองใบสัมผัส


def paint(p: QPainter, w: Wiring, title: str = "") -> None:
    size = diagram_size(w)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(QRectF(0, 0, size.width(), size.height()), QColor("#FFFFFF"))
    _font(p, 14, True)
    p.setPen(INK)
    p.drawText(QRectF(30, 14, W - 60, 28), Qt.AlignLeft | Qt.AlignVCenter, tr("แบบวงจรต่อสาย PLC") + (f" — {title}" if title else ""))
    _font(p, 9)
    p.setPen(DIM)
    common = (tr("NPN / sink: S/S → +24V · สวิตช์ต่อจาก 0V เข้าขา X") if w.common == "sink"
              else tr("PNP / source: S/S → 0V · สวิตช์ต่อจาก +24V เข้าขา X"))
    p.drawText(QRectF(30, 44, W - 60, 20), Qt.AlignLeft, tr("Input: {0}  ·  Output รีเลย์: COM → +24V, โหลดต่อลง 0V", common))

    rows = max(len(w.inputs), len(w.outputs), 1)
    y0 = TOP
    y_end = y0 + rows * ROW
    # ราง
    lx, rx = 50, W - 50
    rail_in = QColor(BLUE if w.switch_from == "0V" else RED)
    p.setPen(QPen(rail_in, 3))
    p.drawLine(QPointF(lx, y0 - 30), QPointF(lx, y_end - ROW / 2 + 4))
    _tag(p, lx + 28, y0 - 40, w.switch_from, rail_in, left=True)
    p.setPen(QPen(BLUE, 3))
    p.drawLine(QPointF(rx, y0 - 30), QPointF(rx, y_end - ROW / 2 + 4))
    _tag(p, rx - 28, y0 - 40, "0V", BLUE, left=False)

    # PLC
    box = QRectF(PLC_X, y0 - 34, PLC_W, rows * ROW + 64)
    p.setPen(QPen(INK, 2))
    p.setBrush(QColor("#EEF2F8"))
    p.drawRoundedRect(box, 8, 8)
    _font(p, 11, True)
    p.drawText(QRectF(PLC_X, y0 - 32, PLC_W, 22), Qt.AlignCenter, "PLC")
    _font(p, 8)
    p.setPen(DIM)
    p.drawText(QRectF(PLC_X, y0 - 14, PLC_W / 2, 14), Qt.AlignCenter, "INPUT")
    p.drawText(QRectF(PLC_X + PLC_W / 2, y0 - 14, PLC_W / 2, 14), Qt.AlignCenter, tr("OUTPUT (รีเลย์)"))

    def terminal(x, y, text, right=False):
        r = QRectF(x - (0 if right else 0), y - 10, 56, 20)
        if right:
            r.moveRight(x)
        else:
            r.moveLeft(x)
        p.setPen(QPen(INK, 1.4))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(r)
        _font(p, 9, True)
        p.setPen(INK)
        p.drawText(r, Qt.AlignCenter, text)

    # ---------- Input ----------
    for i, t in enumerate(w.inputs):
        y = y0 + i * ROW + ROW / 2
        terminal(PLC_X, y, t.addr)
        p.setPen(QPen(INK, 1.6))
        if t.symbol == "sensor":
            bx = 150
            r = QRectF(bx, y - 15, 96, 30)
            p.setBrush(QColor("#FFF8E1"))
            p.drawRoundedRect(r, 5, 5)
            _font(p, 8.5, True)
            p.drawText(r, Qt.AlignCenter, f"SENSOR {t.output.upper()}")
            p.setPen(QPen(BROWN, 2))
            p.drawLine(QPointF(bx, y - 8), QPointF(bx - 30, y - 8))
            _tag(p, bx - 30, y - 8, "+24V", BROWN)
            p.setPen(QPen(BLUE, 2))
            p.drawLine(QPointF(bx, y + 8), QPointF(bx - 30, y + 8))
            _tag(p, bx - 30, y + 8, "0V", BLUE)
            p.setPen(QPen(BLACK, 2))
            p.drawLine(QPointF(bx + 96, y), QPointF(PLC_X, y))
            _caption(p, bx + 100, y, tr("{0} (ดำ)", t.caption), PLC_X - bx - 110)
        else:
            p.drawLine(QPointF(lx, y), QPointF(200, y))
            _contact(p, 200, y, t.symbol == "nc")
            p.setPen(QPen(INK, 1.6))
            p.drawLine(QPointF(230, y), QPointF(PLC_X, y))
            _caption(p, 244, y, f"{t.caption} ({'NC' if t.symbol == 'nc' else 'NO'})", PLC_X - 254)
        p.setPen(QPen(rail_in, 0))
        if t.symbol != "sensor":
            p.setBrush(INK)
            p.drawEllipse(QPointF(lx, y), 3, 3)
    # S/S
    ys = y0 + rows * ROW + 12
    terminal(PLC_X, ys, "S/S")
    p.setPen(QPen(RED if w.ss_to == "+24V" else BLUE, 2))
    p.drawLine(QPointF(PLC_X, ys), QPointF(PLC_X - 60, ys))
    _tag(p, PLC_X - 60, ys, w.ss_to, RED if w.ss_to == "+24V" else BLUE)

    # ---------- Output ----------
    ox = PLC_X + PLC_W
    for i, t in enumerate(w.outputs):
        y = y0 + i * ROW + ROW / 2
        terminal(ox, y, t.addr, right=True)
        p.setPen(QPen(INK, 1.6))
        sx = 960
        p.drawLine(QPointF(ox, y), QPointF(sx, y))
        p.setBrush(QColor("#FFFFFF"))
        if t.symbol == "lamp":
            p.drawEllipse(QPointF(sx + 14, y), 12, 12)
            p.drawLine(QPointF(sx + 6, y - 8), QPointF(sx + 22, y + 8))
            p.drawLine(QPointF(sx + 22, y - 8), QPointF(sx + 6, y + 8))
            end = sx + 26
        elif t.symbol == "buzzer":
            p.drawRect(QRectF(sx, y - 11, 28, 22))
            _font(p, 8, True)
            p.drawText(QRectF(sx, y - 11, 28, 22), Qt.AlignCenter, "BZ")
            end = sx + 28
        else:
            p.drawRect(QRectF(sx, y - 9, 34, 18))
            _font(p, 8, True)
            p.drawText(QRectF(sx, y - 9, 34, 18), Qt.AlignCenter, "K" if t.symbol == "contactor" else "SOL")
            end = sx + 34
            if t.symbol == "contactor":
                _font(p, 8)
                p.setPen(DIM)
                p.drawText(QRectF(sx + 38, y - 9, 60, 18), Qt.AlignLeft | Qt.AlignVCenter, "→ ⓜ 380V")
                p.setPen(QPen(INK, 1.6))
                end = sx + 34
        p.setPen(QPen(INK, 1.6))
        dy = 0
        if t.symbol == "contactor":            # เดินสายลงใต้ป้าย "→ ⓜ 380V" ไม่ให้ทับตัวหนังสือ
            dy = 14
            p.drawLine(QPointF(end, y), QPointF(end + 4, y))
            p.drawLine(QPointF(end + 4, y), QPointF(end + 4, y + dy))
            p.drawLine(QPointF(end + 4, y + dy), QPointF(rx, y + dy))
        else:
            p.drawLine(QPointF(end, y), QPointF(rx, y))
        p.setBrush(INK)
        p.drawEllipse(QPointF(rx, y + dy), 3, 3)
        cap = t.caption + (f" ∥ {', '.join(t.parallel)}" if t.parallel else "")
        _caption(p, ox + 12, y, f"{cap} — {SYM_TH[t.symbol]}", sx - ox - 16)
    terminal(ox, ys, "COM", right=True)
    p.setPen(QPen(RED, 2))
    p.drawLine(QPointF(ox, ys), QPointF(ox + 60, ys))
    _tag(p, ox + 60, ys, "+24V", RED, left=False)

    # ---------- หมายเหตุ ----------
    ny = ys + 40
    _font(p, 9)
    if not w.inputs and not w.outputs:
        p.setPen(DIM)
        p.drawText(QRectF(30, ny, W - 60, 18), Qt.AlignLeft, tr("ผังนี้ยังไม่มีอุปกรณ์ที่ใช้ขา X / Y"))
        ny += 20
    for x in w.warnings:
        p.setPen(QColor("#B45309"))
        p.drawText(QRectF(30, ny, W - 60, 18), Qt.AlignLeft, "⚠ " + x)
        ny += 20
    p.setPen(DIM)
    for x in w.others[:8]:
        p.drawText(QRectF(30, ny, W - 60, 18), Qt.AlignLeft, "• " + x)
        ny += 20
    if len(w.others) > 8:
        p.drawText(QRectF(30, ny, W - 60, 18), Qt.AlignLeft, tr("… และอีก {0} รายการ", len(w.others) - 8))
        ny += 20
    p.drawText(QRectF(30, ny, W - 60, 18), Qt.AlignLeft,
               tr("หมายเหตุ: แบบสำหรับการเรียน — งานจริงต้องมีฟิวส์/เบรกเกอร์ และวงจรนิรภัย (E-Stop) ตัดไฟกำลังแยกจาก PLC"))


def render(w: Wiring, title: str = "", scale: float = 1.0) -> QImage:
    s = diagram_size(w)
    img = QImage(int(s.width() * scale), int(s.height() * scale), QImage.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.scale(scale, scale)
    paint(p, w, title)
    p.end()
    return img


def export_png(w: Wiring, path, title: str = "") -> bool:
    return render(w, title, 2.0).save(str(path))


def export_pdf(w: Wiring, path, title: str = "") -> None:
    pdf = QPdfWriter(str(path))
    pdf.setPageSize(QPageSize(QPageSize.A4))
    pdf.setPageOrientation(QPageLayout.Landscape)
    pdf.setResolution(150)
    p = QPainter(pdf)
    s = diagram_size(w)
    page = pdf.pageLayout().paintRectPixels(pdf.resolution())
    k = min(page.width() / s.width(), page.height() / s.height())
    p.scale(k, k)
    paint(p, w, title)
    p.end()


class WiringDialog(QDialog):
    def __init__(self, wiring: Wiring, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("🔌 แบบวงจรต่อสาย PLC"))
        self.resize(1240, 820)
        self.wiring, self.title = wiring, title
        v = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        sc = QScrollArea()
        sc.setWidget(self.lbl)
        sc.setWidgetResizable(True)
        sc.setStyleSheet(f"background:{theme.BG_CANVAS};")
        v.addWidget(sc, 1)
        h = QHBoxLayout()
        self.cb_zoom = QComboBox()
        for z in (75, 100, 125, 150):
            self.cb_zoom.addItem(f"{z}%", z / 100)
        self.cb_zoom.setCurrentIndex(1)
        self.cb_zoom.currentIndexChanged.connect(lambda _i: self.refresh())
        b_png, b_pdf, b_close = QPushButton("🖼 Export PNG"), QPushButton("📄 Export PDF"), QPushButton(tr("ปิด"))
        b_png.clicked.connect(lambda: self._export("png"))
        b_pdf.clicked.connect(lambda: self._export("pdf"))
        b_close.clicked.connect(self.close)
        h.addWidget(QLabel(tr("ซูม")))
        h.addWidget(self.cb_zoom)
        h.addStretch(1)
        for b in (b_png, b_pdf, b_close):
            h.addWidget(b)
        v.addLayout(h)
        self.refresh()

    def refresh(self):
        self.lbl.setPixmap(QPixmap.fromImage(render(self.wiring, self.title, self.cb_zoom.currentData())))

    def _export(self, kind: str, path: str | None = None) -> str | None:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export แบบวงจร"), f"wiring_{self.title or 'panel'}.{kind}",
                                                  "PNG (*.png)" if kind == "png" else "PDF (*.pdf)")
        if not path:
            return None
        if kind == "png":
            export_png(self.wiring, path, self.title)
        else:
            export_pdf(self.wiring, path, self.title)
        return str(Path(path))
