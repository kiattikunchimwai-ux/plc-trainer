"""แป้นพิมพ์ไทย (เกษมณี) → ตัวอังกฤษตำแหน่งเดียวกัน — ใช้กับช่องที่ต้องเป็นอังกฤษ (address, คำสั่ง ladder)
จึงพิมพ์ X0 ได้โดยไม่ต้องสลับแป้นก่อน."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

_EN = "`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./" + "~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>?"
_TH = "_ๅ/-ภถุึคตจขชๆไำพะัีรนยบลฃฟหกดเ้่าสวงผปแอิืทมใฝ" + "%+๑๒๓๔ู฿๕๖๗๘๙๐\"ฎฑธํ๊ณฯญฐ,ฅฤฆฏโฌ็๋ษศซ.()ฉฮฺ์?ฒฬฦ"  # i18n: skip
assert len(_EN) == len(_TH)
_MAP = {t: e for t, e in zip(_TH, _EN) if not t.isascii()}


def to_latin(text: str) -> str:
    """แปลงตัวไทยเป็นปุ่มอังกฤษตำแหน่งเดียวกัน (ตัวอื่นคงเดิม)."""
    return "".join(_MAP.get(c, c) for c in text)


def key_text(e) -> str:
    """ตัวอักษรที่ปุ่มนี้ให้บนแป้นอังกฤษ ("" = ไม่ใช่ปุ่มตัวอักษร) ไม่ว่าตอนนี้แป้นเป็นภาษาอะไร."""
    t = e.text()
    if not t or not t.isprintable() or e.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
        return ""
    vk, shift = e.nativeVirtualKey(), bool(e.modifiers() & Qt.ShiftModifier)
    if 0x41 <= vk <= 0x5A:
        return t if t.isascii() and t.isalpha() else (chr(vk) if shift else chr(vk).lower())
    if 0x30 <= vk <= 0x39 and not shift:
        return chr(vk)
    return to_latin(t)


class _Latin(QObject):
    def eventFilter(self, obj, e):
        if e.type() == QEvent.KeyPress:
            t = key_text(e)
            if t and t != e.text():
                QApplication.sendEvent(obj, QKeyEvent(QEvent.KeyPress, 0, Qt.KeyboardModifiers(), t))
                return True
        return False


def latin_only(edit):
    """ให้ QLineEdit นี้รับปุ่มเป็นอังกฤษเสมอ."""
    edit.installEventFilter(_Latin(edit))
    return edit
