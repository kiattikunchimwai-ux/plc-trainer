"""รายงานข้อที่พลาดบ่อย + ข้อสังเกต ladder ใน Excel + บทเรียน ladder."""
import time

from PySide6.QtWidgets import QApplication

from test_classroom import FakeRunner, _seed, app, tmp_class  # noqa: F401
from test_tutorial import win  # noqa: F401

from plc_game import classroom
from plc_game.levels import CheckResult, load_all, scores
from plc_game.ladder.editor import rungs_from_text

L1 = "01_self_hold"


def test_weak_points_counts_latest_and_ignores_guest_and_skipped(tmp_class):  # noqa: F811
    _seed()
    scores.record(L1, FakeRunner(1, False), scores.GUEST)
    r = FakeRunner(0, False)
    r.results.append(CheckResult("ข้อ 2", 1, 0, "expect", "ข้าม", False, skipped=True))
    scores.record(L1, r, "66003")
    w = classroom.weak_points(load_all())
    assert w[0]["failed"] == ["66002", "66003"] and w[0]["tried"] == 3
    assert all(x["msg"] != "ข้าม" for x in w)
    scores.record(L1, FakeRunner(3, True), "66003")                # แก้ได้แล้ว = ไม่นับ
    assert all("66003" not in x["failed"] for x in classroom.weak_points(load_all()))
    assert classroom.weak_points(load_all(), {"a": None, "b": {L1: {"last_detail": ["x", {}]}}}) == []


def test_note_ladder_only_for_same_attempt(tmp_class):  # noqa: F811
    st = scores.record(L1, FakeRunner(1, False), "66001")
    key = f"{st['last_time']}#{st['attempts']}"
    assert scores.note_ladder(L1, "66001", ["a", "b", "c", "d"], key)
    got = scores.load()["66001"][L1]
    assert got["last_ladder"] == ["a", "b", "c"] and got["best_stars"] == 1
    assert not scores.note_ladder(L1, "66001", ["x"], "old") and not scores.note_ladder(L1, "nobody", ["x"], key)
    assert "last_ladder" not in scores.record(L1, FakeRunner(1, False), "66001")


def test_dialog_and_xlsx(app, tmp_class):  # noqa: F811
    from openpyxl import load_workbook

    from plc_game.ui.classroom_dlg import ScoreDialog
    _seed()
    st = scores.load()["66002"][L1]
    scores.note_ladder(L1, "66002", ["Y0 ไม่ ON"], f"{st['last_time']}#{st['attempts']}")
    dlg = ScoreDialog(load_all())
    assert dlg.tabs.count() == 2 and dlg.weak.rowCount() == 2 and dlg.weak.item(0, 3).text() == "1"
    dlg.deleteLater()
    wb = load_workbook(classroom.export_xlsx(tmp_class / "x.xlsx", load_all()))
    assert list(wb["ข้อที่พลาดบ่อย"].iter_rows(values_only=True))[0][3] == "พลาด (คน)"
    rows = list(wb["รายข้อ"].iter_rows(values_only=True))
    assert any(r[13] == "Y0 ไม่ ON" for r in rows[1:]) and "ladder" in rows[0][13]


def pump(cond, s=4):
    end = time.monotonic() + s
    while not cond() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    return cond()


def test_walk_ladder_tutorial(app, win):  # noqa: F811
    w = win
    w.ladderv.learn_requested.emit()
    t = w.tutorial
    n = len(t.steps)
    t.next()
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("soft"))
    t._tick()
    assert t.index == 2
    w.btn_connect.click()
    assert pump(lambda: w.online)
    t._tick()
    assert t.index == 3
    w.open_level(0)
    t._tick()
    assert t.index == 4 and w.ladderv.isVisible() and not t.hole.isEmpty()
    t._tick()
    assert t.index == 4                                            # ladder ว่าง: ยังไม่ไปต่อ
    v = w.ladderv
    v.doc.rungs = rungs_from_text("LD X0;OUT ?".replace("OUT ?", "OUT Y0"))
    leaf, coil = v.doc.rungs[0].body.cond.kids[0], v.doc.rungs[0].body.outs[0]
    coil.args = ("?",)
    v.after_edit()
    t._tick()
    assert t.index == 5
    t._tick()
    assert t.index == 5
    v.doc.set_coil(coil.uid, "OUT", ["Y0"])
    v.after_edit()
    t._tick()
    assert t.index == 6 and leaf.args == ("X0",)
    assert w.send_ladder()
    t._tick()
    assert t.index == 7
    w._history.append((0.0, {"X0": 1}))
    t._tick()
    assert t.index == 8
    t.next()
    assert t.index == n - 1
    t.next()
    assert w.tutorial is None
    w.btn_connect.click()
    pump(lambda: not w.online)


def test_ladder_tutorial_command_and_exam_lock(app, win):  # noqa: F811
    w = win
    assert w.start_tutorial(ladder=True).title == "บทเรียน ladder"
    w.tutorial.finish(False)
    w.exam = True
    assert w.start_tutorial(ladder=True) is None
    w.exam = None
