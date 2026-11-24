# ค้นคว้า: อุปกรณ์นิวเมติกส์ และมอเตอร์ AC/DC สำหรับ PLC Trainer

ค้นเมื่อ 2026-11-18 · เป้าหมาย: หาว่าอุปกรณ์จริงทำงานอย่างไร ต่อกับ PLC ด้วย I/O อะไร และควรจำลองอะไรในโปรแกรม
(แหล่งส่วนใหญ่เป็นคู่มือผู้ผลิตและบล็อกของผู้ขาย — ตัวเลขเฉพาะรุ่นให้ถือเป็นค่าโดยประมาณ ข้อที่ไม่มีแหล่งอ้างอิงระบุว่า "ความรู้ทั่วไป")

## สิ่งที่โปรแกรมมีอยู่แล้ว

| กลุ่ม | อุปกรณ์ที่มี |
|---|---|
| นิวเมติกส์ | `cylinder`/`pusher` + วาล์ว 5/2 (โซลินอยด์เดียว/สองโซลินอยด์), `compressor`, `pressure_switch`, `pick_place` (หัวจับ) |
| มอเตอร์ | `motor`, `motor_rev` (DOL / Y-Δ / soft เป็นแค่ค่าสเปกกระแสกระชาก), `contactor`, `overload`, `vfd`, `servo` (แกนเชิงเส้น), `axis`, `encoder` |

---

## 1. นิวเมติกส์

### 1.1 วาล์ว 5/3 (สามตำแหน่ง) — ยังไม่มี ⭐ แนะนำ
- สองโซลินอยด์ + สปริงดันกลับกลาง: ตัดไฟทั้งคู่ → กลับตำแหน่งกลาง
- ตำแหน่งกลาง 3 แบบ:
  - **Closed center** — ปิดทุกพอร์ต ลูกสูบ **ค้างอยู่กับที่** (หยุดกลางช่วงชักได้) ไม่กินลม
  - **Exhaust center** — ระบายลมทั้งสองฝั่ง ลูกสูบ **ไหล/ดันด้วยมือได้**
  - **Pressure center** — จ่ายลมทั้งสองฝั่ง ลูกสูบ **ค้างกลางช่วงชักด้วยแรงดัน** (แรงสุทธิดันออกเพราะพื้นที่ฝั่งหัวใหญ่กว่า — ความรู้ทั่วไป)
- I/O: Y สองตัว (SOL-A ยืด, SOL-B หด) · ห้ามสั่งพร้อมกัน (ต้อง interlock ในโปรแกรม)
- คุณค่าการสอน: หยุดกระบอกกลางทาง, interlock สองโซลินอยด์, พฤติกรรมเมื่อไฟดับ/E-Stop ต่างกันตามชนิดกลาง
- แหล่ง: [Tameson – 5/3 center closed](https://tameson.com/products/mvsc-220-4e2c-dc24-g-g1-4inch-24vdc-5-3-way-center-closed-solenoid-valve-1p5-8bar), [Tameson – directional valves](https://tameson.co.uk/pages/directional-control-valve-applications), [McMaster – double-acting solenoid valves](https://www.mcmaster.com/products/double-acting-solenoid-valves), [Industrial Monitor Direct – center configurations](https://industrialmonitordirect.com/blogs/knowledgebase/three-position-solenoid-valve-center-position-configurations)

### 1.2 กระบอกสูบทางเดียว (single-acting, สปริงคืน) + วาล์ว 3/2 — ยังไม่มี
- ลมเข้าด้านเดียว สปริงดันกลับ ใช้วาล์ว 3/2 (ความรู้ทั่วไป) · ไฟ/ลมหาย → กลับตำแหน่งเดิมเสมอ
- I/O: Y หนึ่งตัว · ทำได้ง่ายโดยเพิ่มตัวเลือกใน `cylinder` แทนการสร้างชนิดใหม่

### 1.3 สวิตช์ตรวจตำแหน่งลูกสูบ (Reed / Auto switch)
- 2 สาย (reed หรือโซลิดสเตต) — **แรงดันตกคร่อมมากกว่า** แบบ 3 สาย, ต้องมีโหลดต่ออยู่เสมอ ไม่งั้นเสียทันที
- 3 สาย — NPN (sink) / PNP (source) ต้องเลือกให้ตรงกับขา S/S ของ PLC, ห้ามสลับสายไฟเลี้ยงกับเอาต์พุต
- ในโปรแกรม: `cylinder` มีสวิตช์ปลายทาง (X) อยู่แล้ว → เพิ่มได้คือ **ตำแหน่งสวิตช์ปรับได้ (เลื่อนบนตัวกระบอก)**, ชนิด 2/3 สาย, และ fault "สวิตช์เลื่อนหลุดตำแหน่ง"
- แหล่ง: [SMC auto switch manual](https://manualmachine.com/smcnetworks/da90/24188355-user-manual), [SMC MRHQ rotary gripper](https://ocpneumatics.com/content//cutsheets/MRHQ.pdf), [SMC auto switch catalog](https://www.ocpneumatics.com/content/smcdigitalcat3/docs/electric/erodless/8-01-3-AutoSW.pdf)

### 1.4 ระบบสุญญากาศ: Ejector + ถ้วยดูด + Vacuum switch — ยังไม่มี ⭐ แนะนำ
- Ejector สร้างสุญญากาศจากลมอัดด้วยหลัก venturi · มีแบบ NO/NC
- **Blow-off** เป่าลมเข้าวงจรสุญญากาศให้ปล่อยชิ้นงานได้เร็ว
- **Vacuum switch** ยืนยันว่าดูดติดแล้วก่อนให้ PLC สั่งยก (ตั้งราว 80% ของสุญญากาศปกติ — คำแนะนำผู้ขาย)
- ลำดับ PLC มาตรฐาน: ดูด ON → รอ vacuum switch → ยก/ย้าย → ดูด OFF + blow-off ON → รอสุญญากาศหมด → blow-off OFF
- I/O: Y ดูด, Y เป่า, X vacuum OK (บางรุ่นเป็นค่า analog ความดัน)
- Fault ที่สอนได้: ถ้วยรั่ว/ชิ้นงานพรุน (ไม่ถึงค่าตั้ง), ไส้กรองตัน
- แหล่ง: [Schmalz – ejectors with active blow-off](https://test-cdn-origin.schmalz.com/en/vacuum-technology-for-automation/vacuum-components/vacuum-generators/decentralized-ejectors/ejectors-with-active-blow-off-seac-307826), [Schmalz PGE](https://www.schmalz.com/en-at/category/PGE-03839), [Schmalz SCPMc manual](https://www.manualslib.com/manual/3154723/Schmalz-Scpmc.html?page=21), [Camozzi vacuum](https://issuu.com/camozzi/docs/vuoto_en/52), [Piab](https://www.airhydropower.com/piab), [SMC vacuum products](https://automationdistribution.com/smc-vacuum-products/)

### 1.5 อื่น ๆ (ความรู้ทั่วไป — ยังไม่ได้ค้นลึก)
- **Rotary actuator** (หมุน 90°/180°) — เหมือนกระบอกสูบแต่หมุน มีสวิตช์สองปลาย
- **Gripper ลม** (2/3 นิ้ว) — มีในแขน `pick_place` แล้ว แยกเป็นอุปกรณ์เดี่ยวได้
- **Flow control (one-way)** — ปรับความเร็วกระบอก = ตั้ง `stroke_s` อยู่แล้ว อาจทำเป็นปุ่มหมุนบนผัง
- **FRL / Air service unit** — กรอง ปรับ ความดัน หล่อลื่น; ใช้เป็นอุปกรณ์ปรับ `pressure_bar` ร่วมกัน

---

## 2. มอเตอร์ AC

### 2.1 สตาร์-เดลต้า (Y-Δ) เป็นวงจรจริง — ปัจจุบันเป็นแค่ค่าสเปก ⭐ แนะนำ
- คอนแทคเตอร์ 3 ตัว: Main (KM1), Star (KM2), Delta (KM3) · ห้าม Star กับ Delta ON พร้อมกัน (ลัดวงจร)
- ลำดับ: KM1+KM2 → ครบเวลา star (≥ ~1 s, ปรับตามโหลด) → ปลด KM2 → **เว้นช่วงตาย ~50 ms** → KM3
- ข้อควรรู้: ผู้ผลิตแนะนำให้ interlock ระหว่าง Star/Delta เป็นสายไฟจริงด้วย ไม่พึ่ง PLC อย่างเดียว
- ในโปรแกรม: มอเตอร์ชนิด `motor_yd` รับ Y 3 ตัว → กระแส/แรงบิดตามช่วง, ถ้า Star+Delta พร้อมกัน = "ลัดวงจร" (เบรกเกอร์ทริป), ไม่มีช่วงตาย = กระแสกระชาก
- แหล่ง: [ABB – star-delta timer](https://library.e.abb.com/public/01053359d394a130c1256e780058e485/2CDC111004D0201.pdf), [ABB UMC100.3](https://www.manualslib.com/manual/1426748/Abb-Umc100-3.html?page=80), [Schneider TeSys Tera – Star Delta](https://www.productinfo.schneider-electric.com/tesys_tera_ug/tesys-tera-motor-management-system-user-guide/EN/TeSys-Tera-User%20Guide-DOCA0257-01.xml/$/W2_TeSys_Tera_UG_StarDelta_0001013349), [Schneider FAQ](https://www.se.com/uk/en/faqs/FA24956), [InstrumentationTools – PLC star-delta](https://instrumentationtools.com/plc-program-for-star-delta-motor-starter), [ElectricalTechnology – automatic star-delta](https://www.electricaltechnology.org/?p=241), [PLCtalk – switchover problem](https://www.plctalk.net/threads/simocode-star-delta-switchover-problem.84347/), [IMD – hardwired preferred](https://industrialmonitordirect.com/blogs/knowledgebase/star-delta-starting-why-hardwired-control-is-preferred-over-plc)

### 2.2 มอเตอร์ 1 เฟส (capacitor start / capacitor run)
- กลับทางหมุนโดย **สลับปลายขดลวดสตาร์ท** (สลับสายไฟเข้าไม่ได้ผล, สลับขดรันไม่ได้ผล)
- มีสวิตช์แรงเหวี่ยงตัดขดสตาร์ทเมื่อรอบสูง → **ต้องหยุดสนิทก่อนกลับทาง** (ถ้ากลับตอนหมุนอยู่ มอเตอร์จะหมุนทางเดิมต่อ)
- มอเตอร์ shaded pole กลับทางไม่ได้
- ในโปรแกรม: เพิ่มใน `motor_rev` ตัวเลือก "1 เฟส" → สั่งกลับทางขณะรอบ > ~25% = ไม่กลับ (สอนให้ใส่ timer รอหยุด)
- แหล่ง: [MSU – single-phase motors](https://www.maec.msu.edu/download_file/view/153/303), [Maritime – single phase motor review](https://weh.maritime.edu/EN-3111/images/SinglePhaseMotorReview.pdf), [IMD – start winding method](https://industrialmonitordirect.com/blogs/knowledgebase/reversing-capacitor-start-motor-rotation-start-winding-method), [IMD – reversing methods](https://industrialmonitordirect.com/blogs/knowledgebase/reversing-single-phase-motor-direction-wiring-methods), [Eng-Tips](https://www.eng-tips.com/threads/reversing-a-single-phase-motor.59505)

### 2.3 มอเตอร์สองความเร็ว (Dahlander)
- เปลี่ยนจำนวนขั้วด้วยการต่อขดลวดใหม่: ช้า = Δ (คอนแทคเตอร์ 1 ตัว), เร็ว = YY (2 ตัว)
- กฎ: **เข้าเร็วได้ผ่านช้าเท่านั้น**, ห้ามช้า+เร็วพร้อมกัน
- ในโปรแกรม: `motor_2speed` รับ Y 2–3 ตัว แสดงรอบ 2 ระดับ, ผิดลำดับ = ทริป
- แหล่ง: [JIAEE – Dahlander S7-1200](https://jiaee.ppj.unp.ac.id/index.php/jiaee/article/download/80/76/300), [SolisPLC – Dahlander](https://www.solisplc.com/tutorials/how-to-control-a-dahlander-motor-with-an-electronic-starter), [IMD – Dahlander wiring](https://industrialmonitordirect.com/blogs/knowledgebase/dahlander-2-speed-3-phase-motor-wiring-and-control-circuit), [KNTU – Motor control](https://plc.ee.kntu.ac.ir/dorsapax/userfiles/file/Electrical/az-plc/Motor.pdf)

### 2.4 มอเตอร์มีเบรก / มอเตอร์เกียร์ (ความรู้ทั่วไป — แหล่งที่ค้นได้น้อย)
- เบรกแม่เหล็กไฟฟ้าแบบ fail-safe: **จ่ายไฟ = ปลดเบรก**, ไฟดับ = เบรกจับ
- ลำดับ: ปลดเบรกพร้อม/ก่อนเดินมอเตอร์, หยุด → จับเบรก · เหมาะกับลิฟต์/เครน (`axis` แบบ elevator)
- ในโปรแกรม: ตัวเลือก `brake` ใน `motor` + Y แยก → ลืมปลดเบรก = มอเตอร์ร้อน/OL ทริป, ไม่มีเบรก = ลิฟต์ไหลลง
- แหล่ง: [IMD – 2-speed crane motor](https://industrialmonitordirect.com/blogs/knowledgebase/2-speed-crane-motor-wiring-converting-to-low-speed-operation)

### 2.5 AC Servo (โหมดตำแหน่ง ด้วยพัลส์)
- PLC ส่งพัลส์ + ทิศทาง → ไดรฟ์ · สัญญาณกลับ: **Servo ready, INP (ถึงตำแหน่ง), Alarm** · PLC ส่ง **Servo ON, Alarm reset**
- ต้องตั้งไดรฟ์เป็นโหมดตำแหน่ง (PT) และโหมดพัลส์ให้ตรงกับ PLC
- Home return: วิ่งเร็วหา dog → คลานช้าเข้าจุด home; ชน limit แล้วกลับทาง
- ในโปรแกรม: `servo` ตอนนี้รับค่าตำแหน่งเป็น word → เพิ่มสัญญาณ SON/ALM/RST/INP และขั้นตอน home ได้
- แหล่ง: [Panasonic – pulse/direction](https://infohub.industry.panasonic.eu/data/motors/en/topics/t-0000036281.html), [Panasonic FP0H positioning](https://fs-ep-eu-p-industry-pim.wd.pisceu.panasonic.eu/storage/download-files/import/mn_fp0h_positioning_user_pid_en.pdf), [Panasonic FP7 wiring](https://www.manualslib.com/manual/1383830/Panasonic-Fp7.html?page=111), [JTEKT – external pulses](https://www.electronics.jtekt.co.jp/en/knowledge-base/servo-43), [Mitsubishi MR-J2 operation](https://Manualslib.com/manual/2769221/Mitsubishi-Electric-Melservo-J2-Series.html?page=77)

---

## 3. มอเตอร์ DC

### 3.1 Stepper + ไดรฟ์ (PUL/DIR/ENA) ⭐ แนะนำ
- PLC ต่อมอเตอร์ตรงไม่ได้ ต้องผ่านไดรฟ์ · สัญญาณ: PUL (พัลส์), DIR (ทิศ), ENA (ปลดแรงบิด)
- 1.8°/สเต็ป = 200 สเต็ป/รอบ × microstep (เช่น 1/16 → 3200 พัลส์/รอบ) ตั้งที่ DIP switch ของไดรฟ์
- ระวัง NPN/PNP ของอินพุตไดรฟ์ และความถี่พัลส์สูงสุด
- **สอนเรื่องสำคัญ:** stepper เป็น open-loop — โหลดเกิน/เร่งเร็วเกิน = **หลุดสเต็ป** ตำแหน่งเพี้ยนโดย PLC ไม่รู้ → ต้อง home ใหม่
- ในโปรแกรม: Mitsubishi ใช้คำสั่ง PLSY/DRVI ซึ่งทำงานกับ GX Simulator3 ได้ไม่ครบ → จำลองด้วย **word จำนวนพัลส์เป้าหมาย + bit สั่ง/ทิศ** แทนพัลส์จริง (ต้องทดสอบกับ sim ก่อน)
- แหล่ง: [IMD – FX5U to TB6600](https://industrialmonitordirect.com/blogs/knowledgebase/mitsubishi-fx5u-to-tb6600-stepper-driver-wiring-guide), [IMD – FX3U YKA2304](https://industrialmonitordirect.com/blogs/knowledgebase/yka2304-stepper-driver-to-mitsubishi-fx3u-wiring-and-programming), [IMD – FX5U PLSY DRVI](https://industrialmonitordirect.com/blogs/knowledgebase/mitsubishi-fx5u-plsy-drvi-stepper-motor-control-via-fx5-16etes-h), [IMD – FX3U pulse ladder](https://industrialmonitordirect.com/blogs/knowledgebase/mitsubishi-fx3u-stepper-motor-control-pulse-output-ladder-logic)

### 3.2 มอเตอร์ DC แปรงถ่าน (brushed)
- กลับทาง = สลับขั้วไฟ (รีเลย์ DPDT หรือ H-bridge) · ปรับรอบ = PWM หรือไดรฟ์ DC รับ 0–10 V
- มอเตอร์ใหญ่ใช้คอนแทคเตอร์ ไม่ใช้รีเลย์เล็ก
- ในโปรแกรม: `dc_motor` รับ Y เดินหน้า/ถอยหลัง (ON พร้อมกัน = ลัดวงจร) + word ความเร็ว 0–4000 (เหมือน D/A)
- แหล่ง: [IMD – Delta PLC DC motor analog](https://industrialmonitordirect.com/blogs/knowledgebase/delta-plc-dc-motor-control-with-ladder-logic-analog-speed), [IMD – Keyence PWM DC motor](https://industrialmonitordirect.com/blogs/knowledgebase/keyence-plc-pwm-control-for-dc-motor-speed-with-encoder-feedback), [IMD – PLC speed control methods](https://industrialmonitordirect.com/blogs/knowledgebase/plc-motor-speed-control-vfd-integration-and-analog-methods), [IMD – legacy DC drive](https://industrialmonitordirect.com/blogs/knowledgebase/controlling-legacy-dc-drive-with-siemens-s7-1500-plc)

### 3.3 BLDC + ไดรฟ์
- ไดรฟ์รับ: Enable, Direction (bit), Speed 0–5/0–10 V (analog) · กลับทางที่ไดรฟ์ ไม่ต้องสลับสาย
- เอาต์พุตไดรฟ์: พัลส์จาก Hall sensor ใช้นับรอบด้วย high-speed counter
- ในโปรแกรม: คล้าย `vfd` แต่เป็นมอเตอร์ DC ขนาดเล็ก (AGV/สายพานเล็ก) + พัลส์ป้อนกลับ → เหมาะทำด่าน PID ควบคุมรอบ
- แหล่ง: [IMD – Delta PLC BLDC PID AGV](https://industrialmonitordirect.com/blogs/knowledgebase/delta-plc-bldc-motor-speed-control-pid-for-line-following-agvs), [IMD – BLDC hall pulse capture](https://industrialmonitordirect.com/blogs/knowledgebase/durus-ic210ddr012-plc-counter-setup-for-bldc-motor-hall-sensor-pulse-capture)

---

## 4. ข้อเสนอลำดับการทำ (ถ้าจะเพิ่มเป็นอุปกรณ์ในโปรแกรม)

| ลำดับ | อุปกรณ์ | I/O | เหตุผล |
|---|---|---|---|
| 1 | วาล์ว 5/3 (3 ชนิดกลาง) ใน `cylinder` | Y×2, X×2 | ต่อยอดของเดิม, สอน interlock + หยุดกลางทาง |
| 2 | มอเตอร์ Y-Δ วงจรจริง `motor_yd` | Y×3 | หัวข้อคลาสสิกของ ปวช. ไฟฟ้ากำลัง, ทดสอบ black-box ได้ชัด (ห้าม Y+Δ พร้อมกัน, ช่วงตาย) |
| 3 | ชุดสุญญากาศ `vacuum` | Y×2, X×1 | งาน pick & place จริง, ลำดับรอยืนยัน |
| 4 | Stepper `stepper` | Y×2–3 + D | สอน open-loop / หลุดสเต็ป / home |
| 5 | DC motor / BLDC | Y×2 + D | กลับขั้ว + ควบคุมความเร็วด้วย analog |
| 6 | ตัวเลือกเสริม: 1 เฟสกลับทาง, Dahlander, เบรก, single-acting, AC servo signals | — | เพิ่มเป็นตัวเลือกในอุปกรณ์เดิม |

ด่านที่ทำต่อได้: "สตาร์-เดลต้า", "กระบอกสูบหยุดกลางทาง (5/3)", "ดูดยกชิ้นงานด้วยสุญญากาศ", "สเต็ปเปอร์ไปตำแหน่ง + home"

## 5. ช่องว่างที่ยังไม่ได้ข้อมูล
- รายวิชาหลักสูตร ปวช. ปัจจุบัน (2562/2567) ที่ตรงกับนิวเมติกส์ไฟฟ้า — ค้นไม่เจอเอกสารทางการ เจอแค่วิชา "การควบคุมมอเตอร์ไฟฟ้า (2104-2009)" ของหลักสูตร 2556 ([คู่มือ อศ.](https://docs.google.com/document/d/1Tlf1pCM6VCFQSlJpJiQYyK8WaBnj8Y_B/export?format=pdf)) → ถ้าครูมีคำอธิบายรายวิชา จะช่วยเลือกอุปกรณ์ได้ตรงขึ้น
- ค่ากระแส/แรงบิดช่วง Star จริงเทียบ DOL, เวลาตอบสนองของเบรก — ใช้ค่าตำราทั่วไป (กระแสสตาร์ทช่วง Y ≈ 1/3 ของ DOL)
- คำสั่งพัลส์ (PLSY/DRVI) บน GX Simulator3 รุ่น iQ-R ทำงานแค่ไหน — ต้องทดลองจริง
