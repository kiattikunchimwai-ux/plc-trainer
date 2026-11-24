import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.panel.catalog import CATALOG  # noqa: E402
from plc_game.ui.fault_dock import FaultPanel  # noqa: E402
from plc_game.ui.panel.items import ITEM_CLASSES  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make(app, *specs):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=list(specs)))
    w = []
    v.request_write.connect(lambda a, x: w.append((a, x)))
    v.request_write_word.connect(lambda a, x: w.append((a, x, "w")))
    return v, w, list(v.items_by_id.values())


def run(item, sec, step=0.05):
    for _ in range(int(sec / step)):
        item.tick(step)


def test_physical_devices_have_faults():
    for kind in ("pushbutton", "sensor", "limit", "overload", "lamp", "motor", "motor_rev", "conveyor", "contactor",
                 "cylinder", "pusher", "tank", "oven", "vfd", "axis", "encoder"):
        assert ITEM_CLASSES[kind].FAULTS, kind
    for kind in ("note", "zone", "display", "setvalue"):
        assert not ITEM_CLASSES[kind].FAULTS, kind
    assert set(CATALOG) <= set(ITEM_CLASSES)


def test_sensor_stuck_on_and_wire_break(app):
    v, w, (s,) = make(app, DeviceSpec.new("sensor", address="X2"))
    v.set_fault(s, "stuck_on")
    assert w == [("X2", 1)] and s.signal() == 1       # ส่ง 1 ทันทีแม้ไม่มีชิ้นงาน
    v.set_fault(s, "wire_break")
    s.on_press(QPointF())                             # สั่งด้วยมือก็ยังเป็น 0
    assert s.signal() == 0 and w[-1] == ("X2", 0)
    v.set_fault(s, "")
    assert s.signal() == 1                            # manual ON ยังค้างอยู่ → กลับมาส่ง 1
    assert not v.set_fault(s, "bogus") and s.fault == ""


def test_nc_estop_wire_break_reads_as_stop(app):
    v, w, (e,) = make(app, DeviceSpec.new("estop", address="X5"))
    assert e.signal() == 1                            # NC ปกติ = 1
    v.set_fault(e, "wire_break")
    assert w == [("X5", 0)]                           # สายขาด = เหมือนกด E-Stop (ปลอดภัย)


def test_dirty_sensor_ignores_parts(app):
    v, w, (conv, s) = make(app, DeviceSpec.new("conveyor", 0, 0, address="Y0"),
                           DeviceSpec.new("sensor", -180, -100, address="X0"))
    v.set_run_mode(True)
    v.set_fault(s, "dirty")
    conv.spawn()
    conv.parts[0].local_x = s.x()
    conv.parts[0].place()
    v._tick()
    assert not s.detected and ("X0", 1) not in w
    v.set_fault(s, "")
    v._tick()
    assert s.detected and ("X0", 1) in w


def test_cylinder_no_air_and_broken_reed(app):
    v, w, (c,) = make(app, DeviceSpec.new("cylinder", address="Y5", addr_ret="X10", addr_ext="X11", stroke_s=0.5))
    v.set_fault(c, "no_air")
    c.apply_snapshot({"Y5": 1})
    run(c, 1.0)
    assert c.pos_k == 0.0 and ("X11", 1) not in w
    v.set_fault(c, "reed_a1")
    run(c, 1.0)
    assert c.pos_k == 1.0 and ("X11", 1) not in w and ("X10", 0) in w   # ยื่นได้ แต่ a1 ไม่ส่ง
    v.set_fault(c, "")
    run(c, 0.1)
    assert ("X11", 1) in w


def test_overload_trip_fault(app):
    v, w, (ol,) = make(app, DeviceSpec.new("overload", address="X7"))
    v.set_fault(ol, "trip")
    assert w == [("X7", 0)] and ol.tripped           # NC เปิดเมื่อทริป


def test_contactor_coil_and_aux(app):
    v, w, (k,) = make(app, DeviceSpec.new("contactor", address="Y0", addr_aux="X20"))
    v.set_fault(k, "coil_burn")
    k.apply_snapshot({"Y0": 1})
    assert not k.pulled and ("X20", 1) not in w
    v.set_fault(k, "")
    assert ("X20", 1) in w
    v.set_fault(k, "aux_fail")
    assert w[-1] == ("X20", 0) and k.pulled


def test_tank_oven_vfd_axis_faults(app):
    v, w, (t, ov, inv, ax) = make(
        app, DeviceSpec.new("tank", address="Y6", addr_high="X12", addr_low="X13", level0=10, fill_rate=50),
        DeviceSpec.new("oven", address="Y0", addr_temp="D30", tau_s=1, heat_c=200),
        DeviceSpec.new("vfd", address="Y2", addr_freq="D0", ramp_s=0.5),
        DeviceSpec.new("axis", address="Y3", addr_rev="Y4", addr_p1="X0", addr_p3="X1", travel_s=0.5))
    for it, code in ((t, "pump_fail"), (ov, "heater_open"), (inv, "trip"), (ax, "jammed")):
        v.set_fault(it, code)
    snap = {"Y6": 1, "Y0": 1, "Y2": 1, "D0": 500, "Y3": 1}
    for it in (t, ov, inv, ax):
        it.apply_snapshot(snap)
        run(it, 1.0)
    assert t.level == 10 and ov.temp < 26 and inv.hz == 0 and ax.k == 0
    v.set_fault(ov, "tc_open")
    assert w[-1] == ("D30", 0, "w")
    n = len(w)
    v.set_fault(ax, "p1_fail")
    assert ("X0", 0) in w[n:] and ax.sens["addr_p1"] is False


def test_clear_random_and_undo_keeps_fault(app):
    v, _, items = make(app, DeviceSpec.new("pushbutton", 0, 0, address="X0", label="Start"),
                       DeviceSpec.new("lamp", 100, 0, address="Y0", label="RUN"),
                       DeviceSpec.new("note", 0, 100))
    assert len(v.fault_items()) == 2                  # ข้อความไม่มี fault
    it, code = v.random_fault(random.Random(1))
    assert it.fault == code
    v.set_run_mode(False)
    v.add_device("lamp", QPointF(200, 0))
    v.do_undo()                                       # Undo สร้าง item ใหม่ แต่ fault ต้องยังอยู่
    assert v.items_by_id[it.spec.id].fault == code
    assert v.find_item("start").label == "Start" and v.find_item("Y0").label == "RUN"
    assert v.clear_faults() == 1
    assert not any(i.fault for i in v.items_by_id.values())


def test_fault_panel_combo_and_hidden(app):
    v, w, (s,) = make(app, DeviceSpec.new("sensor", address="X2", label="PS1"))
    fp = FaultPanel(v)
    msgs = []
    fp.message.connect(msgs.append)
    cb = fp._combos[s.spec.id]
    cb.setCurrentIndex(cb.findData("stuck_on"))
    assert s.fault == "stuck_on" and "PS1" in msgs[-1]
    fp.cb_hidden.setChecked(True)
    assert v.sc.faults_hidden and fp.table.isColumnHidden(2) and "ความผิดปกติ" not in s.toolTip()
    fp.random_fault()                                 # ไม่มีอุปกรณ์ปกติเหลือ
    fp.clear_all()
    assert s.fault == "" and cb.currentIndex() == 0
