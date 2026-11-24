"""ที่อยู่ไฟล์ของโปรแกรม.

รันจากซอร์ส  → ทุกอย่างอยู่ในโฟลเดอร์โปรเจกต์ (panels/, levels/) เหมือนเดิม
รันจาก .exe  → ไฟล์ที่มากับโปรแกรม (assets/, i18n/, levels/ ต้นฉบับ) อยู่ในโฟลเดอร์โปรแกรม (อ่านอย่างเดียว)
               ไฟล์ของผู้ใช้อยู่ที่ %APPDATA%\\PLCTrainer\\ (panels/ + levels/ โครงเดียวกับซอร์ส)
               ครั้งแรกที่เปิดจะคัดลอกผังตัวอย่าง/ด่านไปให้ · เปลี่ยนเวอร์ชันแล้วอัปเดตเฉพาะไฟล์ที่ผู้ใช้ไม่เคยแก้
               (ตรงกับที่เคยแจกใน plc_game/shipped_hashes.json) — ไม่ทับของที่ครูแก้
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

APP_NAME = "PLCTrainer"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """ไฟล์ที่มากับโปรแกรม (levels/, panels/ ตัวอย่าง, assets/, i18n/) — อ่านอย่างเดียวเมื่อเป็น .exe."""
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def user_root() -> Path:
    """ราก ข้อมูลของผู้ใช้ (มี panels/ และ levels/) — เขียนได้เสมอ."""
    if frozen():
        override = os.environ.get("PLCTRAINER_HOME")          # ใช้ทดสอบ .exe โดยไม่แตะ %APPDATA% จริง
        if override:
            return Path(override)
        return Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    return app_root()


def data_dir() -> Path:
    """ui_state.json, scores.json, students.json, ผังที่บันทึก."""
    return user_root() / "panels"


def levels_dir() -> Path:
    """ด่าน YAML (ตัวแก้ไขด่านของครูเขียนที่นี่)."""
    return user_root() / "levels"


def cache_dir() -> Path:
    """ไฟล์ที่สร้างใหม่ได้เสมอ เช่น เสียง WAV."""
    return (user_root() / "cache") if frozen() else app_root() / "assets"


def config_path() -> Path:
    """config.yaml ของผู้ใช้ (ถ้ามี) ก่อน แล้วค่อยของที่มากับโปรแกรม."""
    user = user_root() / "config.yaml"
    if frozen() and user.exists():
        return user
    return app_root() / "plc_game" / "config.yaml"


def seed_user_dir() -> list[Path]:
    """(.exe เท่านั้น) คัดลอกผังตัวอย่างและด่านที่ยังไม่มีไปไว้ที่ข้อมูลผู้ใช้ (ไม่คัดด่านที่ครูลบกลับมา) — คืนรายการไฟล์ที่คัดลอก."""
    if not frozen():
        return []
    copied = []
    record = user_root() / "seeded.json"                  # ด่านที่เคยคัดให้แล้ว: หายไป = ครูลบ/เปลี่ยนรหัส → ไม่คัดกลับ
    had = _read_json(record).get("levels")
    had = {str(n) for n in had} if isinstance(had, list) else set()
    if not any(levels_dir().glob("*.yaml")):
        had = set()                                       # ไม่เหลือด่านเลย (โฟลเดอร์หาย) → คัดให้ใหม่ทั้งหมด
    given = set(had)
    for sub, pats in (("panels", ("*.plcpanel",)), ("levels", ("*.yaml", "*.plcpanel"))):
        src, dst = app_root() / sub, user_root() / sub
        dst.mkdir(parents=True, exist_ok=True)
        for pat in pats:
            for f in sorted(src.glob(pat)):
                target = dst / f.name
                if not target.exists() and not (f.suffix == ".yaml" and f.name in had):
                    try:
                        shutil.copy2(f, target)
                        copied.append(target)
                    except OSError:
                        pass
                if f.suffix == ".yaml" and target.exists():
                    given.add(f.name)
    if given != had or not record.exists():
        try:
            record.write_text(json.dumps({"levels": sorted(given)}, indent=1), encoding="utf-8")
        except OSError:
            pass
    return copied


# ---------------- อัปเดตไฟล์ที่เคยแจก (.exe) ----------------
_SEEDED = (("panels", (".plcpanel",)), ("levels", (".yaml", ".plcpanel")))
_PANEL_REF = re.compile(r"^panel:\s*['\"]?([^'\"#\r\n]+)", re.M)


def content_hash(data: bytes) -> str:
    """แฮชเนื้อหา ไม่นับชนิดตัวขึ้นบรรทัด (git/ตัวแก้ข้อความสลับ CRLF ได้)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _group(name: str, data: bytes) -> str:
    """ด่านกับผังที่ด่านใช้ต้องอัปเดตพร้อมกัน — กลุ่มเดียวกัน = ชื่อไฟล์ผังเดียวกัน."""
    if name.endswith(".yaml"):
        m = _PANEL_REF.search(data.decode("utf-8", "replace"))
        if m:
            return re.split(r"[\\/]", m.group(1).strip())[-1].lower()
    return name.rsplit("/", 1)[-1].lower()


def update_user_files() -> tuple[list[str], list[str]]:
    """(.exe เท่านั้น) แทนด่าน/ผังที่ผู้ใช้ไม่เคยแก้ด้วยของเวอร์ชันนี้ — คืน (ที่อัปเดต, ที่เก็บของผู้ใช้ไว้และเพิ่งพบ).

    ไฟล์ที่ผู้ใช้แก้ไม่ถูกแตะ และไฟล์อื่นในกลุ่มเดียวกัน (ด่าน + ผัง) ก็คงไว้ ไม่ให้รุ่นไม่ตรงกัน
    """
    if not frozen():
        return [], []
    known = _read_json(app_root() / "plc_game" / "shipped_hashes.json")
    old: list[tuple[str, bytes, str, bool]] = []          # (ชื่อ, เนื้อหาใหม่, กลุ่ม, ผู้ใช้แก้)
    for sub, exts in _SEEDED:
        for f in sorted((app_root() / sub).glob("*")):
            name, target = f"{sub}/{f.name}", user_root() / sub / f.name
            hashes = known.get(name)
            if f.suffix not in exts or not isinstance(hashes, list) or not target.is_file():
                continue
            try:
                new, mine = f.read_bytes(), content_hash(target.read_bytes())
            except OSError:
                continue
            h = content_hash(new)
            if mine != h and any(x != h for x in hashes):
                old.append((name, new, _group(name, new), mine not in hashes))
    blocked = {g for _, _, g, edited in old if edited}
    updated, kept = [], {}
    for name, new, g, _ in old:
        if g in blocked:
            kept[name] = content_hash(new)
            continue
        target = user_root() / name
        tmp = target.with_name(target.name + ".tmp")
        try:
            tmp.write_bytes(new)
            os.replace(tmp, target)
            updated.append(name)
        except OSError:                                   # ไฟล์ถูกเปิดค้าง/เขียนไม่ได้ → ลองใหม่ครั้งหน้า
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    note = user_root() / "update_notice.json"             # แจ้งครั้งเดียวต่อรุ่นของไฟล์
    seen = _read_json(note)
    fresh = [n for n, h in kept.items() if seen.get(n) != h]
    if fresh:
        try:
            note.write_text(json.dumps({**seen, **kept}, indent=1), encoding="utf-8")
        except OSError:
            pass
    return updated, fresh
