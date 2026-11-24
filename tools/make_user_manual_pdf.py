"""สร้างคู่มือการใช้งาน PLC Trainer (PDF)

  .venv\\Scripts\\python tools\\capture_manual_shots.py     # ถ่ายภาพหน้าจอใหม่ (ถ้า UI เปลี่ยน)
  .venv\\Scripts\\python tools\\capture_ladder_shots.py     # ภาพแท็บ Ladder
  .venv\\Scripts\\python tools\\make_user_manual_pdf.py

ผลลัพธ์: docs/คู่มือการใช้งาน_PLC_Trainer.pdf  (render ด้วย Chrome เพื่อให้สระ/วรรณยุกต์ไทยถูกต้อง)
"""
import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images" / "manual"
OUT_HTML = ROOT / "docs" / "user_manual.html"
OUT_PDF = ROOT / "docs" / "คู่มือการใช้งาน_PLC_Trainer.pdf"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def img(name: str, width: str = "100%", cap: str = "") -> str:
    data = base64.b64encode((IMG / name).read_bytes()).decode()
    c = f"<figcaption>{cap}</figcaption>" if cap else ""
    return f'<figure><img src="data:image/png;base64,{data}" style="width:{width}">{c}</figure>'


def table(head, rows, cls="") -> str:
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def sec(num, title, html) -> str:
    return f'<section><h2><span class="num">{num}</span>{title}</h2>{html}</section>'


def build_html() -> str:
    parts = []

    parts.append(sec("1", "เปิดโปรแกรม", """
<p>บน Desktop มีไอคอน 2 อัน</p>
<ul><li><b>PLC Trainer</b> — ใช้งานปกติ</li>
<li><b>PLC Trainer (สาธิตวิธีใช้)</b> — โปรแกรมกดอุปกรณ์ให้ดูเองทีละขั้น พร้อมคำอธิบายด้านบน (ประมาณ 50 วินาที)</li></ul>
<p>เมื่อเปิด โปรแกรมจะโหลด<b>ผังล่าสุด</b>ที่ใช้ให้อัตโนมัติ (ครั้งแรกจะเป็นผังตัวอย่าง <code>panels\\default.plcpanel</code>)</p>"""))

    parts.append(sec("2", "ส่วนประกอบของหน้าจอ", img("01_overview.png", "84%") + "<p>ตัวเลขในตารางตรงกับกรอบสีเหลืองในภาพ</p>" + table(
        ["", "ส่วน", "หน้าที่"],
        [["1", "แถบบน + Ribbon", "แถบบน: ▶ ใช้งาน / ✎ แก้ไขผัง, เลือก PLC, เชื่อมต่อ · Ribbon: จัดการผัง (ใหม่ / เปิด / บันทึก / ย้อนกลับ) · มุมมอง (แบ่งจอ / ตัวใหญ่) · รอบอ่าน · กราฟ"],
         ["2", "แผงซ้าย", "🧰 อุปกรณ์ (ลากไปวางบนผัง หรือดับเบิลคลิก) · ☰ ตาราง I/O · 📈 สัญญาณบนกราฟ"],
         ["3", "พื้นที่ทำงาน", "แท็บ <b>Panel</b> = ผังอุปกรณ์ · แท็บ <b>Chart</b> = กราฟ · แท็บ <b>Ladder</b> = เขียน ladder (สลับแท็บที่มุมล่างซ้าย)"],
         ["4", "แผงขวา", "⚙ คุณสมบัติของอุปกรณ์ที่เลือก · 🎯 ด่าน / ผลตรวจ / AI · ⚡ ความผิดปกติ (ครู) — คลิกไอคอนเพื่อเปิด/ยุบแผง"],
         ["5", "COMMAND LINE", "ข้อความจากโปรแกรม และพิมพ์คำสั่งได้ (ดูหัวข้อ 9)"],
         ["6", "Status bar", "อัตราการอ่าน (Hz) และปุ่มสถานะ RUN/EDIT · SNAP · GRID · SPLIT · BIG · REC · ONLINE"]],
        "compact")))

    parts.append(sec("3", "เชื่อมต่อ PLC", """
<ol><li>ที่แถบบน ช่อง <b>PLC</b> เลือก (ตั้ง Host / Port ที่ปุ่ม ⚙ ข้าง ๆ)
  <ul><li><b>GX Simulator3 (SLMP)</b> — ต่อกับ ladder ที่เขียนใน GX Works3 (Host <code>127.0.0.1</code>, Port <code>5511</code>)</li>
  <li><b>PLC ในตัว (รัน ladder)</b> — รัน ladder ที่วาดในแท็บ Ladder ไม่ต้องเปิด GX (ดูหัวข้อ 12)</li>
  <li><b>Mock PLC (ทดสอบ)</b> — PLC จำลองในโปรแกรม มี ladder ตัวอย่างฝังไว้ ใช้ทดลองได้โดยไม่ต้องเปิด GX</li></ul></li>
<li>กด <b>⏻ เชื่อมต่อ</b> → ปุ่ม <b>ONLINE</b> มุมขวาล่างเป็นสีเขียว และมีตัวเลข Hz แสดงอัตราการอ่าน</li>
<li>กดอีกครั้ง (<b>ตัดการเชื่อมต่อ</b>) เมื่อเลิกใช้</li></ol>
<div class="note">💡 การตั้งค่า GX Works3 / GX Simulator3 ให้ต่อได้ ดูคู่มือแยก <b>คู่มือตั้งค่า_GX_Simulator3.pdf</b>
(สรุป: ใช้โปรเจกต์ CPU <b>R04</b> และตั้ง <b>Enable All (SLMP)</b>)</div>
<p class="small">ladder ของ Mock PLC: X0 Start / X1 Stop → Y0 (self-hold) · Y0 ติด 3 วินาที → T0 → Y1 · X2 นับ 5 ครั้ง → C0 → Y2 · X3 รีเซ็ต C0</p>"""))

    parts.append(sec("4", "ใช้งานผัง (โหมดใช้งาน ▶)", img("02_run.png", "100%") + """
<p>ปกติโปรแกรมอยู่ใน<b>โหมดใช้งาน</b> (Status bar แสดง <b>RUN</b>) — คลิกอุปกรณ์บนผังเพื่อสั่งงานเหมือนตู้คอนโทรลจริง</p>
<ul>
<li><b>ปุ่มกด / ลิมิตสวิตช์</b> — กดค้าง = ON ปล่อย = OFF</li>
<li><b>สวิตช์เลือก / E-Stop</b> — คลิกครั้งเดียวค้างไว้ คลิกอีกครั้งเพื่อปลด</li>
<li><b>คีย์ลัด</b> — ป้ายสีขาวมุมอุปกรณ์ (1, 2, 3…) กดคีย์นั้นบนคีย์บอร์ดแทนการคลิกได้ (ใช้ได้แม้คีย์บอร์ดเป็นภาษาไทย)</li>
<li><b>สายพาน</b> — เดินเมื่อ address ของมัน ON · กด <b>+ ชิ้นงาน</b> เพื่อปล่อยชิ้นงาน</li>
<li><b>เซนเซอร์</b> — ON เมื่อชิ้นงานตัดลำแสงสีแดง (คลิกที่เซนเซอร์เพื่อสั่ง ON/OFF เองก็ได้)</li>
<li><b>ไฟเล็กมุมขวาบนของอุปกรณ์ Input</b> = ค่าที่ PLC อ่านได้จริง (ใช้ตรวจว่าสัญญาณถึง PLC หรือไม่)</li>
<li><b>ชี้เมาส์ค้าง</b>ที่อุปกรณ์ → เห็น address, ค่าที่ส่ง / ค่าที่ PLC เห็น และเวลาที่เปลี่ยนล่าสุด</li>
</ul>
<h3>อุปกรณ์ที่มีให้เลือก</h3>""" + table(
        ["หมวด", "อุปกรณ์", "Address ที่ใช้ได้", "หมายเหตุ"],
        [["Input", "ปุ่มกด, สวิตช์เลือก, E-Stop, ลิมิตสวิตช์", "X, M", "ตั้ง NO/NC ได้ · E-Stop ค่าเริ่มต้น NC"],
         ["Output", "หลอดไฟ (6 สี), มอเตอร์, ออด, โซลินอยด์วาล์ว", "Y, M", "หลายชิ้นใช้ address เดียวกันได้"],
         ["Sensor / สายพาน", "เซนเซอร์ (Proximity/Photo), สายพาน", "เซนเซอร์ X, M · สายพาน Y, M", "ตั้งความยาว/ความเร็วสายพานได้"],
         ["Input เพิ่ม", "โอเวอร์โหลดรีเลย์ (OL)", "X, M (+ มอเตอร์ที่เฝ้า Y)", "คลิก = ทริป/รีเซ็ต · ตั้งให้ทริปเองเมื่อมอเตอร์ทำงานนานเกินได้"],
         ["Output เพิ่ม", "คอนแทคเตอร์, ไฟจราจร", "คอยล์ Y · aux X · แดง/เหลือง/เขียว Y", "หน้าสัมผัสช่วยส่งกลับเข้า PLC อัตโนมัติ"],
         ["นิวแมติก / กระบวนการ", "กระบอกสูบ + วาล์ว 5/2, ถังน้ำ", "โซลินอยด์/ปั๊ม Y · รีดสวิตช์/เซนเซอร์ระดับ X", "รีดสวิตช์ a0/a1 และเซนเซอร์ระดับ H/L ทำงานเองตามตำแหน่ง/ระดับน้ำ"],
         ["แสดงค่า / ตั้งค่า", "Display, 7-Segment, ตัวตั้งค่า (Thumbwheel)", "TN, CN, D · ตัวตั้งค่าใช้ D", "ตัวตั้งค่าเขียนตัวเลขลง D ใน PLC"]]) + """
<h3>อุปกรณ์ที่มีหลาย Address</h3>
<p>กระบอกสูบ, ถังน้ำ, คอนแทคเตอร์, ไฟจราจร และ OL มีช่อง Address หลายช่องในแผง ⚙ คุณสมบัติ —
<b>→ PLC</b> = สัญญาณที่โปรแกรมเขียนเข้า PLC (เป็น Input ของ ladder) · <b>PLC →</b> = ทำงานตามค่าจาก PLC ·
ช่องที่เขียนว่า <i>เว้นว่างได้</i> ไม่ต้องใส่ก็ได้</p>
<ul>
<li><b>กระบอกสูบ</b> — วาล์ว<i>โซลินอยด์เดียว</i>: ปล่อยสัญญาณแล้วสปริงดันกลับ · <i>สองโซลินอยด์</i>: ค้างตำแหน่งจนกว่าจะสั่งอีกด้าน · ตั้งเวลาเคลื่อนสุดระยะได้</li>
<li><b>ถังน้ำ</b> — ปั๊ม ON = น้ำขึ้น · วาล์วปล่อย ON หรือ<b>คลิกที่ถัง (เปิดก๊อก)</b> = น้ำลง · เซนเซอร์ H/L ON เมื่อน้ำถึงระดับ</li>
<li><b>ตัวตั้งค่า</b> — ปุ่ม −10 −1 +1 +10 หรือคลิกตัวเลขเพื่อพิมพ์ · ขึ้น “✔ PLC รับค่าแล้ว” เมื่อค่าใน D ตรงกัน</li>
</ul>
<p class="small">ผังตัวอย่างในโฟลเดอร์ panels: cylinder_AplusBplus, tank, star_delta, traffic (กด เปิด ที่ Ribbon)</p>"""))

    parts.append('<div style="page-break-before:always"></div>' + sec("5", "จัดผังเอง (โหมดแก้ไข ✎)", f"""
<p>กด <b>✎ แก้ไขผัง</b> ที่แถบบน (หรือคลิก RUN ที่ Status bar) → Status bar เปลี่ยนเป็น <b>EDIT</b></p>
<div class="two"><div>{img("03_edit.png", "100%")}</div></div>
<ol><li><b>วางอุปกรณ์:</b> ลากจากแผง 🧰 อุปกรณ์ มาวางบนผัง, ดับเบิลคลิกในรายการ (วางกลางจอ) หรือคลิกขวาที่พื้นว่าง</li>
<li><b>ย้าย:</b> ลากอุปกรณ์ (จะเกาะกริดทีละ 20 px เมื่อเปิด SNAP) · ลากกรอบบนพื้นว่างเพื่อเลือกหลายชิ้น</li>
<li><b>ตั้งค่า:</b> คลิกเลือกอุปกรณ์ แล้วแก้ในแผง ⚙ คุณสมบัติ — ชื่อ, <b>Address</b> (ทุกช่อง), หน้าสัมผัส NO/NC, คีย์ลัด, สี, หน่วย, ค่าเฉพาะอุปกรณ์ (ความเร็วสายพาน, ชนิดวาล์ว, อัตราเติมน้ำ ฯลฯ)</li>
<li>ตั้ง <b>Address ให้ตรงกับ ladder</b> ที่เขียนใน GX Works3 — โปรแกรมตรวจให้ทันที
  <ul><li>กรอบแดง = ชนิด address ไม่ถูก (เช่น หลอดไฟใส่ X) หรือเลขไม่มีจริง</li>
  <li>⚠ = Input สองชิ้นใช้ address เดียวกัน (สัญญาณจะเขียนทับกัน)</li></ul></li>
<li>เสร็จแล้วกด <b>▶ ใช้งาน</b> เพื่อกลับไปทดลองกดอุปกรณ์</li></ol>
<div class="imgs">{img("04_props_conflict.png", "135px", "ตัวอย่าง: address ชนกัน")}
{img("05_context_menu.png", "150px", "คลิกขวาที่อุปกรณ์")}
{img("06_context_add.png", "140px", "คลิกขวาที่พื้นว่าง")}{img("06b_context_add_sub.png", "135px", "→ เลือกอุปกรณ์มาวาง")}</div>
<div class="note">↶ ทำพลาด? กด <b>Ctrl+Z</b> (ย้อนกลับ) หรือ <b>Ctrl+Y</b> (ทำซ้ำ) ได้ทุกขั้น — วาง ย้าย ลบ แก้ address</div>"""))

    parts.append(sec("6", "บันทึกและเปิดผัง", """
<ul><li><b>💾 บันทึก</b> — บันทึกทับไฟล์เดิม · <b>💾 บันทึกเป็น</b> — ตั้งชื่อไฟล์ใหม่ (นามสกุล <code>.plcpanel</code>)</li>
<li><b>📂 เปิด</b> — เปิดผังที่บันทึกไว้ · <b>📄 ใหม่</b> — เริ่มผังว่าง</li>
<li>ไฟล์ผังเก็บในโฟลเดอร์ <code>panels\\</code> ของโปรแกรม (ส่งให้เพื่อน/ครูได้)</li>
<li>ชื่อหน้าต่างมีเครื่องหมาย <b>*</b> = ยังไม่ได้บันทึก — ถ้าปิดโปรแกรมจะถามก่อน</li></ul>
<div class="warn">⚠️ อย่ากด <b>บันทึก</b> ทับผังตัวอย่าง <code>default.plcpanel</code> — ให้ใช้ <b>บันทึกเป็น</b> ตั้งชื่อใหม่</div>"""))

    parts.append(sec("7", "กราฟ (Timing Diagram / Trend)", img("08_chart.png", "100%") + """
<ul><li><b>TIMING DIAGRAM</b> — สัญญาณบิต (X, Y, M, T, C) แสดงเป็น 0/1 เลื่อนตามเวลาจริง</li>
<li><b>TREND</b> — ค่าตัวเลขของ Timer / Counter</li>
<li>สัญญาณบนกราฟสร้างจาก <b>address ที่มีในผัง</b>อัตโนมัติ · ติ๊กเลือก/เอาออกได้ที่แผง <b>📈 สัญญาณบนกราฟ</b></li>
<li><b>⏸ หยุดกราฟ</b> แล้วเลื่อนเมาส์บนกราฟ → แถบล่างบอกค่าทุกสัญญาณ ณ เวลานั้น (ใช้ตรวจลำดับการทำงาน)</li>
<li><b>ช่วงเวลา</b> = ความยาวที่แสดง (วินาที) · <b>🗑 ล้างกราฟ</b> = เริ่มบันทึกใหม่</li></ul>"""))

    parts.append(sec("8", "มุมมอง: แบ่งจอ และ ตัวใหญ่", img("07_split.png", "100%", "◫ แบ่งจอ — ผังด้านบน กราฟด้านล่าง") + """
<ul><li><b>◫ แบ่งจอ</b> (หรือ SPLIT ที่ Status bar) — เห็นผังและกราฟพร้อมกัน ลากเส้นแบ่งเพื่อปรับขนาด</li>
<li><b>🔍 ตัวใหญ่</b> (หรือ BIG) — ขยายตัวอักษรทั้งโปรแกรม สำหรับฉายโปรเจกเตอร์หน้าห้อง</li>
<li>ซูมผัง: <b>ล้อเมาส์</b> · เลื่อนผัง: <b>กดปุ่มกลางค้างแล้วลาก</b> · ดูทั้งผัง: <b>ดับเบิลคลิกปุ่มกลาง</b> หรือปุ่ม ⛶ ดูทั้งผัง</li></ul>
<p class="small">โปรแกรมจำการตั้งค่าแบ่งจอ / ตัวใหญ่ไว้ เปิดครั้งหน้าจะเหมือนเดิม</p>""" + img("09_large.png", "78%", "🔍 โหมดตัวใหญ่")))

    parts.append(sec("9", "คำสั่ง (COMMAND LINE)", "<p>คลิกช่อง <b>▸ คำสั่ง</b> ด้านล่าง พิมพ์แล้วกด Enter (พิมพ์ตัวเล็กหรือใหญ่ก็ได้)</p>" + table(
        ["คำสั่ง", "ความหมาย"],
        [["<code>CONNECT</code> / <code>DISCONNECT</code>", "เชื่อมต่อ / ตัดการเชื่อมต่อ PLC"],
         ["<code>SET X0</code> / <code>RST X0</code>", "สั่งอุปกรณ์บิต ON / OFF โดยตรง"],
         ["<code>PULSE X2</code>", "ON แล้ว OFF (0.2 วินาที)"],
         ["<code>EDIT</code> / <code>RUN</code>", "โหมดแก้ไขผัง / โหมดใช้งาน"],
         ["<code>U</code> / <code>REDO</code>", "ย้อนกลับ / ทำซ้ำ การแก้ผัง"],
         ["<code>SPLIT</code> / <code>BIG</code>", "สลับแบ่งจอ / สลับโหมดตัวใหญ่"],
         ["<code>DRAW</code>", "เปิดแท็บ Ladder"],
         ["<code>ZOOM</code>", "ดูทั้งผัง"],
         ["<code>PAUSE</code> / <code>RESUME</code> / <code>CLEAR</code>", "หยุด / เล่นต่อ / ล้างกราฟ"],
         ["<code>WINDOW 20</code>", "ตั้งช่วงเวลาที่แสดงบนกราฟ (วินาที)"],
         ["<code>TUTORIAL</code> / <code>TUTORIAL LADDER</code>", "บทเรียนนำทาง / บทเรียนเขียน ladder"],
         ["<code>LOGIN</code> / <code>SCORES</code>", "ลงชื่อนักเรียน / ตารางคะแนนทั้งห้อง"],
         ["<code>HELP</code>", "แสดงคำสั่งทั้งหมด"]], "compact")))

    parts.append(sec("10", "คีย์ลัดทั้งหมด", table(
        ["คีย์", "ทำอะไร", "ใช้ได้ในโหมด"],
        [["1–9, A–Z", "กดอุปกรณ์ Input ที่ตั้งคีย์นั้นไว้", "ใช้งาน (RUN)"],
         ["Ctrl+Z / Ctrl+Y", "ย้อนกลับ / ทำซ้ำ", "ทุกโหมด"],
         ["Delete", "ลบอุปกรณ์ที่เลือก", "แก้ไข (EDIT)"],
         ["Ctrl+D", "ทำซ้ำอุปกรณ์ที่เลือก (address Input จะเลื่อนเป็นเลขถัดไป)", "แก้ไข (EDIT)"],
         ["คลิกขวา", "เมนูอุปกรณ์ / วางอุปกรณ์", "แก้ไข (EDIT)"],
         ["ล้อเมาส์ · ปุ่มกลางลาก · ดับเบิลคลิกปุ่มกลาง", "ซูม · เลื่อน · ดูทั้งผัง", "ทุกโหมด"]], "compact")))

    parts.append(sec("11", "การตั้งค่า", """
<h3>11.1 ไฟล์ <code>plc_game\\config.yaml</code> (ค่าเริ่มต้นตอนเปิดโปรแกรม)</h3>""" + table(
        ["ค่า", "ตัวอย่าง", "ความหมาย"],
        [["<code>backend</code>", "slmp", "แหล่ง PLC เริ่มต้น: <code>slmp</code> = GX Simulator3 / PLC จริง, <code>soft</code> = PLC ในตัว, <code>mock</code> = PLC จำลอง"],
         ["<code>host</code> / <code>port</code>", "127.0.0.1 / 5511", "ที่อยู่ PLC (GX Simulator3 ระบบที่ 1 = พอร์ต 5511)"],
         ["<code>plc_type</code>", "iQ-R", "ชนิด PLC สำหรับโปรโตคอล SLMP"],
         ["<code>xy_base</code>", "16", "ระบบเลข X/Y: <b>16</b> = iQ-R (X0–XF, X10…), <b>8</b> = FX5U (X0–X7, X10…)"],
         ["<code>timeout_s</code>", "2.0", "รอคำตอบจาก PLC นานสุด (วินาที)"],
         ["<code>poll_ms</code>", "50", "รอบอ่านข้อมูล (มิลลิวินาที) — ปรับได้ที่ Ribbon ช่อง รอบอ่าน"],
         ["<code>chart_window_s</code>", "10", "ช่วงเวลาที่แสดงบนกราฟตอนเปิดโปรแกรม"]], "compact") + """
<p class="small">แก้ไฟล์ด้วย Notepad แล้วเปิดโปรแกรมใหม่ · ค่าบนหน้าจอ (PLC / Host / Port / รอบอ่าน) เปลี่ยนได้ทันทีโดยไม่ต้องแก้ไฟล์ แต่จะไม่ถูกจำ</p>
<h3>11.2 ตัวเลือกที่สั่งจากหน้าจอ</h3>""" + table(
        ["ตั้งค่า", "อยู่ที่", "จำไว้ไหม"],
        [["PLC / Host / Port", "แถบบน → ช่อง PLC และปุ่ม ⚙ (ตั้งได้ตอนยังไม่เชื่อมต่อ)", "ไม่ (ใช้ค่าใน config.yaml)"],
         ["รอบอ่าน", "Ribbon → การอ่านข้อมูล", "ไม่"],
         ["ช่วงเวลากราฟ", "Ribbon → กราฟ หรือคำสั่ง WINDOW", "ไม่"],
         ["SNAP / GRID", "Status bar", "ไม่"],
         ["แบ่งจอ / ตัวใหญ่ / ผังล่าสุด", "Ribbon → มุมมอง หรือ Status bar", "จำใน <code>panels\\ui_state.json</code>"]], "compact") + """
<h3>11.3 กติกา Address</h3>
<ul><li>ใส่เป็นชื่ออุปกรณ์ PLC เช่น <code>X0</code>, <code>Y10</code>, <code>M5</code>, <code>TN0</code>, <code>CN1</code>, <code>D100</code> (พิมพ์ตัวเล็กได้ โปรแกรมแปลงให้)</li>
<li>ชนิดต้องตรงกับอุปกรณ์ — Input ใช้ X/M, Output ใช้ Y/M, ตัวแสดงค่าใช้ TN/CN/D</li>
<li>เลข X/Y ต้องถูกตามฐาน (<code>xy_base</code>) เช่น ฐาน 8 ไม่มี X8 (ต่อจาก X7 คือ X10)</li>
<li>ถ้า PLC ไม่ยอมให้เขียน X จากภายนอก ให้ตั้งปุ่มเป็น <b>M</b> แทน (เช่น M100) แล้วใช้ M นั้นใน ladder</li></ul>"""))

    parts.append('<div style="page-break-before:always"></div>' + sec("12", "เขียน ladder ในโปรแกรม (PLC ในตัว)",
        "<p>ใช้ฝึกได้โดย<b>ไม่ต้องมี GX Works3</b> — วาด รัน และตรวจด่านในโปรแกรมเดียว · เพิ่งเริ่ม: กด <b>🎓</b> ในแท็บ Ladder เพื่อทำบทเรียนทีละขั้น</p>"
        + img("10_ladder.png", "100%", "แท็บ Ladder ขณะ RUN — สีเขียว = ไฟผ่าน (วงจรตัวอย่าง ไม่ใช่คำตอบของด่าน)") + """
<ol><li>แถบบน ช่อง <b>PLC</b> เลือก <b>PLC ในตัว (รัน ladder)</b> → <b>⏻ เชื่อมต่อ</b></li>
<li>เปิดด่านหรือผัง → แท็บ <b>Ladder</b> (หรือพิมพ์ <code>DRAW</code>)</li>
<li>วาด ladder — ดับเบิลคลิกรายการ<b>อุปกรณ์บนผัง</b>ด้านขวาเพื่อใช้ address นั้นได้</li>
<li>กด <b>F4</b> → โปรแกรมตรวจก่อน ถ้าผ่านจะ<b>ล้าง M/T/C/D แล้ว RUN</b></li>
<li>ทดลองกดอุปกรณ์ในแท็บ Panel หรือกด <b>▶ ตรวจคำตอบ</b> (แก้ ladder แล้วต้องกด F4 ก่อนตรวจ)</li></ol>""" + table(
        ["คีย์ (ในแท็บ Ladder)", "ทำอะไร"],
        [["F5 / F6", "หน้าสัมผัส NO / NC · Shift = ต่อขนาน · Ctrl = แทรกก่อน"],
         ["F7 / Shift+F7", "คอยล์ / output ที่มีหน้าสัมผัสของตัวเอง (แยกกิ่ง)"],
         ["F8", "คำสั่ง เช่น <code>MOV K10 D0</code>, <code>SET M0</code>, <code>RST C0</code>"],
         ["พิมพ์ได้เลย", "<code>X0</code>, <code>ANI X1</code>, <code>OUT T0 K30</code> (แป้นภาษาอังกฤษ)"],
         ["Enter หรือ F2 · Space", "แก้ชิ้นที่เลือก · สลับ NO/NC"],
         ["Shift+→", "เลือกช่วง (ใช้ก่อนต่อขนาน)"],
         ["Insert / Shift+Insert", "แทรก rung ใต้ / เหนือ"],
         ["Delete / Ctrl+Delete", "ลบชิ้นที่เลือก / ทั้ง rung"],
         ["Alt+↑↓ · ;", "ย้าย rung · ใส่คอมเมนต์"],
         ["Ctrl+Z / Y / C / X / V", "ย้อนกลับ / ทำซ้ำ / คัดลอก / ตัด / วาง rung"]], "compact")
        + img("11_ladder_problem.png", "88%", "มีช่อง ? ที่ยังไม่ได้กรอก — คลิกข้อความในผลตรวจ ladder เพื่อไปที่ rung") + """
<ul><li><b>คำสั่งที่รองรับ:</b> หน้าสัมผัสทุกแบบ, เปรียบเทียบ 16/32 บิต (เช่น LDD>=), OUT/SET/RST/PLS/PLF/FF, T/C/ST, MOV/FMOV/BMOV, INC/DEC, + − × ÷, BCD/BIN, 32 บิต DMOV/DINC/DDEC/D+ D- D* D/ /DBCD/DBIN (ใช้ D, W, SD 2 ตัวติดกัน), กลุ่มบิต K1–K8 เช่น BIN K4X0 D0, CJ/CJP/JMP (JMP เฉพาะ R04), CALL/CALLP + ป้าย P0, FEND, RET/SRET (AI ยังไม่วิเคราะห์ ladder ที่กระโดด), MC/MCR, INV/MEP/MEF (คำสั่งอื่นจะไม่ให้ RUN)</li>
<li><b>RUN / STOP / RESET</b> — STOP: Y ดับหมด · RESET: ล้าง M/T/C/D และข้อผิดพลาด แล้วหยุด</li>
<li><b>บันทึกอัตโนมัติ</b> แยกตามนักเรียนและด่าน · โหมดสอบเริ่มจาก ladder ว่าง และปิดการนำเข้า/ส่งออก</li></ul>
<div class="note"><b>ส่งออก CSV</b> นำเข้าใน GX Works3 ได้ (ลองแล้วกับ R04 และ FX5U): Edit → Import File — คำสั่งที่ PLC รุ่นนั้นไม่มีจะกลายเป็น OUT SM4095 ให้ตรวจ ladder หลังนำเข้า</div>"""))

    parts.append(sec("13", "ให้ AI อ่าน ladder (CSV)", """
<p>ไม่บังคับ — ช่วยให้ AI ชี้ step ที่น่าจะผิด <b>คะแนนยังมาจาก I/O เท่านั้น</b> และปิดอัตโนมัติในโหมดสอบ</p>
<ol><li>GX Works3: เปิดหน้า ladder ที่ Convert แล้ว → <b>Edit → Export to File…</b> → <b>Yes</b> → <b>Save</b></li>
<li>PLC Trainer: เปิดด่าน → <b>📄 เลือก CSV ladder</b> → <b>▶ ตรวจคำตอบ</b></li>
<li>แก้ ladder แล้ว: Write ลง PLC และ Export ทับไฟล์เดิม — โปรแกรมอ่านใหม่ให้เอง</li></ol>
<div class="note">ถ้าขึ้นว่า "ไฟล์ CSV ไม่ตรงกับโปรแกรมที่รันอยู่ใน PLC" ให้ Export ใหม่และ Write ลง PLC ก่อนตรวจอีกครั้ง</div>"""))

    parts.append(sec("14", "รายงานสำหรับครู", """
<ul><li>เปิดตารางคะแนน (พิมพ์ <code>SCORES</code>) → แท็บ <b>ข้อที่พลาดบ่อย</b>: จำนวนคนที่พลาด ร้อยละ และรหัสนักเรียน
(นับจากการตรวจครั้งล่าสุดของแต่ละคน ไม่รวม guest และข้อที่ถูกข้าม)</li>
<li><b>📊 Export Excel</b> ได้ 3 แผ่น: สรุป · รายข้อ · ข้อที่พลาดบ่อย</li>
<li>แผ่น <b>รายข้อ</b> มี <b>ข้อสังเกตจาก ladder</b> ของการตรวจครั้งล่าสุด (ถ้ามี) — ช่วยครูอธิบายเท่านั้น ไม่มีผลต่อคะแนน</li></ul>"""))

    parts.append(sec("?", "แก้ปัญหาที่พบบ่อย", table(
        ["อาการ", "สาเหตุ / วิธีแก้"],
        [["กดเชื่อมต่อแล้ว OFFLINE ค้าง / timed out", "GX Simulator3 ยังไม่ได้ Start Simulation หรือโปรเจกต์ไม่ใช่ R04 — ดูคู่มือตั้งค่า GX · หรือเปลี่ยนแหล่งเป็น Mock PLC เพื่อทดลองก่อน"],
         ["คลิกปุ่มแล้วไฟเล็กมุมปุ่มไม่ติด", "PLC ไม่ได้รับค่า: ยังไม่ได้ตั้ง Enable All (SLMP) ใน GX หรือ address ของปุ่มเป็นสีแดง (ไม่ถูกต้อง)"],
         ["กด ตรวจคำตอบ แล้วเตือนว่ายังไม่ได้ส่งลง PLC", "แก้ ladder แล้วยังไม่ได้กด F4 ในแท็บ Ladder"],
         ["กด F4 แล้วส่งไม่ได้", "ดูผลตรวจ ladder ด้านขวา คลิกข้อความเพื่อไปที่ rung — ช่อง ? = ยังไม่ได้กรอก"],
         ["ไฟเล็กติด แต่ Output ไม่ทำงาน", "สัญญาณถึง PLC แล้ว — ตรวจ ladder หรือ address ของ Output ว่าตรงกับคอยล์ใน ladder หรือไม่"],
         ["คลิกอุปกรณ์แล้วมันขยับแทนที่จะกด", "อยู่ในโหมดแก้ไข (EDIT) — กด ▶ ใช้งาน"],
         ["คีย์ลัดไม่ทำงาน", "ต้องอยู่โหมดใช้งาน และเคอร์เซอร์ไม่ได้อยู่ในช่องพิมพ์ (คลิกที่ผังก่อน)"],
         ["ปุ่ม Stop แบบ NC ทำงานกลับด้าน", "ตรวจหน้าสัมผัสในแผง ⚙ คุณสมบัติ ให้ตรงกับที่เขียนใน ladder (NO = ปกติ 0, NC = ปกติ 1)"],
         ["ชื่อสัญญาณบนกราฟซ้อนกัน", "เลือกสัญญาณน้อยลงที่แผง 📈 สัญญาณบนกราฟ หรือลากเส้นแบ่งให้กราฟสูงขึ้น"]])))

    body = "".join(parts)
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>คู่มือการใช้งาน PLC Trainer</title>
<style>
@page {{ size: A4; margin: 14mm 14mm 16mm; }}
body {{ font-family: "Leelawadee UI", "Tahoma", sans-serif; font-size: 11pt; color: #1d2430; line-height: 1.55; }}
header {{ background: #212830; color: #fff; padding: 18px 22px; border-left: 6px solid #1F8FD6; margin-bottom: 14px; }}
header h1 {{ margin: 0; font-size: 22pt; }}
header p {{ margin: 4px 0 0; color: #b9c3cf; font-size: 10.5pt; }}
.toc {{ background: #eef5fb; border: 1px solid #c9dff0; padding: 8px 14px; font-size: 10.5pt; columns: 2; }}
.toc div {{ margin: 1px 0; }}
section {{ margin: 0 0 10px; }}
h2 {{ font-size: 14.5pt; margin: 14px 0 6px; color: #12324d; border-bottom: 2px solid #1F8FD6; padding-bottom: 3px;
      page-break-after: avoid; }}
h3 {{ font-size: 12pt; color: #12324d; margin: 10px 0 4px; page-break-after: avoid; }}
.num {{ display: inline-block; background: #1F8FD6; color: #fff; min-width: 26px; height: 26px; line-height: 26px; padding: 0 4px;
        box-sizing: border-box; text-align: center; border-radius: 13px; margin-right: 8px; font-size: 12pt; }}
ol, ul {{ margin: 4px 0 6px 0; padding-left: 22px; }} li {{ margin: 2px 0; }}
code {{ background: #eef1f5; padding: 0 4px; border-radius: 3px; font-family: Consolas, monospace; font-size: 9.5pt; }}
.imgs {{ text-align: center; margin: 6px 0; }}
figure {{ display: inline-block; margin: 4px 6px; page-break-inside: avoid; vertical-align: top; }}
figure img {{ border: 1px solid #9aa4b2; box-shadow: 0 1px 4px rgba(0,0,0,.18); }}
figcaption {{ font-size: 9pt; color: #5b6676; text-align: center; }}
section > figure {{ display: block; text-align: center; margin: 6px 0; }}
.note {{ background: #f3f8ec; border-left: 4px solid #5ea83a; padding: 6px 10px; margin: 6px 0; font-size: 10.5pt; }}
.warn {{ background: #fff6e5; border-left: 4px solid #e8a317; padding: 6px 10px; margin: 6px 0; font-size: 10.5pt; }}
.small {{ font-size: 9.5pt; color: #5b6676; }}
table {{ border-collapse: collapse; width: 100%; font-size: 10pt; margin: 4px 0 6px; }}
tr {{ page-break-inside: avoid; }}
thead, tbody tr:first-child {{ break-after: avoid; }}
tbody tr:last-child {{ break-before: avoid; }}
th, td {{ border: 1px solid #c4ccd6; padding: 4px 7px; vertical-align: top; text-align: left; }}
th {{ background: #212830; color: #fff; }}
table.compact td:first-child {{ white-space: nowrap; }}
</style></head><body>
<header><h1>คู่มือการใช้งาน PLC Trainer</h1>
<p>โปรแกรมฝึก PLC สำหรับนักเรียน ปวช.3 · จัดผังอุปกรณ์เอง เขียน ladder ในโปรแกรมหรือต่อกับ GX Simulator3 และดูกราฟสัญญาณแบบเรียลไทม์</p></header>
<div class="toc">
<div>1. เปิดโปรแกรม</div><div>2. ส่วนประกอบของหน้าจอ</div><div>3. เชื่อมต่อ PLC</div><div>4. ใช้งานผัง</div>
<div>5. จัดผังเอง</div><div>6. บันทึกและเปิดผัง</div><div>7. กราฟ</div><div>8. แบ่งจอ / ตัวใหญ่</div>
<div>9. คำสั่ง</div><div>10. คีย์ลัด</div><div>11. การตั้งค่า</div><div>12. เขียน ladder ในโปรแกรม</div><div>13. AI อ่าน ladder</div><div>14. รายงานครู</div><div>?. แก้ปัญหา</div></div>
{body}
</body></html>"""


def main():
    OUT_HTML.write_text(build_html(), encoding="utf-8")
    tmp = OUT_PDF.with_name("_tmp_manual.pdf")
    tmp.unlink(missing_ok=True)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={tmp}", OUT_HTML.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    try:
        tmp.replace(OUT_PDF)
    except PermissionError:
        sys.exit(f"✖ ไฟล์ {OUT_PDF.name} ถูกเปิดอยู่ — ปิดโปรแกรมอ่าน PDF แล้วรันใหม่ (ไฟล์ใหม่อยู่ที่ {tmp})")
    print("PDF:", OUT_PDF, OUT_PDF.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
