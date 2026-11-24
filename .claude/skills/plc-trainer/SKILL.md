---
name: plc-trainer
description: ทำงานต่อกับโปรเจกต์ PLC Trainer (เกมสอน PLC ปวช.3 — Python + PySide6 + pyqtgraph คุยกับ GX Simulator3 ผ่าน SLMP) ในโฟลเดอร์ E:\PLC\Study Program PLC. ใช้เมื่อผู้ใช้สั่ง "ทำต่อ", เพิ่มด่าน/อุปกรณ์/ฟีเจอร์, แก้บั๊ก, หรือ "เทสหน่อย" กับโปรแกรมนี้.
---

# PLC Trainer — วิธีทำงานต่อ

## กฎจากผู้ใช้ (ห้ามละเมิด)
- **ตรวจด่านจากผล I/O (black-box) เท่านั้น** — ห้ามบังคับรูปแบบ ladder; ladder จาก CSV (`plc_game/ladder`) ใช้ **อธิบาย** ได้ ห้ามใช้ให้คะแนน และต้องปิดตอนสอบ
- ไฟล์ทุกอย่างอยู่ใน `E:\PLC\Study Program PLC` (venv `.venv`, แผนใน `docs/`); ไฟล์ชั่วคราวไว้ scratchpad
- ธีม AutoCAD + game (ใช้ `plc_game/ui/theme.py`), ข้อความ UI/ข้อความด่านเขียนเป็นภาษาไทย **และต้องมีคำแปลอังกฤษ** (ดู "หลายภาษา" ด้านล่าง)
- "เทสหน่อย" = pytest **และ** e2e บนหน้าต่างจริงกับ Mock PLC พร้อมภาพหน้าจอ
- ทำทีละโมดูล จบแต่ละงานแล้วรายงานและถามก่อนเริ่มงานใหญ่ถัดไป (ผู้ใช้ชอบหยุดเป็นช่วง ๆ)
- ทดสอบกับ GX Simulator3 จริง (คุม GX Works3 ผ่าน `tools/gui.py`, `tools/gx.py`) **ทำเมื่อผู้ใช้สั่งเท่านั้น** และเตือนให้ไม่แตะเมาส์/คีย์บอร์ดก่อน. เฉพาะโปรเจกต์ RCPU (`gx_projects/test_r04.gx3`) ที่ตอบ SLMP พอร์ต 5511

## โครงสร้าง
- `plc_game/plc/` — `create_client` (slmp | mock | soft), `MockPLC.program(mem, now, ctx)` แทน ladder, `parse_device`, `poller.PLCPoller`
- `plc_game/levels/engine.py` — YAML ด่าน: steps `set/pulse/word/wait/part/expect/hold/waitfor`; `LevelRunner.feed(snap,t)`; `CheckResult` (t_start/t_end, conds, targets); `expected_segments`, `fail_spans` (กราฟผลตรวจ); `scores.py` → `panels/scores.json` {student:{level:{...}}} (`by_plc` / `last_plc` = ตรวจกับ mock/soft/slmp/none, "" = ไม่ทราบ; บอกที่มาเท่านั้น ไม่มีผลต่อดาว)
- `levels/NN_name.yaml` + `.plcpanel` — ผังด่านสร้างจาก `LEVEL_PANELS` / `_variant()` ใน `tools/make_example_panels.py`
- เพิ่มอุปกรณ์ใหม่ 1 ชนิด = แก้ 8 จุด: `panel/catalog.py` (KindInfo), `panel/specs.py`, `panel/presets.py` (≥1 รุ่น), `panel/knowledge.py` (KNOW), `panel/wiring.py` (COIL/CONTACTOR), `ai/analyzer.py` (กฎ black-box ถ้ามี), `panel/physics.py` (สูตรไม่ใช้ Qt), คลาสใน `ui/panel/items_ext3.py` (R5) + `CLASSES`; เทสใน `tests/test_devices_r5.py`; วาดภาพตรวจด้วยสคริปต์ใน scratchpad (platform ปกติ) แล้ว Read ดู
- `plc_game/ui/panel/` — `items.py`, `items_ext.py`, `items_ext2.py`, `items_ext3.py` (DeviceItem: `paint_body/paint_caption/apply_snapshot/tick/input_signals/emit_bit`), `paintkit.py` (ตัวช่วยวาดสมจริง), `specs/presets/physics`, `view.PanelView`
- `plc_game/ui/main_window.py` — top bar, ribbon (หน้าแรก/แก้ไขผัง/ด่าน/ครู/AI), SideDock ซ้ายขวา, command line (`_on_command` + `HELP`), status bar
- `plc_game/ui/chart_widget.py` — timing + trend; result mode `show_level_result/focus_time/exit_result`
- `plc_game/ui/level_dock.py` (ด่าน/ผลตรวจ/AI, `jump_requested`), `fault_dock.py`, `iolist_dock.py`, `quickstart.py`
- `plc_game/classroom.py` + `ui/classroom_dlg.py` (ลงชื่อ, ตารางคะแนน, Export xlsx), `ui/sound.py` (สร้าง WAV เอง)
- `plc_game/ladder/` — CSV ของ GX Works3 (UTF-16 tab, operand ต่อแถว): `csvio` → `model.Ladder` → `sim.Sim` (3 ค่า 0/1/None — ไม่รู้ต้องเป็น None ไม่เดา) → `static` / `replay.diagnose` (เทียบที่วัดได้ก่อน ไม่ตรง = ไม่สรุป); UI ใน `ui/level_dock.py` (`_LadderWorker`); test ใช้ `tests/ladder_kit.py` (`play_slow` = SLMP ช้า — ต้องทดสอบด้วยเสมอ), e2e `tools/e2e_ladder.py` (docs/ladder_test/), ข้อมูลจริงจาก GX Simulator3 `tests/data/gx_csv/gx_trace_*.json` (tests/test_ladder_gx.py, บันทึกใหม่ด้วย `tools/compare_gx_ladder.py`; ถ้าเขียนได้ error 0x0055 = ยังไม่ตั้ง Enable All (SLMP)), คุม GX แบบปลอดภัย `tools/gx_sample/safe_gx.py`
- เขียน ladder ในโปรแกรม: `ladder/editor.py` (LadderDoc = tree อนุกรม/ขนาน ↔ คำสั่ง, ช่องว่าง = `BLANK` "?") → `ladder/check.py` (ตรวจก่อน RUN, `Problem(k, text)`) → `plc/soft_plc.py` (`SoftPLC(MockPLC)`, RUN/STOP/RESET, ข้อผิด → ERROR) ใช้ `ladder/runtime.py` (ต่อจาก `Sim`; ทุกค่ารู้แน่ เริ่ม 0 — อย่าแก้ให้กระทบโหมด 3 ค่าของ `Sim`) · UI `ui/ladder_view.py` (แท็บ Ladder, F4 → `MainWindow.send_ladder`), บันทึก `panels/ladders/<id>/<ด่าน>.csv` แยกโฟลเดอร์ตอนสอบ · tests `test_ladder_editor*.py`, `test_soft_plc*.py` (เฉลยอยู่ใน `tests/ladder_good.py` เท่านั้น ห้ามเข้า exe), e2e `tools/e2e_ladder_editor.py` (docs/ladder_editor_test/)
- `plc_game/ai/` — analyzer แบบกฎ (ออฟไลน์) + `llm.py` Claude (ต้องมี `anthropic` + `ANTHROPIC_API_KEY`)

## หลายภาษา (ไทย/อังกฤษ) — ทำทุกครั้งที่เพิ่มข้อความ
- ข้อความ UI ใหม่ครอบ `tr("ข้อความไทย {0}", x)` (`from ..i18n import tr`) — ข้อความไทยคือ key, placeholder ใช้ `{0}` ไม่ใช้ f-string
- ห้ามตัดสินใจจากข้อความที่แปลแล้ว (เทียบ/ใช้เป็น dict key) และห้ามใช้ `tr()` ใน default parameter — ตั้ง `""` แล้วแปลตอนรัน
- ข้อมูลจากผัง (label/text/unit/messages/ชื่อผัง) แปลตอนแสดงด้วย `tr_data()` / `item.shown_label` — `item.label` เป็นตัวระบุ (ด่านหาจุดเสีย/คำสั่ง) ห้ามแปล; คำที่ความหมายต่างจากในโค้ดใส่ `@คำ` ใน `i18n/extra_keys.txt`
- ด่าน YAML: ทุก `title/desc/name/msg/hint` ต้องมี `title_en/desc_en/name_en/msg_en/hint_en` (engine ใช้ `i18n.pick`, editor เก็บไว้ตอนบันทึก)
- จบงานรัน `tools\i18n_extract.py` → `--missing` ต้องว่าง (แปลแล้วรวมด้วย `tools\i18n_merge.py <file.json>`) · `--raw` ต้องว่าง (ข้อความไทยที่ตั้งใจไม่แปลใส่ `# i18n: skip`)
- ทดสอบ: `tests/test_i18n.py` (หน้าต่างอังกฤษรันในโปรเซสแยก), `PLC_LANG=pseudo` จับโค้ดที่พึ่งข้อความ, e2e `tools/e2e_i18n.py` (ภาพใน `docs/i18n_test/`)
- ภาษาเลือกครั้งเดียวตอน import (env `PLC_LANG` → ui_state `lang` → locale ระบบ) เปลี่ยนแล้วต้องเปิดใหม่; `i18n.apply_qt_locale()` ก่อน `super().__init__` ของ MainWindow (กัน Windows ตัวเลขไทย ๕๕๑๑)
- **.exe (D1)**: path ทุกตัวผ่าน `plc_game/paths.py` — ไฟล์มากับโปรแกรม `app_root()` (อ่านอย่างเดียว), ข้อมูลผู้ใช้ `data_dir()` / `levels_dir()` / `cache_dir()`, `config_path()`; ห้ามใช้ `Path(__file__).parents[..]` ใหม่ · ซอร์สโหมด = โฟลเดอร์โปรเจกต์เหมือนเดิม, .exe = `%APPDATA%\PLCTrainer` (`seed_user_dir()` คัดผังตัวอย่าง/ด่านที่ยังไม่มี)
- ด่าน/ผังของผู้ใช้ .exe: `paths.update_user_files()` แทนเฉพาะไฟล์ที่ตรงกับ `plc_game/shipped_hashes.json` (make_release จดแฮชจาก zip ที่แจกให้เอง — ต้องเก็บไฟล์นี้ไว้ ห้ามลบแฮชเก่า); ไฟล์ที่ผู้ใช้แก้และคู่ด่าน+ผังของมันไม่ถูกแตะ · `seed_user_dir` จด `seeded.json` ใน user_root — ด่าน .yaml ที่เคยคัดแล้วหายไป = ครูลบ ไม่คัดกลับ
- build: `.venv\Scripts\python.exe tools\build_exe.py` → `dist\PLCTrainer\` + zip; ไฟล์ข้อมูลใหม่ต้องเพิ่มใน `data_files()` · ทดสอบ exe: ตั้ง `PLCTRAINER_HOME` (scratchpad) แล้วรัน `PLCTrainer.exe --selftest report.json` (เชื่อม Mock → ด่าน 1 → CHECK → รายงาน+ภาพ) — ห้ามให้ exe เขียน %APPDATA% จริงตอนเทส
- เวอร์ชันอยู่ที่ `plc_game/__init__.py __version__`; About (`ui/about_dlg.py`, คำสั่ง ABOUT) เช็ก `update_url` ใน config.yaml เฉพาะตอนกดปุ่ม
- **ปล่อยเวอร์ชัน** (GitHub Releases, repo สาธารณะมีแค่ README+zip, ซอร์สไม่ขึ้น): แก้ `__version__` + หัวข้อใหม่ใน `CHANGELOG.md` (`## x.y.z — วันที่` / `### th` / `### en`, bullet แรก = โน้ตในหน้า About) → `tools\make_release.py [--repo owner/repo]` (ครั้งแรกเขียน update_url = `.../releases/latest/download/version.json` ลง config.yaml แล้ว build) → `release\v<ver>\` → อัปโหลดตาม `docs\release_guide.md` (ปล่อยจริงแล้ว v1.0.0: repo `kiattikunchimwai-ux/plc-trainer`, gh CLI ล็อกอินแล้ว — คำสั่งอยู่บนสุดของคู่มือ; ปล่อยสาธารณะต้องถามผู้ใช้ก่อนทุกครั้ง) → `make_release.py --check` · ห้ามรัน make_release ใน test โดยไม่ monkeypatch `CONFIG`/`DIST` (มันเขียน config.yaml จริง) · เว็บ: แม่แบบ `site/index.html` (ธีมจาก theme.py, ตัวแปร `__REPO__ __SITE__ __VERSION__ __SIZE_MB__`; รูปแชร์ลิงก์ `site/img/og.png` 1200×630 สร้างด้วย `tools/make_og_image.py`; og:image ต้องเป็นลิงก์เต็ม — ตัวแปรใหม่ต้องแก้ `render_site`) + `site/img/` → make_release วางที่ `release/repo/` สำหรับ GitHub Pages · `main.load_config` = config ที่มากับโปรแกรม + ทับด้วยค่าที่ไม่ว่างของผู้ใช้

## ขั้นตอนมาตรฐาน
1. เพิ่มด่าน: เขียน YAML (msg/hint ไทย) → ผังใน `LEVEL_PANELS` → สร้าง **เฉพาะไฟล์นั้น**: `.venv\Scripts\python.exe tools\make_example_panels.py 07_traffic.plcpanel` (ห้ามรันแบบไม่ใส่ชื่อ — ทับผังที่ผู้ใช้แก้)
2. เพิ่ม test ใน `tests/test_levels.py`: ladder จำลองที่ถูก (`GOOD`) ต้องได้ 3 ดาว + แบบผิด (`BAD`) ต้องตก; ใช้ `run()` (MockPLC + PanelView + นาฬิกาปลอม); เวลาตรวจ ≤ 60 s
3. `.venv\Scripts\python.exe -m pytest -q` (ปัจจุบัน 1292 ข้อผ่าน, ~3 นาทีครึ่ง, exit code ต้องเป็น 0)
4. e2e: คัด `scripts/e2e_template.py` ไป scratchpad แล้วแก้ขั้นตอน; รันด้วย `$env:PYTHONIOENCODING="utf-8"` และ platform ปกติ (offscreen ทำให้อักษรไทยเป็นสี่เหลี่ยม); ดูภาพหน้าจอด้วย Read
5. อัปเดต memory `plc-game-project` เมื่อจบงาน

## กับดักที่เจอแล้ว
- แก้ `spec.props` ใน script ต้องเรียก `w.panel.item_props_changed(item)` ไม่งั้น `slot_ok` ค้าง
- ห้ามตั้งชื่อ attribute ของ DeviceItem ชนเมธอด Qt (`self.x`, `self.y` …)
- ห้ามเปลี่ยนขนาด `body_rect` ของอุปกรณ์เดิม (ผังเก่าจะเพี้ยน)
- e2e ที่เปลี่ยน ladder ของ Mock หลายช่วง: Mock จำค่า Y/D เดิมไว้ → ตอนเปลี่ยน ladder ให้เขียน 0 ทับเอาต์พุตที่ ladder เป็นเจ้าของก่อน (ดู `OUTS` ใน `tools/e2e_devices_r5.py`) ไม่งั้นไม่เกิดขอบขาขึ้น/ลง
- e2e ต้องสำรอง/คืน `panels/ui_state.json`, `scores.json`, `students.json` แบบ byte ต่อ byte
- test ที่สร้าง MainWindow ต้อง monkeypatch `state.PANEL_DIR/STATE_FILE/_OLD_LAST`, `sidebar.ANIMATE=False`, และ `classroom.STUDENT_FILE`, `scores.SCORE_FILE`
- `MockPLC`: `mem["X"][n]` ใช้ index จริง (ไม่ใช่ฐาน 8); ตั้ง `cli.program, cli._ctx = prog, {}` เพื่อเปลี่ยน ladder ใน e2e
- เปลี่ยนผัง/เริ่มตรวจต้องเขียนค่า input ของผังลง PLC ใหม่ (`_write_input_states`) — แก้แล้ว อย่าถอดออก
- ฟิสิกส์ช้าเกินในด่าน → ลด `travel_s`/`tau_s` ในผังของด่าน ไม่แก้ physics

## งานที่ทำแล้ว / ค้าง (รายการค้างล่าสุดดู memory `ladder-editor-progress`)
- **M12**: ~~โหมดสอบ `ui/exam.py`~~ ✔ 2026-11-18 (tests/test_exam.py, tools/e2e_exam.py 11/11; ระหว่างสอบใช้ `self._exam_locked("…")` กันทุกทางที่แก้ผัง/ใช้ AI) · ~~ด่าน 14 หาจุดเสีย~~ ✔ 2026-11-18 (`levels/faultfind.py`, tests/test_faultfind.py, tools/e2e_faultfind.py 7/7; ด่านแบบ `faults:` ไม่มี cases → test_levels ข้ามใน GOOD; ใช้ `levelp.busy` แทน `levelp.runner` เมื่อต้องรู้ว่ากำลังตรวจ/หาจุดเสีย) · ~~บทเรียนนำทาง~~ ✔ 2026-11-18 (`ui/tutorial.py`, tests/test_tutorial.py, tools/e2e_tutorial.py 14/14; เปิดเองครั้งแรกจาก `main.py` เท่านั้น — e2e ที่สร้าง MainWindow ตรง ๆ ไม่โดน) → **M12 ครบแล้ว**
- ~~ทดสอบ GX Simulator3 จริง~~ ✔ 2026-11-18: `tools/e2e_gx_slmp.py` 4/4, ภาพใน `docs/gx_test/` (ถ้า sim ค้าง STOP/SD0=2200H → หน้าต่าง GX Simulator3: STOP → RESET → RUN) · ยังไม่ได้ดู: poll ได้ 13 Hz กับ SLMP (ตั้ง 50 ms)
- ~~M11 ตัวแก้ไขด่านของครู~~ ✔ 2026-11-18: `levels/editor.py` (LevelDraft ไม่ใช้ Qt) + `ui/level_editor.py`; tests/test_level_editor.py, tools/e2e_level_editor.py 11/11 (ทำกับสำเนา levels/ ผ่าน `LevelPanel.folder` — test/e2e ห้ามเขียน levels/ จริง)
- ~~M7 สื่อการสอน~~ ✔ 2026-11-18: แท็บ "สื่อการสอน" (ต่อท้ายสุด — อย่าแทรก index แท็บเดิม) · `panel/knowledge.py` (ชนิดใหม่ต้องเพิ่ม KNOW ไม่งั้น test ตก) · `panel/wiring.py` + `ui/wiring_view.py` · กราฟ A/B + Export · `panel/macro.py` + `ui/macro_ctl.py` (.plcmacro → ด่าน); tests/test_teaching.py, tools/e2e_teaching.py 11/11
- ChartWidget ที่สร้างลอย ๆ ใน test ต้อง `shutdown()` + `deleteLater()` ก่อนจบ
- แผนเดิมครบทุก milestone แล้ว
- ~~poll 13 Hz~~ ✔ 2026-11-18: GX Simulator3 ตอบ SLMP เป็นช่วงทุก ~100 ms (ข้อจำกัดของ sim) · แก้ poller ให้แปะเวลาตอนข้อมูลมาถึง (tests/test_poller.py) — test ห้ามสร้าง QCoreApplication (test ถัดไปที่สร้าง widget จะ crash) ใช้ QApplication เสมอ
- ~~crash ตอนปิด pytest~~ ✔ 2026-11-18 (0/30 รอบ): ห้ามให้ widget เป็น event filter ระดับแอป (`QApplication.installEventFilter(self)`) — ใช้ QObject ลูกตัวแรกแบบ `MainWindow._KeyFilter`; pyqtgraph ต้อง `ChartWidget.shutdown()` (view.close) ก่อนลบ — `MainWindow.shutdown()` เรียกจาก closeEvent; ChartWidget รับเมนู/QWidget ไม่มี parent ของ pyqtgraph เป็นลูก; `tests/conftest.py` ตอนจบ session เรียก shutdown() แล้วลบ widget ที่ค้าง · วิธีหา: `-X faulthandler -p no:faulthandler` + ลบทีละตัวพร้อม `sys.setprofile` ดูว่า Python ตัวไหนถูกเรียกก่อน abort
- แผนรอบล่าสุด: `~/.claude/plans/zippy-hopping-hamming.md` (โดเนท → ภาษาอังกฤษ → .exe)
- โดเนท ✔ 2026-11-18: `plc_game/support.py` + `support.json` (ห้ามใส่เลขพร้อมเพย์จริงเอง — ผู้ใช้ใส่), `ui/support_dlg.py`; test/e2e ต้องชี้ `support.SUPPORT_FILE` ไปไฟล์ชั่วคราวและสำรอง/คืน ui_state (คีย์ `support_*`); tests/test_support.py, tools/e2e_support.py 8/8 (docs/support_test/)
