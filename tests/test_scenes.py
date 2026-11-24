"""ฉากโรงงานสำเร็จรูป + หน้า Quick Start."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import PanelDoc, conflicts, validate_address  # noqa: E402
from plc_game.panel.iolist import rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_example_panels  # noqa: E402
from plc_game.ui.quickstart import SCENES  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_every_scene_is_built_and_listed():
    assert {f for f, _, _ in SCENES} == set(make_example_panels.PANELS)


@pytest.mark.parametrize("name", sorted(make_example_panels.PANELS))
def test_scene_valid_and_documented(name):
    doc = make_example_panels.PANELS[name]
    for d in doc.devices:
        for prop, _, raw in d.all_io():
            assert validate_address(d.kind, raw, 8, prop)[0], (name, d.kind, prop, raw)
    assert not conflicts(doc.devices, 8)
    notes = [d for d in doc.devices if d.kind == "note"]
    assert notes and "โจทย์" in notes[0].props["text"]
    # ทุก address ที่ใช้ในผังต้องถูกอธิบายในกล่องโจทย์
    text = notes[0].props["text"]
    for r in rows(doc.devices):
        if r.address.startswith(("X", "Y", "D")):
            assert r.address in text, (name, r.address)
    assert PanelDoc.from_json(doc.to_json()).name == doc.name


def test_sorting_scene_works(app):
    """ฉากคัดแยก: inductive เห็นเฉพาะโลหะ, ตัวดันยื่นแล้วชิ้นงานลงถาด."""
    from plc_game.ui.panel.view import PanelView
    v = PanelView()
    v.load_doc(make_example_panels.PANELS["sorting.plcpanel"])
    v.set_run_mode(True)
    by = {it.label: it for it in v.items_by_id.values()}
    conv, ind, ps, pu = by["สายพาน"], by["IND โลหะ"], by["PS ชิ้นงานเข้า"], by["ตัวดันโลหะ"]
    for mat, seen in (("metal", True), ("plastic", False)):
        conv.spawn()
        wp = conv.parts[-1]
        wp.material = mat
        wp.local_x = ind.x() - conv.x()
        wp.place()
        v._tick()
        assert ind.detected is seen, mat
        wp.local_x = ps.x() - conv.x()
        conv.parts[-1].place()
        v._tick()
        assert ps.detected, mat
        conv.remove_part(wp)
    conv.spawn()
    conv.parts[-1].local_x = pu.x() - conv.x()
    conv.parts[-1].place()
    pu.pos_k = 1.0
    v._tick()
    assert not conv.parts and pu.bin_count == 1


def _scene(name):
    from plc_game.ui.panel.view import PanelView
    v = PanelView()
    v.load_doc(PanelDoc.from_json(make_example_panels.PANELS[name].to_json()))
    v.set_run_mode(True)
    return v, {it.label: it for it in v.items_by_id.values()}


def test_pick_place_scene_picks_from_conveyor(app):
    """ชิ้นงานบนสายพานวิ่งถึงจุดหยิบ → เซนเซอร์เห็น → แขนลงหยิบได้จริง แล้ววางถาด."""
    v, by = _scene("pick_place.plcpanel")
    conv, ps, arm = by["สายพานป้อน"], by["PS ถึงจุดหยิบ"], by["แขนหยิบ"]
    conv.spawn()
    conv.apply_snapshot({"Y0": 1})
    t = 0.0
    while not ps.actuated and t < 10:
        v.step(0.05)
        t += 0.05
    assert ps.actuated, "ชิ้นงานต้องวิ่งถึงจุดหยิบ"
    conv.apply_snapshot({"Y0": 0})
    seq = [{"Y1": 1}, {"Y1": 1, "Y3": 1}, {"Y3": 1}, {"Y3": 1, "Y2": 1}, {"Y1": 1, "Y2": 1, "Y3": 1},
           {"Y1": 1, "Y2": 1}, {"Y2": 1}, {}]
    for i, cmd in enumerate(seq):
        arm.apply_snapshot(cmd)
        for _ in range(30):
            v.step(0.05)
        if i == 1:
            assert arm.held and not conv.parts
    assert arm.placed == 1 and arm.crash_t == 0 and arm.dropped == 0


def test_air_scene_pressure_builds(app):
    v, by = _scene("air_system.plcpanel")
    comp, ps, cyl = by["ปั๊มลม"], by["PS ลม 6 bar"], by["กระบอกสูบ A"]
    cyl.apply_snapshot({"Y1": 1})
    for _ in range(20):
        v.step(0.05)
    assert cyl.pos_k == 0                         # ยังไม่มีลม
    comp.apply_snapshot({"Y0": 1})
    for _ in range(600):
        v.step(0.05)
        if ps.actuated:
            break
    assert ps.actuated and cyl.pos_k == 1.0


def test_quickstart_dialog(app, tmp_path, monkeypatch):
    from plc_game.ui import quickstart, state
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui.json")
    quickstart.remember_recent(ROOT / "panels" / "tank.plcpanel")
    dlg = quickstart.QuickStartDialog(current_backend="mock")
    assert "sorting.plcpanel" in dlg.cards and "tank.plcpanel" in dlg.cards
    assert not dlg.cards["sorting.plcpanel"].icon().isNull()
    dlg.cards["sorting.plcpanel"].click()
    assert dlg.path.name == "sorting.plcpanel" and dlg.backend == "mock" and dlg.action == "open"
    dlg.cb_show.setChecked(False)
    assert state.load()["quickstart"] is False
