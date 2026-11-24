"""E2E D2: หน้าสนับสนุน (ribbon/cmd/top bar) → ตรวจด่าน 1 ได้ 3★ ครั้งแรก → toast ชวน → ระหว่างสอบไม่ชวน.

รัน:  $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe tools\\e2e_support.py docs\\support_test\\support_main.png
ใช้เลขพร้อมเพย์ตัวอย่าง (ไม่ใช่ของจริง) ผ่าน support.json ชั่วคราว
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = r"E:\PLC\Study Program PLC"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + r"\tests")
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom, support  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import exam, state, theme  # noqa: E402
from plc_game.ui.exam import ExamSession, hash_password  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402
from plc_game.ui.support_dlg import SupportDialog  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT + r"\docs\support_test\support_main.png")
out.parent.mkdir(parents=True, exist_ok=True)
backups = {}
for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE):
    backups[f] = f.read_bytes() if f.exists() else None
tmpcfg = Path(tempfile.mkdtemp()) / "support.json"
tmpcfg.write_text(json.dumps({
    "promptpay_id": "0812345678", "promptpay_name": "ตัวอย่าง (ไม่ใช่บัญชีจริง)",
    "links": [{"label": "Ko-fi", "url": "https://ko-fi.com/example"}],
    "goal": {"text": "Ladder editor + PLC จำลองในตัว", "target": 20000, "current": 6500},
    "supporters": ["ครูสมชาย", "Anan", "ช่างเอ"]}, ensure_ascii=False), encoding="utf-8")
support.SUPPORT_FILE = tmpcfg
exam.ITER = 1000

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


def dialogs():
    return [d for d in QApplication.topLevelWidgets() if isinstance(d, SupportDialog) and d.isVisible()]


def run_level1():
    cli = w.poller.client
    cli.program, cli._ctx = T.GOOD["01_self_hold"], {}
    cmd("CHECK")
    t0 = time.monotonic()
    while w.levelp.busy and time.monotonic() - t0 < 60:
        pump(0.05)
    return w.levelp.last_runner


try:
    scores.SCORE_FILE.write_text("{}", encoding="utf-8")      # เริ่มจากยังไม่เคยได้ 3 ดาว
    state.update(support_last_shown=0, support_never=False, support_milestones=[], student=scores.GUEST)
    w._set_student(scores.GUEST, save=False)
    pump(0.3)

    w.btn_support.click()
    pump(0.5)
    ds = dialogs()
    check("ปุ่ม ☕ บน top bar เปิดหน้าสนับสนุน", len(ds) == 1)
    d = ds[0]
    d.amount_buttons[1].click()
    pump(0.3)
    check("เลือก ฿99 → QR มีจำนวนเงิน + CRC", "540599.00" in d.qr.payload and d.qr.matrix,
          d.qr.payload[-12:])
    d.grab().save(str(out.with_name("support_dialog.png")))
    d.close()
    cmd("SUPPORT")
    pump(0.4)
    check("คำสั่ง SUPPORT เปิดหน้าสนับสนุน", len(dialogs()) == 1)
    for x in dialogs():
        x.close()

    w.connect_plc()
    pump(1.0)
    cmd("LEVEL 1")
    pump(0.5)
    r = run_level1()
    pump(0.5)
    toast = getattr(w, "_support_toast", None)
    check("ด่าน 1 ได้ 3 ดาว", r is not None and r.stars == 3, f"{r.passed}/{r.total}" if r else "")
    check("ได้ 3 ดาวครั้งแรก → toast ชวนขึ้นมุมขวาล่าง", toast is not None and toast.isVisible())
    w.grab().save(str(out))
    if toast is not None:
        toast.btn_later.click()
    pump(0.3)

    r = run_level1()
    pump(0.5)
    check("ตรวจซ้ำได้ 3 ดาวอีก → ไม่ชวนซ้ำ", getattr(w, "_support_toast", None) is toast)

    # โหมดสอบ: ไม่ชวนแม้เป็น 3 ดาวครั้งแรก
    scores.SCORE_FILE.write_text("{}", encoding="utf-8")
    state.update(support_last_shown=0, teacher_pw=hash_password("1234", iterations=1000))
    w._support_toast = None
    ids = [lv.id for lv in w.levelp.levels]
    w.start_exam(ExamSession.start(ids[:1], minutes=10, max_checks=0))
    pump(0.5)
    r = run_level1()
    pump(0.5)
    check("ระหว่างสอบได้ 3 ดาว → ไม่มี toast", r.stars == 3 and w._support_toast is None)
    check("จบสอบด้วยรหัสครู", w.end_exam("1234"))
    pump(0.3)
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
