"""แบบร่างด่านสำหรับตัวแก้ไขด่านของครู (ไม่ใช้ Qt).

อ่าน levels/*.yaml → LevelDraft (แก้ไขได้) → ตรวจความถูกต้องด้วยตัวโหลดจริง (level_from_data) → บันทึกกลับเป็น YAML
- คอมเมนต์ต้นไฟล์ (#…) ถูกเก็บไว้ · คีย์ที่ตัวแก้ไขไม่รู้จักถูกเก็บไว้ใน extra แล้วเขียนกลับ
- ลบด่าน = ย้ายไป levels/_trash/ (กู้คืนได้)
"""
from __future__ import annotations

from ..i18n import tr

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..plc.device import parse_device
from .. import paths
from .engine import LEVEL_DIR, ROOT, Level, level_from_data, parse_step

OPS = ["set", "pulse", "word", "wait", "part", "expect", "hold", "waitfor"]
OP_HELP = {
    "set": (tr("เขียนบิต"), tr("X0 1  (ปุ่ม NC ตอนกด = 0)")),
    "pulse": (tr("กดแล้วปล่อย"), tr("X0 0.3  (ON 0.3 วินาทีแล้ว OFF)")),
    "word": (tr("เขียนค่าตัวเลข"), "D10 50"),
    "wait": (tr("รอ"), tr("1.5  (วินาที)")),
    "part": (tr("ปล่อยชิ้นงานบนสายพาน"), tr("metal  หรือ  plastic")),
    "expect": (tr("ต้องเป็นจริงภายในเวลา (นับคะแนน)"), "Y0 = 1 within 0.5   ·   D0 >= +1 within 2"),
    "hold": (tr("ต้องเป็นจริงตลอดช่วง (นับคะแนน)"), "Y0 = 1 and Y1 = 0 for 2"),
    "waitfor": (tr("รอจนเป็นจริง (ไม่นับคะแนน)"), "X2 = 1 within 5"),
}
CHECK_OPS = ("expect", "hold")
_ID = re.compile(r"^[0-9A-Za-z_\-]+$")
_KNOWN = {"id", "order", "title", "panel", "desc", "idle", "settle", "reset", "cases", "faults"}


# ---------------- ขั้นตอน ----------------
@dataclass
class StepRow:
    op: str = "set"
    params: str = ""
    msg: str = ""
    hint: str = ""
    extra: dict = field(default_factory=dict)      # key อื่นที่ตัวแก้ไขไม่รู้จัก เช่น msg_en / hint_en

    @classmethod
    def from_raw(cls, raw) -> "StepRow":
        msg = hint = ""
        extra = {}
        if isinstance(raw, dict):
            msg, hint = str(raw.get("msg", "") or ""), str(raw.get("hint", "") or "")
            extra = {k: v for k, v in raw.items() if k not in ("do", "msg", "hint")}
            raw = raw.get("do", "")
        op, _, rest = str(raw).strip().partition(" ")
        return cls(op.lower(), rest.strip(), msg, hint, extra)

    @property
    def text(self) -> str:
        return f"{self.op} {self.params}".strip()

    def to_raw(self):
        if not (self.msg or self.hint or self.extra):
            return self.text
        d = {"do": self.text}
        if self.msg:
            d["msg"] = self.msg
        if self.hint:
            d["hint"] = self.hint
        d.update(self.extra)
        return d

    def error(self, xy_base: int = 8) -> str:
        try:
            parse_step(self.to_raw(), xy_base)
        except ValueError as e:
            return str(e)
        return ""

    @property
    def is_check(self) -> bool:
        return self.op in CHECK_OPS


@dataclass
class CaseRow:
    name: str
    steps: list[StepRow] = field(default_factory=list)
    extra: dict = field(default_factory=dict)      # เช่น name_en

    def to_raw(self) -> dict:
        return {"name": self.name, **self.extra, "steps": [s.to_raw() for s in self.steps]}


# ---------------- idle ----------------
def idle_to_text(idle: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (idle or {}).items())


def text_to_idle(text: str, xy_base: int = 8) -> dict[str, int]:
    out = {}
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        a, eq, v = part.partition("=")
        if not eq:
            raise ValueError(tr("ค่าพัก '{0}' ต้องเขียนแบบ X0=0", part))
        try:
            name = parse_device(a.strip(), xy_base).name
            out[name] = int(v)
        except ValueError as e:
            raise ValueError(tr("ค่าพัก '{0}': {1}", part, e)) from None
    return out


# ---------------- ด่าน ----------------
@dataclass
class LevelDraft:
    id: str
    title: str
    order: int = 0
    panel: str = ""
    desc: str = ""
    idle: dict = field(default_factory=dict)
    settle: float = 0.6
    reset: list[StepRow] = field(default_factory=list)
    cases: list[CaseRow] = field(default_factory=list)
    hunt: bool = False
    guesses: int = 3
    pool: list[tuple[str, list[str]]] = field(default_factory=list)
    path: Path | None = None
    header: str = ""                          # คอมเมนต์ต้นไฟล์เดิม
    extra: dict = field(default_factory=dict)

    # ----- อ่าน -----
    @classmethod
    def from_data(cls, data: dict, path: Path | None = None, header: str = "") -> "LevelDraft":
        f = data.get("faults") or None
        return cls(
            id=str(data.get("id", path.stem if path else "new_level")),
            title=str(data.get("title", "")),
            order=int(data.get("order", 0) or 0),
            panel=str(data.get("panel", "") or ""),
            desc=str(data.get("desc", "") or "").strip(),
            idle={str(k): int(v) for k, v in (data.get("idle") or {}).items()},
            settle=float(data.get("settle", 0.6)),
            reset=[StepRow.from_raw(s) for s in data.get("reset") or []],
            cases=[CaseRow(str(c.get("name", tr("ข้อ {0}", i + 1))), [StepRow.from_raw(s) for s in c.get("steps") or []],
                           {k: v for k, v in c.items() if k not in ("name", "steps")})
                   for i, c in enumerate(data.get("cases") or [])],
            hunt=f is not None,
            guesses=int((f or {}).get("guesses", 3)),
            pool=[(str(e.get("device", "")), [str(c) for c in e.get("codes") or []]) for e in (f or {}).get("pool") or []],
            path=path, header=header,
            extra={k: v for k, v in data.items() if k not in _KNOWN},
        )

    @classmethod
    def load(cls, path: Path) -> "LevelDraft":
        text = Path(path).read_text(encoding="utf-8")
        header = "".join(ln for ln in _leading_comments(text))
        return cls.from_data(yaml.safe_load(text) or {}, Path(path), header)

    # ----- เขียน -----
    def to_data(self) -> dict:
        d: dict = {"id": self.id, "order": self.order, "title": self.title}
        if self.panel:
            d["panel"] = self.panel
        d["desc"] = self.desc.strip() + "\n" if self.desc.strip() else ""
        if self.hunt:
            d["faults"] = {"guesses": int(self.guesses),
                           "pool": [{"device": dev, "codes": list(codes)} for dev, codes in self.pool]}
        else:
            d["idle"] = dict(self.idle)
            if abs(self.settle - 0.6) > 1e-9:
                d["settle"] = self.settle
            if self.reset:
                d["reset"] = [s.to_raw() for s in self.reset]
            d["cases"] = [c.to_raw() for c in self.cases]
        d.update(self.extra)
        return d

    def dump(self) -> str:
        body = yaml.dump(self.to_data(), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1000,
                         default_flow_style=False)
        head = self.header or tr("# สร้าง/แก้ด้วยตัวแก้ไขด่านของครู — ตรวจจากผล I/O เท่านั้น\n")
        return head + body

    def target_path(self, folder: Path = LEVEL_DIR) -> Path:
        return Path(folder) / f"{self.id}.yaml"

    # ----- ตรวจ -----
    def problems(self, folder: Path = LEVEL_DIR, xy_base: int = 8, others: list[str] = ()) -> list[str]:
        """รายการปัญหาเป็นภาษาไทย (ว่าง = บันทึกได้)."""
        out = []
        if not _ID.match(self.id or ""):
            out.append(tr("รหัสด่านใช้ได้เฉพาะ a-z A-Z 0-9 _ - (เป็นชื่อไฟล์ด้วย)"))
        elif self.id in others:
            out.append(tr("รหัสด่าน '{0}' ซ้ำกับด่านอื่น", self.id))
        if not self.title.strip():
            out.append(tr("ยังไม่ได้ตั้งชื่อด่าน"))
        if self.panel and not _panel_exists(self.panel, folder):
            out.append(tr("ไม่พบไฟล์ผัง {0}", self.panel))
        if self.hunt:
            if not self.pool:
                out.append(tr("หาจุดเสีย: ยังไม่มีรายการอุปกรณ์ที่สุ่มเสียได้"))
            for i, (dev, codes) in enumerate(self.pool, 1):
                if not dev or not codes:
                    out.append(tr("หาจุดเสีย แถว {0}: ต้องมีชื่ออุปกรณ์และอาการอย่างน้อย 1 แบบ", i))
        else:
            for k, v in self.idle.items():
                try:
                    parse_device(k, xy_base)
                except ValueError as e:
                    out.append(tr("ค่าพัก {0}: {1}", k, e))
            for j, s in enumerate(self.reset, 1):
                if e := s.error(xy_base):
                    out.append(tr("reset ขั้น {0}: {1}", j, e))
                elif s.is_check:
                    out.append(tr("reset ขั้น {0}: ใช้ {1} ไม่ได้ (ใช้ waitfor แทน)", j, s.op))
            if not self.cases:
                out.append(tr("ยังไม่มีข้อตรวจ (case)"))
            for i, c in enumerate(self.cases, 1):
                if not c.steps:
                    out.append(tr("ข้อ {0} '{1}': ยังไม่มีขั้นตอน", i, c.name))
                for j, s in enumerate(c.steps, 1):
                    if e := s.error(xy_base):
                        out.append(tr("ข้อ {0} ขั้น {1}: {2}", i, j, e))
            if self.cases and not any(s.is_check for c in self.cases for s in c.steps):
                out.append(tr("ไม่มีขั้นตอนที่นับคะแนน — ต้องมี expect หรือ hold อย่างน้อย 1 ขั้น"))
        if not out:
            try:
                self.build(folder, xy_base)
            except (ValueError, TypeError) as e:
                out.append(str(e))
        return out

    def build(self, folder: Path = LEVEL_DIR, xy_base: int = 8) -> Level:
        return level_from_data(self.to_data(), self.target_path(folder), xy_base)

    # ----- ไฟล์ -----
    def save(self, folder: Path = LEVEL_DIR) -> Path:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        new = self.target_path(folder)
        new.write_text(self.dump(), encoding="utf-8")
        if self.path and Path(self.path).resolve() != new.resolve() and Path(self.path).exists():
            trash(Path(self.path), folder)       # เปลี่ยนรหัส = ย้ายไฟล์เดิมไปถังขยะ
        self.path = new
        return new


class _Dumper(yaml.SafeDumper):
    """ข้อความหลายบรรทัด (desc) เขียนแบบ | ให้ครูเปิดไฟล์อ่านได้ง่าย."""


def _str_repr(dumper, s):
    if "\n" in s:
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


_Dumper.add_representer(str, _str_repr)


def _leading_comments(text: str):
    for ln in text.splitlines(keepends=True):
        if ln.startswith("#"):
            yield ln
        else:
            break


def _panel_exists(panel: str, folder: Path) -> bool:
    return any((base / panel).exists() for base in (Path(folder), paths.user_root(), ROOT))


def trash(path: Path, folder: Path = LEVEL_DIR) -> Path:
    """ย้ายไฟล์ด่านไป levels/_trash/ (ไม่ลบจริง)."""
    t = Path(folder) / "_trash"
    t.mkdir(exist_ok=True)
    dst = t / f"{Path(path).stem}_{time.strftime('%Y%m%d_%H%M%S')}.yaml"
    Path(path).replace(dst)
    return dst


def load_drafts(folder: Path = LEVEL_DIR) -> list[LevelDraft]:
    ds = []
    for p in sorted(Path(folder).glob("*.yaml")):
        try:
            ds.append(LevelDraft.load(p))
        except (OSError, ValueError, yaml.YAMLError, TypeError, AttributeError):
            continue
    return sorted(ds, key=lambda d: (d.order, d.id))


def new_draft(existing: list[LevelDraft], hunt: bool = False) -> LevelDraft:
    order = max((d.order for d in existing), default=0) + 1
    ids = {d.id for d in existing}
    base = f"{order:02d}_new"
    lid, n = base, 2
    while lid in ids:
        lid, n = f"{base}{n}", n + 1
    d = LevelDraft(lid, tr("ด่าน {0}: (ตั้งชื่อด่าน)", order), order, desc=tr("กด Start (X0) → ..."))
    if hunt:
        d.hunt = True
    else:
        d.idle = {"X0": 0, "X1": 0}
        d.reset = [StepRow("pulse", "X1 0.3")]
        d.cases = [CaseRow(tr("ข้อ 1"), [StepRow("pulse", "X0 0.3"),
                                     StepRow("expect", "Y0 = 1 within 0.5", tr("กด Start → Y0 ทำงาน"))])]
    return d


def duplicate(d: LevelDraft, existing: list[LevelDraft]) -> LevelDraft:
    import copy
    c = copy.deepcopy(d)
    ids = {x.id for x in existing}
    lid, n = f"{d.id}_copy", 2
    while lid in ids:
        lid, n = f"{d.id}_copy{n}", n + 1
    c.id, c.path, c.title = lid, None, d.title + tr(" (สำเนา)")
    c.order = max((x.order for x in existing), default=0) + 1
    return c


def panel_choices(folder: Path = LEVEL_DIR) -> list[tuple[str, str]]:
    """[(ข้อความแสดง, ค่าที่เขียนใน YAML)] — ผังของด่าน (levels/) และฉากตัวอย่าง (panels/)."""
    out = [(p.name, p.name) for p in sorted(Path(folder).glob("*.plcpanel"))]
    out += [(tr("ฉาก: {0}", p.name), f"panels/{p.name}") for p in sorted(paths.data_dir().glob("*.plcpanel"))]
    return out


def resolve_panel(panel: str, folder: Path = LEVEL_DIR) -> Path | None:
    for base in (Path(folder), paths.user_root(), ROOT):
        if panel and (base / panel).exists():
            return (base / panel).resolve()
    return None
