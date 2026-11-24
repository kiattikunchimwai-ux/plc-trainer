"""รูปตัวอย่างตอนแชร์ลิงก์ (Facebook / LINE / X) 1200×630 → site/img/og.png

รัน:  .venv\\Scripts\\python.exe tools\\make_og_image.py   (platform ปกติ — offscreen ทำให้อักษรไทยเป็นสี่เหลี่ยม)
สีจาก plc_game/ui/theme.py · ภาพหน้าจอจาก site/img/devices.png
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen)

from plc_game.ui import theme  # noqa: E402

W, H = 1200, 630
SRC = ROOT / "site" / "img" / "devices.png"
OUT = ROOT / "site" / "img" / "og.png"


def font(size: int, bold: bool = False) -> QFont:
    f = QFont(["Segoe UI", "Leelawadee UI", "Tahoma"])
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def main() -> Path:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    img = QImage(W, H, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    p.fillRect(0, 0, W, H, QColor(theme.BG_CANVAS))
    # ตาราง model space
    for step, col in ((20, theme.GRID_MINOR), (100, theme.GRID_MAJOR)):
        p.setPen(QPen(QColor(col), 1))
        for x in range(0, W, step):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, step):
            p.drawLine(0, y, W, y)

    # ภาพหน้าจอ (ครอปส่วนผังอุปกรณ์) ชิดขวา
    shot = QImage(str(SRC))
    crop = shot.copy(60, 230, 1360, 860).scaled(620, 393, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    r = QRectF(W - crop.width() - 40, (H - crop.height()) / 2 + 10, crop.width(), crop.height())
    path = QPainterPath()
    path.addRoundedRect(r, 12, 12)
    p.fillPath(path.translated(0, 14), QColor(0, 0, 0, 110))
    p.save()
    p.setClipPath(path)
    p.drawImage(r, crop)
    p.restore()
    p.setPen(QPen(QColor(theme.BORDER), 2))
    p.drawPath(path)

    # ข้อความซ้าย
    x = 56
    bolt = QPainterPath()
    pts = [(13, 2), (4, 14), (11, 14), (10, 22), (19, 10), (12, 10)]
    bolt.moveTo(x + pts[0][0] * 2.2, 70 + pts[0][1] * 2.2)
    for px, py in pts[1:]:
        bolt.lineTo(x + px * 2.2, 70 + py * 2.2)
    bolt.closeSubpath()
    p.fillPath(bolt, QColor(theme.WARN))
    p.setPen(QColor(theme.TEXT))
    p.setFont(font(46, True))
    p.drawText(x + 52, 112, "PLC Trainer")

    p.setFont(font(38, True))
    p.drawText(QRectF(x, 160, 460, 150), Qt.TextWordWrap, "เกมฝึกเขียน PLC\nตรวจคำตอบให้อัตโนมัติ")
    p.setPen(QColor(theme.TEXT_DIM))
    p.setFont(font(22))
    p.drawText(QRectF(x, 315, 460, 120), Qt.TextWordWrap,
               "ใช้กับ GX Works3 / GX Simulator3\nหรือ PLC จำลองในโปรแกรม\nภาษาไทย / English")

    # ป้ายแบบปุ่มในโปรแกรม
    chips = [("ฟรี", None), ("14 ด่าน", theme.SIGNAL_COLORS["X"]), ("โหมดสอบ", theme.SIGNAL_COLORS["Y"])]
    cx = x
    p.setFont(font(22, True))
    for text, col in chips:
        w = p.fontMetrics().horizontalAdvance(text) + 36
        rr = QRectF(cx, 470, w, 46)
        pp = QPainterPath()
        pp.addRoundedRect(rr, 10, 10)
        if col is None:
            g = QLinearGradient(rr.topLeft(), rr.bottomRight())
            g.setColorAt(0, QColor(theme.ACCENT2))
            g.setColorAt(1, QColor(theme.ACCENT))
            p.fillPath(pp, g)
            p.setPen(QColor("white"))
        else:
            p.fillPath(pp, QColor(theme.BG_PANEL))
            p.setPen(QPen(QColor(col), 2))
            p.drawPath(pp)
            p.setPen(QColor(col))
        p.drawText(rr, Qt.AlignCenter, text)
        cx += w + 12

    p.setPen(QColor(theme.TEXT_DIM))
    p.setFont(font(18))
    p.drawText(x, 580, "kiattikunchimwai-ux.github.io/plc-trainer")
    p.end()
    img.save(str(OUT))
    return OUT


if __name__ == "__main__":
    print(main())
