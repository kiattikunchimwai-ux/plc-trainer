"""สร้างคู่มือ PDF: วิธีตั้งค่า GX Simulator3 ให้เชื่อมต่อกับ PLC Trainer

  python tools/make_setup_pdf.py [--crop-from <โฟลเดอร์ภาพหน้าจอ>]

ภาพประกอบเก็บใน docs/images/setup/  (--crop-from ใช้ตัดภาพจากหน้าจอดิบครั้งแรก)
ผลลัพธ์: docs/คู่มือตั้งค่า_GX_Simulator3.pdf  (render ด้วย Chrome เพื่อให้สระ/วรรณยุกต์ไทยถูกต้อง)
"""
import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images" / "setup"
OUT_HTML = ROOT / "docs" / "setup_guide.html"
OUT_PDF = ROOT / "docs" / "คู่มือตั้งค่า_GX_Simulator3.pdf"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ชื่อไฟล์ผลลัพธ์: (ภาพต้นฉบับ, กรอบตัด x1,y1,x2,y2 ในพิกัด 1280x800)
CROPS = {
    "01_project_menu.png": ("s8.png", (0, 20, 250, 215)),
    "02_change_type.png": ("s16.png", (470, 262, 810, 495)),
    "03_confirm.png": ("s17.png", (450, 238, 830, 520)),
    "04_parameter.png": ("s30.png", (150, 112, 1110, 490)),
    "05_rebuild.png": ("s34.png", (455, 235, 825, 525)),
    "06_sim_menu.png": ("s4.png", (290, 20, 670, 130)),
    "07_simulator.png": ("s41.png", (1055, 460, 1277, 674)),
    "08_monitor.png": ("s42.png", (345, 135, 1110, 490)),
}
# 09_trainer.png = ภาพหน้าจอ PLC Trainer (ผังอุปกรณ์) ขณะต่อกับ GX จริง — คัดลอกมาทั้งภาพ ไม่ต้องตัด


def crop_from(src_dir: Path):
    from PIL import Image
    IMG.mkdir(parents=True, exist_ok=True)
    for name, (src, box) in CROPS.items():
        Image.open(src_dir / src).crop(box).save(IMG / name)
        print("crop", name)


def img(name: str, width: str = "100%") -> str:
    data = base64.b64encode((IMG / name).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" style="width:{width}">'


def build_html() -> str:
    steps = [
        ("1", "เปิดโปรเจกต์และเปลี่ยนชนิด CPU เป็น R04",
         """<p>GX Simulator3 จะตอบ SLMP กับโปรแกรมภายนอก <b>เฉพาะโปรเจกต์ RCPU (iQ-R)</b> เท่านั้น
         ถ้าโปรเจกต์ของคุณเป็น FX5U ให้เปลี่ยนชนิด CPU ก่อน (ladder ที่เขียนไว้จะยังอยู่ครบ)</p>
         <ol><li>ไปที่เมนู <b>Project → Change Module Type/Operation Mode...</b></li>
         <li>ตั้ง <b>Series = RCPU</b> และ <b>Type = R04</b> แล้วกด <b>OK</b></li>
         <li>หน้าต่างยืนยันจะบอกว่าโปรแกรมและพารามิเตอร์จะถูกย้ายไปด้วย กด <b>OK</b></li>
         <li>จากนั้นใช้ <b>Project → Save As</b> บันทึกเป็นไฟล์ใหม่ เช่น <code>test_r04.gx3</code></li></ol>
         <div class="note">💡 ถ้าเริ่มโปรเจกต์ใหม่ ให้เลือก Series = RCPU และ Type = R04 ตั้งแต่ตอน Project → New</div>""",
         [("01_project_menu.png", "300px"), ("02_change_type.png", "330px"), ("03_confirm.png", "330px")]),
        ("2", "อนุญาตให้โปรแกรมภายนอกเขียนค่า (SLMP)",
         """<ol><li>ที่หน้าต่าง <b>Navigation</b> ไปที่ <b>Parameter → R04CPU → Module Parameter</b> แล้วดับเบิลคลิก
         <br><span class="small">(ถ้าไม่เห็น Navigation ให้ไปที่ View → Docking Window → Navigation)</span></li>
         <li>ในหัวข้อ <b>Own Node Settings</b> หาบรรทัด <b>Enable/Disable Online Change</b></li>
         <li>เปลี่ยนจาก "Disable All (SLMP)" เป็น <b>"Enable All (SLMP)"</b> แล้วกด <b>Apply</b> ที่มุมขวาล่าง</li></ol>
         <div class="warn">⚠️ ถ้าไม่ตั้งค่านี้ PLC Trainer จะอ่านค่าได้ แต่กดปุ่ม X แล้วจะไม่มีผล</div>""",
         [("04_parameter.png", "100%")]),
        ("3", "Convert โปรแกรม",
         """<p>กด <b>F4</b> (Convert) ถ้ามีคำถามว่า <i>Rebuild All</i> ให้กด <b>Yes</b>
         รอจนคำว่า Project ในหน้าต่าง Navigation ไม่เป็นสีแดงแล้ว</p>""",
         [("05_rebuild.png", "330px")]),
        ("4", "เริ่ม Simulation",
         """<ol><li>ไปที่เมนู <b>Debug → Simulation → Start Simulation</b></li>
         <li>รอให้หน้าต่าง <i>Write to PLC</i> ทำงานเสร็จ แล้วกด Close</li>
         <li>หน้าต่าง <b>GX Simulator3</b> ต้องแสดง <b>R04CPU</b> สวิตช์อยู่ที่ <b>RUN</b> และไฟ <b>P RUN</b> เป็นสีเขียว</li></ol>
         <div class="note">ℹ️ ถ้าไฟ ERROR เป็นสีแดงแต่ P RUN ยังเขียวอยู่ ladder ก็ยังทำงานได้ตามปกติ
         (จากการทดสอบ ส่วนสาเหตุของไฟ ERROR ยังไม่ได้ตรวจสอบ)</div>""",
         [("06_sim_menu.png", "380px"), ("07_simulator.png", "220px")]),
        ("5", "(แนะนำ) เปิด Monitor ladder",
         """<p>ดับเบิลคลิก <b>Program → Scan → MAIN → ProgPou → ProgramBody</b>
         แล้วคลิกในหน้า ladder หนึ่งครั้งก่อนกด <b>F3</b> (Start Monitoring)
         จะเห็นหน้าสัมผัส คอยล์ และค่า T/C เปลี่ยนตามจริงไปพร้อมกับ PLC Trainer</p>""",
         [("08_monitor.png", "100%")]),
        ("6", "เชื่อมต่อจาก PLC Trainer",
         """<ol><li>เปิดไอคอน <b>PLC Trainer</b> บน Desktop</li>
         <li>ที่ Ribbon เลือกแหล่งเป็น <b>GX Simulator3 (SLMP)</b>, Host <code>127.0.0.1</code>, Port <code>5511</code></li>
         <li>กด <b>เชื่อมต่อ</b> ไฟ <b>ONLINE</b> ที่มุมขวาล่างต้องเป็นสีเขียว</li>
         <li>บนผังอุปกรณ์ (แท็บ Panel) คลิกปุ่ม <b>Start (X0)</b> แล้วดูว่าหลอด Y0 ทั้งในโปรแกรมและใน GX Works3 ติดตามกัน</li>
         <li>ถ้าจะจัดผังเอง กด <b>✎ แก้ไขผัง</b> แล้วลากอุปกรณ์จาก TOOL PALETTE มาวาง จากนั้นตั้ง Address ใน PROPERTIES ให้ตรงกับ ladder ของคุณ</li></ol>
         <div class="note">💡 iQ-R ใช้เลข X/Y ฐาน 16 ดังนั้นปุ่มที่ต่อกับ X8–XF ใช้ได้ (ช่อง Address จะเตือนถ้าพิมพ์เลขที่ไม่มีจริง)</div>""",
         [("09_trainer.png", "100%")]),
    ]

    body = []
    for num, title, html, images in steps:
        if num:
            body.append(f'<section><h2><span class="num">{num}</span>{title}</h2>')
        else:
            body.append("<section>")
        body.append(html)
        body.append('<div class="imgs">' + "".join(f"<figure>{img(n, w)}</figure>" for n, w in images) + "</div>")
        body.append("</section>")

    trouble = """
    <section class="trouble"><h2><span class="num">?</span>แก้ปัญหาที่พบบ่อย</h2>
    <table>
      <tr><th>อาการ</th><th>สาเหตุ / วิธีแก้</th></tr>
      <tr><td>เชื่อมต่อแล้วขึ้น timed out หรือ connection reset</td>
          <td>โปรเจกต์ยังเป็น FX5U ให้เปลี่ยนเป็น R04 ตามขั้นที่ 1 หรือยังไม่ได้กด Start Simulation</td></tr>
      <tr><td>อ่านค่าได้ แต่กด X แล้วไม่มีผล</td>
          <td>ยังไม่ได้ตั้ง <b>Enable All (SLMP)</b> ตามขั้นที่ 2 ตั้งแล้วอย่าลืม Apply, F4 และ Start Simulation ใหม่</td></tr>
      <tr><td>Y ติดค้างจากการทดสอบครั้งก่อน</td>
          <td>กด X1 (Stop) / X3 (Reset C0) หรือกด RESET ที่หน้าต่าง GX Simulator3</td></tr>
      <tr><td>ไม่แน่ใจว่าเชื่อมต่อได้หรือไม่</td>
          <td>รัน <code>.venv\\Scripts\\python tools\\probe_gx.py 5511</code> ในโฟลเดอร์โปรแกรม
              ถ้าขึ้น ✔ และ SM400 = [1] แปลว่าเชื่อมต่อได้</td></tr>
    </table>
    <p class="small">หมายเหตุ: iQ-R ใช้เลข X/Y ฐาน 16 (X0–XF, X10…) ส่วน FX5U ใช้ฐาน 8 (X0–X7, X10…)
    ถ้าใช้แค่ X0–X7 / Y0–Y7 ชื่อจะเหมือนกันทั้งสองแบบ</p>
    </section>"""

    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>คู่มือตั้งค่า GX Simulator3 สำหรับ PLC Trainer</title>
<style>
@page {{ size: A4; margin: 14mm 14mm 16mm; }}
body {{ font-family: "Leelawadee UI", "Tahoma", sans-serif; font-size: 11.5pt; color: #1d2430; line-height: 1.55; }}
header {{ background: #212830; color: #fff; padding: 18px 22px; border-left: 6px solid #1F8FD6; margin-bottom: 14px; }}
header h1 {{ margin: 0; font-size: 21pt; }}
header p {{ margin: 4px 0 0; color: #b9c3cf; font-size: 10.5pt; }}
.req {{ background: #eef5fb; border: 1px solid #c9dff0; padding: 8px 14px; margin-bottom: 10px; font-size: 10.5pt; }}
section {{ margin: 0 0 12px; }}
h2 {{ page-break-after: avoid; }}
figure {{ page-break-inside: avoid; }}
h2 {{ font-size: 14.5pt; margin: 14px 0 6px; color: #12324d; border-bottom: 2px solid #1F8FD6; padding-bottom: 3px; }}
.num {{ display: inline-block; background: #1F8FD6; color: #fff; width: 26px; height: 26px; line-height: 26px;
        text-align: center; border-radius: 50%; margin-right: 8px; font-size: 12pt; }}
ol {{ margin: 4px 0 6px 0; padding-left: 22px; }} li {{ margin: 2px 0; }}
code {{ background: #eef1f5; padding: 0 4px; border-radius: 3px; font-family: Consolas, monospace; font-size: 10pt; }}
.imgs {{ text-align: center; margin: 6px 0; }}
figure {{ display: inline-block; margin: 4px 6px; }}
figure img {{ border: 1px solid #9aa4b2; box-shadow: 0 1px 4px rgba(0,0,0,.18); }}
.note {{ background: #f3f8ec; border-left: 4px solid #5ea83a; padding: 6px 10px; margin: 6px 0; font-size: 10.5pt; }}
.warn {{ background: #fff6e5; border-left: 4px solid #e8a317; padding: 6px 10px; margin: 6px 0; font-size: 10.5pt; }}
.small {{ font-size: 9.5pt; color: #5b6676; }}
table {{ border-collapse: collapse; width: 100%; font-size: 10.5pt; }}
th, td {{ border: 1px solid #c4ccd6; padding: 5px 8px; vertical-align: top; text-align: left; }}
th {{ background: #212830; color: #fff; }}
</style></head><body>
<header><h1>คู่มือตั้งค่า GX Simulator3</h1>
<p>สำหรับเชื่อมต่อกับโปรแกรม PLC Trainer ผ่าน SLMP · ทดสอบกับ GX Works3 เวอร์ชัน 1.110Q</p></header>
<div class="req"><b>สิ่งที่ต้องมี:</b> GX Works3 (มี GX Simulator3 ติดมาด้วย) · โปรแกรม PLC Trainer
· โปรเจกต์ ladder ตัวอย่าง <code>gx_projects\\test_r04.gx3</code> (ตั้งค่าตามคู่มือนี้ไว้แล้ว สามารถเปิดแล้วข้ามไปขั้นที่ 4 ได้เลย)</div>
{''.join(body)}
{trouble}
</body></html>"""


def main():
    if "--crop-from" in sys.argv:
        crop_from(Path(sys.argv[sys.argv.index("--crop-from") + 1]))
    OUT_HTML.write_text(build_html(), encoding="utf-8")
    tmp = OUT_PDF.with_name("_tmp_print.pdf")
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
