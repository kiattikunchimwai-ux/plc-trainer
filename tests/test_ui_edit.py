"""M5: จัดแนว / กระจายระยะ / ขยับด้วยลูกศร / ค้นหาใน Tool Palette / ใช้ล่าสุด."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.panel.catalog import CATALOG  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    return tmp_path


def view_with(app, *xy, kind="lamp"):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=[DeviceSpec.new(kind, x, y) for x, y in xy]))
    v.set_run_mode(False)
    items = list(v.items_by_id.values())
    for it in items:
        it.setSelected(True)
    return v, items


def box(v, it):
    return v._box(it)


def test_align_left_and_undo(app):
    v, items = view_with(app, (0, 0), (100, 40), (230, 80))
    before = [(it.spec.x, it.spec.y) for it in items]
    assert v.align("left") == 3
    lefts = {round(box(v, it).left(), 3) for it in items}
    assert len(lefts) == 1
    assert [it.spec.y for it in items] == [b[1] for b in before]     # แนวตั้งไม่ขยับ
    v.do_undo()
    assert sorted((it.spec.x, it.spec.y) for it in v.items_by_id.values()) == sorted(before)


def test_align_centers_mixed_sizes(app):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=[DeviceSpec.new("lamp", 0, 0), DeviceSpec.new("motor", 200, 37)]))
    v.set_run_mode(False)
    items = list(v.items_by_id.values())
    for it in items:
        it.setSelected(True)
    v.align("vcenter")
    cs = [box(v, it).center().y() for it in items]
    assert abs(cs[0] - cs[1]) < 0.01


def test_align_needs_two(app):
    v, items = view_with(app, (0, 0))
    assert v.align("left") == 0


def test_distribute_equal_gaps(app):
    v, items = view_with(app, (0, 0), (60, 0), (400, 0), (500, 0))
    assert v.distribute("h") == 4
    bs = sorted((box(v, it) for it in items), key=lambda b: b.left())
    gaps = [round(bs[i + 1].left() - bs[i].right(), 3) for i in range(3)]
    assert max(gaps) - min(gaps) < 0.01
    assert round(bs[0].left()) == round(box(v, items[0]).left())    # ชิ้นปลายไม่ขยับ


def test_arrow_nudge_and_select_all(app):
    v, items = view_with(app, (0, 0), (100, 0))
    v.sc.clearSelection()
    v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier))
    assert len(v.selected_items()) == 2
    v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    assert [it.spec.x for it in items] == [v.sc.snap, 100 + v.sc.snap]
    v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier))
    assert [it.spec.y for it in items] == [1, 1]
    v.flush_commit()
    v.do_undo()
    assert sorted(it.spec.x for it in v.items_by_id.values()) == [0, 100]


def test_arrows_do_nothing_in_run_mode(app):
    v, items = view_with(app, (0, 0))
    v.set_run_mode(True)
    assert not v.nudge(20, 0)
    assert items[0].spec.x == 0


def test_every_kind_has_description():
    missing = [k for k, info in CATALOG.items() if not info.desc]
    assert not missing, f"ไม่มีคำอธิบาย: {missing}"


def test_palette_search_and_recent(app, tmp_state):
    from plc_game.ui.panel.library_dock import RECENT, LibraryPanel
    lib = LibraryPanel()
    assert lib.cats[RECENT].isHidden()                      # ยังไม่มีของใช้ล่าสุด
    lib.search.setText("มอเตอร์")
    kinds = lib.visible_kinds()
    assert "motor" in kinds and "motor_rev" in kinds and "lamp" not in kinds
    lib.search.setText("timer")                              # ไม่มีอุปกรณ์ชื่อ timer → ว่าง (ไม่ล้ม)
    lib.search.setText("photo")
    assert "sensor" in lib.visible_kinds()
    lib.search.clear()
    assert len(lib.visible_kinds()) == len(CATALOG)

    for k in ("lamp", "motor", "lamp", "valve"):
        lib.remember(k)
    assert lib.recent == ["valve", "lamp", "motor"]
    assert not lib.cats[RECENT].isHidden()
    lib2 = LibraryPanel()
    assert lib2.recent == ["valve", "lamp", "motor"]           # จำข้ามการเปิดโปรแกรม


def test_palette_remembers_collapsed(app, tmp_state):
    from plc_game.ui.panel.library_dock import LibraryPanel
    lib = LibraryPanel()
    lib.cats["display"].setExpanded(False)
    assert "display" in state.load()["palette_collapsed"]
    lib2 = LibraryPanel()
    assert not lib2.cats["display"].isExpanded() and lib2.cats["input"].isExpanded()
