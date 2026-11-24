# คู่มือปล่อยโปรแกรมขึ้น GitHub Releases

**ตั้งแล้ว (2026-11-19):** repo https://github.com/kiattikunchimwai-ux/plc-trainer · เว็บ https://kiattikunchimwai-ux.github.io/plc-trainer/
**ทางลัดด้วย GitHub CLI** (ติดตั้งแล้ว `C:\Program Files\GitHub CLI\gh.exe`, ล็อกอินแล้ว) — หลังรัน make_release:
```
$gh="C:\Program Files\GitHub CLI\gh.exe"; $v="release\v<ver>"
& $gh release create v<ver> "$v\PLCTrainer-<ver>-win64.zip" "$v\version.json" "$v\SHA256SUMS.txt" --repo kiattikunchimwai-ux/plc-trainer --title "PLC Trainer v<ver>" --notes-file "$v\RELEASE_NOTES.md" --latest
.venv\Scripts\python.exe -I tools\gh_upload_site.py kiattikunchimwai-ux/plc-trainer release\repo "Release v<ver>"
.venv\Scripts\python.exe tools\make_release.py --check
```

ทำผ่านหน้าเว็บ GitHub ได้ทั้งหมด ไม่ต้องลง git · ซอร์สโค้ดยังอยู่ในเครื่องนี้เท่านั้น
repo สาธารณะมีแค่ README + ไฟล์แจก (zip) ส่วนโปรแกรมเช็กเวอร์ชันใหม่จากลิงก์คงที่
`https://github.com/<owner>/<repo>/releases/latest/download/version.json`

## ครั้งแรก (ทำครั้งเดียว)
1. สมัคร/ล็อกอิน https://github.com → มุมขวาบน **+** → **New repository**
   - Repository name เช่น `plc-trainer` · เลือก **Public** · ติ๊ก *Add a README file* → **Create repository**
2. ในเครื่องนี้ รัน (แทน `<owner>` ด้วยชื่อบัญชี GitHub):
   ```
   .venv\Scripts\python.exe tools\make_release.py --repo <owner>/plc-trainer
   ```
   โปรแกรมจะเขียน `update_url` ลง `plc_game\config.yaml`, build .exe ใหม่ (ประมาณ 2–3 นาที)
   แล้ววางไฟล์ไว้ที่ `release\v<เวอร์ชัน>\` และ `release\repo\README.md`
3. หน้า repo → เปิดไฟล์ `README.md` → ✏ (Edit) → วางเนื้อหาจาก `release\repo\README.md` → **Commit changes**
4. ทำขั้น "ปล่อยแต่ละเวอร์ชัน" ข้อ 3–5 ด้านล่าง

## ปล่อยแต่ละเวอร์ชัน
1. แก้เลขใน `plc_game\__init__.py` (`__version__ = "1.0.1"`) — ต้องมากกว่ารุ่นที่ปล่อยไปแล้ว
2. เพิ่มหัวข้อใหม่ด้านบนสุดของ `CHANGELOG.md` (`## 1.0.1 — ปี-เดือน-วัน` + `### th` + `### en`)
   ข้อแรกของแต่ละภาษาจะขึ้นในหน้า About ของผู้ใช้ตอนกดเช็กเวอร์ชัน
3. รัน `.venv\Scripts\python.exe -m pytest -q` ให้ผ่านก่อน แล้ว
   `.venv\Scripts\python.exe tools\make_release.py`
4. GitHub → repo → **Releases** (แถบขวา) → **Draft a new release**
   - **Choose a tag** → พิมพ์ `v1.0.1` → *Create new tag*
   - Title: `PLC Trainer v1.0.1` · Description: คัดจาก `release\v1.0.1\RELEASE_NOTES.md`
   - ลากไฟล์ 3 ไฟล์มาวาง: `PLCTrainer-1.0.1-win64.zip`, `version.json`, `SHA256SUMS.txt`
   - ติ๊ก **Set as the latest release** → **Publish release**
5. ตรวจว่าผู้ใช้จะเห็นรุ่นใหม่: `.venv\Scripts\python.exe tools\make_release.py --check`
   (ต้องขึ้น ✔ และเลขเวอร์ชันตรงกัน)

## เว็บของโปรแกรม (GitHub Pages — ฟรี)
แม่แบบอยู่ที่ `site\index.html` + `site\img\` (ธีมเดียวกับโปรแกรม สองภาษา) — `make_release.py` เติมชื่อ repo/เวอร์ชัน/ขนาด
แล้ววางไว้ที่ `release\repo\index.html` + `release\repo\img\`
1. ครั้งแรก: หน้า repo → **Add file → Upload files** → ลาก `index.html` และโฟลเดอร์ `img` จาก `release\repo\` → Commit
2. **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main` / `(root)` → Save
3. รอ 1–2 นาที เว็บจะอยู่ที่ `https://<owner>.github.io/<repo>/`
4. ทุกครั้งที่ปล่อยเวอร์ชันใหม่ อัปโหลด `index.html` ที่สร้างใหม่ทับ (เลขเวอร์ชัน/ขนาดในหน้าเว็บจะได้ตรง)

**ชื่อโดเมนของตัวเอง (ไม่บังคับ):** ซื้อโดเมน เช่น `.com` (ประมาณ 400–600 บาท/ปี) → Settings → Pages → Custom domain
ใส่ชื่อโดเมน → ที่ผู้ขายโดเมนตั้ง DNS ตามที่ GitHub บอก (CNAME ไปที่ `<owner>.github.io`) → ติ๊ก *Enforce HTTPS*
แล้วสร้างไฟล์ `site\CNAME` (ข้างในมีแค่ชื่อโดเมน) เพื่อให้ make_release คัดไปด้วยทุกครั้ง
ลิงก์ดาวน์โหลดและปุ่มเช็กเวอร์ชันยังชี้ GitHub Releases เหมือนเดิม ไม่ต้องแก้อะไรในโปรแกรม

## หมายเหตุ
- **อย่าลบ** `version.json` ออกจาก release ล่าสุด — ไม่งั้นปุ่มเช็กเวอร์ชันของทุกคนจะขึ้นว่าเช็กไม่ได้
- ไฟล์แนบใน release ใหญ่ได้ถึง 2 GB ต่อไฟล์ (zip ของเรา ~75 MB) และฟรี
- Windows SmartScreen จะเตือนเพราะยังไม่ได้ซื้อใบรับรองเซ็นโค้ด — ใน README/Release notes มีวิธีกด *Run anyway* ไว้แล้ว
- ถ้าปล่อยผิด: แก้ไข release เดิมแล้วแทนไฟล์ได้ หรือปล่อยเลขใหม่ทับ (เช่น 1.0.2)
- itch.io (ไม่บังคับ): สร้างหน้า → อัปโหลด zip เดียวกัน · ใช้ข้อความจาก `release\repo\README.md`
  (ปุ่มเช็กเวอร์ชันยังชี้ GitHub เหมือนเดิม)
