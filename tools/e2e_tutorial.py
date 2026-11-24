"""E2E บทเรียนนำทาง บนหน้าต่างจริง + Mock PLC: เดินครบทุกขั้นแบบผู้ใช้จริง พร้อมภาพทุกขั้น
และตรวจว่าช่องที่เจาะคลิกผ่านได้ (QApplication.widgetAt ที่กลางช่อง = widget เป้าหมาย ไม่ใช่ overlay)

รัน:  .venv\\Scripts\\python.exe tools\\e2e_tutorial.py docs\\tutorial_test
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

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/tutorial_test")
out.mkdir(parents=True, exist_ok=True)
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


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def click_through(t, target):
    """กลางช่องที่เจาะ ต้องเป็น widget เป้าหมาย (หรือลูกของมัน) ไม่ใช่ overlay."""
    pump(0.3)
    if t.hole.isEmpty():
        return False
    g = w.mapToGlobal(t.hole.center())
    hit = QApplication.widgetAt(g)
    scr = app.primaryScreen().availableGeometry()
    pts = [type(g)(x, y) for x, y in ((8, w.height() // 2), (w.width() - 8, w.height() // 2), (w.width() // 2, 8))]
    pts = [p for p in pts if not t.hole.contains(p) and scr.contains(w.mapToGlobal(p))]
    outside = QApplication.widgetAt(w.mapToGlobal(pts[0])) if pts else None
    ok_in = hit is not None and (hit is target or target.isAncestorOf(hit))
    ok_out = outside is not None and (outside is t or t.isAncestorOf(outside))
    if not (ok_in and ok_out):
        chain, p = [], hit
        while p is not None:
            chain.append(type(p).__name__ + (f"#{p.objectName()}" if p.objectName() else ""))
            p = p.parentWidget()
        print("   ลำดับ parent:", " < ".join(chain), "| screen:", app.primaryScreen().availableGeometry(),
              "| win:", w.geometry())
        print("   widgetAt กลางช่อง:", type(hit).__name__, hit and hit.objectName(),
              "| นอกช่อง:", type(outside).__name__, "| hole:", t.hole)
    return ok_in and ok_out


def wait_step(t, i, limit=20):
    t0 = time.monotonic()
    while t.index != i and time.monotonic() - t0 < limit:
        pump(0.05)
    return t.index == i


def shot(name):
    pump(0.2)
    w.grab().save(str(out / f"{name}.png"))


try:
    w.set_split(False)
    t = w.start_tutorial()
    pump(0.5)
    check("เริ่ม: กล่องต้อนรับกลางจอ ไม่มีช่อง", t.index == 0 and t.hole.isEmpty())
    shot("t0_welcome")
    t.btn_next.click()

    pump(0.4)
    check("ขั้น 1: ช่องที่ combobox คลิกผ่านได้", click_through(t, w.cb_backend))
    shot("t1_backend")
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    check("เลือก Mock → ไปขั้นเชื่อมต่อเอง", wait_step(t, 2))

    check("ขั้น 2: ช่องที่ปุ่มเชื่อมต่อคลิกผ่านได้", click_through(t, w.btn_connect))
    shot("t2_connect")
    w.btn_connect.click()
    check("เชื่อมต่อ → ไปขั้นเปิดด่าน", wait_step(t, 3))

    check("ขั้น 3: ช่องที่ปุ่มเปิดด่าน (แท็บด่าน)", click_through(t, w.b_level_open) and w.ribbon.currentIndex() == 2)
    shot("t3_level")
    w.b_level_open.click()
    check("เปิดด่าน 1 → ไปขั้นกดปุ่มบนผัง", wait_step(t, 4))

    check("ขั้น 4: ช่องคลุมผังอุปกรณ์", click_through(t, w.panel))
    shot("t4_press")
    w.panel.key_down("1")
    pump(0.3)
    w.panel.key_up("1")
    check("กด Start → Y0 ค้าง → ไปขั้นกราฟ", wait_step(t, 5))

    check("ขั้น 5: ช่องที่ปุ่มแบ่งจอ", click_through(t, w.btn_split))
    shot("t5_split")
    w.btn_split.click()
    check("แบ่งจอ → ไปขั้นตรวจ", wait_step(t, 6))

    check("ขั้น 6: ช่องที่ปุ่มตรวจคำตอบ", click_through(t, w.levelp.btn_check))
    shot("t6_check")
    w.levelp.btn_check.click()
    check("ตรวจจบ (Mock = เฉลย) → ขั้นสุดท้าย", wait_step(t, len(t.steps) - 1, limit=60)
          and w.levelp.last_runner.stars == 3, f"{w.levelp.last_runner.passed}/{w.levelp.last_runner.total}")
    shot("t7_done")
    t.btn_next.click()
    pump(0.3)
    check("เสร็จสิ้น: ปิด overlay + จำว่าดูแล้ว", w.tutorial is None and state.load().get("tutorial_done") is True)
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
