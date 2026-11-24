"""R3: พฤติกรรมหลักของอุปกรณ์ชนิดใหม่ 12 ชนิด."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.panel.catalog import CATALOG  # noqa: E402
from plc_game.panel.presets import PRESETS  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402

NEW = ("selector3", "timer_relay", "float_switch", "compressor", "pressure_switch", "level_tx", "load_cell",
       "servo", "safety_door", "light_curtain", "pick_place", "barcode")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make(*specs):
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc(devices=list(specs)))
    v.set_run_mode(True)
    w = []
    v.request_write.connect(lambda a, x: w.append((a, x)))
    v.request_write_word.connect(lambda a, x: w.append((a, x, "w")))
    return v, w, list(v.items_by_id.values())


def run(v, s, dt=0.05):
    for _ in range(round(s / dt)):
        v.step(dt)


def link(item, prop, other):
    item.spec.props[prop] = other.spec.id


def test_new_kinds_complete():
    for k in NEW:
        info = CATALOG[k]
        assert info.desc and info.aliases and info.specs, k
        assert PRESETS.get(k), f"{k} ไม่มีรุ่นสำเร็จรูป"


def test_selector3(app):
    _, w, (s,) = make(DeviceSpec.new("selector3", address="X4", addr_right="X5"))
    s.on_press(QPointF(20, 0))
    assert s.position == 1 and ("X5", 1) in w and s.signal_of("address") == 0
    s.on_press(QPointF(-20, 0))
    s.on_press(QPointF(-20, 0))
    assert s.position == -1 and ("X4", 1) in w and ("X5", 0) in w
    s.on_press(QPointF())                         # คีย์ลัด = วนตำแหน่ง
    assert s.position == 0 and "OFF" in s.state_text()


@pytest.mark.parametrize("mode,expect", [
    ("on", [(0.9, 0), (1.1, 1), ("off", 0)]),
    ("off", [(0.1, 1), ("off", 1), (1.1, 0)]),
])
def test_timer_relay(app, mode, expect):
    v, w, (t,) = make(DeviceSpec.new("timer_relay", address="Y2", addr_contact="X6", mode=mode, set_s=1.0))
    t.apply_snapshot({"Y2": 1})
    elapsed = 0.0
    for when, val in expect:
        if when == "off":
            t.apply_snapshot({"Y2": 0})
            v.step(0.01)
        else:
            run(v, when - elapsed, dt=0.01)
            elapsed = when
        assert int(t.contact) == val, (mode, when)


def test_timer_relay_flicker(app):
    v, w, (t,) = make(DeviceSpec.new("timer_relay", address="Y2", addr_contact="X6", mode="flicker", set_s=0.5))
    t.apply_snapshot({"Y2": 1})
    run(v, 2.0, dt=0.01)
    xs = [x for a, x in w if a == "X6"]
    assert xs == [1, 0, 1, 0, 1]                   # สลับทุก 0.5 s


def test_float_switch_follows_tank(app):
    v, w, (tank, fs) = make(DeviceSpec.new("tank", 0, 0, address="Y6", level0=40, fill_rate=20),
                            DeviceSpec.new("float_switch", 200, 0, address="X14", level_pct=50))
    link(fs, "link_tank", tank)
    v.step(0.05)
    assert not fs.actuated
    tank.apply_snapshot({"Y6": 1})
    run(v, 1)
    assert fs.actuated and ("X14", 1) in w


def test_compressor_and_pressure_switch_hysteresis(app):
    v, w, (c, ps, cyl) = make(
        DeviceSpec.new("compressor", 0, 0, address="Y7", addr_bar="D60", lpm=600, tank_l=10, leak_bar_min=0),
        DeviceSpec.new("pressure_switch", 200, 0, address="X15", set_bar=6.0, diff_bar=1.0),
        DeviceSpec.new("cylinder", 0, 300, address="Y5", addr_ret="X10", addr_ext="X11"))
    link(ps, "link_air", c)
    link(cyl, "link_air", c)
    cyl.apply_snapshot({"Y5": 1})
    run(v, 1)
    assert cyl.pos_k == 0                          # ยังไม่มีลม กระบอกสูบไม่ขยับ
    c.apply_snapshot({"Y7": 1})
    t = 0.0
    while not ps.actuated and t < 10:
        v.step(0.05)
        t += 0.05
    assert ps.actuated and c.bar >= 6.0 and ("D60", 60, "w") in w
    c.apply_snapshot({"Y7": 0})
    bar = c.bar
    cyl.apply_snapshot({"Y5": 0})
    run(v, 1.5)
    assert c.bar < bar                             # กระบอกสูบกินลม
    assert ps.actuated or c.bar <= 5.0             # hysteresis: ยังไม่ปลดจนกว่าจะต่ำกว่า 5 bar
    c.bar = 5.4
    v.step(0.05)
    assert ps.actuated
    c.bar = 4.9
    v.step(0.05)
    assert not ps.actuated


def test_level_tx_scaling(app):
    v, w, (tank, lt) = make(DeviceSpec.new("tank", 0, 0, address="Y6", level0=50),
                            DeviceSpec.new("level_tx", 200, 0, address="D40"))
    link(lt, "link_tank", tank)
    v.step(0.05)
    assert lt.value == 2000 and ("D40", 2000, "w") in w and lt.ma() == pytest.approx(12.0)
    lt.set_fault("lost_echo")
    v.step(0.05)
    assert lt.value == 0


def test_load_cell_fill_and_empty(app):
    v, w, (lc,) = make(DeviceSpec.new("load_cell", address="D42", addr_fill="Y10", fill_gps=100, noise_g=0))
    lc.apply_snapshot({"Y10": 1})
    run(v, 2)
    assert lc.value == pytest.approx(200, abs=2)
    lc.apply_snapshot({"Y10": 0})
    lc.on_press(QPointF())
    v.step(0.05)
    assert lc.value == 0


def test_servo_trapezoid_and_alarm(app):
    v, w, (s,) = make(DeviceSpec.new("servo", address="Y11", addr_target="D50", addr_inpos="X16",
                                     addr_alarm="X26", addr_pos="D52", stroke_mm=500, vmax=250, acc=500))
    s.apply_snapshot({"Y11": 1, "D50": 300})
    run(v, 0.2)
    assert 0 < s.pos < 30 and not s.inpos         # กำลังเร่ง
    run(v, 2.0)
    assert s.pos == 300 and s.inpos and ("X16", 1) in w and ("D52", 300, "w") in w
    s.apply_snapshot({"Y11": 1, "D50": 900})       # เกินระยะ
    v.step(0.05)
    assert s.alarm and ("X26", 1) in w and s.pos == 300
    s.apply_snapshot({"Y11": 0, "D50": 100})       # ปิด Servo ON = รีเซ็ต
    v.step(0.05)
    assert not s.alarm


def test_safety_door_dual_channel(app):
    v, w, (d,) = make(DeviceSpec.new("safety_door", address="X17", addr_ch2="X27", contact="NC"))
    assert d.input_signals() == [("X17", 1, False), ("X27", 1, False)]      # ปิด = 1 ทั้งคู่
    d.on_press(QPointF())
    assert ("X17", 0) in w and ("X27", 0) in w
    d.set_fault("ch2_weld")                        # หน้าสัมผัสเชื่อมติด: สองช่องไม่ตรงกัน
    assert d.signal_of("address") == 0 and d.signal_of("addr_ch2") == 1


def test_light_curtain_hand_and_part(app):
    v, w, (conv, lc) = make(DeviceSpec.new("conveyor", 0, 0, address="Y0"),
                            DeviceSpec.new("light_curtain", 0, -20, address="X20", response_ms=20))
    v.step(0.05)
    assert lc.signal() == 1                        # ลำแสงครบ = OSSD ON
    lc.on_press(QPointF())
    v.step(0.01)
    assert lc.signal() == 1                        # ยังไม่ครบเวลาตอบสนอง
    v.step(0.02)
    assert lc.signal() == 0 and ("X20", 0) in w
    lc.on_release(QPointF())
    run(v, 0.1)
    assert lc.signal() == 1
    conv.spawn()
    conv.parts[0].local_x = 0
    conv.parts[0].place()
    run(v, 0.1)
    assert lc.signal() == 0                        # ชิ้นงานผ่านก็ตัดลำแสง
    lc.set_fault("ossd_fail")
    assert lc.signal() == 1


def test_pick_place_sequence(app):
    v, w, (pp,) = make(DeviceSpec.new("pick_place", address="Y12", addr_right="Y13", addr_grip="Y14",
                                      addr_up="X21", addr_down="X22", addr_left="X23", addr_rightlim="X24",
                                      addr_gripped="X25"))
    cmd = {"Y12": 0, "Y13": 0, "Y14": 0}

    def do(**kw):
        cmd.update(kw)
        pp.apply_snapshot(dict(cmd))
        run(v, 1.2)

    do(Y12=1)                      # ลง
    do(Y14=1)                      # จับ
    assert pp.held and ("X25", 1) in w
    do(Y12=0)                      # ขึ้น
    do(Y13=1)                      # ไปขวา
    assert pp.crash_t == 0 and pp.sens["addr_rightlim"]
    do(Y12=1)
    do(Y14=0)                      # ปล่อย
    assert pp.placed == 1 and pp.held is None
    assert pp.dropped == 0
    cmd.update(Y13=0)              # กลับซ้ายทั้งที่ Z ยังลงอยู่ = ชน
    pp.apply_snapshot(dict(cmd))
    v.step(0.05)
    assert pp.crash_t > 0 and "ชน" in pp.state_text()


def test_pick_place_drop_when_released_midway(app):
    v, _, (pp,) = make(DeviceSpec.new("pick_place"))
    a = {k: pp.addr_of(k) for k in ("address", "addr_grip")}
    pp.apply_snapshot({a["address"]: 1})
    run(v, 1)
    pp.apply_snapshot({a["address"]: 1, a["addr_grip"]: 1})
    run(v, 0.5)
    pp.apply_snapshot({a["addr_grip"]: 1})
    run(v, 1)
    assert pp.held
    pp.apply_snapshot({})                          # ปล่อยกลางอากาศ
    v.step(0.05)
    assert pp.dropped == 1 and pp.placed == 0


def test_barcode_reads_code_with_trigger(app):
    v, w, (conv, bc) = make(DeviceSpec.new("conveyor", 0, 0, address="Y0", part_mode="metal"),
                            DeviceSpec.new("barcode", 0, -100, address="D44", addr_ok="X25", addr_trig="Y15",
                                           read_ms=100))
    conv.spawn()
    wp = conv.parts[0]
    wp.local_x = 0
    wp.place()
    run(v, 0.3)
    assert not bc.ok                               # ยังไม่สั่ง Trigger
    bc.apply_snapshot({"Y15": 1})
    run(v, 0.2)
    assert bc.ok and bc.value == wp.code and 100 <= wp.code <= 199
    assert ("D44", wp.code, "w") in w and ("X25", 1) in w
    conv.clear_parts()
    run(v, 0.1)
    assert not bc.ok and bc.value == wp.code       # D ค้างค่าล่าสุด
