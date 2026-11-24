"""M8: รายชื่อนักเรียน, ตารางคะแนนทั้งห้อง, Export .xlsx, ลงชื่อใน MainWindow, HMI เต็มจอ, เสียง."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import load_all, scores  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_class(tmp_path, monkeypatch):
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    return tmp_path


class FakeRunner:
    def __init__(self, stars, ok):
        from plc_game.levels import CheckResult
        self.stars, self.score = stars, stars / 3
        self.results = [CheckResult("ข้อ 1", 0, 0, "expect", "กด Start → Y0 ON", ok, "" if ok else "Y0 = 0 (ต้อง = 1)")]


def _seed():
    classroom.upsert_student("66001", "สมชาย ใจดี")
    classroom.upsert_student("66002", "สมหญิง รักเรียน")
    scores.record("01_self_hold", FakeRunner(3, True), "66001")
    scores.record("01_self_hold", FakeRunner(1, False), "66002")
    scores.record("02_interlock", FakeRunner(2, False), "66002")
    scores.record("01_self_hold", FakeRunner(3, True), scores.GUEST)


def test_students_roundtrip(tmp_class):
    assert classroom.load_students() == []
    s = classroom.upsert_student(" 66-001 ", "ก ข")
    assert s.sid == "66-001"
    classroom.upsert_student("66-001", "")                      # ไม่ใส่ชื่อ = ใช้ชื่อเดิม
    classroom.upsert_student("66/002!", "ค")                    # อักขระแปลกถูกตัดออก
    assert [(x.sid, x.name) for x in classroom.load_students()] == [("66-001", "ก ข"), ("66002", "ค")]
    with pytest.raises(ValueError):
        classroom.upsert_student("ไทย", "x")
    with pytest.raises(ValueError):
        classroom.upsert_student("guest", "x")


def test_class_table(tmp_class):
    _seed()
    scores.record("01_self_hold", FakeRunner(2, False), "99999")   # มีคะแนนแต่ไม่อยู่ในรายชื่อ
    levels = load_all()
    headers, rows = classroom.class_table(levels)
    assert headers[:3] == ["รหัส", "ชื่อ", "1"] and headers[-3:] == ["รวมดาว", "ผ่าน★★★", "ตรวจ (ครั้ง)"]
    assert [r[0] for r in rows] == ["66001", "66002", "99999", "guest"]
    r1, r2 = rows[0], rows[1]
    assert r1[2] == 3 and r1[-3:] == [3, 1, 1]
    assert r2[2:4] == [1, 2] and r2[-3:] == [3, 0, 2]
    assert len(rows[0]) == 2 + len(levels) + 3


def test_export_xlsx_reads_back(tmp_class):
    from openpyxl import load_workbook
    _seed()
    levels = load_all()
    out = classroom.export_xlsx(tmp_class / "คะแนน.xlsx", levels)
    wb = load_workbook(out)
    assert wb.sheetnames == ["สรุป", "รายข้อ", "ข้อที่พลาดบ่อย"]
    ws = wb["สรุป"]
    assert ws.cell(1, 3).value == levels[0].title
    assert ws.cell(3, 1).value == "66001" and ws.cell(3, 2).value == "สมชาย ใจดี" and ws.cell(3, 3).value == 3
    assert ws.cell(4, 4).value == 2
    assert ws.cell(3, 3).fill.fgColor.rgb.endswith("B2F2BB")
    det = wb["รายข้อ"]
    rows = list(det.iter_rows(min_row=2, values_only=True))
    assert ("66002", "สมหญิง รักเรียน") in {r[:2] for r in rows}
    bad = [r for r in rows if r[0] == "66002" and r[9] == "ไม่ผ่าน"]
    assert len(bad) == 2 and bad[0][10] == "Y0 = 0 (ต้อง = 1)"


def test_sound_files_generated(tmp_path, monkeypatch, app):
    from plc_game.ui import sound
    monkeypatch.setattr(sound, "SOUND_DIR", tmp_path / "snd")
    s = sound.Sounds()
    assert set(s.files) >= {"pass", "fail", "buzzer"} and all(p.stat().st_size > 500 for p in s.files.values())
    s.play("pass")
    s.enabled = False
    s.play("fail")
    assert s.played == ["pass"]


def test_main_window_login_hmi_sound(app, tmp_class):
    from plc_game.ui.main_window import MainWindow
    _seed()
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        assert w.levelp.student == scores.GUEST
        w._set_student("66002")
        assert w.levelp.student == "66002" and "สมหญิง" in w.btn_student.text()
        assert state.load()["student"] == "66002"
        assert w.cb_level.itemText(0).startswith("★☆☆")           # ดาวของคนที่ลงชื่อ
        w._set_student("nobody")                                   # ไม่มีในรายชื่อ → guest
        assert w.levelp.student == scores.GUEST

        w.set_split(True)
        w.set_hmi(True)
        assert w.hmi and w.menuWidget().isHidden() and w.statusBar().isHidden() and w.cmd_bar.isHidden()
        assert not w.side_l.pane.isVisible() and w.panel.isVisible()
        w.set_hmi(False)
        assert not w.hmi and not w.menuWidget().isHidden() and not w.statusBar().isHidden()
        assert w.btn_split.isChecked()                             # กลับมาแบ่งจอเหมือนเดิม

        w.st_sound.setChecked(False)
        assert not w.sounds.enabled and state.load()["sound"] is False
        w.st_sound.setChecked(True)
        w.levelp.last_runner = FakeRunner(3, True)
        w.levelp.level = w.levelp.levels[0]
        w.levelp.last_runner.trace = []
        w._on_level_finished()
        assert w.sounds.played[-1] == "pass"
        dlg = w.show_scores()
        assert dlg.table.rowCount() == 3 and dlg.table.item(0, 0).text() == "66001"   # 2 คน + guest
        out = dlg.export(str(tmp_class / "x.xlsx"))
        assert out and out.exists()
        dlg.close()
    finally:
        w.dirty = False
        w.close()
