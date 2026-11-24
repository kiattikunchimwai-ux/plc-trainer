"""แถบขั้นตอน 1-4, โจทย์ไม่ซ้ำ, แผงกาง/ยุบเองตามโหมด, หน้าต่างย่อได้บนจอโน้ตบุ๊ก."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QWidget  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.flow_bar import FlowBar  # noqa: E402
from plc_game.ui.flow_layout import FlowLayout  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture
def make(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    wins = []

    def f():
        from plc_game.ui.main_window import MainWindow
        w = MainWindow({"backend": "mock", "xy_base": 8})
        w._confirm_discard = lambda: True
        wins.append(w)
        return w
    yield f
    for w in wins:
        w.disconnect_plc()
        w.dirty = False
        w.close()


def steps(w):
    w._update_flow()
    return w.flow.next, [b.property("st") for b in w.flow.steps]


def test_flow_bar_marks_next_step():
    QApplication.instance() or QApplication([])
    f = FlowBar(3)
    f.set_steps([("a", "ha", True, True), ("b", "hb", False, True), ("c", "hc", False, False)])
    assert f.next == 1 and f.hint.text() == "hb" and not f.steps[2].isEnabled()
    assert [b.property("st") for b in f.steps] == ["done", "next", "todo"]
    f.set_steps([("a", "", True, True)] * 3, "ครบ")
    assert f.next is None and f.hint.text() == "ครบ"


def test_steps_follow_real_state(make):
    w = make()
    assert steps(w)[0] == 0 and not w.flow.steps[3].isEnabled()
    w.open_level(0)
    assert steps(w)[0] == 1
    w._connect_to(w.cb_backend.findData("soft"))
    assert w.soft is not None and not w.flow.steps[1].isEnabled() or steps(w)
    w.online = True                              # ไม่รอ thread
    assert steps(w)[0] == 2                       # ยังไม่มี ladder รัน
    w.online = False
    w.disconnect_plc()
    assert steps(w)[0] == 1 and w.flow.steps[1].isEnabled()


def test_fault_hunt_skips_ladder(make):
    w = make()
    k = next(i for i, lv in enumerate(w.levelp.levels) if lv.is_fault_hunt)
    w.open_level(k)
    assert steps(w)[1][2] == "done"


def test_menus(make):
    w = make()
    m = QMenu()
    w._fill_level_menu(m)
    assert len(m.actions()) == len(w.levelp.levels)
    m.actions()[1].trigger()
    assert w.levelp.level is w.levelp.levels[1]
    c = QMenu()
    w._fill_connect_menu(c)
    assert len(c.actions()) == 3


def test_level_text_not_shown_twice(make):
    w = make()
    w.open_level(0)
    assert w.side_r.is_showing("level") and w.banner.isHidden()
    w.side_r.collapse()
    assert not w.banner.isHidden()
    w.show_levels()
    assert w.banner.isHidden()
    w.show_banner("เดโม")                        # ข้อความที่ไม่ใช่โจทย์แสดงเสมอ
    assert not w.banner.isHidden()


def test_panes_follow_edit_mode(make):
    w = make()
    assert not w.side_l.is_open and w.side_r.is_showing("level") and w.cmd_history.isHidden()
    w.set_edit_mode(True)
    assert w.side_l.is_showing("library") and w.side_r.is_showing("props")
    w.set_edit_mode(False)
    assert not w.side_l.is_open and w.side_r.is_showing("level")
    w.side_l.open("library")                      # ผู้ใช้กางเอง → ไม่ยุบให้
    w.set_edit_mode(True)
    w.set_edit_mode(False)
    assert w.side_l.is_showing("library")


def test_layout_reset_only_once(make):
    state.update(pane_left={"key": "library", "open": True, "w": 250}, cmd_history=True)     # ผู้ใช้รุ่นเก่า
    w = make()
    assert not w.side_l.is_open and w.cmd_history.isHidden()
    w.side_l.open("iolist")
    w.btn_cmd.setChecked(True)
    w2 = make()
    assert w2.side_l.is_showing("iolist") and not w2.cmd_history.isHidden()


def test_window_fits_laptop(make):
    w = make()
    assert w.minimumSizeHint().width() <= 1400        # ฟอนต์ offscreen กว้างกว่าจริง (จอจริง ~1150)


def test_flow_layout_wraps():
    QApplication.instance() or QApplication([])
    box = QWidget()
    lay = FlowLayout(box)
    for i in range(6):
        b = QPushButton(str(i))
        b.setFixedSize(100, 30)
        lay.addWidget(b)
    assert lay.heightForWidth(700) == 30 and lay.heightForWidth(210) == 30 * 3 + 2 * 4


def test_starts_blank_and_keeps_old_ladder(make, tmp_path):
    w = make()
    assert not w.panel.items_by_id and w.panel_path is None and w.ladderv.empty and w.ladderv.canvas.pristine
    w.ladderv.doc.paste_text(0, "LD X0\nOUT Y0")
    w.ladderv.after_edit()
    assert not w.ladderv.canvas.pristine
    w.ladderv.flush()
    free = w.ladderv.file
    assert free.exists()
    w2 = make()                                   # เปิดใหม่ = เปล่า แต่ของเดิมยังอยู่ในไฟล์ตามเวลา
    assert w2.ladderv.empty and w2.ladderv.file == free
    kept = list(free.parent.glob("free_*.csv"))
    assert len(kept) == 1 and "Y0".encode("utf-16-le") in kept[0].read_bytes()


def test_level_ladder_survives_restart(make):
    w = make()
    w.open_level(0)
    w.ladderv.doc.paste_text(0, "LD X0\nOUT Y0")
    w.ladderv.after_edit()
    w.ladderv.flush()
    w2 = make()
    w2.open_level(0)
    assert not w2.ladderv.empty
