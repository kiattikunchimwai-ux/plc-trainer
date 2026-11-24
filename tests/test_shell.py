"""R1: แถบไอคอนข้างจอ — กาง/ยุบ/จำสถานะ, PaneHandle, ยุบ Ribbon, MainWindow สร้างได้."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QSplitter, QWidget  # noqa: E402

from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402
from plc_game.ui.shell.sidebar import PaneHandle, SideDock  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    return tmp_path


def make_side(app):
    sp = QSplitter()
    side = SideDock("left", sp, 0)
    sp.addWidget(side.pane)
    sp.addWidget(QWidget())
    sp.addWidget(QWidget())
    side.add("a", "A", "หน้า A", QLabel("a"))
    side.add("b", "B", "หน้า B", QLabel("b"))
    sp.resize(1000, 600)
    return side


def test_click_opens_click_again_collapses(app, tmp_state):
    s = make_side(app)
    s.bar.clicked.emit("a")
    assert s.is_showing("a") and s.bar.buttons["a"].isChecked()
    s.bar.clicked.emit("b")                       # คลิกไอคอนอื่น = สลับหน้า (ยังกางอยู่)
    assert s.is_showing("b") and not s.bar.buttons["a"].isChecked()
    s.bar.clicked.emit("b")                       # คลิกซ้ำ = ยุบ
    assert not s.is_open and s.pane.isHidden()
    assert not any(b.isChecked() for b in s.bar.buttons.values())


def test_state_remembered(app, tmp_state):
    s = make_side(app)
    s.open("b")
    s.save()
    s2 = make_side(app)
    s2.restore()
    assert s2.is_showing("b")
    s2.collapse()
    s2.save()
    s3 = make_side(app)
    s3.restore()
    assert not s3.is_open and s3.current == "b"


def test_pane_handle_and_badge(app, tmp_state):
    s = make_side(app)
    h = PaneHandle(s, "b")
    assert not h.isVisible()
    s.bar.set_badge("b", True)
    assert s.bar.has_badge("b")
    h.show()
    assert h.isVisible() and not s.bar.has_badge("b")      # เปิดดูแล้ว badge หาย
    h.hide()
    assert not s.is_open


def test_main_window_shell(app, tmp_state):
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    assert not w.side_l.is_open and w.side_r.is_showing("level")   # ครั้งแรก: โล่ง เหลือแผงด่าน
    w.show_iolist()
    assert w.d_iolist.isVisible() and w.side_l.current == "iolist"
    w.show_levels()
    assert w.d_level.isVisible()
    w.side_l.collapse()
    w.set_edit_mode(True)                                       # แก้ไขผัง → เปิดแผงอุปกรณ์ให้เอง
    assert w.side_l.is_showing("library") and w.btn_edit.isChecked() and not w.btn_run.isChecked()
    w.set_edit_mode(False)
    assert w.btn_run.isChecked()
    w.set_ribbon_collapsed(True)
    assert w.ribbon.height() < 60 and state.load()["ribbon_collapsed"] is True
    w.set_ribbon_collapsed(False)
    assert w.ribbon.height() >= w.RIBBON_H
    w.log("ข้อความทดสอบ")
    w.btn_cmd.setChecked(False)
    assert w.cmd_history.isHidden() and w.lbl_last.text() == "ข้อความทดสอบ"
    w.dirty = False
    w.close()


def _pump_until(app, cond, limit=3.0):
    import time
    end = time.monotonic() + limit
    while time.monotonic() < end and not cond():
        app.processEvents()
        time.sleep(0.01)
    return cond()


def test_switch_panel_while_online_rewrites_inputs(app, tmp_state):
    """เปลี่ยนผังขณะเชื่อมต่อ: ค่า Input ของผังใหม่ (อุณหภูมิเตา D0) ต้องทับค่าเก่าที่ค้างใน PLC."""
    from plc_game.levels import LEVEL_DIR
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        w.connect_plc()
        assert _pump_until(app, lambda: w.online)
        cli = w.poller.client
        cli.write_words("D0", [600])                       # ค่าค้างจากผังก่อนหน้า (เช่น VFD)
        w._load_panel(LEVEL_DIR / "11_oven.plcpanel")
        assert _pump_until(app, lambda: cli.read_words("D0", 1)[0] == 120), cli.read_words("D0", 1)
    finally:
        w.disconnect_plc()
        w.dirty = False
        w.close()
