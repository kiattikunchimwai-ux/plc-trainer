"""R5: รีเลย์ชุดใหม่ — รีเลย์ควบคุม, Latching/Impulse relay, SSR, รีเลย์ป้องกันเฟส, เซฟตี้รีเลย์.

ทุกตัวทำงานจาก I/O อย่างเดียว (black-box) และมีพฤติกรรมผิดพลาดที่ใช้สอน (FAULTS)
"""
from __future__ import annotations

from ...i18n import tr

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen

from ...panel import physics
from .. import theme
from . import paintkit as pk
from .items import JAM, DeviceItem, MotorSim, OutputItem, _bit
from .items_ext import _emit_word as item_emit_word

ON_Y = QColor(theme.SIGNAL_COLORS["Y"])
ON_X = QColor(theme.SIGNAL_COLORS["X"])
GREEN, RED, AMBER = "#5EE36A", "#FF5A5A", "#FFA94D"
TINY = QFont("Segoe UI", 5, QFont.Bold)
SMALL = QFont("Segoe UI", 6, QFont.Bold)


def _txt(p, rect, text, color="#1C2229", font=SMALL, align=Qt.AlignCenter):
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(rect, align, text)


def _contact_sym(p, x, y, closed: bool, nc: bool, color="#1C2229"):
    """สัญลักษณ์หน้าสัมผัสเล็ก ๆ (แนวตั้ง 16 px): ปิด = เส้นตรง, เปิด = เส้นเอียง."""
    p.setPen(QPen(QColor(color), 1.3))
    p.drawLine(QPointF(x, y), QPointF(x, y + 4))
    p.drawLine(QPointF(x, y + 12), QPointF(x, y + 16))
    if closed:
        p.drawLine(QPointF(x, y + 4), QPointF(x, y + 12))
    else:
        p.drawLine(QPointF(x, y + 4), QPointF(x + 4, y + 11))
    if nc:
        p.drawLine(QPointF(x - 2, y + 12), QPointF(x + 3, y + 12))


class _Contacts:
    """ชุดหน้าสัมผัส addr_c1..addr_cN ที่ส่งค่ากลับเข้า PLC (NO/NC เลือกได้จากสเปก c1..cN)."""
    N_CONTACTS = 4

    def _contacts_init(self):
        self._cv = {i: None for i in range(1, self.N_CONTACTS + 1)}

    def operated(self) -> bool:            # คลาสลูกกำหนด: กลไกหน้าสัมผัสถูกดึง/สลับอยู่ไหม
        return False

    def is_nc(self, i: int) -> bool:
        return str(self.sprop(f"c{i}") or "NO").upper() == "NC"

    def contact_value(self, i: int) -> int:
        return int(self.operated()) ^ int(self.is_nc(i))

    def contact_signals(self):
        out = []
        for i in self._cv:
            a = self.addr_of(f"addr_c{i}")
            if a:
                out.append((a, self.contact_value(i), False))
        return out

    def sync_contacts(self):
        for i in self._cv:
            v = self.contact_value(i)
            if v != self._cv[i]:
                self._cv[i] = v
                self.emit_bit(f"addr_c{i}", v)


# ======================= รีเลย์ควบคุม =======================
class RelayItem(_Contacts, OutputItem):
    W, H = 60, 96
    FAULTS = {"coil_open": tr("คอยล์ขาด (สั่งแล้วไม่ดูด)"),
              "weld": tr("หน้าสัมผัสชุด 1 เชื่อมติด (ส่ง 1 ค้าง)"),
              "burnt": tr("หน้าสัมผัสชุด 1 ไหม้ (ไม่ต่อ ส่ง 0)")}

    def __init__(self, spec):
        super().__init__(spec)
        self._contacts_init()
        self.pulled = False          # อาร์เมเจอร์ถูกดึงแล้ว
        self.manual = False          # คันโยกทดสอบ (ล็อกให้ทำงานด้วยมือ)
        self._t = 0.0

    def coil_powered(self) -> bool:
        return (self.on and self.fault != "coil_open") or self.manual

    def operated(self) -> bool:
        return self.pulled

    def contact_value(self, i: int) -> int:
        if i == 1 and self.fault == "weld":
            return 1
        if i == 1 and self.fault == "burnt":
            return 0
        return super().contact_value(i)

    def input_signals(self):
        return self.contact_signals()

    def _advance(self, dt):
        target = self.coil_powered()
        if target != self.pulled:
            self._t += dt
            delay = self.fnum("pickup_ms" if target else "release_ms") / 1000.0
            if self._t >= delay - 1e-9:
                self.pulled, self._t = target, 0.0
                self.update()
        else:
            self._t = 0.0
        self.sync_contacts()

    def apply_snapshot(self, snap):
        super().apply_snapshot(snap)
        self._advance(0.0)

    def tick(self, dt):
        self._advance(dt)

    def on_fault_changed(self):
        self._advance(0.0)

    def on_press(self, pos):
        self.manual = not self.manual          # คันโยกทดสอบสีส้มบนตัวรีเลย์
        self._advance(0.0)
        self.update()

    def state_text(self):
        cs = " ".join(f"c{i}={self.contact_value(i)}" for i in self._cv if self.addr_of(f"addr_c{i}"))
        s = tr("คอยล์ {0} · {1}", 'ON' if self.on else 'OFF', 'ดูด' if self.pulled else 'ปล่อย')
        if self.manual:
            s += tr(" · 🔧 คันโยกทดสอบล็อกอยู่ (คลิกเพื่อปลด)")
        return s + (f" · {cs}" if cs else "")

    def paint_body(self, p):
        r = self.body_rect()
        # ซ็อกเก็ต (ฐานดำ + ขั้วสกรู)
        base_r = QRectF(r.left(), r.bottom() - 24, r.width(), 24)
        pk.plate(p, base_r, 3, fill="#2A3038", edge="#4A5260")
        for k, x in enumerate((-20, -7, 7, 20)):
            pk.screw(p, x, base_r.top() + 8, 3.2, angle=30)
            _txt(p, QRectF(x - 6, base_r.top() + 13, 12, 8), str(k + 1), "#C7CED8", TINY)
        # ตัวรีเลย์ (กล่องใส)
        cube = QRectF(r.left() + 5, r.top() + 4, r.width() - 10, r.height() - 30)
        p.setPen(QPen(pk.INK, 1.2))
        p.setBrush(pk.lin(cube, ((0, "#E8EEF4"), (1, "#B8C2CE"))))
        p.drawRoundedRect(cube, 4, 4)
        inner = cube.adjusted(4, 12, -4, -4)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(QColor(255, 255, 255, 90))
        p.drawRect(inner)
        # คอยล์ (ขดลวดทองแดง)
        coil = QRectF(inner.left() + 3, inner.top() + 3, 12, inner.height() - 6)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.metal(coil, "#C27A3A", vertical=False))
        p.drawRect(coil)
        if self.coil_powered():
            pk.glow(p, coil.center(), 10, ON_Y, 0.6)
        # หน้าสัมผัส 4 ชุด
        for i in range(1, 5):
            x = inner.left() + 19 + (i - 1) * 6
            used = bool(self.addr_of(f"addr_c{i}"))
            closed = bool(self.contact_value(i)) if used else (self.pulled != self.is_nc(i))
            _contact_sym(p, x, inner.top() + 6, closed, self.is_nc(i), "#1C2229" if used else "#7C8796")
        # LED + คันโยกทดสอบ
        pk.led(p, cube.right() - 6, cube.top() + 6, self.coil_powered(), GREEN, 2.8)
        lever = QRectF(cube.left() + 4, cube.top() + 2, 14, 7)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(QColor("#FF8C1A") if self.manual else QColor("#D9781A").darker(130))
        p.drawRoundedRect(lever.translated(0, 2 if self.manual else 0), 2, 2)
        _txt(p, QRectF(cube.left() + 20, cube.top() + 1, cube.width() - 30, 9),
             "24VDC" if str(self.sprop("coil")) == "24vdc" else "220VAC", "#3B4350", TINY)


# ======================= Latching / Impulse relay =======================
class LatchRelayItem(_Contacts, OutputItem):
    W, H = 60, 88
    N_CONTACTS = 2
    HOT_S = 2.0                      # คอยล์ impulse ห้ามจ่ายไฟค้างนาน
    FAULTS = {"jammed": tr("กลไกล็อกค้าง (สั่งแล้วไม่สลับ)")}

    def __init__(self, spec):
        super().__init__(spec)
        self._contacts_init()
        self.latched = False         # สถานะที่จำไว้ (ไม่หายแม้ PLC หยุด/ตัดการเชื่อมต่อ)
        self.set_cmd = self.rst_cmd = False
        self.sr_conflict = False
        self.coil_t = 0.0

    @property
    def impulse(self) -> bool:
        return str(self.sprop("mode")) != "set_reset"

    def operated(self) -> bool:
        return self.latched

    def input_signals(self):
        return self.contact_signals()

    def _set_state(self, v: bool):
        if self.fault == "jammed":
            return
        if v != self.latched:
            self.latched = v
            self.sync_contacts()
            self.update()

    def apply_snapshot(self, snap):
        s = _bit(snap, self.addr_of("address"))
        r = _bit(snap, self.addr_of("addr_reset"))
        if self.impulse:
            if s and not self.set_cmd:              # ขอบขาขึ้น = สลับสถานะ
                self._set_state(not self.latched)
            self.sr_conflict = False
        else:
            self.sr_conflict = s and r
            if r:                                   # RESET ชนะเสมอ
                self._set_state(False)
            elif s:
                self._set_state(True)
        if (s, r) != (self.set_cmd, self.rst_cmd):
            self.update()
        self.set_cmd, self.rst_cmd = s, r
        self.on = s
        self.sync_contacts()

    def tick(self, dt):
        self.coil_t = self.coil_t + dt if (self.impulse and self.set_cmd) else 0.0
        self.sync_contacts()

    def on_press(self, pos):
        self._set_state(not self.latched)           # สลับด้วยมือ (ปุ่มบนตัว)

    def state_text(self):
        mode = tr("Impulse (กดติด-กดดับ)") if self.impulse else "SET/RESET"
        s = tr("{0} · สถานะ {1} (จำไว้แม้ตัดไฟ)", mode, 'ON' if self.latched else 'OFF')
        if self.sr_conflict:
            s += tr(" · ⚠ สั่ง SET และ RESET พร้อมกัน (RESET ชนะ)")
        if self.coil_t > self.HOT_S:
            s += tr(" · ⚠ คอยล์ impulse ได้ไฟค้างนาน — ควรสั่งเป็นพัลส์สั้น ๆ")
        return s

    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 4, fill="#D9DDE3", edge="#F2F4F7")
        _txt(p, QRectF(r.left(), r.top() + 2, r.width(), 9),
             "A1  A2" if self.impulse else "S   R   A2", "#2B323C", TINY)
        # ตัวบอกสถานะแบบกลไก (หน้าต่าง I / O)
        win = QRectF(-14, r.top() + 14, 28, 18)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(QColor("#1A1E24"))
        p.drawRoundedRect(win, 3, 3)
        flag = QRectF(win.left() + (14 if self.latched else 2), win.top() + 2, 12, 14)
        p.setBrush(QColor(GREEN) if self.latched else QColor("#C7CED8"))
        p.drawRoundedRect(flag, 2, 2)
        _txt(p, flag, "I" if self.latched else "O", "#0E1218", SMALL)
        # ไฟคอยล์ SET / RESET
        pk.led(p, -12, r.top() + 42, self.set_cmd, ON_Y, 3)
        _txt(p, QRectF(-24, r.top() + 47, 24, 8), "SET" if not self.impulse else "PULSE", "#2B323C", TINY)
        if not self.impulse:
            pk.led(p, 12, r.top() + 42, self.rst_cmd, RED, 3)
            _txt(p, QRectF(0, r.top() + 47, 24, 8), "RST", "#2B323C", TINY)
        for i in (1, 2):
            used = bool(self.addr_of(f"addr_c{i}"))
            _contact_sym(p, -8 + (i - 1) * 16, r.bottom() - 27, bool(self.contact_value(i)), self.is_nc(i),
                         "#1C2229" if used else "#7C8796")
        _txt(p, QRectF(r.left(), r.bottom() - 10, r.width(), 9), "11-14  21-24", "#2B323C", TINY)
        if self.sr_conflict or self.coil_t > self.HOT_S:
            badge = QRectF(r.left() - 2, r.top() + 2, r.width() + 4, 11)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.DANGER))
            p.drawRoundedRect(badge, 3, 3)
            _txt(p, badge, "⚠ S+R" if self.sr_conflict else tr("⚠ ร้อน"), "white", SMALL)


# ======================= SSR =======================
class SSRItem(OutputItem):
    W, H = 76, 104
    FAULTS = {"short": tr("ไทริสเตอร์ช็อต (โหลดติดค้าง)"), "open": tr("SSR ขาด (สั่งแล้วโหลดไม่ติด)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.conduct = False
        self.duty = 0.0              # ค่าเฉลี่ยการนำกระแส (เห็นผล PWM)
        self.heat = 0.0              # ความร้อนของฮีตเตอร์ 0..1
        self.temp = self.fnum("ambient", 30)
        self.burnt = False           # ร้อนเกินจนพัง (ช็อตค้าง) — คลิกเพื่อเปลี่ยนตัวใหม่
        self._zc = 0.0

    def gate(self) -> bool:
        if self.burnt or self.fault == "short":
            return True
        if self.fault == "open":
            return False
        return self.on

    def leak_glow(self) -> float:
        """กระแสรั่วตอน OFF ทำให้หลอด LED เล็ก ๆ ติดหรี่ ๆ ได้."""
        return 0.12 if (not self.conduct and str(self.sprop("load")) == "lamp" and self.fnum("leak_ma") >= 3) else 0.0

    def tick(self, dt):
        g = self.gate()
        if g != self.conduct:
            # zero-cross: เปลี่ยนสถานะที่จุดตัดศูนย์ถัดไป (เฉลี่ย ¼ ไซเคิล 50 Hz = 5 ms)
            self._zc += dt
            if str(self.sprop("zero_cross")) == "no" or self._zc >= 0.005 - 1e-9:
                self.conduct, self._zc = g, 0.0
        else:
            self._zc = 0.0
        c = 1.0 if self.conduct else 0.0
        self.duty += (c - self.duty) * min(1.0, dt / 0.3)
        self.heat += (c - self.heat) * min(1.0, dt / 3.0)
        self.temp = physics.ssr_heat_step(self.temp, self.fnum("ambient", 30), self.fnum("load_a", 5), c,
                                          str(self.sprop("heatsink")), dt)
        if self.temp >= physics.SSR_FAIL_C and not self.burnt:
            self.burnt = True
        self.update()

    def on_press(self, pos):
        if self.burnt:                                # เปลี่ยน SSR ตัวใหม่
            self.burnt = False
            self.temp = self.fnum("ambient", 30)
            self.update()

    def state_text(self):
        s = (tr("อินพุต {0} · โหลด{1} · duty {2:.0%} · ตัว SSR {3:.0f} °C", 'ON' if self.on else 'OFF', 'ติด' if self.conduct else 'ดับ', self.duty, self.temp))
        if self.burnt:
            s += tr(" · 💥 ร้อนเกินจนพัง (ช็อตค้าง ON) — ต้องมีฮีตซิงก์! คลิกเพื่อเปลี่ยนตัวใหม่")
        elif self.temp >= 80:
            s += tr(" · ⚠ ร้อนมาก")
        if self.leak_glow():
            s += tr(" · หลอดติดหรี่จากกระแสรั่ว")
        return s

    def paint_body(self, p):
        r = self.body_rect()
        # ฮีตซิงก์ (ครีบอะลูมิเนียม) ด้านหลัง
        top = QRectF(r.left(), r.top(), r.width(), 56)
        if str(self.sprop("heatsink")) != "no":
            p.setPen(QPen(pk.INK, 0.8))
            for i in range(9):
                fin = QRectF(top.left() + 2 + i * (top.width() - 4) / 9, top.top(), 5, top.height())
                p.setBrush(pk.metal(fin, "#AEB7C2", vertical=False))
                p.drawRect(fin)
        # ตัว SSR
        body = top.adjusted(9, 6, -9, -6)
        hot = min(max((self.temp - 40) / 70, 0), 1)
        fill = QColor(round(43 + 150 * hot), round(50 - 10 * hot), round(60 - 20 * hot))
        pk.plate(p, body, 3, fill=fill.name(), edge="#6A7480", shade=False)
        _txt(p, QRectF(body.left(), body.top() + 1, body.width(), 9), "SSR 25A", "#E6E9EE", TINY)
        _txt(p, QRectF(body.left(), body.bottom() - 10, body.width(), 9), "3+ 4−   1 ~ 2", "#C7CED8", TINY)
        pk.led(p, body.center().x(), body.center().y(), self.on and not self.burnt, AMBER, 3)
        if self.burnt:
            _txt(p, body, "💥", "white", QFont("Segoe UI", 12))
        # โหลดในตัว
        load = QRectF(-24, r.bottom() - 40, 48, 36)
        if str(self.sprop("load")) == "lamp":
            k = max(self.duty, self.leak_glow())
            pk.dome(p, load.center(), 14, "#FFE066", k)
        else:
            p.setPen(QPen(pk.INK, 1))
            p.setBrush(QColor("#2B323C"))
            p.drawRoundedRect(load, 4, 4)
            col = QColor(round(90 + 165 * self.heat), round(60 + 40 * self.heat), 40)
            p.setPen(QPen(col, 2.2))
            y = load.center().y()
            for i in range(5):
                x = load.left() + 6 + i * 8
                p.drawArc(QRectF(x, y - 6, 8, 12), 0, 180 * 16 if i % 2 == 0 else -180 * 16)
            if self.heat > 0.3:
                pk.glow(p, load.center(), 20, "#FF6A1A", self.heat * 0.7)


# ======================= รีเลย์ป้องกันเฟส =======================
PHASE_CONDS = (("ok", tr("ไฟปกติ")), ("loss", tr("เฟสขาด")), ("rev", tr("สลับเฟส")), ("under", tr("แรงดันต่ำ")), ("over", tr("แรงดันเกิน")))


class PhaseRelayItem(DeviceItem):
    W, H = 64, 92
    FAULTS = {"contact_fail": tr("หน้าสัมผัสเสีย (ส่ง 0 ตลอด — เครื่องเดินไม่ได้)"),
              "no_trip": tr("ไม่ทริป (ไฟผิดปกติแต่ยังส่ง OK — อันตราย!)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.cond = "ok"
        self.ok_out = True           # รีเลย์ภายในดูดอยู่ = ไฟปกติ
        self._t = 0.0
        self._sent = None

    def cond_name(self) -> str:
        return dict(PHASE_CONDS)[self.cond]

    def set_condition(self, cond: str):
        if cond in dict(PHASE_CONDS) and cond != self.cond:
            self.cond = cond
            self._t = 0.0
            self.update()

    def signal(self) -> int:
        return 0 if self.fault == "contact_fail" else int(self.ok_out)

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.signal(), False)] if a else []

    def _sync(self):
        v = self.signal()
        if v != self._sent:
            self._sent = v
            self.emit_bit("address", v)

    def tick(self, dt):
        bad = self.cond != "ok" and self.fault != "no_trip"
        if bad == self.ok_out:                   # สถานะต้องเปลี่ยน → นับเวลาหน่วง
            self._t += dt
            if bad:
                delay = 0.1 if self.cond == "rev" else self.fnum("trip_s", 1.0)
            else:
                delay = self.fnum("reset_s", 1.0)
            if self._t >= delay - 1e-9:
                self.ok_out, self._t = not bad, 0.0
                self.update()
        else:
            self._t = 0.0
        self._sync()

    def on_fault_changed(self):
        self._sync()

    def on_press(self, pos):
        keys = [k for k, _ in PHASE_CONDS]
        self.set_condition(keys[(keys.index(self.cond) + 1) % len(keys)])

    def state_text(self):
        s = tr("ไฟเข้า: {0} → หน้าสัมผัส OK = {1}", self.cond_name(), self.signal())
        if self.cond != "ok" and self.ok_out and self.fault != "no_trip":
            s += tr(" (กำลังนับเวลาทริป {0:.1f} s)", self._t)
        return s + tr(" · คลิก = เปลี่ยนสภาพไฟ")

    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 4, fill="#C9CFD7", edge="#EEF1F4")
        _txt(p, QRectF(r.left(), r.top() + 2, r.width(), 9), "L1  L2  L3", "#2B323C", TINY)
        # เฟส 3 เส้น (เส้นที่ผิดปกติแสดงสีแดง/ขาด)
        for k, x in enumerate((-16, 0, 16)):
            broken = (self.cond == "loss" and k == 2)
            col = QColor(RED) if (self.cond != "ok" and (broken or self.cond in ("under", "over"))) else QColor("#3B4350")
            p.setPen(QPen(col, 2, Qt.DotLine if broken else Qt.SolidLine))
            p.drawLine(QPointF(x, r.top() + 12), QPointF(x, r.top() + 24))
        if self.cond == "rev":
            _txt(p, QRectF(-20, r.top() + 12, 40, 12), "⇄", RED, QFont("Segoe UI", 9, QFont.Bold))
        # LED
        pk.led(p, -14, r.top() + 34, True, GREEN, 3)
        pk.led(p, 14, r.top() + 34, not self.ok_out or self.cond != "ok", RED, 3)
        _txt(p, QRectF(-26, r.top() + 39, 24, 8), "PWR", "#2B323C", TINY)
        _txt(p, QRectF(2, r.top() + 39, 24, 8), "FAULT", "#2B323C", TINY)
        # ปุ่มหมุนตั้งเวลาทริป
        c = QPointF(0, r.top() + 58)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.ball(c, 8, "#3A6EA5", 0.6))
        p.drawEllipse(c, 8, 8)
        _txt(p, QRectF(-30, r.top() + 67, 60, 9), f"t={self.fnum('trip_s', 1.0):g}s", "#2B323C", TINY)
        # ป้ายสภาพไฟ (คลิกเปลี่ยน)
        tag = QRectF(r.left() + 3, r.bottom() - 14, r.width() - 6, 11)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(GREEN) if self.cond == "ok" else QColor(theme.DANGER))
        p.drawRoundedRect(tag, 3, 3)
        _txt(p, tag, self.cond_name(), "#0E1218" if self.cond == "ok" else "white", TINY)


# ======================= เซฟตี้รีเลย์ =======================
class SafetyRelayItem(DeviceItem):
    W, H = 72, 104
    FAULTS = {"weld": tr("ช่อง 2 เชื่อมติด (ไม่เปิดเมื่อกด E-Stop) → ตรวจพบ รีเซ็ตไม่ได้"),
              "wire_break": tr("สายช่อง 1 ขาด (รีเซ็ตไม่ได้)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.out = False             # K1/K2 ดูด = หน้าสัมผัส safety 13-14 ต่อ
        self.discrepancy = False
        self.manual_open = False     # ไม่ได้ผูก E-Stop: คลิกครึ่งบน = จำลองวงจร S11-S12 เปิด
        self.reset_btn = False
        self._rst_prev = False
        self._rst_req = False
        self._sent: dict[str, int] = {}

    # ---------- วงจรนิรภัย ----------
    def source(self):
        return self.linked("link_estop")

    def demand(self) -> bool:
        """มีการสั่งหยุดนิรภัย (กด E-Stop / เปิดประตู / ลำแสงขาด)."""
        s = self.source()
        return bool(getattr(s, "actuated", False)) if s is not None else self.manual_open

    def channels(self) -> tuple[bool, bool]:
        d = self.demand()
        ch1 = not d and self.fault != "wire_break"
        ch2 = (not d) or self.fault == "weld"
        return ch1, ch2

    @property
    def auto_reset(self) -> bool:
        return str(self.sprop("reset_mode")) == "auto"

    def signals(self) -> dict[str, int]:
        return {"address": int(self.out), "addr_aux": int(not self.out)}

    def input_signals(self):
        return [(self.addr_of(k), v, False) for k, v in self.signals().items() if self.addr_of(k)]

    def _sync(self):
        for k, v in self.signals().items():
            if self._sent.get(k) != v:
                self._sent[k] = v
                self.emit_bit(k, v)

    def apply_snapshot(self, snap):
        r = _bit(snap, self.addr_of("addr_reset"))
        if self._rst_prev and not r:                 # monitored reset: รีเซ็ตที่ขอบขาลง
            self._rst_req = True
        self._rst_prev = r

    def tick(self, dt):
        ch1, ch2 = self.channels()
        if ch1 != ch2:
            self.discrepancy = True                  # สองช่องไม่ตรงกัน = มีจุดเสีย
        elif not ch1 and not ch2:
            self.discrepancy = False                 # ต้องเปิดครบทั้งสองช่องจึงล้างได้
        if not (ch1 and ch2):
            self.out = False
        ready = ch1 and ch2 and not self.discrepancy and not self.out
        if ready and (self.auto_reset or self._rst_req):
            self.out = True
        self._rst_req = False
        self._sync()
        self.update()

    def on_fault_changed(self):
        self.tick(0.0)

    def _reset_rect(self) -> QRectF:
        r = self.body_rect()
        return QRectF(-14, r.bottom() - 26, 28, 20)

    def on_press(self, pos):
        if pos is not None and self._reset_rect().adjusted(-4, -4, 4, 4).contains(pos):
            self.reset_btn = True
        elif self.source() is None:
            self.manual_open = not self.manual_open
        self.update()

    def on_release(self, pos):
        if self.reset_btn:
            self.reset_btn = False
            self._rst_req = True                     # ปล่อยปุ่ม = ขอบขาลง
            self.update()

    def state_text(self):
        ch1, ch2 = self.channels()
        s = (tr("ช่อง 1 {0} · ช่อง 2 {1} → เอาต์พุต safety {2}", 'ปิด' if ch1 else 'เปิด', 'ปิด' if ch2 else 'เปิด', 'ON' if self.out else 'OFF'))
        if self.discrepancy:
            s += tr(" · ⚠ สองช่องไม่ตรงกัน (ตรวจพบจุดเสีย) — รีเซ็ตไม่ได้")
        elif ch1 and ch2 and not self.out:
            s += tr(" · รอรีเซ็ต") + ("" if self.auto_reset else tr(" (กดปุ่ม RESET แล้วปล่อย)"))
        if self.source() is None:
            s += tr(" · ไม่ได้ผูก E-Stop: คลิกครึ่งบน = เปิด/ปิดวงจรนิรภัย")
        return s

    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 4, fill="#F2C200", edge="#FFE680")
        _txt(p, QRectF(r.left(), r.top() + 2, r.width(), 9), "A1 S11 S12 S21 S22", "#2B2400", TINY)
        _txt(p, QRectF(r.left(), r.top() + 12, r.width(), 10), "SAFETY", "#2B2400", SMALL)
        ch1, ch2 = self.channels()
        leds = (("PWR", True, GREEN), ("CH1", ch1, GREEN), ("CH2", ch2, GREEN),
                ("OUT", self.out, GREEN))
        for i, (name, on, col) in enumerate(leds):
            y = r.top() + 30 + i * 11
            pk.led(p, r.left() + 10, y, on, col, 2.8)
            _txt(p, QRectF(r.left() + 16, y - 5, 30, 10), name, "#2B2400", TINY, Qt.AlignLeft | Qt.AlignVCenter)
        pk.led(p, r.right() - 10, r.top() + 30, self.discrepancy, RED, 2.8)
        _txt(p, QRectF(r.right() - 34, r.top() + 35, 30, 8), "ERR", "#2B2400", TINY)
        # หน้าสัมผัส 13-14 (เปิด/ปิดตามเอาต์พุต)
        _contact_sym(p, r.right() - 14, r.top() + 48, self.out, False)
        _txt(p, QRectF(r.right() - 34, r.top() + 64, 34, 8), "13-14", "#2B2400", TINY)
        # ปุ่ม RESET สีน้ำเงิน
        rb = self._reset_rect()
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.ball(rb.center(), 10, "#2F6FB2" if not self.reset_btn else "#1C4E80", 0.6))
        p.drawRoundedRect(rb.adjusted(0, 1 if self.reset_btn else 0, 0, 0), 4, 4)
        _txt(p, rb, "RESET", "white", TINY)
        if self.source() is None and self.manual_open:
            _txt(p, QRectF(r.left(), r.top() + 22, r.width(), 10), tr("วงจรเปิด"), theme.DANGER, TINY)


# ======================= มอเตอร์สตาร์-เดลต้า =======================
class MotorYDItem(MotorSim, DeviceItem):
    W, H = 132, 84
    WARN_S = 3.0
    FAULTS = {**JAM, "star_open": tr("คอนแทคเตอร์สตาร์ (KM2) ไม่ต่อ → สตาร์ทไม่ขึ้น")}

    def __init__(self, spec):
        super().__init__(spec)
        self._msim_init()
        self.main = self.star = self.delta = False
        self.mode = "off"
        self.angle = 0.0
        self.shorted = False         # ลัดวงจรแล้ว: มอเตอร์หยุด ต้องตัด KM2 และ KM3 ก่อน
        self.star_t = 0.0
        self.jerk_t = 0.0            # เวลาที่เหลือของป้าย "สลับเร็วเกินไป"
        self.jerk_count = 0
        self.theta = 0.0             # ความร้อนสะสมของ OL ในตัว
        self.ol_tripped = False
        self._sent = None

    # ---------- I/O ----------
    def ol_signal(self) -> int:
        return 0 if self.ol_tripped else 1          # หน้าสัมผัส 95-96 (NC): ปกติ = 1, ทริป = 0

    def input_signals(self):
        a = self.addr_of("addr_ol")
        return [(a, self.ol_signal(), False)] if a else []

    def apply_snapshot(self, snap):
        v = (_bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_star")),
             _bit(snap, self.addr_of("addr_delta")))
        if v != (self.main, self.star, self.delta):
            was_delta = self.mode == "delta"
            self.main, self.star, self.delta = v
            self._update_mode()
            if self.mode == "delta" and not was_delta and abs(self.speed) < physics.YD_SAFE_SWITCH:
                self.jerk_t = self.WARN_S
                self.jerk_count += 1
            self.update()

    def _update_mode(self):
        star = self.star and self.fault != "star_open"
        m = physics.yd_mode(self.main, star, self.delta)
        if m == "short" or (self.star and self.delta):
            self.shorted = True
        elif self.shorted and not self.star and not self.delta:
            self.shorted = False
        if self.ol_tripped:                         # OL ในตัวตัดวงจรคอยล์ทุกตัว
            m = "off"
        self.mode = "short" if self.shorted else m

    # ---------- simulation ----------
    def tick(self, dt):
        self._update_mode()
        jam = self.fault == "jammed"
        target = 0.0 if jam else physics.yd_target(self.mode)
        if jam:
            self.speed = 0.0
        else:
            t = self.fnum("accel_s") if target > self.speed else self.fnum("decel_s")
            self.speed = physics.ramp(self.speed, target, dt, t, t)
        self.current_a = physics.yd_current(self.fnum("fla"), self.mode, self.speed, self.fnum("load_pct", 80), jam)
        self.star_t = self.star_t + dt if self.mode == "star" else 0.0
        self.jerk_t = max(0.0, self.jerk_t - dt)
        fla = self.fnum("fla")
        if fla > 0:
            self.theta = physics.ol_heat_step(self.theta, self.current_a, fla, physics.ol_tau(10), dt)
            if not self.ol_tripped and self.theta >= physics.OL_TRIP_THETA:
                self.ol_tripped = True
        if self.speed:
            self.angle = (self.angle + 360 * dt * self.speed) % 360
        s = self.ol_signal()
        if s != self._sent:
            self._sent = s
            self.emit_bit("addr_ol", s)
        self.update()

    def star_too_long(self) -> bool:
        return self.star_t > self.fnum("star_max_s", 15)

    def on_press(self, pos):
        if self.ol_tripped and self.theta < physics.OL_TRIP_THETA * 0.7:   # กดรีเซ็ต OL (ต้องเย็นก่อน)
            self.ol_tripped = False
            self.update()

    def state_text(self):
        name = {"off": tr("หยุด"), "open": tr("มีแค่ Main — ขดลวดไม่ครบวงจร ไม่หมุน"), "star": tr("ต่อสตาร์ (Y) — เริ่มเดิน"),
                "delta": tr("ต่อเดลต้า (Δ) — รอบเต็ม"), "short": tr("⚠ ลัดวงจร! KM2 (Y) และ KM3 (Δ) ON พร้อมกัน")}
        s = name[self.mode]
        t = self.motor_text()
        if t and self.mode != "short":
            s += f" · {t}"
        if self.shorted and self.mode == "short":
            s += tr(" — ต้องตัดทั้งคู่ก่อน")
        if self.jerk_t > 0:
            s += tr(" · ⚠ สลับเป็นเดลต้าเร็วเกินไป (รอบยังต่ำ กระแสกระชากสูง)")
        if self.star_too_long():
            s += tr(" · ⚠ ค้างสตาร์นานเกิน — แรงบิดต่ำ มอเตอร์ร้อน")
        if self.ol_tripped:
            s += tr(" · OL ทริป! (คลิกมอเตอร์เพื่อรีเซ็ตเมื่อเย็นลง)")
        return s

    # ---------- painting ----------
    def boundingRect(self):
        return super().boundingRect().adjusted(0, -14, 0, 0)

    def paint_meter(self, p):
        p.save()
        p.translate(-30, 0)
        MotorSim.paint_meter(self, p)
        p.restore()

    def paint_body(self, p):
        r = self.body_rect()
        mr = QRectF(r.left(), r.top() + 6, 76, 76)
        bad = self.mode == "short" or self.ol_tripped
        ring = QColor(RED) if bad else ON_Y if self.mode in ("star", "delta") else None
        pk.motor_end(p, mr, self.angle, self.speed != 0, ring=ring, alarm=bad)
        # แผงคอนแทคเตอร์ 3 ตัว
        panel = QRectF(r.left() + 80, r.top() + 2, r.width() - 80, r.height() - 4)
        pk.plate(p, panel, 4, fill="#2A3038", edge="#4A5260")
        star_on = self.star and self.fault != "star_open"
        rows = (("KM1", "M", self.main), ("KM2", "Y", star_on), ("KM3", "Δ", self.delta))
        for i, (km, tag, on) in enumerate(rows):
            y = panel.top() + 6 + i * 19
            cell = QRectF(panel.left() + 4, y, panel.width() - 8, 16)
            p.setPen(QPen(pk.INK, 0.8))
            p.setBrush(QColor("#3B4350") if not on else QColor(ON_Y).darker(160))
            p.drawRoundedRect(cell, 3, 3)
            pk.led(p, cell.left() + 7, cell.center().y(), on, RED if self.mode == "short" and i else ON_Y, 3)
            _txt(p, QRectF(cell.left() + 12, cell.top(), 22, cell.height()), km, "#C7CED8", TINY)
            _txt(p, QRectF(cell.left() + 30, cell.top(), cell.width() - 32, cell.height()), tag,
                 "#FFFFFF" if on else "#7C8796", SMALL)
        # OL
        ol = QRectF(panel.left() + 4, panel.bottom() - 18, panel.width() - 8, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.DANGER) if self.ol_tripped else QColor("#1E242C"))
        p.drawRoundedRect(ol, 3, 3)
        _txt(p, ol, "OL TRIP" if self.ol_tripped else "OL", "white" if self.ol_tripped else "#7C8796", TINY)
        self.paint_meter(p)
        msg = tr("⚠ ลัดวงจร!") if self.mode == "short" else tr("⚠ สลับเร็วไป") if self.jerk_t > 0 else \
            tr("⚠ ค้างสตาร์") if self.star_too_long() else ""
        if msg:
            badge = QRectF(mr.center().x() - 34, mr.center().y() - 9, 68, 18)
            p.setPen(QPen(QColor("white"), 1))
            p.setBrush(QColor("#E03131"))
            p.drawRoundedRect(badge, 4, 4)
            _txt(p, badge, msg, "white", QFont("Segoe UI", 7, QFont.Bold))


# ======================= ชุดสุญญากาศ =======================
class VacuumItem(DeviceItem):
    W, H = 100, 116
    FAULTS = {"leak": tr("ถ้วยดูดรั่ว/ขาด (สุญญากาศไม่ถึงค่าตั้ง)"), "clog": tr("ไส้กรองตัน (ดูดช้าลงมาก)")}
    WARN_S = 3.0

    def __init__(self, spec):
        super().__init__(spec)
        self.suck = self.blow = self.lift = False
        self.vac = 0.0               # kPa ต่ำกว่าบรรยากาศ
        self.ok = False
        self.cup_z = 0.0             # 0 = ลงแนบถาด, 1 = ยกขึ้นสุด
        self.part = True             # มีชิ้นงาน (บนถาดหรือติดถ้วย)
        self.held = False            # ชิ้นงานติดถ้วยลอยขึ้นมา
        self.lifted = self.dropped = 0
        self.warn = ""
        self.warn_t = 0.0
        self._word = None

    # ---------- I/O ----------
    def kpa_word(self) -> int:
        return int(round(self.vac * 10))            # 0–1000 = 0 ถึง −100.0 kPa

    def input_signals(self):
        out = []
        if self.addr_of("addr_ok"):
            out.append((self.addr_of("addr_ok"), int(self.ok), False))
        if self.addr_of("addr_kpa"):
            out.append((self.addr_of("addr_kpa"), self.kpa_word(), True))
        return out

    def apply_snapshot(self, snap):
        v = (_bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_blow")),
             _bit(snap, self.addr_of("addr_lift")))
        if v != (self.suck, self.blow, self.lift):
            self.suck, self.blow, self.lift = v
            self.update()

    # ---------- simulation ----------
    def sealed(self) -> bool:
        return self.part and (self.held or self.cup_z < 0.05)

    def _warn(self, text):
        self.warn, self.warn_t = text, self.WARN_S

    def tick(self, dt):
        self.vac = physics.vacuum_step(self.vac, self.suck, self.blow, self.sealed(), self.fault == "leak",
                                       self.fault == "clog", dt)
        hold = self.fnum("hold_kpa", 40)
        # แกนยก (ถ้าต่อ addr_lift)
        target = 1.0 if self.lift else 0.0
        was_down = self.cup_z < 0.05
        step = dt / max(self.fnum("lift_s", 0.5), 0.05)
        self.cup_z = min(target, self.cup_z + step) if target > self.cup_z else max(target, self.cup_z - step)
        if was_down and self.cup_z >= 0.05 and self.part and not self.held:
            if self.vac >= hold:
                self.held = True
            else:
                self._warn(tr("ยกก่อนสุญญากาศพอ — ชิ้นงานไม่ติดขึ้นมา"))
        if self.held:
            if self.cup_z < 0.05:
                self.held = False                       # วางกลับลงถาด
                self.lifted += 1
            elif self.vac < hold:
                self.held = False                       # หลุดกลางอากาศ → ตกลงถาด
                self.dropped += 1
                self._warn(tr("ชิ้นงานหลุดกลางทาง! (สุญญากาศไม่พอ/ปล่อยลมกลางอากาศ)"))
        if self.suck and self.blow:
            self._warn(tr("สั่งดูดและเป่าพร้อมกัน (เป่าชนะ เปลืองลม)"))
        self.warn_t = max(0.0, self.warn_t - dt)
        s, d = self.fnum("set_kpa", 60), self.fnum("diff_kpa", 5)
        ok = self.vac >= s if not self.ok else self.vac > s - d
        if ok != self.ok:
            self.ok = ok
            self.emit_bit("addr_ok", int(ok))
        w = self.kpa_word()
        if w != self._word:
            self._word = w
            item_emit_word(self, "addr_kpa", w)
        self.update()

    def _tray_rect(self) -> QRectF:
        r = self.body_rect()
        return QRectF(r.left() + 6, r.bottom() - 26, r.width() - 12, 24)

    def on_press(self, pos):
        on_tray = pos is None or self._tray_rect().adjusted(0, -16, 0, 0).contains(pos)
        if on_tray and not self.held:
            self.part = not self.part                   # วาง/เอาชิ้นงานออกจากถาด
            self.update()

    def state_text(self):
        s = (tr("ดูด {0} · เป่า {1} · สุญญากาศ −{2:.0f} kPa (ตั้ง −{3:.0f}) → OK={4} · {5}", 'ON' if self.suck else 'OFF', 'ON' if self.blow else 'OFF', self.vac, self.fnum('set_kpa', 60), int(self.ok), 'ชิ้นงานติดถ้วย' if self.held else 'มีชิ้นงานบนถาด' if self.part else 'ถาดว่าง (คลิกถาดเพื่อวาง)'))
        if self.addr_of("addr_lift"):
            s += tr(" · ยกสำเร็จ {0} / หลุด {1}", self.lifted, self.dropped)
        if self.warn_t > 0:
            s += f" · ⚠ {self.warn}"
        return s

    def paint_body(self, p):
        r = self.body_rect()
        # ejector + วาล์วบนสุด
        ej = QRectF(r.left() + 8, r.top(), r.width() - 16, 26)
        pk.plate(p, ej, 3, fill="#3A6EA5", edge="#7FA9D6")
        pk.led(p, ej.left() + 8, ej.top() + 8, self.suck, ON_Y, 2.8)
        _txt(p, QRectF(ej.left() + 12, ej.top() + 3, 22, 10), "VAC", "white", TINY, Qt.AlignLeft | Qt.AlignVCenter)
        pk.led(p, ej.left() + 8, ej.top() + 19, self.blow, AMBER, 2.8)
        _txt(p, QRectF(ej.left() + 12, ej.top() + 14, 22, 10), "BLOW", "white", TINY, Qt.AlignLeft | Qt.AlignVCenter)
        # เกจดิจิทัล
        lcd = QRectF(ej.right() - 38, ej.top() + 4, 34, 18)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(QColor("#0E2A1E"))
        p.drawRoundedRect(lcd, 2, 2)
        _txt(p, lcd.adjusted(0, 0, -2, 0), f"-{self.vac:.0f}" if self.vac >= 0.5 else "0", GREEN if self.ok else "#7CFC9A",
             QFont("Consolas", 8, QFont.Bold), Qt.AlignRight | Qt.AlignVCenter)
        # ก้าน + ถ้วยดูด (เลื่อนตาม cup_z)
        tray = self._tray_rect()
        down_y, up_y = tray.top() - 14, ej.bottom() + 20
        cy = down_y + (up_y - down_y) * self.cup_z
        p.setPen(QPen(QColor("#C7CED8"), 4))
        p.drawLine(QPointF(0, ej.bottom()), QPointF(0, cy - 8))
        cup = QRectF(-14, cy - 8, 28, 10)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(QColor("#2B323C") if self.fault != "leak" or self.faults_hidden() else QColor("#5A2B2B"))
        for i in range(3):                                   # ถ้วยแบบลูกฟูก (bellows)
            p.drawRoundedRect(QRectF(-8 - i * 2, cy - 14 + i * 4, 16 + i * 4, 4), 1.5, 1.5)
        p.drawChord(cup, 0, -180 * 16)
        if self.suck and self.vac > 5:
            pk.glow(p, QPointF(0, cy), 14, ON_Y, min(self.vac / 80, 1) * 0.6)
        if self.blow:
            p.setPen(QPen(QColor(116, 192, 252, 200), 1.2, Qt.DashLine))
            for dx in (-10, 0, 10):
                p.drawLine(QPointF(dx * 0.6, cy + 3), QPointF(dx, cy + 12))
        # ถาด + ชิ้นงาน
        p.setPen(QPen(QColor("#9AA4B2"), 2))
        p.setBrush(QColor("#1E242C"))
        p.drawRect(tray)
        if self.part:
            py = cy + 2 if self.held else tray.top() - 12
            p.setPen(QPen(pk.INK, 1))
            p.setBrush(pk.metal(QRectF(-16, py, 32, 12), "#B9C2CE"))
            p.drawRect(QRectF(-16, py, 32, 12))
        else:
            _txt(p, QRectF(tray.left(), tray.top() - 12, tray.width(), 11), tr("คลิก = วางชิ้นงาน"), "#9AA4B2", TINY)
        if self.addr_of("addr_lift"):
            _txt(p, QRectF(tray.left(), tray.top() + 10, tray.width(), 12), f"✔{self.lifted}  ✖{self.dropped}",
                 "#FFE066", TINY)
        if self.warn_t > 0:
            badge = tray.adjusted(-4, 4, 4, -4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.DANGER))
            p.drawRoundedRect(badge, 3, 3)
            short = (tr("⚠ หลุด!") if self.warn == tr("ชิ้นงานหลุดกลางทาง! (สุญญากาศไม่พอ/ปล่อยลมกลางอากาศ)")
                     else tr("⚠ ยกเร็วไป") if self.warn == tr("ยกก่อนสุญญากาศพอ — ชิ้นงานไม่ติดขึ้นมา")
                     else tr("⚠ ดูด+เป่า"))
            _txt(p, badge, short, "white", SMALL)


# ======================= มอเตอร์ DC / BLDC =======================
class DCMotorItem(DeviceItem):
    W, H = 120, 78
    BASE_FAULTS = {"jammed": tr("เพลาติดขัด (ได้ไฟแต่ไม่หมุน)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.a = self.b = False      # brushed: FWD/REV · bldc: EN/DIR
        self.cmd = None              # ค่าความเร็วจาก D (None = ไม่ได้ผูก → เต็มสปีด)
        self.speed = 0.0             # -1..1
        self.angle = 0.0
        self.alarm = False
        self._sent: dict[str, int] = {}

    @property
    def FAULTS(self):  # noqa: N802
        extra = {"hall_fail": tr("เซนเซอร์ Hall เสีย → ไดรฟ์ Alarm")} if self.bldc \
            else {"brush_worn": tr("แปรงถ่านสึก (รอบตกครึ่งหนึ่ง)")}
        return {**self.BASE_FAULTS, **extra}

    @property
    def bldc(self) -> bool:
        return str(self.sprop("drive")) == "bldc"

    @property
    def short(self) -> bool:
        return not self.bldc and self.a and self.b

    def cmd_k(self) -> float:
        if self.cmd is None:
            return 1.0
        return max(0.0, min(self.cmd / max(self.fnum("max_word", 4000), 1), 1.0))

    def direction(self) -> int:
        if self.bldc:
            return (-1 if self.b else 1) if self.a else 0
        if self.short:
            return 0
        return 1 if self.a else -1 if self.b else 0

    def rpm(self) -> int:
        return int(round(self.speed * self.fnum("rpm_max", 3000)))

    # ---------- I/O ----------
    def signals(self) -> dict[str, tuple[int, bool]]:
        return {"addr_alarm": (int(self.alarm), False), "addr_rpm": (self.rpm(), True)}

    def input_signals(self):
        return [(self.addr_of(k), v, w) for k, (v, w) in self.signals().items() if self.addr_of(k)]

    def apply_snapshot(self, snap):
        self.a = _bit(snap, self.addr_of("address"))
        self.b = _bit(snap, self.addr_of("addr_rev"))
        sa = self.addr_of("addr_speed")
        self.cmd = int(snap.get(sa, 0) or 0) if sa else None

    # ---------- simulation ----------
    def tick(self, dt):
        jam = self.fault == "jammed"
        self.alarm = self.bldc and self.a and (self.fault == "hall_fail" or jam)
        d = 0 if (jam or self.alarm) else self.direction()
        k = self.cmd_k() * (0.5 if self.fault == "brush_worn" and not self.bldc else 1.0)
        target = d * k
        if jam:
            self.speed = 0.0
        else:
            self.speed = physics.ramp(self.speed, target, dt, self.fnum("accel_s"), self.fnum("decel_s"))
        if abs(self.speed) < 1e-6:
            self.speed = 0.0
        self.angle = (self.angle + 360 * 3 * dt * self.speed) % 360
        for prop, (v, word) in self.signals().items():
            if self._sent.get(prop) != v:
                self._sent[prop] = v
                (item_emit_word(self, prop, v) if word else self.emit_bit(prop, v))
        self.update()

    def state_text(self):
        if self.short:
            return tr("⚠ ลัดวงจร! สั่งเดินหน้าและถอยหลังพร้อมกัน (รีเลย์กลับขั้วต่อชนกัน)")
        kind = "BLDC" if self.bldc else tr("DC แปรงถ่าน")
        if self.bldc:
            cmd = tr("EN {0} · DIR {1}", "ON" if self.a else "OFF", tr("กลับ") if self.b else tr("หน้า"))
        else:
            cmd = tr("เดินหน้า") if self.a else tr("ถอยหลัง") if self.b else tr("หยุด")
        sp = "" if self.cmd is None else tr(" · สั่ง {0:.0%}", self.cmd_k())
        s = f"{kind} · {cmd}{sp} · {self.rpm():+d} rpm"
        if self.alarm:
            s += tr(" · ⚠ ไดรฟ์ ALARM (ปิด EN แล้วแก้สาเหตุ)")
        return s

    def paint_body(self, p):
        r = self.body_rect()
        bad = self.short or self.alarm
        # ตัวมอเตอร์ (มองด้านข้าง)
        body = QRectF(r.left() + 4, r.top() + 14, 62, 40)
        base_col = "#B9C2CE" if self.bldc else "#2B323C"
        p.setPen(QPen(QColor(RED) if bad else ON_Y if self.direction() else pk.INK, 1.6))
        p.setBrush(pk.metal(body, base_col))
        p.drawRoundedRect(body, 6, 6)
        p.setPen(QPen(pk.INK, 0.8))
        for x in (body.left() + 14, body.right() - 14):
            p.drawLine(QPointF(x, body.top() + 2), QPointF(x, body.bottom() - 2))
        _txt(p, body, "BLDC" if self.bldc else "DC", "#1C2229" if self.bldc else "#C7CED8", SMALL)
        # เพลา + จานหมุน (เห็นทิศ)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.metal(QRectF(body.right(), body.center().y() - 3, 12, 6), "#C7CED8"))
        p.drawRect(QRectF(body.right(), body.center().y() - 3, 12, 6))
        c = QPointF(body.right() + 22, body.center().y())
        p.setBrush(QColor("#E6E9EE"))
        p.drawEllipse(c, 14, 14)
        p.save()
        p.translate(c)
        p.rotate(self.angle)
        p.setBrush(QColor(theme.ACCENT))
        p.drawPie(QRectF(-14, -14, 28, 28), 75 * 16, 30 * 16)
        p.restore()
        # สาย / กล่องไดรฟ์
        if self.bldc:
            drv = QRectF(r.left() + 6, r.top(), 40, 14)
            pk.plate(p, drv, 2, fill="#2A3038", edge="#4A5260", shade=False)
            pk.led(p, drv.left() + 7, drv.center().y(), self.a, ON_Y, 2.5)
            pk.led(p, drv.right() - 7, drv.center().y(), self.alarm, RED, 2.5)
            _txt(p, drv, "DRV", "#C7CED8", TINY)
        else:
            for i, col in enumerate(("#E03131", "#1C2229")):
                p.setPen(QPen(QColor(col), 2))
                p.drawLine(QPointF(body.left() + 18 + i * 8, body.top()), QPointF(body.left() + 14 + i * 8, r.top() + 2))
        # รอบ
        lcd = QRectF(r.left() + 4, r.bottom() - 18, 62, 16)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(QColor("#0E2A1E"))
        p.drawRoundedRect(lcd, 2, 2)
        _txt(p, lcd.adjusted(0, 0, -3, 0), f"{self.rpm():+d}" if self.rpm() else "0", "#7CFC9A", QFont("Consolas", 8, QFont.Bold),
             Qt.AlignRight | Qt.AlignVCenter)
        arrow = "⟳" if self.speed > 0 else "⟲" if self.speed < 0 else "■"
        _txt(p, QRectF(c.x() - 14, r.bottom() - 18, 28, 16), arrow, "#C7CED8", QFont("Segoe UI", 9, QFont.Bold))
        if bad:
            badge = QRectF(body.left(), body.center().y() - 8, body.width(), 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#E03131"))
            p.drawRoundedRect(badge, 4, 4)
            _txt(p, badge, tr("⚠ ลัดวงจร!") if self.short else "⚠ ALARM", "white", SMALL)


# ======================= Stepper + ไดรฟ์ =======================
class StepperItem(DeviceItem):
    W, H = 300, 84
    FAULTS = {"lost_steps": tr("หลุดสเต็ปทุกครั้งที่เคลื่อน (หายราว 10%)"),
              "driver_alarm": tr("ไดรฟ์เสีย (รับพัลส์แต่มอเตอร์ไม่ขยับ)")}
    WARN_S = 3.0
    MECH_MIN_MM = -1.0               # ชนปลายกลไกด้านซ้าย (เลย Home ไปนิดเดียว)
    HOME_MM = 0.5                    # เซนเซอร์ Home ON เมื่อแคร่อยู่ซ้ายกว่านี้

    def __init__(self, spec):
        super().__init__(spec)
        self.ena = self.start = self.jog_f = self.jog_r = False
        self.target = 0
        self.count = 0.0             # พัลส์ที่ PLC/ไดรฟ์นับได้
        self.actual = 0.0            # ตำแหน่งจริงของแคร่ (หน่วยพัลส์)
        self.v = 0.0                 # พัลส์/วินาที (มีเครื่องหมาย)
        self.mode = None             # None | "pos" | "jog"
        self.goal = 0
        self.stalled = False
        self.homed_t = 0.0
        self.warn = ""
        self.warn_t = 0.0
        self._sent: dict[str, int] = {}

    # ---------- หน่วย ----------
    @property
    def spr(self) -> float:
        return physics.steps_per_rev(self.fnum("step_deg", 1.8), self.fnum("microstep", 16))

    @property
    def ppm(self) -> float:          # พัลส์ต่อ mm
        return self.spr / max(self.fnum("lead_mm", 10), 0.1)

    def mm(self, pulses: float) -> float:
        return pulses / self.ppm

    def at_home(self) -> bool:
        return self.mm(self.actual) <= self.HOME_MM

    def lost_mm(self) -> float:
        return self.mm(self.count - self.actual)

    def busy(self) -> bool:
        return self.mode is not None

    # ---------- I/O ----------
    def signals(self) -> dict[str, tuple[int, bool]]:
        pos = max(-32768, min(32767, int(round(self.count))))
        return {"addr_busy": (int(self.busy()), False), "addr_home": (int(self.at_home()), False),
                "addr_pos": (pos, True)}

    def input_signals(self):
        return [(self.addr_of(k), v, w) for k, (v, w) in self.signals().items() if self.addr_of(k)]

    def _warn(self, text):
        self.warn, self.warn_t = text, self.WARN_S

    def apply_snapshot(self, snap):
        s = _bit(snap, self.addr_of("addr_start"))
        self.ena = _bit(snap, self.addr_of("address"))
        self.jog_f = _bit(snap, self.addr_of("addr_jog_f"))
        self.jog_r = _bit(snap, self.addr_of("addr_jog_r"))
        ta = self.addr_of("addr_target")
        self.target = int(snap.get(ta, 0) or 0) if ta else 0
        if s and not self.start:                      # ขอบขาขึ้นของ START
            if not self.ena:
                self._warn(tr("สั่ง START ตอน ENA OFF — ไดรฟ์ไม่รับคำสั่ง"))
            elif self.mode is None:
                self.mode, self.goal, self.stalled = "pos", self.target, False
        self.start = s

    # ---------- simulation ----------
    def tick(self, dt):
        if dt <= 0:
            return
        acc = max(self.fnum("accel_pps2", 32000), 1.0)
        if not self.ena:                              # ปลดแรงบิด: หยุดนิ่ง ตัวนับคงเดิม
            self.v, self.mode = 0.0, None
        elif self.mode is None and self.jog_r and self.at_home() and self.count != 0:
            self.count, self.homed_t = 0.0, self.WARN_S   # อยู่ที่ Home อยู่แล้ว: เซนเซอร์ยืนยัน → รีเซ็ตตัวนับ
        elif self.mode is None and (self.jog_f or (self.jog_r and not self.at_home())):
            self.mode, self.stalled = "jog", False
        if self.mode == "pos":
            d = self.goal - self.count
            vdes = math.copysign(min(self.fnum("pps_max", 16000), math.sqrt(2 * acc * abs(d))), d) if abs(d) > 1e-9 else 0.0
        elif self.mode == "jog":
            j = self.fnum("jog_pps", 3200)
            vdes = j if self.jog_f else -j if self.jog_r else 0.0
        else:
            vdes = 0.0
        v0 = self.v
        self.v = min(vdes, self.v + acc * dt) if self.v < vdes else max(vdes, self.v - acc * dt)
        dc = self.v * dt
        if self.mode == "pos" and (self.goal - (self.count + dc)) * (self.goal - self.count) <= 0:
            dc, self.v = self.goal - self.count, 0.0
            self.mode = None
        elif self.mode == "jog" and vdes == 0 and self.v == 0:
            self.mode = None
        self.count += dc
        # มอเตอร์ตามพัลส์ทันไหม (โค้งแรงบิด)
        # ความเร่งจริงไม่เกินค่าตั้ง (การหยุดตรงเป้าพอดีในรอบเดียวเป็นแค่การปัดเศษของการจำลอง)
        rps, rps2 = self.v / self.spr, max(-acc, min(acc, (self.v - v0) / dt)) / self.spr
        if dc and not physics.stepper_torque_ok(rps, rps2, self.fnum("load_pct", 50)):
            if not self.stalled:
                self._warn(tr("หลุดสเต็ป! แรงบิดไม่พอ (โหลด/ความเร็ว/ความเร่งสูงเกิน)"))
            self.stalled = True
        if dc and not self.stalled and self.fault != "driver_alarm":
            k = 0.9 if self.fault == "lost_steps" else 1.0
            lo, hi = self.MECH_MIN_MM * self.ppm, self.fnum("stroke_mm", 100) * self.ppm
            self.actual = max(lo, min(hi, self.actual + dc * k))
        # Jog กลับจนเจอ Home → หยุด + รีเซ็ตตัวนับเป็น 0
        if self.mode == "jog" and self.jog_r and self.v < 0 and self.at_home():
            self.v, self.mode, self.count = 0.0, None, 0.0
            self.homed_t = self.WARN_S
        self.warn_t = max(0.0, self.warn_t - dt)
        self.homed_t = max(0.0, self.homed_t - dt)
        for prop, (val, word) in self.signals().items():
            if self._sent.get(prop) != val:
                self._sent[prop] = val
                (item_emit_word(self, prop, val) if word else self.emit_bit(prop, val))
        self.update()

    def state_text(self):
        s = (tr("ENA {0} · {1} · ตัวนับ {2:.0f} พัลส์ ({3:.1f} mm) · ตำแหน่งจริง {4:.1f} mm · 1 รอบ = {5:.0f} พัลส์", 'ON' if self.ena else 'OFF', 'กำลังเคลื่อน' if self.busy() else 'หยุด', self.count, self.mm(self.count), self.mm(self.actual), self.spr))
        if abs(self.lost_mm()) > 0.5:
            s += tr(" · ⚠ ตำแหน่งจริงไม่ตรงกับที่นับ ({0:+.1f} mm) — ต้อง Home ใหม่", self.lost_mm())
        if self.warn_t > 0:
            s += f" · ⚠ {self.warn}"
        if self.homed_t > 0:
            s += tr(" · ✔ Home แล้ว รีเซ็ตตัวนับเป็น 0")
        return s

    # ---------- painting ----------
    def paint_body(self, p):
        r = self.body_rect()
        stroke = max(self.fnum("stroke_mm", 100), 1)
        rail = QRectF(r.left() + 52, -10, r.width() - 58, 20)
        x0, x1 = rail.left() + 12, rail.right() - 12

        def xpos(mm):
            return x0 + (x1 - x0) * max(self.MECH_MIN_MM, min(stroke, mm)) / stroke

        # ราง + บอลสกรู
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.metal(rail, "#AEB7C2"))
        p.drawRoundedRect(rail, 3, 3)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        x = x0
        while x < x1:
            p.drawLine(QPointF(x, rail.top() + 6), QPointF(x + 4, rail.bottom() - 6))
            x += 6
        # มอเตอร์ stepper (ตัวสี่เหลี่ยม NEMA)
        m = QRectF(r.left() + 4, -20, 44, 40)
        p.setPen(QPen(ON_Y if self.ena else pk.INK, 1.6))
        p.setBrush(pk.lin(m, ((0, "#4B5666"), (0.5, "#2B323C"), (1, "#1A1F26"))))
        p.drawRoundedRect(m, 4, 4)
        for cx, cy in ((m.left() + 6, m.top() + 6), (m.right() - 6, m.top() + 6),
                       (m.left() + 6, m.bottom() - 6), (m.right() - 6, m.bottom() - 6)):
            pk.screw(p, cx, cy, 2.2)
        _txt(p, m, "STEP", "#C7CED8", SMALL)
        # เซนเซอร์ Home
        hx = xpos(self.HOME_MM)
        pk.led(p, hx, -24, self.at_home(), ON_X, 3)
        _txt(p, QRectF(hx + 5, -29, 30, 10), "HOME", "#9AA4B2", TINY, Qt.AlignLeft | Qt.AlignVCenter)
        # ตำแหน่งที่นับ (เส้นประ) vs ตำแหน่งจริง (แคร่)
        cxp = xpos(self.mm(self.count))
        lost = abs(self.lost_mm()) > 0.5
        p.setPen(QPen(QColor(AMBER), 1.5, Qt.DashLine))
        p.drawLine(QPointF(cxp, rail.top() - 4), QPointF(cxp, rail.bottom() + 8))
        ax = xpos(self.mm(self.actual))
        car = QRectF(ax - 16, -16, 32, 32)
        p.setPen(QPen(pk.INK, 1.5))
        p.setBrush(QColor(theme.DANGER) if lost else QColor(theme.ACCENT))
        p.drawRoundedRect(car, 4, 4)
        # แผงล่าง: ตัวนับ + LED
        lcd = QRectF(r.left() + 4, r.bottom() - 18, 74, 16)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(QColor("#0E2A1E"))
        p.drawRoundedRect(lcd, 2, 2)
        _txt(p, lcd.adjusted(0, 0, -3, 0), f"{self.count:.0f}", "#7CFC9A", QFont("Consolas", 8, QFont.Bold),
             Qt.AlignRight | Qt.AlignVCenter)
        for i, (name, on, col) in enumerate((("ENA", self.ena, GREEN), ("BUSY", self.busy(), AMBER),
                                             ("ALM", self.fault == "driver_alarm" and not self.faults_hidden(), RED))):
            x = r.left() + 92 + i * 40
            pk.led(p, x, r.bottom() - 10, on, col, 3)
            _txt(p, QRectF(x + 5, r.bottom() - 16, 32, 12), name, "#9AA4B2", TINY, Qt.AlignLeft | Qt.AlignVCenter)
        msg = tr("⚠ หลุดสเต็ป!") if lost else ("⚠ " + self.warn.split(" ")[0]) if self.warn_t > 0 else \
            "✔ Home" if self.homed_t > 0 else ""
        if msg:
            badge = QRectF(r.right() - 96, r.bottom() - 18, 94, 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(GREEN) if msg.startswith("✔") else QColor(theme.DANGER))
            p.drawRoundedRect(badge, 4, 4)
            _txt(p, badge, msg, "#0E1218" if msg.startswith("✔") else "white", SMALL)


CLASSES = {
    "stepper": StepperItem,
    "dc_motor": DCMotorItem,
    "vacuum": VacuumItem,
    "motor_yd": MotorYDItem,
    "relay": RelayItem, "latch_relay": LatchRelayItem, "ssr": SSRItem,
    "phase_relay": PhaseRelayItem, "safety_relay": SafetyRelayItem,
}
