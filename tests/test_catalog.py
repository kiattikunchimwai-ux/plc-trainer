import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc, validate_address  # noqa: E402
from plc_game.panel.catalog import CATALOG, CATEGORIES  # noqa: E402
from plc_game.ui.panel.items import ITEM_CLASSES, make_item  # noqa: E402
from plc_game.ui.panel.library_dock import device_icon  # noqa: E402
from plc_game.ui.panel.properties_dock import PropertiesPanel  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_every_kind_has_class_and_category():
    cats = {c for c, _ in CATEGORIES}
    for kind, info in CATALOG.items():
        assert kind in ITEM_CLASSES, kind
        assert info.category in cats, kind
        assert info.desc, f"{kind} ไม่มีคำอธิบาย"


@pytest.mark.parametrize("kind", list(CATALOG))
def test_kind_places_paints_and_edits(app, kind):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc())
    v.set_run_mode(False)
    it = v.add_device(kind, QPointF(0, 0))
    assert it.valid, (kind, it.slot_ok)          # ค่าเริ่มต้นต้องถูกต้อง
    for s in it.info.slots():
        ok, _ = validate_address(kind, it.spec.props.get(s.prop, ""), 8, s.prop)
        assert ok
    img = QImage(400, 400, QImage.Format_ARGB32)
    p = QPainter(img)
    it.paint(p, None)
    p.end()
    for _ in range(5):
        it.apply_snapshot({a: 1 for a in v.addresses()})
        it.tick(0.1)
    it.refresh_tooltip()
    assert not device_icon(kind).isNull()
    PropertiesPanel(v).set_item(it)               # แผง Properties สร้างได้ทุกชนิด
    js = v.to_doc().to_json()
    assert PanelDoc.from_json(js).devices[0].kind == kind


def make(app, *specs):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=list(specs)))
    w = []
    v.request_write.connect(lambda a, x: w.append((a, x)))
    v.request_write_word.connect(lambda a, x: w.append((a, x, "w")))
    return v, w, list(v.items_by_id.values())


def test_inductive_sees_only_metal(app):
    v, _, (conv, ind, ph) = make(app, DeviceSpec.new("conveyor", 0, 0, address="Y0", part_mode="plastic"),
                                 DeviceSpec.new("sensor", -180, -60, address="X0", sense="inductive"),
                                 DeviceSpec.new("sensor", -180 + 60, -100, address="X1", sense="photo"))
    v.set_run_mode(True)
    conv.spawn()
    conv.parts[0].local_x = ind.x()
    conv.parts[0].place()
    v._tick()
    assert not ind.detected
    conv.clear_parts()
    conv.spec.props["part_mode"] = "metal"
    conv.spawn()
    conv.parts[0].local_x = ind.x()
    conv.parts[0].place()
    v._tick()
    assert ind.detected and conv.parts[0].material == "metal"


def test_motor_rev_short_and_vfd_ramp(app):
    _, w, (m, inv) = make(app, DeviceSpec.new("motor_rev", address="Y0", addr_rev="Y1"),
                          DeviceSpec.new("vfd", address="Y2", addr_freq="D0", addr_atspeed="X5", ramp_s=1.0))
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    assert m.short and "ลัดวงจร" in m.state_text()
    inv.apply_snapshot({"Y2": 1, "D0": 300})
    for _ in range(20):
        inv.tick(0.05)
    assert abs(inv.hz - 30) < 0.01 and ("X5", 1) in w


def test_axis_sensors_and_position(app):
    _, w, (ax,) = make(app, DeviceSpec.new("axis", address="Y0", addr_rev="Y1", addr_p1="X0", addr_p2="X1",
                                           addr_p3="X2", addr_pos="D5", travel_s=1.0))
    ax.apply_snapshot({"Y0": 1})
    for _ in range(25):
        ax.tick(0.05)
    assert ax.k == 1.0 and ("X0", 0) in w and ("X1", 1) in w and ("X1", 0) in w and ("X2", 1) in w
    assert ("D5", 1000, "w") in w


def test_oven_heats_and_thermostat(app):
    _, w, (ov,) = make(app, DeviceSpec.new("oven", address="Y0", addr_temp="D30", addr_thermo="X3",
                                           heat_c=200, tau_s=1, thermo_c=100))
    ov.apply_snapshot({"Y0": 1})
    for _ in range(100):
        ov.tick(0.05)
    assert ov.temp > 190 and ("X3", 1) in w and any(x[0] == "D30" and x[1] > 150 for x in w if len(x) == 3)


def test_pusher_removes_part(app):
    v, _, (conv, pu) = make(app, DeviceSpec.new("conveyor", 0, 0, address="Y0"),
                            DeviceSpec.new("pusher", 0, -80, address="Y1", addr_ret="X0", addr_ext="X1"))
    v.set_run_mode(True)
    conv.spawn()
    conv.parts[0].local_x = 0
    conv.parts[0].place()
    pu.apply_snapshot({"Y1": 1})
    for _ in range(20):
        pu.tick(0.05)
        v._tick()
    assert pu.bin_count == 1 and not conv.parts


def test_annotations_have_no_io(app):
    for kind in ("note", "zone"):
        assert CATALOG[kind].slots() == []
        assert DeviceSpec.new(kind).all_io() == []
