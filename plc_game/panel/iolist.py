"""ตาราง I/O ของผัง + export (CSV / GX Works3 Device Comment) + จัด address อัตโนมัติ (ไม่ใช้ Qt)."""
from __future__ import annotations

from ..i18n import tr, tr_data

import csv
import io
from dataclasses import dataclass

from ..plc.device import PREFIXES, Device, parse_device
from .catalog import CATALOG
from .model import DeviceSpec, validate_address

DIR_TH = {"in": "Input → PLC", "out": "PLC → Output", "word": tr("PLC → แสดงค่า"), "wordin": tr("ค่า → PLC")}
_ORDER = {p: i for i, p in enumerate(("X", "Y", "M", "D", "TN", "TS", "CN", "CS", "L", "B", "W", "SM", "SD"))}
GX_COMMENT_MAX = 32


@dataclass
class IORow:
    address: str
    io: str              # in / out / word / wordin
    label: str           # ชื่อที่ผู้ใช้ตั้ง
    device: str          # ชนิดอุปกรณ์ (ไทย)
    slot: str            # หน้าที่ของ address นี้ในอุปกรณ์ เช่น "รีดสวิตช์ยื่น (a1)"
    contact: str         # NO / NC / ""
    device_id: str
    prop: str

    @property
    def is_reference(self) -> bool:
        """ช่องที่แค่ "อ้างถึง" Output ของอุปกรณ์อื่น (มอเตอร์ที่ OL/encoder เฝ้า) ไม่ได้ขับเอง."""
        return self.prop == "addr_motor"

    @property
    def role(self) -> str:
        """หน้าที่ของ address (ว่างถ้าอุปกรณ์มี address เดียว)."""
        return "" if self.slot == "Address" else self.slot

    @property
    def direction(self) -> str:
        return DIR_TH.get(self.io, self.io)

    @property
    def comment(self) -> str:
        """ข้อความสั้นสำหรับ Device Comment."""
        base = self.label or self.device
        if self.prop != "address":
            base = f"{base} {self.slot}"
        return base


def _sort_key(addr: str, xy_base: int):
    d = parse_device(addr, xy_base)
    return (_ORDER.get(d.kind, len(_ORDER) + PREFIXES.index(d.kind)), d.number)


def rows(devices: list[DeviceSpec], xy_base: int = 8) -> list[IORow]:
    """ทุก address ที่ถูกต้องในผัง เรียงตามชนิด (X, Y, M, D, T, C) และเลข."""
    out = []
    for d in devices:
        info = CATALOG[d.kind]
        for prop, io_, raw in d.all_io():
            ok, name = validate_address(d.kind, raw, xy_base, prop)
            if not (ok and name):
                continue
            contact = str(d.props.get("contact", "")).upper() if prop == "address" and io_ == "in" else ""
            out.append(IORow(name, io_, tr_data(str(d.props.get("label", "") or "")), info.name,
                             info.slot(prop).label if prop != "address" else info.main_label,
                             contact, d.id, prop))
    # อุปกรณ์ที่ "เป็นเจ้าของ" address (ช่องหลัก) มาก่อนช่องที่อ้างถึง เช่น มอเตอร์ที่ OL เฝ้า
    out.sort(key=lambda r: (_sort_key(r.address, xy_base), r.prop != "address", r.label))
    return out


def to_csv(rs: list[IORow]) -> str:
    """CSV ภาษาไทย (ขึ้นต้นด้วย BOM เพื่อให้ Excel อ่านภาษาไทยได้)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Address", tr("ทิศทาง"), tr("ชื่อ"), tr("อุปกรณ์"), tr("หน้าที่"), tr("หน้าสัมผัส")])
    for r in rs:
        w.writerow([r.address, r.direction, r.label, r.device, r.role, r.contact])
    return "﻿" + buf.getvalue()


def _clip(text: str, n: int = GX_COMMENT_MAX) -> str:
    """ตัดข้อความไม่เกิน n ตัวอักษร ที่ขอบคำ (ไม่ตัดกลางคำไทยจนสระ/วรรณยุกต์หลุด)."""
    if len(text) <= n:
        return text
    cut = text[:n]
    i = cut.rfind(" ") if text[n] != " " else n      # ตัดที่ช่องว่างสุดท้าย (เก็บข้อความได้มากที่สุด)
    if i > 0:
        return cut[:i].rstrip(" /")
    # ไม่มีช่องว่าง: ถอยจนตัวถัดไปไม่ใช่สระบน/ล่าง/วรรณยุกต์ (ไม่ให้พยัญชนะเหลือโดยไม่มีสระของมัน)
    is_mark = lambda ch: "ั" <= ch <= "๎" and ch not in "าำเแโใไๅๆ"  # noqa: E731  # i18n: skip
    while len(cut) > 1 and is_mark(text[len(cut)]):
        cut = cut[:-1]
    return cut


def gx_comments(rs: list[IORow]) -> list[tuple[str, str]]:
    """[(device, comment)] หนึ่งแถวต่อ address · ใช้ชื่ออุปกรณ์ที่ "ขับ/เป็นเจ้าของ" address นั้น
    (หลายตัวใช้ร่วม = รวมด้วย /) ส่วนช่องที่แค่อ้างถึง (เช่น มอเตอร์ที่ OL เฝ้า) ใช้เมื่อไม่มีเจ้าของเท่านั้น."""
    owners: dict[str, list[str]] = {}
    refs: dict[str, list[str]] = {}
    for r in rs:
        names = (refs if r.is_reference else owners).setdefault(r.address, [])
        if r.comment not in names:
            names.append(r.comment)
    out = []
    for a in dict.fromkeys(r.address for r in rs):
        names = owners.get(a) or refs.get(a, [])
        out.append((a, _clip(" / ".join(names))))
    return out


def to_gx_comment_csv(rs: list[IORow]) -> str:
    """CSV สำหรับนำเข้า Device Comment ใน GX Works3 (คอลัมน์ Device Name, Comment)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    w.writerow(["Device Name", "Comment"])
    for a, c in gx_comments(rs):
        w.writerow([a, c])
    return "﻿" + buf.getvalue()


def to_html(rs: list[IORow], title: str) -> str:
    """ตาราง I/O แบบ HTML (ใช้พิมพ์เป็น PDF)."""
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    body = "".join(f"<tr><td><b>{esc(r.address)}</b></td><td>{esc(r.direction)}</td><td>{esc(r.label)}</td>"
                   f"<td>{esc(r.device)}</td><td>{esc(r.role)}</td><td>{esc(r.contact)}</td></tr>" for r in rs)
    return (tr("<h2>ตาราง I/O — {0}</h2><table border='1' cellspacing='0' cellpadding='4' width='100%'><tr style='background:#DDE3EA'><th>Address</th><th>ทิศทาง</th><th>ชื่อ</th><th>อุปกรณ์</th><th>หน้าที่</th><th>NO/NC</th></tr>{1}</table>", esc(title), body))


# ======================= จัด address อัตโนมัติ =======================
def auto_assign(devices: list[DeviceSpec], xy_base: int = 8) -> dict[str, dict[str, str]]:
    """เรียงอุปกรณ์ตามตำแหน่ง (บน→ล่าง ซ้าย→ขวา) แล้วให้เลข X0, X1… และ Y0, Y1… ใหม่.

    - Output ที่เคยใช้ address เดียวกัน (เช่น หลอด RUN + มอเตอร์ = Y0) ยังใช้ร่วมกันต่อ
    - ช่องที่ "อ้างถึง" Output (เช่น มอเตอร์ที่ OL เฝ้า) ใช้เลขใหม่ของ Y เดิมนั้น
    - ไม่แตะ M / D / T / C
    คืน {device_id: {prop: address ใหม่}} เฉพาะช่องที่เปลี่ยน
    """
    order = sorted(devices, key=lambda d: (round(d.y / 40), d.x))
    x_next, y_map = 0, {}
    changes: dict[str, dict[str, str]] = {}

    def ok_name(d, prop, raw):
        ok, name = validate_address(d.kind, raw, xy_base, prop)
        return name if ok and name else ""

    # Output ก่อน เพื่อให้ช่องอ้างอิง (addr_motor) ได้เลขเดียวกับตัวจริง
    for d in order:
        for prop, io_, raw in d.all_io():
            name = ok_name(d, prop, raw)
            if io_ == "out" and name.startswith("Y") and name not in y_map:
                if prop == "address" or CATALOG[d.kind].io == "out":
                    y_map[name] = Device("Y", len(y_map), xy_base).name
    for d in order:
        for prop, io_, raw in d.all_io():
            name = ok_name(d, prop, raw)
            if not name:
                continue
            new = name
            if io_ == "in" and name.startswith("X"):
                new = Device("X", x_next, xy_base).name
                x_next += 1
            elif io_ == "out" and name.startswith("Y"):
                if name not in y_map:                      # อ้างถึง Y ที่ไม่มีอุปกรณ์ใช้จริง
                    y_map[name] = Device("Y", len(y_map), xy_base).name
                new = y_map[name]
            if new != name:
                changes.setdefault(d.id, {})[prop] = new
    return changes
