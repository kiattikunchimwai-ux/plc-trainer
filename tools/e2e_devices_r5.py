"""E2E R5 บนหน้าต่างจริง + Mock PLC: ผังรวมอุปกรณ์ R5 ทั้ง 12 ชนิด แล้วใช้ ladder จำลองขับทีละตัว
ตรวจผลแบบ black-box (สถานะอุปกรณ์ + ค่าที่ PLC เห็น) และถ่ายภาพหน้าจอทุกช่วง

รัน:  .venv\\Scripts\\python.exe tools\\e2e_devices_r5.py docs\\devices_r5_test\\r5.png
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.main import load_config  # noqa: E402
from plc_game.panel import DeviceSpec as D, PanelDoc  # noqa: E402
from plc_game.plc.device import parse_device  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402
from plc_game.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/devices_r5_test/r5.png")
out.parent.mkdir(parents=True, exist_ok=True)
backups = {f: (f.read_bytes() if f.exists() else None)
           for f in (scores.SCORE_FILE, classroom.STUDENT_FILE, state.STATE_FILE)}

# ---------------- ผังรวมอุปกรณ์ R5 ----------------
es = D.new("estop", -620, -10, label="E-Stop", address="X12", contact="NC")
DEVICES = [
    es,
    D.new("safety_relay", -500, 0, label="SR1", address="X13", addr_aux="X14", addr_reset="Y11", link_estop=es.id),
    D.new("phase_relay", -380, 0, label="PR1", address="X11", trip_s=1.0, reset_s=0.5),
    D.new("relay", -270, 0, label="CR1", address="Y6", addr_c1="X6", addr_c3="X7"),
    D.new("latch_relay", -170, 0, label="LR1", address="Y7", addr_c1="X10"),
    D.new("ssr", -60, 0, label="SSR1", address="Y10", load="heater", load_a=10.0),
    D.new("pushbutton", 60, 0, label="Start Y-Δ", address="X0", color="green"),
    D.new("motor_yd", -520, 230, label="M1 Y-Δ", address="Y0", addr_star="Y1", addr_delta="Y2", addr_ol="X1",
          fla=15.0, accel_s=4.0),
    D.new("cylinder", -170, 230, label="Cyl 5/3", address="Y3", addr_sol_b="Y4", addr_ret="X2", addr_ext="X3",
          valve="c_closed", stroke_s=1.0),
    D.new("cylinder", 200, 230, label="Cyl ทางเดียว", address="Y5", addr_ret="X4", addr_ext="X5",
          actuation="single", stroke_s=0.5),
    D.new("vacuum", -560, 450, label="VAC1", address="Y12", addr_blow="Y13", addr_ok="X15", addr_lift="Y14",
          addr_kpa="D60"),
    D.new("dc_motor", -390, 450, label="BLDC1", address="Y15", addr_rev="Y16", addr_speed="D0", addr_alarm="X16",
          addr_rpm="D2", drive="bldc", accel_s=1.0, decel_s=1.0),
    D.new("stepper", -50, 450, label="STP1", address="Y17", addr_start="Y20", addr_target="D50", addr_jog_r="Y21",
          addr_busy="X17", addr_home="X20", addr_pos="D52"),
]
R5_KINDS = {"safety_relay", "phase_relay", "relay", "latch_relay", "ssr", "motor_yd", "vacuum", "dc_motor", "stepper"}
scene = out.with_name("r5_devices.plcpanel")
PanelDoc("R5: อุปกรณ์นิวเมติกส์ + มอเตอร์ + รีเลย์ชุดใหม่", DEVICES).save(scene)

QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
cfg = load_config()
cfg["backend"] = "mock"
w = MainWindow(cfg)
w.resize(1600, 950)
w.show()
w.set_split(False)
results = []
last = {}

# ---------------- ladder ใน Mock PLC ----------------
CMD: dict[str, int] = {}          # ค่าที่สคริปต์สั่งตรง (แทนวงจรที่ไม่ใช่จุดทดสอบ)
LOGIC: list = []                  # ladder จริงที่ทำงานตามอินพุต (black-box)


OUTS = ["Y%o" % i for i in range(0o22)] + ["D0", "D50"]     # เอาต์พุต/ค่าสั่งที่ ladder เป็นเจ้าของ


def prog(mem, now, ctx):
    if not ctx.get("_init"):                  # เปลี่ยน ladder = เริ่มจากเอาต์พุตเป็น 0 ทั้งหมด (เหมือน Write โปรแกรมใหม่)
        ctx["_init"] = True
        for a in OUTS:
            d = parse_device(a, cli.xy_base)
            mem[d.kind][d.number] = 0
    for a, v in CMD.items():
        d = parse_device(a, cli.xy_base)
        mem[d.kind][d.number] = v
    for f in LOGIC:
        f(mem, now, ctx)


def io(mem, a):
    d = parse_device(a, cli.xy_base)
    return mem[d.kind], d.number


def yd_ladder(star_s):
    """Start (X0) → KM1+KM2 (สตาร์) → ครบ star_s วินาที → ปลด KM2 → 0.1 s → KM3 (เดลต้า) · OL (X1) = 0 → หยุด."""
    def f(mem, now, ctx):
        X, xi = io(mem, "X0")
        Y = mem["Y"]
        y = {k: io(mem, k)[1] for k in ("Y0", "Y1", "Y2")}
        ol_ok = io(mem, "X1")[0][io(mem, "X1")[1]]
        if X[xi] and "t0" not in ctx:
            ctx["t0"] = now
        if "t0" in ctx and ol_ok:
            t = now - ctx["t0"]
            Y[y["Y0"]] = 1
            Y[y["Y1"]] = int(t < star_s)
            Y[y["Y2"]] = int(t >= star_s + 0.1)
        else:
            Y[y["Y0"]] = Y[y["Y1"]] = Y[y["Y2"]] = 0
    return f


def vac_ladder(mem, now, ctx):
    """ดูดเมื่อสั่ง (CMD Y12) · ยก (Y14) ได้เฉพาะเมื่อสวิตช์สุญญากาศ OK (X15) — interlock ใน ladder."""
    Y, y14 = io(mem, "Y14")
    Xm, x15 = io(mem, "X15")
    want = ctx.get("lift_req", 0)
    Y[y14] = int(want and (Xm[x15] or Y[y14]) and io(mem, "Y12")[0][io(mem, "Y12")[1]])


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


def set_ladder(cmd=None, logic=()):
    CMD.clear()
    CMD.update(cmd or {})
    LOGIC[:] = list(logic)
    cli._ctx = {}


def item(label):
    return next(it for it in w.panel.items_by_id.values() if it.label == label)


def shot(name):
    w.grab().save(str(out.with_name(out.stem + f"_{name}.png")))


try:
    w._load_panel(scene)
    w.set_edit_mode(False)
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    w.connect_plc()
    pump(1.0)
    cli = w.poller.client
    cli.program, cli._ctx = prog, {}
    w.poller.snapshot.connect(lambda s, t: last.update(s))
    w.panel.fit_all()
    pump(0.8)
    its = list(w.panel.items_by_id.values())
    kinds = {it.spec.kind for it in its}
    check("โหลดผัง R5 บนหน้าต่างจริง: ครบทุกชนิด + address ถูกทั้งหมด",
          R5_KINDS <= kinds and all(it.valid and not it.conflict for it in its),
          f"{len(its)} อุปกรณ์, ไม่ถูก: {[it.label for it in its if not it.valid or it.conflict]}")
    shot("scene")

    # ---- 1. สตาร์-เดลต้า: ladder ถูก (สตาร์ 5 s) ----
    m = item("M1 Y-Δ")
    set_ladder(logic=[yd_ladder(5.0)])
    w._history.clear()
    w.panel.press("X0", 300)
    pump(2.0)
    check("Y-Δ: กด Start → ต่อสตาร์ (KM1+KM2) กระแส ~2×FLA", m.mode == "star" and m.current_a < 2.1 * 15,
          m.state_text())
    shot("yd_star")
    pump(4.5)
    fs = [f.title for f in w.levelp.analyze_live(list(w._history))]
    check("Y-Δ: ครบ 5 s สลับเป็นเดลต้า รอบเต็ม ไม่มีคำเตือน", m.mode == "delta" and m.jerk_count == 0
          and m.speed > 0.95 and last.get("X1") == 1, m.state_text())
    check("AI วิเคราะห์ (ladder ถูก): ไม่เตือนสตาร์-เดลต้า", not any("เดลต้า" in t for t in fs), " | ".join(fs))
    shot("yd_delta")
    # ladder ผิด: สลับเร็ว 0.5 s
    set_ladder()
    pump(6.0)                                             # หยุดให้รอบลงก่อน
    set_ladder(logic=[yd_ladder(0.5)])
    w._history.clear()
    w.panel.press("X0", 300)
    pump(1.5)
    fs = [f.title for f in w.levelp.analyze_live(list(w._history))]
    check("Y-Δ ladder ผิด (สตาร์ 0.5 s): อุปกรณ์เตือนสลับเร็ว + AI จับได้",
          m.jerk_count == 1 and any("เร็วเกินไป" in t for t in fs), " | ".join(fs))
    shot("yd_fast")
    set_ladder()
    pump(1.0)

    # ---- 2. กระบอกสูบ 5/3 กลางปิด + ทางเดียว ----
    c53, c1 = item("Cyl 5/3"), item("Cyl ทางเดียว")
    set_ladder({"Y3": 1, "Y5": 1})
    pump(0.5)
    set_ladder({"Y5": 1})                                 # ปล่อย A → วาล์วกลับกลาง → ค้างกลางทาง
    pump(1.0)
    mid = c53.pos_k
    pump(1.0)
    check("5/3 กลางปิด: ปล่อยทั้งสองโซลินอยด์ → หยุดค้างกลางทาง", 0.2 < mid < 0.9 and abs(c53.pos_k - mid) < 1e-6
          and last.get("X2") == 0 and last.get("X3") == 0, f"pos={c53.pos_k:.2f}")
    check("กระบอกทางเดียว: สั่ง A → ยื่นสุด (a1 = 1)", c1.pos_k == 1.0 and last.get("X5") == 1)
    shot("cylinders")
    set_ladder({"Y4": 1})
    pump(1.5)
    check("5/3 สั่ง B → หดสุด · ทางเดียวตัดไฟ → สปริงดันกลับ", c53.pos_k == 0 and c1.pos_k == 0
          and last.get("X2") == 1 and last.get("X4") == 1)

    # ---- 3. รีเลย์ + latching + SSR + ป้องกันเฟส ----
    set_ladder({"Y6": 1, "Y10": 1})
    pump(0.5)
    check("รีเลย์: คอยล์ ON → PLC เห็น c1 (NO) = 1, c3 (NC) = 0", last.get("X6") == 1 and last.get("X7") == 0)
    set_ladder({"Y7": 1, "Y10": 1})
    pump(0.3)
    set_ladder({"Y10": 1})
    pump(0.5)
    lr = item("LR1")
    check("Impulse relay: พัลส์ 1 ครั้ง → ON และจำไว้หลังปล่อย", lr.latched and last.get("X10") == 1)
    pump(1.5)
    ssr = item("SSR1")
    check("SSR: สั่ง ON → โหลดฮีตเตอร์นำกระแส + ตัว SSR อุ่นขึ้น", ssr.conduct and ssr.temp > ssr.fnum("ambient") + 0.5,
          ssr.state_text())
    pr = item("PR1")
    pr.set_condition("loss")
    pump(1.6)
    check("รีเลย์ป้องกันเฟส: เฟสขาด → หน่วง 1 s → PLC เห็น OK = 0", last.get("X11") == 0, pr.state_text())
    shot("relays")
    pr.set_condition("ok")
    set_ladder({"Y7": 1})
    pump(0.3)
    set_ladder()
    pump(1.0)
    check("Impulse พัลส์ครั้งที่ 2 → OFF · ไฟกลับปกติ → OK = 1", not lr.latched and last.get("X10") == 0
          and last.get("X11") == 1)

    # ---- 4. เซฟตี้รีเลย์ + E-Stop ----
    sr, estop = item("SR1"), item("E-Stop")
    check("เซฟตี้รีเลย์: เปิดเครื่องแล้วยังไม่รีเซ็ต → 13-14 = 0, 41-42 = 1", last.get("X13") == 0 and last.get("X14") == 1)
    set_ladder({"Y11": 1})
    pump(0.3)
    set_ladder()
    pump(0.4)
    check("รีเซ็ตด้วย Y (monitored, ขอบขาลง) → 13-14 = 1", last.get("X13") == 1 and sr.out)
    estop.set_actuated(True)
    pump(0.4)
    ok_cut = last.get("X13") == 0
    estop.set_actuated(False)
    pump(0.6)
    check("กด E-Stop → ตัดทันที · ปลดแล้วไม่เดินเอง", ok_cut and last.get("X13") == 0 and not sr.out)
    shot("safety")
    set_ladder({"Y11": 1})
    pump(0.3)
    set_ladder()
    pump(0.4)
    check("รีเซ็ตอีกครั้ง → กลับมา ON", last.get("X13") == 1)

    # ---- 5. ชุดสุญญากาศ: ยกได้เมื่อ OK (interlock ใน ladder) ----
    vac = item("VAC1")
    set_ladder({"Y12": 1}, [vac_ladder])
    cli._ctx["lift_req"] = 1
    pump(1.5)
    check("สุญญากาศ: ดูด → OK (X15) → ladder ยก → ชิ้นงานติดถ้วย", vac.held and last.get("X15") == 1
          and last.get("D60", 0) > 700, vac.state_text())
    shot("vacuum")
    cli._ctx["lift_req"] = 0
    pump(1.0)
    set_ladder({"Y13": 1})
    pump(0.5)
    check("วางลง + เป่าปล่อย → นับยกสำเร็จ 1 ครั้ง, OK ดับ", vac.lifted == 1 and not vac.held and last.get("X15") == 0)
    set_ladder()

    # ---- 6. BLDC ----
    dc = item("BLDC1")
    set_ladder({"Y15": 1, "D0": 2000})
    pump(1.5)
    check("BLDC: EN + D0 = 2000 → รอบจริง (D2) ≈ 1500 rpm", abs(last.get("D2", 0) - 1500) <= 30, dc.state_text())
    set_ladder({"Y15": 1, "Y16": 1, "D0": 2000})
    pump(0.4)
    slowing = 0 < dc.speed < 0.5
    pump(1.5)
    check("BLDC: กลับ DIR ขณะหมุน → ชะลอผ่าน 0 แล้วหมุนกลับ", slowing and last.get("D2", 0) < -1400, dc.state_text())
    shot("bldc")
    set_ladder()

    # ---- 7. Stepper ----
    st = item("STP1")
    set_ladder({"Y17": 1, "D50": 3200})
    pump(0.3)
    busy_seen = []
    w.poller.snapshot.connect(lambda s, t: busy_seen.append(s.get("X17", 0)))
    set_ladder({"Y17": 1, "Y20": 1, "D50": 3200})
    pump(0.3)
    set_ladder({"Y17": 1, "D50": 3200})
    pump(1.5)
    check("Stepper: START → BUSY ระหว่างเคลื่อน → ถึง 3200 พัลส์ = 10 mm (1 รอบ)",
          1 in busy_seen and last.get("X17") == 0 and last.get("D52") == 3200
          and abs(st.mm(st.actual) - 10.0) < 0.1, st.state_text())
    st.set_fault("lost_steps")
    set_ladder({"Y17": 1, "Y20": 1, "D50": 9600})
    pump(0.3)
    set_ladder({"Y17": 1, "D50": 9600})
    pump(2.0)
    check("Stepper หลุดสเต็ป: ตัวนับ 9600 แต่ตำแหน่งจริงไม่ถึง 30 mm", last.get("D52") == 9600
          and abs(st.lost_mm()) > 0.5, st.state_text())
    shot("stepper_lost")
    st.set_fault("")
    set_ladder({"Y17": 1, "Y21": 1})
    pump(6.0)
    check("Jog ถอยจนเจอ Home → ตัวนับรีเซ็ต 0 + เซนเซอร์ Home = 1", last.get("D52") == 0 and last.get("X20") == 1
          and abs(st.lost_mm()) <= 0.5, st.state_text())
    set_ladder()
    pump(0.5)

    # ---- 8. Fault Injection บนอุปกรณ์ใหม่ ----
    w.panel.set_fault(item("CR1"), "weld")
    pump(0.5)
    check("ใส่ความผิดปกติ (รีเลย์หน้าสัมผัสเชื่อมติด) → PLC เห็น c1 = 1 ทั้งที่คอยล์ OFF", last.get("X6") == 1)
    w.panel.clear_faults()
    pump(0.5)
    check("ล้างความผิดปกติ → c1 กลับเป็น 0", last.get("X6") == 0)
    w.panel.fit_all()
    pump(0.5)
    w.grab().save(str(out))
finally:
    if w.poller:
        w.disconnect_plc()
    pump(0.3)
    w.dirty = False
    for f, data in backups.items():
        if data is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(data)
print(f"\nสรุป: ผ่าน {sum(results)}/{len(results)}")
sys.exit(0 if results and all(results) else 1)
