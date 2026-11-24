"""สร้างผังตัวอย่าง (ฉากโรงงานสำเร็จรูป) ใน panels/ — รันซ้ำได้ เขียนทับเฉพาะไฟล์ตัวอย่างเหล่านี้

  .venv\\Scripts\\python tools\\make_example_panels.py                     (ทุกไฟล์)
  .venv\\Scripts\\python tools\\make_example_panels.py 07_traffic.plcpanel (เฉพาะไฟล์ที่ระบุ)
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plc_game.panel import DeviceSpec as D, PanelDoc  # noqa: E402


def task(x, y, text, width=300):
    """กล่องโจทย์ + ตาราง I/O (สีเหลืองอ่อน)."""
    return D.new("note", x, y, text=text, width=width, size=9, color="yellow")


PANELS = {
    # ---------------- ผังเดิม (เพิ่มคำอธิบายโจทย์) ----------------
    "cylinder_AplusBplus.plcpanel": PanelDoc("ลำดับกระบอกสูบ A+ B+ A− B−", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 100, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("lamp", 220, 0, label="RUN", address="M0", color="green"),
        D.new("cylinder", 60, 160, label="กระบอกสูบ A", address="Y0", addr_ret="X2", addr_ext="X3", stroke_s=1.0),
        D.new("cylinder", 60, 300, label="กระบอกสูบ B", address="Y1", addr_ret="X4", addr_ext="X5", stroke_s=1.0),
        task(480, 150, "โจทย์: กด Start → A ยื่น (A+) → B ยื่น (B+) → A หด (A−) → B หด (B−) แล้วจบรอบ\n"
                       "ใช้รีดสวิตช์ a0 / a1 ยืนยันตำแหน่งก่อนขั้นถัดไป\n\n"
                       "X0 Start · X1 Stop\nX2 a0 / X3 a1 (กระบอก A)\nX4 b0 / X5 b1 (กระบอก B)\n"
                       "Y0 โซลินอยด์ A · Y1 โซลินอยด์ B"),
    ]),
    "tank.plcpanel": PanelDoc("ควบคุมระดับน้ำในถัง", [
        D.new("selector", 0, 0, label="Auto", address="X0", key="1"),
        D.new("estop", 100, 0, label="E-Stop", address="X1", key="2"),
        D.new("overload", 200, 0, label="OL ปั๊ม", address="X2", addr_motor="Y0", trip_s=0, key="3"),
        D.new("tank", 120, 200, label="ถังน้ำ", address="Y0", addr_drain="Y1", addr_high="X3", addr_low="X4",
              level0=30, fill_rate=12, drain_rate=6),
        D.new("lamp", 320, 120, label="ปั๊มทำงาน", address="Y0", color="green"),
        D.new("lamp", 320, 240, label="น้ำต่ำ (เตือน)", address="Y2", color="orange"),
        D.new("buzzer", 320, 360, label="ออดเตือน", address="Y3"),
        task(600, 160, "โจทย์: โหมด Auto → น้ำต่ำกว่า Low ให้ปั๊มเติมจนถึง High แล้วหยุด\n"
                       "E-Stop หรือ OL ทริป = หยุดปั๊มทันที + ออดเตือน\n\n"
                       "X0 Auto · X1 E-Stop (NC) · X2 OL (NC)\nX3 ระดับสูง · X4 ระดับต่ำ\n"
                       "Y0 ปั๊ม · Y1 วาล์วปล่อย · Y2 ไฟเตือน · Y3 ออด"),
    ]),
    "star_delta.plcpanel": PanelDoc("สตาร์-เดลต้า (Star-Delta)", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 100, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("overload", 200, 0, label="OL1", address="X2", addr_motor="Y0", trip_s=0, key="3"),
        D.new("contactor", 0, 180, label="K1 Main", address="Y0", addr_aux="X3"),
        D.new("contactor", 100, 180, label="K2 Star", address="Y1"),
        D.new("contactor", 200, 180, label="K3 Delta", address="Y2"),
        D.new("motor", 340, 180, label="มอเตอร์ 3 เฟส", address="Y0"),
        D.new("display", 100, 330, label="Timer T0", address="TN0", unit="×100ms"),
        D.new("lamp", 260, 330, label="Y (สตาร์)", address="Y1", color="yellow"),
        D.new("lamp", 360, 330, label="Δ (เดลต้า)", address="Y2", color="green"),
        task(620, 170, "โจทย์: Start → K1 + K2 (สตาร์) 5 วินาที → ปลด K2 → ต่อ K3 (เดลต้า)\n"
                       "ห้าม K2 กับ K3 ติดพร้อมกัน (Interlock) · Stop หรือ OL ทริป = ปลดทุกตัว\n\n"
                       "X0 Start · X1 Stop · X2 OL (NC) · X3 aux K1\nY0 K1 Main · Y1 K2 Star · Y2 K3 Delta"),
    ]),
    "traffic.plcpanel": PanelDoc("ไฟจราจร + ปุ่มคนข้าม", [
        D.new("traffic", 0, 60, label="ไฟรถ", address="Y0", addr_yellow="Y1", addr_green="Y2"),
        D.new("lamp", 120, 20, label="คนข้าม: หยุด", address="Y3", color="red"),
        D.new("lamp", 120, 130, label="คนข้าม: เดิน", address="Y4", color="green"),
        D.new("pushbutton", 260, 20, label="ปุ่มขอข้าม", address="X0", color="yellow", key="1"),
        D.new("sevenseg", 300, 150, label="นับถอยหลัง (D0)", address="D0", digits=2),
        D.new("setvalue", 300, 270, label="เวลาไฟเขียว (D10, วินาที)", address="D10", value=10, min=1, max=99),
        task(620, 120, "โจทย์: ไฟรถเขียวค้าง · กดปุ่มขอข้าม → เหลือง 3 วิ → แดง แล้วไฟคนข้ามเขียว\n"
                       "ตามเวลาใน D10 พร้อมนับถอยหลังที่ D0 → กลับเป็นไฟรถเขียว\n\n"
                       "X0 ปุ่มขอข้าม · D10 เวลา (วินาที) · D0 นับถอยหลัง\n"
                       "Y0 แดง · Y1 เหลือง · Y2 เขียว (รถ)\nY3 หยุด · Y4 เดิน (คนข้าม)"),
    ]),

    # ---------------- ฉากโรงงานใหม่ ----------------
    "sorting.plcpanel": PanelDoc("คัดแยกโลหะ / พลาสติก", [
        D.new("zone", 260, 215, label="สถานีคัดแยก", w=640, h=330, color="blue"),
        D.new("pushbutton", 0, -60, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, -60, label="Stop", address="X1", color="red", key="2"),
        D.new("tower", 500, -40, label="สถานะ", address="Y3", addr_yellow="Y4", addr_green="Y5"),
        D.new("sensor", 60, 120, label="PS ชิ้นงานเข้า", address="X2", sense="photo"),
        D.new("sensor", 320, 160, label="IND โลหะ", address="X3", sense="inductive"),
        D.new("pusher", 410, 140, label="ตัวดันโลหะ", address="Y1", addr_ret="X4", addr_ext="X5"),
        D.new("conveyor", 260, 220, label="สายพาน", address="Y0", length=520, part_mode="random"),
        D.new("sevenseg", 120, 450, label="โลหะ (D0)", address="D0", digits=3),
        D.new("sevenseg", 380, 450, label="ทั้งหมด (D1)", address="D1", digits=3),
        task(820, 140, "โจทย์: Start → สายพานเดิน (ไฟเขียว)\n"
                       "เซนเซอร์ IND เห็นชิ้นงานโลหะ → ตัวดันดันลงถาด แล้วนับใน D0\n"
                       "ชิ้นพลาสติกปล่อยผ่านไป · นับชิ้นงานทั้งหมดที่ผ่าน PS ใน D1\n"
                       "Stop → สายพานหยุด (ไฟเหลือง)\n\n"
                       "X0 Start · X1 Stop\nX2 Photo (เห็นทุกชิ้น) · X3 Inductive (โลหะ)\n"
                       "X4 ตัวดันหด (a0) · X5 ตัวดันยื่น (a1)\n"
                       "Y0 สายพาน · Y1 ตัวดัน\nY3 แดง · Y4 เหลือง · Y5 เขียว\n\n"
                       "คลิก '+ ชิ้นงาน' ซ้ายสายพานเพื่อปล่อยชิ้นงาน", width=320),
    ]),
    "elevator3.plcpanel": PanelDoc("ลิฟต์ 3 ชั้น", [
        D.new("axis", 0, 120, label="ลิฟต์", address="Y0", addr_rev="Y1", addr_p1="X0", addr_p2="X1",
              addr_p3="X2", style="elevator", travel_s=6.0),
        D.new("pushbutton", 160, 0, label="เรียกชั้น 3", address="X5", color="yellow", key="3"),
        D.new("pushbutton", 160, 120, label="เรียกชั้น 2", address="X4", color="yellow", key="2"),
        D.new("pushbutton", 160, 240, label="เรียกชั้น 1", address="X3", color="yellow", key="1"),
        D.new("sevenseg", 320, 0, label="ชั้นปัจจุบัน (D0)", address="D0", digits=1),
        D.new("lamp", 300, 140, label="ขึ้น", address="Y0", color="green"),
        D.new("lamp", 380, 140, label="ลง", address="Y1", color="orange"),
        D.new("lamp", 340, 260, label="ประตูเปิด", address="Y2", color="yellow"),
        task(640, 120, "โจทย์: กดเรียกชั้นไหน ลิฟต์ไปจอดชั้นนั้น (ขึ้น = Y0, ลง = Y1)\n"
                       "ห้ามสั่งขึ้นและลงพร้อมกัน · ถึงชั้นแล้วเปิดประตู (Y2) 3 วินาที\n"
                       "แสดงเลขชั้นที่ D0\n\n"
                       "X0 ชั้น 1 · X1 ชั้น 2 · X2 ชั้น 3 (เซนเซอร์ตำแหน่ง)\n"
                       "X3 / X4 / X5 ปุ่มเรียกชั้น 1 / 2 / 3\n"
                       "Y0 ขึ้น · Y1 ลง · Y2 ประตูเปิด · D0 เลขชั้น"),
    ]),
    "garage_door.plcpanel": PanelDoc("ประตูม้วนโรงรถ", [
        D.new("axis", 180, 100, label="ประตูม้วน", address="Y0", addr_rev="Y1", addr_p1="X0", addr_p3="X1",
              style="door", travel_s=5.0),
        D.new("pushbutton", 0, 0, label="เปิด", address="X2", color="green", key="1"),
        D.new("pushbutton", 0, 120, label="ปิด", address="X3", color="yellow", key="2"),
        D.new("pushbutton", 0, 240, label="หยุด", address="X4", color="red", key="3"),
        D.new("sensor", 180, 300, label="กันหนีบ", address="X5", sense="photo"),
        D.new("lamp", 380, 40, label="ไฟเตือน", address="Y2", color="orange"),
        D.new("buzzer", 380, 160, label="ออด", address="Y3"),
        task(660, 140, "โจทย์: กดเปิด → ประตูขึ้นจนถึงลิมิตบน · กดปิด → ประตูลงจนถึงลิมิตล่าง\n"
                       "ระหว่างเคลื่อนที่ไฟเตือนกระพริบ · กดหยุดได้ทุกเมื่อ\n"
                       "ขณะปิดถ้าเซนเซอร์กันหนีบเห็นสิ่งกีดขวาง → หยุดแล้วเปิดขึ้นทันที + ออดดัง\n\n"
                       "X0 ลิมิตล่าง (ปิดสุด) · X1 ลิมิตบน (เปิดสุด)\n"
                       "X2 เปิด · X3 ปิด · X4 หยุด · X5 กันหนีบ\n"
                       "Y0 มอเตอร์ขึ้น · Y1 มอเตอร์ลง · Y2 ไฟเตือน · Y3 ออด\n\n"
                       "คลิกเซนเซอร์กันหนีบเพื่อจำลองว่ามีรถขวาง"),
    ]),
    "mixing.plcpanel": PanelDoc("ถังผสมสาร + ให้ความร้อน", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("tank", 60, 220, label="ถังผสม", address="Y0", addr_drain="Y1", addr_high="X2", addr_low="X3",
              level0=10, fill_rate=15, drain_rate=12),
        D.new("motor", 260, 120, label="มอเตอร์กวน", address="Y2"),
        D.new("oven", 270, 300, label="ฮีตเตอร์", address="Y3", addr_temp="D30", ambient=25, heat_c=120, tau_s=15),
        D.new("gauge", 450, 300, label="อุณหภูมิ (D30)", address="D30", style="needle", min=0, max=150, unit="°C"),
        D.new("message", 420, 120, label="ขั้นตอน (D1)", address="D1",
              messages="0=พร้อม;1=เติมสาร;2=กวน+ให้ความร้อน;3=ปล่อยออก;4=เสร็จ"),
        task(760, 180, "โจทย์: Start → เติมสาร (Y0) จนถึงระดับสูง → กวน (Y2) + ให้ความร้อน (Y3)\n"
                       "จนอุณหภูมิ D30 ≥ 60 °C แล้วกวนต่ออีก 5 วินาที → ปล่อยออก (Y1) จนถึงระดับต่ำ\n"
                       "แสดงขั้นตอนปัจจุบันลง D1 (0–4)\n\n"
                       "X0 Start · X1 Stop · X2 ระดับสูง · X3 ระดับต่ำ\n"
                       "Y0 ปั๊มเติม · Y1 วาล์วปล่อย · Y2 มอเตอร์กวน · Y3 ฮีตเตอร์\n"
                       "D30 อุณหภูมิ (°C) · D1 ขั้นตอน"),
    ]),
    "parking.plcpanel": PanelDoc("ลานจอดรถ", [
        D.new("sensor", 0, 0, label="รถเข้า", address="X0", sense="photo"),
        D.new("sensor", 140, 0, label="รถออก", address="X1", sense="photo"),
        D.new("pushbutton", 300, 30, label="รีเซ็ต", address="X2", color="yellow", key="3"),
        D.new("setvalue", 0, 200, label="จำนวนช่องจอด (D10)", address="D10", value=10, min=1, max=99),
        D.new("sevenseg", 200, 200, label="ช่องว่าง (D0)", address="D0", digits=2),
        D.new("lamp", 360, 180, label="ว่าง", address="Y0", color="green"),
        D.new("lamp", 360, 280, label="เต็ม", address="Y1", color="red"),
        task(760, 130, "โจทย์: รถเข้า 1 คัน → ช่องว่างลด 1 · รถออก 1 คัน → ช่องว่างเพิ่ม 1\n"
                       "ช่องว่าง = 0 → ไฟเต็ม (Y1) · ยังมีที่ → ไฟว่าง (Y0)\n"
                       "ปุ่มรีเซ็ต → ช่องว่าง = ค่าใน D10\n\n"
                       "X0 เซนเซอร์รถเข้า · X1 เซนเซอร์รถออก · X2 รีเซ็ต\n"
                       "D10 จำนวนช่องจอด · D0 ช่องว่าง\nY0 ว่าง · Y1 เต็ม\n\n"
                       "คลิกที่เซนเซอร์ = รถผ่าน 1 คัน"),
    ]),
    "reversing.plcpanel": PanelDoc("มอเตอร์กลับทางหมุน + Interlock", [
        D.new("pushbutton", 0, 0, label="FWD", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="REV", address="X1", color="yellow", key="2"),
        D.new("pushbutton", 220, 0, label="Stop", address="X2", color="red", key="3"),
        D.new("overload", 330, 0, label="OL1", address="X3", addr_motor="Y0", trip_s=0, key="4"),
        D.new("motor_rev", 120, 200, label="มอเตอร์", address="Y0", addr_rev="Y1"),
        D.new("lamp", 300, 180, label="หมุนหน้า", address="Y0", color="green"),
        D.new("lamp", 300, 290, label="หมุนกลับ", address="Y1", color="orange"),
        task(640, 130, "โจทย์: กด FWD → หมุนหน้าค้าง · กด REV → หมุนกลับค้าง · Stop = หยุด\n"
                       "ห้าม Y0 กับ Y1 ON พร้อมกันเด็ดขาด (Interlock) — ถ้าพร้อมกันจะขึ้น 'ลัดวงจร!'\n"
                       "จะเปลี่ยนทิศต้องกด Stop ก่อน · OL ทริป = หยุดทันที\n\n"
                       "X0 FWD · X1 REV · X2 Stop · X3 OL (NC)\nY0 หมุนหน้า · Y1 หมุนกลับ"),
    ]),
    "vfd_conveyor.plcpanel": PanelDoc("สายพานปรับความเร็วด้วย VFD", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("pot", 240, 0, label="ปรับความเร็ว (D20)", address="D20", value=2000, max=4000),
        D.new("vfd", 0, 180, label="INV1", address="Y0", addr_freq="D0", addr_atspeed="X2", ramp_s=3.0, max_hz=60),
        D.new("gauge", 400, 0, label="ความถี่สั่ง (D0)", address="D0", style="bar", min=0, max=600, unit="Hz×10"),
        D.new("sensor", 360, 260, label="PS ปลายสาย", address="X3", sense="photo"),
        D.new("conveyor", 260, 360, label="สายพาน", address="Y0", length=440, addr_hz="D0", part_mode="random"),
        D.new("sevenseg", 520, 180, label="นับชิ้นงาน (C0)", address="CN0", digits=3),
        task(820, 180, "โจทย์: หมุนปุ่มปรับความเร็ว (0–4000 ที่ D20) แล้วแปลงเป็นความถี่ D0 = 0–600\n"
                       "(D0 = D20 × 600 / 4000 → 60.0 Hz) · Start → VFD เดิน (Y0) สายพานวิ่งตามความถี่\n"
                       "นับชิ้นงานที่ผ่านเซนเซอร์ปลายสายด้วย C0\n\n"
                       "X0 Start · X1 Stop · X2 ถึงความเร็ว (SU) · X3 เซนเซอร์ปลายสาย\n"
                       "D20 ค่าจากปุ่มหมุน · D0 ความถี่สั่ง (Hz×10)\nY0 VFD เดิน (STF)"),
    ]),
}


def _pick_place_scene() -> PanelDoc:
    """สายพานป้อนชิ้นงานไปปลายสาย → แขนหยิบ-วาง 2 แกน หยิบไปวางถาด (โจทย์ลำดับขั้น)."""
    ax, ay = 420, 120                     # ตำแหน่งแขน: จุดหยิบอยู่ที่ x = ax − 90
    return PanelDoc("แขนหยิบ-วาง + สายพาน", [
        D.new("pushbutton", 0, -120, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, -120, label="Stop", address="X1", color="red", key="2"),
        D.new("tower", 620, -100, label="สถานะ", address="Y5", addr_yellow="Y6", addr_green="Y7"),
        D.new("conveyor", ax - 270, ay + 70, label="สายพานป้อน", address="Y0", length=400, part_mode="random"),
        D.new("sensor", ax - 95, ay - 10, label="PS ถึงจุดหยิบ", address="X2", sense="photo", range_mm=60),
        D.new("pick_place", ax, ay, label="แขนหยิบ", address="Y1", addr_right="Y2", addr_grip="Y3",
              addr_up="X3", addr_down="X4", addr_left="X5", addr_rightlim="X6", addr_gripped="X7",
              feed="conveyor"),
        D.new("sevenseg", 620, 120, label="วางแล้ว (C0)", address="CN0", digits=3),
        task(900, 60, "โจทย์: Start → สายพานเดินจนชิ้นงานถึงจุดหยิบ (X2) แล้วหยุดสายพาน\n"
                      "แขน: Z ลง → หนีบ (รอ 0.3 s) → Z ขึ้น → X ไปขวา → Z ลง → ปล่อย → Z ขึ้น → X กลับ\n"
                      "แล้วเดินสายพานรับชิ้นต่อไป · นับชิ้นที่วางด้วย C0\n"
                      "⚠ ห้ามเลื่อนแกน X ขณะแกน Z ยังไม่ขึ้นสุด (X3) — จะชน!\n\n"
                      "X0 Start · X1 Stop · X2 ชิ้นงานถึงจุดหยิบ\n"
                      "X3 Z บนสุด · X4 Z ล่างสุด · X5 X ต้นทาง · X6 X ปลายทาง · X7 จับแล้ว\n"
                      "Y0 สายพาน · Y1 Z ลง · Y2 X ไปขวา · Y3 หัวจับ\nY5 แดง · Y6 เหลือง · Y7 เขียว", width=360),
    ])


def _air_scene() -> PanelDoc:
    """ระบบลม: ปั๊มลม + สวิตช์ความดัน + กระบอกสูบที่กินลมจริง."""
    comp = D.new("compressor", 0, 160, label="ปั๊มลม", address="Y0", addr_bar="D0", lpm=200, tank_l=10)
    return PanelDoc("ระบบลม: ปั๊มลม + สวิตช์ความดัน", [
        D.new("selector", 0, -40, label="Auto", address="X0", key="1"),
        D.new("pushbutton", 110, -40, label="ยื่น/หด", address="X1", color="yellow", key="2"),
        comp,
        D.new("pressure_switch", 160, 160, label="PS ลม 6 bar", address="X2", set_bar=6.0, diff_bar=1.0,
              link_air=comp.id),
        D.new("cylinder", 430, 160, label="กระบอกสูบ A", address="Y1", addr_ret="X3", addr_ext="X4",
              timing="spec", bore_mm=40, stroke_mm=150, pressure_bar=6.0, load_kg=5.0, link_air=comp.id),
        D.new("lamp", 260, -40, label="ลมพร้อม", address="Y2", color="green"),
        D.new("gauge", 360, -40, label="ความดัน (D0 = bar×10)", address="D0", style="needle", min=0, max=100,
              unit="bar×10"),
        task(720, 60, "โจทย์: โหมด Auto (X0) → ปั๊มลม (Y0) เดินเมื่อสวิตช์ความดัน (X2) OFF และหยุดเมื่อ ON\n"
                      "(สวิตช์มี hysteresis: ON ที่ 6 bar, OFF ที่ 5 bar ปั๊มจึงไม่เปิด-ปิดถี่)\n"
                      "ไฟลมพร้อม (Y2) ติดเมื่อ X2 ON · กดปุ่ม X1 → กระบอกสูบยื่น/หด\n"
                      "สังเกต: ทุกครั้งที่กระบอกสูบชัก ความดันลดลง · ถ้าลมต่ำกว่า 2 bar จะไม่ขยับ\n\n"
                      "X0 Auto · X1 ปุ่มยื่น/หด · X2 สวิตช์ความดัน · X3 a0 · X4 a1\n"
                      "Y0 ปั๊มลม · Y1 โซลินอยด์ · Y2 ไฟลมพร้อม · D0 ความดัน (bar×10)", width=360),
    ])


PANELS["pick_place.plcpanel"] = _pick_place_scene()
PANELS["air_system.plcpanel"] = _air_scene()

# ผังเฉพาะของด่าน (เก็บใน levels/) — ด่านอื่นใช้ผังใน panels/ ร่วมกับฉากตัวอย่าง
LEVEL_PANELS = {
    "01_self_hold.plcpanel": PanelDoc("ด่าน 1: วงจรคงสถานะ", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("motor", 260, 0, label="มอเตอร์", address="Y0"),
        D.new("lamp", 380, 0, label="RUN", address="Y0", color="green"),
        task(160, 190, "โจทย์: กด Start (X0) → มอเตอร์ (Y0) ทำงานค้างแม้ปล่อยปุ่ม\n"
                       "กด Stop (X1) → มอเตอร์หยุด · ถ้ากด Start กับ Stop พร้อมกัน ต้องหยุด (Stop มาก่อน)\n\n"
                       "X0 Start · X1 Stop (NO)\nY0 มอเตอร์ + ไฟ RUN", width=420),
    ]),
    "03_timer.plcpanel": PanelDoc("ด่าน 3: หน่วงเวลาสตาร์ทมอเตอร์", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("motor", 260, 0, label="ปั๊มน้ำมัน", address="Y0"),
        D.new("motor", 380, 0, label="มอเตอร์หลัก", address="Y1"),
        D.new("display", 320, 150, label="Timer T0", address="TN0", unit="×100ms"),
        task(40, 170, "โจทย์: กด Start → ปั๊มน้ำมันหล่อลื่น (Y0) ทำงานทันที\n"
                      "ครบ 3 วินาที → มอเตอร์หลัก (Y1) ทำงาน\nกด Stop → หยุดทั้งคู่\n\n"
                      "X0 Start · X1 Stop\nY0 ปั๊มน้ำมัน · Y1 มอเตอร์หลัก", width=300),
    ]),
    "14_fault_find.plcpanel": PanelDoc("ด่าน 14: หาจุดเสีย", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("motor", 260, 0, label="ปั๊มน้ำมัน", address="Y0"),
        D.new("motor", 380, 0, label="มอเตอร์หลัก", address="Y1"),
        D.new("lamp", 270, 150, label="ไฟปั๊ม", address="Y0", color="green"),
        D.new("lamp", 390, 150, label="ไฟมอเตอร์หลัก", address="Y1", color="green"),
        D.new("display", 520, 20, label="Timer T0", address="TN0", unit="×100ms"),
        task(40, 280, "โจทย์: เครื่องนี้มีอุปกรณ์เสีย 1 จุด (ซ่อนอยู่)\n"
                      "กด Start / Stop แล้วสังเกตมอเตอร์ ไฟ และตาราง I/O\n"
                      "คลิกขวาอุปกรณ์ที่คิดว่าเสีย → เลือกอาการ\n\n"
                      "X0 Start · X1 Stop · Y0 ปั๊ม+ไฟปั๊ม · Y1 มอเตอร์หลัก+ไฟ (หลัง 3 วินาที)",
             width=420),
    ]),
    "04_counter.plcpanel": PanelDoc("ด่าน 4: นับชิ้นงาน", [
        D.new("pushbutton", 0, 0, label="Start", address="X0", color="green", key="1"),
        D.new("pushbutton", 110, 0, label="Stop", address="X1", color="red", key="2"),
        D.new("pushbutton", 220, 0, label="Reset", address="X3", color="yellow", key="3"),
        D.new("sensor", 140, 120, label="PS นับชิ้น", address="X2", sense="photo"),
        D.new("conveyor", 180, 220, label="สายพาน", address="Y0", length=400, part_mode="random"),
        D.new("lamp", 480, 100, label="ครบ 5 ชิ้น", address="Y2", color="orange"),
        D.new("sevenseg", 480, 240, label="จำนวน (C0)", address="CN0", digits=2),
        task(760, 140, "โจทย์: Start → สายพาน (Y0) เดิน · Stop → หยุด\n"
                       "นับชิ้นงานที่ผ่านเซนเซอร์ X2 ครบ 5 ชิ้น → ไฟครบ (Y2) ติด\n"
                       "กด Reset (X3) → เริ่มนับใหม่ ไฟดับ\n\n"
                       "X0 Start · X1 Stop · X2 เซนเซอร์ · X3 Reset\nY0 สายพาน · Y2 ไฟครบ 5 ชิ้น", width=320),
    ]),
}


def _variant(src: str, title: str, task_text: str | None = None, **by_label) -> PanelDoc:
    """ผังของด่าน = สำเนาฉากตัวอย่าง + ปรับค่าบางชิ้น (by_label = {ชื่อป้าย: {prop: ค่า}}) ให้ตรวจเสร็จเร็ว."""
    doc = copy.deepcopy(PANELS[src])
    doc.name = title
    for d in doc.devices:
        d.props.update(by_label.get(d.props.get("label", ""), {}))
        if task_text is not None and d.kind == "note":
            d.props["text"] = task_text
    return doc


LEVEL_PANELS.update({
    "07_traffic.plcpanel": _variant("traffic.plcpanel", "ด่าน 7: ไฟจราจร + ปุ่มคนข้าม",
                                    **{"เวลาไฟเขียว (D10, วินาที)": {"value": 5, "label": "เวลาคนข้าม (D10, วินาที)"}}),
    "08_garage.plcpanel": _variant("garage_door.plcpanel", "ด่าน 8: ประตูม้วนโรงรถ",
                                   **{"ประตูม้วน": {"travel_s": 3.0}}),
    "09_elevator.plcpanel": _variant("elevator3.plcpanel", "ด่าน 9: ลิฟต์ 3 ชั้น", **{"ลิฟต์": {"travel_s": 3.0}}),
    "10_mixing.plcpanel": _variant("mixing.plcpanel", "ด่าน 10: ถังผสมสาร",
                                   **{"ถังผสม": {"fill_rate": 25, "drain_rate": 25},
                                      "ฮีตเตอร์": {"tau_s": 8}}),
    "11_oven.plcpanel": PanelDoc("ด่าน 11: เตาอบคุมอุณหภูมิ (Hysteresis)", [
        D.new("selector", 0, 0, label="Auto", address="X0", key="1"),
        D.new("oven", 200, 40, label="เตาอบ", address="Y0", addr_temp="D0", ambient=120, heat_c=300, tau_s=15),
        D.new("gauge", 400, 40, label="อุณหภูมิ (D0)", address="D0", style="needle", min=100, max=250, unit="°C"),
        D.new("lamp", 0, 150, label="ฮีตเตอร์ทำงาน", address="Y0", color="orange"),
        task(700, 60, "โจทย์: เปิด Auto (X0) → คุมอุณหภูมิเตา (D0) ให้อยู่ระหว่าง 180–200 °C\n"
                      "ฮีตเตอร์ (Y0) เปิดเมื่อ D0 ≤ 180 และปิดเมื่อ D0 ≥ 200 (Hysteresis)\n"
                      "ช่วงระหว่าง 180–200 ต้องคงสถานะเดิมไว้ — ห้ามเปิด-ปิดถี่\n"
                      "ปิด Auto → ฮีตเตอร์ดับทันที\n\n"
                      "X0 Auto · D0 อุณหภูมิ (°C) · Y0 ฮีตเตอร์\n"
                      "เตาอุ่นไว้ที่ 120 °C แล้ว", width=340),
    ]),
    "12_parking.plcpanel": _variant("parking.plcpanel", "ด่าน 12: ลานจอดรถ",
                                    **{"จำนวนช่องจอด (D10)": {"value": 3}}),
    "13_vfd.plcpanel": _variant("vfd_conveyor.plcpanel", "ด่าน 13: สายพานปรับความเร็วด้วย VFD"),
})


def main(only: list[str] | None = None):
    """only = รายชื่อไฟล์ที่ต้องการสร้าง (ไม่ระบุ = ทุกไฟล์ — ระวังทับผังที่แก้ไว้เอง)."""
    for folder, panels in ((ROOT / "panels", PANELS), (ROOT / "levels", LEVEL_PANELS)):
        folder.mkdir(exist_ok=True)
        for name, doc in panels.items():
            if only and name not in only:
                continue
            doc.save(folder / name)
            print("saved", folder.name + "/" + name, len(doc.devices), "devices")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
