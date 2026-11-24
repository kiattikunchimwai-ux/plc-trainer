"""R3: อุปกรณ์ชุดใหม่ที่ทำงานเหมือนของจริง — สวิตช์ 3 ตำแหน่ง, ไทเมอร์รีเลย์, ลูกลอย, ปั๊มลม, สวิตช์ความดัน,
เซนเซอร์ระดับ 4–20 mA, ตาชั่ง, เซอร์โว, สวิตช์ประตู safety, ม่านแสง, แขนหยิบ-วาง, เครื่องอ่านบาร์โค้ด."""
from __future__ import annotations

from ...i18n import tr

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen, QPolygonF

from .. import theme
from . import items as base
from .items import DIM, TEXT, TEXT_DIM, DeviceItem, InputItem, OutputItem, WorkpieceItem, _bit
from .items_ext import ON_X, ON_Y, _box, _emit_word, _sensor_dot

ORANGE = QColor("#FFA94D")


def _led(p, x, y, on, color: QColor, r=4):
    if on:
        g = QColor(color)
        g.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(x, y), r + 3, r + 3)
    p.setPen(QPen(QColor("#10151B"), 1))
    p.setBrush(color if on else QColor("#2A313B"))
    p.drawEllipse(QPointF(x, y), r, r)


def _lcd(p, rect, text, color="#7CFC9A", size=11):
    p.setPen(QPen(QColor("#10151B"), 1))
    p.setBrush(QColor("#0E2A1E"))
    p.drawRoundedRect(rect, 3, 3)
    p.setFont(QFont("Consolas", size, QFont.Bold))
    p.setPen(QColor(color))
    p.drawText(rect.adjusted(2, 0, -4, 0), Qt.AlignRight | Qt.AlignVCenter, text)


def _parts(item) -> list:
    s = item.scene()
    return [i for i in s.items() if isinstance(i, WorkpieceItem)] if s else []


class _CaptionAbove:
    """ป้ายชื่ออยู่ด้านบน (ด้านล่างเป็นลำแสง/พื้นที่ตรวจจับ)."""

    def paint_caption(self, p):
        r = self.body_rect()
        p.save()
        p.translate(0, -r.height() - base.cap_h())
        DeviceItem.paint_caption(self, p)
        p.restore()


# ======================= สวิตช์ 3 ตำแหน่ง =======================
class Selector3Item(InputItem):
    W, H = 72, 72
    PROPS = ("address", "addr_right")

    def __init__(self, spec):
        super().__init__(spec)
        self.position = 0           # -1 ซ้าย, 0 กลาง, 1 ขวา

    def names(self) -> list[str]:
        n = [s.strip() for s in str(self.sprop("pos_names") or "").split(";")]
        return (n + [tr("ซ้าย"), tr("กลาง"), tr("ขวา")][len(n):])[:3]

    def signal_of(self, prop) -> int:
        if prop == "address" and self.fault == "stuck_on":
            return 1
        if prop == "address" and self.fault == "wire_break":
            return 0
        on = self.position == (-1 if prop == "address" else 1)
        return int(on) ^ int(self.nc)

    def signal(self) -> int:
        return self.signal_of("address")

    def input_signals(self):
        return [(self.addr_of(p), self.signal_of(p), False) for p in self.PROPS if self.addr_of(p)]

    def state_text(self):
        n = self.names()[self.position + 1]
        return tr("ตำแหน่ง {0} → ซ้าย {1} / ขวา {2}", n, self.signal_of('address'), self.signal_of('addr_right'))

    def set_position(self, pos: int):
        pos = max(-1, min(1, pos))
        if pos == self.position:
            return
        old = {p: self.signal_of(p) for p in self.PROPS}
        self.position = pos
        self.actuated = pos != 0
        for p in self.PROPS:
            v = self.signal_of(p)
            if v != old[p]:
                self.emit_bit(p, v)
        self.update()

    def on_press(self, pos):
        x = pos.x() if pos is not None else 0.0
        if x < -8:
            self.set_position(self.position - 1)
        elif x > 8:
            self.set_position(self.position + 1)
        else:                                  # คีย์ลัด/คลิกกลาง = วน ซ้าย→กลาง→ขวา
            self.set_position({-1: 0, 0: 1, 1: -1}[self.position])

    def on_release(self, pos):
        pass

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 8)
        names = self.names()
        p.setFont(QFont("Segoe UI", 6, QFont.Bold))
        for i, (n, ang) in enumerate(zip(names, (-45, 0, 45))):
            a = math.radians(ang - 90)
            c = QPointF(30 * math.cos(a), 6 + 30 * math.sin(a))
            p.setPen(QColor(theme.ACCENT2) if self.position == i - 1 else TEXT_DIM)
            p.drawText(QRectF(c.x() - 18, c.y() - 6, 36, 12), Qt.AlignCenter, n)
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        p.drawEllipse(QPointF(0, 8), 20, 20)
        p.save()
        p.translate(0, 8)
        p.rotate(self.position * 45)
        p.setPen(Qt.NoPen)
        if str(self.sprop("keyed")) == "key":
            p.setBrush(QColor("#D4B44A"))
            p.drawRoundedRect(QRectF(-3, -16, 6, 24), 2, 2)
            p.drawEllipse(QPointF(0, -16), 7, 7)
        else:
            p.setBrush(QColor("#E6E9EE"))
            p.drawRoundedRect(QRectF(-5, -18, 10, 36), 4, 4)
            p.setBrush(QColor(theme.ACCENT))
            p.drawEllipse(QPointF(0, -12), 3, 3)
        p.restore()
        self.paint_led(p, r.right() - 8, r.top() + 8)


# ======================= ไทเมอร์รีเลย์ =======================
class TimerRelayItem(OutputItem):
    W, H = 64, 92
    FAULTS = {"stuck": tr("หน้าสัมผัสเชื่อมติด (ON ค้าง)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.t = 0.0
        self.contact = False

    @property
    def set_s(self) -> float:
        return max(self.fnum("set_s", 3.0), 0.05)

    def input_signals(self):
        a = self.addr_of("addr_contact")
        return [(a, int(self.contact), False)] if a else []

    def state_text(self):
        mode = {"on": "ON-delay", "off": "OFF-delay", "flicker": "Flicker"}.get(str(self.sprop("mode")), "")
        return (tr("{0} {1:.1f} s · คอยล์ {2} · นับ {3:.1f} s · หน้าสัมผัส {4}", mode, self.set_s, 'ON' if self.on else 'OFF', self.t, int(self.contact)))

    def tick(self, dt):
        mode, set_s = str(self.sprop("mode")), self.set_s
        if mode == "off":
            if self.on:
                self.t, c = 0.0, True
            elif self.contact:
                self.t += dt
                c = self.t < set_s - 1e-9
            else:
                c = False
        elif mode == "flicker":
            if self.on:
                self.t += dt
                c = int(self.t / set_s + 1e-9) % 2 == 0
            else:
                self.t, c = 0.0, False
        else:
            if self.on:
                self.t = min(self.t + dt, set_s)
                c = self.t >= set_s - 1e-9
            else:
                self.t, c = 0.0, False
        if self.fault == "stuck":
            c = True
        if c != self.contact:
            self.contact = c
            self.emit_bit("addr_contact", int(c))
        if self.on or self.t:
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 4, "#D9DDE3", QPen(QColor("#8A94A3"), 1.5))
        p.setFont(QFont("Segoe UI", 6, QFont.Bold))
        p.setPen(QColor("#2B323C"))
        p.drawText(QRectF(r.left(), r.top() + 2, r.width(), 10), Qt.AlignCenter, "A1   A2")
        p.drawText(QRectF(r.left(), r.bottom() - 12, r.width(), 10), Qt.AlignCenter, "15   18")
        c = QPointF(0, r.top() + 36)
        p.setPen(QPen(QColor("#5F6B7A"), 1))
        p.setBrush(QColor("#F5F6F8"))
        p.drawEllipse(c, 17, 17)
        k = min(self.t / self.set_s, 1.0) if str(self.sprop("mode")) == "on" else (self.t % self.set_s) / self.set_s
        p.setPen(QPen(ORANGE, 3))
        p.drawArc(QRectF(c.x() - 14, c.y() - 14, 28, 28), 90 * 16, int(-360 * 16 * k))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(QColor("#1E242C"))
        p.drawText(QRectF(c.x() - 16, c.y() - 7, 32, 14), Qt.AlignCenter, f"{self.set_s:g}s")
        _led(p, -14, r.bottom() - 24, self.on, QColor("#5EE36A"), 3.5)
        _led(p, 14, r.bottom() - 24, self.contact, ORANGE, 3.5)
        p.setFont(QFont("Segoe UI", 5))
        p.setPen(QColor("#2B323C"))
        p.drawText(QRectF(-24, r.bottom() - 20, 20, 8), Qt.AlignCenter, "PWR")
        p.drawText(QRectF(4, r.bottom() - 20, 20, 8), Qt.AlignCenter, "OUT")
        mode = {"on": "ON-D", "off": "OFF-D", "flicker": "FLK"}.get(str(self.sprop("mode")), "")
        p.drawText(QRectF(r.left(), r.top() + 56, r.width(), 8), Qt.AlignCenter, mode)


# ======================= ลูกลอย =======================
class FloatSwitchItem(InputItem):
    W, H = 46, 70

    def tank(self):
        return self.linked("link_tank")

    def state_text(self):
        t = self.tank()
        where = tr(" · ถัง {0} ระดับ {1:.0f}% (ตั้ง {2:.0f}%)", t.shown_label, t.level, self.fnum('level_pct', 50)) if t else tr(" · ไม่ได้ผูกถัง")
        return super().state_text() + where

    def tick(self, dt):
        super().tick(dt)
        t = self.tank()
        if t is not None:
            lv, set_ = t.level, self.fnum("level_pct", 50)
            self.set_actuated(lv >= set_ if str(self.sprop("float_dir")) != "down" else lv < set_)

    def on_press(self, pos):
        if self.tank() is None:
            super().on_press(pos)
        else:
            self.flash()          # ผูกถังแล้ว: ทำงานตามระดับน้ำจริง

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRoundedRect(QRectF(-14, r.top(), 28, 14), 3, 3)
        up = self.actuated if str(self.sprop("float_dir")) != "down" else not self.actuated
        p.setPen(QPen(QColor("#5F6B7A"), 2))
        p.drawLine(QPointF(0, r.top() + 14), QPointF(0, r.bottom() - 20))
        fy = r.top() + 30 if up else r.bottom() - 14
        p.setPen(QPen(QColor("#10151B"), 1))
        p.setBrush(QColor("#F2D648") if up else QColor("#C7A83A"))
        p.drawEllipse(QPointF(0, fy), 11, 9)
        p.setPen(QPen(QColor(79, 163, 255, 160), 2, Qt.DashLine))
        p.drawLine(QPointF(-20, fy + 4), QPointF(20, fy + 4))
        self.paint_led(p, r.right() - 6, r.top() + 6)


# ======================= ปั๊มลม =======================
class CompressorItem(OutputItem):
    W, H = 132, 92
    FAULTS = {"motor_fail": tr("มอเตอร์ปั๊มลมเสีย (ไม่อัดลม)"), "leak": tr("ท่อลมรั่ว (ความดันลดเร็ว)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.bar = self.fnum("bar0")
        self.relief = False
        self.angle = 0.0
        self._word = None

    def consume(self, liters: float):
        """อุปกรณ์ที่ใช้ลม (กระบอกสูบ) ดึงลมอิสระ liters ลิตร → ความดันในถังลดลง."""
        self.bar = max(0.0, self.bar - liters / max(self.fnum("tank_l", 10), 0.1))

    def word(self) -> int:
        return int(round(self.bar * 10))

    def input_signals(self):
        a = self.addr_of("addr_bar")
        return [(a, self.word(), True)] if a else []

    def state_text(self):
        return (tr("มอเตอร์ {0} · ความดัน {1:.1f} bar", 'ON' if self.on else 'OFF', self.bar)
                + (tr(" · วาล์วนิรภัยระบาย!") if self.relief else ""))

    def tick(self, dt):
        tank = max(self.fnum("tank_l", 10), 0.1)
        mx = self.fnum("max_bar", 8.0)
        if self.on and self.fault != "motor_fail":
            self.bar += self.fnum("lpm", 200) / 60.0 / tank * dt * max(0.2, 1 - 0.5 * self.bar / mx)
            self.angle = (self.angle + 900 * dt) % 360
        leak = self.fnum("leak_bar_min", 0.3) / 60.0 + (0.6 if self.fault == "leak" else 0.0)
        self.bar = max(0.0, self.bar - leak * dt)
        self.relief = self.bar > mx
        if self.relief:
            self.bar = mx
        w = self.word()
        if w != self._word:
            self._word = w
            _emit_word(self, "addr_bar", w)
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        tank = QRectF(r.left() + 4, r.top() + 34, r.width() - 8, 46)
        p.setPen(QPen(QColor("#7A1F1F"), 2))
        p.setBrush(QColor("#C92A2A"))
        p.drawRoundedRect(tank, 22, 22)
        p.setPen(QPen(QColor(255, 255, 255, 60), 3))
        p.drawLine(QPointF(tank.left() + 20, tank.top() + 8), QPointF(tank.right() - 20, tank.top() + 8))
        for x in (tank.left() + 18, tank.right() - 18):
            p.setPen(QPen(QColor("#3A4048"), 3))
            p.drawLine(QPointF(x, tank.bottom()), QPointF(x, r.bottom()))
        # มอเตอร์ + พัดลม
        mc = QPointF(r.left() + 30, r.top() + 18)
        p.setPen(QPen(ON_Y if self.on else DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawEllipse(mc, 16, 16)
        from .items_ext import _fan
        _fan(p, mc, self.angle, 13, ON_Y if self.on else QColor("#5F6B7A"))
        # เกจวัดความดัน
        gc = QPointF(r.right() - 30, r.top() + 18)
        p.setPen(QPen(QColor("#C7CED8"), 2))
        p.setBrush(QColor("#F5F6F8"))
        p.drawEllipse(gc, 17, 17)
        mx = max(self.fnum("max_bar", 8.0), 1)
        p.setPen(QPen(QColor("#E03131"), 2))
        p.drawArc(QRectF(gc.x() - 14, gc.y() - 14, 28, 28), -45 * 16, 45 * 16)
        ang = math.radians(225 - 270 * min(self.bar / (mx * 1.25), 1))
        p.setPen(QPen(QColor("#1E242C"), 2))
        p.drawLine(gc, QPointF(gc.x() + 13 * math.cos(ang), gc.y() - 13 * math.sin(ang)))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(QColor("white"))
        p.drawText(tank, Qt.AlignCenter, f"{self.bar:.1f} bar")
        if self.relief:
            p.setPen(QColor("#74C0FC"))
            p.drawText(QRectF(r.right() - 60, r.top() - 4, 60, 12), Qt.AlignRight, tr("ฟู่ว~"))


# ======================= สวิตช์ความดัน =======================
class PressureSwitchItem(InputItem):
    W, H = 56, 66

    def comp(self):
        c = self.linked("link_air")
        return c if isinstance(c, CompressorItem) else None

    def state_text(self):
        c = self.comp()
        s, d = self.fnum("set_bar", 6), self.fnum("diff_bar", 1)
        return super().state_text() + (tr(" · ความดัน {0:.1f} bar", c.bar) if c else "") + \
            f" · ON ≥ {s:.1f} / OFF ≤ {s - d:.1f} bar"

    def tick(self, dt):
        super().tick(dt)
        c = self.comp()
        if c is None:
            return
        s, d = self.fnum("set_bar", 6), self.fnum("diff_bar", 1)
        if not self.actuated and c.bar >= s:
            self.set_actuated(True)
        elif self.actuated and c.bar <= s - d:
            self.set_actuated(False)

    def on_press(self, pos):
        if self.comp() is None:
            super().on_press(pos)
        else:
            self.flash()

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(QColor("#5F6B7A"), 2))
        p.setBrush(QColor("#9AA4B2"))
        p.drawRect(QRectF(-5, r.bottom() - 14, 10, 14))
        c = QPointF(0, r.top() + 24)
        p.setPen(QPen(QColor("#1C4E80"), 2))
        p.setBrush(QColor("#2F6FB2"))
        p.drawEllipse(c, 22, 22)
        p.setBrush(QColor("#F5F6F8"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 16, 16)
        cmp = self.comp()
        bar = cmp.bar if cmp else (self.fnum("set_bar", 6) if self.actuated else 0)
        ang = math.radians(225 - 270 * min(bar / 10.0, 1))
        sang = math.radians(225 - 270 * min(self.fnum("set_bar", 6) / 10.0, 1))
        p.setPen(QPen(ORANGE, 2))
        p.drawLine(c, QPointF(c.x() + 14 * math.cos(sang), c.y() - 14 * math.sin(sang)))
        p.setPen(QPen(QColor("#1E242C"), 2))
        p.drawLine(c, QPointF(c.x() + 13 * math.cos(ang), c.y() - 13 * math.sin(ang)))
        self.paint_contact_tag(p)
        self.paint_led(p, r.right() - 6, r.top() + 6)


# ======================= เซนเซอร์ระดับ 4–20 mA =======================
class LevelTxItem(DeviceItem):
    W, H = 84, 58
    FAULTS = {"lost_echo": tr("สัญญาณสะท้อนหาย (ค่าเป็น 0)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0

    def tank(self):
        return self.linked("link_tank")

    def compute(self) -> int:
        t = self.tank()
        if t is None or self.fault == "lost_echo":
            return 0
        lo, hi = self.fnum("min_pct", 0), self.fnum("max_pct", 100)
        k = (t.level - lo) / max(hi - lo, 1e-6)
        return int(round(max(0.0, min(1.0, k)) * self.fnum("raw_max", 4000)))

    def ma(self) -> float:
        return 4 + 16 * self.value / max(self.fnum("raw_max", 4000), 1)

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.value, True)] if a else []

    def state_text(self):
        return tr("ค่า {0} ({1:.1f} mA)", self.value, self.ma()) + ("" if self.tank() else tr(" · ไม่ได้ผูกถัง"))

    def tick(self, dt):
        v = self.compute()
        if v != self.value:
            self.value = v
            _emit_word(self, "address", v)
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, QRectF(r.left(), r.top(), r.width(), 34), 6, "#E6E9EE", QPen(QColor("#8A94A3"), 1.5))
        _lcd(p, QRectF(r.left() + 6, r.top() + 5, r.width() - 12, 24), str(self.value))
        p.setPen(QPen(QColor("#5F6B7A"), 2))
        p.setBrush(QColor("#3A4048"))
        p.drawRect(QRectF(-12, r.top() + 34, 24, 10))
        for i, rad in enumerate((8, 14, 20)):
            p.setPen(QPen(QColor(116, 192, 252, 200 - i * 50), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(-rad, r.top() + 44 - rad, 2 * rad, 2 * rad), 225 * 16, 90 * 16)


# ======================= ตาชั่ง =======================
class LoadCellItem(DeviceItem):
    W, H = 112, 104
    FAULTS = {"drift": tr("ตาชั่งไม่ตั้งศูนย์ (ค่าเพี้ยน +150 g)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.grams = 0.0
        self.value = 0
        self.fill = False
        self._noise = 0.0
        self._nt = 0.0

    def apply_snapshot(self, snap):
        self.fill = _bit(snap, self.addr_of("addr_fill"))

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.value, True)] if a else []

    def state_text(self):
        return tr("{0} g · วาล์วเติม {1} (คลิก = เทออก)", self.value, 'เปิด' if self.fill else 'ปิด')

    def tick(self, dt):
        if self.fill:
            self.grams = min(self.fnum("cap_g", 5000), self.grams + self.fnum("fill_gps", 200) * dt)
        self._nt += dt
        if self._nt >= 0.2:
            self._nt = 0.0
            n = self.fnum("noise_g", 2)
            self._noise = random.uniform(-n, n) if n > 0 else 0.0
        v = int(round(self.grams + self._noise + (150 if self.fault == "drift" else 0)))
        if v != self.value:
            self.value = v
            _emit_word(self, "address", v)
            self.update()

    def on_press(self, pos):
        self.grams = 0.0
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        # ถังพัก + ของในถัง
        hop = QRectF(-30, r.top() + 2, 60, 46)
        k = min(self.grams / max(self.fnum("cap_g", 5000), 1), 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C08A4A"))
        p.drawRect(QRectF(hop.left() + 2, hop.bottom() - hop.height() * k, hop.width() - 4, hop.height() * k))
        p.setPen(QPen(QColor("#C7CED8"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(hop)
        if self.fill:
            p.setPen(QPen(QColor("#C08A4A"), 3, Qt.DotLine))
            p.drawLine(QPointF(0, r.top() - 8), QPointF(0, hop.top() + 8))
        # แท่นชั่ง
        p.setPen(QPen(QColor("#5F6B7A"), 2))
        p.setBrush(QColor("#9AA4B2"))
        p.drawRect(QRectF(-44, hop.bottom() + 2, 88, 8))
        _box(p, QRectF(r.left() + 6, hop.bottom() + 14, r.width() - 12, 30), 4, "#2B323C")
        _lcd(p, QRectF(r.left() + 12, hop.bottom() + 18, r.width() - 24, 22), f"{self.value} g")


# ======================= เซอร์โว =======================
class ServoItem(DeviceItem):
    W, H = 300, 76
    FAULTS = {"encoder_err": tr("เอนโค้ดเดอร์ของมอเตอร์ผิดพลาด → Alarm")}

    def __init__(self, spec):
        super().__init__(spec)
        self.pos = 0.0
        self.v = 0.0
        self.son = False
        self.target = 0
        self.alarm = ""
        self.inpos = False
        self._word = None

    @property
    def stroke(self) -> float:
        return max(self.fnum("stroke_mm", 500), 1.0)

    def apply_snapshot(self, snap):
        self.son = _bit(snap, self.addr_of("address"))
        a = self.addr_of("addr_target")
        self.target = int(snap.get(a, 0) or 0) if a else 0

    def input_signals(self):
        out = []
        for prop, v in (("addr_inpos", self.inpos), ("addr_alarm", bool(self.alarm))):
            if self.addr_of(prop):
                out.append((self.addr_of(prop), int(v), False))
        if self.addr_of("addr_pos"):
            out.append((self.addr_of("addr_pos"), int(round(self.pos)), True))
        return out

    def state_text(self):
        st = tr("Servo {0} · ตำแหน่ง {1:.1f} mm → เป้า {2} mm · INP={3}", 'ON' if self.son else 'OFF', self.pos, self.target, int(self.inpos))
        return st + (f" · ⚠ ALARM: {self.alarm}" if self.alarm else "")

    def tick(self, dt):
        if not self.son:
            self.alarm = ""            # ปิด Servo ON = รีเซ็ต Alarm
            self.v = 0.0
        else:
            if self.fault == "encoder_err":
                self.alarm = tr("AL.16 เอนโค้ดเดอร์ผิดพลาด")
            elif not self.alarm and not (0 <= self.target <= self.stroke):
                self.alarm = tr("AL.OT เป้าหมาย {0} mm เกินระยะ 0–{1:.0f}", self.target, self.stroke)
            if self.alarm:
                self.v = 0.0
            else:
                d = self.target - self.pos
                vmax, acc = self.fnum("vmax", 250), max(self.fnum("acc", 500), 1)
                vdes = math.copysign(min(vmax, math.sqrt(2 * acc * abs(d))), d) if abs(d) > 1e-6 else 0.0
                self.v = min(vdes, self.v + acc * dt) if self.v < vdes else max(vdes, self.v - acc * dt)
                new = self.pos + self.v * dt
                if (self.target - new) * d <= 0:          # ผ่านเป้า = หยุดที่เป้าพอดี
                    new, self.v = float(self.target), 0.0
                self.pos = max(0.0, min(self.stroke, new))
        inp = self.son and not self.alarm and abs(self.target - self.pos) <= self.fnum("inpos_mm", 1.0)
        if inp != self.inpos:
            self.inpos = inp
            self.emit_bit("addr_inpos", int(inp))
        al = bool(self.alarm)
        if al != getattr(self, "_al", False):
            self._al = al
            self.emit_bit("addr_alarm", int(al))
        w = int(round(self.pos))
        if w != self._word:
            self._word = w
            _emit_word(self, "addr_pos", w)
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        rail = QRectF(r.left() + 46, -8, r.width() - 52, 20)
        p.setPen(QPen(QColor("#8A94A3"), 1.5))
        p.setBrush(QColor("#C7CED8"))
        p.drawRoundedRect(rail, 3, 3)
        p.setPen(QPen(QColor("#5F6B7A"), 1))
        for i in range(11):
            x = rail.left() + 10 + (rail.width() - 20) * i / 10
            p.drawLine(QPointF(x, rail.bottom()), QPointF(x, rail.bottom() + (6 if i % 5 == 0 else 3)))
        # มอเตอร์เซอร์โว
        m = QRectF(r.left() + 4, -16, 42, 36)
        p.setPen(QPen(ON_Y if self.son else DIM, 2))
        p.setBrush(QColor("#1E242C"))
        p.drawRoundedRect(m, 4, 4)
        p.setFont(QFont("Segoe UI", 6, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(m, Qt.AlignCenter, "SERVO")
        # แคร่
        x = rail.left() + 10 + (rail.width() - 20) * self.pos / self.stroke
        car = QRectF(x - 16, -18, 32, 30)
        p.setPen(QPen(QColor("#10151B"), 1.5))
        p.setBrush(QColor(theme.ACCENT) if not self.alarm else QColor(theme.DANGER))
        p.drawRoundedRect(car, 4, 4)
        tx = rail.left() + 10 + (rail.width() - 20) * max(0, min(self.target, self.stroke)) / self.stroke
        p.setPen(QPen(ORANGE, 1.5, Qt.DashLine))
        p.drawLine(QPointF(tx, -24), QPointF(tx, rail.bottom() + 8))
        _lcd(p, QRectF(r.left() + 4, r.bottom() - 18, 70, 16), f"{self.pos:6.1f}", size=9)
        _led(p, r.left() + 86, r.bottom() - 10, self.inpos, QColor("#5EE36A"), 3.5)
        _led(p, r.left() + 120, r.bottom() - 10, bool(self.alarm), QColor(theme.DANGER), 3.5)
        p.setFont(QFont("Segoe UI", 6))
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(r.left() + 92, r.bottom() - 16, 24, 12), Qt.AlignLeft, "INP")
        p.drawText(QRectF(r.left() + 126, r.bottom() - 16, 24, 12), Qt.AlignLeft, "ALM")
        if self.alarm:
            p.setPen(QColor(theme.DANGER))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.drawText(QRectF(r.left() + 150, r.bottom() - 17, r.width() - 150, 14), Qt.AlignLeft,
                       self.alarm.split(" ")[0])


# ======================= สวิตช์ประตู safety =======================
class SafetyDoorItem(InputItem):
    W, H = 92, 80
    FAULTS = {"ch1_weld": tr("ช่อง 1 เชื่อมติด (ส่งเหมือนประตูปิดตลอด)"),
              "ch2_weld": tr("ช่อง 2 เชื่อมติด (ส่งเหมือนประตูปิดตลอด)"),
              "wire_break": tr("สายช่อง 1 ขาด (ส่ง 0)")}

    def signal_of(self, prop) -> int:
        if prop == "address" and self.fault == "wire_break":
            return 0
        if self.fault == ("ch1_weld" if prop == "address" else "ch2_weld"):
            return int(self.nc)                     # ค่าเหมือนประตูปิด
        return int(self.actuated) ^ int(self.nc)

    def signal(self) -> int:
        return self.signal_of("address")

    def input_signals(self):
        return [(self.addr_of(p), self.signal_of(p), False) for p in ("address", "addr_ch2") if self.addr_of(p)]

    def set_actuated(self, v):
        if v != self.actuated:
            super().set_actuated(v)
            self.emit_bit("addr_ch2", self.signal_of("addr_ch2"))

    def state_text(self):
        s = tr("ประตู{0} · ช่อง 1 = {1}", 'เปิด' if self.actuated else 'ปิด', self.signal_of('address'))
        if self.addr_of("addr_ch2"):
            s += tr(" · ช่อง 2 = {0}", self.signal_of('addr_ch2'))
        return s

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(QColor("#B08900"), 3))
        p.setBrush(QColor("#1B2027"))
        p.drawRect(r.adjusted(2, 2, -2, -2))
        door = QRectF(r.left() + 6, r.top() + 6, r.width() - 26, r.height() - 12)
        if self.actuated:                    # เปิด: แผงประตูหมุนออก (มองเห็นเป็นแผงแคบ)
            door = QRectF(door.left(), door.top(), 14, door.height())
        p.setPen(QPen(QColor("#5F6B7A"), 1.5))
        p.setBrush(QColor("#F2C200"))
        p.drawRect(door)
        p.setPen(QPen(QColor("#1E242C"), 1))
        for i in range(1, 4):
            y = door.top() + door.height() * i / 4
            p.drawLine(QPointF(door.left() + 3, y), QPointF(door.right() - 3, y))
        # ตัวสวิตช์ + ลิ้น
        sw = QRectF(r.right() - 18, -14, 14, 28)
        p.setBrush(QColor("#C92A2A"))
        p.setPen(QPen(QColor("#7A0000"), 1))
        p.drawRoundedRect(sw, 3, 3)
        if not self.actuated:
            p.setBrush(QColor("#C7CED8"))
            p.drawRect(QRectF(door.right(), -4, sw.left() - door.right() + 4, 8))
        if str(self.sprop("lock")) == "lock":
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor("white"))
            p.drawText(sw, Qt.AlignCenter, "🔒")
        self.paint_led(p, r.right() - 8, r.top() + 8)


# ======================= ม่านแสง =======================
class LightCurtainItem(InputItem):
    H = 100
    FAULTS = {"misalign": tr("แนวลำแสงเพี้ยน (ขาดตลอด)"), "ossd_fail": tr("OSSD ค้าง ON — อันตราย! (ส่ง 1 แม้ลำแสงขาด)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.manual = False
        self.part_block = False
        self._out = False
        self._t = 0.0

    @property
    def W(self):  # noqa: N802
        return max(self.fnum("height", 140), 40)

    def zone_scene_rect(self) -> QRectF:
        r = self.body_rect()
        return self.mapRectToScene(QRectF(r.left() + 4, r.top() + 14, r.width() - 8, r.height() - 28))

    def broken_now(self) -> bool:
        return self.manual or self.part_block or self.fault == "misalign"

    def signal(self) -> int:
        if self.fault == "ossd_fail":
            return int(self.nc)
        return int(self.actuated) ^ int(self.nc)

    def state_text(self):
        return tr("ลำแสง{0} → OSSD {1} · PLC เห็น {2}", 'ขาด' if self.actuated else 'ครบ', self.signal(), self.plc_seen)

    def detect_parts(self, parts):
        z = self.zone_scene_rect()
        self.part_block = any(wp.sceneBoundingRect().intersects(z) for wp in parts)

    def tick(self, dt):
        super().tick(dt)
        raw = self.broken_now()
        resp = self.fnum("response_ms", 15) / 1000.0
        if raw != self._out:
            self._t += dt
            if self._t >= resp - 1e-9:
                self._out, self._t = raw, 0.0
        else:
            self._t = 0.0
        self.set_actuated(self._out)

    def on_press(self, pos):
        self.manual = True

    def on_release(self, pos):
        self.manual = False

    def paint_body(self, p):
        r = self.body_rect()
        for y in (r.top(), r.bottom() - 12):
            p.setPen(QPen(QColor("#10151B"), 1))
            p.setBrush(QColor("#F2C200"))
            p.drawRoundedRect(QRectF(r.left(), y, r.width(), 12), 3, 3)
        n = int(self.fnum("beams", 8))
        broken = self.actuated
        for i in range(n):
            x = r.left() + 8 + (r.width() - 16) * i / max(n - 1, 1)
            p.setPen(QPen(QColor(255, 80, 80, 200) if broken else QColor(255, 80, 80, 90), 1.5,
                          Qt.SolidLine if not broken else Qt.DotLine))
            p.drawLine(QPointF(x, r.top() + 12), QPointF(x, r.bottom() - 12))
        _led(p, r.right() - 10, r.top() + 6, not broken, QColor("#5EE36A"), 3.5)
        _led(p, r.right() - 22, r.top() + 6, broken, QColor(theme.DANGER), 3.5)
        if self.manual:
            p.setFont(QFont("Segoe UI", 16))
            p.setPen(TEXT)
            p.drawText(r, Qt.AlignCenter, "✋")


# ======================= แขนหยิบ-วาง =======================
class PickPlaceItem(DeviceItem):
    W, H = 260, 210
    SENS = ("addr_up", "addr_down", "addr_left", "addr_rightlim", "addr_gripped")
    FAULTS = {"grip_fail": tr("ลมหัวจับรั่ว (จับไม่อยู่ ชิ้นงานหล่น)"), "z_stuck": tr("แกน Z ติด (ไม่ลง)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.ax = self.az = 0.0
        self.cmd_down = self.cmd_right = self.cmd_grip = False
        self.grip_t = 0.0
        self.closed = False
        self.held: str | None = None       # วัสดุชิ้นงานที่จับอยู่
        self.held_code = 0
        self.placed = self.dropped = 0
        self.crash_t = 0.0
        self.sens = self._compute_sens()

    # ---------- geometry ----------
    def _xr(self):
        r = self.body_rect()
        return r.left() + 40, r.right() - 40

    def carriage_x(self) -> float:
        a, b = self._xr()
        return a + (b - a) * self.ax

    def tip_y(self) -> float:
        return self.body_rect().top() + 40 + self.az * 104

    def pick_scene_rect(self) -> QRectF:
        a, _ = self._xr()
        return self.mapRectToScene(QRectF(a - 16, self.body_rect().top() + 40 + 104 - 6, 32, 30))

    # ---------- signals ----------
    def _compute_sens(self):
        return {"addr_up": self.az <= 0.02, "addr_down": self.az >= 0.98, "addr_left": self.ax <= 0.02,
                "addr_rightlim": self.ax >= 0.98, "addr_gripped": self.held is not None}

    def input_signals(self):
        return [(self.addr_of(k), int(v), False) for k, v in self.sens.items() if self.addr_of(k)]

    def apply_snapshot(self, snap):
        self.cmd_down = _bit(snap, self.addr_of("address"))
        self.cmd_right = _bit(snap, self.addr_of("addr_right"))
        self.cmd_grip = _bit(snap, self.addr_of("addr_grip"))

    def state_text(self):
        held = {"metal": tr("จับโลหะ"), "plastic": tr("จับพลาสติก")}.get(self.held or "", tr("ว่าง"))
        s = tr("X {0:.0%} · Z {1:.0%} · หัวจับ{2} ({3})", self.ax, self.az, 'หนีบ' if self.closed else 'เปิด', held)
        s += tr(" · วางแล้ว {0} · หล่น {1}", self.placed, self.dropped)
        return s + (tr(" · ⚠ ชน! เลื่อนแกน X ตอนแกน Z ยังไม่ขึ้นสุด") if self.crash_t > 0 else "")

    # ---------- simulation ----------
    def _pick(self):
        if str(self.sprop("feed")) == "conveyor":
            zone = self.pick_scene_rect()
            for wp in _parts(self):
                if wp.sceneBoundingRect().intersects(zone):
                    self.held, self.held_code = wp.material, getattr(wp, "code", 0)
                    wp.conveyor.remove_part(wp)
                    return
        else:
            self.held = random.choice(("metal", "plastic"))
            self.held_code = (100 if self.held == "metal" else 200) + random.randint(0, 99)

    def tick(self, dt):
        zt = 1.0 if (self.cmd_down and self.fault != "z_stuck") else 0.0
        xt = 1.0 if self.cmd_right else 0.0
        if xt != self.ax and self.az > 0.05:
            self.crash_t = 2.0                       # เลื่อน X ขณะ Z ยังลงอยู่ = ชน
        self.crash_t = max(0.0, self.crash_t - dt)
        sz, sx = dt / max(self.fnum("z_s", 0.5), 0.05), dt / max(self.fnum("x_s", 1.0), 0.05)
        self.az = min(zt, self.az + sz) if zt > self.az else max(zt, self.az - sz)
        self.ax = min(xt, self.ax + sx) if xt > self.ax else max(xt, self.ax - sx)
        # หัวจับ
        was = self.closed
        if self.cmd_grip:
            self.grip_t += dt
            self.closed = self.grip_t >= self.fnum("grip_ms", 200) / 1000.0 - 1e-9
        else:
            self.grip_t, self.closed = 0.0, False
        if self.closed and not was and self.held is None and self.az >= 0.95 and self.ax <= 0.02:
            self._pick()
        if was and not self.closed and self.held is not None:
            if self.ax >= 0.98 and self.az >= 0.95:
                self.placed += 1
            else:
                self.dropped += 1
            self.held = None
        if self.held is not None and self.fault == "grip_fail" and self.az < 0.9:
            self.held = None
            self.dropped += 1
        new = self._compute_sens()
        for k, v in new.items():
            if v != self.sens[k]:
                self.sens[k] = v
                self.emit_bit(k, int(v))
        self.update()

    def on_press(self, pos):
        r = self.body_rect()
        if QRectF(r.right() - 64, r.bottom() - 52, 60, 50).contains(pos):
            self.placed = self.dropped = 0           # คลิกถาด = เทถาด
            self.update()

    # ---------- painting ----------
    def paint_body(self, p):
        r = self.body_rect()
        a, b = self._xr()
        on_c = ON_Y
        # เสา + ราง
        p.setPen(QPen(QColor("#5F6B7A"), 2))
        p.setBrush(QColor("#3A4453"))
        p.drawRect(QRectF(r.left() + 4, r.top() + 4, 12, r.height() - 8))
        rail = QRectF(r.left() + 4, r.top() + 4, r.width() - 8, 14)
        p.setBrush(QColor("#C7CED8"))
        p.drawRoundedRect(rail, 3, 3)
        # ถาดป้อน (ซ้าย) / ถาดปลายทาง (ขวา)
        base_y = self.body_rect().top() + 40 + 104
        if str(self.sprop("feed")) != "conveyor":
            for i in range(3):
                look = WorkpieceItem.LOOK["metal" if i % 2 else "plastic"]
                p.setPen(QPen(QColor(look[1]), 1.5))
                p.setBrush(QColor(look[0]))
                p.drawRect(QRectF(a - 13, base_y + 2 + i * 9 - 4, 26, 9))
        tray = QRectF(b - 26, base_y + 2, 52, r.bottom() - base_y - 4)
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        p.drawRect(tray)
        p.setFont(base.FONT_B)
        p.setPen(QColor("#FFE066"))
        p.drawText(tray, Qt.AlignCenter, str(self.placed))
        # แคร่ + ก้าน Z + หัวจับ
        cx = self.carriage_x()
        p.setPen(QPen(on_c if self.cmd_right else QColor("#10151B"), 1.5))
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(QRectF(cx - 16, rail.top() - 2, 32, 22), 3, 3)
        ty = self.tip_y()
        p.setPen(QPen(QColor("#E6E9EE"), 5))
        p.drawLine(QPointF(cx, rail.bottom() + 4), QPointF(cx, ty - 8))
        p.setPen(QPen(on_c if self.cmd_grip else QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRect(QRectF(cx - 14, ty - 10, 28, 8))
        gap = 9 if self.closed else 16
        for s in (-1, 1):
            p.drawRect(QRectF(cx + s * gap - (4 if s > 0 else 0), ty - 2, 4, 16))
        if self.held:
            look = WorkpieceItem.LOOK[self.held]
            p.setPen(QPen(QColor(look[1]), 1.5))
            p.setBrush(QColor(look[0]))
            p.drawRect(QRectF(cx - 8, ty, 16, 16))
        # รีดสวิตช์
        _sensor_dot(p, r.left() + 26, r.top() + 30, self.sens["addr_up"], "Z↑")
        _sensor_dot(p, r.left() + 26, r.top() + 48, self.sens["addr_down"], "Z↓")
        _sensor_dot(p, a, r.top() + 26 - 18, self.sens["addr_left"])
        _sensor_dot(p, b, r.top() + 26 - 18, self.sens["addr_rightlim"])
        if self.dropped:
            p.setFont(base.FONT)
            p.setPen(QColor(theme.WARN))
            p.drawText(QRectF(r.left() + 20, r.bottom() - 16, 120, 14), Qt.AlignLeft, tr("หล่น {0} ชิ้น", self.dropped))
        if self.crash_t > 0:
            badge = QRectF(cx - 30, ty + 18, 60, 18)
            p.setPen(QPen(QColor("white"), 1))
            p.setBrush(QColor(theme.DANGER))
            p.drawRoundedRect(badge, 4, 4)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(badge, Qt.AlignCenter, tr("⚠ ชน!"))


# ======================= เครื่องอ่านบาร์โค้ด =======================
class BarcodeItem(_CaptionAbove, DeviceItem):
    W, H = 64, 44
    FAULTS = {"dirty_label": tr("ฉลากเปื้อน อ่านไม่ได้ (ส่ง −1)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0
        self.ok = False
        self.trig = False
        self.seen = None
        self._seen_id = None
        self._read_t = 0.0
        self._done = False

    @property
    def BEAM(self):  # noqa: N802
        return self.fnum("range_mm", 120)

    def beam_scene_rect(self) -> QRectF:
        return self.mapRectToScene(QRectF(-12, self.H / 2, 24, self.BEAM))

    def boundingRect(self):
        r = self.body_rect()
        return QRectF(-48 * base.SCALE, r.top() - 4 - base.cap_h(), 96 * base.SCALE,
                      r.height() + 4 + base.cap_h() + self.BEAM)

    def apply_snapshot(self, snap):
        self.trig = _bit(snap, self.addr_of("addr_trig"))

    def input_signals(self):
        out = []
        if self.addr_of("address"):
            out.append((self.addr_of("address"), self.value, True))
        if self.addr_of("addr_ok"):
            out.append((self.addr_of("addr_ok"), int(self.ok), False))
        return out

    def state_text(self):
        mode = tr("รอ Trigger") if self.addr_of("addr_trig") else tr("อ่านต่อเนื่อง")
        return tr("{0} · รหัสล่าสุด {1} · OK={2}", mode, self.value, int(self.ok))

    def detect_parts(self, parts):
        beam = self.beam_scene_rect()
        self.seen = next((wp for wp in parts if wp.sceneBoundingRect().intersects(beam)), None)

    def tick(self, dt):
        triggered = self.trig or not self.addr_of("addr_trig")
        if self.seen is not None and id(self.seen) != self._seen_id:
            self._seen_id, self._read_t, self._done = id(self.seen), 0.0, False
        ok = False
        if self.seen is None:
            self._seen_id, self._read_t, self._done = None, 0.0, False
        elif triggered:
            self._read_t += dt
            if not self._done and self._read_t >= self.fnum("read_ms", 100) / 1000.0 - 1e-9:
                self._done = True
                self.value = -1 if self.fault == "dirty_label" else int(getattr(self.seen, "code", 0))
                _emit_word(self, "address", self.value)
            ok = self._done and self.value != -1
        if ok != self.ok:
            self.ok = ok
            self.emit_bit("addr_ok", int(ok))
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        _box(p, r, 6, "#1E242C")
        win = QRectF(-16, r.bottom() - 9, 32, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3A1010") if self.seen is None else QColor("#FF4D4D"))
        p.drawRect(win)
        _led(p, r.left() + 9, r.top() + 9, self.ok, QColor("#5EE36A"), 3.5)
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.setPen(QColor("#7CFC9A") if self.value != -1 else QColor(theme.DANGER))
        p.drawText(QRectF(r.left() + 16, r.top() + 2, r.width() - 20, 16), Qt.AlignRight | Qt.AlignVCenter,
                   "NG" if self.value == -1 else str(self.value))
        triggered = self.trig or not self.addr_of("addr_trig")
        col = QColor(255, 77, 77, 120 if (triggered and self.seen is not None) else 40)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(-6, r.bottom()), QPointF(6, r.bottom()),
                                 QPointF(14, r.bottom() + self.BEAM), QPointF(-14, r.bottom() + self.BEAM)]))


CLASSES = {
    "selector3": Selector3Item, "timer_relay": TimerRelayItem, "float_switch": FloatSwitchItem,
    "compressor": CompressorItem, "pressure_switch": PressureSwitchItem, "level_tx": LevelTxItem,
    "load_cell": LoadCellItem, "servo": ServoItem, "safety_door": SafetyDoorItem,
    "light_curtain": LightCurtainItem, "pick_place": PickPlaceItem, "barcode": BarcodeItem,
}
