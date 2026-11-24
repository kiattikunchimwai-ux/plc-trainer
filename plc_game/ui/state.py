"""การตั้งค่า UI ที่จำข้ามการเปิดโปรแกรม: panels/ui_state.json."""
from __future__ import annotations

import json
from pathlib import Path

from .. import paths

ROOT = paths.app_root()
PANEL_DIR = paths.data_dir()
STATE_FILE = PANEL_DIR / "ui_state.json"
_OLD_LAST = PANEL_DIR / "last_panel.txt"


def load() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    data = {}
    try:   # ย้ายจากไฟล์รุ่นเก่า
        data["last_panel"] = _OLD_LAST.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return data


def update(**kw) -> dict:
    data = load()
    data.update(kw)
    try:
        PANEL_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _OLD_LAST.unlink(missing_ok=True)
    except OSError:
        pass
    return data
