"""กราฟิกของอุปกรณ์แต่ละชนิดบนผัง (QGraphicsObject).

โหมด RUN: คลิกเพื่อใช้งาน (กดปุ่ม/สับสวิตช์/ใส่ชิ้นงาน)
โหมด EDIT: ลากย้าย/เลือก ได้ตามปกติ
"""
from __future__ import annotations

from ...i18n import tr, tr_data

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsRectItem

from ...panel import physics
from ...panel.catalog import CATALOG, LAMP_COLORS
from ...panel.model import DeviceSpec
from .. import theme
from . import paintkit as pk

BODY = 64          # ขนาดตัวอุปกรณ์มาตรฐาน
DIM = QColor("#4A5568")
TEXT = QColor(theme.TEXT)
TEXT_DIM = QColor(theme.TEXT_DIM)
FONT = QFont("Segoe UI", 8)
FONT_B = QFont("Segoe UI", 9, QFont.Bold)
FONT_KEY = QFont("Consolas", 8, QFont.Bold)


SCALE = 1.0


def cap_h() -> float:
    """ความสูงของป้ายชื่อ + address ใต้อุปกรณ์ (ขยายตามโหมดตัวใหญ่)."""
    return 40 * SCALE


def set_font_scale(scale: float):
    """โหมดตัวใหญ่: ขยายป้ายชื่อ/address บนผัง."""
    global FONT, FONT_B, FONT_KEY, SCALE
    SCALE = scale
    FONT = QFont("Segoe UI", round(8 * scale))
    FONT_B = QFont("Segoe UI", round(9 * scale), QFont.Bold)
    FONT_KEY = QFont("Consolas", round(8 * scale), QFont.Bold)


def _color(name, default="#5EE36A"):
    return QColor(LAMP_COLORS.get(name, default))


class DeviceItem(QGraphicsObject):
    request_write = Signal(str, int)        # เขียนบิต
    request_write_word = Signal(str, int)   # เขียนค่าตัวเลข (D)
    W, H = BODY, BODY
    Z = 1                                   # ลำดับชั้นการวาด (กรอบโซน = -1, สายพาน = 0)
    FAULTS: dict[str, str] = {}             # ความผิดปกติที่ครูใส่ได้: รหัส -> คำอธิบาย

    def __init__(self, spec: DeviceSpec):
        super().__init__()
        self.spec = spec
        self.info = CATALOG[spec.kind]
        self.fault = ""            # ความผิดปกติตอนรัน (ไม่บันทึกลงไฟล์ผัง)
        self.valid = True          # address ทุกช่องถูกต้องไหม
        self.conflict = False
        self.slot_ok: dict[str, tuple[bool, str]] = {}   # prop -> (ถูกต้อง, ชื่อมาตรฐาน/ข้อความผิด)
        self._flash = False
        self.last_change = ""      # เวลาที่สถานะเปลี่ยนล่าสุด (สำหรับ tooltip)
        self.setPos(spec.x, spec.y)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.PointingHandCursor)

    # ---------- props ----------
    @property
    def addr(self) -> str:
        return self.spec.address.upper()

    @property
    def label(self) -> str:
        return str(self.spec.props.get("label", ""))

    @property
    def shown_label(self) -> str:
        """ชื่อที่แสดง — แปลตามภาษา (ชื่อในไฟล์ยังเป็นภาษาเดิม; label ใช้เป็นตัวระบุ เช่น ด่านหาจุดเสีย)."""
        return tr_data(self.label)

    def prop(self, key, default=None):
        return self.spec.props.get(key, default)

    def sprop(self, key):
        """ค่าสเปก — ถ้ายังไม่ได้ตั้ง ใช้ค่าเริ่มต้นของ SpecField (ผังเก่าไม่มี prop ใหม่ก็ทำงานเหมือนเดิม)."""
        v = self.spec.props.get(key)
        if v is None or v == "":
            f = self.info.spec_field(key)
            return self.info.default_of(f) if f else None
        return v

    def fnum(self, key, fallback=0.0) -> float:
        try:
            return float(self.sprop(key))
        except (TypeError, ValueError):
            return fallback

    def panel_view(self):
        s = self.scene()
        return getattr(s, "owner", None) if s else None

    def linked(self, prop: str):
        """อุปกรณ์ที่ผูกไว้ผ่าน field แบบ link (เก็บ id)."""
        v, i = self.panel_view(), str(self.prop(prop, "") or "")
        return v.items_by_id.get(i) if (v is not None and i) else None

    def addr_of(self, prop: str) -> str:
        """address ของช่องนั้น (ชื่อมาตรฐาน) หรือ "" ถ้าว่าง/ไม่ถูกต้อง."""
        ok, name = self.slot_ok.get(prop, (False, ""))
        return name if ok else ""

    def emit_bit(self, prop: str, value: int):
        a = self.addr_of(prop)
        if a:
            self.request_write.emit(a, int(value))

    def input_signals(self) -> list[tuple[str, int, bool]]:
        """ค่าที่ต้องเขียนลง PLC ตอนเชื่อมต่อ/เปลี่ยน address: [(address, ค่า, เป็น word)]."""
        return []

    # ---------- Fault Injection ----------
    def faults_hidden(self) -> bool:
        s = self.scene()
        return bool(s and getattr(s, "faults_hidden", False))

    def set_fault(self, code: str):
        """ใส่/ล้างความผิดปกติ ("" = ปกติ) แล้วส่งค่า Input ปัจจุบันให้ PLC ทันที."""
        code = code if code in self.FAULTS else ""
        if code == self.fault:
            return
        self.fault = code
        self.on_fault_changed()
        for a, v, is_word in self.input_signals():
            (self.request_write_word if is_word else self.request_write).emit(a, int(v))
        self.refresh_tooltip()
        self.update()

    def on_fault_changed(self):
        pass

    def caption_tag(self) -> str:
        slots = self.info.slots()
        if len(slots) == 1:
            return self.addr
        return " ".join(self.addr_of(s.prop) or (str(self.prop(s.prop, "")) and "?")
                        for s in slots if self.prop(s.prop, "") or not s.optional)

    @property
    def key(self) -> str:
        return str(self.spec.props.get("key", "") or "").upper()

    def run_mode(self) -> bool:
        s = self.scene()
        return bool(s and getattr(s, "run_mode", False))

    # ---------- tooltip ----------
    def state_text(self) -> str:
        return ""

    def refresh_tooltip(self):
        rows = [f"<b>{self.shown_label or '-'}</b> — {self.info.name}"]
        contact = self.prop("contact")
        for s in self.info.slots():
            raw = str(self.prop(s.prop, "") or "")
            if not raw and s.optional:
                continue
            ok = self.slot_ok.get(s.prop, (True, raw))[0]
            a = raw.upper() if ok else tr("{0} (ไม่ถูกต้อง)", raw or '?')
            extra = f" ({contact})" if contact and s.prop == "address" else ""
            rows.append(f"{s.label}: <b>{a}</b>{extra}")
        st = self.state_text()
        if st:
            rows.append(tr("สถานะ: {0}", st))
        if self.last_change:
            rows.append(tr("เปลี่ยนล่าสุด: {0}", self.last_change))
        if self.key:
            rows.append(tr("คีย์ลัด: [{0}]", self.key))
        if self.conflict:
            rows.append(tr("<span style='color:#FF6B6B'>⚠ address ซ้ำกับ Input อื่น</span>"))
        if self.fault and not self.faults_hidden():
            rows.append(tr("<span style='color:#FF6B6B'>⚡ ความผิดปกติ: {0}</span>", self.FAULTS.get(self.fault, self.fault)))
        self.setToolTip("<br>".join(rows))

    # ---------- geometry ----------
    def body_rect(self) -> QRectF:
        return QRectF(-self.W / 2, -self.H / 2, self.W, self.H)

    def boundingRect(self) -> QRectF:
        r = self.body_rect()
        return QRectF(min(r.left() - 10, -48 * SCALE), r.top() - 10, max(r.width() + 20, 96 * SCALE),
                      r.height() + 6 + cap_h())   # เผื่อป้าย ⚡ ความผิดปกติที่มุมซ้ายบน

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            grid = getattr(self.scene(), "snap", 0)
            if grid:
                value = QPointF(round(value.x() / grid) * grid, round(value.y() / grid) * grid)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.spec.x, self.spec.y = self.pos().x(), self.pos().y()
            s = self.scene()
            if s and hasattr(s, "item_moved"):
                s.item_moved()
        return super().itemChange(change, value)

    # ---------- painting ----------
    def paint(self, p: QPainter, opt, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        self.paint_body(p)
        self.paint_caption(p)
        if self.fault and not self.faults_hidden():
            r = self.body_rect()
            badge = QRectF(r.left() - 8, r.top() - 8, 18, 18)
            p.setPen(QPen(QColor("white"), 1.5))
            p.setBrush(QColor("#E03131"))
            p.drawEllipse(badge)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(QColor("white"))
            p.drawText(badge, Qt.AlignCenter, "⚡")
        if self.key:
            r = self.body_rect()
            p.setFont(FONT_KEY)
            w = p.fontMetrics().horizontalAdvance(self.key) + 8
            kr = QRectF(r.left() - 4, r.bottom() - 12, max(w, 16), 16)
            p.setPen(QPen(QColor("#10151B"), 1))
            p.setBrush(QColor("#E6E9EE"))
            p.drawRoundedRect(kr, 3, 3)
            p.setPen(QColor("#10151B"))
            p.drawText(kr, Qt.AlignCenter, self.key)
        if self.isSelected() and not self.run_mode():
            p.setPen(QPen(QColor(theme.ACCENT), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))
        if self._flash:
            p.setPen(QPen(QColor("#FFE066"), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.body_rect().adjusted(-6, -6, 6, 6), 8, 8)

    def paint_body(self, p: QPainter):
        pass

    def paint_caption(self, p: QPainter):
        r = self.body_rect()
        y = r.bottom() + 4
        p.setFont(FONT_B)
        p.setPen(TEXT)
        h1 = 16 * SCALE
        p.drawText(QRectF(-80 * SCALE, y, 160 * SCALE, h1), Qt.AlignHCenter, self.shown_label)
        tag = self.caption_tag() if self.valid else (self.caption_tag() or "?") + " ?"
        if self.conflict:
            tag = "⚠ " + tag
        col = QColor("#FF6B6B") if (not self.valid or self.conflict) else QColor(theme.color_for(self.addr))
        p.setFont(FONT)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(tag) + 14
        tag_r = QRectF(-w / 2, y + h1, w, 14 * SCALE)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BG_CANVAS))
        p.drawRoundedRect(tag_r, tag_r.height() / 2, tag_r.height() / 2)
        pk.chip(p, tag_r, tag, col, FONT)

    def flash(self, ms=600):
        self._flash = True
        self.update()
        QTimer.singleShot(ms, self._unflash)

    def _unflash(self):
        self._flash = False
        self.update()

    # ---------- runtime ----------
    def apply_snapshot(self, snap: dict):
        pass

    def tick(self, dt: float):
        pass

    def on_press(self, pos: QPointF):
        pass

    def on_release(self, pos: QPointF):
        pass

    def mousePressEvent(self, e):
        if self.run_mode():
            self.on_press(e.pos())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self.run_mode():
            self.on_release(e.pos())
            e.accept()
            return
        super().mouseReleaseEvent(e)


# ======================= INPUT =======================
INPUT_FAULTS = {"stuck_on": tr("หน้าสัมผัสค้าง ON (ส่ง 1 ตลอด)"), "wire_break": tr("สายขาด (ส่ง 0 ตลอด)")}


class InputItem(DeviceItem):
    FAULTS = INPUT_FAULTS

    def __init__(self, spec):
        super().__init__(spec)
        self.actuated = False
        self.plc_seen = 0     # ค่าที่ PLC เห็นจริง (อ่านกลับ)
        self._bounce: list[tuple[float, int]] = []
        self._bounce_t = 0.0

    @property
    def nc(self) -> bool:
        return str(self.prop("contact", "NO")).upper() == "NC"

    def signal(self) -> int:
        if self.fault == "stuck_on":
            return 1
        if self.fault == "wire_break":
            return 0
        act = self.actuated or self.fault == "trip"
        return int(act) ^ int(self.nc)

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.signal(), False)] if a else []

    def state_text(self) -> str:
        act = tr("ถูกกด/ทำงาน") if self.actuated else tr("ปกติ")
        return tr("{0} → ส่ง {1} · PLC เห็น {2}", act, self.signal(), self.plc_seen)

    def set_actuated(self, v: bool):
        if v != self.actuated:
            self.actuated = v
            self.emit_bit("address", self.signal())
            self._start_bounce()
            self.update()

    # ---------- หน้าสัมผัสกระเด้ง (bounce) ----------
    def _start_bounce(self):
        """หลังเปลี่ยนสถานะ ส่งสัญญาณกลับไปกลับมาอีก 2 รอบภายใน bounce_ms แล้วจบที่ค่าจริง."""
        b = self.fnum("bounce_ms") / 1000.0 if self.info.spec_field("bounce_ms") else 0.0
        if b <= 0 or self.fault:
            self._bounce = []
            return
        final = self.signal()
        self._bounce_t = 0.0
        self._bounce = [(b * 0.25, 1 - final), (b * 0.5, final), (b * 0.75, 1 - final), (b, final)]

    def _tick_bounce(self, dt):
        if not self._bounce:
            return
        self._bounce_t += dt
        while self._bounce and self._bounce[0][0] <= self._bounce_t + 1e-9:
            self.emit_bit("address", self._bounce.pop(0)[1])

    def tick(self, dt):
        self._tick_bounce(dt)

    def on_press(self, pos):
        if self.info.momentary:
            self.set_actuated(True)
        else:
            self.set_actuated(not self.actuated)

    def on_release(self, pos):
        if self.info.momentary:
            self.set_actuated(False)

    def apply_snapshot(self, snap):
        v = int(bool(snap.get(self.addr, 0)))
        if v != self.plc_seen:
            self.plc_seen = v
            self.update()

    def paint_led(self, p, x, y):
        """ไฟเล็กบอกว่า PLC เห็นสัญญาณ ON."""
        pk.led(p, x, y, bool(self.plc_seen), theme.SIGNAL_COLORS["X"], 3.5)

    def paint_contact_tag(self, p):
        r = self.body_rect()
        p.setFont(FONT)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(r.left() + 3, r.top() + 2, 30, 12), Qt.AlignLeft, "NC" if self.nc else "NO")


class PushButtonItem(InputItem):
    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 8)
        c = _color(self.prop("color", "green"))
        ctr = QPointF(0, 3)
        pk.bezel(p, ctr, 23, 4)
        pressed = self.actuated
        if not pressed:      # ขอบข้างของหัวปุ่มที่ยื่นขึ้นมา
            p.setPen(Qt.NoPen)
            p.setBrush(c.darker(230))
            p.drawEllipse(ctr + QPointF(0, 2.5), 17.5, 17.5)
        top = ctr + (QPointF(0, 1.5) if pressed else QPointF(0, -0.5))
        rad = 16.0 if pressed else 17.5
        p.setPen(QPen(c.darker(220), 1.2))
        p.setBrush(pk.ball(top, rad, c.darker(115) if pressed else c, 0.4 if pressed else 1.0))
        p.drawEllipse(top, rad, rad)
        self.paint_contact_tag(p)
        self.paint_led(p, r.right() - 8, r.top() + 8)


class SelectorItem(InputItem):
    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 8)
        ctr = QPointF(0, 4)
        pk.bezel(p, ctr, 23, 3.5)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.ball(ctr, 19, "#2A2F37", 0.5))
        p.drawEllipse(ctr, 19, 19)
        p.save()
        p.translate(ctr)
        p.rotate(40 if self.actuated else -40)
        handle = QRectF(-6, -19, 12, 38)          # ด้ามจับ
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.lin(handle, ((0, "#4A525E"), (0.45, "#16191E"), (1, "#3A414C")), vertical=False))
        p.drawRoundedRect(handle, 5, 5)
        p.setPen(QPen(QColor("#F4F6F9"), 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(0, -16), QPointF(0, -8))   # ขีดบอกตำแหน่ง
        p.restore()
        p.setFont(FONT)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(-30, -30, 20, 12), Qt.AlignCenter, "0")
        p.drawText(QRectF(10, -30, 20, 12), Qt.AlignCenter, "1")
        self.paint_led(p, r.right() - 8, r.top() + 8)


class EStopItem(InputItem):
    W = H = 70

    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 8, fill="#E9B800", edge="#FFE27A")
        ctr = QPointF(0, 0)
        p.setPen(QPen(QColor("#8A6A00"), 1))           # ฐานวงกลมเหลือง
        p.setBrush(pk.ball(ctr, 31, "#F7CF1C", 0.4))
        p.drawEllipse(ctr, 31, 31)
        pk.bezel(p, ctr, 25.5, 3)
        locked = self.actuated
        if not locked:      # หัวเห็ดยกขึ้น: เห็นก้านใต้หัว
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#5E0F0F"))
            p.drawEllipse(ctr + QPointF(0, 3), 23.5, 23.5)
        head = ctr + (QPointF(0, 1) if locked else QPointF(0, -1))
        rad = 21.5 if locked else 23.5
        p.setPen(QPen(QColor("#4A0808"), 1.2))
        p.setBrush(pk.ball(head, rad, "#A51D1D" if locked else "#E03131", 0.4 if locked else 1.0))
        p.drawEllipse(head, rad, rad)
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 230))
        p.drawText(QRectF(-24, head.y() - 8, 48, 16), Qt.AlignCenter, "STOP" if not locked else "LOCK")
        self.paint_led(p, r.right() - 8, r.top() + 8)


class LimitItem(InputItem):
    def paint_body(self, p):
        r = self.body_rect()
        # สายไฟออกทางต่อสาย (ขวาล่าง)
        pk.cable(p, [QPointF(24, 20), QPointF(31, 22), QPointF(34, 30)], width=3.5)
        p.setPen(QPen(pk.INK, 0.8))
        gland = QRectF(22, 16, 6, 8)
        p.setBrush(pk.metal(gland, "#5B6370"))
        p.drawRect(gland)
        # ตัวสวิตช์ (โลหะหล่อ) + หัวสวิตช์
        body = QRectF(-24, -2, 46, 28)
        pk.plate(p, body, 3, fill="#8C96A4", edge="#C9D0DA")
        pk.screw(p, body.left() + 5, body.bottom() - 5, 2)
        pk.screw(p, body.right() - 5, body.bottom() - 5, 2)
        head = QRectF(-21, -10, 15, 10)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.lin(head, ((0, "#4B5462"), (1, "#262C35"))))
        p.drawRoundedRect(head, 2, 2)
        # คันโยก + ลูกล้อยาง
        ang = -15 if self.actuated else -45
        p.save()
        p.translate(-14, -6)
        p.rotate(ang)
        arm = QRectF(-2, -2.5, 34, 5)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.metal(arm, "#B5BEC9"))
        p.drawRoundedRect(arm, 2, 2)
        p.setBrush(pk.ball(QPointF(32, 0), 7, "#2A2F36", 0.5))
        p.drawEllipse(QPointF(32, 0), 7, 7)
        p.setBrush(pk.ball(QPointF(32, 0), 2.6, "#C7CED8", 0.8))
        p.drawEllipse(QPointF(32, 0), 2.6, 2.6)
        p.restore()
        pk.screw(p, -14, -6, 3)
        self.paint_contact_tag(p)
        self.paint_led(p, r.right() - 8, r.top() + 8)


SENSE_TAG = {"photo": "PH", "inductive": "IND", "capacitive": "CAP"}


class SensorItem(InputItem):
    """เซนเซอร์ตรวจจับชิ้นงาน: ยิงลงด้านล่าง ชิ้นงานที่อยู่ในระยะ = ตรวจเจอ.
    photo = ลำแสงยาว เห็นทุกชิ้น · inductive = ระยะสั้น เฉพาะโลหะ · capacitive = ระยะสั้น ทุกวัสดุ."""
    W, H = 46, 40
    BEAM_PHOTO, BEAM_PROX = 120, 50
    FAULTS = {**INPUT_FAULTS, "dirty": tr("หน้าเซนเซอร์สกปรก (มองไม่เห็นชิ้นงาน)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.manual = False
        self.detected = False     # เห็นชิ้นงานจริงตอนนี้
        self._out = False         # ผลหลังผ่านเวลาตอบสนอง
        self._resp_t = 0.0
        self._resolve()

    @property
    def sense(self) -> str:
        s = str(self.prop("sense", "photo"))
        return s if s in SENSE_TAG else "photo"

    @property
    def dark_on(self) -> bool:
        return str(self.sprop("mode")) == "don"

    @property
    def BEAM(self):  # noqa: N802
        r = self.fnum("range_mm")
        if r > 0:
            return r
        return self.BEAM_PHOTO if self.sense == "photo" else self.BEAM_PROX

    def _resolve(self):
        self.set_actuated(self.manual or (self._out ^ self.dark_on))

    def tick(self, dt):
        super().tick(dt)
        resp = self.fnum("response_ms") / 1000.0
        if resp > 0 and self.detected != self._out:
            self._resp_t += dt
            if self._resp_t >= resp - 1e-9:
                self._out, self._resp_t = self.detected, 0.0
                self._resolve()
        else:
            self._resp_t = 0.0

    def state_text(self) -> str:
        s = super().state_text()
        out = str(self.sprop("output")).upper()
        return tr("{0} · {1} {2} · ระยะ {3:.0f} mm", s, out, 'D.ON' if self.dark_on else 'L.ON', self.BEAM)

    def sees(self, wp) -> bool:
        """เซนเซอร์ชนิดนี้มองเห็นชิ้นงานนี้ไหม (ตามวัสดุ)."""
        return self.sense != "inductive" or getattr(wp, "material", "") == "metal"

    def beam_scene_rect(self) -> QRectF:
        return self.mapRectToScene(QRectF(-1.5 if self.sense == "photo" else -10, self.H / 2,
                                          3 if self.sense == "photo" else 20, self.BEAM))

    def paint_caption(self, p):
        # ป้ายชื่อไว้ด้านบน เพราะด้านล่างเป็นลำแสง
        r = self.body_rect()
        p.save()
        p.translate(0, -r.height() - cap_h())
        super().paint_caption(p)
        p.restore()

    def boundingRect(self):  # รวมป้ายด้านบนและลำแสงด้านล่าง
        r = self.body_rect()
        return QRectF(-48 * SCALE, r.top() - 4 - cap_h(), 96 * SCALE, r.height() + 4 + cap_h() + self.BEAM)

    def set_detected(self, v: bool):
        v = v and self.fault != "dirty"
        self.detected = v
        if self.fnum("response_ms") <= 0:
            self._out, self._resp_t = v, 0.0
        self._resolve()

    def on_press(self, pos):
        self.manual = not self.manual
        self._resolve()

    def paint_body(self, p):
        r = self.body_rect()
        # สายไฟออกท้ายเซนเซอร์
        pk.cable(p, [QPointF(-6, -16), QPointF(-16, -17), QPointF(-27, -12)], width=3)
        # ฝาท้าย + LED 2 ดวง (เขียว = ไฟเลี้ยง, ส้ม = เอาต์พุต)
        cap = QRectF(-9, -20, 18, 8)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.lin(cap, ((0, "#3A424E"), (1, "#1C2129")), vertical=False))
        p.drawRoundedRect(cap, 2, 2)
        pk.led(p, -4, -16, True, "#22C55E", 2)
        pk.led(p, 4, -16, self.actuated, "#FF9F1C", 2)
        # กระบอกเกลียว M18 + น็อต 2 ตัว
        pk.thread(p, QRectF(-8, -12, 16, 26))
        pk.hex_nut(p, 0, -5, 24, 5)
        pk.hex_nut(p, 0, 8, 24, 5)
        face = QRectF(-8, 14, 16, 6)       # หน้าตรวจจับ
        face_col = {"photo": "#3A1212", "inductive": "#E8913A", "capacitive": "#3B7DD8"}[self.sense]
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.lin(face, ((0, QColor(face_col).lighter(140)), (1, face_col)), vertical=False))
        p.drawRoundedRect(face, 1.5, 1.5)
        if self.sense == "photo":
            pk.led(p, 0, 17, self.actuated, "#FF4D4D", 2)
        p.setFont(FONT)
        p.setPen(TEXT_DIM)
        p.drawText(QRectF(13, -6, 24, 12), Qt.AlignLeft | Qt.AlignVCenter, "NC" if self.nc else "NO")
        p.setFont(QFont("Segoe UI", 6, QFont.Bold))
        p.setPen(QColor("#9AC8FF"))
        p.drawText(QRectF(13, 5, 24, 12), Qt.AlignLeft | Qt.AlignVCenter, SENSE_TAG[self.sense])
        if self.sense == "photo":      # ลำแสง
            col = QColor("#FF6B6B") if self.actuated else QColor(255, 107, 107, 70)
            p.setPen(QPen(col, 2 if self.actuated else 1, Qt.DashLine))
            p.drawLine(QPointF(0, r.bottom()), QPointF(0, r.bottom() + self.BEAM))
        else:                          # สนามแม่เหล็ก/ประจุ ระยะสั้น
            col = QColor(116, 192, 252, 150 if self.actuated else 45)
            p.setPen(QPen(col, 1, Qt.DashLine))
            p.setBrush(QColor(116, 192, 252, 60 if self.actuated else 18))
            p.drawPolygon(QPolygonF([QPointF(-8, r.bottom()), QPointF(8, r.bottom()),
                                     QPointF(12, r.bottom() + self.BEAM), QPointF(-12, r.bottom() + self.BEAM)]))
        self.paint_led(p, r.right() - 7, r.top() + 7)


# ======================= OUTPUT =======================
class OutputItem(DeviceItem):
    def __init__(self, spec):
        super().__init__(spec)
        self.on = False

    def state_text(self) -> str:
        return "ON" if self.on else "OFF"

    def apply_snapshot(self, snap):
        v = bool(snap.get(self.addr, 0))
        if v != self.on:
            self.on = v
            self.update()


def _mix(a: QColor, b: QColor, k: float) -> QColor:
    k = max(0.0, min(1.0, k))
    return QColor(round(a.red() + (b.red() - a.red()) * k), round(a.green() + (b.green() - a.green()) * k),
                  round(a.blue() + (b.blue() - a.blue()) * k))


class LampItem(OutputItem):
    FAULTS = {"burnt": tr("หลอดขาด (ไม่ติด)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.bright = 0.0          # 0..1 — หลอดไส้ค่อยๆ สว่าง/หรี่ (~150 ms)

    @property
    def lit(self) -> bool:
        return self.on and self.fault != "burnt"

    def tick(self, dt):
        target = 1.0 if self.lit else 0.0
        if str(self.sprop("lamp_type")) == "incand":
            new = physics.ramp(self.bright, target, dt, 0.15, 0.15)
        else:
            new = target
        if new != self.bright:
            self.bright = new
            self.update()

    def paint_body(self, p):
        c = _color(self.prop("color", "green"))
        r = self.body_rect()
        pk.plate(p, r, 8)
        k = self.bright if str(self.sprop("lamp_type")) == "incand" else (1.0 if self.lit else 0.0)
        pk.bezel(p, QPointF(0, 0), 24, 4)
        pk.dome(p, QPointF(0, 0), 19.5, c, k)


JAM = {"jammed": tr("มอเตอร์ติดขัด (ได้ไฟแต่ไม่หมุน)")}


class MotorSim:
    """ความเร็วไต่/ลดตามแรงเฉื่อย + กระแสตามสเปก (ใช้ร่วม MotorItem / MotorRevItem)."""

    def _msim_init(self):
        self.speed = 0.0           # -1..1 (ลบ = หมุนกลับ)
        self.current_a = 0.0

    def motor_step(self, dt, direction: int):
        """direction: 1 = หน้า, -1 = กลับ, 0 = ไม่มีไฟ."""
        jam = self.fault == "jammed"
        target = 0.0 if jam else float(direction)
        if jam:
            self.speed = 0.0
        else:
            t = self.fnum("accel_s") if target != 0 else self.fnum("decel_s")
            if t <= 0:
                self.speed = target
            elif self.speed < target:
                self.speed = min(target, self.speed + dt / t)
            elif self.speed > target:
                self.speed = max(target, self.speed - dt / t)
        same = direction != 0 and self.speed * direction >= 0
        self.current_a = physics.motor_current(self.fnum("fla"), direction != 0,
                                               abs(self.speed) if same else 0.0,
                                               self.fnum("load_pct", 80), str(self.sprop("start")), jam)

    def has_nameplate(self) -> bool:
        return self.fnum("fla") > 0

    def rpm_now(self) -> float:
        return abs(self.speed) * self.fnum("rpm", 1400)

    def motor_text(self) -> str:
        if not self.has_nameplate():
            return ""
        return f"{self.rpm_now():.0f} rpm · {self.current_a:.1f} A"

    def paint_meter(self, p):
        """ป้ายเล็กเหนือมอเตอร์: รอบ + กระแส (เมื่อใส่สเปก FLA)."""
        txt = self.motor_text()
        if not txt:
            return
        r = self.body_rect()
        p.setFont(FONT)
        w = p.fontMetrics().horizontalAdvance(txt) + 12
        box = QRectF(-w / 2, r.top() - 20, w, 16)
        over = self.current_a > self.fnum("fla") * 1.05 and self.current_a > 0
        p.setPen(QPen(QColor(theme.DANGER if over else theme.BORDER), 1))
        p.setBrush(QColor(theme.BG_PANEL))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(theme.DANGER) if over else TEXT)
        p.drawText(box, Qt.AlignCenter, txt)


class MotorItem(MotorSim, OutputItem):
    FAULTS = JAM

    def __init__(self, spec):
        super().__init__(spec)
        self.angle = 0.0
        self._msim_init()

    def state_text(self):
        t = self.motor_text()
        return super().state_text() + (f" · {t}" if t else "")

    def boundingRect(self):
        r = super().boundingRect()
        return r.adjusted(0, -14, 0, 0)

    def tick(self, dt):
        self.motor_step(dt, 1 if self.on else 0)
        if self.speed:
            self.angle = (self.angle + 360 * dt * self.speed) % 360
            self.update()
        elif self.has_nameplate():
            self.update()

    def paint_body(self, p):
        on_c = QColor(theme.SIGNAL_COLORS["Y"])
        pk.motor_end(p, self.body_rect(), self.angle, self.speed != 0, ring=on_c if self.on else None)
        self.paint_meter(p)


class BuzzerItem(OutputItem):
    def __init__(self, spec):
        super().__init__(spec)
        self.phase = 0.0

    def tick(self, dt):
        if self.on:
            self.phase += dt * 6
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRoundedRect(r, 8, 8)
        c = QColor("#F2D648") if self.on else QColor("#6B7686")
        p.setPen(QPen(c, 2))
        p.setBrush(c.darker(200))
        p.drawEllipse(QPointF(-6, 0), 13, 13)
        if self.on:
            k = (math.sin(self.phase) + 1) / 2
            for i, rad in enumerate((16, 22)):
                col = QColor(c)
                col.setAlpha(int(120 + 120 * k) if i == 0 else int(60 + 120 * (1 - k)))
                p.setPen(QPen(col, 2))
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(-6 - rad + 12, -rad, 2 * rad, 2 * rad), -45 * 16, 90 * 16)


class ValveItem(OutputItem):
    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRoundedRect(r, 8, 8)
        c = QColor("#4FA3FF") if self.on else QColor("#6B7686")
        p.setPen(QPen(c, 2))
        p.setBrush(c.darker(150) if self.on else Qt.NoBrush)
        bow = QPolygonF([QPointF(-20, -10), QPointF(0, 2), QPointF(-20, 14)])
        bow2 = QPolygonF([QPointF(20, -10), QPointF(0, 2), QPointF(20, 14)])
        p.drawPolygon(bow)
        p.drawPolygon(bow2)
        p.setBrush(c if self.on else QColor("#2B323C"))
        p.drawRect(QRectF(-8, -24, 16, 12))   # คอยล์โซลินอยด์
        p.drawLine(QPointF(0, -12), QPointF(0, 2))
        if self.on:   # น้ำไหล
            p.setPen(QPen(QColor("#74C0FC"), 2, Qt.DotLine))
            p.drawLine(QPointF(-28, 2), QPointF(28, 2))


class ConveyorItem(OutputItem):
    H = 34
    Z = 0
    FAULTS = {"jammed": tr("สายพานติด (มอเตอร์ได้ไฟแต่ไม่เดิน)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.offset = 0.0
        self.travel = 0.0         # ระยะที่สายพานเดินสะสม (ใช้หมุนลูกกลิ้ง)
        self.parts: list[WorkpieceItem] = []
        self.hz10 = None          # ความถี่จาก VFD (Hz×10) ถ้าผูก addr_hz ไว้

    @property
    def W(self):  # noqa: N802
        return float(self.prop("length", 440))

    @property
    def speed(self):
        base = float(self.prop("speed", 120))
        if self.addr_of("addr_hz"):
            return base * max(0, min(int(self.hz10 or 0), 1200)) / 500.0   # 50.0 Hz = ความเร็วที่ตั้งไว้
        return base

    def apply_snapshot(self, snap):
        super().apply_snapshot(snap)
        a = self.addr_of("addr_hz")
        if a:
            self.hz10 = snap.get(a, 0)

    def state_text(self):
        s = super().state_text()
        if self.addr_of("addr_hz"):
            s += f" · {int(self.hz10 or 0) / 10:.1f} Hz"
        return s

    def body_rect(self):
        return QRectF(-self.W / 2, -self.H / 2, self.W, self.H)

    SPAWN_W = 66

    def boundingRect(self):
        r = self.body_rect()
        left = r.left() - self.SPAWN_W - 10
        return QRectF(left, r.top() - 34, r.right() + 4 - left, r.height() + 34 + cap_h())

    def spawn_rect(self) -> QRectF:
        """ปุ่ม '+ ชิ้นงาน' อยู่ซ้ายของหัวสายพาน — ชิ้นงานที่เพิ่งปล่อยจะไม่บังปุ่ม."""
        r = self.body_rect()
        return QRectF(r.left() - self.SPAWN_W - 6, -13, self.SPAWN_W, 26)

    def tick(self, dt):
        if self.on and self.fault != "jammed":
            self.offset = (self.offset + self.speed * dt) % 24
            self.travel = (self.travel + self.speed * dt) % 100000.0
            for wp in list(self.parts):
                wp.local_x += self.speed * dt
                if wp.local_x > self.W / 2 + 10:
                    self.remove_part(wp)
                else:
                    wp.place()
            self.update()

    def spawn(self):
        sc = self.scene()
        if not sc:
            return
        # ไม่ใส่ซ้อน: ต้องมีที่ว่างที่หัวสายพาน
        start = -self.W / 2 + 18
        if any(abs(wp.local_x - start) < 34 for wp in self.parts):
            return
        mode = str(self.prop("part_mode", "random"))
        material = mode if mode in ("metal", "plastic") else random.choice(("metal", "plastic"))
        wp = WorkpieceItem(self, start, material)
        sc.addItem(wp)
        self.parts.append(wp)
        wp.place()

    def remove_part(self, wp):
        if wp in self.parts:
            self.parts.remove(wp)
        if wp.scene():
            wp.scene().removeItem(wp)

    def clear_parts(self):
        for wp in list(self.parts):
            self.remove_part(wp)

    def on_press(self, pos):
        if self.spawn_rect().contains(pos):
            self.spawn()

    def itemChange(self, change, value):
        r = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            for wp in self.parts:
                wp.place()
        return r

    def paint_body(self, p):
        r = self.body_rect()
        # ปุ่มใส่ชิ้นงาน
        sr = self.spawn_rect()
        acc = QColor(theme.ACCENT)
        p.setPen(QPen(acc, 1))
        p.setBrush(pk.lin(sr, ((0, "#26506B"), (1, "#1A3346"))))
        p.drawRoundedRect(sr, sr.height() / 2, sr.height() / 2)
        p.setFont(FONT)
        p.setPen(TEXT)
        p.drawText(sr, Qt.AlignCenter, tr("+ ชิ้นงาน"))
        p.setPen(QPen(acc, 1, Qt.DotLine))     # ลูกศรชี้เข้าหัวสายพาน
        p.drawLine(QPointF(sr.right(), 0), QPointF(r.left(), 0))
        # ---- สายพานยาง (มองด้านข้าง) วนรอบลูกกลิ้งหัว-ท้าย ----
        R = self.H / 2
        pk.shadow(p, r, R, 3)
        p.setPen(QPen(pk.INK, 1.2))
        p.setBrush(pk.lin(r, ((0, "#30363F"), (0.15, "#1D2128"), (1, "#14171C"))))
        p.drawRoundedRect(r, R, R)
        # ปุ่มยาง (cleat) บนผิวสายพาน: ด้านบนเดินไปขวา ด้านล่างเดินกลับซ้าย
        p.save()
        clip = QPainterPath()
        clip.addRect(QRectF(r.left() + R, r.top() - 1, r.width() - 2 * R, r.height() + 2))
        p.setClipPath(clip)
        p.setPen(QPen(QColor("#454D59"), 2))
        x = r.left() - 24 + self.offset
        while x < r.right() + 24:
            p.drawLine(QPointF(x, r.top() + 0.5), QPointF(x, r.top() + 4))
            xb = r.right() - (x - r.left())
            p.drawLine(QPointF(xb, r.bottom() - 4), QPointF(xb, r.bottom() - 0.5))
            x += 24
        p.restore()
        # โครงอะลูมิเนียมด้านใน
        frame = QRectF(r.left() + R - 2, r.top() + 9, r.width() - 2 * R + 4, r.height() - 18)
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(pk.metal(frame, "#7C8898"))
        p.drawRect(frame)
        p.setPen(QPen(QColor(0, 0, 0, 70), 1))
        p.drawLine(QPointF(frame.left(), frame.center().y()), QPointF(frame.right(), frame.center().y()))
        # ลูกกลิ้งรองกลาง
        n = max(int((frame.width() - 40) // 70), 0)
        for i in range(1, n + 1):
            cx = frame.left() + i * frame.width() / (n + 1)
            pk.screw(p, cx, frame.center().y(), 3.2, angle=self.travel * 360 / (2 * math.pi * 3.2))
        # ลูกกลิ้งหัว-ท้าย (หมุนตามระยะที่สายพานเดิน)
        rr = R - 4
        ang = self.travel * 360 / (2 * math.pi * rr)
        for cx in (r.left() + R, r.right() - R):
            c = QPointF(cx, 0)
            p.setPen(QPen(pk.INK, 1))
            p.setBrush(pk.chrome_ring(c, rr))
            p.drawEllipse(c, rr, rr)
            p.setBrush(pk.ball(c, rr * 0.55, "#5B6573", 0.6))
            p.drawEllipse(c, rr * 0.55, rr * 0.55)
            p.save()
            p.translate(c)
            p.rotate(ang)
            p.setPen(QPen(QColor("#E6E9EE"), 1.6))
            for _ in range(3):
                p.rotate(120)
                p.drawLine(QPointF(0, -rr * 0.15), QPointF(0, -rr * 0.5))
            p.restore()
        # ไฟสถานะมอเตอร์สายพาน
        pk.led(p, r.right() - 8, r.top() - 14, self.on, theme.SIGNAL_COLORS["Y"], 4.5)


class WorkpieceItem(QGraphicsRectItem):
    SIZE = 26
    LOOK = {"metal": ("#B8C2CF", "#6B7686"), "plastic": ("#C08A4A", "#7A5426")}

    def __init__(self, conveyor: ConveyorItem, local_x: float, material: str = "plastic"):
        super().__init__(-self.SIZE / 2, -self.SIZE, self.SIZE, self.SIZE)
        self.conveyor = conveyor
        self.local_x = local_x
        self.set_material(material)
        self.setZValue(5)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_material(self, material: str):
        self.material = material if material in self.LOOK else "plastic"
        fill, edge = self.LOOK[self.material]
        self.setBrush(QBrush(QColor(fill)))
        self.setPen(QPen(QColor(edge), 2))
        # บาร์โค้ดบนชิ้นงาน: โลหะ = 1xx, พลาสติก = 2xx
        self.code = (100 if self.material == "metal" else 200) + random.randint(0, 99)
        name = tr("ชิ้นงานโลหะ") if self.material == "metal" else tr("ชิ้นงานพลาสติก")
        self.setToolTip(tr("{0} · รหัส {1}", name, self.code))

    def place(self):
        c = self.conveyor
        self.setPos(c.mapToScene(QPointF(self.local_x, -c.H / 2)))


# ======================= DISPLAY =======================
class DisplayItem(DeviceItem):
    W, H = 110, 52

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0

    def state_text(self) -> str:
        return f"{self.value} {self.prop('unit', '')}"

    def boundingRect(self):
        r = self.body_rect()
        return QRectF(min(r.left(), -60 * SCALE), r.top() - 4, max(r.width(), 120 * SCALE), r.height() + cap_h())

    def apply_snapshot(self, snap):
        v = snap.get(self.addr, 0)
        if v != self.value:
            self.value = v
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(DIM, 2))
        p.setBrush(QColor("#10151B"))
        p.drawRoundedRect(r, 6, 6)
        p.setFont(QFont("Consolas", 20, QFont.Bold))
        p.setPen(QColor(theme.color_for(self.addr)))
        p.drawText(r.adjusted(6, 0, -6, -10), Qt.AlignRight | Qt.AlignVCenter, str(self.value))
        p.setFont(FONT)
        p.setPen(TEXT_DIM)
        p.drawText(r.adjusted(6, 0, -6, -3), Qt.AlignRight | Qt.AlignBottom, tr_data(str(self.prop("unit", ""))))


# ======================= M2: อุปกรณ์เพิ่มเติม =======================
def _bit(snap, addr) -> bool:
    return bool(addr) and bool(snap.get(addr, 0))


class OverloadItem(InputItem):
    """โอเวอร์โหลดรีเลย์: คลิก = ทริป/รีเซ็ต · ทริปเองได้ถ้ามอเตอร์ที่เฝ้าทำงานนานเกิน trip_s."""
    FAULTS = {"trip": tr("ทริปค้าง (มอเตอร์ร้อนเกิน)"), **INPUT_FAULTS}

    def __init__(self, spec):
        super().__init__(spec)
        self.motor_on = False
        self.run_t = 0.0
        self.theta = 0.0           # ความร้อนสะสม (โมเดล I²t)
        self.current = 0.0
        self.note = ""

    @property
    def trip_s(self) -> float:
        return float(self.prop("trip_s", 0) or 0)

    @property
    def thermal(self) -> bool:
        return self.fnum("ir_a") > 0

    @property
    def heat_k(self) -> float:
        return min(self.theta / physics.OL_TRIP_THETA, 1.0)

    @property
    def tripped(self) -> bool:
        return self.actuated or self.fault == "trip"

    def state_text(self):
        s = tr("ทริป (TRIP)") if self.tripped else tr("ปกติ")
        extra = ""
        if self.thermal:
            extra = tr(" · กระแส {0:.1f} A / ตั้ง {1:.1f} A · ความร้อน {2:.0%}", self.current, self.fnum('ir_a'), self.heat_k)
        return tr("{0} → ส่ง {1} · PLC เห็น {2}{3}{4}", s, self.signal(), self.plc_seen, extra, self.note)

    def apply_snapshot(self, snap):
        super().apply_snapshot(snap)
        self.motor_on = _bit(snap, self.addr_of("addr_motor"))

    def _motor_current(self) -> float:
        """กระแสจากมอเตอร์ที่ address ตรงกับช่อง 'มอเตอร์ที่เฝ้า' (ถ้ามอเตอร์ใส่สเปก FLA ไว้)."""
        m = self.addr_of("addr_motor")
        v = self.panel_view()
        if m and v is not None:
            for it in v.items_by_id.values():
                if isinstance(it, MotorSim) and it.has_nameplate() and m in (it.addr_of("address"),
                                                                             it.addr_of("addr_rev")):
                    return it.current_a
        return self.fnum("ir_a") if self.motor_on else 0.0   # ไม่รู้กระแสจริง = ถือว่าเท่ากระแสตั้ง

    def tick(self, dt):
        if self.thermal:
            self.current = self._motor_current()
            self.theta = physics.ol_heat_step(self.theta, self.current, self.fnum("ir_a"),
                                              physics.ol_tau(self.sprop("trip_class")), dt)
            if not self.actuated and self.theta >= physics.OL_TRIP_THETA:
                self.set_actuated(True)
            elif (self.actuated and str(self.sprop("reset")) == "auto"
                  and self.theta < physics.OL_TRIP_THETA * 0.7):
                self.set_actuated(False)
            if self.current or self.theta > 1e-3:
                self.update()
            return
        if self.trip_s > 0 and self.motor_on and not self.actuated:
            self.run_t += dt
            if self.run_t >= self.trip_s:
                self.set_actuated(True)
            self.update()
        elif not self.motor_on and self.run_t:
            self.run_t = 0.0
            self.update()

    def on_press(self, pos):
        if self.actuated and self.thermal and self.theta >= physics.OL_TRIP_THETA * 0.7:
            self.note = tr(" · ⚠ ยังร้อนอยู่ รีเซ็ตไม่ได้ รอให้เย็นก่อน")   # เหมือนของจริง
            self.flash()
            self.refresh_tooltip()
            return
        self.note = ""
        self.run_t = 0.0
        super().on_press(pos)

    def paint_body(self, p):
        r = self.body_rect()
        pk.plate(p, r, 6, fill="#3A4350")
        p.setFont(QFont("Segoe UI", 12, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(r.left(), r.top() + 4, r.width(), 22), Qt.AlignCenter, "OL")
        # ธงทริป
        flag = QRectF(-20, 0, 40, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E03131") if self.tripped else QColor("#2F9E44"))
        p.drawRoundedRect(flag, 3, 3)
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(QColor("white"))
        p.drawText(flag, Qt.AlignCenter, "TRIP" if self.tripped else "OK")
        if self.trip_s > 0 or self.thermal:      # แถบความร้อนสะสม
            if self.thermal:
                k = self.heat_k
            else:
                k = min(self.run_t / self.trip_s, 1.0) if not self.tripped else 1.0
            bar = QRectF(-22, 20, 44, 5)
            p.setBrush(QColor("#1E242C"))
            p.drawRect(bar)
            p.setBrush(QColor("#FFA94D"))
            p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * k, bar.height()))
        self.paint_contact_tag(p)
        self.paint_led(p, r.right() - 8, r.top() + 8)


class ContactorItem(OutputItem):
    """คอนแทคเตอร์: คอยล์ = address หลัก · หน้าสัมผัสช่วย NO ส่งกลับเข้า PLC (ถ้ากำหนด)."""
    W, H = 64, 72
    FAULTS = {"coil_burn": tr("คอยล์ขาด (ไม่ดูด หน้าสัมผัสไม่ต่อ)"), "aux_fail": tr("หน้าสัมผัสช่วยเสีย (ไม่ส่งกลับ)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.aux = False
        self._pick_t = 0.0
        self._picked = False

    @property
    def pulled(self) -> bool:
        """คอนแทคเตอร์ดูดจริงไหม (คอยล์ได้ไฟ คอยล์ไม่ขาด และผ่านเวลาดูดแล้ว)."""
        return self.on and self.fault != "coil_burn" and (self.fnum("pickup_ms") <= 0 or self._picked)

    def tick(self, dt):
        if self.on and not self._picked and self.fnum("pickup_ms") > 0:
            self._pick_t += dt
            if self._pick_t >= self.fnum("pickup_ms") / 1000.0 - 1e-9:
                self._picked = True
                self._sync_aux()
                self.update()

    def _sync_aux(self):
        v = self.pulled and self.fault != "aux_fail"
        if v != self.aux:
            self.aux = v
            self.emit_bit("addr_aux", int(v))

    def state_text(self):
        return tr("คอยล์ {0} · {1} · aux={2}", 'ON' if self.on else 'OFF', 'ดูด' if self.pulled else 'ปล่อย', int(self.aux))

    def apply_snapshot(self, snap):
        super().apply_snapshot(snap)
        if not self.on:
            self._picked, self._pick_t = False, 0.0
        self._sync_aux()

    def on_fault_changed(self):
        self._sync_aux()

    def input_signals(self):
        a = self.addr_of("addr_aux")
        return [(a, int(self.aux), False)] if a else []

    def paint_body(self, p):
        r = self.body_rect()
        on_c = QColor(theme.SIGNAL_COLORS["Y"])
        pk.plate(p, r, 4, fill="#BCC3CD", edge="#E8ECF1")
        if self.pulled:
            p.setPen(QPen(on_c, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 5, 5)
        # ขั้วต่อสายด้านบน (1 3 5) / ด้านล่าง (2 4 6)
        tiny = QFont("Segoe UI", 5, QFont.Bold)
        for y, nums in ((r.top() + 3, "135"), (r.bottom() - 16, "246")):
            strip = QRectF(r.left() + 4, y, r.width() - 8, 13)
            p.setPen(QPen(pk.INK, 0.8))
            p.setBrush(pk.lin(strip, ((0, "#3A414B"), (1, "#22272E"))))
            p.drawRoundedRect(strip, 2, 2)
            for x, n in zip((-18, 0, 18), nums):
                pk.screw(p, x, strip.center().y(), 3.6, angle=30)
                p.setFont(tiny)
                p.setPen(QColor("#C7CED8"))
                p.drawText(QRectF(x + 4, strip.top(), 8, 7), Qt.AlignCenter, n)
        # ป้ายรุ่น
        pk.nameplate(p, QRectF(-26, r.top() + 20, 30, 12), "MC 9A", "AC-3 4 kW")
        # สัญลักษณ์หน้าสัมผัสหลัก (เปิด/ปิดตามการดูด)
        p.setPen(QPen(QColor("#2B323C"), 1.4))
        for x in (-22, -12, -2):
            y0 = r.top() + 37
            p.drawLine(QPointF(x, y0), QPointF(x, y0 + 4))
            p.drawLine(QPointF(x, y0 + 12), QPointF(x, y0 + 16))
            if self.pulled:
                p.drawLine(QPointF(x, y0 + 4), QPointF(x, y0 + 12))
            else:
                p.drawLine(QPointF(x, y0 + 4), QPointF(x + 4, y0 + 11))
        # ไฟคอยล์ + ตัวกดทดสอบ (ยุบลงเมื่อดูด)
        pk.led(p, 18, r.top() + 23, self.on, theme.SIGNAL_COLORS["Y"], 3)
        win = QRectF(12, r.top() + 30, 12, 22)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(QColor("#1A1E24"))
        p.drawRect(win)
        slider = QRectF(win.left() + 2, win.top() + (10 if self.pulled else 2), win.width() - 4, 10)
        p.setBrush(pk.lin(slider, ((0, "#FFB347"), (1, "#D9781A"))))
        p.drawRoundedRect(slider, 1.5, 1.5)


class TrafficItem(OutputItem):
    W, H = 46, 116
    COLORS = (("address", "#FF5A5A"), ("addr_yellow", "#F2D648"), ("addr_green", "#5EE36A"))

    def __init__(self, spec):
        super().__init__(spec)
        self.lights = [False, False, False]

    def state_text(self):
        names = (tr("แดง"), tr("เหลือง"), tr("เขียว"))
        on = [n for n, v in zip(names, self.lights) if v]
        return tr("ติด: ") + (", ".join(on) if on else "-")

    def apply_snapshot(self, snap):
        v = [_bit(snap, self.addr_of(prop)) for prop, _ in self.COLORS]
        if v != self.lights:
            self.lights = v
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(QColor("#10151B"), 2))
        p.setBrush(QColor("#1B2027"))
        p.drawRoundedRect(r, 8, 8)
        for i, ((_, col), on) in enumerate(zip(self.COLORS, self.lights)):
            c = QColor(col)
            cy = r.top() + 20 + i * 38
            if on:
                g = QColor(c)
                g.setAlpha(80)
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(0, cy), 19, 19)
            p.setPen(QPen(c.darker(200), 2))
            p.setBrush(c if on else c.darker(330))
            p.drawEllipse(QPointF(0, cy), 14, 14)


class CylinderItem(DeviceItem):
    """กระบอกสูบนิวแมติก + วาล์ว 5/2 / 5/3 + รีดสวิตช์ a0/a1 (หรือกระบอกทางเดียวสปริงคืน + วาล์ว 3/2).

    valve: single = 5/2 สปริงคืน, double = 5/2 ค้างตำแหน่ง,
           c_closed / c_exhaust / c_pressure = 5/3 ตำแหน่งกลาง ปิด / ระบาย / จ่ายลม
    """
    W, H = 280, 70
    BARREL = (-30.0, 50.0)
    ROD = 84
    CENTER = ("c_closed", "c_exhaust", "c_pressure")
    CREEP = 4.0              # ตำแหน่งกลาง exhaust/pressure: เคลื่อนช้ากว่าปกติกี่เท่า
    FAULTS = {"no_air": tr("ลมไม่มา (กระบอกสูบไม่ขยับ)"), "reed_a0": tr("รีดสวิตช์ a0 เสีย (ส่ง 0 ตลอด)"),
              "reed_a1": tr("รีดสวิตช์ a1 เสีย (ส่ง 0 ตลอด)"), "slow": tr("ลมรั่ว (เคลื่อนช้ากว่าปกติ 4 เท่า)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.pos_k = 0.0         # 0 = หดสุด, 1 = ยื่นสุด
        self.sol_a = self.sol_b = False
        self.spool = "ret"       # ตำแหน่งแกนวาล์ว: ext = จ่ายลมด้านยื่น, ret = ด้านหด, mid = ตำแหน่งกลาง (5/3)
        self.sol_conflict = False    # 5/3 ถูกสั่ง A และ B พร้อมกัน
        self.reed = {"addr_ret": True, "addr_ext": False}

    @property
    def valve_kind(self) -> str:
        return str(self.prop("valve", "single") or "single")

    @property
    def double(self) -> bool:
        return self.valve_kind == "double"

    @property
    def three_pos(self) -> bool:
        return self.valve_kind in self.CENTER and not self.single_acting

    @property
    def single_acting(self) -> bool:
        return str(self.prop("actuation", "double")) == "single"

    @property
    def spool_ext(self) -> bool:
        return self.spool == "ext"

    def air_bar(self) -> float:
        """ความดันลมที่ได้: จากปั๊มลมที่ผูกไว้ (ถ้ามี) หรือค่าที่ตั้ง."""
        comp = self.linked("link_air")
        if comp is not None and hasattr(comp, "bar"):
            return comp.bar
        return self.fnum("pressure_bar", 6.0)

    def stroke_time(self, extend: bool) -> float | None:
        """เวลาเคลื่อนสุดระยะ (s) — None = ไม่ขยับ (ลมต่ำกว่า 2 bar / โหลดหนักเกิน)."""
        bar = self.air_bar()
        if str(self.sprop("timing")) == "spec":
            return physics.cylinder_stroke_time(self.fnum("bore_mm", 32), self.fnum("stroke_mm", 100), bar,
                                                self.fnum("load_kg"), extend)
        if bar < physics.MIN_BAR:
            return None
        return max(float(self.prop("stroke_s", 1.0) or 1.0), 0.05)

    def state_text(self):
        st = tr("ยื่นสุด") if self.pos_k >= 0.98 else tr("หดสุด") if self.pos_k <= 0.02 else tr("ตำแหน่ง {0:.0%}", self.pos_k)
        s = f"{st} · a0={int(self.reed['addr_ret'])} a1={int(self.reed['addr_ext'])}"
        if self.sol_conflict:
            s += tr(" · ⚠ สั่งโซลินอยด์ A และ B พร้อมกัน (วาล์วค้างกลาง)")
        elif self.three_pos and self.spool == "mid":
            s += {"c_closed": tr(" · วาล์วกลาง: ปิดทุกพอร์ต (ค้าง)"), "c_exhaust": tr(" · วาล์วกลาง: ระบายลม (ลูกสูบลอย)"),
                  "c_pressure": tr(" · วาล์วกลาง: จ่ายลมสองฝั่ง (คืบออก)")}[self.valve_kind]
        bar = self.air_bar()
        if bar < physics.MIN_BAR:
            s += tr(" · ⚠ ลมไม่พอ ({0:.1f} bar)", bar)
        elif str(self.sprop("timing")) == "spec":
            t = self.stroke_time(True)
            f = physics.cylinder_force(self.fnum("bore_mm", 32), bar)
            s += tr(" · แรงดัน {0:.0f} N · ยื่น {1}", f, 'ไม่ขึ้น (โหลดหนักเกิน)' if t is None else f'{t:.2f} s')
        return s

    def apply_snapshot(self, snap):
        a, b = _bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_sol_b"))
        if (a, b) != (self.sol_a, self.sol_b):
            self.sol_a, self.sol_b = a, b
            self.update()

    def input_signals(self):
        return [(self.addr_of(k), int(v), False) for k, v in self.reed.items() if self.addr_of(k)]

    def _update_spool(self):
        old = (self.spool, self.sol_conflict)
        self.sol_conflict = False
        if self.single_acting or self.valve_kind == "single":   # สปริงดันแกนวาล์วกลับ
            self.spool = "ext" if self.sol_a else "ret"
        elif self.double:      # 5/2 สองโซลินอยด์: ค้างตำแหน่งเดิมถ้าไม่มี/มีทั้งสองสัญญาณ
            if self.sol_a and not self.sol_b:
                self.spool = "ext"
            elif self.sol_b and not self.sol_a:
                self.spool = "ret"
        else:                  # 5/3: สปริงสองข้างดันกลับกลาง; สั่งพร้อมกัน = แรงหักล้าง ค้างกลาง
            self.sol_conflict = self.sol_a and self.sol_b
            self.spool = "ext" if self.sol_a and not self.sol_b else "ret" if self.sol_b and not self.sol_a else "mid"
        if (self.spool, self.sol_conflict) != old:
            self.update()

    def _motion(self) -> tuple[float, float | None, bool]:
        """(เป้าหมาย, เวลาเคลื่อนสุดระยะ, ใช้ลม) ตามตำแหน่งวาล์ว — เวลา None = ไม่ขยับ."""
        air_ok = self.fault != "no_air"
        if self.spool == "ext":
            return 1.0, (self.stroke_time(True) if air_ok else None), True
        if self.spool == "ret":
            if self.single_acting:     # สปริงในกระบอกดันกลับ ไม่ต้องใช้ลม
                return 0.0, max(float(self.prop("stroke_s", 1.0) or 1.0), 0.05), False
            return 0.0, (self.stroke_time(False) if air_ok else None), True
        base = max(float(self.prop("stroke_s", 1.0) or 1.0), 0.05) * self.CREEP
        kind = self.valve_kind
        if kind == "c_exhaust" and self.fnum("load_kg") > 0:     # ลูกสูบลอย โหลดดึงกลับ
            return 0.0, base, False
        if kind == "c_pressure" and air_ok and self.air_bar() >= physics.MIN_BAR:
            return 1.0, base, True                                 # พื้นที่หัวลูกสูบ > ฝั่งก้าน → คืบออก
        return self.pos_k, None, False                             # กลางปิด: ค้างกับที่

    def tick(self, dt):
        self._update_spool()
        target, t, uses_air = self._motion()
        if target != self.pos_k and t is not None:
            step = dt / t
            if self.fault == "slow":
                step /= 4
            old = self.pos_k
            self.pos_k = min(self.pos_k + step, target) if target > self.pos_k else max(self.pos_k - step, target)
            comp = self.linked("link_air")
            if uses_air and comp is not None and hasattr(comp, "consume"):   # กินลม: ปริมาตรกระบอก × ความดันสัมบูรณ์
                area = math.pi * (self.fnum("bore_mm", 32) / 2000.0) ** 2
                vol_l = area * self.fnum("stroke_mm", 100) / 1000.0 * abs(self.pos_k - old) * 1000.0
                comp.consume(vol_l * (comp.bar + 1.0))
            self.update()
        new = {"addr_ret": self.pos_k <= 0.02 and self.fault != "reed_a0",
               "addr_ext": self.pos_k >= 0.98 and self.fault != "reed_a1"}
        for k, v in new.items():
            if v != self.reed[k]:
                self.reed[k] = v
                self.emit_bit(k, int(v))
                self.update()

    @staticmethod
    def _spring(p, rect: QRectF, n=6, amp=6):
        p.setPen(QPen(QColor("#9AA4B2"), 1.5))
        p.setBrush(Qt.NoBrush)
        cy = rect.center().y()
        path = QPainterPath(QPointF(rect.left(), cy))
        for i in range(1, n + 1):
            path.lineTo(rect.left() + i * rect.width() / n, cy - amp if i % 2 else cy + amp)
        p.drawPath(path)

    def _solenoid(self, p, rect: QRectF, on: bool, on_c: QColor):
        p.setPen(QPen(on_c if on else QColor("#9AA4B2"), 1.5))
        p.setBrush(on_c.darker(200) if on else QColor("#1E242C"))
        p.drawRect(rect)
        p.drawLine(rect.topLeft(), rect.bottomRight())

    def _paint_valve(self, p, vx: float, on_c: QColor):
        """สัญลักษณ์วาล์วตามมาตรฐาน ISO 1219 (ย่อ): ช่องที่แกนวาล์วอยู่ระบายสีน้ำเงิน."""
        line = QColor("#C7CED8")

        def box(b: QRectF, active: bool):
            p.setPen(QPen(line, 1.5))
            p.setBrush(QColor("#22384D") if active else QColor("#2B323C"))
            p.drawRect(b)
            p.setPen(QPen(line, 1.2))

        def cross(b):      # ทางไขว้ (หด)
            p.drawLine(b.bottomLeft() + QPointF(5, -4), b.topRight() + QPointF(-5, 4))
            p.drawLine(b.topLeft() + QPointF(5, 4), b.bottomRight() + QPointF(-5, -4))

        def straight(b):   # ทางตรง (ยื่น)
            p.drawLine(QPointF(b.left() + 6, b.bottom() - 4), QPointF(b.left() + 6, b.top() + 4))
            p.drawLine(QPointF(b.right() - 6, b.top() + 4), QPointF(b.right() - 6, b.bottom() - 4))

        sa = QRectF(vx - 16, -10, 16, 20)
        right = QRectF(vx + 52, -10, 16, 20)
        if self.three_pos:
            w = 52 / 3
            bs = [QRectF(vx + i * w, -14, w, 28) for i in range(3)]
            for b, st in zip(bs, ("ext", "mid", "ret")):
                box(b, self.spool == st)
            straight(bs[0])
            cross(bs[2])
            m, kind = bs[1], self.valve_kind
            cx1, cx2 = m.left() + 5, m.right() - 5
            if kind == "c_closed":       # ปิดทุกพอร์ต: สัญลักษณ์ ⊤ ⊥
                for cx in (cx1, cx2):
                    p.drawLine(QPointF(cx, m.top() + 3), QPointF(cx, m.top() + 9))
                    p.drawLine(QPointF(cx - 3, m.top() + 9), QPointF(cx + 3, m.top() + 9))
                    p.drawLine(QPointF(cx, m.bottom() - 3), QPointF(cx, m.bottom() - 9))
                    p.drawLine(QPointF(cx - 3, m.bottom() - 9), QPointF(cx + 3, m.bottom() - 9))
            elif kind == "c_exhaust":    # พอร์ตกระบอกต่อลงระบาย
                for cx in (cx1, cx2):
                    p.drawLine(QPointF(cx, m.top() + 3), QPointF(cx, m.bottom() - 3))
            else:                        # จ่ายลมเข้าทั้งสองพอร์ต
                p.drawLine(QPointF(m.center().x(), m.bottom() - 3), QPointF(m.center().x(), m.top() + 8))
                p.drawLine(QPointF(cx1, m.top() + 8), QPointF(cx2, m.top() + 8))
                for cx in (cx1, cx2):
                    p.drawLine(QPointF(cx, m.top() + 8), QPointF(cx, m.top() + 3))
            self._solenoid(p, QRectF(sa.left(), -10, 16, 13), self.sol_a, on_c)
            self._solenoid(p, QRectF(right.left(), -10, 16, 13), self.sol_b, on_c)
            self._spring(p, QRectF(sa.left(), 6, 16, 6), amp=3)     # สปริงจัดกลางสองข้าง
            self._spring(p, QRectF(right.left(), 6, 16, 6), amp=3)
            if self.sol_conflict:
                p.setPen(QPen(QColor("#FF5A5A"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(vx - 2, -16, 56, 32))
            return
        bs = [QRectF(vx, -14, 26, 28), QRectF(vx + 26, -14, 26, 28)]
        for i, b in enumerate(bs):
            box(b, (i == 0) == self.spool_ext)
        if self.single_acting:           # 3/2: ช่องซ้ายจ่ายลม ช่องขวาระบาย
            p.drawLine(QPointF(bs[0].left() + 6, bs[0].bottom() - 4), QPointF(bs[0].left() + 6, bs[0].top() + 4))
            b = bs[1]
            p.drawLine(QPointF(b.left() + 6, b.top() + 4), QPointF(b.right() - 6, b.bottom() - 4))
            p.drawLine(QPointF(b.left() + 3, b.bottom() - 9), QPointF(b.left() + 9, b.bottom() - 9))
        else:
            straight(bs[0])
            cross(bs[1])
        self._solenoid(p, sa, self.sol_a, on_c)
        if self.double and not self.single_acting:
            self._solenoid(p, right, self.sol_b, on_c)
        else:
            self._spring(p, right)

    def paint_body(self, p):
        r = self.body_rect()
        on_c = QColor(theme.SIGNAL_COLORS["Y"])
        # ---- วาล์ว 5/2 · 5/3 · 3/2 (ใช้พื้นที่กว้าง 52 px เท่าเดิม) ----
        vx = r.left() + 22
        self._paint_valve(p, vx, on_c)
        # ท่อลม
        x0, x1 = self.BARREL
        p.setPen(QPen(QColor("#4FA3FF"), 1.5))
        p.drawLine(QPointF(vx + 8, -14), QPointF(vx + 8, -24))
        p.drawLine(QPointF(vx + 8, -24), QPointF(x0 + 6, -24))
        p.drawLine(QPointF(x0 + 6, -24), QPointF(x0 + 6, -16))
        if not self.single_acting:      # กระบอกทางเดียว: ฝั่งก้านเป็นรูระบาย ไม่มีท่อ
            p.drawLine(QPointF(vx + 44, -14), QPointF(vx + 44, -28))
            p.drawLine(QPointF(vx + 44, -28), QPointF(x1 - 6, -28))
            p.drawLine(QPointF(x1 - 6, -28), QPointF(x1 - 6, -16))
        # ---- กระบอกสูบ (ท่อโลหะเงา + ฝาท้าย/ฝาหน้า + พอร์ตลม) ----
        barrel = QRectF(x0, -14, x1 - x0, 28)
        pk.shadow(p, barrel, 3, 3)
        px = x0 + 4 + self.pos_k * (x1 - x0 - 16)
        rod_end = px + 8 + self.ROD
        rod = QRectF(px + 8, -4, rod_end - px - 8, 8)
        p.setPen(QPen(pk.INK, 0.8))
        p.setBrush(pk.metal(rod, "#D5DBE3"))       # ก้านสูบโครเมียม
        p.drawRect(rod)
        clevis = QRectF(rod_end, -9, 9, 18)
        p.setBrush(pk.metal(clevis, "#7D8796"))
        p.drawRoundedRect(clevis, 2, 2)
        p.setBrush(pk.metal(barrel, "#B7C0CC"))
        p.drawRect(barrel)
        p.save()                                     # ลูกสูบมองผ่านท่อ (โปร่งแสงเล็กน้อย)
        p.setOpacity(0.55)
        p.setBrush(pk.metal(QRectF(px, -12, 8, 24), "#3F4753"))
        p.drawRect(QRectF(px, -12, 8, 24))
        p.restore()
        for cx in (x0, x1):                          # ฝาปิดหัว-ท้าย
            cap = QRectF(cx - 5, -17, 10, 34)
            p.setBrush(pk.metal(cap, "#6D7786"))
            p.drawRoundedRect(cap, 1.5, 1.5)
            pk.screw(p, cx, -12, 1.6)
            pk.screw(p, cx, 12, 1.6)
        if self.single_acting:                       # สปริงคืนในฝั่งก้านสูบ
            p.setPen(QPen(QColor("#5B6573"), 1.2))
            p.setBrush(Qt.NoBrush)
            sx0, sx1 = px + 9, x1 - 6
            path = QPainterPath(QPointF(sx0, 0))
            n = 10
            for i in range(1, n + 1):
                path.lineTo(sx0 + i * (sx1 - sx0) / n, -9 if i % 2 else 9)
            p.drawPath(path)
            p.setPen(QPen(pk.INK, 0.8))
        ports = ((x0 + 6, self.spool == "ext" or (self.spool == "mid" and self.valve_kind == "c_pressure")),)
        if not self.single_acting:
            ports += ((x1 - 6, self.spool == "ret" or (self.spool == "mid" and self.valve_kind == "c_pressure")),)
        for cx, on in ports:                         # พอร์ตลมแบบ push-in (สีฟ้า = มีลมเข้า)
            port = QRectF(cx - 4, -21, 8, 5)
            p.setBrush(QColor("#2F7DE1") if on else QColor("#4B5563"))
            p.drawRoundedRect(port, 1.5, 1.5)
        # รีดสวิตช์ a0 / a1 (ตัวเซนเซอร์ติดท่อ + LED)
        for k, x, name in (("addr_ret", x0 + 10, "a0"), ("addr_ext", x1 - 10, "a1")):
            on = self.reed[k]
            body = QRectF(x - 8, 15, 16, 7)
            p.setPen(QPen(pk.INK, 0.8))
            p.setBrush(pk.lin(body, ((0, "#3A424E"), (1, "#1C2129"))))
            p.drawRoundedRect(body, 2, 2)
            pk.led(p, x + 4, 18.5, on, theme.SIGNAL_COLORS["X"], 2.2)
            p.setFont(FONT)
            p.setPen(TEXT_DIM)
            p.drawText(QRectF(x - 14, 23, 28, 12), Qt.AlignCenter, name)



class TankItem(DeviceItem):
    """ถังน้ำ: ปั๊มเติม (address หลัก), วาล์วปล่อย, เซนเซอร์ระดับสูง/ต่ำ · คลิก = เปิด/ปิดก๊อกใช้น้ำ."""
    W, H = 130, 160
    FAULTS = {"pump_fail": tr("ปั๊มเสีย (ได้ไฟแต่ไม่สูบ)"), "high_fail": tr("เซนเซอร์ระดับสูงเสีย (ส่ง 0 ตลอด)"),
              "low_fail": tr("เซนเซอร์ระดับต่ำเสีย (ส่ง 0 ตลอด)"), "leak": tr("ถังรั่ว (น้ำลดเองช้าๆ)")}

    def __init__(self, spec):
        super().__init__(spec)
        self.level = float(self.prop("level0", 30))
        self.pump = self.drain = False
        self.tap = False
        self.wave = 0.0            # เฟสคลื่นผิวน้ำ (ภาพเท่านั้น)
        self.sens = {"addr_high": False, "addr_low": False}
        self._update_sensors(emit=False)

    def state_text(self):
        return (tr("ระดับน้ำ {0:.0f}% · ปั๊ม {1} · ก๊อก {2}", self.level, 'ON' if self.pump else 'OFF', 'เปิด' if self.tap else 'ปิด'))

    def apply_snapshot(self, snap):
        pump, drain = _bit(snap, self.addr_of("address")), _bit(snap, self.addr_of("addr_drain"))
        if (pump, drain) != (self.pump, self.drain):
            self.pump, self.drain = pump, drain
            self.update()

    def input_signals(self):
        return [(self.addr_of(k), int(v), False) for k, v in self.sens.items() if self.addr_of(k)]

    def _update_sensors(self, emit=True):
        new = {"addr_high": self.level >= float(self.prop("high_pct", 80)) and self.fault != "high_fail",
               "addr_low": self.level >= float(self.prop("low_pct", 20)) and self.fault != "low_fail"}
        for k, v in new.items():
            if v != self.sens[k]:
                self.sens[k] = v
                if emit:
                    self.emit_bit(k, int(v))

    def rates(self) -> tuple[float, float]:
        """อัตราเติม/ปล่อย (%/s) — โหมดสเปก: คำนวณจาก L/min ÷ ความจุถัง."""
        if str(self.sprop("rate_mode")) == "spec":
            vol = self.fnum("volume_l", 200)
            return (physics.lpm_to_pct_s(self.fnum("pump_lpm", 20), vol),
                    physics.lpm_to_pct_s(self.fnum("drain_lpm", 15), vol))
        return float(self.prop("fill_rate", 12)), float(self.prop("drain_rate", 8))

    def tick(self, dt):
        self.wave = (self.wave + dt * 4.0) % (2 * math.pi)
        d = 0.0
        fill, drain = self.rates()
        if self.pump and self.fault != "pump_fail":
            d += fill * dt
        if self.drain or self.tap:
            d -= drain * dt
        if self.fault == "leak":
            d -= 2.0 * dt
        if d:
            old = self.level
            self.level = max(0.0, min(100.0, self.level + d))
            if self.level != old:
                self._update_sensors()
        if d or self.pump or self.drain or self.tap:
            self.update()

    def on_fault_changed(self):
        self._update_sensors()

    def on_press(self, pos):
        self.tap = not self.tap
        self.update()

    def paint_body(self, p):
        r = self.body_rect()
        tank = QRectF(r.left() + 22, r.top() + 22, r.width() - 44, r.height() - 44)
        # ตัวถังสแตนเลส (มองทะลุด้านใน)
        pk.shadow(p, tank, 6, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(pk.lin(tank, ((0, "#1A2029"), (0.5, "#232B36"), (1, "#151A21")), vertical=False))
        p.drawRoundedRect(tank, 6, 6)
        # น้ำ + ผิวน้ำเป็นคลื่น (คลื่นแรงขึ้นตอนเติม/ปล่อย)
        h = tank.height() * self.level / 100
        if h > 0.5:
            busy = self.pump or self.drain or self.tap
            amp = min(2.5 if busy else 0.8, h / 2)
            top = tank.bottom() - h
            water = QPainterPath(QPointF(tank.left(), tank.bottom()))
            n = 24
            for i in range(n + 1):
                x = tank.left() + tank.width() * i / n
                y = top + amp * math.sin(self.wave + i * 0.7)
                water.lineTo(QPointF(x, y))
            water.lineTo(QPointF(tank.right(), tank.bottom()))
            water.closeSubpath()
            clip = QPainterPath()
            clip.addRoundedRect(tank, 6, 6)
            p.save()
            p.setClipPath(clip)
            p.setBrush(pk.lin(QRectF(tank.left(), top, tank.width(), h),
                              ((0, QColor(110, 190, 255, 210)), (1, QColor(30, 100, 200, 220)))))
            p.drawPath(water)
            p.setPen(QPen(QColor(220, 240, 255, 160), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(water)
            p.restore()
        # ผนังถังโลหะ + แถบสะท้อนแสง
        p.setPen(QPen(pk.INK, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(tank, 6, 6)
        for side in (QRectF(tank.left() - 3, tank.top(), 6, tank.height()),
                     QRectF(tank.right() - 3, tank.top(), 6, tank.height())):
            p.setBrush(pk.metal(side, "#AEB8C5", vertical=False))
            p.drawRect(side)
        lid = QRectF(tank.left() - 5, tank.top() - 4, tank.width() + 10, 6)
        p.setBrush(pk.metal(lid, "#9AA4B2"))
        p.drawRoundedRect(lid, 2, 2)
        p.setPen(QPen(QColor(255, 255, 255, 35), 4))
        p.drawLine(QPointF(tank.left() + 9, tank.top() + 6), QPointF(tank.left() + 9, tank.bottom() - 6))
        p.setFont(FONT_B)
        p.setPen(TEXT)
        p.drawText(tank, Qt.AlignCenter, f"{self.level:.0f}%")
        # เซนเซอร์ระดับ (ด้านขวา)
        for k, pct_key, name in (("addr_high", "high_pct", "H"), ("addr_low", "low_pct", "L")):
            y = tank.bottom() - tank.height() * float(self.prop(pct_key, 50)) / 100
            p.setPen(QPen(QColor("#9AA4B2"), 1, Qt.DashLine))
            p.drawLine(QPointF(tank.left(), y), QPointF(tank.right() + 6, y))
            p.setPen(QPen(QColor("#10151B"), 1))
            p.setBrush(QColor(theme.SIGNAL_COLORS["X"]) if self.sens[k] else QColor("#3A4048"))
            p.drawEllipse(QPointF(tank.right() + 11, y), 5, 5)
            p.setFont(FONT)
            p.setPen(TEXT_DIM)
            p.drawText(QRectF(tank.right() + 17, y - 7, 14, 14), Qt.AlignCenter, name)
        # ปั๊ม (ซ้ายบน) + ท่อน้ำเข้า
        on_c = QColor(theme.SIGNAL_COLORS["Y"])
        pc = QPointF(r.left() + 12, r.top() + 12)
        pk.glow(p, pc, 18, on_c, 0.8 if self.pump else 0)
        p.setPen(QPen(on_c if self.pump else pk.INK, 1.5))
        p.setBrush(pk.ball(pc, 10, "#3F6E9E" if self.pump else "#3A424E", 0.6))
        p.drawEllipse(pc, 10, 10)
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(pc.x() - 10, pc.y() - 10, 20, 20), Qt.AlignCenter, "P")
        p.setPen(QPen(QColor("#4FA3FF") if self.pump else QColor("#5F6B7A"), 3))
        p.drawLine(QPointF(pc.x() + 10, pc.y()), QPointF(tank.left() + 16, pc.y()))
        p.drawLine(QPointF(tank.left() + 16, pc.y()), QPointF(tank.left() + 16, tank.top() + 6))
        # วาล์วปล่อย (ล่างขวา) + ก๊อก
        vy = r.bottom() - 12
        out_on = self.drain or self.tap
        p.setPen(QPen(QColor("#4FA3FF") if out_on else QColor("#5F6B7A"), 3))
        p.drawLine(QPointF(tank.right() - 16, tank.bottom()), QPointF(tank.right() - 16, vy))
        p.drawLine(QPointF(tank.right() - 16, vy), QPointF(r.right() - 4, vy))
        vb = QRectF(tank.right() - 4, vy - 7, 14, 14)
        p.setPen(QPen(on_c if self.drain else QColor("#9AA4B2"), 1.5))
        p.setBrush(on_c.darker(220) if self.drain else QColor("#1E242C"))
        p.drawPolygon(QPolygonF([vb.topLeft(), vb.bottomRight(), vb.topRight(), vb.bottomLeft()]))
        p.setFont(FONT)
        p.setPen(QColor("#74C0FC") if self.tap else TEXT_DIM)
        p.drawText(QRectF(r.left(), r.bottom() - 18, 70, 14), Qt.AlignLeft, tr("ก๊อก: เปิด") if self.tap else tr("คลิก = ก๊อก"))


SEGMENTS = {  # a b c d e f g
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
    "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
}


class SevenSegItem(DeviceItem):
    H = 64

    def __init__(self, spec):
        super().__init__(spec)
        self.value = 0

    @property
    def digits(self) -> int:
        return max(1, min(6, int(self.prop("digits", 4) or 4)))

    @property
    def W(self):  # noqa: N802
        return self.digits * 30 + 16

    def state_text(self):
        return str(self.value)

    def apply_snapshot(self, snap):
        v = int(snap.get(self.addr, 0) or 0)
        if v != self.value:
            self.value = v
            self.update()

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(DIM, 2))
        p.setBrush(QColor("#0B0E12"))
        p.drawRoundedRect(r, 6, 6)
        n = self.digits
        txt = str(self.value)
        if len(txt) > n:
            txt = "-" * n            # เกินจำนวนหลัก
        txt = txt.rjust(n)
        on = QColor("#FF4D4D")
        off = QColor(255, 77, 77, 28)
        for i, ch in enumerate(txt):
            x = r.left() + 10 + i * 30
            self._digit(p, x, r.top() + 10, SEGMENTS.get(ch, ""), on, off)

    @staticmethod
    def _digit(p, x, y, segs, on, off):
        w, h, t = 20, 44, 4
        geo = {
            "a": QRectF(x + t, y, w - 2 * t, t), "g": QRectF(x + t, y + h / 2 - t / 2, w - 2 * t, t),
            "d": QRectF(x + t, y + h - t, w - 2 * t, t),
            "f": QRectF(x, y + t, t, h / 2 - t * 1.5), "b": QRectF(x + w - t, y + t, t, h / 2 - t * 1.5),
            "e": QRectF(x, y + h / 2 + t / 2, t, h / 2 - t * 1.5), "c": QRectF(x + w - t, y + h / 2 + t / 2, t, h / 2 - t * 1.5),
        }
        p.setPen(Qt.NoPen)
        for s, rc in geo.items():
            p.setBrush(on if s in segs else off)
            p.drawRoundedRect(rc, 1.5, 1.5)


class SetValueItem(DeviceItem):
    """ตัวตั้งค่า (Thumbwheel): ปุ่ม −10 −1 +1 +10 หรือคลิกตัวเลขเพื่อพิมพ์ — เขียนค่าลง D."""
    W, H = 180, 56
    BTN = (("−10", -10), ("−1", -1), ("+1", 1), ("+10", 10))

    def __init__(self, spec):
        super().__init__(spec)
        self.value = int(self.prop("value", 0) or 0)
        self.plc_value = None

    def state_text(self):
        seen = "-" if self.plc_value is None else self.plc_value
        return tr("ตั้งไว้ {0} · PLC เห็น {1}", self.value, seen)

    def input_signals(self):
        a = self.addr_of("address")
        return [(a, self.value, True)] if a else []

    def apply_snapshot(self, snap):
        a = self.addr_of("address")
        v = snap.get(a) if a else None
        if v != self.plc_value:
            self.plc_value = v
            self.update()

    def _btn_rects(self):
        r = self.body_rect()
        bw = 30
        return [QRectF(r.left() + 4, r.top() + 14, bw, 28), QRectF(r.left() + 4 + bw, r.top() + 14, bw, 28),
                QRectF(r.right() - 4 - 2 * bw, r.top() + 14, bw, 28), QRectF(r.right() - 4 - bw, r.top() + 14, bw, 28)]

    def set_value(self, v: int):
        lo, hi = int(self.prop("min", 0)), int(self.prop("max", 9999))
        v = max(lo, min(hi, int(v)))
        if v != self.value:
            self.value = v
            self.spec.props["value"] = v
            a = self.addr_of("address")
            if a:
                self.request_write_word.emit(a, v)
            self.update()

    def on_press(self, pos):
        for (txt, d), rc in zip(self.BTN, self._btn_rects()):
            if rc.contains(pos):
                self.set_value(self.value + d)
                return
        from PySide6.QtWidgets import QInputDialog
        v, ok = QInputDialog.getInt(None, tr("ตั้งค่า"), f"{self.shown_label} → {self.addr}", self.value,
                                    int(self.prop("min", 0)), int(self.prop("max", 9999)))
        if ok:
            self.set_value(v)

    def paint_body(self, p):
        r = self.body_rect()
        p.setPen(QPen(DIM, 2))
        p.setBrush(QColor("#2B323C"))
        p.drawRoundedRect(r, 6, 6)
        for (txt, _), rc in zip(self.BTN, self._btn_rects()):
            p.setPen(QPen(QColor("#10151B"), 1))
            p.setBrush(QColor("#3B4453"))
            p.drawRoundedRect(rc.adjusted(1, 0, -1, 0), 3, 3)
            p.setFont(FONT)
            p.setPen(TEXT)
            p.drawText(rc, Qt.AlignCenter, txt)
        mid = QRectF(r.left() + 66, r.top() + 10, r.width() - 132, 36)
        p.setPen(QPen(QColor(theme.ACCENT), 1))
        p.setBrush(QColor("#10151B"))
        p.drawRoundedRect(mid, 3, 3)
        p.setFont(QFont("Consolas", 14, QFont.Bold))
        p.setPen(QColor("#F2D648"))
        p.drawText(mid, Qt.AlignCenter, str(self.value))
        synced = self.plc_value is not None and self.plc_value == self.value
        p.setFont(QFont("Segoe UI", 6))
        p.setPen(QColor("#5EE36A") if synced else TEXT_DIM)
        p.drawText(QRectF(r.left(), r.top() + 1, r.width(), 10), Qt.AlignCenter,
                   tr("✔ PLC รับค่าแล้ว") if synced else tr("คลิกตัวเลข = พิมพ์ค่า"))


ITEM_CLASSES = {
    "pushbutton": PushButtonItem, "selector": SelectorItem, "estop": EStopItem, "limit": LimitItem,
    "sensor": SensorItem, "lamp": LampItem, "motor": MotorItem, "buzzer": BuzzerItem,
    "valve": ValveItem, "conveyor": ConveyorItem, "display": DisplayItem,
    "overload": OverloadItem, "contactor": ContactorItem, "traffic": TrafficItem,
    "cylinder": CylinderItem, "tank": TankItem, "sevenseg": SevenSegItem, "setvalue": SetValueItem,
}


from .items_ext import CLASSES as _EXT_CLASSES  # noqa: E402  (ต้องอยู่ท้ายไฟล์: items_ext import จากไฟล์นี้)

ITEM_CLASSES.update(_EXT_CLASSES)

from .items_ext2 import CLASSES as _EXT2_CLASSES  # noqa: E402

ITEM_CLASSES.update(_EXT2_CLASSES)

from .items_ext3 import CLASSES as _EXT3_CLASSES  # noqa: E402

ITEM_CLASSES.update(_EXT3_CLASSES)


def make_item(spec: DeviceSpec) -> DeviceItem:
    return ITEM_CLASSES[spec.kind](spec)
