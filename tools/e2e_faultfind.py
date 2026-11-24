"""E2E ด่าน 14 หาจุดเสีย บนหน้าต่างจริง + Mock PLC (ladder ในตัว Mock = เฉลยด่าน 3):
เปิดด่าน → เริ่มหาจุดเสีย → กด Start ดูอาการ → เมนูคลิกขวา → ทายผิด 1 ครั้ง → ทายถูก → 2★ + เฉลย → หยุด/ล้าง

รัน:  .venv\\Scripts\\python.exe tools\\e2e_faultfind.py docs\\faultfind_test\\hunt.png
"""
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QLocale, QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/faultfind_test/hunt.png")
out.parent.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 4)

cfg = load_config()
cfg["backend"] = "mock"
w = MainWindow(cfg)
w.resize(1600, 950)
w.show()
w.set_split(True)
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


try:
    classroom.upsert_student("E2E01", "ทดสอบ อัตโนมัติ")
    w._set_student("E2E01")
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.connect_plc()
    pump(1.0)
    w.poller.snapshot.connect(lambda s, t: last.update(s))
    cmd("LEVEL 14")
    pump(0.8)
    check("เปิดด่าน 14", w.levelp.level.id == "14_fault_find" and "หาจุดเสีย" in w.levelp.btn_check.text())
    cmd("CHECK")
    pump(0.5)
    h = w.levelp.hunt
    broken = [it for it in w.panel.fault_items() if it.fault]
    check("เริ่มหาจุดเสีย: เสีย 1 จุด ซ่อนป้าย ⚡", h is not None and len(broken) == 1 and w.panel.sc.faults_hidden,
          f"คำตอบ (ซ่อน) = {h.answer_text() if h else '-'}")

    # นักเรียนลองกด Start แล้วดูอาการ
    w._write("X0", 1); pump(0.4); w._write("X0", 0); pump(3.6)
    sym = {k: last.get(k) for k in ("X0", "X1", "Y0", "Y1")}
    motors = {it.label: getattr(it, "speed", None) for it in w.panel.fault_items() if "มอเตอร์" in it.label or "ปั๊ม" in it.label}
    print("   อาการหลังกด Start 4 วินาที:", sym, "| มอเตอร์:", {k: round(v or 0, 2) for k, v in motors.items()})
    w.grab().save(str(out.with_name(out.stem + "_symptom.png")))

    # เมนูคลิกขวา (สร้างเมนูเดียวกับที่ contextMenuEvent ใช้ แล้วถ่ายภาพ)
    lab, code = h.answer
    target = broken[0]
    m = QMenu(w.panel)
    sub = w.panel.guess_menu(m, target)
    m.addSeparator()
    m.addAction("✎ สลับเป็นโหมดแก้ไขผัง")
    pos = w.panel.mapToGlobal(w.panel.mapFromScene(target.sceneBoundingRect().center()))
    m.popup(pos)
    pump(0.3)
    sub.popup(pos + QPoint(m.width() - 6, 0))
    pump(0.4)
    shot = app.primaryScreen().grabWindow(0, pos.x() - 380, pos.y() - 200, 1100, 520)
    shot.save(str(out.with_name(out.stem + "_menu.png")))
    texts = [a.text() for a in sub.actions()]
    check("เมนูคลิกขวามีอาการทุกแบบของอุปกรณ์", texts == list(target.FAULTS.values()), " | ".join(texts))
    sub.close()
    m.close()

    # ทายผิด 1 ครั้ง (อุปกรณ์อื่น) ผ่านเมนู แล้วทายถูก
    other = next(it for it in w.panel.fault_items() if it.label != lab)
    m1 = QMenu()
    next(a for a in w.panel.guess_menu(m1, other).actions()).trigger()
    pump(0.3)
    check("ทายผิด → นับครั้ง เหลือ 2 + เสียง fail", len(h.results) == 1 and not h.results[0].passed and h.left == 2
          and w.sounds.played[-1:] == ["fail"], h.results[0].detail)
    m2 = QMenu()
    acts = {a.text(): a for a in w.panel.guess_menu(m2, target).actions()}
    acts[target.FAULTS[code]].trigger()
    pump(0.5)
    check("ทายถูก → 2 ดาว + บันทึกคะแนน", h.found and h.stars == 2
          and scores.best_stars("E2E01").get("14_fault_find") == 2)
    check("เฉลย: แสดงป้าย ⚡ + คำอธิบาย + ปิดเมนูทาย", not w.panel.sc.faults_hidden and not w.panel.guess_enabled
          and "สังเกตอย่างไร" in w.levelp.ai.toPlainText())
    w.grab().save(str(out))

    cmd("CHECK")
    pump(0.3)
    cmd("STOP")
    pump(0.3)
    check("หยุดกลางคัน → ล้างจุดเสีย", w.levelp.hunt is None and not any(it.fault for it in w.panel.fault_items()))
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
