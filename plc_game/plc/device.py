"""ชื่ออุปกรณ์ PLC (X0, Y17, M100, TN0 ...) และการแปลงเลข.

FX5 / GX Works3 (FX5 CPU) ใช้เลข X/Y เป็นฐาน 8: X0..X7, X10..X17
อุปกรณ์อื่น (M, D, T, C) เป็นฐาน 10
"""
from __future__ import annotations

from ..i18n import tr

import re
from dataclasses import dataclass

# ลำดับสำคัญ: prefix ยาวต้องมาก่อน (TS ก่อน T)
PREFIXES = ("TS", "TN", "TC", "CS", "CN", "CC", "SM", "SD", "X", "Y", "M", "D", "L", "B", "W")
BIT_KINDS = {"X", "Y", "M", "L", "B", "TS", "TC", "CS", "CC", "SM"}
OCTAL_KINDS = {"X", "Y"}

_RE = re.compile(r"^(" + "|".join(PREFIXES) + r")([0-9A-Fa-f]+)$")


@dataclass(frozen=True)
class Device:
    kind: str      # เช่น "X", "TN"
    number: int    # ค่าตัวเลขจริง (X10 ฐาน 8 → 8)
    xy_base: int = 8

    @property
    def is_bit(self) -> bool:
        return self.kind in BIT_KINDS

    @property
    def name(self) -> str:
        """ชื่อที่แสดงให้นักเรียนเห็น เช่น 'X10'."""
        if self.kind in OCTAL_KINDS:
            return f"{self.kind}{_fmt(self.number, self.xy_base)}"
        return f"{self.kind}{self.number}"

    def offset(self, n: int) -> "Device":
        return Device(self.kind, self.number + n, self.xy_base)

    def __str__(self) -> str:
        return self.name


def _fmt(n: int, base: int) -> str:
    if base == 8:
        return format(n, "o")
    if base == 16:
        return format(n, "X")
    return str(n)


def parse_device(text: str, xy_base: int = 8) -> Device:
    m = _RE.match(text.strip().upper())
    if not m:
        raise ValueError(tr("ชื่ออุปกรณ์ไม่ถูกต้อง: {0!r}", text))
    kind, num = m.groups()
    base = xy_base if kind in OCTAL_KINDS else 10
    try:
        number = int(num, base)
    except ValueError:
        raise ValueError(tr("เลขอุปกรณ์ {0!r} ไม่ถูกต้องสำหรับฐาน {1}", text, base)) from None
    return Device(kind, number, xy_base)


def device_range(head: str, count: int, xy_base: int = 8) -> list[Device]:
    """device_range('X0', 10) → X0..X7, X10, X11 (ฐาน 8)."""
    d = parse_device(head, xy_base)
    return [d.offset(i) for i in range(count)]
