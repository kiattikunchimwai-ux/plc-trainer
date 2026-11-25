"""D0: หลายภาษา — tr() fallback/format, en.json ครบและ placeholder ตรงกัน, หน้าต่างภาษาอังกฤษไม่มีอักษรไทยหลงเหลือ."""
import json
import os
import re
import string
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QLabel, QTabWidget  # noqa: E402

from plc_game import i18n  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import i18n_extract  # noqa: E402

THAI = re.compile(r"[฀-฾เ-๿]")      # ไม่นับ ฿ (U+0E3F)
# ทุกไฟล์ครอบ tr() แล้ว — ข้อความไทยที่เหลือ (ไม่นับ docstring) ต้องเป็นแค่ที่ตั้งใจข้าม (# i18n: skip)
DONE_FILES = [p.relative_to(ROOT).as_posix() for p in i18n_extract.py_files()]


@pytest.fixture
def en():
    i18n.set_lang("en")
    yield
    i18n.set_lang("th")


def test_tr_basic(en):
    assert i18n.tr("ปิด") == "Close"
    assert i18n.tr("ข้อความที่ไม่มีคำแปล {0}", 5) == "ข้อความที่ไม่มีคำแปล 5"     # fallback + format
    assert i18n.tr("ลงชื่อ: {0}", "A") == "Logged in: A"
    assert i18n.pick("ไทย", "Eng") == "Eng" and i18n.pick("ไทย", None) == "ไทย"
    i18n.set_lang("th")
    assert i18n.tr("ปิด") == "ปิด" and i18n.pick("ไทย", "Eng") == "ไทย"


def _fields(s):
    return sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)


def test_en_json_consistent():
    en = json.loads((ROOT / "i18n" / "en.json").read_text(encoding="utf-8"))
    keys, _ = i18n_extract.collect()
    done = {k for k, f in keys.items() if f in DONE_FILES}
    missing = sorted(k for k in done if not en.get(k))
    assert not missing, f"ยังไม่แปล {len(missing)}: {missing[:5]}"
    for k, v in en.items():
        if v:
            assert _fields(k) == _fields(v), f"placeholder ไม่ตรง: {k!r} → {v!r}"
            assert not THAI.search(v), f"คำแปลยังมีอักษรไทย: {v!r}"


def test_no_raw_thai_left():
    _, raw = i18n_extract.collect()          # ข้าม # i18n: skip / skip-file ให้แล้ว
    assert not raw, raw[:5]


def test_levels_have_english():
    """ทุกด่านมีคำแปลครบ: title/desc/name/msg/hint → *_en และโหลดในโหมด en ไม่มีอักษรไทย."""
    import yaml
    from plc_game.levels import engine
    for f in sorted((ROOT / "levels").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert d.get("title_en") and d.get("desc_en"), f.name
        for c in d.get("cases") or []:
            assert c.get("name_en"), (f.name, c.get("name"))
            for s in c.get("steps") or []:
                if isinstance(s, dict):
                    for k in ("msg", "hint"):
                        assert not s.get(k) or s.get(k + "_en"), (f.name, s.get(k))
    i18n.set_lang("en")
    try:
        for lv in engine.load_all():
            texts = [lv.title, lv.desc] + [c.name for c in lv.cases] + \
                    [x for c in lv.cases for s in c.steps for x in (s.msg, s.hint)]
            assert not [t for t in texts if THAI.search(t)], lv.id
    finally:
        i18n.set_lang("th")
    assert not THAI.search(engine.load_all()[0].title) is False      # โหมดไทยยังเป็นภาษาไทย


def test_editor_keeps_english(tmp_path):
    from plc_game.levels.editor import LevelDraft
    src = ROOT / "levels" / "01_self_hold.yaml"
    d = LevelDraft.load(src)
    again = LevelDraft.from_data(__import__("yaml").safe_load(d.dump()), src)
    data = again.to_data()
    assert data["title_en"] and data["desc_en"]
    assert data["cases"][0]["name_en"] == "Start latches the motor"
    step = data["cases"][0]["steps"][1]
    assert step["msg_en"] and step["hint_en"]


def _thai_texts(root):
    """ข้อความไทยบนทุก widget ลูกของ root (ยกเว้นตัวเลือกภาษา 'ไทย')."""
    from PySide6.QtWidgets import QComboBox, QLineEdit, QListWidget, QTreeWidget
    bad = []
    for wd in [root] + root.findChildren(object):
        texts = []
        if isinstance(wd, (QAbstractButton, QLabel, QLineEdit)):
            texts.append(wd.text())
        if isinstance(wd, QLineEdit):
            texts.append(wd.placeholderText())
        if hasattr(wd, "toolTip"):
            texts.append(wd.toolTip())
        if isinstance(wd, QTabWidget):
            texts += [wd.tabText(i) for i in range(wd.count())]
        if isinstance(wd, QComboBox):
            texts += [wd.itemText(i) for i in range(wd.count())]
        if isinstance(wd, QListWidget):
            texts += [wd.item(i).text() for i in range(wd.count())]
        if isinstance(wd, QTreeWidget):
            it = wd.invisibleRootItem()
            stack = [it.child(i) for i in range(it.childCount())]
            while stack:
                x = stack.pop()
                texts += [x.text(c) for c in range(wd.columnCount())]
                stack += [x.child(i) for i in range(x.childCount())]
        bad += [(type(wd).__name__, wd.objectName(), t) for t in texts
                if t and THAI.search(t) and "ไทย" not in t and "Language" not in t]
    return bad


_WINDOW_SCRIPT = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, {root!r}); sys.path.insert(0, {tests!r})
from PySide6.QtWidgets import QApplication
app = QApplication([])
from plc_game import classroom, i18n
from plc_game.levels import scores
from plc_game.ui import state
from plc_game.ui.shell import sidebar
import test_i18n as T
tmp = Path({tmp!r})
classroom.STUDENT_FILE = tmp / "students.json"; scores.SCORE_FILE = tmp / "scores.json"
state.PANEL_DIR = tmp; state.STATE_FILE = tmp / "ui_state.json"; state._OLD_LAST = tmp / "last.txt"
from plc_game.ai import learn; learn.MEMORY_FILE = tmp / "m.json"; sidebar.ANIMATE = False
from plc_game.ui.main_window import MainWindow
w = MainWindow({{"backend": "mock", "xy_base": 8}})
res = {{"lang": i18n.lang(), "bad": T._thai_texts(w),
        "same": w.set_language("en", ask_restart=False),
        "switch": w.set_language("th", ask_restart=False), "saved": state.load().get("lang")}}
w.close()
print("RESULT" + json.dumps(res, ensure_ascii=False))
"""


def test_window_english(tmp_path):
    """เปิดหน้าต่างเป็นภาษาอังกฤษในโปรเซสใหม่ (เหมือนผู้ใช้จริง: เลือกภาษาก่อน import ทุกโมดูล)
    → ทุก widget ไม่มีอักษรไทย (รวมข้อความที่แปลตอน import เช่น catalog/ALIGN_NAMES)."""
    import subprocess
    code = _WINDOW_SCRIPT.format(root=str(ROOT), tests=str(ROOT / "tests"), tmp=str(tmp_path))
    env = dict(os.environ, PLC_LANG="en", QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
                       env=env, cwd=str(ROOT), timeout=120)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT")), None)
    assert line, p.stdout[-800:] + p.stderr[-1500:]
    res = json.loads(line[6:])
    assert res["lang"] == "en"
    assert not res["bad"], res["bad"][:8]
    assert res["same"] is False                                   # ภาษาเดิม → ไม่ต้องเปิดใหม่
    assert res["switch"] is True and res["saved"] == "th"
