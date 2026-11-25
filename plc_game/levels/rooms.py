"""ห้องด่านของผู้ใช้ — แยกจากด่านมาตรฐาน (ไม่ใช้ Qt).

levels/rooms/<key>/room.json + *.yaml + *.plcpanel
- ด่านมาตรฐาน (levels/*.yaml) อ่านอย่างเดียว ทำสำเนาเข้าห้องเพื่อแก้
- รหัสด่านตอนใช้งาน = <key>__<id> คะแนนจึงไม่ปนกับด่านมาตรฐานหรือห้องอื่น
- ส่งต่อได้เป็นไฟล์ .plcroom (zip) — ตอนนำเข้าตรวจทุกไฟล์ก่อนวาง
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..i18n import tr
from ..panel.model import PanelDoc
from . import editor as E
from .engine import LEVEL_DIR, Level, load_level

SEP = "__"
MAX_FILES, MAX_FILE, MAX_TOTAL = 300, 2_000_000, 20_000_000
_KEY = re.compile(r"^[0-9a-z]{1,24}$")
_FILE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,80}\.(yaml|plcpanel)$")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\.|$)", re.I)
BAD = (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError, yaml.YAMLError)


class RoomError(ValueError):
    """ข้อความสำหรับแสดงผู้ใช้."""


@dataclass(frozen=True)
class Room:
    key: str
    name: str
    path: Path

    def level_id(self, lid: str) -> str:
        return f"{self.key}{SEP}{lid}"


def rooms_dir(folder: Path = LEVEL_DIR) -> Path:
    return Path(folder) / "rooms"


def list_rooms(folder: Path = LEVEL_DIR) -> list[Room]:
    out = []
    base = rooms_dir(folder)
    for p in sorted(base.iterdir()) if base.is_dir() else []:
        if p.is_dir() and _KEY.match(p.name) and (p / "room.json").is_file():
            out.append(Room(p.name, _read_name(p) or p.name, p))
    return sorted(out, key=lambda r: (r.name.lower(), r.key))


def get(key: str, folder: Path = LEVEL_DIR) -> Room | None:
    return next((r for r in list_rooms(folder) if r.key == key), None)


def _read_name(p: Path) -> str:
    try:
        d = json.loads((p / "room.json").read_text(encoding="utf-8"))
        return _clean(d.get("name", "")) if isinstance(d, dict) else ""
    except (OSError, ValueError):
        return ""


def _clean(name) -> str:
    return " ".join("".join(c if c.isprintable() else " " for c in str(name)).split())[:60]


def _write_name(p: Path, name: str):
    (p / "room.json").write_text(json.dumps({"version": 1, "name": name}, ensure_ascii=False, indent=1), encoding="utf-8")


def _check_name(name: str, folder: Path, skip: str = "") -> str:
    name = _clean(name)
    if not name:
        raise RoomError(tr("ยังไม่ได้ตั้งชื่อห้อง"))
    if any(r.name.lower() == name.lower() and r.key != skip for r in list_rooms(folder)):
        raise RoomError(tr("มีห้องชื่อ '{0}' อยู่แล้ว", name))
    return name


def create(name: str, folder: Path = LEVEL_DIR) -> Room:
    name = _check_name(name, folder)
    key = "r" + uuid.uuid4().hex[:8]
    p = rooms_dir(folder) / key
    p.mkdir(parents=True)
    _write_name(p, name)
    return Room(key, name, p)


def rename(room: Room, name: str, folder: Path = LEVEL_DIR) -> Room:
    name = _check_name(name, folder, room.key)
    _write_name(room.path, name)
    return Room(room.key, name, room.path)


def delete(room: Room, folder: Path = LEVEL_DIR) -> Path:
    """ย้ายทั้งห้องไป levels/_trash (กู้คืนได้)."""
    t = Path(folder) / "_trash"
    t.mkdir(exist_ok=True)
    dst = t / f"room_{room.key}_{time.strftime('%Y%m%d_%H%M%S')}"
    room.path.replace(dst)
    return dst


def load_levels(room: Room, xy_base: int = 8) -> tuple[list[Level], list[str]]:
    """(ด่านของห้อง, ไฟล์ที่อ่านไม่ได้) — ไฟล์เสียไฟล์เดียวไม่ทำให้ทั้งห้องเปิดไม่ได้."""
    out, errs = [], []
    for p in sorted(room.path.glob("*.yaml")):
        try:
            lv = load_level(p, xy_base)
        except BAD as e:
            errs.append(f"{p.name}: {e}")
            continue
        lv.id = room.level_id(lv.id)
        out.append(lv)
    return sorted(out, key=lambda lv: (lv.order, lv.id)), errs


def new_id(room: Room, base: str = "") -> str:
    have = {p.stem for p in room.path.glob("*.yaml")}
    have |= {re.sub(r"_\d{8}_\d{6}$", "", p.stem) for p in (room.path / "_trash").glob("*.yaml")}      # ลบแล้ว: คะแนน/ladder เก่ายังผูกกับรหัสนี้
    base = re.sub(r"[^0-9A-Za-z_\-]", "", base) or f"{len(have) + 1:02d}_new"
    lid, n = base, 2
    while lid in have:
        lid, n = f"{base}_{n}", n + 1
    return lid


def add_panel(room: Room, doc_or_path, name: str = "") -> str:
    """คัดลอกผังเข้าห้อง (ไม่ทับไฟล์ที่เนื้อหาต่างกัน) — คืนชื่อไฟล์."""
    if isinstance(doc_or_path, PanelDoc):
        data = doc_or_path.to_json().encode("utf-8")
        name = name or doc_or_path.name
    else:
        p = Path(doc_or_path)
        data, name = p.read_bytes(), name or p.stem
    stem = re.sub(r"[\\/:*?\"<>|\x00-\x1f.]", "_", name).strip() or "panel"
    if _RESERVED.match(stem):
        stem = "_" + stem
    stem, n, fn = stem[:50], 2, ""
    while True:
        fn = f"{stem}.plcpanel" if n == 2 else f"{stem}_{n - 1}.plcpanel"
        f = room.path / fn
        if not f.exists():
            f.write_bytes(data)
            return fn
        if f.read_bytes() == data:
            return fn
        n += 1


def copy_level(src: E.LevelDraft, src_folder: Path, room: Room) -> E.LevelDraft:
    """สำเนาด่าน (พร้อมผัง) เข้าห้อง แล้วบันทึก."""
    d = copy.deepcopy(src)
    d.path = None
    d.id = new_id(room, d.id)
    d.order = max((x.order for x in E.load_drafts(room.path)), default=0) + 1
    p = E.resolve_panel(d.panel, src_folder)
    if p is not None:
        d.panel = add_panel(room, p)
    d.save(room.path)
    return d


# ======================= ส่งออก / นำเข้า =======================
def export(room: Room, path: Path) -> Path:
    """.plcroom = zip ที่มีด่านและผังครบในตัว (ผังนอกห้องถูกฝังไปด้วย)."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as td:
        tmp = Room(room.key, room.name, Path(td))
        _write_name(tmp.path, room.name)
        for p in sorted(room.path.glob("*.plcpanel")):
            shutil.copy2(p, tmp.path / p.name)
        for d in E.load_drafts(room.path):
            src = E.resolve_panel(d.panel, room.path)
            d.panel = add_panel(tmp, src) if src is not None else ""
            (tmp.path / f"{d.id}.yaml").write_text(d.dump(), encoding="utf-8")
        out = path.with_name(path.name + ".tmp")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(tmp.path.iterdir()):
                z.write(f, f.name)
        out.replace(path)
    return path


def _read_member(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    with z.open(info) as f:
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise RoomError(tr("ไฟล์ {0} ใหญ่เกินไป", info.filename))
    return data


def import_room(path: Path, folder: Path = LEVEL_DIR, xy_base: int = 8) -> Room:
    """อ่าน .plcroom → ห้องใหม่ (รหัสใหม่เสมอ ไม่ทับห้องเดิม)."""
    files: dict[str, bytes] = {}
    name, total = "", 0
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_FILES:
                raise RoomError(tr("ไฟล์ห้องมีไฟล์มากเกินไป"))
            for i in infos:
                fn = i.filename
                if fn != "room.json" and (not _FILE.match(fn) or _RESERVED.match(fn)):
                    raise RoomError(tr("ไฟล์ห้องมีไฟล์ที่ไม่รองรับ: {0}", fn[:60]))
                data = _read_member(z, i)
                total += len(data)
                if total > MAX_TOTAL:
                    raise RoomError(tr("ไฟล์ห้องใหญ่เกินไป"))
                if fn == "room.json":
                    d = json.loads(data.decode("utf-8"))
                    name = _clean(d.get("name", "")) if isinstance(d, dict) else ""
                elif fn.lower() in {f.lower() for f in files}:
                    raise RoomError(tr("ไฟล์ห้องมีไฟล์ชื่อซ้ำ: {0}", fn))
                else:
                    files[fn] = data
    except RoomError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as e:
        raise RoomError(tr("อ่านไฟล์ห้องไม่ได้: {0}", e)) from None
    if not name and not files:
        raise RoomError(tr("ไฟล์นี้ไม่ใช่ห้องด่าน"))
    base = name or tr("ห้องที่นำเข้า")
    have = {r.name.lower() for r in list_rooms(folder)}
    name, n = base, 2
    while name.lower() in have:
        name, n = f"{base[:54]} ({n})", n + 1
    key = "r" + uuid.uuid4().hex[:8]
    root = rooms_dir(folder)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".tmp_{key}"
    tmp.mkdir()
    try:
        for fn, data in files.items():
            if fn.endswith(".plcpanel"):
                try:
                    PanelDoc.from_json(data.decode("utf-8"))
                except BAD as e:
                    raise RoomError(tr("ผัง {0} เสียหาย: {1}", fn, e)) from None
                (tmp / fn).write_bytes(data)
        for fn, data in files.items():
            if fn.endswith(".yaml"):
                (tmp / fn).write_text(_safe_level(fn, data, files, tmp, xy_base), encoding="utf-8")
        _write_name(tmp, name)
        tmp.replace(root / key)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return Room(key, name, root / key)


def _safe_level(fn: str, data: bytes, files: dict, tmp: Path, xy_base: int) -> str:
    stem = fn[:-5]
    if not re.match(r"^[0-9A-Za-z_\-]+$", stem):
        raise RoomError(tr("ไฟล์ห้องมีไฟล์ที่ไม่รองรับ: {0}", fn))
    try:
        text = data.decode("utf-8")
        if any(isinstance(t, yaml.AliasToken) for t in yaml.scan(text)):       # กันไฟล์ที่ขยายตัวไม่จำกัด
            raise ValueError("alias")
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError("not a level")
        d = E.LevelDraft.from_data(raw, tmp / fn)
        d.id = stem
        if d.panel not in files:                     # ผังต้องมากับไฟล์เท่านั้น ไม่อ้างพาธในเครื่อง
            d.panel = ""
        probs = d.problems(tmp, xy_base)
        if probs:
            raise ValueError(probs[0])
        return d.dump()
    except BAD as e:
        raise RoomError(tr("ด่าน {0} ใช้ไม่ได้: {1}", fn, e)) from None
