"""E2E M8: ลงชื่อ → ตรวจด่าน 1 (ถูก) → คะแนนเข้าชื่อ → ตารางคะแนน + Export xlsx → HMI เต็มจอ → ออก."""
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = r"E:\PLC\Study Program PLC"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + r"\tests")
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1])
backups = {}
for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE):
    backups[f] = f.read_bytes() if f.exists() else None
QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
import test_levels as T  # noqa: E402

cfg = load_config()
cfg["backend"] = "mock"
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


def cmd(text):
    w.cmd_input.setText(text)
    w._on_command()


try:
    classroom.upsert_student("E2E01", "ทดสอบ อัตโนมัติ")
    w._set_student("E2E01")
    pump(0.3)
    check("ลงชื่อแล้วปุ่มบน top bar แสดงชื่อ", "ทดสอบ" in w.btn_student.text(), w.btn_student.text())
    w.connect_plc()
    pump(1.0)
    cmd("LEVEL 1")
    pump(0.5)
    cli = w.poller.client
    cli.program, cli._ctx = T.GOOD["01_self_hold"], {}
    cmd("CHECK")
    t0 = time.monotonic()
    while w.levelp.runner is not None and time.monotonic() - t0 < 60:
        pump(0.05)
    r = w.levelp.last_runner
    check("ตรวจด่าน 1 ได้ 3 ดาว", r.stars == 3, f"{r.passed}/{r.total}")
    check("เสียงตรวจผ่านเล่น", w.sounds.played[-1:] == ["pass"], str(w.sounds.played))
    st = scores.load().get("E2E01", {}).get("01_self_hold", {})
    check("คะแนนบันทึกใต้รหัสนักเรียน", st.get("best_stars") == 3, str(st))
    check("ดาวในรายการด่านเป็นของคนที่ลงชื่อ", w.cb_level.itemText(0).startswith("★★★"), w.cb_level.itemText(0))

    dlg = w.show_scores()
    pump(0.5)
    rows = [dlg.table.item(i, 0).text() for i in range(dlg.table.rowCount())]
    check("ตารางคะแนนมีนักเรียนที่ลงชื่อ", "E2E01" in rows, f"{len(rows)} แถว")
    dlg.grab().save(str(out.with_name("m8_scores.png")))
    x = dlg.export(str(out.with_name("m8_scores.xlsx")))
    from openpyxl import load_workbook
    wb = load_workbook(x)
    ids = [c.value for c in wb["สรุป"]["A"]]
    check("Export xlsx เปิดอ่านกลับได้ + มีรหัส", "E2E01" in ids, str(x))
    dlg.close()

    cmd("HMI")
    pump(1.0)
    check("HMI เต็มจอ: ซ่อน ribbon / status bar / แผงข้าง",
          w.isFullScreen() and w.menuWidget().isHidden() and w.statusBar().isHidden() and not w.side_r.pane.isVisible())
    w.grab().save(str(out))
    w.set_hmi(False)
    pump(1.0)
    check("ออกจาก HMI: เครื่องมือกลับมาครบ", not w.isFullScreen() and w.menuWidget().isVisible() and w.statusBar().isVisible())
    w.grab().save(str(out.with_name("m8_normal.png")))
finally:
    w.disconnect_plc()
    pump(0.3)
    w.dirty = False
    for f, data in backups.items():
        if data is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(data)
print(f"\nสรุป: ผ่าน {sum(results)}/{len(results)}")
