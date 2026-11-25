"""M12: โหมดสอบ — รหัสครู pbkdf2, เวลา/สิทธิ์ตรวจ, ล็อก AI/แก้ผัง, กลับเข้าโหมดสอบหลังเปิดโปรแกรมใหม่."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.ui import exam, state  # noqa: E402
from plc_game.ui.exam import ExamSession, fmt_clock, hash_password, verify_password  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    monkeypatch.setattr(exam, "ITER", 1000)          # ทดสอบให้เร็ว
    return tmp_path


def test_password_hash():
    h = hash_password("ครู1234", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$") and "ครู1234" not in h
    assert verify_password("ครู1234", h)
    assert not verify_password("ครู1235", h)
    assert not verify_password("x", None) and not verify_password("x", "garbage")
    assert hash_password("a", iterations=1000) != hash_password("a", iterations=1000)   # salt สุ่ม


def test_session_limits():
    s = ExamSession.start(["01", "03"], minutes=10, max_checks=2, now=1000.0)
    assert s.remaining_s(1000 + 30) == 570 and not s.expired(1000 + 599) and s.expired(1000 + 600)
    assert s.can_check("01", 1001) == (True, "")
    assert not s.can_check("02", 1001)[0]                       # ไม่อยู่ในชุดข้อสอบ
    s.use_check("01")
    s.use_check("01")
    ok, why = s.can_check("01", 1001)
    assert not ok and "ครบ 2" in why and s.checks_left("01") == 0 and s.checks_left("03") == 2
    assert s.can_check("03", 2000) == (False, "หมดเวลาสอบแล้ว")
    s.record("01", 2)
    s.record("01", 1)
    assert s.best == {"01": 2} and s.total_stars() == 2
    s2 = ExamSession.from_dict(s.to_dict())
    assert s2 == s
    assert ExamSession.from_dict({"bad": 1}) is None
    unlimited = ExamSession.start(["01"], 5, 0, now=0)
    for _ in range(20):
        unlimited.use_check("01")
    assert unlimited.checks_left("01") is None and unlimited.can_check("01", 1)[0]
    with pytest.raises(ValueError):
        ExamSession.start([], 5, 1)
    assert fmt_clock(65.4) == "01:05"


class FakeRunner:
    def __init__(self, stars, ok):
        from plc_game.levels import CheckResult
        self.stars, self.score = stars, stars / 3
        self.results = [CheckResult("ข้อ 1", 0, 0, "expect", "กด Start → Y0 ON", ok, "" if ok else "Y0 = 0")]


class _FakePoller:
    def set_watch(self, *_a):
        pass

    def write_bit(self, *_a):
        pass

    def write_word(self, *_a):
        pass


def test_exam_mode_in_window(app, tmp_state, monkeypatch):
    from plc_game.ui.main_window import MainWindow
    classroom.upsert_student("66001", "สมชาย ใจดี")
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        w._set_student("66001")
        ids = [lv.id for lv in w.levelp.levels]
        state.update(teacher_pw=hash_password("1234"))
        w.start_exam(ExamSession.start(ids[:2], minutes=10, max_checks=1))
        # ล็อก
        assert w.exam and w.lbl_exam.isVisibleTo(w) and w.lbl_exam.text().startswith("📝 ")
        assert w.levelp.level.id == ids[0]                           # เปิดด่านแรกของชุดสอบให้เอง
        w.set_edit_mode(True)
        assert w.panel.sc.run_mode and not w.btn_edit.isEnabled()
        assert not w.ribbon.isTabEnabled(1) and not w.ribbon.isTabEnabled(4)
        assert not w.levelp.ai_enabled
        assert not w.btn_student.isEnabled() and not w.faults.isEnabled() and w.b_exam_end.isEnabled()
        n = len(w.panel.items_by_id)
        w._add_from_library("lamp")
        assert len(w.panel.items_by_id) == n
        w.open_level(2)                                              # ด่าน 3 ไม่อยู่ในชุดสอบ
        assert w.levelp.level.id == ids[0]
        assert state.load()["exam"]["level_ids"] == ids[:2]

        # สิทธิ์ตรวจ 1 ครั้ง
        started = []
        monkeypatch.setattr(w.levelp, "start", lambda *a: started.append(1) or True)
        w.poller, w.online = _FakePoller(), True
        w.start_check()
        w.start_check()
        assert started == [1] and w.exam.checks == {ids[0]: 1}
        assert "ตรวจได้อีก 0" in w.lbl_exam.text()

        # จบด่าน: บันทึกดาวในการสอบ + ไม่มีผล AI
        w.levelp.last_runner = FakeRunner(2, False)
        w.levelp.last_runner.trace = []
        w._on_level_finished()
        assert w.exam.best == {ids[0]: 2} and state.load()["exam"]["best"] == {ids[0]: 2}
        w.analyze_last()
        assert "ปิด AI" in w.levelp.ai.toPlainText()

        # หมดเวลา
        w.exam.started_at -= 11 * 60
        w._exam_tick()
        assert w._exam_over and "หมดเวลา" in w.lbl_exam.text() and w.sounds.played[-1] == "buzzer"
        w.open_level(1)
        w.start_check()
        assert started == [1]

        # รหัสผิดออกไม่ได้ / รหัสถูกออกได้
        assert not w.end_exam("0000") and w.exam
        assert w.end_exam("1234")
        assert w.exam is None and state.load()["exam"] is None
        assert w.btn_edit.isEnabled() and w.ribbon.isTabEnabled(1) and w.levelp.ai_enabled
        assert not w.lbl_exam.isVisibleTo(w)
    finally:
        w.poller = None
        w.dirty = False
        w.close()


def test_exam_resumes_after_restart(app, tmp_state):
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    ids = [lv.id for lv in w.levelp.levels]
    state.update(teacher_pw=hash_password("1234"))
    w.start_exam(ExamSession.start(ids[1:2], minutes=30, max_checks=3))
    w.dirty = False
    w.close()
    w2 = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        assert w2.exam and w2.exam.level_ids == ids[1:2] and w2.levelp.level.id == ids[1]
        assert not w2.btn_edit.isEnabled() and not w2.levelp.ai_enabled
        assert w2.end_exam("1234")
    finally:
        w2.dirty = False
        w2.close()
