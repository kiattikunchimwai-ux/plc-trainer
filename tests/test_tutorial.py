"""M12 บทเรียนนำทาง: overlay เจาะช่อง (mask), เดินครบทุกขั้นตามเงื่อนไข, ข้ามได้, จำว่าเคยดูแล้ว."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import CheckResult, scores  # noqa: E402
from plc_game.ui import state, tutorial  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    monkeypatch.setattr(tutorial, "DWELL_S", 0.0)
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "slmp", "xy_base": 8})
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


class _Runner:
    stars, score, trace = 3, 1.0, []
    results = [CheckResult("ข้อ 1", 0, 0, "expect", "x", True)]


def test_walk_all_steps(app, win):
    w = win
    t = w.start_tutorial()
    assert w.start_tutorial() is t                         # เรียกซ้ำไม่สร้างใหม่
    n = len(t.steps)
    assert t.index == 0 and t.isVisible() and t.hole.isEmpty()
    assert t.btn_next.text().startswith("ถัดไป")
    t.next()

    # ขั้น: เลือก Mock — ช่องเจาะตรงกับ combobox และคลิกผ่านได้ (ไม่อยู่ใน mask)
    assert t.index == 1
    t._tick()
    r = t.hole
    exp = w.cb_backend.rect().translated(w.cb_backend.mapTo(w, QPoint(0, 0)))
    assert r.contains(exp)
    assert not t.mask().contains(r.center()) and t.mask().contains(QPoint(2, r.bottom() + 40))
    t._tick()
    assert t.index == 1                                    # ยังไม่ทำ → ไม่ไปต่อ
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("mock"))
    t._tick()
    assert t.index == 2 and t.completed == [1]

    w.online = True                                        # ขั้น: เชื่อมต่อ
    t._tick()
    assert t.index == 3 and w.ribbon.currentIndex() == 2   # prepare เปิดแท็บด่านให้
    w.open_level(0)
    t._tick()
    assert t.index == 4
    w._history.append((0.0, {"Y0": 1}))                    # ขั้น: กด Start → Y0
    t._tick()
    assert t.index == 5 and w.ribbon.currentIndex() == 0
    w.set_split(True)
    t._tick()
    assert t.index == 6
    w.levelp.last_runner = _Runner()
    t._tick()
    assert t.index == n - 1 and t.btn_next.text().startswith("เสร็จสิ้น") and not t.btn_skip_all.isVisible()
    done = []
    t.finished.connect(done.append)
    t.next()
    assert done == [True] and w.tutorial is None and state.load()["tutorial_done"] is True
    w.online = False


def test_skip_and_exam_block(app, win):
    w = win
    t = w.start_tutorial()
    t.next()
    t.btn_next.click()                                     # "ข้ามขั้นนี้" ในขั้นที่มีเงื่อนไข
    assert t.index == 2
    t.btn_skip_all.click()
    assert w.tutorial is None and state.load()["tutorial_done"] is True and not t.isVisible()

    from plc_game.ui.exam import ExamSession, hash_password
    state.update(teacher_pw=hash_password("1234", iterations=1000))
    t2 = w.start_tutorial()
    w.start_exam(ExamSession.start([w.levelp.levels[0].id], 5, 1))
    assert w.tutorial is None and not t2.isVisible()      # เริ่มสอบ → ปิดบทเรียน
    assert w.start_tutorial() is None                      # ระหว่างสอบเปิดไม่ได้
    assert w.end_exam("1234")


def test_hidden_target_centers_bubble(app, win):
    w = win
    t = w.start_tutorial()
    t.goto(1)                                              # เป้าหมาย = combobox เลือก PLC
    t._tick()
    assert not t.hole.isEmpty()
    w.cb_backend.hide()                                    # เป้าหมายมองไม่เห็น → ไม่เจาะช่อง กล่องอยู่กลางจอ
    t._tick()
    assert t.hole.isEmpty() and t.mask().contains(t.rect().center())
    c = t.bubble.geometry().center()
    assert abs(c.x() - t.rect().center().x()) <= 2 and abs(c.y() - t.rect().center().y()) <= 2
    w.cb_backend.show()
    t.finish(False)
