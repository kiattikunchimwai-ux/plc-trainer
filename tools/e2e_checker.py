"""E2E ตัวตรวจด่าน: Mock ที่ตอบช้าแบบ GX Simulator3 — ทุกด่าน (ถูก) · โปรแกรมเปล่า · หลุดกลางคัน · ล็อกการกด.

    python tools/e2e_checker.py <โฟลเดอร์ภาพ>
"""
import os
import sys
import time
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
sys.path[:0] = [ROOT, ROOT + r"\tests"]
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
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
        time.sleep(0.005)


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def cmd(text):
    w.cmd_input.setText(text)
    w._on_command()


def slow(cli):
    for n in ("read_bits", "read_words"):
        real = getattr(cli, n)

        def f(head, count, real=real):
            time.sleep(0.1 / max(1, len(w.poller.watch)) if w.poller else 0)
            return real(head, count)
        setattr(cli, n, f)


def clear_outputs(cli):
    with cli._lock:
        for k in ("Y", "M", "D", "TN", "TS", "CN", "CS"):
            cli._mem[k].clear()
    cli._t0_start = None


def run_level(i, program):
    cmd(f"LEVEL {i}")
    pump(0.4)
    cli = w.poller.client
    clear_outputs(cli)
    cli.program, cli._ctx = program, {}
    pump(0.4)
    cmd("CHECK")
    t0 = time.monotonic()
    while w.levelp.runner is not None and time.monotonic() - t0 < 120:
        pump(0.05)
    return w.levelp.last_runner


try:
    w.connect_plc()
    pump(0.8)
    slow(w.poller.client)
    pump(0.5)
    for i, lid in enumerate(sorted(T.GOOD), 1):
        r = run_level(i, T.GOOD[lid])
        bad = [f"{x.msg}: {x.detail}" for x in r.results if not x.passed and not x.skipped] if r else ["ยกเลิก"]
        check(f"{lid} คำตอบถูก (SLMP จำลอง ~10 Hz) ได้ 3 ดาว", r and r.stars == 3, "; ".join(bad))
    r = run_level(1, lambda m, n, c: None)
    check("โปรแกรมเปล่า ด่าน 1 = 0 ดาว", r.stars == 0 and r.passed == 0, f"{r.passed}/{r.total}")
    w.grab().save(str(out / "empty_program.png"))

    before = scores.SCORE_FILE.read_bytes()
    cmd("CHECK")
    pump(0.8)
    key = next(it.key for it in w.panel.items_by_id.values() if getattr(it, "key", ""))
    check("ระหว่างตรวจกดอุปกรณ์ไม่ได้", w.panel.input_locked and not w.panel.key_down(key))
    w.disconnect_plc()
    pump(0.3)
    check("หลุดกลางคัน = ยกเลิก ไม่บันทึกคะแนน", w.levelp.runner is None and scores.SCORE_FILE.read_bytes() == before)
    check("หลังยกเลิกกดอุปกรณ์ได้ตามปกติ", not w.panel.input_locked)
    w.grab().save(str(out / "aborted.png"))
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
