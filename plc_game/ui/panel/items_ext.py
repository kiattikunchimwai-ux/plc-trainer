"""อุปกรณ์ชุดขยาย: encoder, มอเตอร์กลับทาง, VFD, แกนเลื่อน/ลิฟต์/ประตู, ตัวดันคัดแยก,
Analog (pot, เตาอบ, มาตรวัด), ไฟทาวเวอร์, ป้ายข้อความ, ข้อความ และกรอบโซน."""
from __future__ import annotations

from ...i18n import tr, tr_data

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPainterPathStroker, QPen

from ...panel import physics
from .. import theme
from . import items as base
from . import paintkit as pk
from .items import DIM, TEXT, TEXT_DIM, CylinderItem, DeviceItem, InputItem, _bit, _color

ON_Y = QColor(theme.SIGNAL_COLORS["Y"])
ON_X = QColor(theme.SIGNAL_COLORS["X"])


def _emit_word(item: DeviceItem, prop: str, value: int):
    a = item.addr_of(prop)
    if a:
        item.request_write_word.emit(a, int(value))


def _box(p, r, radius=6, fill="#2B323C", pen=None):
    p.setPen(pen or QPen(DIM, 2))
    p.setBrush(QColor(fill))
    p.drawRoundedRect(r, radius, radius)


def _fan(p, center: QPointF, angle: float, rad: float, color: QColor):
    p.save()
    p.translate(center)
    p.rotate(angle)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    for _ in range(3):
        p.rotate(120)
        path = QPainterPath()
        path.moveTo(0, 0)
        path.cubicTo(rad * 0.25, -rad * 0.4, rad * 0.17, -rad * 0.9, 0, -rad)
        path.cubicTo(-rad * 0.25, -rad * 0.75, -rad * 0.25, -rad * 0.33, 0, 0)
        p.drawPath(path)
    p.restore()


def _sensor_dot(p, x, y, on, name=""):
    p.setPen(QPen(QColor("#10151B"), 1))
    p.setBrush(ON_X if on else QColor("#3A4048"))
    p.drawEllipse(QPointF(x, y), 5, 5)
    if name:
        p.setFont(base.FONT)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(x + 7, y - 7, 40, 14), Qt.AlignLeft | Qt.AlignVCenter, name)


# ======================= Encoder =======================
class EncoderItem(InputItem):
    """ส่งพัลส์ตามการหมุนของมอเตอร์ที่ผูกไว้ · คลิก = ส่งพัลส์เอง 1 ครั้ง."""

    def __init__(self, spec):
        super().__init__(spec)
        self.motor_on = False
        self.phase = 0.0
        self.count = 0

    def _conv(self):
        return self.linked("link_conv") if self.fnum("ppr") > 0 else None

    @property
    def hz(self) -> float:
        conv = self._conv()
        if conv is not None:        # โหมดสเปก: ความเร็วสายพานจริง ÷ เส้นรอบวงล้อ × PPR
            return physics.encoder_hz(conv.speed, self.fnum("wheel_mm", 50), self.fnum("ppr"))
        return max(0.5, min(float(self.prop("pulse_hz", 4) or 4), 10.0))

    def running(self) -> bool:
        conv = self._conv()
        if conv is not None:
            return conv.on and conv.fault != "jammed"
        return self.motor_on

    def state_text(self):
        run = tr("หมุน") if self.running() else tr("หยุด")
        s = tr("{0} · {1:.1f} Hz · พัลส์ {2} · ส่ง {3} · PLC เห็น {4}", run, self.hz, self.count, self.signal(), self.plc_seen)
        if self.running() and self.hz > physics.max_readable_hz():
            s += tr(" · ⚠ เร็วเกิน {0:.0f} Hz — PLC อ่านไม่ทัน (รอบอ่าน 50 ms) ต้องใช้ High-speed counter", physics.max_readable_hz())
        return s

    def apply_snapshot(self, snap):
        super().apply_snapshot(snap)
        self.motor_on = _bit(snap, self.addr_of("addr_motor"))

    def tick(self, dt):
        super().tick(dt)
        if not self.running():
            return
        old = self.phase
        self.phase += dt * self.hz
        self.count += math.ceil(self.phase) - math.ceil(old)      # จำนวนพัลส์จริง (แม้ PLC อ่านไม่ทัน)
        self.set_actuated((self.phase % 1.0) < 0.5)
        self.update()

    def on_press(self, pos):
        self.count += 1
        self.set_actuated(True)

    def on_release(self, pos):
        self.set_actuated(False)

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 8)
        p.save()
        p.translate(0, 4)
        p.rotate(self.phase * 45)
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        p.drawEllipse(QPointF(0, 0), 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C7CED8"))
        for i in range(8):
            p.rotate(45)
            p.drawRect(QRectF(-2.5, -20, 5, 7))
        p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FF6B6B") if self.actuated else QColor("#5A2A2A"))
        p.drawEllipse(QPointF(0, 4), 5, 5)
        self.paint_contact_tag(p)
        self.paint_led(p, r.right() - 8, r.top() + 8)


# ======================= มอเตอร์กลับทางหมุน =======================
class MotorRevItem(base.MotorSim, DeviceItem):
    W, H = 72, 72
    FAULTS = base.JAM

    def __init__(self, spec):
        super().__init__(spec)
        self.fwd = self.rev = False
        self.angle = 0.0
        self.blink = 0.0
        self._msim_init()

    @property
    def short(self) -> bool:
        return self.fwd and self.rev

    def boundingRect(self):
        return super().boundingRect().adjusted(0, -14, 0, 0)

    def state_text(self):
        if self.short:
            return tr("⚠ ลัดวงจร! สั่ง FWD และ REV พร้อมกัน")
        s = tr("หมุนหน้า (FWD)") if self.fwd else tr("หมุนกลับ (REV)") if self.rev else tr("หยุด")
        t = self.motor_text()
        return s + (f" · {t}" if t else "")

    def apply_snapshot(self, snap):
        v = (_bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_rev")))
        if v != (self.fwd, self.rev):
            self.fwd, self.rev = v
            self.update()

    def tick(self, dt):
        direction = 0 if self.short else 1 if self.fwd else -1 if self.rev else 0
        self.motor_step(dt, direction)
        if self.short:
            self.blink += dt
            self.update()
        elif self.speed:
            self.angle = (self.angle + 360 * self.speed * dt) % 360
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        bad = self.short and int(self.blink * 4) % 2 == 0
        col = QColor("#FF5A5A") if self.short else ON_Y if (self.fwd or self.rev) else None
        pk.motor_end(p, r, self.angle, self.speed != 0, ring=col, alarm=bad)
        self.paint_meter(p)
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        for txt, on, x in (("FWD", self.fwd, r.left() + 2), ("REV", self.rev, r.right() - 26)):
            p.setPen(ON_Y if on else TEXT_DIM)
            p.drawText(QRectF(x, r.top(), 24, 12), Qt.AlignCenter, txt)
        if self.short:
            badge = QRectF(-34, -9, 68, 18)
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.setBrush(QColor("#E03131") if bad else QColor("#9C1C1C"))
            p.drawRoundedRect(badge, 4, 4)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignCenter, tr("⚠ ลัดวงจร!"))


# ======================= อินเวอร์เตอร์ =======================
class VfdItem(DeviceItem):
    W, H = 150, 84
    FAULTS = {"trip": tr("อินเวอร์เตอร์ทริป E.OC (กระแสเกิน — หยุดหมุน)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.run = self.rev = False
        self.cmd10 = 0
        self.hz = 0.0          # ความถี่จริง (มีเครื่องหมาย: ลบ = หมุนกลับ)
        self.angle = 0.0
        self.atspeed = False

    def target(self) -> float:
        if not self.run or self.fault == "trip":
            return 0.0
        f = max(0.0, min(self.cmd10 / 10.0, float(self.prop("max_hz", 60) or 60)))
        return -f if self.rev else f

    def state_text(self):
        st = tr("เดิน") if self.run else tr("หยุด")
        rpm = abs(self.hz) / 50.0 * self.fnum("motor_rpm", 1450)
        return (tr("{0} · สั่ง {1:.1f} Hz · จริง {2:.1f} Hz ≈ {3:.0f} rpm · SU={4}", st, self.cmd10 / 10, abs(self.hz), rpm, int(self.atspeed)))

    def apply_snapshot(self, snap):
        self.run = _bit(snap, self.addr_of("address"))
        self.rev = _bit(snap, self.addr_of("addr_rev"))
        a = self.addr_of("addr_freq")
        self.cmd10 = int(snap.get(a, 0) or 0) if a else 0

    def input_signals(self):
        a = self.addr_of("addr_atspeed")
        return [(a, int(self.atspeed), False)] if a else []

    def tick(self, dt):
        tgt = self.target()
        ramp_s = max(float(self.prop("ramp_s", 3) or 3), 0.1)
        slowing = abs(tgt) < abs(self.hz) or tgt * self.hz < 0
        if slowing and self.fnum("decel_s") > 0:
            ramp_s = self.fnum("decel_s")
        rate = 50.0 / ramp_s * dt
        if self.fault == "trip":
            rate = abs(self.hz)         # ทริป = ตัดเอาต์พุตทันที มอเตอร์หมุนฟรีจนหยุด
        if self.hz != tgt:
            self.hz = min(self.hz + rate, tgt) if tgt > self.hz else max(self.hz - rate, tgt)
            self.update()
        if self.hz:
            self.angle = (self.angle + self.hz * 14 * dt) % 360
            self.update()
        at = self.run and abs(tgt) > 0 and abs(self.hz - tgt) < 0.5
        if at != self.atspeed:
            self.atspeed = at
            self.emit_bit("addr_atspeed", int(at))
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 6, "#232A33")
        lcd = QRectF(r.left() + 8, r.top() + 8, 84, 34)
        p.setPen(QPen(QColor("#10151B"), 1))
        p.setBrush(QColor("#0E2A1E"))
        p.drawRoundedRect(lcd, 3, 3)
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        # อินเวอร์เตอร์จริงโชว์รหัสผิดพลาดบนจอเสมอ (แม้โหมดซ่อน) — นักเรียนต้องอ่านจอให้เป็น
        p.setPen(QColor("#FF5A5A") if self.fault == "trip" else QColor("#7CFC9A"))
        p.drawText(lcd.adjusted(0, 0, -4, 0), Qt.AlignRight | Qt.AlignVCenter,
                   "E.OC" if self.fault == "trip" else f"{abs(self.hz):5.1f}")
        p.setFont(base.FONT)
        p.drawText(QRectF(lcd.left() + 3, lcd.top(), 30, 12), Qt.AlignLeft, "Hz")
        for i, (txt, on) in enumerate((("RUN", self.run), ("FWD", self.run and not self.rev),
                                       ("REV", self.run and self.rev), ("SU", self.atspeed))):
            x = r.left() + 14 + i * 22
            p.setPen(Qt.NoPen)
            p.setBrush(ON_Y if on else QColor("#3A4048"))
            p.drawEllipse(QPointF(x, r.bottom() - 26), 4, 4)
            p.setFont(QFont("Segoe UI", 6))
            p.setPen(TEXT_DIM)
            p.drawText(QRectF(x - 11, r.bottom() - 20, 22, 12), Qt.AlignCenter, txt)
        c = QPointF(r.right() - 28, r.top() + 34)
        p.setPen(QPen(ON_Y if self.hz else DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawEllipse(c, 22, 22)
        _fan(p, c, self.angle, 18, ON_Y if self.hz else QColor("#5F6B7A"))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(r.right() - 56, r.bottom() - 16, 56, 12), Qt.AlignCenter, "INVERTER")


# ======================= แกนเลื่อน / ลิฟต์ / ประตู =======================
class AxisItem(DeviceItem):
    SENS = (("addr_p1", 0.0), ("addr_p2", 0.5), ("addr_p3", 1.0))
    TOL = 0.04      # ช่วงที่เซนเซอร์ตำแหน่งเห็น (±4% ของระยะ) — เผื่อ PLC สั่งหยุดช้า 1–3 รอบอ่าน ไม่ให้เลยจุด
    FAULTS = {"jammed": tr("ติดขัด (มอเตอร์ได้ไฟแต่ไม่เคลื่อน)"), "p1_fail": tr("เซนเซอร์ต้นทางเสีย (ส่ง 0 ตลอด)"),
              "p3_fail": tr("เซนเซอร์ปลายทางเสีย (ส่ง 0 ตลอด)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.k = 0.0
        self.fwd = self.rev = False
        self.sens = {p: self._at(k) for p, k in self.SENS}
        self._pos_sent = 0

    @property
    def style(self) -> str:
        s = str(self.prop("style", "slide"))
        return s if s in ("slide", "elevator", "door") else "slide"

    @property
    def W(self):  # noqa: N802
        return {"slide": 240, "elevator": 110, "door": 150}[self.style]

    @property
    def H(self):  # noqa: N802
        return {"slide": 70, "elevator": 200, "door": 170}[self.style]

    def _at(self, k) -> bool:
        return abs(self.k - k) <= self.TOL

    def _sense(self, prop, k) -> bool:
        broken = (prop == "addr_p1" and self.fault == "p1_fail") or (prop == "addr_p3" and self.fault == "p3_fail")
        return self._at(k) and not broken

    def _sync_sensors(self):
        for p, k in self.SENS:
            v = self._sense(p, k)
            if v != self.sens[p]:
                self.sens[p] = v
                self.emit_bit(p, int(v))

    def on_fault_changed(self):
        self._sync_sensors()

    def state_text(self):
        mv = tr("⚠ สั่งสองทางพร้อมกัน") if (self.fwd and self.rev) else tr("เคลื่อนไปปลาย") if self.fwd \
            else tr("เคลื่อนกลับ") if self.rev else tr("หยุด")
        return tr("{0} · ตำแหน่ง {1:.0f}%", mv, self.k * 100)

    def apply_snapshot(self, snap):
        v = (_bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_rev")))
        if v != (self.fwd, self.rev):
            self.fwd, self.rev = v
            self.update()

    def input_signals(self):
        out = [(self.addr_of(p), int(v), False) for p, v in self.sens.items() if self.addr_of(p)]
        a = self.addr_of("addr_pos")
        if a:
            out.append((a, round(self.k * 1000), True))
        return out

    def tick(self, dt):
        if self.fwd == self.rev or self.fault == "jammed":
            return
        step = dt / max(float(self.prop("travel_s", 4) or 4), 0.2)
        old = self.k
        self.k = min(1.0, self.k + step) if self.fwd else max(0.0, self.k - step)
        if self.k == old:
            return
        self._sync_sensors()
        pos = round(self.k * 1000)
        if abs(pos - self._pos_sent) >= 10 or self.k in (0.0, 1.0):
            if pos != self._pos_sent:
                self._pos_sent = pos
                _emit_word(self, "addr_pos", pos)
        self.update()

    def _motor(self, p, x, y):
        on = self.fwd != self.rev
        p.setPen(QPen(ON_Y if on else DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawEllipse(QPointF(x, y), 11, 11)
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(x - 11, y - 11, 22, 22), Qt.AlignCenter, "M")
        if self.fwd and self.rev:
            p.setPen(QColor("#FF5A5A"))
            p.drawText(QRectF(x - 40, y + 10, 80, 12), Qt.AlignCenter, tr("สั่ง 2 ทาง!"))

    def paint_body(self, p):
        r = self.body_rect()
        getattr(self, "_paint_" + self.style)(p, r)

    def _paint_slide(self, p, r):
        _box(p, r, 6, "#1E242C")
        rail = QRectF(r.left() + 30, -4, r.width() - 50, 8)
        p.setPen(QPen(QColor("#6B7686"), 1))
        p.setBrush(QColor("#3B4453"))
        p.drawRect(rail)
        cx = rail.left() + self.k * (rail.width() - 36)
        p.setPen(QPen(QColor("#C7CED8"), 2))
        p.setBrush(QColor("#4A6FA5"))
        p.drawRoundedRect(QRectF(cx, -16, 36, 26), 3, 3)
        self._motor(p, r.left() + 15, 0)
        for prop, k in self.SENS:
            if self.addr_of(prop) or prop != "addr_p2":
                x = rail.left() + 18 + k * (rail.width() - 36)
                _sensor_dot(p, x, r.bottom() - 12, self.sens[prop])

    def _paint_elevator(self, p, r):
        shaft = QRectF(r.left() + 30, r.top() + 26, 54, r.height() - 32)
        _box(p, r, 6, "#1E242C")
        p.setPen(QPen(QColor("#6B7686"), 2))
        p.setBrush(QColor("#151A20"))
        p.drawRect(shaft)
        car_h = 38
        cy = shaft.bottom() - car_h - self.k * (shaft.height() - car_h)
        p.setPen(QPen(QColor("#9AA4B2"), 1, Qt.DashLine))
        p.drawLine(QPointF(shaft.center().x(), shaft.top()), QPointF(shaft.center().x(), cy))
        car = QRectF(shaft.left() + 5, cy, shaft.width() - 10, car_h)
        p.setPen(QPen(QColor("#C7CED8"), 2))
        p.setBrush(QColor("#4A6FA5"))
        p.drawRect(car)
        p.setPen(QPen(QColor("#C7CED8"), 1))
        p.drawLine(QPointF(car.center().x(), car.top() + 4), QPointF(car.center().x(), car.bottom() - 2))
        self._motor(p, shaft.center().x(), r.top() + 13)
        for i, (prop, k) in enumerate(self.SENS):
            y = shaft.bottom() - car_h / 2 - k * (shaft.height() - car_h)
            p.setFont(base.FONT)
            p.setPen(TEXT_DIM)
            p.drawText(QRectF(r.left() + 2, y - 7, 26, 14), Qt.AlignCenter, tr("ชั้น{0}", i + 1))
            if self.addr_of(prop) or prop != "addr_p2":
                _sensor_dot(p, shaft.right() + 10, y, self.sens[prop])

    def _paint_door(self, p, r):
        _box(p, r, 4, "#1E242C")
        frame = QRectF(r.left() + 12, r.top() + 26, r.width() - 40, r.height() - 32)
        p.setPen(QPen(QColor("#6B7686"), 3))
        p.setBrush(QColor("#10151B"))
        p.drawRect(frame)
        dh = frame.height() * (1 - self.k * 0.9)
        door = QRectF(frame.left() + 2, frame.top() + 2, frame.width() - 4, max(dh - 4, 4))
        p.setPen(QPen(QColor("#9AA4B2"), 1))
        p.setBrush(QColor("#5F6B7A"))
        p.drawRect(door)
        y = door.top() + 10
        while y < door.bottom():
            p.drawLine(QPointF(door.left(), y), QPointF(door.right(), y))
            y += 10
        self._motor(p, frame.center().x(), r.top() + 13)
        for prop, name, y in (("addr_p3", tr("เปิด"), frame.top() + 8), ("addr_p2", tr("กลาง"), frame.center().y()),
                              ("addr_p1", tr("ปิด"), frame.bottom() - 8)):
            if self.addr_of(prop) or prop != "addr_p2":
                _sensor_dot(p, frame.right() + 10, y, self.sens[prop])


# ======================= กระบอกดันคัดแยก =======================
class PusherItem(CylinderItem):
    """กระบอกสูบแนวตั้งวางเหนือสายพาน ยื่นลงแล้วดันชิ้นงานที่อยู่ใต้ลงถาด."""
    W, H = 90, 110
    STROKE = 40

    def __init__(self, spec):
        super().__init__(spec)
        self.bin_count = 0

    def plate_y(self) -> float:
        return -2 + self.pos_k * self.STROKE

    def rod_scene_rect(self) -> QRectF:
        return self.mapRectToScene(QRectF(-16, -2, 32, self.plate_y() + 8))

    def state_text(self):
        return super().state_text() + tr(" · ในถาด {0} ชิ้น", self.bin_count)

    def on_press(self, pos):
        if QRectF(18, 6, 28, 34).contains(pos):
            self.bin_count = 0     # คลิกถาด = เทถาด
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        on_c = ON_Y
        barrel = QRectF(-12, r.top() + 2, 24, 48)
        p.setPen(QPen(QColor("#C7CED8"), 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRect(barrel)
        py = barrel.top() + 3 + self.pos_k * (barrel.height() - 12)
        p.setBrush(QColor("#9AA4B2"))
        p.drawRect(QRectF(-10, py, 20, 6))
        p.setBrush(QColor("#E6E9EE"))
        p.drawRect(QRectF(-3, py + 6, 6, self.plate_y() - py - 6))
        p.drawRoundedRect(QRectF(-16, self.plate_y(), 32, 6), 2, 2)
        # โซลินอยด์
        sol = QRectF(r.left() + 4, r.top() + 4, 26, 16)
        p.setPen(QPen(on_c if self.sol_a else QColor("#9AA4B2"), 1.5))
        p.setBrush(on_c.darker(200) if self.sol_a else QColor("#1E242C"))
        p.drawRect(sol)
        p.setFont(QFont("Segoe UI", 6, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(sol, Qt.AlignCenter, "SOL")
        # รีดสวิตช์
        for k, y, name in (("addr_ret", barrel.top() + 8, "a0"), ("addr_ext", barrel.bottom() - 8, "a1")):
            _sensor_dot(p, barrel.right() + 7, y, self.reed[k], name)
        # ถาดคัดแยก
        tray = QRectF(18, 6, 28, 34)
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        path = QPainterPath(tray.topLeft())
        path.lineTo(tray.left() + 4, tray.bottom())
        path.lineTo(tray.right() - 4, tray.bottom())
        path.lineTo(tray.topRight())
        p.drawPath(path)
        p.setFont(base.FONT_B)
        p.setPen(QColor("#FFE066"))
        p.drawText(tray, Qt.AlignCenter, str(self.bin_count))
        p.setFont(QFont("Segoe UI", 6))
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(tray.left() - 4, tray.bottom(), tray.width() + 8, 10), Qt.AlignCenter, tr("ถาด"))


# ======================= Analog: Potentiometer =======================
class PotItem(DeviceItem):
    W, H = 84, 84
    SPAN = 135.0

    def __init__(self, spec):
        super().__init__(spec)
        self.value = int(self.prop("value", 0) or 0)
        self.plc_value = None
        self._drag = False

    @property
    def vmax(self) -> int:
        return max(1, int(self.prop("max", 4000) or 4000))

    def state_text(self):
        seen = "-" if self.plc_value is None else self.plc_value
        return tr("ตั้งไว้ {0} ({1}%) · PLC เห็น {2}", self.value, self.value * 100 // self.vmax, seen)

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.value, True)] if a else []

    def apply_snapshot(self, snap):
        a = self.addr_of("address")
        v = snap.get(a) if a else None
        if v != self.plc_value:
            self.plc_value = v
            self.update()

    def set_value(self, v: int):
        v = max(0, min(self.vmax, int(v)))
        if v != self.value:
            self.value = v
            self.spec.props["value"] = v
            _emit_word(self, "address", v)
            self.update()

    def _from_pos(self, pos: QPointF):
        ang = math.degrees(math.atan2(pos.x(), -(pos.y() + 6)))
        ang = max(-self.SPAN, min(self.SPAN, ang))
        step = max(1, self.vmax // 400)
        self.set_value(round((ang + self.SPAN) / (2 * self.SPAN) * self.vmax / step) * step)

    def on_press(self, pos):
        self._drag = True
        self._from_pos(pos)

    def on_release(self, pos):
        self._drag = False

    def mouseMoveEvent(self, e):
        if self.run_mode() and self._drag:
            self._from_pos(e.pos())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 8)
        c = QPointF(0, -6)
        p.setPen(QPen(QColor("#6B7686"), 1))
        for i in range(11):
            a = math.radians(-self.SPAN + i * 2 * self.SPAN / 10)
            p.drawLine(QPointF(c.x() + 27 * math.sin(a), c.y() - 27 * math.cos(a)),
                       QPointF(c.x() + 31 * math.sin(a), c.y() - 31 * math.cos(a)))
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        p.drawEllipse(c, 23, 23)
        ang = -self.SPAN + 2 * self.SPAN * self.value / self.vmax
        a = math.radians(ang)
        p.setPen(QPen(QColor(theme.ACCENT), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(c, QPointF(c.x() + 19 * math.sin(a), c.y() - 19 * math.cos(a)))
        p.setFont(QFont("Consolas", 9, QFont.Bold))
        synced = self.plc_value == self.value
        p.setPen(QColor("#F2D648") if synced else TEXT)
        p.drawText(QRectF(r.left(), r.bottom() - 18, r.width(), 16), Qt.AlignCenter, str(self.value))


# ======================= Analog: เตาอบ =======================
class OvenItem(DeviceItem):
    W, H = 130, 110
    FAULTS = {"heater_open": tr("ฮีตเตอร์ขาด (ได้ไฟแต่ไม่ร้อน)"), "tc_open": tr("เทอร์โมคัปเปิลขาด (ส่งค่า 0)")}

    def reading(self) -> int:
        """ค่าที่เทอร์โมคัปเปิลส่งให้ PLC."""
        return 0 if self.fault == "tc_open" else round(self.temp)

    def on_fault_changed(self):
        self._sent = self.reading()

    def __init__(self, spec):
        super().__init__(spec)
        self.temp = float(self.prop("ambient", 25) or 25)
        self.heater = False
        self.thermo = self.temp >= float(self.prop("thermo_c", 100) or 100)
        self._sent = round(self.temp)

    def state_text(self):
        return tr("{0:.1f} °C · ฮีตเตอร์ {1}", self.temp, 'ON' if self.heater else 'OFF')

    def input_signals(self):
        out = []
        a = self.addr_of("addr_temp")
        if a:
            out.append((a, self.reading(), True))
        b = self.addr_of("addr_thermo")
        if b:
            out.append((b, int(self.thermo), False))
        return out

    def apply_snapshot(self, snap):
        v = _bit(snap, self.addr_of("address"))
        if v != self.heater:
            self.heater = v
            self.update()

    def tick(self, dt):
        amb = float(self.prop("ambient", 25) or 25)
        heating = self.heater and self.fault != "heater_open"
        target = float(self.prop("heat_c", 250) or 250) if heating else amb
        tau = max(float(self.prop("tau_s", 20) or 20), 0.5)
        old = self.temp
        self.temp += (target - self.temp) * min(dt / tau, 1.0)
        if abs(self.temp - old) < 1e-4:
            return
        t = self.reading()
        if t != self._sent:
            self._sent = t
            _emit_word(self, "addr_temp", t)
        th = self.temp >= float(self.prop("thermo_c", 100) or 100)
        if th != self.thermo:
            self.thermo = th
            self.emit_bit("addr_thermo", int(th))
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 6, "#2B323C")
        cav = QRectF(r.left() + 8, r.top() + 8, r.width() - 40, r.height() - 30)
        hot = min(max((self.temp - 25) / 225, 0.0), 1.0)
        p.setPen(QPen(QColor("#6B7686"), 2))
        p.setBrush(QColor(40 + int(90 * hot), 30, 30))
        p.drawRect(cav)
        coil = QPainterPath(QPointF(cav.left() + 6, cav.bottom() - 8))
        n = 8
        for i in range(1, n + 1):
            coil.lineTo(cav.left() + 6 + i * (cav.width() - 12) / n, cav.bottom() - (14 if i % 2 else 8))
        glow = self.heater and self.fault != "heater_open"
        p.setPen(QPen(QColor("#FF6B3D") if glow else QColor("#6B4A40"), 3 if glow else 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(coil)
        # เทอร์โมมิเตอร์
        tx = r.right() - 18
        tube = QRectF(tx - 4, r.top() + 8, 8, r.height() - 36)
        p.setPen(QPen(QColor("#9AA4B2"), 1))
        p.setBrush(QColor("#10151B"))
        p.drawRoundedRect(tube, 4, 4)
        fill = tube.height() * min(max(self.temp / max(float(self.prop("heat_c", 250) or 250), 1), 0), 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FF5A5A"))
        p.drawRoundedRect(QRectF(tube.left() + 1, tube.bottom() - fill, 6, fill), 3, 3)
        p.drawEllipse(QPointF(tx, tube.bottom() + 4), 6, 6)
        p.setFont(QFont("Consolas", 10, QFont.Bold))
        p.setPen(QColor("#FFA94D"))
        p.drawText(QRectF(r.left(), r.bottom() - 20, r.width() - 24, 18), Qt.AlignCenter, f"{self.temp:.0f} °C")
        if self.addr_of("addr_thermo"):
            _sensor_dot(p, r.right() - 8, r.bottom() - 10, self.thermo)


# ======================= Analog: มาตรวัด =======================
class GaugeItem(DeviceItem):
    W, H = 130, 96

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0

    def state_text(self):
        return f"{self.value} {self.prop('unit', '')}"

    def apply_snapshot(self, snap):
        v = int(snap.get(self.addr, 0) or 0)
        if v != self.value:
            self.value = v
            self.update()

    def frac(self) -> float:
        lo, hi = float(self.prop("min", 0) or 0), float(self.prop("max", 100) or 100)
        return 0.0 if hi <= lo else max(0.0, min(1.0, (self.value - lo) / (hi - lo)))

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 6, "#1B2027")
        unit = tr_data(str(self.prop("unit", "")))
        k = self.frac()
        if str(self.prop("style", "needle")) == "bar":
            bar = QRectF(r.left() + 12, r.top() + 22, r.width() - 24, 26)
            p.setPen(QPen(QColor("#6B7686"), 1))
            p.setBrush(QColor("#10151B"))
            p.drawRect(bar)
            col = QColor("#5EE36A") if k < 0.7 else QColor("#F2D648") if k < 0.9 else QColor("#FF5A5A")
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRect(QRectF(bar.left() + 1, bar.top() + 1, (bar.width() - 2) * k, bar.height() - 2))
            p.setPen(QPen(QColor("#6B7686"), 1))
            for i in range(11):
                x = bar.left() + i * bar.width() / 10
                p.drawLine(QPointF(x, bar.bottom()), QPointF(x, bar.bottom() + (6 if i % 5 == 0 else 3)))
        else:
            c = QPointF(0, r.top() + 62)
            rad = 46
            p.setPen(QPen(QColor("#3B4453"), 6))
            p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), 0, 180 * 16)
            p.setPen(QPen(QColor("#FF5A5A"), 6))
            p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), 0, 18 * 16)
            p.setPen(QPen(QColor("#9AA4B2"), 1))
            for i in range(11):
                a = math.radians(180 - i * 18)
                p.drawLine(QPointF(c.x() + (rad - 10) * math.cos(a), c.y() - (rad - 10) * math.sin(a)),
                           QPointF(c.x() + (rad - 4) * math.cos(a), c.y() - (rad - 4) * math.sin(a)))
            a = math.radians(180 - k * 180)
            p.setPen(QPen(QColor("#FFA94D"), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(c, QPointF(c.x() + (rad - 8) * math.cos(a), c.y() - (rad - 8) * math.sin(a)))
            p.setBrush(QColor("#C7CED8"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(c, 4, 4)
        p.setFont(QFont("Consolas", 10, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(r.left(), r.bottom() - 20, r.width(), 18), Qt.AlignCenter, f"{self.value} {unit}")


# ======================= ไฟทาวเวอร์ =======================
class TowerItem(DeviceItem):
    W, H = 46, 140
    LIGHTS = (("address", "#FF5A5A"), ("addr_yellow", "#F2D648"), ("addr_green", "#5EE36A"))

    def __init__(self, spec):
        super().__init__(spec)
        self.lights = [False, False, False]
        self.buzz = False
        self.phase = 0.0

    def state_text(self):
        names = (tr("แดง"), tr("เหลือง"), tr("เขียว"))
        on = [n for n, v in zip(names, self.lights) if v] + ([tr("ออด")] if self.buzz else [])
        return tr("ติด: ") + (", ".join(on) if on else "-")

    def apply_snapshot(self, snap):
        v = [_bit(snap, self.addr_of(prop)) for prop, _ in self.LIGHTS]
        b = _bit(snap, self.addr_of("addr_buzzer"))
        if v != self.lights or b != self.buzz:
            self.lights, self.buzz = v, b
            self.update()

    def tick(self, dt):
        if self.buzz:
            self.phase += dt * 6
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        cap = QRectF(-14, r.top() + 2, 28, 16)
        p.setPen(QPen(QColor("#10151B"), 1))
        p.setBrush(QColor("#3B4453"))
        p.drawRoundedRect(cap, 6, 6)
        if self.buzz:
            k = (math.sin(self.phase) + 1) / 2
            col = QColor("#F2D648")
            col.setAlpha(int(90 + 160 * k))
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            for rad in (18, 24):
                p.drawArc(QRectF(-rad, cap.center().y() - rad, 2 * rad, 2 * rad), 30 * 16, 120 * 16)
        for i, ((_, col), on) in enumerate(zip(self.LIGHTS, self.lights)):
            c = QColor(col)
            seg = QRectF(-15, r.top() + 20 + i * 30, 30, 28)
            if on:
                g = QColor(c)
                g.setAlpha(70)
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawRoundedRect(seg.adjusted(-6, -3, 6, 3), 8, 8)
            p.setPen(QPen(c.darker(220), 1.5))
            p.setBrush(c if on else c.darker(340))
            p.drawRoundedRect(seg, 4, 4)
            if on:
                p.setPen(QPen(QColor(255, 255, 255, 120), 2))
                p.drawLine(QPointF(seg.left() + 6, seg.top() + 5), QPointF(seg.left() + 6, seg.bottom() - 5))
        p.setPen(QPen(QColor("#6B7686"), 4))
        p.drawLine(QPointF(0, r.top() + 112), QPointF(0, r.bottom() - 6))
        p.setPen(QPen(QColor("#6B7686"), 2))
        p.setBrush(QColor("#3B4453"))
        p.drawRect(QRectF(-16, r.bottom() - 6, 32, 6))


# ======================= ป้ายข้อความ =======================
def parse_messages(text: str) -> dict[int, str]:
    out = {}
    for part in str(text or "").replace("\n", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                out[int(k.strip())] = v.strip()
            except ValueError:
                pass
    return out


class MessageItem(DeviceItem):
    W, H = 230, 50

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0

    def text(self) -> str:
        msg = parse_messages(self.prop("messages", "")).get(self.value)
        return tr_data(msg) if msg else tr("(ไม่มีข้อความของค่า {0})", self.value)

    def state_text(self):
        return f"{self.addr} = {self.value} → {self.text()}"

    def boundingRect(self):
        r = self.body_rect()
        return QRectF(r.left() - 2, r.top() - 4, r.width() + 4, r.height() + base.cap_h())

    def apply_snapshot(self, snap):
        v = int(snap.get(self.addr, 0) or 0)
        if v != self.value:
            self.value = v
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 4, "#2B323C")
        lcd = r.adjusted(6, 6, -6, -6)
        p.setPen(QPen(QColor("#10151B"), 1))
        p.setBrush(QColor("#0E2A1E"))
        p.drawRect(lcd)
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.setPen(QColor("#7CFC9A"))
        p.drawText(lcd, Qt.AlignCenter, self.text())


# ======================= ข้อความ / กรอบ (ไม่มี I/O) =======================
class NoteItem(DeviceItem):
    Z = 2

    def _font(self) -> QFont:
        return QFont("Segoe UI", max(6, round(float(self.prop("size", 10) or 10) * base.SCALE)))

    def _text_rect(self) -> QRectF:
        w = float(self.prop("width", 260) or 260) * base.SCALE
        fm = QFontMetricsF(self._font())
        br = fm.boundingRect(QRectF(0, 0, w, 10000), Qt.TextWordWrap, tr_data(str(self.prop("text", ""))) or " ")
        return QRectF(-w / 2, -br.height() / 2, w, br.height())

    def body_rect(self):
        return self._text_rect().adjusted(-6, -4, 6, 4)

    def boundingRect(self):
        return self.body_rect().adjusted(-2, -2, 2, 2)

    def paint_body(self, p):
        if not self.run_mode():
            p.setPen(QPen(QColor(theme.TEXT_DIM), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.body_rect())
        p.setFont(self._font())
        p.setPen(_color(self.prop("color", "white"), "#F1F3F5"))
        p.drawText(self._text_rect(), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, tr_data(str(self.prop("text", ""))))

    def paint_caption(self, p):
        pass


class ZoneItem(DeviceItem):
    Z = -1

    @property
    def W(self):  # noqa: N802
        return max(40.0, float(self.prop("w", 360) or 360))

    @property
    def H(self):  # noqa: N802
        return max(40.0, float(self.prop("h", 240) or 240))

    def _title_rect(self) -> QRectF:
        r = self.body_rect()
        return QRectF(r.left(), r.top() - 22 * base.SCALE, max(120.0, r.width() * 0.6), 20 * base.SCALE)

    def boundingRect(self):
        return self.body_rect().united(self._title_rect()).adjusted(-3, -3, 3, 3)

    def shape(self):
        """คลิกได้เฉพาะขอบและหัวกรอบ — อุปกรณ์ข้างในยังคลิก/ลากได้ตามปกติ."""
        path = QPainterPath()
        path.addRect(self.body_rect())
        st = QPainterPathStroker()
        st.setWidth(12)
        out = st.createStroke(path)
        out.addRect(self._title_rect())
        return out

    def paint_body(self, p):
        r = self.body_rect()
        c = _color(self.prop("color", "blue"), "#4FA3FF")
        fill = QColor(c)
        fill.setAlpha(14)
        p.setPen(QPen(c, 1.5, Qt.DashLine))
        p.setBrush(fill)
        p.drawRect(r)
        p.setFont(base.FONT_B)
        p.setPen(c)
        p.drawText(self._title_rect(), Qt.AlignLeft | Qt.AlignVCenter, self.shown_label)

    def paint_caption(self, p):
        pass


CLASSES = {
    "encoder": EncoderItem, "motor_rev": MotorRevItem, "vfd": VfdItem, "axis": AxisItem,
    "pusher": PusherItem, "pot": PotItem, "oven": OvenItem, "gauge": GaugeItem, "tower": TowerItem,
    "message": MessageItem, "note": NoteItem, "zone": ZoneItem,
}
