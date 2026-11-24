"""E2E M12 โหมดสอบ บนหน้าต่างจริง + Mock PLC:
ลงชื่อ → เริ่มสอบ (ด่าน 1,3 · 10 นาที · ตรวจได้ 2 ครั้ง) → ล็อกแก้ผัง/AI → ตรวจด่าน 1 ถูก 3★
→ ด่าน 3 ผิด → ครบสิทธิ์ → หมดเวลา → รหัสผิด/ถูก → ปลดล็อก

รัน:  .venv\\Scripts\\python.exe tools\\e2e_exam.py docs\\exam_test\\exam.png
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.exam import ExamSession, hash_password  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/exam_test/exam.png")
out.parent.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
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


def wait_check():
    t0 = time.monotonic()
    while w.levelp.runner is not None and time.monotonic() - t0 < 90:
        pump(0.05)
    return w.levelp.last_runner


try:
    classroom.upsert_student("E2E01", "ทดสอบ อัตโนมัติ")
    w._set_student("E2E01")
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.connect_plc()
    pump(1.0)
    ids = [lv.id for lv in w.levelp.levels]
    state.update(teacher_pw=hash_password("1234"))
    w.start_exam(ExamSession.start([ids[0], ids[2]], minutes=10, max_checks=2))
    pump(1.2)
    check("เริ่มสอบ: นาฬิกาถอยหลังบน top bar", w.lbl_exam.isVisible() and "09:5" in w.lbl_exam.text(),
          w.lbl_exam.text())
    cmd("EDIT")
    pump(0.2)
    check("ล็อกแก้ผัง (EDIT ไม่ได้)", w.panel.sc.run_mode and not w.btn_edit.isEnabled())
    cmd("ANALYZE LIVE")
    check("ปิด AI วิเคราะห์", "ปิด AI" in w.levelp.ai.toPlainText() and not w.ribbon.isTabEnabled(4))
    cmd("LEVEL 2")
    check("เปิดด่านนอกชุดสอบไม่ได้", w.levelp.level.id == ids[0], w.levelp.level.id)

    cli = w.poller.client
    cli.program, cli._ctx = T.GOOD["01_self_hold"], {}
    cmd("CHECK")
    r = wait_check()
    check("ด่าน 1 ถูก → 3 ดาว (ในโหมดสอบ)", r.stars == 3 and w.exam.best.get(ids[0]) == 3, f"{r.passed}/{r.total}")
    check("ผลตรวจไม่มี AI", "ปิด AI" in w.levelp.ai.toPlainText())
    w.grab().save(str(out))

    cmd("LEVEL 3")
    pump(0.5)
    cli.program, cli._ctx = T.wrong_timer, {}                    # ตั้ง Timer 1 s แทน 3 s
    got = []
    for _ in range(2):
        cmd("CHECK")
        r3 = wait_check()
        got.append(f"{r3.passed}/{r3.total}={r3.stars}★")
    check("ด่าน 3 ผิด 2 ครั้ง ไม่ถึง 3 ดาว", w.exam.checks.get(ids[2]) == 2 and w.exam.best.get(ids[2], 0) < 3,
          f"{w.exam.checks} {w.exam.best} {got} level={w.levelp.level.id}")
    cmd("CHECK")
    pump(0.3)
    check("ครั้งที่ 3 ถูกปฏิเสธ (ครบสิทธิ์)", w.levelp.runner is None and w.exam.checks[ids[2]] == 2
          and "ตรวจได้อีก 0" in w.lbl_exam.text(), w.lbl_exam.text())

    w.exam.started_at -= 11 * 60
    pump(1.3)
    check("หมดเวลา: แสดงหมดเวลา + ออด", "หมดเวลา" in w.lbl_exam.text() and w.sounds.played[-1:] == ["buzzer"],
          w.lbl_exam.text())
    w.grab().save(str(out.with_name(out.stem + "_timeout.png")))

    check("รหัสครูผิดออกไม่ได้", not w.end_exam("9999") and w.exam is not None)
    check("รหัสครูถูก → ปลดล็อกทั้งหมด", w.end_exam("1234") and w.exam is None and w.btn_edit.isEnabled()
          and w.ribbon.isTabEnabled(4) and w.levelp.ai_enabled and not w.lbl_exam.isVisible())
    pump(0.3)
    w.grab().save(str(out.with_name(out.stem + "_after.png")))
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
print(f"\nสรุป: ผ่าน {sum(results)}/{len(results)}")
sys.exit(0 if results and all(results) else 1)
