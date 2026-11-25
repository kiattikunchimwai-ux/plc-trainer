"""E2E ตัวแก้ไขด่านของครู บนหน้าต่างจริง + Mock PLC (ทำกับสำเนาโฟลเดอร์ levels/ — ไฟล์จริงไม่ถูกแตะ)

ครูเปิดตัวแก้ไขจากแท็บครู → ดูด่าน 3 → ใส่พารามิเตอร์ผิดให้เห็นช่องแดง → สร้างด่านใหม่จากฟอร์ม
→ บันทึกแล้วเปิดด่าน → ตรวจด้วย Mock (ladder ในตัว = self-hold) ต้องได้ 3 ดาว → แก้ชื่อ → ลบ (ไป _trash)

รัน:  .venv\\Scripts\\python.exe tools\\e2e_level_editor.py docs\\level_editor_test
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.levels.engine import LEVEL_DIR, load_level  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.level_dock import LevelPanel  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/level_editor_test")
out.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
tmp = Path(tempfile.mkdtemp(prefix="plc_lvedit_"))
lvdir = tmp / "levels"
shutil.copytree(LEVEL_DIR, lvdir, ignore=shutil.ignore_patterns("_trash"))
real_before = sorted((p.name, p.stat().st_mtime_ns) for p in LEVEL_DIR.iterdir())
LevelPanel.folder = lvdir
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)   # ยืนยันลบอัตโนมัติ

QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
cfg = load_config()
cfg["backend"] = "mock"
import tempfile as _tf  # noqa: E402
from plc_game.ai import learn as _learn  # noqa: E402
_learn.MEMORY_FILE = Path(_tf.gettempdir()) / "plc_e2e_ai_memory.json"      # ไม่แตะความจำ AI จริง
w = MainWindow(cfg)
w.resize(1600, 950)
w.show()
w.set_split(False)
results = []


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def shot(widget, name):
    pump(0.25)
    widget.grab().save(str(out / f"{name}.png"))


def set_step(tbl, r, op, params, msg=None):
    tbl.table.cellWidget(r, 0).setCurrentText(op)
    tbl.table.item(r, 1).setText(params)
    if msg is not None:
        tbl.table.item(r, 2).setText(msg)


try:
    w.open_level(2)
    w.ribbon.setCurrentIndex(3)                 # แท็บครู
    pump(0.3)
    check("ปุ่มตัวแก้ไขด่านอยู่ในแท็บครู", w.b_level_edit.isVisible() and w.b_level_edit.isEnabled())
    shot(w, "e0_teacher_tab")
    w.b_level_edit.click()
    pump(0.5)
    dlg = w._level_editor
    dlg.resize(1280, 800)
    check("เปิดตัวแก้ไข เลือกด่านที่เปิดอยู่ (ด่าน 3)", dlg.cur.id == "03_timer" and dlg.lst_cases.count() == 3)
    check("แสดง I/O ของผัง", "X0" in dlg.lbl_io.text() and "Y1" in dlg.lbl_io.text())
    shot(dlg, "e1_level3")

    dlg.steps.table.item(2, 1).setText("Y1 = 0 for")
    pump(0.2)
    bad = dlg.steps.validate()
    dlg.check()
    check("พารามิเตอร์ผิด → ช่องแดง + บอกปัญหา", bad == 1 and "ยังบันทึกไม่ได้" in dlg.lbl_status.text())
    shot(dlg, "e2_error")
    dlg.steps.table.item(2, 1).setText("Y1 = 0 for 2.4")
    dlg.dirty = False                            # ทิ้งการแก้ด่าน 3 (ค่ากลับเหมือนเดิมแล้ว)
    dlg.cur = None

    # ----- ด่านใหม่ -----
    dlg.new_level(False)
    pump(0.3)
    d = dlg.cur
    dlg.ed_title.setText("ด่าน 15: ทดสอบตัวแก้ไข")
    dlg.ed_desc.setPlainText("กด Start (X0) → มอเตอร์ (Y0) ทำงานค้าง · กด Stop (X1) → หยุด")
    dlg.lst_cases.item(0).setText("Start แล้วค้าง")
    dlg.steps.table.setCurrentCell(1, 1)
    dlg.steps.add_row()
    set_step(dlg.steps, 2, "hold", "Y0 = 1 for 1", "ปล่อยปุ่มแล้วมอเตอร์ยังทำงาน")
    dlg.add_case()
    dlg.lst_cases.item(1).setText("Stop แล้วหยุด")
    set_step(dlg.steps, 0, "pulse", "X1 0.3")
    set_step(dlg.steps, 1, "expect", "Y0 = 0 within 0.5", "กด Stop → มอเตอร์หยุด")
    pump(0.2)
    probs = dlg.check()
    check("ฟอร์มด่านใหม่ถูกต้อง", probs == [] and "นับคะแนน 3 จุด" in dlg.lbl_status.text(), "; ".join(probs))
    shot(dlg, "e3_new_level")
    new_id = d.id
    dlg.b_open.click()
    pump(0.8)
    f = lvdir / f"{new_id}.yaml"
    check("บันทึกเป็น YAML ที่ตัวโหลดจริงอ่านได้", f.exists() and load_level(f).checks == 3, f.name)
    check("หน้าต่างหลักเปิดด่านใหม่", w.levelp.level is not None and w.levelp.level.id == new_id
          and any("ด่าน 15" in w.cb_level.itemText(i) for i in range(w.cb_level.count())))

    # ----- ตรวจด้วย Mock -----
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.btn_connect.click()
    pump(1.0)
    w.levelp.btn_check.click()
    t0 = time.monotonic()
    pump(0.5)
    while w.levelp.busy and time.monotonic() - t0 < 60:
        pump(0.1)
    r = w.levelp.last_runner
    check("ตรวจด่านใหม่ด้วย Mock ได้ 3 ดาว", r is not None and r.stars == 3, r and f"{r.passed}/{r.total}")
    shot(w, "e4_checked")

    # ----- แก้ชื่อด่านที่เปิดอยู่ → หน้าต่างหลักอัปเดต -----
    dlg = w.open_level_editor()
    dlg.ed_title.setText("ด่าน 15: แก้ชื่อแล้ว")
    dlg._mark()
    dlg.save()
    pump(0.4)
    check("แก้ชื่อ → โจทย์ในแท็บด่านอัปเดตทันที", w.levelp.level.title == "ด่าน 15: แก้ชื่อแล้ว")
    shot(dlg, "e5_saved")

    # ----- ลบ -----
    n = len(w.levelp.levels)
    dlg.delete()
    pump(0.4)
    check("ลบด่าน → ย้ายไป _trash + หายจากรายการด่าน", not f.exists()
          and list((lvdir / "_trash").glob(f"{new_id}_*.yaml")) and len(w.levelp.levels) == n - 1)
    dlg.close()
    pump(0.2)
    check("ไฟล์ใน levels/ จริงไม่ถูกแตะ",
          sorted((p.name, p.stat().st_mtime_ns) for p in LEVEL_DIR.iterdir()) == real_before)
finally:
    if w.poller:
        w.disconnect_plc()
    pump(0.3)
    w.dirty = False
    for f_, data in backups.items():
        if data is None:
            f_.unlink(missing_ok=True)
        else:
            f_.write_bytes(data)
    shutil.rmtree(tmp, ignore_errors=True)
print(f"\nสรุป: ผ่าน {sum(results)}/{len(results)}")
sys.exit(0 if results and all(results) else 1)
