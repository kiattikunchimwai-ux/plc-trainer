"""นิยามสเปก (ดาต้าชีท) + ค่าการจำลองของอุปกรณ์แต่ละชนิด — ใช้สร้างหน้า Properties อัตโนมัติ.

group:  "spec" = สเปกอุปกรณ์จริง (ดาต้าชีท) · "sim" = การจำลอง · "general" = ทั่วไป
ค่า default ทุกตัวต้องให้พฤติกรรมเหมือนเวอร์ชันก่อน (ผัง/ด่านเดิมทำงานเหมือนเดิม).
"""
from __future__ import annotations

from ..i18n import tr

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecField:
    prop: str
    label: str
    type: str = "num"            # num | choice | text | mtext | link
    unit: str = ""
    lo: float = 0
    hi: float = 100
    step: float = 1
    dec: int = 0
    default: Any = None          # None = ใช้ค่าใน KindInfo.defaults
    group: str = "sim"
    help: str = ""
    choices: tuple = ()          # ((ค่า, ข้อความ), ...)
    links: tuple = ()            # ชนิดอุปกรณ์ที่ผูกได้ (type = link)
    special: str = ""            # ข้อความแทนค่าต่ำสุด เช่น "ทันที", "ตามชนิด"


def N(prop, label, lo, hi, step=1, dec=0, unit="", default=None, group="sim", help="", special=""):
    return SpecField(prop, label, "num", unit, lo, hi, step, dec, default, group, help, special=special)


def C(prop, label, choices, default=None, group="sim", help=""):
    return SpecField(prop, label, "choice", default=default if default is not None else choices[0][0],
                     group=group, help=help, choices=tuple(choices))


def T(prop, label, multiline=False, group="general", help=""):
    return SpecField(prop, label, "mtext" if multiline else "text", group=group, help=help)


def L(prop, label, kinds, help=""):
    return SpecField(prop, label, "link", default="", group="sim", help=help, links=tuple(kinds))


VALVE = C("valve", tr("ชนิดวาล์ว"), (("single", tr("5/2 โซลินอยด์เดียว (สปริงคืน)")),
                                ("double", tr("5/2 สองโซลินอยด์ (ค้างตำแหน่ง)")),
                                ("c_closed", tr("5/3 กลางปิด (Closed center — หยุดค้างกลางทาง)")),
                                ("c_exhaust", tr("5/3 กลางระบาย (Exhaust center — ลูกสูบลอย)")),
                                ("c_pressure", tr("5/3 กลางจ่ายลม (Pressure center — คืบออก)"))), group="spec",
          help=tr("5/2 โซลินอยด์เดียว: ตัดไฟแล้วสปริงดันกลับ · 5/2 สองโซลินอยด์: ค้างตำแหน่งสุดท้ายแม้ตัดไฟ\n"
               "5/3: สั่ง A = ยื่น, สั่ง B = หด, ไม่สั่งทั้งคู่ = สปริงดันแกนวาล์วกลับตำแหน่งกลาง\n"
               "  กลางปิด = ปิดทุกพอร์ต ลูกสูบหยุดค้างกับที่ (หยุดกลางช่วงชักได้)\n"
               "  กลางระบาย = ระบายลมทั้งสองฝั่ง ลูกสูบลอย ถ้ามีโหลดจะไหลกลับเอง\n"
               "  กลางจ่ายลม = จ่ายลมทั้งสองฝั่ง ฝั่งหัวลูกสูบพื้นที่มากกว่า → คืบออกช้า ๆ\n"
               "ห้ามสั่ง A และ B พร้อมกัน (ต้อง interlock ในโปรแกรม)"))
ACTUATION = C("actuation", tr("ชนิดกระบอกสูบ"), (("double", tr("สองทาง (ลมดันทั้งไปและกลับ)")),
                                            ("single", tr("ทางเดียว (สปริงดันกลับ, วาล์ว 3/2)"))), group="spec",
              help=tr("ทางเดียว: ลมดันออกด้านเดียว สปริงในกระบอกดันกลับ — ลมหาย/ไฟดับจะหดกลับเสมอ\n"
                   "ใช้เฉพาะโซลินอยด์ A (ไม่สนใจโซลินอยด์ B และชนิดวาล์ว)"))
BOUNCE = N("bounce_ms", tr("หน้าสัมผัสกระเด้ง (bounce)"), 0, 50, 1, unit=" ms", default=0, special=tr("ไม่มี"),
           help=tr("หน้าสัมผัสจริงจะกระเด้งเปิด-ปิดหลายครั้งในไม่กี่มิลลิวินาทีตอนกด/ปล่อย\n"
                "ถ้าโปรแกรมนับจำนวนครั้งโดยไม่กรอง จะนับเกิน → ใช้สอนเรื่อง debounce"))


def _cyl(stroke_s, bore, stroke, max_s=10):
    return (
        VALVE,
        ACTUATION,
        L("link_air", tr("รับลมจากปั๊มลม"), ("compressor",),
          help=tr("ผูกแล้วใช้ความดันจริงจากถังลม และกินลมทุกครั้งที่ชัก (ไม่ผูก = ใช้ค่าความดันที่ตั้ง)")),
        C("timing", tr("เวลาเคลื่อนที่"), (("fixed", tr("ตั้งเวลาเอง")), ("spec", tr("คำนวณจากสเปก (ขนาด/ลม/โหลด)"))),
          default="fixed", help=tr("คำนวณจากสเปก: แรง = ความดัน × พื้นที่ลูกสูบ, โหลดมาก/ลมน้อย = ช้าลง")),
        N("stroke_s", tr("เวลาเคลื่อนสุดระยะ"), 0.1, max_s, 0.1, 1, " s", default=stroke_s),
        N("bore_mm", tr("ขนาดกระบอก (Bore)"), 8, 125, 1, unit=" mm", default=bore, group="spec",
          help=tr("เส้นผ่านศูนย์กลางลูกสูบ — ใหญ่ = แรงมาก")),
        N("stroke_mm", tr("ช่วงชัก (Stroke)"), 10, 500, 5, unit=" mm", default=stroke, group="spec"),
        N("pressure_bar", tr("ความดันลม"), 0, 10, 0.5, 1, " bar", default=6.0, group="spec",
          help=tr("ลมโรงงานทั่วไป 5–7 bar · ต่ำกว่า 2 bar กระบอกสูบจะไม่ขยับ")),
        N("load_kg", tr("น้ำหนักโหลด"), 0, 500, 0.5, 1, " kg", default=0.0, group="spec"),
    )


MOTOR = (
    N("kw", tr("กำลัง"), 0.1, 30, 0.05, 2, " kW", default=0.75, group="spec"),
    C("volt", tr("แรงดัน"), (("380", tr("3 เฟส 380 V")), ("220", tr("1 เฟส 220 V"))), group="spec"),
    N("fla", tr("กระแสพิกัด (FLA)"), 0, 60, 0.1, 1, " A", default=0.0, group="spec", special=tr("ไม่ระบุ"),
      help=tr("กระแสตอนรับโหลดเต็ม ดูจาก nameplate — ใช้คำนวณกระแสและให้ Overload ทำงานตามจริง")),
    N("rpm", tr("ความเร็วรอบพิกัด"), 100, 3600, 10, unit=" rpm", default=1400, group="spec",
      help=tr("มอเตอร์ 4 ขั้ว 50 Hz ≈ 1400–1450 rpm · 2 ขั้ว ≈ 2850–2900 rpm")),
    C("start", tr("วิธีสตาร์ท"), (("dol", tr("DOL — ต่อตรง (กระแสกระชาก ~6×)")),
                              ("yd", tr("สตาร์-เดลต้า (~2×)")), ("soft", "Soft starter (~3×)")),
      group="spec", help=tr("กระแสตอนเริ่มเดินสูงกว่ากระแสพิกัดหลายเท่า → ต้องเลือก Overload/เบรกเกอร์ให้เหมาะ")),
    N("accel_s", tr("เวลาเร่งถึงรอบ"), 0, 20, 0.1, 1, " s", default=0.0, special=tr("ทันที"),
      help=tr("ความเฉื่อยของโหลด: มอเตอร์จริงต้องใช้เวลาไต่ความเร็ว")),
    N("decel_s", tr("เวลาหมุนฟรีจนหยุด"), 0, 30, 0.1, 1, " s", default=0.0, special=tr("ทันที"),
      help=tr("ตัดไฟแล้วมอเตอร์ยังหมุนต่อด้วยแรงเฉื่อย (ไม่มีเบรก)")),
    N("load_pct", tr("โหลด"), 0, 150, 5, unit=" %", default=80,
      help=tr("เกิน 100% = โหลดเกิน → กระแสเกิน FLA → Overload ทริป")),
)

def _yd_motor():
    from dataclasses import replace
    new = {"kw": 7.5, "fla": 15.0, "rpm": 1450, "accel_s": 4.0, "decel_s": 5.0}
    out = []
    for f in MOTOR:
        if f.prop == "start":
            continue                       # สตาร์-เดลต้าเสมอ
        if f.prop == "accel_s":
            f = replace(f, lo=0.5, special="",
                        help=tr("เวลาไต่จาก 0 ถึงรอบเต็ม · ต่อสตาร์ไต่ได้ราว 90% — ต้องรอให้รอบขึ้นก่อนสลับเป็นเดลต้า"))
        out.append(replace(f, default=new[f.prop]) if f.prop in new else f)
    out.append(N("star_max_s", tr("เวลาค้างสตาร์สูงสุด"), 2, 60, 1, unit=" s", default=15, group="spec",
                 help=tr("ค้างสตาร์นานกว่านี้ = มอเตอร์ร้อน (แรงบิดเหลือ 1/3) · ไทเมอร์สลับ Y→Δ ทั่วไปตั้ง 5–10 s")))
    return tuple(out)


YD_MOTOR = _yd_motor()

COLORABLE = ("lamp", "pushbutton", "note", "zone")

SPECS: dict[str, tuple[SpecField, ...]] = {
    "pushbutton": (
        C("size", tr("ขนาดรูติดตั้ง"), (("22", tr("Ø22 mm (มาตรฐาน)")), ("30", "Ø30 mm")), group="spec"),
        BOUNCE,
    ),
    "limit": (
        C("actuator", tr("ชนิดก้าน"), (("roller", tr("ก้านโยกลูกล้อ")), ("plunger", tr("ปุ่มกดลูกล้อ"))), group="spec"),
        BOUNCE,
    ),
    "estop": (
        C("release", tr("การปลดล็อก"), (("twist", tr("บิดคลาย")), ("pull", tr("ดึงคลาย")), ("key", tr("กุญแจ"))), group="spec",
          help=tr("E-Stop จริงกดแล้วล็อกค้าง ต้องปลดด้วยมือก่อนเดินเครื่องใหม่")),
    ),
    "overload": (
        N("ir_a", tr("กระแสตั้ง (Ir)"), 0, 100, 0.1, 1, " A", default=0.0, group="spec", special=tr("ไม่ใช้ (นับเวลา)"),
          help=tr("ตั้งเท่ากับ FLA ของมอเตอร์ · ใช้โมเดลความร้อน I²t: กระแสยิ่งเกินมาก ยิ่งทริปเร็ว")),
        C("trip_class", "Trip class", (("10", tr("Class 10 (≤10 s ที่ 7.2×Ir)")), ("20", "Class 20 (≤20 s)"),
                                       ("30", "Class 30 (≤30 s)")), group="spec",
          help=tr("Class 10 = มอเตอร์ทั่วไป · Class 20/30 = โหลดเฉื่อยมาก สตาร์ทนาน")),
        C("reset", tr("การรีเซ็ต"), (("manual", tr("Manual — กดรีเซ็ตเอง")), ("auto", tr("Auto — รีเซ็ตเมื่อเย็นลง"))),
          group="spec", help=tr("Manual ปลอดภัยกว่า: มอเตอร์ไม่เดินเองหลังเย็นลง")),
        N("trip_s", tr("ทริปเองเมื่อมอเตอร์ทำงานเกิน"), 0, 600, 1, unit=" s", default=0, special=tr("ปิด"),
          help=tr("(โหมดง่าย ใช้เมื่อไม่ได้ตั้ง Ir) นับเวลามอเตอร์ทำงานต่อเนื่อง")),
    ),
    "lamp": (
        C("lamp_type", tr("ชนิดหลอด"), (("led", tr("LED (ติด/ดับทันที)")), ("incand", tr("หลอดไส้ (ค่อยๆ สว่าง/หรี่)"))),
          group="spec"),
        C("volt", tr("แรงดัน"), (("24vdc", "24 VDC"), ("220vac", "220 VAC")), group="spec",
          help=tr("24 VDC ต่อตรงจากเอาต์พุตทรานซิสเตอร์ได้ · 220 VAC ต้องใช้เอาต์พุตรีเลย์")),
    ),
    "sensor": (
        C("sense", tr("ชนิดเซนเซอร์"), (("photo", tr("Photoelectric — ลำแสง เห็นทุกชิ้น")),
                                    ("inductive", tr("Inductive — เฉพาะโลหะ ระยะสั้น")),
                                    ("capacitive", tr("Capacitive — ทุกวัสดุ ระยะสั้น"))), group="spec"),
        C("output", tr("ชนิดเอาต์พุต"), (("npn", "NPN (Sink)"), ("pnp", "PNP (Source)")), group="spec",
          help=tr("NPN: ต่อขา S/S ของ PLC เข้ากับ +24V · PNP: ต่อ S/S เข้ากับ 0V\n"
               "ต่อผิดแบบ = PLC ไม่เห็นสัญญาณ (ไม่เสียหาย)")),
        N("range_mm", tr("ระยะตรวจจับ"), 0, 400, 5, unit=" mm", default=0, group="spec", special=tr("ตามชนิด"),
          help=tr("Inductive M18 ≈ 5–8 mm, Photo diffuse ≈ 100–300 mm (บนผัง 1 px = 1 mm)")),
        C("mode", tr("โหมดเอาต์พุต"), (("lon", tr("Light-ON (เจอชิ้นงาน = ON)")), ("don", tr("Dark-ON (เจอชิ้นงาน = OFF)"))),
          group="spec", help=tr("สวิตช์บนตัวเซนเซอร์จริง เลือกให้ OUT ติดเมื่อเจอหรือไม่เจอวัตถุ")),
        N("response_ms", tr("เวลาตอบสนอง"), 0, 500, 1, unit=" ms", default=0, special=tr("ทันที"),
          help=tr("ชิ้นงานวิ่งเร็วแต่เซนเซอร์ตอบสนองช้า → อาจมองไม่เห็นชิ้นงาน")),
    ),
    "encoder": (
        N("pulse_hz", tr("จำนวนพัลส์ต่อวินาที"), 0.5, 10, 0.5, 1, " Hz"),
        N("ppr", tr("ความละเอียด (PPR)"), 0, 1000, 1, unit=tr(" พัลส์/รอบ"), default=0, group="spec",
          special=tr("ไม่ใช้ (ตั้ง Hz เอง)"), help=tr("พัลส์ต่อรอบ — ใช้คู่กับล้อวัดที่แตะสายพาน")),
        N("wheel_mm", tr("เส้นผ่านศูนย์กลางล้อวัด"), 10, 500, 5, unit=" mm", default=50, group="spec"),
        L("link_conv", tr("ล้อวัดแตะสายพาน"), ("conveyor",),
          help=tr("ผูกกับสายพาน → ความถี่พัลส์ = ความเร็วสายพาน ÷ เส้นรอบวงล้อ × PPR")),
    ),
    "conveyor": (
        N("length", tr("ความยาว"), 160, 1600, 20, unit=" px", group="general"),
        N("speed", tr("ความเร็ว"), 20, 600, 10, unit=" mm/s"),
        C("part_mode", tr("ชิ้นงานที่ปล่อย"), (("random", tr("สุ่มโลหะ/พลาสติก")), ("metal", tr("โลหะทั้งหมด")),
                                          ("plastic", tr("พลาสติกทั้งหมด")))),
    ),
    "motor": MOTOR,
    "motor_rev": MOTOR,
    "motor_yd": YD_MOTOR,
    "contactor": (
        C("coil", tr("แรงดันคอยล์"), (("24vdc", "24 VDC"), ("220vac", "220 VAC")), group="spec",
          help=tr("คอยล์ 220 VAC ต้องสั่งผ่านเอาต์พุตรีเลย์ของ PLC")),
        N("pickup_ms", tr("เวลาดูด (pick-up)"), 0, 200, 5, unit=" ms", default=0, special=tr("ทันที"),
          help=tr("คอนแทคเตอร์จริงใช้เวลา 10–40 ms กว่าหน้าสัมผัสจะต่อ")),
    ),
    "vfd": (
        N("ramp_s", tr("เวลาเร่ง 0→50 Hz"), 0.1, 30, 0.5, 1, " s"),
        N("decel_s", tr("เวลาลด 50→0 Hz"), 0, 30, 0.5, 1, " s", default=0.0, special=tr("เท่าเวลาเร่ง")),
        N("max_hz", tr("ความถี่สูงสุด"), 10, 120, 5, unit=" Hz"),
        N("motor_rpm", tr("รอบมอเตอร์ที่ 50 Hz"), 100, 3600, 10, unit=" rpm", default=1450, group="spec"),
    ),
    "axis": (
        C("style", tr("รูปแบบ"), (("slide", tr("แกนสไลด์ (แนวนอน)")), ("elevator", tr("ลิฟต์ (แนวตั้ง)")),
                              ("door", tr("ประตูม้วน (ขึ้น = เปิด)"))), group="general"),
        N("travel_s", tr("เวลาเคลื่อนสุดระยะ"), 0.5, 60, 0.5, 1, " s"),
    ),
    "cylinder": _cyl(1.0, 32, 100),
    "pusher": _cyl(0.4, 20, 50),
    "tank": (
        C("rate_mode", tr("อัตราไหล"), (("pct", tr("ตั้งเป็น %/วินาที")), ("spec", tr("คำนวณจากปริมาตรถัง + ปั๊ม"))),
          default="pct"),
        N("fill_rate", tr("อัตราเติม (ปั๊ม)"), 1, 100, 1, unit=" %/s"),
        N("drain_rate", tr("อัตราปล่อย"), 1, 100, 1, unit=" %/s"),
        N("volume_l", tr("ความจุถัง"), 1, 10000, 10, unit=" L", default=200, group="spec"),
        N("pump_lpm", tr("อัตราปั๊ม"), 1, 1000, 1, unit=" L/min", default=20, group="spec"),
        N("drain_lpm", tr("อัตราวาล์วปล่อย"), 1, 1000, 1, unit=" L/min", default=15, group="spec"),
        N("high_pct", tr("ตำแหน่งเซนเซอร์สูง"), 5, 100, 5, unit=" %"),
        N("low_pct", tr("ตำแหน่งเซนเซอร์ต่ำ"), 0, 95, 5, unit=" %"),
        N("level0", tr("ระดับน้ำเริ่มต้น"), 0, 100, 5, unit=" %"),
    ),
    # ---------------- R3 ----------------
    "selector3": (
        T("pos_names", tr("ชื่อตำแหน่ง ซ้าย;กลาง;ขวา")),
        C("keyed", tr("ชนิด"), (("knob", tr("ด้ามบิด")), ("key", tr("สวิตช์กุญแจ (ถอดกุญแจได้เฉพาะตำแหน่งกลาง)"))),
          group="spec", help=tr("สวิตช์กุญแจใช้ล็อกโหมด เช่น ให้เฉพาะช่างเปลี่ยนเป็น MAN ได้")),
    ),
    "timer_relay": (
        C("mode", tr("โหมด"), (("on", tr("ON-delay — คอยล์ ON ครบเวลาแล้วหน้าสัมผัสต่อ")),
                          ("off", tr("OFF-delay — คอยล์ OFF แล้วหน้าสัมผัสค้างอีกตามเวลา")),
                          ("flicker", tr("Flicker — กะพริบ ON/OFF ทุกช่วงเวลา"))), group="spec"),
        N("set_s", tr("เวลาตั้ง"), 0.1, 600, 0.5, 1, " s", group="spec", help=tr("หมุนหน้าปัดบนตัวไทเมอร์")),
    ),
    "float_switch": (
        L("link_tank", tr("ติดตั้งในถัง"), ("tank",)),
        N("level_pct", tr("ระดับที่ทำงาน"), 0, 100, 5, unit=" %", group="spec"),
        C("float_dir", tr("การทำงาน"), (("up", tr("ON เมื่อน้ำถึงระดับ (ลูกลอยยกขึ้น)")),
                                    ("down", tr("ON เมื่อน้ำต่ำกว่าระดับ"))), group="spec"),
    ),
    "compressor": (
        N("lpm", tr("อัตราผลิตลม"), 20, 1000, 10, unit=" L/min", default=200, group="spec",
          help=tr("ปริมาณลมอิสระที่อัดได้ต่อนาที — มาก = ถังเต็มเร็ว")),
        N("tank_l", tr("ความจุถังลม"), 5, 500, 5, unit=" L", default=10, group="spec",
          help=tr("ถังเล็ก = ความดันขึ้นเร็วแต่ตกเร็วเมื่อใช้ลม")),
        N("max_bar", tr("วาล์วนิรภัย (ความดันสูงสุด)"), 4, 12, 0.5, 1, " bar", default=8.0, group="spec"),
        N("bar0", tr("ความดันเริ่มต้น"), 0, 12, 0.5, 1, " bar", default=0.0),
        N("leak_bar_min", tr("ลมรั่วตามธรรมชาติ"), 0, 5, 0.1, 1, tr(" bar/นาที"), default=0.3),
    ),
    "pressure_switch": (
        L("link_air", tr("ต่อกับถังลม"), ("compressor",)),
        N("set_bar", tr("ค่าตั้ง (ON ที่)"), 0.5, 12, 0.5, 1, " bar", group="spec"),
        N("diff_bar", tr("ค่า Diff (OFF ที่ ค่าตั้ง − Diff)"), 0.1, 5, 0.1, 1, " bar", group="spec",
          help=tr("Hysteresis: ป้องกันสัญญาณสั่นเปิด-ปิดถี่ ๆ เมื่อความดันแกว่งรอบค่าตั้ง")),
    ),
    "level_tx": (
        L("link_tank", tr("ติดตั้งบนถัง"), ("tank",)),
        N("raw_max", tr("ค่า A/D เต็มสเกล"), 100, 32000, 100, default=4000, group="spec",
          help=tr("20 mA = ค่านี้ · 4 mA = 0")),
        N("min_pct", tr("ระดับที่ 4 mA"), 0, 90, 5, unit=" %", default=0, group="spec"),
        N("max_pct", tr("ระดับที่ 20 mA"), 10, 100, 5, unit=" %", default=100, group="spec"),
    ),
    "load_cell": (
        N("cap_g", tr("พิกัดตาชั่ง"), 100, 30000, 100, unit=" g", default=5000, group="spec"),
        N("fill_gps", tr("อัตราเติม"), 1, 2000, 10, unit=" g/s", default=200),
        N("noise_g", tr("สัญญาณรบกวน ±"), 0, 50, 1, unit=" g", default=2,
          help=tr("ค่าจริงแกว่งเล็กน้อยเสมอ → อย่าใช้ = เทียบค่า ให้ใช้ >= แทน")),
    ),
    "servo": (
        N("stroke_mm", tr("ระยะเคลื่อนที่"), 50, 2000, 10, unit=" mm", default=500, group="spec"),
        N("vmax", tr("ความเร็วสูงสุด"), 10, 2000, 10, unit=" mm/s", default=250, group="spec"),
        N("acc", tr("อัตราเร่ง"), 50, 10000, 50, unit=" mm/s²", default=500, group="spec"),
        N("inpos_mm", tr("ช่วงถึงตำแหน่ง (In-position)"), 0.1, 20, 0.1, 1, " mm", default=1.0, group="spec"),
    ),
    "safety_door": (
        C("lock", tr("ชนิด"), (("plain", tr("สวิตช์ลิ้นแยก (ไม่ล็อก)")), ("lock", tr("ล็อกด้วยโซลินอยด์"))), group="spec"),
    ),
    "light_curtain": (
        N("beams", tr("จำนวนลำแสง"), 4, 32, 1, default=8, group="spec"),
        N("height", tr("ความสูงเขตป้องกัน"), 60, 400, 10, unit=" mm", default=140, group="spec"),
        N("response_ms", tr("เวลาตอบสนอง"), 0, 100, 1, unit=" ms", default=15, group="spec",
          help=tr("ใช้คำนวณระยะติดตั้งปลอดภัย: S = K × (t_ม่าน + t_เครื่อง) + C")),
    ),
    "pick_place": (
        C("feed", tr("ต้นทางชิ้นงาน"), (("stack", tr("ถาดป้อนในตัว (มีชิ้นงานเสมอ)")),
                                   ("conveyor", tr("ปลายสายพาน (วางแขนให้ตรงชิ้นงาน)"))), group="general"),
        N("x_s", tr("เวลาแกน X"), 0.2, 5, 0.1, 1, " s", default=1.0),
        N("z_s", tr("เวลาแกน Z"), 0.1, 5, 0.1, 1, " s", default=0.5),
        N("grip_ms", tr("เวลาหัวจับหนีบ"), 0, 1000, 50, unit=" ms", default=200,
          help=tr("ต้องรอหัวจับหนีบให้แน่นก่อนยกขึ้น ไม่งั้นชิ้นงานไม่ติดมา")),
    ),
    "barcode": (
        N("read_ms", tr("เวลาอ่าน"), 0, 1000, 10, unit=" ms", default=100, group="spec"),
        N("range_mm", tr("ระยะอ่าน"), 30, 400, 10, unit=" mm", default=120, group="spec"),
    ),
    # ---------------- R5: Stepper ----------------
    "stepper": (
        C("step_deg", tr("มุมต่อสเต็ป"), (("1.8", tr("1.8° (200 สเต็ป/รอบ)")), ("0.9", tr("0.9° (400 สเต็ป/รอบ)"))), group="spec"),
        C("microstep", tr("ไมโครสเต็ป (ตั้งที่ไดรฟ์)"), (("1", "Full step"), ("2", "1/2"), ("4", "1/4"), ("8", "1/8"),
                                                     ("16", "1/16")), default="16", group="spec",
          help=tr("แบ่งสเต็ปให้ละเอียดขึ้น หมุนเรียบขึ้น แต่ต้องส่งพัลส์มากขึ้น · 1.8° + 1/16 = 3200 พัลส์/รอบ")),
        N("lead_mm", tr("ระยะต่อรอบ (Lead บอลสกรู)"), 1, 40, 1, unit=" mm", default=10, group="spec"),
        N("stroke_mm", tr("ระยะเคลื่อนที่"), 10, 400, 10, unit=" mm", default=100, group="spec",
          help=tr("ระวัง: D เก็บได้ถึง 32767 — ตำแหน่งพัลส์สูงสุด = ระยะ × พัลส์ต่อ mm")),
        N("pps_max", tr("ความเร็วสูงสุด"), 100, 50000, 100, unit=tr(" พัลส์/s"), default=16000,
          help=tr("ความเร็วรอบ = พัลส์/s ÷ พัลส์ต่อรอบ · ยิ่งเร็วแรงบิดยิ่งตก")),
        N("accel_pps2", tr("ความเร่ง"), 1000, 400000, 1000, unit=tr(" พัลส์/s²"), default=32000,
          help=tr("เร่งแรงไปต้องใช้แรงบิดมาก → หลุดสเต็ปตอนออกตัว/หยุด")),
        N("jog_pps", tr("ความเร็ว Jog"), 100, 20000, 100, unit=tr(" พัลส์/s"), default=3200),
        N("load_pct", tr("โหลด (เทียบแรงบิดพิกัด)"), 0, 150, 5, unit=" %", default=50,
          help=tr("เกิน 100% = แรงบิดไม่พอแม้ความเร็วต่ำ → หลุดสเต็ปทันที")),
    ),
    # ---------------- R5: มอเตอร์ DC / BLDC ----------------
    "dc_motor": (
        C("drive", tr("ชนิด"), (("brushed", tr("DC แปรงถ่าน + รีเลย์กลับขั้ว/PWM")),
                            ("bldc", tr("BLDC + ไดรฟ์ (EN / DIR / ความเร็ว)"))), group="spec",
          help=tr("แปรงถ่าน: ถูก ควบคุมง่าย แต่แปรงสึก · BLDC: ไม่มีแปรง ทนกว่า ต้องมีไดรฟ์อ่าน Hall sensor")),
        C("volt", tr("แรงดัน"), (("24", "24 VDC"), ("12", "12 VDC"), ("48", "48 VDC")), group="spec"),
        N("rpm_max", tr("รอบสูงสุด"), 100, 10000, 100, unit=" rpm", default=3000, group="spec"),
        N("max_word", tr("ค่าสั่งเต็มสเกล"), 100, 32000, 100, default=4000, group="spec",
          help=tr("ค่าใน D ที่ได้รอบสูงสุด (PWM 100% / analog 10 V)")),
        N("accel_s", tr("เวลาเร่ง 0→สูงสุด"), 0, 10, 0.1, 1, " s", default=0.5, special=tr("ทันที"),
          help=tr("BLDC: ไดรฟ์ตั้ง ramp ได้ · แปรงถ่าน: ตามความเฉื่อยของโหลด")),
        N("decel_s", tr("เวลาลด สูงสุด→0"), 0, 10, 0.1, 1, " s", default=0.5, special=tr("ทันที")),
    ),
    # ---------------- R5: สุญญากาศ ----------------
    "vacuum": (
        N("set_kpa", tr("ค่าตั้งสวิตช์สุญญากาศ"), 10, 90, 5, unit=" kPa", default=60, group="spec",
          help=tr("OK เมื่อสุญญากาศถึง −ค่านี้ · ถ้วยปิดผนึกดีได้ราว −80 kPa, ไม่มีชิ้นงานได้แค่ −10")),
        N("diff_kpa", "Hysteresis", 1, 20, 1, unit=" kPa", default=5, group="spec"),
        N("hold_kpa", tr("สุญญากาศต่ำสุดที่จับชิ้นงานอยู่"), 10, 80, 5, unit=" kPa", default=40, group="spec",
          help=tr("ต่ำกว่านี้ชิ้นงานหลุด (ขึ้นกับน้ำหนักชิ้นงานและขนาดถ้วย)")),
        N("lift_s", tr("เวลายกถ้วยขึ้นสุด"), 0.1, 5, 0.1, 1, " s", default=0.5),
    ),
    # ---------------- R5: รีเลย์ ----------------
    "relay": (
        C("coil", tr("แรงดันคอยล์"), (("24vdc", "24 VDC"), ("220vac", "220 VAC")), group="spec",
          help=tr("คอยล์ 24 VDC สั่งจากเอาต์พุตทรานซิสเตอร์ได้ (ต้องมีไดโอดกันไฟย้อน)")),
        N("pickup_ms", tr("เวลาดูด"), 0, 100, 1, unit=" ms", default=10, group="spec", special=tr("ทันที"),
          help=tr("รีเลย์จริงใช้เวลา 5–20 ms กว่าหน้าสัมผัสจะเปลี่ยน")),
        N("release_ms", tr("เวลาปล่อย"), 0, 100, 1, unit=" ms", default=5, group="spec", special=tr("ทันที")),
        *(C(f"c{i}", tr("หน้าสัมผัสชุด {0}", i), (("NO", tr("NO — ปกติเปิด (ดูดแล้วต่อ)")), ("NC", tr("NC — ปกติปิด (ดูดแล้วตัด)"))),
            default="NO" if i <= 2 else "NC", group="spec") for i in range(1, 5)),
    ),
    "latch_relay": (
        C("mode", tr("โหมด"), (("impulse", tr("Impulse — พัลส์เดียวสลับ ON/OFF")),
                          ("set_reset", tr("SET/RESET — คอยล์แยก 2 ตัว (RESET ชนะ)"))), group="spec",
          help=tr("Impulse ใช้กับปุ่มกดหลายจุดคุมไฟดวงเดียว (ไฟบันได/ทางเดิน)\n"
               "ห้ามจ่ายไฟคอยล์ค้าง — สั่งเป็นพัลส์ 0.1–1 s")),
        *(C(f"c{i}", tr("หน้าสัมผัสชุด {0}", i), (("NO", tr("NO — ON แล้วต่อ")), ("NC", tr("NC — ON แล้วตัด"))),
            default="NO", group="spec") for i in (1, 2)),
    ),
    "ssr": (
        C("load", tr("โหลดที่ต่อ"), (("heater", tr("ฮีตเตอร์")), ("lamp", tr("หลอดไฟ LED ขนาดเล็ก"))), group="general"),
        N("load_a", tr("กระแสโหลด"), 0.1, 40, 0.5, 1, " A", default=5.0, group="spec",
          help=tr("SSR ร้อนขึ้นตามกระแส (แรงดันตกคร่อม ~1.2 V × กระแส = ความร้อน)")),
        C("heatsink", tr("ฮีตซิงก์"), (("yes", tr("ติดฮีตซิงก์")), ("no", tr("ไม่มีฮีตซิงก์"))), group="spec",
          help=tr("กระแสเกิน ~5 A ต้องติดฮีตซิงก์ ไม่งั้นร้อนเกินจนพัง (พังแบบช็อต = โหลดติดค้าง!)")),
        C("zero_cross", "Zero-cross", (("yes", tr("มี — ต่อ/ตัดที่จุดตัดศูนย์ (หน่วง ≤10 ms)")),
                                       ("no", tr("ไม่มี (Random turn-on) — ตอบสนองทันที"))), group="spec",
          help=tr("Zero-cross ลดสัญญาณรบกวน เหมาะกับฮีตเตอร์ · Random เหมาะกับหลอด/คุมมุมเฟส")),
        N("leak_ma", tr("กระแสรั่วตอน OFF"), 0, 20, 1, unit=" mA", default=5, group="spec",
          help=tr("SSR ไม่ได้ตัดขาดจริง ตอน OFF ยังรั่วไม่กี่ mA → หลอด LED เล็ก ๆ อาจติดหรี่")),
        N("ambient", tr("อุณหภูมิในตู้"), 0, 60, 1, unit=" °C", default=30),
    ),
    "phase_relay": (
        N("trip_s", tr("เวลาหน่วงทริป"), 0.1, 10, 0.1, 1, " s", default=1.0, group="spec",
          help=tr("กันทริปเพราะไฟกระพริบสั้น ๆ · สลับเฟสทริปทันที (~0.1 s)")),
        N("reset_s", tr("เวลากลับคืนเมื่อไฟปกติ"), 0, 10, 0.5, 1, " s", default=1.0, group="spec", special=tr("ทันที")),
    ),
    "safety_relay": (
        L("link_estop", tr("อุปกรณ์สั่งหยุดนิรภัย"), ("estop", "safety_door", "light_curtain"),
          help=tr("ผูก E-Stop / สวิตช์ประตู / ม่านแสง (ไม่ผูก = คลิกครึ่งบนของตัวรีเลย์เพื่อจำลอง)")),
        C("reset_mode", tr("การรีเซ็ต"), (("monitored", tr("Monitored — รีเซ็ตเมื่อปล่อยปุ่ม (ขอบขาลง)")),
                                      ("auto", tr("Auto — เดินเองเมื่อวงจรปิด (ใช้กับประตูเท่านั้น)"))), group="spec",
          help=tr("Monitored: ปุ่มรีเซ็ตค้าง/ช็อตจะไม่ทำให้เครื่องเดินเอง · Auto อันตรายถ้าใช้กับ E-Stop")),
    ),
    "sevenseg": (N("digits", tr("จำนวนหลัก"), 1, 6, 1, group="general"),),
    "setvalue": (N("min", tr("ค่าต่ำสุด"), -32768, 32767, 1, group="general"),
                 N("max", tr("ค่าสูงสุด"), -32768, 32767, 1, group="general")),
    "pot": (N("max", tr("ค่าสูงสุด (เต็มสเกล)"), 1, 32767, 100, group="spec",
              help=tr("A/D ของ PLC ทั่วไป: 0–10 V → 0–4000")),),
    "oven": (
        N("heat_c", tr("อุณหภูมิสูงสุดของฮีตเตอร์"), 30, 1000, 10, unit=" °C", group="spec"),
        N("ambient", tr("อุณหภูมิห้อง"), -20, 60, 1, unit=" °C"),
        N("tau_s", tr("ความเร็วการเปลี่ยน (τ)"), 1, 600, 1, unit=" s",
          help=tr("ค่าคงที่เวลา: ใช้ราว 3τ กว่าจะร้อนเกือบเต็มที่")),
        N("thermo_c", tr("จุดตัดเทอร์โมสตัท"), 0, 1000, 5, unit=" °C", group="spec"),
    ),
    "gauge": (
        C("style", tr("รูปแบบ"), (("needle", tr("เข็ม")), ("bar", tr("แท่ง (Bar graph)"))), group="general"),
        N("min", tr("ค่าต่ำสุด"), -32768, 32767, 10, group="general"),
        N("max", tr("ค่าสูงสุด"), -32768, 32767, 10, group="general"),
        T("unit", tr("หน่วย")),
    ),
    "display": (T("unit", tr("หน่วย")),),
    "message": (T("messages", tr("ข้อความ"), help=tr("รูปแบบ: ค่า=ข้อความ คั่นด้วย ; เช่น 0=พร้อม;1=ทำงาน")),),
    "note": (T("text", tr("ข้อความ"), multiline=True),
             N("size", tr("ขนาดตัวอักษร"), 6, 40, 1, unit=" pt", group="general"),
             N("width", tr("ความกว้าง"), 60, 1200, 20, unit=" px", group="general")),
    "zone": (N("w", tr("กว้าง"), 40, 3000, 20, unit=" px", group="general"),
             N("h", tr("สูง"), 40, 3000, 20, unit=" px", group="general")),
}
