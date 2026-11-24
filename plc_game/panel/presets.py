"""รุ่นสำเร็จรูป: ชุดสเปกทั่วไปของอุปกรณ์จริง (ไม่อ้างยี่ห้อ) — เลือกแล้วตั้งค่าหลายช่องพร้อมกัน."""
from __future__ import annotations

from ..i18n import tr

PRESETS: dict[str, list[tuple[str, dict]]] = {
    "pushbutton": [
        (tr("ปุ่มกด Ø22 หน้าสัมผัสใหม่ (ไม่กระเด้ง)"), {"size": "22", "bounce_ms": 0}),
        (tr("ปุ่มกด Ø22 หน้าสัมผัสเก่า (กระเด้ง 10 ms)"), {"size": "22", "bounce_ms": 10}),
    ],
    "limit": [
        (tr("ลิมิตสวิตช์ก้านโยกลูกล้อ"), {"actuator": "roller", "bounce_ms": 0}),
        (tr("ลิมิตสวิตช์ก้านโยก (กระเด้ง 8 ms)"), {"actuator": "roller", "bounce_ms": 8}),
    ],
    "sensor": [
        (tr("Proximity Inductive M18 ระยะ 8 mm NPN-NO"),
         {"sense": "inductive", "output": "npn", "range_mm": 8, "mode": "lon", "response_ms": 2, "contact": "NO"}),
        (tr("Proximity Inductive M12 ระยะ 4 mm PNP-NO"),
         {"sense": "inductive", "output": "pnp", "range_mm": 4, "mode": "lon", "response_ms": 2, "contact": "NO"}),
        (tr("Proximity Capacitive M18 ระยะ 10 mm NPN"),
         {"sense": "capacitive", "output": "npn", "range_mm": 10, "mode": "lon", "response_ms": 10, "contact": "NO"}),
        ("Photo diffuse 300 mm PNP Light-ON",
         {"sense": "photo", "output": "pnp", "range_mm": 300, "mode": "lon", "response_ms": 1, "contact": "NO"}),
        ("Photo diffuse 100 mm NPN Dark-ON",
         {"sense": "photo", "output": "npn", "range_mm": 100, "mode": "don", "response_ms": 1, "contact": "NO"}),
    ],
    "motor": [
        (tr("มอเตอร์ 3 เฟส 0.37 kW 380 V 1.1 A 1400 rpm"),
         {"kw": 0.37, "volt": "380", "fla": 1.1, "rpm": 1400, "start": "dol", "accel_s": 0.5, "decel_s": 1.0}),
        (tr("มอเตอร์ 3 เฟส 0.75 kW 380 V 1.9 A 1400 rpm"),
         {"kw": 0.75, "volt": "380", "fla": 1.9, "rpm": 1400, "start": "dol", "accel_s": 0.8, "decel_s": 1.5}),
        (tr("มอเตอร์ 3 เฟส 2.2 kW 380 V 4.9 A 1430 rpm"),
         {"kw": 2.2, "volt": "380", "fla": 4.9, "rpm": 1430, "start": "dol", "accel_s": 1.2, "decel_s": 2.5}),
        (tr("มอเตอร์ 3 เฟส 7.5 kW 380 V 15 A สตาร์-เดลต้า"),
         {"kw": 7.5, "volt": "380", "fla": 15.0, "rpm": 1450, "start": "yd", "accel_s": 3.0, "decel_s": 5.0}),
        (tr("มอเตอร์ 1 เฟส 0.37 kW 220 V 3.0 A"),
         {"kw": 0.37, "volt": "220", "fla": 3.0, "rpm": 1420, "start": "dol", "accel_s": 0.5, "decel_s": 1.0}),
    ],
    "overload": [
        (tr("OL 1.0–1.6 A Class 10 (ตั้ง 1.1 A)"), {"ir_a": 1.1, "trip_class": "10", "reset": "manual"}),
        (tr("OL 1.6–2.5 A Class 10 (ตั้ง 1.9 A)"), {"ir_a": 1.9, "trip_class": "10", "reset": "manual"}),
        (tr("OL 4–6 A Class 10 (ตั้ง 4.9 A)"), {"ir_a": 4.9, "trip_class": "10", "reset": "manual"}),
        (tr("OL 12–18 A Class 20 (ตั้ง 15 A)"), {"ir_a": 15.0, "trip_class": "20", "reset": "manual"}),
    ],
    "contactor": [
        (tr("คอนแทคเตอร์ 9 A คอยล์ 24 VDC"), {"coil": "24vdc", "pickup_ms": 25}),
        (tr("คอนแทคเตอร์ 18 A คอยล์ 220 VAC"), {"coil": "220vac", "pickup_ms": 15}),
    ],
    "lamp": [
        (tr("ไพล็อตแลมป์ LED Ø22 24 VDC"), {"lamp_type": "led", "volt": "24vdc"}),
        (tr("หลอดไส้ 220 VAC (แบบเก่า)"), {"lamp_type": "incand", "volt": "220vac"}),
    ],
    "cylinder": [
        (tr("กระบอกสูบ Ø32 ช่วงชัก 100 mm (6 bar)"),
         {"timing": "spec", "bore_mm": 32, "stroke_mm": 100, "pressure_bar": 6.0, "load_kg": 2.0}),
        (tr("กระบอกสูบ Ø50 ช่วงชัก 200 mm (6 bar, โหลด 30 kg)"),
         {"timing": "spec", "bore_mm": 50, "stroke_mm": 200, "pressure_bar": 6.0, "load_kg": 30.0}),
        (tr("กระบอกสูบ Ø20 ช่วงชัก 50 mm (ลมอ่อน 3 bar)"),
         {"timing": "spec", "bore_mm": 20, "stroke_mm": 50, "pressure_bar": 3.0, "load_kg": 0.5}),
        (tr("วาล์ว 5/3 กลางปิด + กระบอก Ø32 (หยุดกลางทาง)"),
         {"valve": "c_closed", "actuation": "double", "timing": "fixed", "stroke_s": 2.0}),
        (tr("วาล์ว 5/3 กลางระบาย + กระบอก Ø32 โหลด 5 kg"),
         {"valve": "c_exhaust", "actuation": "double", "timing": "fixed", "stroke_s": 2.0, "load_kg": 5.0}),
        (tr("กระบอกทางเดียว Ø16 สปริงคืน + วาล์ว 3/2"),
         {"actuation": "single", "valve": "single", "timing": "fixed", "stroke_s": 0.5}),
    ],
    "pusher": [
        (tr("กระบอกดัน Ø20 ช่วงชัก 50 mm"), {"timing": "spec", "bore_mm": 20, "stroke_mm": 50, "pressure_bar": 6.0,
                                         "load_kg": 0.3}),
    ],
    "tank": [
        (tr("ถัง 200 L + ปั๊ม 20 L/min"), {"rate_mode": "spec", "volume_l": 200, "pump_lpm": 20, "drain_lpm": 15}),
        (tr("ถัง 50 L + ปั๊ม 20 L/min (เต็มเร็ว)"), {"rate_mode": "spec", "volume_l": 50, "pump_lpm": 20,
                                                "drain_lpm": 12}),
    ],
    "encoder": [
        (tr("เอนโค้ดเดอร์ 100 PPR ล้อวัด Ø50 mm"), {"ppr": 100, "wheel_mm": 50}),
        (tr("เอนโค้ดเดอร์ 10 PPR ล้อวัด Ø100 mm (PLC อ่านทัน)"), {"ppr": 10, "wheel_mm": 100}),
    ],
    "vfd": [
        (tr("อินเวอร์เตอร์ 0.75 kW เร่ง 3 s ลด 3 s"), {"ramp_s": 3.0, "decel_s": 3.0, "max_hz": 60, "motor_rpm": 1450}),
        (tr("อินเวอร์เตอร์ 2.2 kW เร่ง 5 s ลด 8 s"), {"ramp_s": 5.0, "decel_s": 8.0, "max_hz": 60, "motor_rpm": 1430}),
    ],
    # ---------------- R3 ----------------
    "selector3": [
        (tr("สวิตช์บิด 3 ตำแหน่ง MAN-OFF-AUTO"), {"keyed": "knob", "pos_names": "MAN;OFF;AUTO"}),
        (tr("สวิตช์กุญแจ 3 ตำแหน่ง HAND-OFF-AUTO"), {"keyed": "key", "pos_names": "HAND;OFF;AUTO"}),
    ],
    "timer_relay": [
        (tr("ไทเมอร์ ON-delay 0.1–10 s (ตั้ง 3 s)"), {"mode": "on", "set_s": 3.0}),
        (tr("ไทเมอร์ OFF-delay (ตั้ง 5 s)"), {"mode": "off", "set_s": 5.0}),
        (tr("ไทเมอร์ Flicker 0.5 s (ไฟกะพริบ)"), {"mode": "flicker", "set_s": 0.5}),
    ],
    "float_switch": [
        (tr("ลูกลอยไฟฟ้า แจ้งน้ำเต็ม (80%)"), {"level_pct": 80, "float_dir": "up"}),
        (tr("ลูกลอยไฟฟ้า กันปั๊มแห้ง (15%)"), {"level_pct": 15, "float_dir": "down"}),
    ],
    "compressor": [
        (tr("ปั๊มลมโรงเรียน 200 L/min ถัง 10 L"), {"lpm": 200, "tank_l": 10, "max_bar": 8.0}),
        (tr("ปั๊มลมโรงงาน 600 L/min ถัง 100 L"), {"lpm": 600, "tank_l": 100, "max_bar": 10.0}),
    ],
    "pressure_switch": [
        (tr("สวิตช์ความดัน ON 6 bar / Diff 1 bar"), {"set_bar": 6.0, "diff_bar": 1.0}),
        (tr("สวิตช์ความดัน ON 4 bar / Diff 0.5 bar"), {"set_bar": 4.0, "diff_bar": 0.5}),
    ],
    "level_tx": [
        (tr("Ultrasonic 4–20 mA → 0–4000 (เต็มถัง)"), {"raw_max": 4000, "min_pct": 0, "max_pct": 100}),
        ("Ultrasonic 4–20 mA → 0–32000", {"raw_max": 32000, "min_pct": 0, "max_pct": 100}),
    ],
    "load_cell": [
        (tr("ตาชั่ง 5 kg (ละเอียด)"), {"cap_g": 5000, "noise_g": 2, "fill_gps": 200}),
        (tr("ตาชั่ง 30 kg (รบกวนสูง)"), {"cap_g": 30000, "noise_g": 15, "fill_gps": 1500}),
    ],
    "servo": [
        (tr("แกนเซอร์โว 500 mm 250 mm/s"), {"stroke_mm": 500, "vmax": 250, "acc": 500}),
        (tr("แกนเซอร์โว 1000 mm ความเร็วสูง 800 mm/s"), {"stroke_mm": 1000, "vmax": 800, "acc": 3000}),
    ],
    "safety_door": [
        (tr("สวิตช์ประตูลิ้นแยก 2 ช่อง NC"), {"lock": "plain", "contact": "NC"}),
        (tr("สวิตช์ประตูล็อกด้วยโซลินอยด์"), {"lock": "lock", "contact": "NC"}),
    ],
    "light_curtain": [
        (tr("ม่านแสงกันนิ้ว 14 mm (16 ลำแสง)"), {"beams": 16, "height": 160, "response_ms": 10}),
        (tr("ม่านแสงกันมือ 30 mm (8 ลำแสง)"), {"beams": 8, "height": 140, "response_ms": 15}),
    ],
    "pick_place": [
        (tr("แขนหยิบ-วางนิวแมติกมาตรฐาน"), {"x_s": 1.0, "z_s": 0.5, "grip_ms": 200}),
        (tr("แขนหยิบ-วางเร็ว"), {"x_s": 0.5, "z_s": 0.3, "grip_ms": 100}),
    ],
    "barcode": [
        (tr("เครื่องอ่านบาร์โค้ดแบบติดตั้งอยู่กับที่"), {"read_ms": 100, "range_mm": 120}),
        (tr("เครื่องอ่าน 2D แบบเร็ว"), {"read_ms": 30, "range_mm": 150}),
    ],
    # ---------------- R5 ----------------
    "stepper": [
        (tr("NEMA 23 + ไดรฟ์ 1/16 บอลสกรู 10 mm (โหลดปกติ)"), {"step_deg": "1.8", "microstep": "16", "lead_mm": 10,
                                                         "pps_max": 16000, "accel_pps2": 32000, "load_pct": 50}),
        (tr("NEMA 17 Full step (หยาบ เร็ว)"), {"step_deg": "1.8", "microstep": "1", "lead_mm": 8, "pps_max": 1000,
                                         "accel_pps2": 2000, "jog_pps": 400, "load_pct": 40}),
        (tr("ตั้งเร็วเกินกับโหลดหนัก (จะหลุดสเต็ป)"), {"microstep": "16", "pps_max": 30000, "accel_pps2": 200000,
                                                 "load_pct": 90}),
    ],
    "dc_motor": [
        (tr("มอเตอร์ DC แปรงถ่าน 24 V 3000 rpm (รีเลย์กลับขั้ว)"), {"drive": "brushed", "volt": "24", "rpm_max": 3000,
                                                             "accel_s": 0.3, "decel_s": 0.6}),
        (tr("BLDC 24 V 3000 rpm + ไดรฟ์ ramp 1 s"), {"drive": "bldc", "volt": "24", "rpm_max": 3000, "accel_s": 1.0,
                                                "decel_s": 1.0}),
        ("BLDC 48 V 4000 rpm (ramp 2 s)", {"drive": "bldc", "volt": "48", "rpm_max": 4000, "accel_s": 2.0,
                                          "decel_s": 2.0}),
    ],
    "vacuum": [
        (tr("ejector + ถ้วยดูด Ø20 ชิ้นงานเบา (ตั้ง −60 kPa)"), {"set_kpa": 60, "diff_kpa": 5, "hold_kpa": 30, "lift_s": 0.5}),
        (tr("ชิ้นงานหนัก (ต้อง −70 kPa ขึ้นไปจึงจับอยู่)"), {"set_kpa": 75, "diff_kpa": 5, "hold_kpa": 65, "lift_s": 0.8}),
    ],
    "motor_yd": [
        (tr("มอเตอร์ 7.5 kW 380 V 15 A สตาร์-เดลต้า"), {"kw": 7.5, "fla": 15.0, "rpm": 1450, "accel_s": 4.0,
                                                   "decel_s": 5.0, "star_max_s": 15}),
        (tr("มอเตอร์ 15 kW 380 V 29 A (เฉื่อยมาก)"), {"kw": 15.0, "fla": 29.0, "rpm": 1460, "accel_s": 8.0,
                                                 "decel_s": 10.0, "star_max_s": 20}),
        (tr("มอเตอร์ 5.5 kW 380 V 11 A (เร่งเร็ว)"), {"kw": 5.5, "fla": 11.0, "rpm": 1440, "accel_s": 2.5,
                                                "decel_s": 4.0, "star_max_s": 10}),
    ],
    "relay": [
        (tr("รีเลย์ 4 คอนแทค คอยล์ 24 VDC (2NO+2NC)"),
         {"coil": "24vdc", "pickup_ms": 10, "release_ms": 5, "c1": "NO", "c2": "NO", "c3": "NC", "c4": "NC"}),
        (tr("รีเลย์ 2 คอนแทค คอยล์ 220 VAC"), {"coil": "220vac", "pickup_ms": 15, "release_ms": 10, "c1": "NO", "c2": "NC"}),
    ],
    "latch_relay": [
        (tr("Impulse relay (ไฟบันได กดสลับ)"), {"mode": "impulse", "c1": "NO", "c2": "NC"}),
        (tr("Latching relay คอยล์ SET/RESET"), {"mode": "set_reset", "c1": "NO", "c2": "NC"}),
    ],
    "ssr": [
        (tr("SSR 25 A + ฮีตซิงก์ คุมฮีตเตอร์ 10 A"), {"load": "heater", "load_a": 10.0, "heatsink": "yes", "zero_cross": "yes"}),
        (tr("SSR ไม่ติดฮีตซิงก์ โหลด 10 A (จะร้อนจนพัง)"), {"load": "heater", "load_a": 10.0, "heatsink": "no"}),
        (tr("SSR คุมหลอด LED เล็ก (เห็นกระแสรั่ว)"), {"load": "lamp", "load_a": 0.1, "leak_ma": 5, "zero_cross": "no"}),
    ],
    "phase_relay": [
        (tr("รีเลย์ป้องกันเฟส 380 V หน่วง 1 s"), {"trip_s": 1.0, "reset_s": 1.0}),
        (tr("รีเลย์ป้องกันเฟส หน่วง 5 s (โหลดไฟกระพริบบ่อย)"), {"trip_s": 5.0, "reset_s": 2.0}),
    ],
    "safety_relay": [
        (tr("เซฟตี้รีเลย์ 2 ช่อง รีเซ็ตแบบ Monitored (E-Stop)"), {"reset_mode": "monitored"}),
        (tr("เซฟตี้รีเลย์ 2 ช่อง Auto reset (ประตู guard)"), {"reset_mode": "auto"}),
    ],
}
PRESETS["motor_rev"] = PRESETS["motor"]


def presets_for(kind: str) -> list[tuple[str, dict]]:
    return PRESETS.get(kind, [])
