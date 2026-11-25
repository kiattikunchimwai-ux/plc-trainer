"""รายการชนิดอุปกรณ์ที่วางบนผังได้."""
from __future__ import annotations

from ..i18n import tr

from dataclasses import dataclass, field

CATEGORIES = [
    ("input", tr("Input — ปุ่ม/สวิตช์")),
    ("output", tr("Output — ไฟ/ออด/วาล์ว")),
    ("sensor", tr("Sensor / สายพาน")),
    ("motor", tr("มอเตอร์ / ขับเคลื่อน")),
    ("relay", tr("รีเลย์ / ไทเมอร์")),
    ("process", tr("นิวแมติก / กระบวนการ")),
    ("analog", tr("Analog / อุณหภูมิ")),
    ("safety", tr("ความปลอดภัย")),
    ("robot", tr("เซอร์โว / หุ่นยนต์")),
    ("display", tr("แสดงค่า / ตั้งค่า")),
    ("annotation", tr("ข้อความ / กรอบ")),
]

LAMP_COLORS = {"green": "#5EE36A", "red": "#FF5A5A", "orange": "#FFA94D",
               "yellow": "#F2D648", "blue": "#4FA3FF", "white": "#F1F3F5"}

# ทิศทางของ address:
#   "in"     = PLC อ่านจากอุปกรณ์ (โปรแกรมเขียนบิตลง PLC)
#   "out"    = อุปกรณ์ทำงานตามบิตจาก PLC
#   "word"   = แสดงค่าตัวเลขจาก PLC
#   "wordin" = ผู้ใช้ตั้งค่าตัวเลข แล้วโปรแกรมเขียนลง PLC
#   "none"   = ไม่มี address หลัก (ข้อความ/กรอบ) — มีเฉพาะ extra_io ถ้ามี
IN_KINDS = ("in", "wordin")


@dataclass(frozen=True)
class IOSlot:
    """address เสริมของอุปกรณ์ (นอกจาก 'address' หลัก)."""
    prop: str
    io: str
    label: str
    prefixes: tuple[str, ...]
    optional: bool = False     # เว้นว่างได้


@dataclass(frozen=True)
class KindInfo:
    kind: str
    name: str                 # ชื่อไทยที่แสดงใน Tool Palette
    category: str
    io: str                   # ทิศทางของ address หลัก
    prefixes: tuple[str, ...]
    momentary: bool = False   # True = ON เฉพาะตอนกดค้าง
    defaults: dict = field(default_factory=dict)
    main_label: str = "Address"
    extra_io: tuple[IOSlot, ...] = ()
    desc: str = ""            # ใช้ทำอะไรในงานจริง (tooltip สอนนักเรียน)
    aliases: str = ""         # คำค้นเพิ่มเติม (อังกฤษ/ชื่อเรียกอื่น)
    specs: tuple = ()         # SpecField — สเปก/ค่าการจำลอง (เติมจาก specs.SPECS)

    def default_of(self, f) -> object:
        """ค่าเริ่มต้นของ SpecField: ตาม field ก่อน แล้วค่อยดูใน defaults."""
        if f.default is not None:
            return f.default
        return self.defaults.get(f.prop, f.lo if f.type == "num" else "")

    def spec_field(self, prop: str):
        return next((f for f in self.specs if f.prop == prop), None)

    def slots(self) -> list[IOSlot]:
        """address ทั้งหมด (หลัก + เสริม)."""
        if self.io == "none":
            return list(self.extra_io)
        return [IOSlot("address", self.io, self.main_label, self.prefixes)] + list(self.extra_io)

    def slot(self, prop: str) -> IOSlot:
        return next(s for s in self.slots() if s.prop == prop)


XM, YM = ("X", "M"), ("Y", "M")
WORDS = ("TN", "CN", "D")

_K = [
    # ---------- Input ----------
    KindInfo("pushbutton", tr("ปุ่มกด (Push button)"), "input", "in", XM, True,
             {"label": "Start", "address": "X0", "contact": "NO", "color": "green"},
             desc=tr("ปุ่มกดแบบกดติด-ปล่อยดับ ใช้สั่ง Start/Stop/Reset · ปุ่ม Stop มักต่อแบบ NC เพื่อความปลอดภัย"),
             aliases="push button pb start stop"),
    KindInfo("selector", tr("สวิตช์เลือก (Selector)"), "input", "in", XM, False,
             {"label": "Auto/Man", "address": "X4", "contact": "NO"},
             desc=tr("สวิตช์บิดค้างตำแหน่ง ใช้เลือกโหมด Auto/Manual หรือ On/Off"), aliases="selector switch auto manual"),
    KindInfo("estop", tr("หยุดฉุกเฉิน (E-Stop)"), "input", "in", XM, False,
             {"label": "E-Stop", "address": "X5", "contact": "NC"},
             desc=tr("ปุ่มหัวเห็ดสีแดง กดแล้วล็อกค้าง ต้องต่อแบบ NC เสมอ (สายขาด = หยุดเครื่อง)"),
             aliases="emergency stop estop"),
    KindInfo("limit", tr("ลิมิตสวิตช์ (Limit)"), "input", "in", XM, True,
             {"label": "LS1", "address": "X6", "contact": "NO"},
             desc=tr("สวิตช์ก้านโยก ตรวจว่าชิ้นส่วนเครื่องจักรเคลื่อนมาถึงตำแหน่งปลายทาง"), aliases="limit switch ls"),
    KindInfo("overload", tr("โอเวอร์โหลด (Overload relay)"), "input", "in", XM, False,
             {"label": "OL1", "address": "X7", "contact": "NC", "addr_motor": "", "trip_s": 0},
             main_label=tr("หน้าสัมผัส OL"),
             extra_io=(IOSlot("addr_motor", "out", tr("มอเตอร์ที่เฝ้า"), YM, optional=True),),
             desc=tr("รีเลย์ป้องกันมอเตอร์กินกระแสเกิน ทริปแล้วหน้าสัมผัส NC เปิด → PLC ต้องหยุดมอเตอร์"),
             aliases="overload relay ol thermal"),
    # ---------- Output ----------
    KindInfo("lamp", tr("หลอดไฟ (Pilot lamp)"), "output", "out", YM,
             defaults={"label": "L1", "address": "Y0", "color": "green"},
             desc=tr("ไฟแสดงสถานะบนตู้ควบคุม · เขียว = ทำงาน, แดง = หยุด/ขัดข้อง, ส้ม = เตือน"), aliases="pilot lamp light"),
    KindInfo("buzzer", tr("ออด (Buzzer)"), "output", "out", YM,
             defaults={"label": "BZ", "address": "Y3"},
             desc=tr("ส่งเสียงเตือน เช่น เครื่องขัดข้อง หรือก่อนเครื่องเริ่มเดิน"), aliases="buzzer alarm horn"),
    KindInfo("valve", tr("โซลินอยด์วาล์ว (Valve)"), "output", "out", YM,
             defaults={"label": "SOL1", "address": "Y4"},
             desc=tr("วาล์วไฟฟ้าเปิด/ปิดทางน้ำหรือลม เมื่อคอยล์ได้ไฟ"), aliases="solenoid valve sol"),
    KindInfo("traffic", tr("ไฟจราจร (Traffic light)"), "output", "out", YM,
             defaults={"label": tr("ไฟจราจร"), "address": "Y0", "addr_yellow": "Y1", "addr_green": "Y2"},
             main_label=tr("ไฟแดง"),
             extra_io=(IOSlot("addr_yellow", "out", tr("ไฟเหลือง"), YM), IOSlot("addr_green", "out", tr("ไฟเขียว"), YM)),
             desc=tr("ไฟจราจร 3 ดวง ใช้ฝึกโปรแกรมแบบลำดับเวลา (Timer)"), aliases="traffic light"),
    KindInfo("tower", tr("ไฟทาวเวอร์ (Tower light)"), "output", "out", YM,
             defaults={"label": "Tower", "address": "Y0", "addr_yellow": "Y1", "addr_green": "Y2", "addr_buzzer": ""},
             main_label=tr("ไฟแดง"),
             extra_io=(IOSlot("addr_yellow", "out", tr("ไฟเหลือง"), YM), IOSlot("addr_green", "out", tr("ไฟเขียว"), YM),
                       IOSlot("addr_buzzer", "out", tr("ออดบนยอด"), YM, optional=True)),
             desc=tr("ไฟสัญญาณบนเครื่องจักร (มาตรฐาน IEC 60204): แดง = ขัดข้อง, เหลือง = เตือน/รอ, เขียว = ทำงานปกติ"),
             aliases="tower light stack light signal"),
    # ---------- Sensor / สายพาน ----------
    KindInfo("sensor", tr("เซนเซอร์ (Photo/Proximity)"), "sensor", "in", XM, False,
             {"label": "PS1", "address": "X2", "contact": "NO", "sense": "photo"},
             desc=tr("Photoelectric = ลำแสงยาว เห็นทุกชิ้นงาน · Inductive = ระยะสั้น เห็นเฉพาะโลหะ · "
                  "Capacitive = ระยะสั้น เห็นทุกวัสดุ (ตั้งชนิดได้ที่ Properties)"),
             aliases="sensor photo proximity inductive capacitive prox"),
    KindInfo("encoder", tr("เอนโค้ดเดอร์ (Encoder)"), "sensor", "in", XM, False,
             {"label": "ENC", "address": "X3", "contact": "NO", "addr_motor": "Y0", "pulse_hz": 4},
             main_label=tr("สัญญาณพัลส์"),
             extra_io=(IOSlot("addr_motor", "out", tr("มอเตอร์ที่ติดตั้ง"), YM, optional=True),),
             desc=tr("จานหมุนมีร่อง ส่งพัลส์ตามการหมุนของมอเตอร์ ใช้นับรอบ/วัดระยะด้วย Counter"),
             aliases="rotary encoder pulse"),
    KindInfo("conveyor", tr("สายพาน (Conveyor)"), "sensor", "out", YM,
             defaults={"label": tr("สายพาน"), "address": "Y0", "length": 440, "speed": 120, "part_mode": "random",
                       "addr_hz": ""},
             extra_io=(IOSlot("addr_hz", "word", tr("ความเร็วจาก VFD (Hz×10)"), ("D",), optional=True),),
             desc=tr("สายพานลำเลียงชิ้นงาน · คลิก '+ ชิ้นงาน' เพื่อปล่อยชิ้นงาน (โลหะ = สีเงิน, พลาสติก = สีน้ำตาล)"),
             aliases="conveyor belt"),
    # ---------- มอเตอร์ / ขับเคลื่อน ----------
    KindInfo("motor", tr("มอเตอร์ (Motor)"), "motor", "out", YM,
             defaults={"label": "M1", "address": "Y0"},
             desc=tr("มอเตอร์ไฟฟ้า หมุนเมื่อ PLC สั่ง (งานจริงสั่งผ่านคอนแทคเตอร์)"), aliases="motor"),
    KindInfo("motor_rev", tr("มอเตอร์กลับทางหมุน (FWD/REV)"), "motor", "out", YM,
             defaults={"label": "M1", "address": "Y0", "addr_rev": "Y1"},
             main_label=tr("หมุนหน้า (FWD)"),
             extra_io=(IOSlot("addr_rev", "out", tr("หมุนกลับ (REV)"), YM),),
             desc=tr("มอเตอร์ 3 เฟสกลับทางหมุนด้วยคอนแทคเตอร์ 2 ตัว · ห้ามสั่ง FWD และ REV พร้อมกัน "
                  "(ต้องทำ Interlock ไม่งั้นลัดวงจร!)"),
             aliases="reversing motor forward reverse interlock"),
    KindInfo("motor_yd", tr("มอเตอร์สตาร์-เดลต้า (Y-Δ)"), "motor", "out", YM,
             defaults={"label": "M1", "address": "Y0", "addr_star": "Y1", "addr_delta": "Y2", "addr_ol": ""},
             main_label="KM1 Main",
             extra_io=(IOSlot("addr_star", "out", tr("KM2 สตาร์ (Y)"), YM),
                       IOSlot("addr_delta", "out", tr("KM3 เดลต้า (Δ)"), YM),
                       IOSlot("addr_ol", "in", "OL 95-96 (NC)", XM, optional=True)),
             desc=tr("สตาร์ทมอเตอร์ใหญ่แบบลดกระแส: Main + Star ก่อน (กระแส ~2× แทน 6×) รอรอบขึ้นแล้วสลับเป็น "
                  "Main + Delta · ห้าม Star กับ Delta พร้อมกัน (ลัดวงจร!) · สลับเร็วไป = กระแสกระชาก · "
                  "มี OL ในตัว (คลิก = รีเซ็ต OL)"),
             aliases="star delta wye delta y-d yd starter motor reduced voltage start km1 km2 km3"),
    KindInfo("contactor", tr("คอนแทคเตอร์ (Contactor)"), "relay", "out", YM,
             defaults={"label": "K1", "address": "Y0", "addr_aux": ""},
             main_label=tr("คอยล์"),
             extra_io=(IOSlot("addr_aux", "in", tr("หน้าสัมผัสช่วย (NO)"), XM, optional=True),),
             desc=tr("สวิตช์แม่เหล็กตัดต่อไฟกำลังให้มอเตอร์ PLC สั่งที่คอยล์ A1-A2"), aliases="contactor magnetic"),
    KindInfo("vfd", tr("อินเวอร์เตอร์ (VFD)"), "motor", "out", YM,
             defaults={"label": "INV1", "address": "Y0", "addr_rev": "", "addr_freq": "D0", "addr_atspeed": "",
                       "ramp_s": 3.0, "max_hz": 60},
             main_label=tr("สั่งเดิน (RUN/STF)"),
             extra_io=(IOSlot("addr_rev", "out", tr("หมุนกลับ (STR)"), YM, optional=True),
                       IOSlot("addr_freq", "word", tr("ความถี่สั่ง (Hz×10)"), ("D",)),
                       IOSlot("addr_atspeed", "in", tr("ถึงความเร็ว (SU)"), XM, optional=True)),
             desc=tr("ปรับความเร็วมอเตอร์ด้วยการเปลี่ยนความถี่ · PLC สั่งเดินด้วยบิต และตั้งความถี่ด้วยค่า D "
                  "(เช่น D0 = 500 → 50.0 Hz) · มีเวลาเร่ง (ramp)"),
             aliases="vfd inverter drive frequency speed"),
    KindInfo("axis", tr("แกนเลื่อน / ลิฟต์ / ประตู"), "motor", "out", YM,
             defaults={"label": tr("แกน 1"), "address": "Y0", "addr_rev": "Y1", "addr_p1": "X0", "addr_p2": "",
                       "addr_p3": "X1", "addr_pos": "", "style": "slide", "travel_s": 4.0},
             main_label=tr("เคลื่อนไปปลาย/ขึ้น/เปิด"),
             extra_io=(IOSlot("addr_rev", "out", tr("เคลื่อนกลับ/ลง/ปิด"), YM),
                       IOSlot("addr_p1", "in", tr("เซนเซอร์ต้นทาง (ล่าง/ปิด)"), XM),
                       IOSlot("addr_p2", "in", tr("เซนเซอร์กลาง"), XM, optional=True),
                       IOSlot("addr_p3", "in", tr("เซนเซอร์ปลายทาง (บน/เปิด)"), XM),
                       IOSlot("addr_pos", "wordin", tr("ตำแหน่ง 0–1000 → D"), ("D",), optional=True)),
             desc=tr("ชุดขับเคลื่อนด้วยมอเตอร์ 2 ทิศทาง พร้อมเซนเซอร์ตำแหน่ง · เลือกรูปแบบเป็นแกนสไลด์ ลิฟต์ "
                  "หรือประตูม้วนได้ที่ Properties"),
             aliases="axis slide elevator lift door garage servo stepper"),
    # ---------- นิวแมติก / กระบวนการ ----------
    KindInfo("cylinder", tr("กระบอกสูบ + วาล์ว 5/2 · 5/3"), "process", "out", YM,
             defaults={"label": "Cyl A", "address": "Y5", "addr_sol_b": "", "addr_ret": "X10", "addr_ext": "X11",
                       "valve": "single", "stroke_s": 1.0},
             main_label=tr("โซลินอยด์ยื่น (A+)"),
             extra_io=(IOSlot("addr_sol_b", "out", tr("โซลินอยด์หด (A−)"), YM, optional=True),
                       IOSlot("addr_ret", "in", tr("รีดสวิตช์หด (a0)"), XM),
                       IOSlot("addr_ext", "in", tr("รีดสวิตช์ยื่น (a1)"), XM)),
             desc=tr("กระบอกสูบลม ควบคุมด้วยวาล์ว 5/2 หรือ 5/3 (หยุดกลางทางได้) หรือแบบทางเดียวสปริงคืน "
                  "มีรีดสวิตช์บอกตำแหน่งหดสุด (a0) / ยื่นสุด (a1) · เลือกชนิดที่ Properties"),
             aliases="pneumatic cylinder 5/2 5/3 3/2 valve reed closed exhaust pressure center single acting spring"),
    KindInfo("pusher", tr("กระบอกดันคัดแยก (Pusher)"), "process", "out", YM,
             defaults={"label": tr("ตัวดัน"), "address": "Y5", "addr_sol_b": "", "addr_ret": "X10", "addr_ext": "X11",
                       "valve": "single", "stroke_s": 0.4},
             main_label=tr("โซลินอยด์ดัน"),
             extra_io=(IOSlot("addr_sol_b", "out", tr("โซลินอยด์ดึงกลับ"), YM, optional=True),
                       IOSlot("addr_ret", "in", tr("รีดสวิตช์หด (a0)"), XM),
                       IOSlot("addr_ext", "in", tr("รีดสวิตช์ยื่น (a1)"), XM)),
             desc=tr("วางเหนือสายพาน เมื่อยื่นจะดันชิ้นงานที่อยู่ใต้ลงถาดคัดแยก (ใช้คัดของเสีย/แยกวัสดุ)"),
             aliases="pusher sorting diverter reject"),
    KindInfo("tank", tr("ถังน้ำ + ปั๊ม"), "process", "out", YM,
             defaults={"label": tr("ถังน้ำ"), "address": "Y6", "addr_drain": "Y7", "addr_high": "X12", "addr_low": "X13",
                       "fill_rate": 12, "drain_rate": 8, "level0": 30, "high_pct": 80, "low_pct": 20},
             main_label=tr("ปั๊มน้ำเข้า"),
             extra_io=(IOSlot("addr_drain", "out", tr("วาล์วปล่อยน้ำ"), YM, optional=True),
                       IOSlot("addr_high", "in", tr("เซนเซอร์ระดับสูง"), XM),
                       IOSlot("addr_low", "in", tr("เซนเซอร์ระดับต่ำ"), XM)),
             desc=tr("ถังน้ำพร้อมปั๊ม วาล์วปล่อย และเซนเซอร์ระดับ (Float/Level switch) · คลิกถัง = เปิดก๊อกใช้น้ำ"),
             aliases="tank pump level float"),
    # ---------- Analog ----------
    KindInfo("pot", tr("ปุ่มปรับค่า Analog (Potentiometer)"), "analog", "wordin", ("D",),
             defaults={"label": tr("ปรับความเร็ว"), "address": "D20", "value": 0, "max": 4000},
             desc=tr("จำลองอินพุต Analog 0–10V ที่ผ่าน A/D แล้วได้ค่า 0–4000 ลง D · ลากปุ่มหมุนเพื่อปรับ"),
             aliases="potentiometer analog input knob adc 0-10v 4-20ma"),
    KindInfo("oven", tr("เตาอบ + เทอร์โมคัปเปิล"), "analog", "out", YM,
             defaults={"label": tr("เตาอบ"), "address": "Y0", "addr_temp": "D30", "addr_thermo": "", "ambient": 25,
                       "heat_c": 250, "tau_s": 20, "thermo_c": 100},
             main_label=tr("ฮีตเตอร์"),
             extra_io=(IOSlot("addr_temp", "wordin", tr("อุณหภูมิ °C → D"), ("D",)),
                       IOSlot("addr_thermo", "in", tr("เทอร์โมสตัท (≥ ค่าตั้ง)"), XM, optional=True)),
             desc=tr("ฮีตเตอร์ให้ความร้อน และเทอร์โมคัปเปิลส่งค่าอุณหภูมิ (°C) เข้า D · อุณหภูมิเปลี่ยนช้าแบบจริง "
                  "ใช้ฝึกควบคุมแบบ On/Off (ใช้คำสั่งเปรียบเทียบ)"),
             aliases="oven heater temperature thermocouple analog"),
    KindInfo("gauge", tr("มาตรวัด / Bar graph"), "analog", "word", WORDS,
             defaults={"label": tr("มาตรวัด"), "address": "D30", "style": "needle", "min": 0, "max": 300, "unit": "°C"},
             desc=tr("แสดงค่าตัวเลขเป็นเข็มหรือแท่ง เหมือนมิเตอร์หน้าตู้"), aliases="gauge meter bar graph analog output"),
    # ---------- แสดงค่า / ตั้งค่า ----------
    KindInfo("display", tr("ตัวแสดงค่า (Display)"), "display", "word", WORDS,
             defaults={"label": "Timer T0", "address": "TN0", "unit": "×100ms"},
             desc=tr("แสดงค่าปัจจุบันของ Timer / Counter / D"), aliases="display value"),
    KindInfo("sevenseg", "7-Segment", "display", "word", WORDS,
             defaults={"label": "7-Seg", "address": "D0", "digits": 4},
             desc=tr("ตัวเลข 7 ส่วน แสดงค่าจาก D/T/C เช่น ตัวนับชิ้นงาน นับถอยหลัง"), aliases="seven segment 7seg"),
    KindInfo("message", tr("ป้ายข้อความ (Message)"), "display", "word", ("D",),
             defaults={"label": tr("สถานะ"), "address": "D1", "messages": tr("0=พร้อมทำงาน;1=กำลังทำงาน;2=ขัดข้อง!")},
             desc=tr("แสดงข้อความตามค่าใน D เหมือนจอ HMI (ตั้งข้อความได้ที่ Properties)"),
             aliases="message text hmi display status"),
    KindInfo("setvalue", tr("ตัวตั้งค่า (Thumbwheel)"), "display", "wordin", ("D",),
             defaults={"label": tr("ตั้งค่า"), "address": "D10", "value": 0, "min": 0, "max": 9999},
             desc=tr("ตั้งค่าตัวเลขเขียนลง D เช่น เวลา จำนวนชิ้น"), aliases="thumbwheel set value"),
    # ---------- R3: อุปกรณ์เหมือนของจริงชุดใหม่ ----------
    KindInfo("selector3", tr("สวิตช์ 3 ตำแหน่ง (MAN-OFF-AUTO)"), "input", "in", XM, False,
             {"label": tr("โหมด"), "address": "X4", "addr_right": "X5", "contact": "NO", "pos_names": "MAN;OFF;AUTO"},
             main_label=tr("ตำแหน่งซ้าย"),
             extra_io=(IOSlot("addr_right", "in", tr("ตำแหน่งขวา"), XM),),
             desc=tr("สวิตช์บิด 3 ตำแหน่ง ซ้าย-กลาง-ขวา ใช้ 2 อินพุต (ตำแหน่งกลาง = ทั้งคู่ OFF) · "
                  "คลิกซีกซ้าย/ขวาของปุ่มเพื่อบิด"),
             aliases="selector 3 position man off auto key switch"),
    KindInfo("timer_relay", tr("ไทเมอร์รีเลย์ (Timer relay)"), "relay", "out", YM,
             defaults={"label": "TR1", "address": "Y2", "addr_contact": "X6", "mode": "on", "set_s": 3.0},
             main_label=tr("คอยล์ (A1-A2)"),
             extra_io=(IOSlot("addr_contact", "in", tr("หน้าสัมผัส NO (15-18)"), XM, optional=True),),
             desc=tr("ไทเมอร์ภายนอกแบบติดราง: ON-delay (หน่วงต่อ), OFF-delay (หน่วงปลด), Flicker (กะพริบ) · "
                  "ใช้ในตู้ควบคุมจริงที่ไม่มี PLC — เทียบกับ Timer ใน ladder"),
             aliases="timer relay on delay off delay flicker"),
    KindInfo("float_switch", tr("ลูกลอย (Float switch)"), "process", "in", XM, False,
             {"label": "FS1", "address": "X14", "contact": "NO", "level_pct": 50},
             desc=tr("ลูกลอยตรวจระดับน้ำ ผูกกับถังน้ำได้ ลูกลอยขยับขึ้นลงตามน้ำ · ไม่ผูก = คลิกเพื่อจำลอง"),
             aliases="float switch level"),
    KindInfo("compressor", tr("ปั๊มลม + ถังลม (Compressor)"), "process", "out", YM,
             defaults={"label": tr("ปั๊มลม"), "address": "Y7", "addr_bar": ""},
             main_label=tr("มอเตอร์ปั๊มลม"),
             extra_io=(IOSlot("addr_bar", "wordin", tr("ความดัน (bar×10) → D"), ("D",), optional=True),),
             desc=tr("อัดลมเข้าถังเมื่อมอเตอร์เดิน · กระบอกสูบที่ผูกไว้จะใช้ลมจากถังนี้ (ความดันลดทุกครั้งที่ชัก) · "
                  "มีวาล์วนิรภัยระบายเมื่อความดันเกิน"),
             aliases="air compressor pneumatic pressure tank"),
    KindInfo("pressure_switch", tr("สวิตช์ความดัน (Pressure switch)"), "process", "in", XM, False,
             {"label": "PS-AIR", "address": "X15", "contact": "NO", "set_bar": 6.0, "diff_bar": 1.0},
             desc=tr("ON เมื่อความดันถึงค่าตั้ง และ OFF เมื่อลดลงต่ำกว่า (ค่าตั้ง − ค่า Diff) — มี hysteresis "
                  "ไม่ให้ปั๊มเปิด-ปิดถี่ · ผูกกับปั๊มลม"),
             aliases="pressure switch air hysteresis differential"),
    KindInfo("level_tx", tr("เซนเซอร์ระดับ Ultrasonic (4–20 mA)"), "analog", "wordin", ("D",),
             defaults={"label": "LT1", "address": "D40"},
             desc=tr("วัดระดับน้ำแบบต่อเนื่องด้วยคลื่นเสียง ส่ง 4–20 mA → A/D ได้ 0–4000 ลง D · ผูกกับถังน้ำ"),
             aliases="level transmitter ultrasonic analog 4-20ma"),
    KindInfo("load_cell", tr("ตาชั่ง Load cell"), "analog", "wordin", ("D",),
             defaults={"label": tr("ตาชั่ง"), "address": "D42", "addr_fill": "Y10"},
             main_label=tr("น้ำหนัก (กรัม) → D"),
             extra_io=(IOSlot("addr_fill", "out", tr("วาล์วเติม"), YM, optional=True),),
             desc=tr("ชั่งน้ำหนักในถังพัก ส่งค่ากรัมเข้า D (มีสัญญาณรบกวนเล็กน้อยเหมือนจริง) · วาล์วเปิด = เติม · "
                  "คลิก = เทออก"),
             aliases="load cell weight scale weighing"),
    KindInfo("servo", tr("เซอร์โว + ไดรฟ์ (Servo)"), "robot", "out", YM,
             defaults={"label": "Servo X", "address": "Y11", "addr_target": "D50", "addr_inpos": "X16",
                       "addr_alarm": "", "addr_pos": ""},
             main_label="Servo ON",
             extra_io=(IOSlot("addr_target", "word", tr("ตำแหน่งเป้าหมาย (mm)"), ("D",)),
                       IOSlot("addr_inpos", "in", tr("ถึงตำแหน่ง (INP)"), XM),
                       IOSlot("addr_alarm", "in", "Alarm (ALM)", XM, optional=True),
                       IOSlot("addr_pos", "wordin", tr("ตำแหน่งปัจจุบัน → D"), ("D",), optional=True)),
             desc=tr("แกนเชิงเส้นขับด้วยเซอร์โว: สั่ง Servo ON แล้วเขียนตำแหน่งเป้าหมาย (mm) ลง D · "
                  "เคลื่อนแบบเร่ง-คงที่-ลด (คางหมู) · เป้าเกินระยะ = Alarm (ปิด Servo ON เพื่อรีเซ็ต)"),
             aliases="servo motor drive positioning linear axis"),
    KindInfo("safety_door", tr("สวิตช์ประตู Safety"), "safety", "in", XM, False,
             {"label": tr("ประตู 1"), "address": "X17", "addr_ch2": "", "contact": "NC"},
             main_label=tr("ช่อง 1 (NC)"),
             extra_io=(IOSlot("addr_ch2", "in", tr("ช่อง 2 (NC)"), XM, optional=True),),
             desc=tr("สวิตช์ล็อกประตูเครื่องจักร ปิดประตู = ส่ง 1 · เปิด = 0 · ใช้ 2 ช่องเพื่อตรวจหน้าสัมผัสเชื่อมติด "
                  "(สองช่องไม่ตรงกัน = ผิดปกติ ห้ามเดินเครื่อง) · คลิก = เปิด/ปิดประตู"),
             aliases="safety door interlock guard switch dual channel"),
    KindInfo("light_curtain", tr("ม่านแสงนิรภัย (Light curtain)"), "safety", "in", XM, False,
             {"label": tr("ม่านแสง"), "address": "X20", "contact": "NC"},
             main_label="OSSD",
             desc=tr("ลำแสงหลายเส้นกันมือเข้าเขตอันตราย ลำแสงครบ = OSSD ON (1) · ขาด = 0 → เครื่องต้องหยุดทันที · "
                  "คลิก = ยื่นมือเข้า, ชิ้นงานผ่านก็ตัดลำแสงได้"),
             aliases="light curtain safety ossd guard"),
    KindInfo("pick_place", tr("แขนหยิบ-วาง 2 แกน (Pick & Place)"), "robot", "out", YM,
             defaults={"label": tr("แขนหยิบ"), "address": "Y12", "addr_right": "Y13", "addr_grip": "Y14",
                       "addr_up": "X21", "addr_down": "X22", "addr_left": "X23", "addr_rightlim": "X24",
                       "addr_gripped": ""},
             main_label=tr("แกน Z ลง"),
             extra_io=(IOSlot("addr_right", "out", tr("แกน X ไปปลายทาง"), YM),
                       IOSlot("addr_grip", "out", tr("หัวจับ (หนีบ)"), YM),
                       IOSlot("addr_up", "in", tr("Z บนสุด"), XM),
                       IOSlot("addr_down", "in", tr("Z ล่างสุด"), XM),
                       IOSlot("addr_left", "in", tr("X ต้นทาง"), XM),
                       IOSlot("addr_rightlim", "in", tr("X ปลายทาง"), XM),
                       IOSlot("addr_gripped", "in", tr("จับชิ้นงานแล้ว"), XM, optional=True)),
             desc=tr("แขนนิวแมติก 2 แกน + หัวจับ: หยิบชิ้นงานจากต้นทาง (ถาดป้อนหรือปลายสายพาน) ไปวางถาดปลายทาง · "
                  "ฝึกโปรแกรมแบบลำดับขั้น (Step) — เลื่อนแกน X ตอน Z ยังไม่ขึ้นสุด = ชน!"),
             aliases="pick and place robot arm gripper sequence"),
    KindInfo("barcode", tr("เครื่องอ่านบาร์โค้ด (Barcode)"), "sensor", "wordin", ("D",),
             defaults={"label": "BCR1", "address": "D44", "addr_ok": "X25", "addr_trig": ""},
             main_label=tr("รหัสที่อ่านได้ → D"),
             extra_io=(IOSlot("addr_ok", "in", tr("อ่านสำเร็จ (OK)"), XM),
                       IOSlot("addr_trig", "out", tr("สั่งอ่าน (Trigger)"), YM, optional=True)),
             desc=tr("อ่านรหัสชิ้นงานที่ผ่านใต้เครื่อง (โลหะ = 1xx, พลาสติก = 2xx) ส่งเลขเข้า D + บิต OK · "
                  "ถ้าต่อ Trigger จะอ่านเฉพาะตอนสั่ง · อ่านไม่ได้ = −1"),
             aliases="barcode reader scanner code id"),
    # ---------- R5: Stepper ----------
    KindInfo("stepper", tr("สเต็ปมอเตอร์ + ไดรฟ์ (Stepper)"), "robot", "out", YM,
             defaults={"label": "STP1", "address": "Y11", "addr_start": "Y12", "addr_target": "D50",
                       "addr_jog_f": "", "addr_jog_r": "", "addr_busy": "X16", "addr_home": "X17", "addr_pos": ""},
             main_label=tr("ENA (เปิดแรงบิด)"),
             extra_io=(IOSlot("addr_start", "out", tr("START (ขอบขาขึ้น = ไปตำแหน่งเป้า)"), YM),
                       IOSlot("addr_target", "word", tr("ตำแหน่งเป้า (พัลส์)"), ("D",)),
                       IOSlot("addr_jog_f", "out", tr("Jog ไปหน้า"), YM, optional=True),
                       IOSlot("addr_jog_r", "out", tr("Jog ถอยกลับ (เจอ Home = รีเซ็ตตัวนับ)"), YM, optional=True),
                       IOSlot("addr_busy", "in", tr("BUSY (กำลังเคลื่อน)"), XM),
                       IOSlot("addr_home", "in", tr("เซนเซอร์ Home"), XM),
                       IOSlot("addr_pos", "wordin", tr("ตำแหน่งที่นับได้ (พัลส์) → D"), ("D",), optional=True)),
             desc=tr("หมุนทีละสเต็ปตามพัลส์ ไม่มี encoder ป้อนกลับ: ไดรฟ์นับพัลส์ไว้ แต่ถ้าโหลด/ความเร็ว/ความเร่งเกินแรงบิด "
                  "มอเตอร์จะหลุดสเต็ป ตำแหน่งจริงไม่ตรงกับที่นับ → ต้อง Home ใหม่ (Jog ถอยจนเจอ Home) · "
                  "1 รอบ = 200 สเต็ป × ไมโครสเต็ป"),
             aliases="stepper stepping motor driver pulse microstep home jog positioning nema"),
    # ---------- R5: มอเตอร์ DC / BLDC ----------
    KindInfo("dc_motor", tr("มอเตอร์ DC / BLDC"), "motor", "out", YM,
             defaults={"label": "DC1", "address": "Y0", "addr_rev": "Y1", "addr_speed": "", "addr_alarm": "",
                       "addr_rpm": ""},
             main_label=tr("เดินหน้า (DC) / EN (BLDC)"),
             extra_io=(IOSlot("addr_rev", "out", tr("ถอยหลัง (DC) / DIR (BLDC)"), YM, optional=True),
                       IOSlot("addr_speed", "word", tr("ความเร็วสั่ง 0–4000 (PWM/analog)"), ("D",), optional=True),
                       IOSlot("addr_alarm", "in", tr("Alarm ไดรฟ์ (BLDC)"), XM, optional=True),
                       IOSlot("addr_rpm", "wordin", tr("รอบจริง (rpm) → D"), ("D",), optional=True)),
             desc=tr("DC แปรงถ่าน: กลับทางด้วยรีเลย์กลับขั้ว (ห้ามสั่งสองทางพร้อมกัน = ลัดวงจร) ปรับรอบด้วย PWM · "
                  "BLDC: ไดรฟ์รับ EN/DIR + ความเร็ว analog กลับ DIR ขณะหมุนไดรฟ์จะชะลอแล้วกลับเอง · "
                  "ส่งรอบจริงกลับเข้า D ได้ (ใช้ฝึกเทียบความเร็ว/PID) · เลือกชนิดที่ Properties"),
             aliases="dc motor brushed bldc brushless pwm h-bridge driver speed direction hall"),
    # ---------- R5: สุญญากาศ ----------
    KindInfo("vacuum", tr("ชุดดูดสุญญากาศ (Vacuum)"), "process", "out", YM,
             defaults={"label": "VAC1", "address": "Y6", "addr_blow": "", "addr_ok": "X12", "addr_lift": "",
                       "addr_kpa": ""},
             main_label=tr("วาล์วดูด (Ejector)"),
             extra_io=(IOSlot("addr_blow", "out", tr("วาล์วเป่าปล่อย"), YM, optional=True),
                       IOSlot("addr_ok", "in", tr("สวิตช์สุญญากาศ (OK)"), XM),
                       IOSlot("addr_lift", "out", tr("ยกถ้วยดูดขึ้น"), YM, optional=True),
                       IOSlot("addr_kpa", "wordin", tr("ค่าสุญญากาศ (0–1000 = 0 ถึง −100 kPa) → D"), ("D",),
                              optional=True)),
             desc=tr("ejector สร้างสุญญากาศให้ถ้วยดูดจับชิ้นงาน · สวิตช์สุญญากาศ ON เมื่อดูดได้ถึงค่าตั้ง (มีชิ้นงานปิดถ้วย) · "
                  "ต้องรอ OK ก่อนยก ไม่งั้นชิ้นงานหลุด · ปล่อยชิ้นงานต้องเป่าลม ไม่งั้นติดถ้วยนาน · คลิกถาด = วาง/เอาชิ้นงานออก"),
             aliases="vacuum ejector suction cup pad venturi blow off vacuum switch pick"),
    # ---------- R5: รีเลย์ ----------
    KindInfo("relay", tr("รีเลย์ควบคุม (Control relay)"), "relay", "out", YM,
             defaults={"label": "CR1", "address": "Y2", "addr_c1": "X6", "addr_c2": "", "addr_c3": "",
                       "addr_c4": ""},
             main_label=tr("คอยล์ (13-14)"),
             extra_io=tuple(IOSlot(f"addr_c{i}", "in", tr("หน้าสัมผัสชุด {0}", i), XM, optional=True)
                            for i in range(1, 5)),
             desc=tr("รีเลย์ขนาดเล็กแบบเสียบซ็อกเก็ต (4 ชุดหน้าสัมผัส) ใช้ขยายหน้าสัมผัส/แยกแรงดัน 24V กับ 220V · "
                  "มีเวลาดูด/ปล่อยไม่กี่ ms · คลิก = คันโยกทดสอบ (ล็อกให้ทำงานด้วยมือ)"),
             aliases="relay control relay my ly plug in socket coil contact"),
    KindInfo("latch_relay", tr("รีเลย์จำสถานะ (Latching / Impulse)"), "relay", "out", YM,
             defaults={"label": "LR1", "address": "Y3", "addr_reset": "", "addr_c1": "X7", "addr_c2": ""},
             main_label=tr("คอยล์ SET / Impulse"),
             extra_io=(IOSlot("addr_reset", "out", tr("คอยล์ RESET (โหมด SET/RESET)"), YM, optional=True),
                       IOSlot("addr_c1", "in", tr("หน้าสัมผัสชุด 1"), XM, optional=True),
                       IOSlot("addr_c2", "in", tr("หน้าสัมผัสชุด 2"), XM, optional=True)),
             desc=tr("รีเลย์ที่จำสถานะด้วยกลไก ไม่ต้องจ่ายไฟค้าง · Impulse: พัลส์หนึ่งครั้ง = สลับ ON/OFF (แบบสวิตช์ไฟบันได) · "
                  "SET/RESET: คอยล์แยก 2 ตัว · สถานะไม่หายเมื่อไฟดับ · คลิก = สลับด้วยมือ"),
             aliases="latching relay impulse relay bistable step relay set reset memory"),
    KindInfo("ssr", tr("โซลิดสเตตรีเลย์ (SSR)"), "relay", "out", YM,
             defaults={"label": "SSR1", "address": "Y4"},
             main_label=tr("อินพุต 3-4 (DC)"),
             desc=tr("รีเลย์ไม่มีหน้าสัมผัส (ไทริสเตอร์) ตัดต่อเร็ว เงียบ ไม่สึก ใช้คุมฮีตเตอร์แบบ PWM · "
                  "มีความร้อนสะสม ต้องติดฮีตซิงก์ · ตอน OFF ยังมีกระแสรั่วเล็กน้อย · พังมักเป็นแบบช็อตค้าง ON"),
             aliases="ssr solid state relay thyristor triac zero cross heater pwm"),
    KindInfo("phase_relay", tr("รีเลย์ป้องกันเฟส (Phase protection)"), "relay", "in", XM, False,
             {"label": "PR1", "address": "X10"},
             main_label=tr("หน้าสัมผัส OK (11-14)"),
             desc=tr("เฝ้าไฟ 3 เฟสที่เข้าเครื่อง: เฟสขาด / สลับเฟส / แรงดันต่ำ-เกิน → หน้าสัมผัส OK เปิด (PLC เห็น 0) "
                  "เพื่อกันมอเตอร์ไหม้หรือหมุนกลับทาง · คลิก = เปลี่ยนสภาพไฟจำลอง"),
             aliases="phase failure relay phase loss reversal sequence under over voltage monitor"),
    KindInfo("safety_relay", tr("เซฟตี้รีเลย์ (Safety relay)"), "safety", "in", XM, False,
             {"label": "SR1", "address": "X11", "addr_aux": "", "addr_reset": ""},
             main_label="Safety 13-14 (NO)",
             extra_io=(IOSlot("addr_aux", "in", tr("หน้าสัมผัสช่วย 41-42 (NC)"), XM, optional=True),
                       IOSlot("addr_reset", "out", tr("สั่งรีเซ็ต (monitored)"), YM, optional=True)),
             desc=tr("โมดูลนิรภัย 2 ช่อง รับ E-Stop/ประตู/ม่านแสง ตัดเอาต์พุตทันทีเมื่อสั่งหยุด และต้องรีเซ็ตก่อนเดินใหม่ "
                  "(รีเซ็ตตอนปล่อยปุ่ม) · สองช่องไม่ตรงกัน = ตรวจพบหน้าสัมผัสเชื่อมติด รีเซ็ตไม่ได้ · ผูก E-Stop ที่ Properties"),
             aliases="safety relay module emergency stop dual channel monitored reset category"),
    # ---------- ข้อความ / กรอบ ----------
    KindInfo("note", tr("ข้อความ (Text)"), "annotation", "none", (),
             defaults={"label": "", "text": "", "size": 10, "width": 260,
                       "color": "white"},
             desc=tr("ข้อความอธิบายบนผัง เช่น โจทย์ หรือตาราง I/O"), aliases="text note label comment"),
    KindInfo("zone", tr("กรอบโซน (Zone)"), "annotation", "none", (),
             defaults={"label": tr("สถานี 1"), "w": 360, "h": 240, "color": "blue"},
             desc=tr("กรอบแบ่งพื้นที่บนผัง เช่น สถานีป้อน / สถานีคัดแยก"), aliases="zone frame box group"),
]

from dataclasses import replace  # noqa: E402

from .specs import SPECS  # noqa: E402

CATALOG: dict[str, KindInfo] = {k.kind: replace(k, specs=SPECS.get(k.kind, ())) for k in _K}
