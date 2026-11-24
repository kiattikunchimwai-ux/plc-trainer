import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=[DeviceSpec.new("pushbutton", 0, 0, address="X0", key="1"),
                                 DeviceSpec.new("lamp", 100, 0, address="Y0")]))
    v.set_run_mode(False)
    return v


def test_add_undo_redo(view):
    assert len(view.items_by_id) == 2 and not view.undo.canUndo()
    it = view.add_device("pushbutton", QPointF(200, 0))
    assert it.addr == "X1"                 # เสนอ address ถัดไปที่ว่าง
    assert it.key == "2"                   # และคีย์ลัดถัดไปที่ว่าง
    assert len(view.items_by_id) == 3
    view.do_undo()
    assert len(view.items_by_id) == 2
    view.do_redo()
    assert len(view.items_by_id) == 3 and "X1" in view.addresses()


def test_props_edit_is_one_undo_step(view):
    it = next(i for i in view.items_by_id.values() if i.addr == "Y0")
    for txt in ("Y", "Y5"):                # พิมพ์ต่อเนื่อง
        it.spec.props["address"] = txt
        view.item_props_changed(it)
    view.flush_commit()
    assert view.undo.count() == 1
    view.do_undo()
    assert "Y0" in view.addresses() and "Y5" not in view.addresses()


def test_delete_and_undo_restores_ids(view):
    ids = set(view.items_by_id)
    for it in view.items_by_id.values():
        it.setSelected(True)
    view.remove_selected()
    assert not view.items_by_id
    view.do_undo()
    assert set(view.items_by_id) == ids


def test_hotkey_press_release(view):
    writes = []
    view.request_write.connect(lambda a, v: writes.append((a, v)))
    assert not view.key_down("1")          # โหมด EDIT: คีย์ลัดไม่ทำงาน
    view.set_run_mode(True)
    assert view.key_down("1")
    assert view.key_up("1")
    assert writes == [("X0", 1), ("X0", 0)]
    assert not view.key_down("9")          # ไม่มีอุปกรณ์ใช้คีย์นี้
