"""สร้างไอคอนโปรแกรม assets/icon.ico (รันครั้งเดียว)."""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen

root = Path(__file__).resolve().parents[1]
app = QGuiApplication(sys.argv)
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setBrush(QColor("#212830"))
p.setPen(QPen(QColor("#1F8FD6"), 10))
p.drawRoundedRect(QRectF(8, 8, 240, 240), 36, 36)
# สัญญาณ timing 0/1
pen = QPen(QColor("#5EE36A"), 14, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
p.setPen(pen)
pts = [(40, 190), (80, 190), (80, 130), (140, 130), (140, 190), (170, 190), (170, 130), (216, 130)]
for a, b in zip(pts, pts[1:]):
    p.drawLine(*a, *b)
p.setPen(QColor("#E6E9EE"))
f = QFont("Segoe UI", 54, QFont.Bold)
p.setFont(f)
p.drawText(QRectF(0, 22, 256, 90), Qt.AlignCenter, "PLC")
p.end()
(root / "assets").mkdir(exist_ok=True)
img.save(str(root / "assets" / "icon.png"))
ok = img.scaled(256, 256).save(str(root / "assets" / "icon.ico"))
print("ico saved" if ok else "ico FAILED")
