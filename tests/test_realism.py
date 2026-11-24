"""R2: พฤติกรรมตามสเปกจริง."""
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc, physics  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make(*specs):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=list(specs)))
    w = []
    v.request_write.connect(lambda a, x: w.append((a, x)))
    v.request_write_word.connect(lambda a, x: w.append((a, x, "w")))
    return v, w, list(v.items_by_id.values())


def run(v, seconds, dt=0.05):
    for _ in range(round(seconds / dt)):
        v.step(dt)


# ---------------- สูตร ----------------
def test_ol_curve_iec():
    assert 4 <= physics.ol_trip_time(7.2, 10) <= 10
    assert 8 <= physics.ol_trip_time(7.2, 20) <= 20
    assert physics.ol_trip_time(1.05, 10) == math.inf
    assert physics.ol_trip_time(1.5, 10) > 60          # เกินนิดหน่อย ทริปช้า


def test_cylinder_formula():
    assert physics.cylinder_stroke_time(32, 100, 1.5, 0) is None          # ลมไม่พอ
    t6 = physics.cylinder_stroke_time(32, 100, 6, 0)
    t3 = physics.cylinder_stroke_time(32, 100, 3, 0)
    assert t6 == pytest.approx(0.2, abs=0.01) and t3 > t6
    assert physics.cylinder_stroke_time(20, 50, 6, 50) is None             # Ø20 ดัน 50 kg ไม่ไหว
    assert physics.cylinder_force(50, 6) == pytest.approx(1178, rel=0.01)


# ---------------- อุปกรณ์ ----------------
def _sensor_scene(**props):
    v, w, (conv, s) = make(DeviceSpec.new("conveyor", 0, 0, address="Y0", part_mode="plastic"),
                           DeviceSpec.new("sensor", 0, -200, address="X0", sense="photo", **props))
    v.set_run_mode(True)
    conv.spawn()
    conv.parts[0].local_x = 0
    conv.parts[0].place()
    return v, w, conv, s


def test_sensor_range(app):
    v, _, _, s = _sensor_scene()                  # ชิ้นงานห่างหน้าเซนเซอร์ ~137 mm
    v.step(0.01)
    assert not s.actuated                         # ค่าเดิม 120 mm มองไม่ถึง
    v, _, _, s = _sensor_scene(range_mm=150)
    v.step(0.01)
    assert s.actuated and s.BEAM == 150


def test_sensor_response_and_dark_on(app):
    v, _, _, s = _sensor_scene(range_mm=200, response_ms=100)
    v.step(0.05)
    v.step(0.04)
    assert s.detected and not s.actuated          # ยังไม่ครบเวลาตอบสนอง
    v.step(0.05)
    v.step(0.05)
    assert s.actuated
    v, _, conv, s = _sensor_scene(range_mm=200, mode="don")
    v.step(0.01)
    assert s.detected and not s.actuated          # Dark-ON: เจอชิ้นงาน = OFF
    conv.clear_parts()
    v.step(0.01)
    assert s.actuated


def test_motor_ramp_and_inrush(app):
    v, _, (m,) = make(DeviceSpec.new("motor", address="Y0", fla=2.0, accel_s=1.0, decel_s=2.0, load_pct=100,
                                     start="dol"))
    m.apply_snapshot({"Y0": 1})
    v.step(0.1)
    assert 0.05 < m.speed < 0.2 and m.current_a > 9          # กระแสกระชาก ~6×FLA
    run(v, 1.2)
    assert m.speed == 1.0 and m.current_a == pytest.approx(2.0)
    assert "1400 rpm" in m.state_text()
    m.apply_snapshot({"Y0": 0})
    run(v, 1.0)
    assert 0.4 < m.speed < 0.6 and m.current_a == 0          # หมุนฟรีด้วยแรงเฉื่อย


def test_ol_thermal_trip_and_reset(app):
    v, w, (m, ol) = make(DeviceSpec.new("motor", 0, 0, address="Y0", fla=2.0, load_pct=100),
                         DeviceSpec.new("overload", 200, 0, address="X3", contact="NC", addr_motor="Y0", ir_a=2.0))
    m.apply_snapshot({"Y0": 1})
    ol.apply_snapshot({"Y0": 1})
    run(v, 60, dt=0.1)
    assert not ol.tripped                         # กระแสพิกัด ไม่ทริป
    m.set_fault("jammed")                         # ล็อกโรเตอร์ = 6×Ir
    t = 0.0
    while not ol.tripped and t < 30:
        v.step(0.1)
        t += 0.1
    assert ol.tripped and 5 < t < 16 and ("X3", 0) in w
    ol.on_press(None)                             # ยังร้อน → รีเซ็ตไม่ได้
    assert ol.tripped and "ยังร้อน" in ol.state_text()
    m.apply_snapshot({"Y0": 0})
    run(v, 200, dt=0.5)                           # ปล่อยให้เย็น
    ol.on_press(None)
    assert not ol.tripped


def test_ol_auto_reset(app):
    v, _, (m, ol) = make(DeviceSpec.new("motor", 0, 0, address="Y0", fla=2.0, load_pct=100),
                         DeviceSpec.new("overload", 200, 0, address="X3", addr_motor="Y0", ir_a=2.0,
                                        reset="auto"))
    m.apply_snapshot({"Y0": 1})
    m.set_fault("jammed")
    run(v, 20, dt=0.1)
    assert ol.tripped
    m.apply_snapshot({"Y0": 0})
    run(v, 60, dt=0.5)
    assert ol.tripped                             # ร้อนจัด ยังไม่คืนเอง
    run(v, 400, dt=0.5)
    assert not ol.tripped                         # เย็นแล้วรีเซ็ตเอง


def test_ol_old_trip_s_unchanged(app):
    v, _, (ol,) = make(DeviceSpec.new("overload", address="X3", addr_motor="Y0", trip_s=2))
    ol.apply_snapshot({"Y0": 1})
    run(v, 1.9)
    assert not ol.tripped
    run(v, 0.2)
    assert ol.tripped


def test_cylinder_low_air_and_spec_timing(app):
    v, w, (c,) = make(DeviceSpec.new("cylinder", address="Y5", addr_ret="X10", addr_ext="X11", pressure_bar=1.5))
    c.apply_snapshot({"Y5": 1})
    run(v, 2)
    assert c.pos_k == 0 and "ลมไม่พอ" in c.state_text()
    v, w, (c,) = make(DeviceSpec.new("cylinder", address="Y5", addr_ret="X10", addr_ext="X11", timing="spec",
                                     bore_mm=32, stroke_mm=100, pressure_bar=6))
    c.apply_snapshot({"Y5": 1})
    run(v, 0.15)
    assert 0 < c.pos_k < 1
    run(v, 0.1)
    assert c.pos_k == 1.0 and ("X11", 1) in w


def test_debounce_pulses(app):
    v, w, (pb,) = make(DeviceSpec.new("pushbutton", address="X0", bounce_ms=20))
    pb.on_press(None)
    run(v, 0.05, dt=0.01)
    xs = [x for a, x in w if a == "X0"]
    assert xs == [1, 0, 1, 0, 1]                  # กดครั้งเดียว แต่ขอบขาขึ้น 3 ครั้ง
    assert pb.signal() == 1


def test_contactor_pickup_and_lamp_fade(app):
    v, w, (k, lamp) = make(DeviceSpec.new("contactor", 0, 0, address="Y0", addr_aux="X1", pickup_ms=30),
                           DeviceSpec.new("lamp", 200, 0, address="Y1", lamp_type="incand"))
    k.apply_snapshot({"Y0": 1})
    lamp.apply_snapshot({"Y1": 1})
    assert not k.pulled
    v.step(0.02)
    assert not k.pulled and 0 < lamp.bright < 1
    v.step(0.02)
    assert k.pulled and ("X1", 1) in w
    run(v, 0.2)
    assert lamp.bright == 1.0


def test_tank_spec_rate_and_encoder_link(app):
    v, _, (t, conv, enc) = make(
        DeviceSpec.new("tank", 0, 0, address="Y6", level0=0, rate_mode="spec", volume_l=60, pump_lpm=60),
        DeviceSpec.new("conveyor", 0, 300, address="Y0", speed=120),
        DeviceSpec.new("encoder", 300, 300, address="X3", addr_motor="", ppr=100, wheel_mm=50))
    enc.spec.props["link_conv"] = conv.spec.id
    t.apply_snapshot({"Y6": 1})
    run(v, 3)
    assert t.level == pytest.approx(5.0, abs=0.1)              # 1 L/s ÷ 60 L = 1.67 %/s
    conv.apply_snapshot({"Y0": 1})
    assert enc.hz == pytest.approx(76.4, abs=0.2)
    run(v, 1)
    assert enc.count == pytest.approx(76, abs=2) and "อ่านไม่ทัน" in enc.state_text()
