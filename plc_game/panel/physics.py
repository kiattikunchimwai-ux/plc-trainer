"""สูตรจำลองพฤติกรรมอุปกรณ์จริง (ฟังก์ชันล้วน ไม่ขึ้นกับ Qt — เทสต์ได้ตรงๆ)."""
from __future__ import annotations

import math

G = 9.81
START_MULT = {"dol": 6.0, "yd": 2.0, "soft": 3.0}   # กระแสตอนเริ่มเดิน ÷ FLA


# ---------------- มอเตอร์ ----------------
def ramp(k: float, target: float, dt: float, up_s: float, down_s: float) -> float:
    """ความเร็ว 0..1 วิ่งเข้าหาเป้า ตามเวลาเร่ง/ลด (0 = ทันที)."""
    if k < target:
        return target if up_s <= 0 else min(target, k + dt / up_s)
    if k > target:
        return target if down_s <= 0 else max(target, k - dt / down_s)
    return k


def motor_current(fla: float, powered: bool, speed_k: float, load_pct: float, start: str = "dol",
                  jammed: bool = False) -> float:
    """กระแสมอเตอร์ (A): ล็อกโรเตอร์/กำลังเร่ง = กระแสกระชาก, วิ่งปกติ ≈ FLA×(0.3+0.7·โหลด)."""
    if not powered or fla <= 0:
        return 0.0
    mult = START_MULT.get(start, 6.0)
    run = fla * (0.3 + 0.7 * max(load_pct, 0) / 100.0)
    if jammed:
        return fla * mult
    if speed_k < 0.95:              # ช่วงเร่ง: กระแสค่อยๆ ลดจากกระแสกระชากลงมาที่กระแสวิ่ง
        return run + (fla * mult - run) * (1 - speed_k / 0.95)
    return run


# ---------------- สตาร์-เดลต้า ----------------
YD_STAR_SPEED = 0.9        # ต่อสตาร์ แรงบิด 1/3 → ไต่ได้ราว 90% ของรอบ
YD_SAFE_SWITCH = 0.7       # เข้าเดลต้าตอนรอบต่ำกว่านี้ = สลับเร็วเกิน (กระแสกระชาก)


def yd_mode(main: bool, star: bool, delta: bool) -> str:
    """short = KM2+KM3 พร้อมกัน · off = ไม่มี Main · open = มี Main แต่ไม่ต่อสตาร์/เดลต้า (ขดลวดไม่ครบวงจร)."""
    if star and delta:
        return "short"
    if not main:
        return "off"
    return "star" if star else "delta" if delta else "open"


def yd_target(mode: str) -> float:
    return {"star": YD_STAR_SPEED, "delta": 1.0}.get(mode, 0.0)


def yd_current(fla: float, mode: str, speed_k: float, load_pct: float, jammed: bool = False) -> float:
    """กระแสสาย (A): สตาร์ = กระแสสตาร์ท ~2×FLA (1/3 ของ DOL) · เดลต้าตอนรอบต่ำ = ~6×FLA."""
    if fla <= 0 or mode in ("off", "open", "short"):
        return 0.0
    run = fla * (0.3 + 0.7 * max(load_pct, 0) / 100.0)
    if mode == "star":
        lock = 2.0 * fla
        k = 1.0 if jammed else 1 - min(speed_k / YD_STAR_SPEED, 1.0)
        return run * 0.6 + (lock - run * 0.6) * k
    lock = 6.0 * fla
    if jammed:
        return lock
    return run + (lock - run) * max(0.0, 1 - speed_k / 0.95)


# ---------------- Overload (โมเดลความร้อน I²t) ----------------
OL_TRIP_THETA = 1.15 ** 2           # ไม่ทริปที่ 1.05×Ir, ทริป (ในที่สุด) ที่ ≥ 1.15×Ir


def ol_tau(trip_class) -> float:
    """ค่าคงที่เวลาความร้อน: Class 10 → ทริปราว 8 s ที่ 7.2×Ir (จากเย็น)."""
    try:
        c = float(trip_class)
    except (TypeError, ValueError):
        c = 10.0
    return 31.4 * c


def ol_heat_step(theta: float, current: float, ir: float, tau: float, dt: float) -> float:
    """θ' = ((I/Ir)² − θ)/τ — θ คือความร้อนสะสม (หน่วย (I/Ir)²)."""
    if ir <= 0:
        return theta
    target = (current / ir) ** 2
    return target + (theta - target) * math.exp(-dt / tau)


def ol_trip_time(multiple: float, trip_class=10) -> float:
    """เวลาทริปจากสภาพเย็นที่กระแส multiple×Ir (∞ ถ้าไม่ทริป)."""
    target = multiple ** 2
    if target <= OL_TRIP_THETA:
        return math.inf
    return -ol_tau(trip_class) * math.log(1 - OL_TRIP_THETA / target)


# ---------------- กระบอกสูบ ----------------
MIN_BAR = 2.0


def cylinder_force(bore_mm: float, pressure_bar: float) -> float:
    """แรงดันออก (N) = ความดัน × พื้นที่ลูกสูบ."""
    area = math.pi * (bore_mm / 2000.0) ** 2
    return pressure_bar * 1e5 * area


def cylinder_stroke_time(bore_mm: float, stroke_mm: float, pressure_bar: float, load_kg: float,
                         extend: bool = True) -> float | None:
    """เวลาเคลื่อนสุดระยะ (s) หรือ None ถ้าไม่ขยับ (ลมน้อยเกิน / โหลดหนักเกินแรง).
    ความเร็วไม่มีโหลดที่ 6 bar ≈ 0.5 m/s, ลดลงตามความดันและสัดส่วนโหลด/แรง."""
    if pressure_bar < MIN_BAR:
        return None
    force = cylinder_force(bore_mm, pressure_bar)
    ratio = (load_kg * G / force) if (extend and force > 0) else 0.0
    if ratio >= 0.9:
        return None
    v = 0.5 * min(1.0, (pressure_bar - 1.5) / 4.5) * (1 - ratio)
    return max(0.05, (stroke_mm / 1000.0) / max(v, 1e-3))


# ---------------- ถังน้ำ / เอนโค้ดเดอร์ ----------------
def lpm_to_pct_s(lpm: float, volume_l: float) -> float:
    return (lpm / 60.0) / max(volume_l, 1e-6) * 100.0


def encoder_hz(speed_mm_s: float, wheel_mm: float, ppr: float) -> float:
    if wheel_mm <= 0 or ppr <= 0:
        return 0.0
    return speed_mm_s / (math.pi * wheel_mm) * ppr


def max_readable_hz(poll_ms: float = 50) -> float:
    """PLC อ่านผ่านการสุ่มอ่านทุก poll_ms: พัลส์ต้องค้างอย่างน้อย 1 รอบอ่าน (Nyquist)."""
    return 1000.0 / poll_ms / 2.0


# ---------------- Stepper ----------------
STEP_RPS_REF = 10.0        # rev/s ที่แรงบิดเหลือน้อย (โค้งแรงบิดตกตามความเร็ว)
STEP_INERTIA_K = 0.02      # แรงบิดที่ต้องใช้ต่อความเร่ง 1 rev/s² (สัดส่วนของแรงบิดพิกัด)


def steps_per_rev(step_deg: float, microstep: float) -> float:
    return 360.0 / max(step_deg, 0.01) * max(microstep, 1.0)


def stepper_torque_avail(rps: float) -> float:
    """แรงบิดที่มอเตอร์ให้ได้ (เท่าของแรงบิดพิกัด) ที่ความเร็ว rps — ความเร็วสูง แรงบิดตก."""
    return max(0.0, 1.2 - 0.8 * (abs(rps) / STEP_RPS_REF) ** 2)


def stepper_torque_ok(rps: float, rps2: float, load_pct: float) -> bool:
    """ยังหมุนตามพัลส์ทันไหม: แรงบิดที่ต้องใช้ (โหลด + เร่ง/ลด) ต้องไม่เกินที่มอเตอร์ให้ได้."""
    need = max(load_pct, 0) / 100.0 + STEP_INERTIA_K * abs(rps2)
    return need <= stepper_torque_avail(rps) + 1e-9


# ---------------- ชุดสุญญากาศ (ejector + ถ้วยดูด) ----------------
VAC_SEALED = 80.0          # kPa ต่ำกว่าบรรยากาศ ที่ได้เมื่อถ้วยปิดผนึกกับชิ้นงาน
VAC_OPEN = 10.0            # ไม่มีชิ้นงาน (ดูดอากาศเปล่า)
VAC_LEAK = 40.0            # ถ้วยรั่ว: ได้สูงสุดเท่านี้
VAC_TAU = {"suck": 0.3, "blow": 0.05, "hold": 1.5, "vent": 0.1}
CLOG_SLOW = 5.0            # ไส้กรองตัน: ช้าลงกี่เท่า


def vacuum_step(vac: float, suction: bool, blow: bool, sealed: bool, leak: bool, clog: bool, dt: float) -> float:
    """ระดับสุญญากาศ vac (kPa ต่ำกว่าบรรยากาศ, 0 = ไม่มี) ไปข้างหน้า dt วินาที (first-order).
    เป่า (blow) ชนะดูดเสมอ · ไม่ดูดไม่เป่า + ปิดผนึก = คลายช้า (ชิ้นงานยังติดถ้วยสักพัก)."""
    if blow:
        target, tau = 0.0, VAC_TAU["blow"]
    elif suction:
        target = (VAC_LEAK if leak else VAC_SEALED) if sealed else VAC_OPEN
        tau = VAC_TAU["suck"] * (CLOG_SLOW if clog else 1.0)
    else:
        target, tau = 0.0, VAC_TAU["hold"] if sealed else VAC_TAU["vent"]
    if leak and sealed and not blow and not suction:
        tau = min(tau, 0.3)
    return target + (vac - target) * math.exp(-dt / tau)


# ---------------- SSR (Solid State Relay) ----------------
SSR_VDROP = 1.2          # แรงดันตกคร่อมไทริสเตอร์ตอนนำกระแส (V) → ความร้อน P = Vdrop × I
SSR_RTH = {"yes": 1.0, "no": 8.0}    # ความต้านทานความร้อนรวม (°C/W): มี / ไม่มีฮีตซิงก์
SSR_TAU_S = 10.0         # ค่าคงที่เวลาความร้อน (ย่อให้เห็นผลเร็วในห้องเรียน)
SSR_FAIL_C = 110.0       # เกินนี้ = ไทริสเตอร์พังแบบช็อต (ค้าง ON)


def ssr_heat_step(temp: float, amb: float, current_a: float, duty: float, heatsink: str, dt: float) -> float:
    """อุณหภูมิตัว SSR: เข้าหา amb + P×Rth แบบ first-order (P = Vdrop × I × duty)."""
    target = amb + SSR_VDROP * max(current_a, 0.0) * max(0.0, min(duty, 1.0)) * SSR_RTH.get(heatsink, 1.0)
    return target + (temp - target) * math.exp(-dt / SSR_TAU_S)
