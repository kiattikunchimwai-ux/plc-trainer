"""E2E M7 สื่อการสอน บนหน้าต่างจริง + Mock PLC (ด่านทำกับสำเนา levels/ — ไฟล์จริงไม่ถูกแตะ)

แท็บสื่อการสอน → วงจรต่อสาย (+PNG/PDF) → ใบความรู้ของปุ่ม Stop → บันทึกการกด Start/Stop
→ เคอร์เซอร์ A/B วัดเวลาบนกราฟ (+PNG/CSV) → เล่นซ้ำ → สร้างด่านจากการกด → ตรวจด้วย Mock ได้ 3 ดาว

รัน:  .venv\\Scripts\\python.exe tools\\e2e_teaching.py docs\\teaching_test
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
from plc_game.levels import rooms, scores  # noqa: E402
from plc_game.levels.engine import LEVEL_DIR  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.level_dock import LevelPanel  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/teaching_test")
out.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}
tmp = Path(tempfile.mkdtemp(prefix="plc_m7_"))
lvdir = tmp / "levels"
shutil.copytree(LEVEL_DIR, lvdir, ignore=shutil.ignore_patterns("_trash"))
real_before = sorted((p.name, p.stat().st_mtime_ns) for p in LEVEL_DIR.iterdir())
LevelPanel.folder = lvdir
rooms.create("e2e", lvdir)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

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
    pump(0.3)
    widget.grab().save(str(out / f"{name}.png"))


def y0():
    return w._history[-1][1].get("Y0") if w._history else None


try:
    w.open_level(0)
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.btn_connect.click()
    pump(1.0)
    w.ribbon.setCurrentIndex(w.ribbon.count() - 1)
    check("แท็บสื่อการสอน + เชื่อม Mock", w.ribbon.tabText(w.ribbon.currentIndex()) == "สื่อการสอน" and w.online)
    shot(w, "m0_tab")

    # ----- วงจรต่อสาย -----
    dlg = w.show_wiring()
    dlg.resize(1360, 760)
    pump(0.4)
    png, pdf = dlg._export("png", str(out / "wiring.png")), dlg._export("pdf", str(out / "wiring.pdf"))
    check("วงจรต่อสาย: X0/X1 → S/S, Y0 → โหลด + Export PNG/PDF",
          [t.addr for t in dlg.wiring.inputs] == ["X0", "X1"] and [t.addr for t in dlg.wiring.outputs] == ["Y0"]
          and Path(png).stat().st_size > 10_000 and Path(pdf).read_bytes()[:4] == b"%PDF")
    shot(dlg, "m1_wiring")
    dlg.close()

    # ----- ใบความรู้ -----
    w.panel.knowledge_requested.emit(w.panel.items_at("X1")[0])     # = คลิกขวาปุ่ม Stop → 📘 ใบความรู้
    k = w._know_dlg
    k.resize(1080, 760)
    pdf2 = k.export("all", str(out / "handbook.pdf"))
    txt = k.view.toPlainText()
    check("ใบความรู้ของปุ่ม Stop (X1) + PDF รวมเล่ม", k.kind == "pushbutton" and "— Stop" in txt and "X1" in txt
          and Path(pdf2).stat().st_size > 50_000, f"{Path(pdf2).stat().st_size // 1024} KB")
    shot(k, "m2_knowledge")
    k.close()

    # ----- บันทึกการกด -----
    w.set_split(True)
    w.chart.clear()
    w.b_rec.click()
    pump(0.6)
    w.panel.key_down("1")                         # ปุ่ม Start (คีย์ลัด 1)
    pump(0.3)
    w.panel.key_up("1")
    pump(1.6)
    on_after_start = y0()
    w.panel.drive_input("X1", 1)                  # Stop
    pump(0.3)
    w.panel.drive_input("X1", 0)
    pump(1.2)
    w.b_rec.click()
    m = w.macro.macro
    check("บันทึก Start/Stop + เห็น Y0 ตอบ", m is not None and [e.addr for e in m.inputs] == ["X0", "X0", "X1", "X1"]
          and [e.value for e in m.outputs if e.addr == "Y0"] == [0, 1, 0] and on_after_start == 1,
          m and f"{len(m.inputs)} กด, {len(m.outputs)} output")
    mp = w.save_macro(str(out / "start_stop.plcmacro"))
    check("บันทึกไฟล์ .plcmacro", mp and Path(mp).exists())

    # ----- เคอร์เซอร์ A/B -----
    w.b_ab.click()
    es = w.chart.edges()
    rise = [t for t in es]
    w.chart.set_ab_pos(rise[0] + 0.03, rise[-1] - 0.03)
    w.chart._snap(w.chart._ab["A"][0])
    w.chart._snap(w.chart._ab["B"][0])
    a, b = w.chart.ab_pos()
    w.chart.focus_time(a, b)
    check("A/B ดูดเข้าขอบ (Start → Stop) + Δt", a in es and b in es and 1.5 < b - a < 2.5 and "Δt" in w.chart.lbl_ab.text(),
          w.chart.ab_text().splitlines()[0])
    shot(w, "m3_ab_cursor")
    pc, cc = w.export_chart("png", str(out / "chart.png")), w.export_chart("csv", str(out / "chart.csv"))
    check("Export กราฟ PNG + CSV", Path(pc).exists() and Path(cc).read_text(encoding="utf-8").count("\n") > 20)
    w.b_ab.click()
    w.btn_pause.setChecked(False)

    # ----- เล่นซ้ำ -----
    pump(0.5)
    w._history.clear()
    w.b_play.click()
    seen = []
    t0 = time.monotonic()
    while w.macro.state == "play" and time.monotonic() - t0 < 15:
        pump(0.05)
        seen.append(y0())
    check("เล่นซ้ำ: มอเตอร์ติดแล้วดับตามการกด", 1 in seen and seen[-1] == 0 and not w.b_play.isChecked())

    # ----- สร้างด่านจากการกด -----
    w.b_mlevel.click()
    pump(0.5)
    ed = w._level_editor
    ed.resize(1280, 800)
    d = ed.cur
    probs = ed.check()
    check("สร้างด่านจากการกด → เปิดในตัวแก้ไข (ยังไม่บันทึก)", d is not None and d.path is None and probs == []
          and d.panel == "01_self_hold.plcpanel", "; ".join(probs) or ed.lbl_status.text()[-60:])
    ed.ed_title.setText("ด่าน 15: Start/Stop จากการกด")
    ed._mark()
    shot(ed, "m4_macro_level")
    ed.b_open.click()
    pump(0.8)
    w.levelp.btn_check.click()
    t0 = time.monotonic()
    pump(0.5)
    while w.levelp.busy and time.monotonic() - t0 < 60:
        pump(0.1)
    r = w.levelp.last_runner
    check("ด่านที่สร้างจากการกด ตรวจด้วย Mock ได้ 3 ดาว", r is not None and r.stars == 3 and r.total >= 3,
          r and f"{r.passed}/{r.total}")
    shot(w, "m5_checked")
    ed = w.open_level_editor()
    ed.delete()
    ed.close()
    pump(0.3)
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
