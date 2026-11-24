"""M7 สื่อการสอน: ใบความรู้, แบบวงจรต่อสาย, กราฟ Export + เคอร์เซอร์ A/B, บันทึก/เล่นซ้ำการกด → ด่าน."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import LEVEL_DIR, scores  # noqa: E402
from plc_game.panel import PanelDoc  # noqa: E402
from plc_game.panel.catalog import CATALOG  # noqa: E402
from plc_game.panel.knowledge import ANNOTATION, KNOW, handbook_html, sheet_html  # noqa: E402
from plc_game.panel.macro import Macro, MacroEvent, to_draft  # noqa: E402
from plc_game.panel.model import DeviceSpec  # noqa: E402
from plc_game.panel.wiring import build, to_text  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402

from test_levels import run  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---------------- ใบความรู้ ----------------
def test_every_device_has_knowledge_sheet():
    missing = [k for k in CATALOG if k not in ANNOTATION and k not in KNOW]
    assert missing == []
    for k in CATALOG:
        if k in ANNOTATION:
            continue
        h = sheet_html(k)
        assert CATALOG[k].name.split(" ")[0] in h and "หลักการทำงาน" in h and "การต่อสายกับ PLC" in h
        if CATALOG[k].slots():
            assert "สัญญาณ I/O" in h
    book = handbook_html()
    assert book.count("page-break-after") >= len(KNOW)
    # ใช้ค่าจริงของอุปกรณ์บนผัง
    assert "X7" in sheet_html("pushbutton", {"label": "Stop", "address": "X7"})


# ---------------- วงจรต่อสาย ----------------
def _d(kind, **props):
    p = dict(CATALOG[kind].defaults)
    p.update(props)
    return DeviceSpec.new(kind, **p)


def test_wiring_rules():
    devs = [_d("pushbutton", label="Start", address="X0"),
            _d("pushbutton", label="Stop", address="X1", contact="NC"),
            _d("sensor", label="PS1", address="X2", output="pnp"),
            _d("lamp", label="ไฟเดิน", address="Y0"),
            _d("motor", label="M1", address="Y0"),
            _d("valve", label="SOL", address="Y1"),
            _d("display", label="T0", address="TN0"),
            _d("pushbutton", label="M-btn", address="M5")]
    w = build(devs)
    assert [t.addr for t in w.inputs] == ["X0", "X1", "X2"]
    assert [t.symbol for t in w.inputs] == ["no", "nc", "sensor"]
    assert w.common == "source" and w.ss_to == "0V" and w.switch_from == "+24V"     # PNP ล้วน
    y0 = w.outputs[0]
    assert y0.symbol == "contactor" and y0.parallel == ["ไฟเดิน"]                     # โหลดหลัก = มอเตอร์
    assert w.outputs[1].symbol == "coil"
    assert any("M5" in o for o in w.others) and any("TN0" in o for o in w.others)
    w2 = build(devs + [_d("sensor", label="PS2", address="X3", output="npn")])
    assert w2.common == "sink" and any("NPN และ PNP" in x for x in w2.warnings)
    assert "S/S → 0V" in to_text(w)


def test_wiring_all_scenes_render(app, tmp_path):
    from plc_game.ui.wiring_view import WiringDialog, export_pdf, export_png
    from plc_game.panel.model import PanelDoc as P
    import glob
    for f in glob.glob(str(LEVEL_DIR.parent / "panels" / "*.plcpanel")):
        build(P.load(f).devices)
    w = build(PanelDoc.load(LEVEL_DIR / "06_sorting.plcpanel").devices) if (LEVEL_DIR / "06_sorting.plcpanel").exists() \
        else build(PanelDoc.load(LEVEL_DIR.parent / "panels" / "sorting.plcpanel").devices)
    assert export_png(w, tmp_path / "w.png", "sorting") and (tmp_path / "w.png").stat().st_size > 10_000
    export_pdf(w, tmp_path / "w.pdf", "sorting")
    assert (tmp_path / "w.pdf").read_bytes()[:4] == b"%PDF"
    dlg = WiringDialog(w, "sorting")
    assert dlg._export("png", str(tmp_path / "d.png")) and (tmp_path / "d.png").exists()
    dlg.close()


# ---------------- กราฟ ----------------
def test_chart_ab_and_export(app, tmp_path):
    from plc_game.ui.chart_widget import ChartWidget
    c = ChartWidget()
    c.resize(800, 400)
    c.set_signals(["X0", "Y0"], ["TN0"])
    for i in range(41):                          # Y0 ขึ้นที่ 1.0 s, X0 ขึ้นที่ 0.5 s
        t = i * 0.05
        c.add_snapshot({"X0": int(t >= 0.5), "Y0": int(t >= 1.0), "TN0": int(t * 10)}, t)
    c._redraw()
    assert 0.5 in c.edges() and 1.0 in c.edges()
    got = []
    c.ab_changed.connect(got.append)
    c.set_ab(True)
    c.set_ab_pos(0.52, 0.98)
    c._snap(c._ab["A"][0])                       # ใกล้ขอบ → ดูดเข้าขอบ
    c._snap(c._ab["B"][0])
    a, b = c.ab_pos()
    assert (a, b) == (pytest.approx(0.5), pytest.approx(1.0))
    assert "Δt = 0.500 s" in c.ab_text() and "Y0=1" in c.ab_text() and got
    c.set_ab(False)
    assert c.ab_text() == "" and not c.lbl_ab.isVisible()
    csv = c.to_csv()
    lines = csv.lstrip("﻿").splitlines()
    assert lines[0] == "เวลา (s),X0,Y0,TN0" and lines[-1] == "2.000,1,1,20" and len(lines) == 42
    c.export_csv(tmp_path / "c.csv")
    assert c.export_png(tmp_path / "c.png") and (tmp_path / "c.png").exists()
    c._timer.stop()                              # ให้ Qt ลบเอง ไม่ปล่อยให้ GC ของ Python เก็บทีหลัง (pyqtgraph ค้างตอนปิด)
    c.deleteLater()
    app.processEvents()


# ---------------- บันทึกการกด ----------------
def test_macro_json_and_steps(tmp_path):
    m = Macro("ทดสอบ", "01_self_hold.plcpanel", {"X0": 0, "X1": 0}, [
        MacroEvent(0.0, "Y0", 0, io="out"),
        MacroEvent(1.0, "X0", 1), MacroEvent(1.06, "Y0", 1, io="out"), MacroEvent(1.4, "X0", 0),
        MacroEvent(3.0, "X1", 1), MacroEvent(3.05, "Y0", 0, io="out"), MacroEvent(3.3, "X1", 0)], 4.0)
    m.save(tmp_path / "a.plcmacro")
    m2 = Macro.load(tmp_path / "a.plcmacro")
    assert m2.events == m.events and m2.idle == m.idle and m2.duration == 4.0
    ops = [(op, p) for op, p, _ in m.to_steps()]
    assert ops[:3] == [("set", "X0 1"), ("expect", "Y0 = 1 within 0.6"), ("wait", "0.3")]
    assert ("set", "X1 1") in ops and ("expect", "Y0 = 0 within 0.5") in ops
    with pytest.raises(ValueError):
        Macro.from_json('{"x": 1}')


def test_record_then_level_grades_3_stars(app, tmp_path):
    """ครูบันทึกการกดบนผังด่าน 1 (Mock = ladder ที่ถูก) → สร้างด่าน → ด่านนั้นตรวจ ladder ถูกได้ 3 ดาว."""
    from plc_game.levels.editor import load_drafts
    from plc_game.plc.device import parse_device
    from plc_game.plc.mock_client import MockPLC
    from plc_game.ui.macro_ctl import MacroController
    from plc_game.ui.panel.view import PanelView
    clock = [0.0]
    plc = MockPLC(clock=lambda: clock[0], auto_scan=False)
    plc.connect()
    view = PanelView()
    view.load_doc(PanelDoc.load(LEVEL_DIR / "01_self_hold.plcpanel"))
    view.set_run_mode(True)
    ctl = MacroController(view)
    ctl.clock = lambda: clock[0]
    view.request_write.connect(lambda a, v: (plc.write_bits(a, [v]), ctl.on_write(a, v)))
    for a, v, _w in view.input_states():
        plc.write_bits(a, [v])
    names = view.addresses()

    def tick(sec):
        end = clock[0] + sec
        while clock[0] < end - 1e-9:
            plc.scan()
            snap = {n: plc.read_bits(n, 1)[0] for n in names if parse_device(n).is_bit}
            view.apply_snapshot(snap)
            ctl.on_snapshot(snap)
            clock[0] += 0.05

    assert ctl.start_record("01_self_hold.plcpanel") and ctl.state == "rec"
    tick(0.5)
    view.drive_input("X0", 1)
    tick(0.3)
    view.drive_input("X0", 0)
    tick(1.5)
    view.drive_input("X1", 1)
    tick(0.3)
    view.drive_input("X1", 0)
    tick(1.0)
    m = ctl.stop_record()
    assert m is not None and [e.addr for e in m.inputs] == ["X0", "X0", "X1", "X1"]
    assert [e.value for e in m.outputs if e.addr == "Y0"] == [0, 1, 0]
    d = to_draft(m, load_drafts(), "01_self_hold.plcpanel")
    assert d.problems() == [], d.problems()
    lv = d.build()
    assert lv.checks == 4                            # expect ×2 + hold ×2 (ค้างหลังปล่อยปุ่ม)
    r = run(lv)                                       # ladder ถูก (Mock) → 3 ดาว
    assert r.stars == 3, [x.detail for x in r.results if not x.passed]

    def no_hold(mem, now, ctx):                       # ladder ผิด: ไม่มี self-hold
        mem["Y"][0] = mem["X"][0] and not mem["X"][1]
    assert run(lv, program=no_hold).stars < 3

    # เล่นซ้ำ: ปุ่มบนผังถูกสั่งตามเวลา
    seen = []
    view.request_write.connect(lambda a, v: seen.append((a, v)))
    assert ctl.play(m) and ctl.state == "play"
    t0 = __import__("time").monotonic()
    while ctl.state == "play" and __import__("time").monotonic() - t0 < 10:
        app.processEvents()
    assert ctl.state == "idle" and [x for x in seen if x[0] == "X0"][-2:] == [("X0", 1), ("X0", 0)]
    assert ("X1", 1) in seen


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    import shutil
    from plc_game.ui.level_dock import LevelPanel
    lvdir = tmp_path / "levels"
    shutil.copytree(LEVEL_DIR, lvdir, ignore=shutil.ignore_patterns("_trash"))
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    monkeypatch.setattr(LevelPanel, "folder", lvdir)
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def cmd(win, text):
    win.cmd_input.setText(text)
    win._on_command()


def test_main_window_teaching_tab(app, win, tmp_path):
    from plc_game.panel.macro import Macro, MacroEvent
    win.open_level(0)
    assert win.ribbon.tabText(win.ribbon.count() - 1) == "สื่อการสอน"
    dlg = win.show_wiring()
    assert [t.addr for t in dlg.wiring.inputs] == ["X0", "X1"] and dlg.title == "01_self_hold"
    dlg.close()
    item = win.panel.items_at("X1")[0]
    win.panel.knowledge_requested.emit(item)          # คลิกขวา → 📘 ใบความรู้ (ใช้ได้ในโหมดใช้งาน)
    k = win._know_dlg
    txt = k.view.toPlainText()
    assert k.kind == "pushbutton" and "Push button) — Stop" in txt and "X1" in txt
    k.close()
    win.set_ab_cursors(True)
    assert win.chart.ab_on and win.chart.paused and win.b_ab.isChecked()
    win.set_ab_cursors(False)
    assert win.export_chart("csv", str(tmp_path / "x.csv")) and (tmp_path / "x.csv").exists()
    # การกด → ด่านใหม่ในตัวแก้ไข (ยังไม่บันทึก)
    win.macro.macro = Macro("กด Start", "01_self_hold.plcpanel", {"X0": 0, "X1": 0},
                            [MacroEvent(0, "Y0", 0, io="out"), MacroEvent(0.5, "X0", 1),
                             MacroEvent(0.55, "Y0", 1, io="out"), MacroEvent(0.8, "X0", 0)], 2.0)
    assert win.save_macro(str(tmp_path / "m.plcmacro")) and win.open_macro(str(tmp_path / "m.plcmacro"))
    d = win.macro_to_level()
    ed = win._level_editor
    assert d is not None and ed.cur is d and d.path is None and d.panel == "01_self_hold.plcpanel"
    assert ed.check() == []
    ed.dirty = False
    ed.close()
    # บันทึกขณะตรวจไม่ได้ / ระหว่างสอบสร้างด่านไม่ได้
    cmd(win, "REC")
    assert win.macro.state == "rec" and win.b_rec.text().startswith("⏹")
    cmd(win, "REC")
    assert win.macro.state == "idle"
