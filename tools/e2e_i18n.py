"""E2E D0: เปิดโปรแกรมเป็นภาษาอังกฤษ → ทั้งหน้าต่างไม่มีอักษรไทย → ด่าน 1 ได้ 3★ (ข้อความผลตรวจอังกฤษ)
→ ด่าน 14 หาจุดเสีย (เมนูทาย/เฉลยอังกฤษ) → ภาพหน้าจอใน docs/i18n_test/ → คืนไฟล์สถานะเดิมทุกไบต์.

รัน:  $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe tools\\e2e_i18n.py
"""
import os
import re
import sys
import time
from pathlib import Path

os.environ["PLC_LANG"] = "en"              # ต้องตั้งก่อน import plc_game (เลือกภาษาครั้งเดียวตอน import)
ROOT = r"E:\PLC\Study Program PLC"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + r"\tests")
os.chdir(ROOT)

from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit,  # noqa: E402
                               QListWidget, QMenu, QTableWidget, QTabWidget, QTextEdit, QTreeWidget)

from plc_game import classroom, i18n  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

THAI = re.compile(r"[\u0e00-\u0e3e\u0e40-\u0e7f]")
out = Path(ROOT) / "docs" / "i18n_test"
out.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}

app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
import test_levels as T  # noqa: E402

cfg = load_config()
cfg["backend"] = "mock"
import tempfile as _tf  # noqa: E402
from plc_game.ai import learn as _learn  # noqa: E402
_learn.MEMORY_FILE = Path(_tf.gettempdir()) / "plc_e2e_ai_memory.json"      # ไม่แตะความจำ AI จริง
w = MainWindow(cfg)
w.resize(1600, 950)
w.show()
results = []


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def cmd(text):
    w.cmd_input.setText(text)
    w._on_command()


def thai_texts(root, visible_only=True):
    """ข้อความไทยบน widget ที่ผู้ใช้เห็น (ยกเว้นตัวเลือกภาษา 'ไทย' / ปุ่ม Language)."""
    bad = []
    for wd in [root] + root.findChildren(object):
        if visible_only and hasattr(wd, "isVisible") and not wd.isVisible():
            continue
        t = []
        if isinstance(wd, (QAbstractButton, QLabel, QLineEdit)):
            t.append(wd.text())
        if isinstance(wd, QLineEdit):
            t.append(wd.placeholderText())
        if hasattr(wd, "toolTip"):
            t.append(wd.toolTip())
        if isinstance(wd, QTextEdit):
            t.append(wd.toPlainText())
        if isinstance(wd, QTabWidget):
            t += [wd.tabText(i) for i in range(wd.count())]
        if isinstance(wd, QComboBox):
            t += [wd.itemText(i) for i in range(wd.count())]
        if isinstance(wd, QListWidget):
            t += [wd.item(i).text() for i in range(wd.count())]
        if isinstance(wd, QTableWidget):
            t += [wd.item(r, c).text() for r in range(wd.rowCount()) for c in range(wd.columnCount())
                  if wd.item(r, c)]
            t += [wd.horizontalHeaderItem(c).text() for c in range(wd.columnCount()) if wd.horizontalHeaderItem(c)]
        if isinstance(wd, QTreeWidget):
            it = wd.invisibleRootItem()
            st = [it.child(i) for i in range(it.childCount())]
            while st:
                x = st.pop()
                t += [x.text(c) for c in range(wd.columnCount())]
                st += [x.child(i) for i in range(x.childCount())]
        bad += [s for s in t if s and THAI.search(s) and "ไทย" not in s and "Language" not in s]
    return bad


def panel_thai():
    """ป้ายอุปกรณ์/ข้อความบนผังที่แสดงจริง (shown_label + text/caption)."""
    bad = []
    for it in w.panel.sc.items():
        for name in ("shown_label", "caption", "state_text", "text"):
            v = getattr(it, name, None)
            v = v() if callable(v) else v
            if isinstance(v, str) and THAI.search(v):
                bad.append(f"{type(it).__name__}.{name}: {v[:40]}")
    return bad


try:
    check("ภาษา = en", i18n.lang() == "en")
    pump(0.5)
    bad = thai_texts(w)
    check("หน้าต่างหลักไม่มีอักษรไทย", not bad, " | ".join(bad[:5]))
    w.grab().save(str(out / "en_main.png"))

    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.connect_plc()
    pump(1.0)

    # ---------- ด่าน 1 ----------
    cmd("LEVEL 1")
    pump(0.8)
    check("ชื่อด่าน 1 เป็นภาษาอังกฤษ", w.levelp.level.title == "Level 1: Self-holding circuit", w.levelp.level.title)
    bad = panel_thai()
    check("ผังด่าน 1: ป้ายอุปกรณ์/โจทย์ไม่มีอักษรไทย", not bad, " | ".join(bad[:4]))
    cli = w.poller.client
    cli.program, cli._ctx = T.GOOD["01_self_hold"], {}
    cmd("CHECK")
    t0 = time.monotonic()
    while w.levelp.busy and time.monotonic() - t0 < 60:
        pump(0.05)
    pump(0.6)
    r = w.levelp.last_runner
    check("ด่าน 1 ได้ 3 ดาว", r is not None and r.stars == 3, f"{r.passed}/{r.total}" if r else "")
    msgs = [x.msg for x in r.results] + [x.case for x in r.results]
    check("ข้อความผลตรวจเป็นภาษาอังกฤษ", not [m for m in msgs if THAI.search(m)], msgs[0] if msgs else "")
    for t in list(getattr(w, "_support_toast", None) and [w._support_toast] or []):
        t.close()
    bad = thai_texts(w)
    check("หลังตรวจ: หน้าต่าง + ผลตรวจไม่มีอักษรไทย", not bad, " | ".join(bad[:5]))
    w.grab().save(str(out / "en_level1.png"))

    # ---------- ด่าน 14 ----------
    cli.program, cli._ctx = T.GOOD["03_timer"], {}
    cmd("LEVEL 14")
    pump(0.8)
    check("ชื่อด่าน 14 เป็นภาษาอังกฤษ", w.levelp.level.title == "Level 14: Troubleshooting", w.levelp.level.title)
    cmd("CHECK")
    pump(0.5)
    h = w.levelp.hunt
    broken = [it for it in w.panel.fault_items() if it.fault]
    check("เริ่มหาจุดเสีย (เสีย 1 จุด)", h is not None and len(broken) == 1)
    w._write("X0", 1); pump(0.4); w._write("X0", 0); pump(3.6)
    target = broken[0]
    lab, code = h.answer
    m = QMenu(w.panel)
    sub = w.panel.guess_menu(m, target)
    texts = [a.text() for a in sub.actions()] + [sub.title()]
    check("เมนูทายอาการเป็นภาษาอังกฤษ", not [t for t in texts if THAI.search(t)], " | ".join(texts))
    acts = {a.text(): a for a in sub.actions()}
    acts[target.FAULTS[code]].trigger()
    pump(0.6)
    check("ทายถูกครั้งแรก → 3 ดาว", h.found and h.stars == 3)
    ai = w.levelp.ai.toPlainText()
    check("เฉลย/คำอธิบายเป็นภาษาอังกฤษ", ai and not THAI.search(ai), ai[:80].replace("\n", " "))
    bad = thai_texts(w) + panel_thai()
    check("ด่าน 14: หน้าต่าง + ผังไม่มีอักษรไทย", not bad, " | ".join(bad[:5]))
    w.grab().save(str(out / "en_level14.png"))
    cmd("STOP")
    pump(0.3)

    # ---------- สลับภาษากลับ (บันทึกค่า แต่ไม่รีสตาร์ต) ----------
    check("LANG TH บันทึกภาษา (ต้องเปิดใหม่)", w.set_language("th", ask_restart=False) and state.load()["lang"] == "th")
finally:
    if w.poller:
        w.disconnect_plc()
    pump(0.3)
    w.dirty = False
    for f, data in backups.items():
        if data is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(data)
    same = all((f.read_bytes() if f.exists() else None) == data for f, data in backups.items())
    print("คืนไฟล์สถานะเดิม:", "ครบทุกไบต์" if same else "ไม่ตรง!")
print(f"\nสรุป: ผ่าน {sum(results)}/{len(results)}")
