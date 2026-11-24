"""R2: นิยามสเปก + รุ่นสำเร็จรูป + ผังเก่าเข้ากันได้."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from plc_game.panel import PanelDoc  # noqa: E402
from plc_game.panel.catalog import CATALOG  # noqa: E402
from plc_game.panel.presets import PRESETS  # noqa: E402
from plc_game.ui.panel.properties_dock import PropertiesPanel  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _check_value(f, v, where):
    if f.type == "num":
        assert f.lo <= float(v) <= f.hi, (where, f.prop, v)
    elif f.type == "choice":
        assert str(v) in [c for c, _ in f.choices], (where, f.prop, v)


def test_spec_fields_valid():
    for kind, info in CATALOG.items():
        props = [f.prop for f in info.specs]
        assert len(props) == len(set(props)), kind
        for f in info.specs:
            assert f.group in ("spec", "sim", "general"), (kind, f.prop)
            _check_value(f, info.default_of(f), kind)
            for k in f.links:
                assert k in CATALOG, (kind, f.prop, k)


def test_presets_use_real_props():
    for kind, presets in PRESETS.items():
        info = CATALOG[kind]
        assert presets, kind
        for name, props in presets:
            assert name and not any(b in name.lower() for b in ("omron", "siemens", "mitsubishi", "schneider")), name
            for k, v in props.items():
                f = info.spec_field(k)
                assert f is not None or k == "contact", (kind, name, k)
                if f:
                    _check_value(f, v, name)


def test_preset_is_one_undo_step(app):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc())
    v.set_run_mode(False)
    m = v.add_device("motor", QPointF(0, 0))
    pp = PropertiesPanel(v)
    pp.set_item(m)
    assert isinstance(pp.cb_preset, QComboBox) and pp.cb_preset.count() == len(PRESETS["motor"]) + 1
    n = v.undo.count()
    name = PRESETS["motor"][1][0]
    assert pp.apply_preset(name)
    assert v.undo.count() == n + 1 and name in v.undo.undoText()
    assert m.fnum("fla") == 1.9 and m.sprop("start") == "dol"
    assert pp.fields["fla"].value() == pytest.approx(1.9)      # ฟอร์มแสดงค่าใหม่
    v.do_undo()
    m2 = next(iter(v.items_by_id.values()))
    assert m2.fnum("fla") == 0.0                                 # กลับเป็นค่าเริ่มต้น


def test_properties_has_cards_and_help(app):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc())
    s = v.add_device("sensor", QPointF(0, 0))
    pp = PropertiesPanel(v)
    pp.set_item(s)
    assert "output" in pp.fields and "NPN" in pp.fields["output"].toolTip()
    assert pp.fields["range_mm"].specialValueText() == "ตามชนิด"
    pp.fields["mode"].setCurrentIndex(1)
    assert s.spec.props["mode"] == "don"


def test_link_field_lists_compatible_devices(app):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc())
    conv = v.add_device("conveyor", QPointF(0, 0))
    v.add_device("lamp", QPointF(0, 200))
    enc = v.add_device("encoder", QPointF(200, 0))
    pp = PropertiesPanel(v)
    pp.set_item(enc)
    cb = pp.fields["link_conv"]
    assert cb.count() == 2 and cb.itemData(1) == conv.spec.id     # มีเฉพาะสายพาน
    cb.setCurrentIndex(1)
    assert enc.linked("link_conv") is conv


@pytest.mark.parametrize("path", sorted((ROOT / "panels").glob("**/*.plcpanel")), ids=lambda p: p.name)
def test_old_panels_load_and_run(app, path):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc.load(path))
    before = {i: dict(it.spec.props) for i, it in v.items_by_id.items()}
    for it in v.items_by_id.values():
        it.apply_snapshot({a: 1 for a in v.addresses()})
    for _ in range(20):
        v.step(0.05)
    assert {i: dict(it.spec.props) for i, it in v.items_by_id.items()} == before   # ไม่แก้ไฟล์เอง
