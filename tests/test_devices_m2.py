import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc, conflicts, validate_address  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_view(app, *specs):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=list(specs)))
    writes = []
    v.request_write.connect(lambda a, x: writes.append((a, x)))
    v.request_write_word.connect(lambda a, x: writes.append((a, x, "w")))
    return v, writes, list(v.items_by_id.values())


def run(item, seconds, step=0.05):
    for _ in range(int(seconds / step)):
        item.tick(step)


# ---------- model ----------
def test_extra_slots_validate_and_conflict():
    cyl = DeviceSpec.new("cylinder", addr_ret="X0", addr_ext="X1")
    pb = DeviceSpec.new("pushbutton", address="X1")
    assert conflicts([cyl, pb]) == {"X1": [cyl.id, pb.id]}       # รีดสวิตช์ชนกับปุ่ม
    assert validate_address("cylinder", "", prop="addr_sol_b") == (True, "")   # เว้นว่างได้
    assert not validate_address("cylinder", "", prop="addr_ext")[0]            # ต้องกำหนด
    assert not validate_address("cylinder", "Y0", prop="addr_ext")[0]          # รีดสวิตช์ต้องเป็น X/M
    assert [p for p, _, _ in cyl.all_io()] == ["address", "addr_ret", "addr_ext"]


def test_new_device_gets_free_input_addresses(app):
    v, _, _ = make_view(app, DeviceSpec.new("pushbutton", address="X10"))
    it = v.add_device("cylinder", QPointF(0, 200))
    assert it.prop("addr_ret") == "X11" and it.prop("addr_ext") == "X12"
    assert not it.conflict and it.valid


# ---------- อุปกรณ์ ----------
def test_cylinder_single_spring_return(app):
    v, w, (c,) = make_view(app, DeviceSpec.new("cylinder", address="Y5", addr_ret="X10", addr_ext="X11", stroke_s=0.5))
    assert v.input_states() == [("X10", 1, False), ("X11", 0, False)]
    c.apply_snapshot({"Y5": 1})
    run(c, 0.7)
    assert c.pos_k == 1.0 and ("X10", 0) in w and ("X11", 1) in w
    w.clear()
    c.apply_snapshot({"Y5": 0})            # ปล่อยโซลินอยด์ → สปริงดันกลับ
    run(c, 0.7)
    assert c.pos_k == 0.0 and w == [("X11", 0), ("X10", 1)]


def test_cylinder_double_holds_position(app):
    _, _, (c,) = make_view(app, DeviceSpec.new("cylinder", valve="double", address="Y5", addr_sol_b="Y6",
                                               addr_ret="X10", addr_ext="X11", stroke_s=0.5))
    c.apply_snapshot({"Y5": 1, "Y6": 0})
    run(c, 0.7)
    c.apply_snapshot({"Y5": 0, "Y6": 0})   # ไม่มีสัญญาณ → ค้างที่ยื่นสุด
    run(c, 0.7)
    assert c.pos_k == 1.0
    c.apply_snapshot({"Y5": 0, "Y6": 1})
    run(c, 0.7)
    assert c.pos_k == 0.0


def test_tank_levels_and_tap(app):
    _, w, (t,) = make_view(app, DeviceSpec.new("tank", address="Y6", addr_drain="Y7", addr_high="X12",
                                               addr_low="X13", level0=10, fill_rate=50, drain_rate=50))
    t.apply_snapshot({"Y6": 1})
    run(t, 2.0)                             # 10% → 100%
    assert t.level == 100 and ("X13", 1) in w and ("X12", 1) in w
    t.apply_snapshot({"Y6": 0})
    w.clear()
    t.on_press(QPointF())                   # เปิดก๊อก
    run(t, 2.0)
    assert t.level == 0 and w == [("X12", 0), ("X13", 0)]


def test_contactor_aux_and_overload_trip(app):
    _, w, (k, ol) = make_view(app, DeviceSpec.new("contactor", address="Y0", addr_aux="X20"),
                              DeviceSpec.new("overload", address="X21", addr_motor="Y0", trip_s=1))
    k.apply_snapshot({"Y0": 1})
    ol.apply_snapshot({"Y0": 1})
    assert ("X20", 1) in w
    run(ol, 1.2)
    assert ol.actuated and ("X21", 0) in w     # NC เปิดเมื่อทริป
    ol.on_press(QPointF())                     # รีเซ็ต
    assert ("X21", 1) in w


def test_traffic_and_sevenseg(app):
    _, _, (tr, ss) = make_view(app, DeviceSpec.new("traffic"), DeviceSpec.new("sevenseg", address="D0"))
    tr.apply_snapshot({"Y0": 0, "Y1": 1, "Y2": 0})
    assert tr.lights == [False, True, False]
    ss.apply_snapshot({"D0": 123})
    assert ss.value == 123 and ss.W == 4 * 30 + 16


def test_setvalue_writes_word_with_limits(app):
    v, w, (s,) = make_view(app, DeviceSpec.new("setvalue", address="D10", value=5, min=0, max=20))
    assert v.input_states() == [("D10", 5, True)]
    s.set_value(s.value + 10)
    s.set_value(99)                         # เกินค่าสูงสุด → 20
    assert w == [("D10", 15, "w"), ("D10", 20, "w")]
    assert "D10" in v.addresses()
