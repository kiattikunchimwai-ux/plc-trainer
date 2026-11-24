# บันทึกการเปลี่ยนแปลง / Changelog

<!--
รูปแบบ (tools/make_release.py อ่านส่วนของเวอร์ชันใน plc_game/__init__.py):
## <เวอร์ชัน> — <ปี ค.ศ.-เดือน-วัน>
### th
- ข้อแรกจะใช้เป็นข้อความสั้นในหน้า About (ปุ่มเช็กเวอร์ชัน)
### en
- First bullet is the short note shown in the About dialog
-->

## 1.0.1 — 2026-11-24
### th
- เขียน ladder ในโปรแกรมได้เลย (แท็บ Ladder) แล้วรันด้วย PLC ในตัว ดูสถานะสด และตรวจด่านได้โดยไม่ต้องมี GX Works3
- ตรวจ ladder ก่อนส่งลง PLC: บอก rung ที่ผิด ช่องที่ยังไม่ได้กรอก และคำสั่งที่ยังไม่รองรับ
- บันทึก ladder อัตโนมัติแยกตามนักเรียนและด่าน, นำเข้า/ส่งออก CSV ของ GX Works3 (ลองนำเข้าไฟล์ส่งออกกับ GX Works3 จริงแล้ว: R04, FX5U)
- AI อ่าน ladder จากไฟล์ CSV ของ GX Works3 แล้วชี้ step ที่น่าจะผิด (ไม่มีผลต่อคะแนน ปิดอัตโนมัติตอนสอบ)
- ตัวตรวจด่าน: รอ PLC เห็น input จริงก่อนตัดสิน, ยกเลิกเมื่อข้อมูลขาดช่วง, โปรแกรมเปล่าไม่ได้ดาว, ล็อกการกดระหว่างตรวจ
- เตือนสัญญาณอันตราย (เช่น หมุนหน้า-กลับพร้อมกัน) แม้ผ่านทุกข้อ
- ผู้ใช้รุ่นเก่าได้ด่านที่แก้แล้วอัตโนมัติ ส่วนด่าน/ผังที่แก้เองจะไม่ถูกทับ
- ตารางคะแนน, Excel และสรุปผลสอบบอกว่าตรวจกับ PLC ไหน (ดาวที่ได้จาก Mock PLC เท่านั้นมีเครื่องหมาย; ดาวไม่เปลี่ยน)
- ladder: เพิ่มคำสั่ง BCD/BIN และ 32 บิต (DMOV, DINC, DDEC, D+ D- D* D/, DBCD, DBIN, เปรียบเทียบ LDD= ฯลฯ) และกลุ่มบิต K4X0/K4Y0; PLC ในตัวรัน CJ/JMP (JMP เฉพาะ R04) และโปรแกรมย่อย CALL/RET ได้ ทั้งตอนรันและตอน AI อ่าน CSV
- AI วิเคราะห์ ladder ด่าน 5–13 แม่นขึ้น (ค่า K, เครื่องหมายเปรียบเทียบ, D ต้นทาง, RST ที่ขาด) และไม่บอกว่ายืนยันแล้วเมื่อมีหลายจุดที่เป็นไปได้
- ครู: แท็บและแผ่น Excel "ข้อที่พลาดบ่อย" + ข้อสังเกตจาก ladder ในแผ่นรายข้อ (ไม่มีผลต่อคะแนน)
- บทเรียน ladder ทีละขั้น (ปุ่ม 🎓 ในแท็บ Ladder หรือ TUTORIAL LADDER)
- ตัวตรวจด่าน 5, 11, 13 เข้มขึ้น: ladder ที่ผิดบางแบบเคยได้ 3 ดาว
- หน้าตาใหม่ ใช้ง่ายขึ้น: แถบขั้นตอน 1–4 (เลือกด่าน → เชื่อมต่อ → เขียน ladder → ตรวจ), แถบเครื่องมือเตี้ยลงและไม่ทับกัน, แท็บผัง/กราฟ/Ladder อยู่บน, แผงอุปกรณ์กางเองเมื่อแก้ไขผัง, ใช้บนจอ 1280 ได้
- คัดลอก/วาง ladder ไปกลับกับ GX Works3 ได้ด้วย Ctrl+C / Ctrl+V (Ctrl+A เลือกทุก rung; ปิดตอนสอบ)
- เปิดโปรแกรมและแท็บ Ladder เป็นหน้าเปล่า (ladder ฝึกอิสระครั้งก่อนเก็บเป็นไฟล์ให้ ไม่หาย)
- แก้: ด่านที่ครูลบหรือเปลี่ยนรหัสกลับมาเองเมื่อเปิดโปรแกรมใหม่
### en
- Draw ladder inside the app (Ladder tab), run it on the built-in PLC with live monitoring, and check levels without GX Works3
- Ladder is checked before it is sent: points to the wrong rung, slots not filled in, and unsupported instructions
- Ladder autosaves per student and level; import/export GX Works3 CSV (exported files were imported into real GX Works3: R04 and FX5U)
- AI reads the ladder from a GX Works3 CSV and points to the likely wrong step (no effect on the score, off during exams)
- Level checker: waits until the PLC really sees the input, aborts on data gaps, an empty program earns no stars, panel locked while checking
- Warns about dangerous signals (e.g. forward and reverse together) even when every check passes
- Existing users get the corrected levels automatically; levels/panels they edited are never overwritten
- Score table, Excel and exam summary show which PLC was used (stars earned only on the Mock PLC are marked; stars are unchanged)
- Ladder: added BCD/BIN and 32-bit instructions (DMOV, DINC, DDEC, D+ D- D* D/, DBCD, DBIN, LDD= comparisons, ...) and digit-specified bits (K4X0/K4Y0); the built-in PLC runs CJ/JMP (JMP on R04 only) and CALL/RET subroutines for running and for AI reading CSV
- AI ladder analysis is more accurate on levels 5–13 (K values, comparison signs, source D, missing RST) and no longer claims confirmation when several spots are possible
- Teachers: a "Common mistakes" tab and Excel sheet, plus ladder notes in the per-item sheet (no effect on score)
- Step-by-step ladder lesson (🎓 button in the Ladder tab, or TUTORIAL LADDER)
- Stricter checks on levels 5, 11 and 13: some wrong ladders used to get 3 stars
- Easier UI: step bar 1–4 (choose level → connect → write ladder → check), shorter toolbars that never overlap, panel/chart/Ladder tabs on top, device pane opens by itself in edit mode, fits 1280-wide screens
- Copy/paste ladder to and from GX Works3 with Ctrl+C / Ctrl+V (Ctrl+A selects every rung; off in exams)
- The app and the Ladder tab start blank (your previous free ladder is kept as a file)
- Fixed: levels a teacher deleted or renamed came back after restarting the app

## 1.0.0 — 2026-11-18
### th
- รุ่นแรก: 14 ด่าน ตรวจคำตอบจากผล I/O กับ GX Simulator3 หรือ PLC จำลองในตัว
- ผังอุปกรณ์ลากวางเอง อุปกรณ์สมจริงกว่า 40 ชนิด (มอเตอร์ Y-Δ, สเต็ปเปอร์, กระบอกสูบ 5/3, รีเลย์นิรภัย ฯลฯ)
- กราฟ timing สด + กราฟเทียบผลที่ควรได้, AI วิเคราะห์ข้อผิดพลาด (ออฟไลน์)
- เครื่องมือครู: จำลองอุปกรณ์เสีย, ตัวแก้ไขด่าน, โหมดสอบ, ห้องเรียน/ตารางคะแนน (Export Excel), สื่อการสอน
- ด่านหาจุดเสีย, บทเรียนนำทาง, ภาษาไทย/อังกฤษ
### en
- First release: 14 levels graded from I/O behaviour with GX Simulator3 or the built-in simulated PLC
- Drag-and-drop device panels with 40+ realistic devices (star-delta motor, stepper, 5/3 cylinder, safety relay, …)
- Live timing chart + expected-vs-actual overlay, offline AI mistake analysis
- Teacher tools: fault injection, level editor, exam mode, classroom score table (Excel export), teaching aids
- Fault-finding level, guided tutorial, Thai/English UI
