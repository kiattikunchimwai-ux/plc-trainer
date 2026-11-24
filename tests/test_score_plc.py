"""คะแนนบอกว่าตรวจกับ PLC ไหน (ดาวไม่เปลี่ยน, คะแนนรุ่นเก่า = ไม่ทราบ)."""
import pytest

from test_classroom import FakeRunner, app, tmp_class  # noqa: F401

from plc_game import classroom
from plc_game.levels import load_all, scores
from plc_game.ui.exam import ExamSession

L1 = "01_self_hold"


def rec(stars, plc, sid="66001"):
    return scores.record(L1, FakeRunner(stars, stars == 3), sid, plc=plc)


def test_best_plc_follows_best_stars(tmp_class):  # noqa: F811
    assert rec(0, "mock")["best_stars"] == 0 and scores.best_plcs(scores.load()["66001"][L1]) == []
    assert scores.mock_only(rec(3, "mock"))
    st = rec(1, "slmp")                                   # ครั้งหลังแย่กว่า: ดาวดีที่สุดยังมาจาก Mock
    assert scores.mock_only(st) and st["last_plc"] == "slmp" and st["best_stars"] == 3
    st = rec(3, "soft")
    assert scores.best_plcs(st) == ["mock", "soft"] and not scores.mock_only(st)


def test_old_scores_are_unknown(tmp_class):  # noqa: F811
    old = {"66001": {L1: {"best_stars": 3, "best_score": 1.0, "attempts": 4}}}
    scores.save(old)
    assert scores.best_plcs(old["66001"][L1]) == [""] and classroom.plc_text(old["66001"][L1]) == "ไม่ทราบ"
    st = rec(1, "mock")
    assert st["best_stars"] == 3 and scores.best_plcs(st) == [""] and not scores.mock_only(st)
    assert scores.best_plcs(rec(3, "slmp")) == ["", "slmp"]


def test_exam_keeps_plc():
    s = ExamSession.start(["a"], 5, 0)
    s.record("a", 2, "mock")
    s.record("a", 1, "slmp")
    assert s.plc == {"a": "mock"}
    s.record("a", 2, "soft")
    s.record("a", 2, "mock")
    assert s.plc == {"a": "soft"} and ExamSession.from_dict(s.to_dict()) == s
    d = s.to_dict()
    d.pop("plc")                                          # สอบค้างจากรุ่นเก่า
    assert ExamSession.from_dict(d).plc == {}


def test_table_and_xlsx(app, tmp_class):  # noqa: F811
    from openpyxl import load_workbook

    from plc_game.ui.classroom_dlg import ScoreDialog
    rec(3, "mock", "66001")
    rec(3, "slmp", "66002")
    levels = load_all()
    dlg = ScoreDialog(levels)
    assert [dlg.table.item(r, 2).text() for r in (0, 1)] == ["★★★ Mock", "★★★"]
    assert "SLMP" in dlg.table.item(1, 2).toolTip() and dlg.table.item(0, 3).text() == "—"
    dlg.deleteLater()
    wb = load_workbook(classroom.export_xlsx(tmp_class / "x.xlsx", levels))
    ws = wb["สรุป"]
    assert ws["C3"].value == ws["C4"].value == 3 and ws["C3"].font.italic and not ws["C4"].font.italic
    assert "Mock PLC" in ws["C3"].comment.text and ws["D3"].comment is None
    rows = list(wb["รายข้อ"].iter_rows(values_only=True))
    assert rows[0][11:13] == ("PLC ล่าสุด", "PLC ที่ได้ดาวดีที่สุด") and rows[1][11:13] == ("Mock PLC", "Mock PLC")


@pytest.mark.parametrize("kind", ["mock", "soft", "slmp"])
def test_window_tags_runner(app, tmp_class, kind):  # noqa: F811
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": kind, "xy_base": 8})
    try:
        lp = w.levelp
        assert lp.plc == "none"
        lp.open_level(lp.levels[0])
        w._set_online(True)
        lp.start(lambda *a: None, lambda *a: None)
        r = lp.runner
        assert r.plc == kind
        lp.ai_enabled = False
        lp._finish()
        assert scores.load()["guest"][L1]["last_plc"] == kind
        w._set_online(False)
        assert lp.plc == "none"
        hunt = type("H", (), {"done": False, "results": [], "left": 3, "guesses_allowed": 3})()
        lp.start_hunt(hunt)
        assert hunt.plc == "none"
        w._set_online(True)                               # ต่อ PLC ระหว่างหา
        w._set_online(False)
        assert hunt.plc == kind
        lp.hunt = None
    finally:
        w.dirty = False
        w.close()
