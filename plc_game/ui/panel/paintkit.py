"""ชุดฟังก์ชันวาดที่ใช้ร่วมกันเพื่อให้อุปกรณ์บนผังดูเหมือนของจริงขึ้น (R4).

ทุกฟังก์ชันรับ QPainter แล้ววาดทันที — ไม่เปลี่ยนขนาด body_rect ของอุปกรณ์
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

INK = QColor("#0E1218")


def _c(c) -> QColor:
    return QColor(c) if not isinstance(c, QColor) else QColor(c)


def alpha(c, a: int) -> QColor:
    c = _c(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


# ---------------- brushes ----------------
def lin(rect: QRectF, stops, vertical=True) -> QBrush:
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft() if vertical else rect.topRight())
    for k, col in stops:
        g.setColorAt(k, _c(col))
    return QBrush(g)


def metal(rect: QRectF, base="#8E99A8", vertical=True) -> QBrush:
    """gradient โลหะแบบทรงกระบอก: ขอบมืด → แถบสะท้อนแสง → ขอบมืด."""
    b = _c(base)
    return lin(rect, ((0.0, b.darker(170)), (0.22, b.lighter(135)), (0.38, b.lighter(165)),
                      (0.62, b), (1.0, b.darker(190))), vertical)


def chrome_ring(center: QPointF, rad: float) -> QBrush:
    g = QConicalGradient(center, 45)
    for k, col in ((0.0, "#F4F6F9"), (0.18, "#7C8796"), (0.35, "#E1E6ED"), (0.55, "#5E6977"),
                   (0.75, "#DCE2EA"), (0.9, "#7C8796"), (1.0, "#F4F6F9")):
        g.setColorAt(k, QColor(col))
    return QBrush(g)


def ball(center: QPointF, rad: float, color, light=1.0) -> QBrush:
    """ทรงโดม/ทรงกลม: จุดสะท้อนแสงซ้ายบน."""
    c = _c(color)
    g = QRadialGradient(center + QPointF(-rad * 0.35, -rad * 0.4), rad * 1.25)
    g.setColorAt(0.0, c.lighter(int(100 + 70 * light)))
    g.setColorAt(0.45, c)
    g.setColorAt(1.0, c.darker(210))
    return QBrush(g)


# ---------------- shapes ----------------
def shadow(p, r: QRectF, radius=8.0, depth=3.0):
    """เงาฟุ้งใต้ตัวอุปกรณ์ (วาดก่อนตัว)."""
    p.setPen(Qt.NoPen)
    for i, a in ((3, 22), (2, 34), (1, 46)):
        d = depth * i / 3
        p.setBrush(QColor(0, 0, 0, a))
        p.drawRoundedRect(r.translated(0, d).adjusted(-i * 0.6, -i * 0.3, i * 0.6, i * 0.6), radius + i, radius + i)


def plate(p, r: QRectF, radius=8.0, fill="#2C3440", edge="#46505F", screws=False, shade=True):
    """ฝาหน้าอุปกรณ์/กล่องพลาสติก: ไล่สีบนสว่าง-ล่างมืด + ขอบไฮไลต์ + น็อต 4 มุม (เลือกได้)."""
    if shade:
        shadow(p, r, radius)
    f = _c(fill)
    p.setPen(QPen(INK, 1.2))
    p.setBrush(lin(r, ((0.0, f.lighter(128)), (0.5, f), (1.0, f.darker(135)))))
    p.drawRoundedRect(r, radius, radius)
    p.setPen(QPen(alpha(_c(edge).lighter(140), 120), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), max(radius - 1.5, 0), max(radius - 1.5, 0))
    if screws:
        k = 5.5
        for x, y in ((r.left() + k, r.top() + k), (r.right() - k, r.top() + k),
                     (r.left() + k, r.bottom() - k), (r.right() - k, r.bottom() - k)):
            screw(p, x, y, 2.2)


def screw(p, x, y, r=2.6, angle=35.0):
    c = QPointF(x, y)
    p.setPen(QPen(INK, 0.8))
    p.setBrush(ball(c, r, "#A9B3C1", 0.6))
    p.drawEllipse(c, r, r)
    a = math.radians(angle)
    dx, dy = math.cos(a) * r * 0.7, math.sin(a) * r * 0.7
    p.setPen(QPen(QColor("#3B4350"), max(r * 0.35, 0.8)))
    p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))


def bezel(p, c: QPointF, rad: float, ring=3.5):
    """ฝาครอบโครเมียมแบบปุ่ม 22 mm (วงแหวนเงา + ร่องดำด้านใน)."""
    p.setPen(QPen(INK, 1))
    p.setBrush(chrome_ring(c, rad))
    p.drawEllipse(c, rad, rad)
    p.setBrush(QColor("#151A21"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(c, rad - ring, rad - ring)


def glow(p, c: QPointF, rad: float, color, k=1.0):
    """แสงฟุ้งแบบ radial (k = ความสว่าง 0..1)."""
    if k <= 0.02:
        return
    col = _c(color)
    g = QRadialGradient(c, rad)
    g.setColorAt(0.0, alpha(col, 150 * k))
    g.setColorAt(0.45, alpha(col, 70 * k))
    g.setColorAt(1.0, alpha(col, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(c, rad, rad)


def led(p, x, y, on: bool, color="#22C55E", r=3.5):
    c = QPointF(x, y)
    col = _c(color)
    if on:
        glow(p, c, r * 3.2, col, 0.9)
    p.setPen(QPen(INK, 0.8))
    p.setBrush(ball(c, r, col if on else col.darker(330), 1.2 if on else 0.4))
    p.drawEllipse(c, r, r)


def dome(p, c: QPointF, rad: float, color, k: float):
    """เลนส์โดม (หลอดไฟ/ไฟสัญญาณ): k = ความสว่าง."""
    col = _c(color)
    off = col.darker(300)
    mix = QColor(round(off.red() + (col.red() - off.red()) * k), round(off.green() + (col.green() - off.green()) * k),
                 round(off.blue() + (col.blue() - off.blue()) * k))
    glow(p, c, rad * 1.9, col, k)
    p.setPen(QPen(INK, 1))
    p.setBrush(ball(c, rad, mix, 0.5 + k))
    p.drawEllipse(c, rad, rad)
    if k > 0.3:      # ไส้แสงตรงกลาง
        g = QRadialGradient(c, rad * 0.75)
        g.setColorAt(0.0, alpha("#FFFFFF", 170 * k))
        g.setColorAt(1.0, alpha(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, rad * 0.75, rad * 0.75)
    p.setPen(QPen(QColor(255, 255, 255, 120), max(rad * 0.12, 1.2)))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(c.x() - rad * 0.68, c.y() - rad * 0.68, rad * 1.36, rad * 1.36), 95 * 16, 70 * 16)


def cable(p, pts, color="#20252C", width=4.0):
    """สายไฟเส้นโค้ง (ผ่านจุด pts) มีไฮไลต์บางๆ."""
    if len(pts) < 2:
        return
    path = QPainterPath(pts[0])
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        m = (a + b) / 2
        path.quadTo(a, m) if i > 1 else path.lineTo(m)
    path.lineTo(pts[-1])
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(INK, width + 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(QPen(_c(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 40), max(width * 0.3, 1), Qt.SolidLine, Qt.RoundCap))
    p.drawPath(path.translated(-width * 0.18, -width * 0.18))


def nameplate(p, r: QRectF, text: str, sub: str = "", fill="#D9DEE5"):
    """ป้ายรุ่นอะลูมิเนียม."""
    p.setPen(QPen(INK, 0.8))
    p.setBrush(lin(r, ((0, _c(fill).lighter(110)), (1, _c(fill).darker(118)))))
    p.drawRoundedRect(r, 1.5, 1.5)
    p.setPen(QColor("#1C2229"))
    if sub:
        p.setFont(QFont("Segoe UI", 5, QFont.Bold))
        p.drawText(r.adjusted(0, 0, 0, -r.height() / 2), Qt.AlignCenter, text)
        p.setFont(QFont("Segoe UI", 4))
        p.drawText(r.adjusted(0, r.height() / 2, 0, 0), Qt.AlignCenter, sub)
    else:
        p.setFont(QFont("Segoe UI", 5, QFont.Bold))
        p.drawText(r, Qt.AlignCenter, text)


def hex_nut(p, cx, cy, w, h, base="#9AA4B2"):
    """น็อตหกเหลี่ยมมองด้านข้าง (กว้าง w สูง h)."""
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QPen(INK, 0.8))
    p.setBrush(metal(r, base, vertical=False))
    p.drawRect(r)
    p.setPen(QPen(alpha(INK, 140), 0.8))
    for x in (cx - w / 4, cx + w / 4):
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))


def thread(p, r: QRectF, pitch=2.6, base="#A3ADBA"):
    """กระบอกเกลียว (แนวตั้ง)."""
    p.setPen(QPen(INK, 0.8))
    p.setBrush(metal(r, base, vertical=False))
    p.drawRect(r)
    p.setPen(QPen(alpha(INK, 110), 0.7))
    y = r.top() + pitch / 2
    while y < r.bottom():
        p.drawLine(QPointF(r.left(), y + 0.8), QPointF(r.right(), y - 0.8))
        y += pitch


def chip(p, r: QRectF, text: str, color, font: QFont, solid=False):
    """ป้าย address แบบ pill ตามธีม."""
    col = _c(color)
    p.setPen(QPen(alpha(col, 220), 1))
    p.setBrush(alpha(col, 235) if solid else alpha(col, 38))
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    p.setFont(font)
    p.setPen(QColor("#0E1218") if solid else col.lighter(115))
    p.drawText(r, Qt.AlignCenter, text)


def motor_end(p, r: QRectF, angle: float, active: bool, ring=None, alarm=False):
    """มอเตอร์มองจากด้านพัดลม: ขาตั้ง, ตัวถังมีครีบ, กล่องขั้วต่อ, ฝาพัดลมมีตะแกรง, ใบพัดหมุนตามเพลา."""
    c = QPointF(r.center().x(), r.center().y() + r.height() * 0.04)
    R = min(r.width(), r.height()) * 0.40
    # ขาตั้ง
    feet = QPolygonF([QPointF(c.x() - R * 0.95, r.bottom()), QPointF(c.x() + R * 0.95, r.bottom()),
                      QPointF(c.x() + R * 0.55, c.y() + R * 0.6), QPointF(c.x() - R * 0.55, c.y() + R * 0.6)])
    p.setPen(QPen(INK, 1))
    p.setBrush(lin(feet.boundingRect(), ((0, "#4B5666"), (1, "#262D37"))))
    p.drawPolygon(feet)
    # กล่องขั้วต่อ
    tb = QRectF(c.x() - R * 0.42, r.top() + 1, R * 0.84, R * 0.5)
    p.setBrush(lin(tb, ((0, "#5D6878"), (1, "#323A46"))))
    p.drawRoundedRect(tb, 2, 2)
    screw(p, tb.left() + 3, tb.center().y(), 1.6)
    screw(p, tb.right() - 3, tb.center().y(), 1.6)
    # ครีบระบายความร้อน
    body_col = QColor("#3F6E9E") if not alarm else QColor("#8A2B2B")
    p.setPen(QPen(INK, 1))
    for i in range(16):
        a = math.radians(i * 22.5 + 11.25)
        if 0.35 < (math.sin(a) + 1) / 2 < 0.65 and math.cos(a) > 0.9:
            continue
        fin = QPolygonF([QPointF(c.x() + math.cos(a - 0.06) * R * 0.86, c.y() + math.sin(a - 0.06) * R * 0.86),
                         QPointF(c.x() + math.cos(a - 0.04) * R * 1.04, c.y() + math.sin(a - 0.04) * R * 1.04),
                         QPointF(c.x() + math.cos(a + 0.04) * R * 1.04, c.y() + math.sin(a + 0.04) * R * 1.04),
                         QPointF(c.x() + math.cos(a + 0.06) * R * 0.86, c.y() + math.sin(a + 0.06) * R * 0.86)])
        p.setBrush(body_col.darker(130))
        p.drawPolygon(fin)
    p.setBrush(ball(c, R * 0.9, body_col, 0.5))
    p.drawEllipse(c, R * 0.9, R * 0.9)
    if ring is not None:     # วงไฟสถานะรอบตัว
        p.setPen(QPen(_c(ring), 2.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, R * 0.9 + 1.5, R * 0.9 + 1.5)
    # ฝาพัดลม + ใบพัดที่มองทะลุตะแกรง
    fr = R * 0.68
    p.setPen(QPen(INK, 1))
    p.setBrush(QColor("#1A1F26"))
    p.drawEllipse(c, fr, fr)
    p.save()
    p.translate(c)
    p.rotate(angle)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E6E9EE") if active else QColor("#7C8796"))
    for _ in range(6):
        p.rotate(60)
        blade = QPainterPath()
        blade.moveTo(0, -fr * 0.18)
        blade.cubicTo(fr * 0.35, -fr * 0.35, fr * 0.30, -fr * 0.8, fr * 0.06, -fr * 0.92)
        blade.cubicTo(-fr * 0.12, -fr * 0.7, -fr * 0.12, -fr * 0.35, 0, -fr * 0.18)
        p.drawPath(blade)
    p.restore()
    p.setBrush(Qt.NoBrush)
    for k in (0.38, 0.62, 0.86):
        p.setPen(QPen(QColor(150, 160, 175, 150), 1.1))
        p.drawEllipse(c, fr * k, fr * k)
    p.setPen(QPen(QColor(150, 160, 175, 120), 1))
    for i in range(4):
        a = math.radians(i * 45)
        d = QPointF(math.cos(a) * fr, math.sin(a) * fr)
        p.drawLine(c - d, c + d)
    p.setPen(QPen(INK, 1))
    p.setBrush(ball(c, fr * 0.22, "#9AA4B2", 0.7))
    p.drawEllipse(c, fr * 0.22, fr * 0.22)
    return c, R
