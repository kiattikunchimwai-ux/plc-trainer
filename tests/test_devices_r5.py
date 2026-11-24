"""R5: อุปกรณ์นิวเมติกส์ + มอเตอร์ชุดใหม่ (วาล์ว 5/3, กระบอกทางเดียว, สตาร์-เดลต้า, สุญญากาศ, DC/BLDC, stepper)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.ui.panel.view import PanelView  # noqa: E402


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


def paints_ok(item):
    """วาดลงภาพได้โดยไม่ error (ครอบทุกสาขาของ paint_body)."""
    img = QImage(400, 200, QImage.Format_ARGB32)
    p = QPainter(img)
    p.translate(200, 100)
    item.paint_body(p)
    p.end()
    r = item.body_rect()
    return QRectF(r).isValid()


def cyl(**kw):
    base = dict(address="Y5", addr_sol_b="Y6", addr_ret="X10", addr_ext="X11", stroke_s=0.5)
    base.update(kw)
    return DeviceSpec.new("cylinder", **base)


# ======================= 1. กระบอกสูบ: 5/3 + ทางเดียว =======================
def test_old_valves_unchanged(app):
    """ผังเก่า: 5/2 โซลินอยด์เดียว/สองโซลินอยด์ ทำงานเหมือนเดิม และขนาดตัวอุปกรณ์ไม่เปลี่ยน."""
    v, w, (c,) = make(cyl())
    assert (c.W, c.H) == (280, 70) and not c.three_pos and not c.single_acting
    c.apply_snapshot({"Y5": 1})
    run(v, 0.7)
    assert c.pos_k == 1.0 and ("X11", 1) in w
    c.apply_snapshot({"Y5": 0})
    run(v, 0.7)
    assert c.pos_k == 0.0
    v, w, (d,) = make(cyl(valve="double"))
    d.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.7)
    d.apply_snapshot({"Y5": 0, "Y6": 0})
    run(v, 0.7)
    assert d.pos_k == 1.0


def test_5_3_closed_center_stops_midway(app):
    v, w, (c,) = make(cyl(valve="c_closed", stroke_s=1.0))
    assert c.three_pos
    c.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.5)                                   # ครึ่งทาง
    c.apply_snapshot({"Y5": 0, "Y6": 0})          # ปล่อยทั้งคู่ → ตำแหน่งกลาง → ค้าง
    mid = c.pos_k
    run(v, 2.0)
    assert 0.3 < mid < 0.7 and c.pos_k == pytest.approx(mid) and c.spool == "mid"
    assert not c.reed["addr_ret"] and not c.reed["addr_ext"]          # ไม่ถึงปลายทั้งสองข้าง
    assert "ปิดทุกพอร์ต" in c.state_text()
    c.apply_snapshot({"Y5": 0, "Y6": 1})
    run(v, 1.2)
    assert c.pos_k == 0.0 and c.reed["addr_ret"]


def test_5_3_exhaust_center_drifts_back_with_load(app):
    v, _, (c,) = make(cyl(valve="c_exhaust", stroke_s=0.5, load_kg=5.0))
    c.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.7)
    assert c.pos_k == 1.0
    c.apply_snapshot({"Y5": 0, "Y6": 0})
    run(v, 0.5)
    assert 0.5 < c.pos_k < 1.0                    # ไหลกลับช้า ๆ (ช้ากว่าปกติ CREEP เท่า)
    run(v, 2.0)
    assert c.pos_k == 0.0
    v, _, (n,) = make(cyl(valve="c_exhaust", stroke_s=0.5, load_kg=0.0))
    n.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.7)
    n.apply_snapshot({"Y5": 0, "Y6": 0})
    run(v, 2.0)
    assert n.pos_k == 1.0                         # ไม่มีโหลด → ลอยอยู่กับที่


def test_5_3_pressure_center_creeps_out(app):
    v, _, (c,) = make(cyl(valve="c_pressure", stroke_s=0.5))
    c.apply_snapshot({"Y5": 0, "Y6": 0})
    run(v, 0.5)
    assert 0.0 < c.pos_k < 0.5
    run(v, 2.0)
    assert c.pos_k == 1.0


def test_5_3_both_solenoids_is_conflict(app):
    v, _, (c,) = make(cyl(valve="c_closed"))
    c.apply_snapshot({"Y5": 1, "Y6": 1})
    run(v, 1.0)
    assert c.sol_conflict and c.spool == "mid" and c.pos_k == 0.0
    assert not c.conflict                         # คนละเรื่องกับ "address ซ้ำ" ของ DeviceItem
    assert "พร้อมกัน" in c.state_text()


def test_single_acting_spring_returns_without_air(app):
    v, w, (c,) = make(cyl(actuation="single", valve="double", stroke_s=0.5))
    assert c.single_acting and not c.three_pos
    c.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.7)
    assert c.pos_k == 1.0
    c.apply_snapshot({"Y5": 0, "Y6": 1})          # โซลินอยด์ B ไม่มีผลกับกระบอกทางเดียว
    c.fault = "no_air"                            # ลมหาย → สปริงยังดันกลับ
    run(v, 0.7)
    assert c.pos_k == 0.0 and c.reed["addr_ret"]
    c.apply_snapshot({"Y5": 1, "Y6": 0})
    run(v, 0.7)
    assert c.pos_k == 0.0                         # ไม่มีลม → ยื่นไม่ได้


def test_cylinder_variants_paint(app):
    for kw in ({}, {"valve": "double"}, {"valve": "c_closed"}, {"valve": "c_exhaust"}, {"valve": "c_pressure"},
               {"actuation": "single"}):
        _, _, (c,) = make(cyl(**kw))
        c.apply_snapshot({"Y5": 1, "Y6": 1})
        c.tick(0.05)
        assert paints_ok(c), kw
    _, _, (pu,) = make(DeviceSpec.new("pusher", address="Y5", valve="c_closed", addr_sol_b="Y6"))
    pu.tick(0.05)
    assert paints_ok(pu)


# ======================= 3. มอเตอร์สตาร์-เดลต้า =======================
def yd(**kw):
    base = dict(address="Y0", addr_star="Y1", addr_delta="Y2", addr_ol="X5", accel_s=4.0)
    base.update(kw)
    return DeviceSpec.new("motor_yd", **base)


def test_yd_correct_sequence(app):
    v, w, (m,) = make(yd())
    run(v, 0.1)
    assert ("X5", 1) in w                                 # OL ปกติ (NC = 1)
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    run(v, 0.2)
    assert m.mode == "star" and 1.5 * 15 < m.current_a <= 2.0 * 15   # กระแสสตาร์ท ~2×FLA
    run(v, 5.0)
    assert m.speed == pytest.approx(0.9) and m.current_a < 15
    m.apply_snapshot({"Y0": 1, "Y1": 0, "Y2": 1})
    run(v, 2.0)
    assert m.mode == "delta" and m.speed == 1.0 and m.jerk_t == 0 and m.jerk_count == 0
    assert "⚠" not in m.state_text()
    m.apply_snapshot({})
    run(v, 6.0)
    assert m.speed == 0 and m.mode == "off"


def test_yd_star_delta_together_is_short(app):
    v, _, (m,) = make(yd())
    m.apply_snapshot({"Y0": 1, "Y1": 1, "Y2": 1})
    run(v, 1.0)
    assert m.mode == "short" and m.speed == 0 and "ลัดวงจร" in m.state_text()
    m.apply_snapshot({"Y0": 1, "Y1": 1, "Y2": 0})        # ปลดแค่ตัวเดียว → ยังค้างลัดวงจร
    run(v, 0.5)
    assert m.mode == "short"
    m.apply_snapshot({"Y0": 1})                          # ตัดทั้งคู่ → หาย
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    run(v, 0.5)
    assert m.mode == "star" and m.speed > 0


def test_yd_switch_too_fast_and_dol(app):
    v, _, (m,) = make(yd())
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    run(v, 0.5)
    m.apply_snapshot({"Y0": 1, "Y2": 1})                 # สลับตอนรอบ ~11%
    run(v, 0.1)
    assert m.jerk_t > 0 and m.current_a > 4 * 15 and "เร็วเกินไป" in m.state_text()
    v, _, (d,) = make(yd())
    d.apply_snapshot({"Y0": 1, "Y2": 1})                 # เดลต้าตรง ๆ = ต่อตรง (DOL)
    run(v, 0.1)
    assert d.jerk_count == 1


def test_yd_open_star_too_long_and_ol(app):
    v, w, (m,) = make(yd(star_max_s=3))
    m.apply_snapshot({"Y0": 1})
    run(v, 1.0)
    assert m.mode == "open" and m.speed == 0             # มีแค่ Main = ไม่หมุน
    m.apply_snapshot({"Y1": 1})
    run(v, 1.0)
    assert m.mode == "off" and m.speed == 0              # ไม่มี Main = ไม่หมุน
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    run(v, 4.0)
    assert m.star_too_long() and "ค้างสตาร์" in m.state_text()
    m.set_fault("jammed")                                # ติดขัด → กระแสล็อกโรเตอร์ → OL ทริป
    m.apply_snapshot({"Y0": 1, "Y2": 1})
    run(v, 20.0)
    assert m.ol_tripped and ("X5", 0) in w and m.mode == "off"
    m.on_press(None)
    assert m.ol_tripped                                  # ยังร้อน รีเซ็ตไม่ได้
    m.set_fault("")
    m.apply_snapshot({})
    run(v, 300.0)
    m.on_press(None)
    run(v, 0.1)
    assert not m.ol_tripped and ("X5", 1) in w


def test_yd_star_open_fault(app):
    v, _, (m,) = make(yd())
    m.set_fault("star_open")
    m.apply_snapshot({"Y0": 1, "Y1": 1})
    run(v, 2.0)
    assert m.mode == "open" and m.speed == 0


def test_yd_analyzer_black_box():
    from plc_game.ai.analyzer import analyze_live
    spec = yd()
    good = [(0.0, {}), (1.0, {"Y0": 1, "Y1": 1}), (7.0, {"Y0": 1}), (7.1, {"Y0": 1, "Y2": 1}), (12.0, {})]
    assert not any("สตาร์" in f.title or "เดลต้า" in f.title for f in analyze_live(good, [spec]))
    short = [(0.0, {}), (1.0, {"Y0": 1, "Y1": 1, "Y2": 1}), (2.0, {})]
    assert any("ลัดวงจร" in f.title for f in analyze_live(short, [spec]))
    fast = [(0.0, {}), (1.0, {"Y0": 1, "Y1": 1}), (1.5, {"Y0": 1, "Y2": 1}), (5.0, {})]
    assert any("เร็วเกินไป" in f.title for f in analyze_live(fast, [spec]))


def test_yd_paints_and_wiring(app):
    from plc_game.panel.wiring import build, to_text
    for snap, fault in (({}, ""), ({"Y0": 1, "Y1": 1}, ""), ({"Y0": 1, "Y2": 1}, ""),
                        ({"Y0": 1, "Y1": 1, "Y2": 1}, ""), ({"Y0": 1, "Y2": 1}, "jammed")):
        v, _, (m,) = make(yd(fla=15))
        m.set_fault(fault)
        m.apply_snapshot(snap)
        run(v, 0.3)
        assert paints_ok(m)
    txt = to_text(build([yd()]))
    assert "Y1" in txt and "Y2" in txt and "KM2" in txt


# ======================= 4. ชุดสุญญากาศ =======================
def vac(**kw):
    base = dict(address="Y6", addr_blow="Y7", addr_ok="X12", addr_lift="Y10", addr_kpa="D60")
    base.update(kw)
    return DeviceSpec.new("vacuum", **base)


def test_vacuum_ok_with_part_not_without(app):
    v, w, (c,) = make(vac())
    c.apply_snapshot({"Y6": 1})
    run(v, 1.0)
    assert c.ok and c.vac > 75 and ("X12", 1) in w and any(x[0] == "D60" and x[1] > 700 for x in w if len(x) == 3)
    c.apply_snapshot({})
    c.part = False
    run(v, 1.0)
    c.apply_snapshot({"Y6": 1})
    run(v, 2.0)
    assert not c.ok and c.vac < 15                       # ไม่มีชิ้นงาน → ได้แค่ ~−10 kPa


def test_vacuum_blow_releases_faster(app):
    def release(blow):
        v, _, (c,) = make(vac())
        c.apply_snapshot({"Y6": 1})
        run(v, 1.0)
        c.apply_snapshot({"Y7": 1} if blow else {})
        t = 0.0
        while c.ok and t < 10:
            run(v, 0.05)
            t += 0.05
        return t
    assert release(True) < 0.2 < 0.5 < release(False)


def test_vacuum_faults(app):
    v, _, (c,) = make(vac())
    c.set_fault("leak")
    c.apply_snapshot({"Y6": 1})
    run(v, 3.0)
    assert not c.ok and 35 < c.vac <= 40
    v, _, (k,) = make(vac())
    k.set_fault("clog")
    k.apply_snapshot({"Y6": 1})
    run(v, 0.5)
    assert not k.ok                                      # ไส้กรองตัน: ช้ากว่าปกติมาก
    run(v, 3.0)
    assert k.ok


def test_vacuum_lift_sequence_and_drop(app):
    v, _, (c,) = make(vac())
    c.apply_snapshot({"Y6": 1})
    run(v, 1.0)
    c.apply_snapshot({"Y6": 1, "Y10": 1})                # ยกหลัง OK → ติดขึ้นมา
    run(v, 1.0)
    assert c.held and c.cup_z == 1.0
    c.apply_snapshot({"Y6": 1})                          # วางลง
    run(v, 1.0)
    c.apply_snapshot({"Y7": 1})                          # เป่าปล่อย
    run(v, 0.3)
    assert not c.held and c.lifted == 1 and c.dropped == 0
    c.apply_snapshot({"Y6": 1, "Y10": 1})                # ยกพร้อมเริ่มดูด → ยังไม่พอ
    run(v, 1.0)
    assert not c.held and "ยกก่อน" in c.state_text()
    v, _, (d,) = make(vac())
    d.apply_snapshot({"Y6": 1})
    run(v, 1.0)
    d.apply_snapshot({"Y6": 1, "Y10": 1})
    run(v, 1.0)
    d.apply_snapshot({"Y10": 1, "Y7": 1})                # เป่ากลางอากาศ → หลุด
    run(v, 0.3)
    assert not d.held and d.dropped == 1 and "หลุด" in d.state_text()


def test_vacuum_click_tray_and_analyzer(app):
    from plc_game.ai.analyzer import analyze_live
    v, _, (c,) = make(vac())
    c.on_press(c._tray_rect().center())
    assert not c.part
    c.on_press(c._tray_rect().center())
    assert c.part
    spec = vac()
    bad = [(0.0, {}), (1.0, {"Y6": 1}), (1.1, {"Y6": 1, "Y10": 1}), (2.0, {"Y6": 1, "Y10": 1, "X12": 1})]
    good = [(0.0, {}), (1.0, {"Y6": 1}), (1.3, {"Y6": 1, "X12": 1}), (1.4, {"Y6": 1, "X12": 1, "Y10": 1})]
    assert any("ก่อนสุญญากาศพอ" in f.title for f in analyze_live(bad, [spec]))
    assert not any("ก่อนสุญญากาศพอ" in f.title for f in analyze_live(good, [spec]))


def test_vacuum_paints(app):
    for snap, fault, part in (({}, "", True), ({"Y6": 1, "Y10": 1}, "", True), ({"Y7": 1}, "leak", False),
                              ({"Y6": 1, "Y7": 1}, "clog", True)):
        v, _, (c,) = make(vac())
        c.part = part
        c.set_fault(fault)
        c.apply_snapshot(snap)
        run(v, 0.6)
        assert paints_ok(c)


# ======================= 5. มอเตอร์ DC / BLDC =======================
def dcm(**kw):
    base = dict(address="Y0", addr_rev="Y1", addr_speed="D0", addr_alarm="X3", addr_rpm="D2",
                accel_s=0.5, decel_s=0.5, rpm_max=3000)
    base.update(kw)
    return DeviceSpec.new("dc_motor", **base)


def test_dc_brushed_speed_and_short(app):
    v, w, (m,) = make(dcm())
    m.apply_snapshot({"Y0": 1, "D0": 2000})              # 50%
    run(v, 1.0)
    assert m.rpm() == 1500 and ("D2", 1500, "w") in w
    m.apply_snapshot({"Y1": 1, "D0": 4000})              # ถอยหลังเต็มสปีด
    run(v, 1.5)
    assert m.rpm() == -3000
    m.apply_snapshot({"Y0": 1, "Y1": 1, "D0": 4000})
    run(v, 0.2)
    assert m.short and "ลัดวงจร" in m.state_text()
    run(v, 1.0)
    assert m.speed == 0
    v, _, (f,) = make(dcm(addr_speed=""))                # ไม่ผูก D = เต็มสปีด
    f.apply_snapshot({"Y0": 1})
    run(v, 1.0)
    assert f.rpm() == 3000
    f.set_fault("brush_worn")
    run(v, 1.0)
    assert f.rpm() == 1500


def test_dc_bldc_dir_reverse_ramps_and_alarm(app):
    v, w, (m,) = make(dcm(drive="bldc", accel_s=1.0, decel_s=1.0))
    assert "hall_fail" in m.FAULTS and "brush_worn" not in m.FAULTS
    m.apply_snapshot({"Y0": 1, "D0": 4000})
    run(v, 1.2)
    assert m.rpm() == 3000
    m.apply_snapshot({"Y0": 1, "Y1": 1, "D0": 4000})     # กลับ DIR ขณะหมุน (ไม่ใช่ลัดวงจร)
    run(v, 0.5)
    assert not m.short and 0 < m.speed < 1               # กำลังชะลอ
    run(v, 2.0)
    assert m.rpm() == -3000
    m.set_fault("hall_fail")
    run(v, 0.1)
    assert m.alarm and ("X3", 1) in w and "ALARM" in m.state_text()
    run(v, 2.0)
    assert m.speed == 0
    m.apply_snapshot({"D0": 4000})                       # ปิด EN → Alarm ดับ
    run(v, 0.1)
    assert not m.alarm and ("X3", 0) in w


def test_dc_analyzer_and_paint(app):
    from plc_game.ai.analyzer import analyze_live
    bad = [(0.0, {}), (1.0, {"Y0": 1, "Y1": 1}), (2.0, {})]
    assert any("ลัดวงจร" in f.title for f in analyze_live(bad, [dcm()]))
    assert not any("ลัดวงจร" in f.title for f in analyze_live(bad, [dcm(drive="bldc")]))
    for kw, snap, fault in (({}, {}, ""), ({}, {"Y0": 1, "D0": 3000}, ""), ({}, {"Y0": 1, "Y1": 1}, ""),
                            ({"drive": "bldc"}, {"Y0": 1, "Y1": 1}, ""), ({"drive": "bldc"}, {"Y0": 1}, "hall_fail"),
                            ({}, {"Y0": 1}, "jammed")):
        v, _, (m,) = make(dcm(**kw))
        m.set_fault(fault)
        m.apply_snapshot(snap)
        run(v, 0.3)
        assert paints_ok(m)


# ======================= 6. Stepper =======================
def stp(**kw):
    base = dict(address="Y11", addr_start="Y12", addr_target="D50", addr_jog_f="Y13", addr_jog_r="Y14",
                addr_busy="X16", addr_home="X17", addr_pos="D52")
    base.update(kw)
    return DeviceSpec.new("stepper", **base)


def move(v, s, target, ena=1, t=1.5):
    s.apply_snapshot({"Y11": ena, "D50": target})
    s.apply_snapshot({"Y11": ena, "Y12": 1, "D50": target})
    run(v, 0.05)
    busy_seen = s.busy()
    s.apply_snapshot({"Y11": ena, "D50": target})
    run(v, t)
    return busy_seen


def test_stepper_one_rev_and_busy(app):
    v, w, (s,) = make(stp())
    assert s.spr == 3200 and s.ppm == 320                # 1.8° × 1/16, บอลสกรู 10 mm
    run(v, 0.1)
    assert ("X17", 1) in w                               # เริ่มที่ Home
    assert move(v, s, 3200)                              # 1 รอบ = 10 mm, BUSY ON ระหว่างเคลื่อน
    assert s.count == 3200 and s.mm(s.actual) == pytest.approx(10.0) and not s.busy()
    assert ("X16", 1) in w and ("X16", 0) in w and ("D52", 3200, "w") in w and ("X17", 0) in w
    assert "หลุด" not in s.state_text()
    move(v, s, 0)
    assert s.count == 0 and s.at_home()
    move(v, s, 16000, t=3.0)                             # ค่าเริ่มต้น: เต็มความเร็วไป 50 mm ต้องไม่หลุดสเต็ป
    assert not s.stalled and s.mm(s.actual) == pytest.approx(50.0)


def test_stepper_ena_off_ignores_start(app):
    v, _, (s,) = make(stp())
    move(v, s, 3200, ena=0)
    assert s.count == 0 and "ENA OFF" in s.state_text()
    s.mode = None


def test_stepper_overload_loses_steps_then_home(app):
    v, _, (s,) = make(stp(load_pct=110))
    move(v, s, 6400)
    assert s.count == 6400 and s.actual < 6400 and abs(s.lost_mm()) > 0.5
    assert "ไม่ตรงกับที่นับ" in s.state_text()
    # ตั้งโหลดปกติ แล้ว Home ใหม่ด้วย Jog ถอยกลับ
    s.spec.props["load_pct"] = 50
    s.apply_snapshot({"Y11": 1, "Y14": 1})
    run(v, 5.0)
    s.apply_snapshot({"Y11": 1})
    run(v, 0.2)
    assert s.count == 0 and s.at_home() and abs(s.lost_mm()) <= 0.5
    move(v, s, 3200)
    assert s.mm(s.actual) == pytest.approx(10.0, abs=0.5)


def test_stepper_too_fast_accel_stalls(app):
    v, _, (s,) = make(stp(accel_pps2=400000, pps_max=30000, load_pct=90))
    move(v, s, 16000, t=2.0)
    assert s.stalled and s.count == 16000 and s.mm(s.actual) < 49
    v, _, (ok,) = make(stp(load_pct=90, pps_max=8000, accel_pps2=8000))
    move(v, ok, 16000, t=4.0)
    assert not ok.stalled and ok.mm(ok.actual) == pytest.approx(50.0)


def test_stepper_jog_forward_and_faults(app):
    v, _, (s,) = make(stp())
    s.apply_snapshot({"Y11": 1, "Y13": 1})
    run(v, 1.0)
    assert s.busy() and s.count > 2000
    s.apply_snapshot({"Y11": 1})
    run(v, 0.5)
    assert not s.busy()
    v, _, (f,) = make(stp())
    f.set_fault("lost_steps")
    move(v, f, 3200)
    assert f.count == 3200 and f.mm(f.actual) == pytest.approx(9.0)
    f.set_fault("")                                      # Jog ถอยจนเจอ Home → หยุด + ตัวนับ = 0
    f.apply_snapshot({"Y11": 1, "Y14": 1})
    run(v, 5.0)
    assert f.count == 0 and f.at_home() and not f.busy() and f.actual > f.MECH_MIN_MM * f.ppm
    v, _, (a,) = make(stp())
    a.set_fault("driver_alarm")
    move(v, a, 3200)
    assert a.count == 3200 and a.actual == 0


def test_stepper_analyzer_and_paint(app):
    from plc_game.ai.analyzer import analyze_live
    spec = stp()
    bad = [(0.0, {}), (1.0, {"Y12": 1}), (1.2, {}), (2.0, {"Y11": 1}), (2.1, {"Y11": 1, "Y12": 1, "X16": 1}),
           (2.2, {"Y11": 1, "X16": 1}), (2.3, {"Y11": 1, "Y12": 1, "X16": 1})]
    titles = [f.title for f in analyze_live(bad, [spec])]
    assert any("ENA" in t for t in titles) and any("ซ้ำ" in t for t in titles)
    good = [(0.0, {}), (1.0, {"Y11": 1}), (1.1, {"Y11": 1, "Y12": 1}), (1.2, {"Y11": 1, "X16": 1})]
    assert not any("ENA" in f.title or "ซ้ำ" in f.title for f in analyze_live(good, [spec]))
    for kw, fault in (({}, ""), ({"load_pct": 120}, ""), ({}, "driver_alarm")):
        v, _, (s,) = make(stp(**kw))
        s.set_fault(fault)
        move(v, s, 6400, t=0.3)
        assert paints_ok(s)


# ======================= 2. รีเลย์ =======================
RELAYS = ("relay", "latch_relay", "ssr", "phase_relay", "safety_relay")


def test_relay_kinds_complete():
    from plc_game.panel.catalog import CATALOG
    from plc_game.panel.knowledge import KNOW
    from plc_game.panel.presets import PRESETS
    for k in RELAYS:
        info = CATALOG[k]
        assert info.desc and info.aliases and info.specs, k
        assert PRESETS[k] and k in KNOW, k


def test_relay_contacts_delay_and_lever(app):
    v, w, (r,) = make(DeviceSpec.new("relay", address="Y2", addr_c1="X6", addr_c3="X7", pickup_ms=20))
    r.apply_snapshot({"Y2": 0})
    assert ("X6", 0) in w and ("X7", 1) in w            # c1 = NO, c3 = NC (ค่าเริ่มต้น)
    w.clear()
    r.apply_snapshot({"Y2": 1})
    r.tick(0.01)
    assert not r.pulled and w == []                      # ยังไม่ครบเวลาดูด 20 ms
    r.tick(0.02)
    assert r.pulled and ("X6", 1) in w and ("X7", 0) in w
    r.apply_snapshot({"Y2": 0})
    run(v, 0.1)
    assert not r.pulled
    r.on_press(None)                                     # คันโยกทดสอบ (ผ่านเวลาดูดเหมือนกัน)
    run(v, 0.05)
    assert r.pulled and "คันโยก" in r.state_text()
    r.on_press(None)
    run(v, 0.05)
    assert not r.pulled


def test_relay_faults(app):
    v, w, (r,) = make(DeviceSpec.new("relay", address="Y2", addr_c1="X6", addr_c2="X5", pickup_ms=0, release_ms=0))
    r.set_fault("coil_open")
    r.apply_snapshot({"Y2": 1})
    run(v, 0.1)
    assert not r.pulled and r.contact_value(1) == 0
    r.set_fault("weld")
    r.apply_snapshot({"Y2": 0})
    run(v, 0.1)
    assert r.contact_value(1) == 1 and r.contact_value(2) == 0     # ชุด 1 ติดค้าง ชุดอื่นปกติ
    r.set_fault("burnt")
    r.apply_snapshot({"Y2": 1})
    run(v, 0.1)
    assert r.contact_value(1) == 0 and r.contact_value(2) == 1


def test_latch_relay_impulse_toggles_and_remembers(app):
    v, w, (r,) = make(DeviceSpec.new("latch_relay", address="Y3", addr_c1="X7", addr_c2="X5", c2="NC"))
    for s, expect in ((1, True), (0, True), (1, False), (0, False), (1, True)):
        r.apply_snapshot({"Y3": s})
        run(v, 0.05)
        assert r.latched == expect
    assert r.contact_value(1) == 1 and r.contact_value(2) == 0 and ("X7", 1) in w
    r.apply_snapshot({})                                 # PLC หยุด/ตัดการเชื่อมต่อ → จำสถานะ
    run(v, 0.5)
    assert r.latched
    r.apply_snapshot({"Y3": 1})
    run(v, 2.5)
    assert r.latched is False and "ค้างนาน" in r.state_text()
    r.on_press(None)
    assert r.latched


def test_latch_relay_set_reset(app):
    v, _, (r,) = make(DeviceSpec.new("latch_relay", address="Y3", addr_reset="Y4", addr_c1="X7", mode="set_reset"))
    r.apply_snapshot({"Y3": 1, "Y4": 0})
    r.apply_snapshot({"Y3": 0, "Y4": 0})
    assert r.latched
    r.apply_snapshot({"Y3": 1, "Y4": 1})
    assert not r.latched and r.sr_conflict and "RESET ชนะ" in r.state_text()
    r.set_fault("jammed")
    r.apply_snapshot({"Y3": 1, "Y4": 0})
    assert not r.latched


def test_ssr_pwm_leak_and_overheat(app):
    v, _, (s,) = make(DeviceSpec.new("ssr", address="Y4", load="lamp", load_a=0.1, leak_ma=5))
    s.apply_snapshot({"Y4": 1})
    run(v, 0.05)
    assert s.conduct
    s.apply_snapshot({"Y4": 0})
    run(v, 0.05)
    assert not s.conduct and s.leak_glow() > 0           # OFF แต่หลอดติดหรี่
    for _ in range(40):                                  # PWM 50% (ทุก 100 ms) → ความสว่างเฉลี่ย ~50%
        s.apply_snapshot({"Y4": 1})
        run(v, 0.05)
        s.apply_snapshot({"Y4": 0})
        run(v, 0.05)
    assert 0.3 < s.duty < 0.7
    # 10 A ไม่มีฮีตซิงก์ → ร้อนจนพังแบบช็อต (ค้าง ON)
    v, _, (h,) = make(DeviceSpec.new("ssr", address="Y4", load_a=10.0, heatsink="no"))
    h.apply_snapshot({"Y4": 1})
    run(v, 60)
    assert h.burnt and "พัง" in h.state_text()
    h.apply_snapshot({"Y4": 0})
    run(v, 0.1)
    assert h.conduct                                     # ช็อตค้าง: สั่ง OFF แล้วโหลดยังติด
    h.on_press(None)                                     # เปลี่ยนตัวใหม่
    run(v, 0.1)
    assert not h.burnt and not h.conduct
    v, _, (k,) = make(DeviceSpec.new("ssr", address="Y4", load_a=10.0, heatsink="yes"))
    k.apply_snapshot({"Y4": 1})
    run(v, 60)
    assert not k.burnt and k.temp < 60


def test_ssr_faults(app):
    v, _, (s,) = make(DeviceSpec.new("ssr", address="Y4"))
    s.set_fault("open")
    s.apply_snapshot({"Y4": 1})
    run(v, 0.1)
    assert not s.conduct
    s.set_fault("short")
    s.apply_snapshot({"Y4": 0})
    run(v, 0.1)
    assert s.conduct


def test_phase_relay_trips_with_delay(app):
    v, w, (pr,) = make(DeviceSpec.new("phase_relay", address="X10", trip_s=1.0, reset_s=0.5))
    run(v, 0.1)
    assert ("X10", 1) in w
    pr.set_condition("loss")
    run(v, 0.5)
    assert pr.signal() == 1                              # ยังไม่ครบเวลาหน่วง
    run(v, 0.6)
    assert pr.signal() == 0 and ("X10", 0) in w
    pr.set_condition("ok")
    run(v, 0.6)
    assert pr.signal() == 1
    pr.set_condition("rev")                              # สลับเฟส = ทริปเร็ว
    run(v, 0.15)
    assert pr.signal() == 0
    pr.set_condition("ok")
    run(v, 1.0)
    pr.set_fault("no_trip")
    pr.set_condition("under")
    run(v, 2.0)
    assert pr.signal() == 1                              # เสียแบบไม่ทริป
    pr.set_fault("contact_fail")
    assert pr.signal() == 0
    pr.set_fault("")
    pr.on_press(None)                                    # คลิกวนสภาพไฟ
    assert pr.cond == "over"


def _sr(**kw):
    es = DeviceSpec.new("estop", 0, 0, address="X5", contact="NC")
    sr = DeviceSpec.new("safety_relay", 120, 0, address="X11", addr_aux="X12", addr_reset="Y5",
                        link_estop=es.id, **kw)
    return make(es, sr)


def test_safety_relay_estop_and_monitored_reset(app):
    v, w, items = _sr()
    es, sr = sorted(items, key=lambda i: i.x())
    run(v, 0.1)
    assert not sr.out and ("X12", 1) in w                # เริ่มต้นต้องรีเซ็ตก่อน
    sr.apply_snapshot({"Y5": 1})
    run(v, 0.1)
    assert not sr.out                                    # กดค้าง (ขอบขาขึ้น) ยังไม่รีเซ็ต
    sr.apply_snapshot({"Y5": 0})
    run(v, 0.1)
    assert sr.out and ("X11", 1) in w
    es.set_actuated(True)                                # กด E-Stop
    run(v, 0.05)
    assert not sr.out and ("X11", 0) in w
    sr.apply_snapshot({"Y5": 1})
    sr.apply_snapshot({"Y5": 0})
    run(v, 0.1)
    assert not sr.out                                    # ยังกด E-Stop อยู่ → รีเซ็ตไม่ได้
    es.set_actuated(False)
    run(v, 0.5)
    assert not sr.out                                    # ปลด E-Stop แล้วไม่เดินเอง
    rb = sr._reset_rect().center()
    sr.on_press(rb)
    run(v, 0.1)
    assert not sr.out
    sr.on_release(rb)                                    # ปุ่ม RESET บนตัว: ปล่อย = รีเซ็ต
    run(v, 0.1)
    assert sr.out


def test_safety_relay_weld_detected(app):
    v, _, items = _sr()
    es, sr = sorted(items, key=lambda i: i.x())
    sr._rst_req = True
    run(v, 0.1)
    assert sr.out
    sr.set_fault("weld")
    es.set_actuated(True)
    run(v, 0.1)
    assert not sr.out and sr.discrepancy                 # ช่อง 1 เปิด ช่อง 2 ไม่เปิด → ตรวจพบ
    es.set_actuated(False)
    sr._rst_req = True
    run(v, 0.1)
    assert not sr.out and "ไม่ตรงกัน" in sr.state_text()
    sr.set_fault("")                                     # ซ่อมแล้ว ต้องสั่งหยุดอีกครั้งให้ทั้งสองช่องเปิด
    es.set_actuated(True)
    run(v, 0.1)
    es.set_actuated(False)
    sr._rst_req = True
    run(v, 0.1)
    assert sr.out and not sr.discrepancy


def test_safety_relay_auto_and_unlinked(app):
    v, _, (sr,) = make(DeviceSpec.new("safety_relay", address="X11", reset_mode="auto"))
    run(v, 0.1)
    assert sr.out
    top = sr.body_rect().topLeft() + QPointF(20, 20)
    sr.on_press(top)                                     # ไม่ได้ผูก: คลิกครึ่งบน = เปิดวงจร
    run(v, 0.1)
    assert not sr.out and sr.manual_open
    sr.on_press(top)
    run(v, 0.1)
    assert sr.out                                        # auto reset เดินเอง


def test_relays_paint_all_states(app):
    for kind, kw in (("relay", {}), ("latch_relay", {"mode": "set_reset", "addr_reset": "Y4"}),
                     ("ssr", {}), ("ssr", {"load": "lamp", "heatsink": "no"}),
                     ("phase_relay", {}), ("safety_relay", {})):
        _, _, (it,) = make(DeviceSpec.new(kind, **kw))
        for snap in ({}, {a: 1 for a in ("Y2", "Y3", "Y4", "Y5")}):
            it.apply_snapshot(snap)
            it.tick(0.05)
            assert paints_ok(it), kind
        for code in it.FAULTS:
            it.set_fault(code)
            it.tick(0.05)
            assert paints_ok(it), (kind, code)
    _, _, (pr,) = make(DeviceSpec.new("phase_relay"))
    for c in ("loss", "rev", "under", "over"):
        pr.set_condition(c)
        pr.tick(2.0)
        assert paints_ok(pr)
