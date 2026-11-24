"""หลายภาษา (ไทย / English) แบบ gettext: ข้อความไทยในโค้ดคือ key, คำแปลอยู่ใน i18n/<lang>.json.

    tr("ผ่าน {0}/{1} ข้อ", r.passed, r.total)  →  "Passed 1/2 checks" (ภาษาอังกฤษ)

- ไม่มีคำแปล → คืนข้อความไทยเดิม (ไม่พัง)
- ภาษาเลือกครั้งเดียวตอน import (อ่าน env PLC_LANG ก่อน แล้วจึง ui_state.json "lang") —
  ข้อความระดับโมดูล (HELP, catalog ฯลฯ) จึงแปลถูกตั้งแต่แรก; เปลี่ยนภาษา = เปิดโปรแกรมใหม่
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "i18n"
LANGS = {"th": "ไทย", "en": "English"}
DEFAULT = "th"

_lang = DEFAULT
_table: dict[str, str] = {}


def _state_file() -> Path:
    try:
        from . import paths
        return paths.data_dir() / "ui_state.json"
    except ImportError:
        return ROOT / "panels" / "ui_state.json"   # import paths ไม่ได้ (ไม่น่าเกิด)


def system_lang() -> str:
    """ภาษาเริ่มต้นตาม locale ของ Windows: ไทย → th, อื่น ๆ → en."""
    try:
        loc = (locale.getlocale()[0] or "") + " " + (os.environ.get("LANG") or "")
    except ValueError:
        loc = ""
    if not loc.strip():
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "th" if lcid & 0x3FF == 0x1E else "en"
        except (AttributeError, OSError):
            return DEFAULT
    return "th" if loc.lower().startswith(("th", "thai")) else "en"


def saved_lang() -> str | None:
    try:
        v = json.loads(_state_file().read_text(encoding="utf-8")).get("lang")
        return v if v in LANGS else None
    except (OSError, ValueError, AttributeError):
        return None


def load_table(lang: str) -> dict[str, str]:
    if lang == DEFAULT:
        return {}
    try:
        data = json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


def set_lang(lang: str):
    """ใช้ใน test/เครื่องมือ — โปรแกรมจริงเลือกภาษาครั้งเดียวตอนเริ่ม."""
    global _lang, _table
    _lang = lang if (lang in LANGS or lang == "pseudo") else DEFAULT
    _table = load_table(_lang)


def lang() -> str:
    return _lang


def tr(text: str, *args, **kw) -> str:
    if _lang == "pseudo":                  # ใช้ทดสอบ: ข้อความเปลี่ยนเล็กน้อย → จับโค้ดที่ตัดสินใจจากข้อความที่แปลแล้ว
        s = text + "​"
    else:
        s = _table.get(text, text) if _table else text
    if args or kw:
        try:
            return s.format(*args, **kw)
        except (IndexError, KeyError, ValueError):
            return text.format(*args, **kw)
    return s


def tr_data(text: str) -> str:
    """แปลข้อความจากข้อมูล (ชื่ออุปกรณ์บนผัง ฯลฯ) — key '@ข้อความ' ใช้เมื่อความหมายต่างจากในโค้ด
    เช่น ปุ่ม 'หยุด' = Stop แต่สถานะ 'หยุด' = stopped. ไม่มีคำแปล → คืนข้อความเดิม (ผังของผู้ใช้)."""
    if not text:
        return text
    if _table and ("@" + text) in _table and _table["@" + text]:
        return _table["@" + text]
    return tr(text)


def apply_qt_locale() -> None:
    """ตั้ง QLocale ตามภาษา — ไม่ใช้ locale ระบบ เพราะ Windows ที่ตั้ง 'ตัวเลขไทย' จะทำให้ spinbox แสดง ๕๕๑๑."""
    from PySide6.QtCore import QLocale
    loc = QLocale(QLocale.Language.Thai, QLocale.Country.Thailand) if _lang == "th" \
        else QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    QLocale.setDefault(loc)


def pick(th: str, en: str | None) -> str:
    """เลือกข้อความจากข้อมูลที่มีสองภาษา (เช่น ด่าน YAML: msg / en.msg)."""
    return en if (_lang == "en" and en) else th


def _initial() -> str:
    env = os.environ.get("PLC_LANG")
    if env in LANGS or env == "pseudo":
        return env
    return saved_lang() or system_lang()


set_lang(_initial())
