"""E2E กับ GX Simulator3 จริง (backend = slmp)

ก่อนรัน:
  - ใน GX Works3 ต้องเปิดโปรเจกต์ RCPU ที่มี ladder self-hold
    (X0 ต่อขนานกับ Y0 แล้วอนุกรมกับ /X1 ไปที่ Y0)
  - กด Start Simulation และ CPU ต้องอยู่ใน RUN

รัน:  .venv\\Scripts\\python.exe tools\\e2e_gx_slmp.py docs\\gx_test\\e2e_slmp.png
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/gx_test/e2e_slmp.png")
out.parent.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)

cfg = load_config()
cfg["backend"] = "slmp"
w = MainWindow(cfg)
w.resize(1600, 950)
w.show()
w.set_split(False)
results = []
last = {}


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


def run_level(n):
    cmd(f"LEVEL {n}")
    pump(0.8)
    cmd("CHECK")
    t0 = time.monotonic()
    while w.levelp.runner is not None and time.monotonic() - t0 < 90:
        pump(0.05)
    return w.levelp.last_runner, time.monotonic() - t0


try:
    i = w.cb_backend.findData("slmp")
    if i >= 0:
        w.cb_backend.setCurrentIndex(i)
    w.connect_plc()
    pump(2.0)
    check("เชื่อมต่อ GX Simulator3 ผ่าน SLMP", w.poller is not None and w._n_snap > 5, f"snapshots={w._n_snap}")
    w.poller.snapshot.connect(lambda s, t: last.update(s))

    # กดปุ่มจากโปรแกรมแล้วดูผลจาก ladder จริง
    w._write("X1", 1); pump(0.3); w._write("X1", 0); pump(0.3)
    w._write("X0", 1); pump(0.4)
    on = last.get("Y0")
    w._write("X0", 0); pump(0.6)
    hold = last.get("Y0")
    w._write("X1", 1); pump(0.4)
    off = last.get("Y0")
    w._write("X1", 0); pump(0.3)
    check("กด X0 → Y0 ติด / ปล่อยแล้วค้าง / กด X1 → ดับ", (on, hold, off) == (1, 1, 0), f"{on},{hold},{off}")

    r, dt = run_level(1)
    check("ด่าน 1 กับ ladder จริงได้ 3 ดาว", r is not None and r.stars == 3,
          f"{getattr(r, 'passed', '?')}/{getattr(r, 'total', '?')} ใน {dt:.1f}s")
    w.grab().save(str(out))

    r3, dt3 = run_level(3)
    check("ด่าน 3 (Timer) ต้องไม่ผ่านด้วย ladder self-hold", r3 is not None and r3.stars < 3,
          f"{getattr(r3, 'passed', '?')}/{getattr(r3, 'total', '?')} ใน {dt3:.1f}s")
    w.grab().save(str(out.with_name(out.stem + "_level3.png")))
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
