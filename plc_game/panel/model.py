"""โมเดลผังอุปกรณ์ + บันทึก/เปิดไฟล์ .plcpanel (JSON)."""
from __future__ import annotations

from ..i18n import tr

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..plc.device import parse_device
from .catalog import CATALOG, IN_KINDS

FORMAT_VERSION = 1


@dataclass
class DeviceSpec:
    kind: str
    x: float = 0.0
    y: float = 0.0
    props: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @classmethod
    def new(cls, kind: str, x: float = 0, y: float = 0, **props) -> "DeviceSpec":
        base = dict(CATALOG[kind].defaults)
        base.update(props)
        return cls(kind=kind, x=x, y=y, props=base)

    @property
    def address(self) -> str:
        return str(self.props.get("address", ""))

    def all_io(self) -> list[tuple[str, str, str]]:
        """[(prop, io, address)] ของทุก address ที่กำหนดไว้ (ข้ามช่องเสริมที่เว้นว่าง)."""
        out = []
        for s in CATALOG[self.kind].slots():
            a = str(self.props.get(s.prop, "") or "").strip().upper()
            if a or not s.optional:
                out.append((s.prop, s.io, a))
        return out


@dataclass
class PanelDoc:
    name: str = tr("ผังใหม่")
    devices: list[DeviceSpec] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"version": FORMAT_VERSION, "name": self.name,
                           "devices": [asdict(d) for d in self.devices]}, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "PanelDoc":
        data = json.loads(text)
        if data.get("version", 1) > FORMAT_VERSION:
            raise ValueError(tr("ไฟล์ผังนี้มาจากโปรแกรมเวอร์ชันใหม่กว่า"))
        devs = []
        for d in data.get("devices", []):
            if d.get("kind") not in CATALOG:
                continue   # ข้ามชนิดที่ไม่รู้จัก
            devs.append(DeviceSpec(kind=d["kind"], x=float(d.get("x", 0)), y=float(d.get("y", 0)),
                                   props=dict(d.get("props", {})), id=d.get("id") or uuid.uuid4().hex[:8]))
        return cls(name=data.get("name", tr("ผัง")), devices=devs)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "PanelDoc":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


def validate_address(kind: str, text: str, xy_base: int = 8, prop: str = "address") -> tuple[bool, str]:
    """คืน (True, ชื่อมาตรฐาน) หรือ (False, ข้อความผิดพลาดภาษาไทย).
    ช่องเสริมที่เว้นว่างได้ (optional) และว่างอยู่ → (True, "")."""
    slot = CATALOG[kind].slot(prop)
    text = (text or "").strip().upper()
    if not text:
        return (True, "") if slot.optional else (False, tr("ยังไม่ได้กำหนด address"))
    try:
        d = parse_device(text, xy_base)
    except ValueError as e:
        return False, str(e)
    if d.kind not in slot.prefixes:
        return False, tr("{0} ใช้ได้เฉพาะ ", slot.label) + " / ".join(slot.prefixes)
    return True, d.name


def conflicts(devices: list[DeviceSpec], xy_base: int = 8) -> dict[str, list[str]]:
    """Input หลายชิ้นใช้ address เดียวกัน = ชนกัน (เขียนทับกัน). คืน {address: [id,...]}."""
    seen: dict[str, list[str]] = {}
    for d in devices:
        for prop, io, addr in d.all_io():
            if io not in IN_KINDS or not addr:
                continue
            ok, name = validate_address(d.kind, addr, xy_base, prop)
            if ok:
                seen.setdefault(name, []).append(d.id)
    return {a: ids for a, ids in seen.items() if len(ids) > 1}
