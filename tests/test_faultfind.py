"""M12 ด่าน 14 หาจุดเสีย: สุ่มจุดเสียแบบซ่อน, ทายอุปกรณ์+อาการ, ให้ดาว, เฉลย, ล้างเมื่อเปลี่ยนด่าน."""
import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import FaultHunt, load_all, scores  # noqa: E402
from plc_game.levels.engine import load_level  # noqa: E402
from plc_game.panel import PanelDoc  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402

LV = next(lv for lv in load_all() if lv.id == "14_fault_find")


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
    return tmp_path


def panel_items(app):
    from plc_game.ui.panel.view import PanelView
    v = PanelView()
    v.load_doc(PanelDoc.load(LV.panel))
    return v, {it.label: dict(it.FAULTS) for it in v.fault_items() if it.label}


def test_level_loads(app):
    assert LV.is_fault_hunt and LV.checks == 0 and LV.faults.guesses == 3
    _, items = panel_items(app)
    for label, codes in LV.faults.pool:                 # ทุกรายการใน pool มีบนผังจริงและรองรับรหัสนั้น
        assert label in items, label
        assert set(codes) <= set(items[label]), label


def test_yaml_errors(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("id: x\nfaults: {pool: []}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pool"):
        load_level(p)
    p.write_text("id: x\nfaults: {pool: [{device: A}]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="codes"):
        load_level(p)


def test_random_pick_only_from_panel(app):
    _, items = panel_items(app)
    seen = {FaultHunt(LV, items, random.Random(s)).answer for s in range(60)}
    valid = {(lab, c) for lab, codes in LV.faults.pool for c in codes}
    assert seen <= valid and len(seen) >= 6
    with pytest.raises(ValueError, match="ไม่มีอุปกรณ์"):
        FaultHunt(LV, {"อื่น": {"burnt": "x"}})


def _hunt(app, answer):
    _, items = panel_items(app)
    h = FaultHunt(LV, items, random.Random(0))
    h.answer = answer
    return h


def test_scoring(app):
    h = _hunt(app, ("Stop", "wire_break"))
    r = h.guess("Stop", "wire_break")
    assert r.passed and h.done and h.found and h.stars == 3 and h.score == 1

    h = _hunt(app, ("Stop", "wire_break"))
    r = h.guess("Stop", "stuck_on")
    assert not r.passed and "อุปกรณ์ถูก" in r.detail and not h.done and h.left == 2
    h.guess("Stop", "wire_break")
    assert h.found and h.stars == 2

    h = _hunt(app, ("ไฟปั๊ม", "burnt"))
    for lab in ("Start", "Stop", "ปั๊มน้ำมัน"):
        r = h.guess(lab, "stuck_on" if lab != "ปั๊มน้ำมัน" else "jammed")
        assert r.detail == "อุปกรณ์นี้ปกติ"
    assert h.done and not h.found and h.stars == 0 and "ไฟปั๊ม" in h.answer_text() and "ไฟไม่ติด" in h.hint()
    with pytest.raises(ValueError):
        h.guess("ไฟปั๊ม", "burnt")


def test_scores_record(app, tmp_path):
    h = _hunt(app, ("Start", "stuck_on"))
    h.guess("Start", "wire_break")
    h.guess("Start", "stuck_on")
    st = scores.record(LV.id, h, "66001", tmp_path / "s.json")
    assert st["best_stars"] == 2 and len(st["last_detail"]) == 2 and st["last_detail"][1]["passed"]


def test_hunt_in_window(app, tmp_state):
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        idx = [lv.id for lv in w.levelp.levels].index(LV.id)
        w.open_level(idx)
        assert w.levelp.btn_check.text().endswith("เริ่มหาจุดเสีย")
        w.start_check()                                       # ไม่ต้องเชื่อม PLC ก็เริ่มได้
        h = w.levelp.hunt
        assert h is not None and w.panel.guess_enabled and w.panel.sc.faults_hidden
        broken = [it for it in w.panel.fault_items() if it.fault]
        assert len(broken) == 1 and (broken[0].label, broken[0].fault) == h.answer
        lab, code = h.answer
        wrong = next(it for it in w.panel.fault_items() if it.label != lab)
        w.cmd_input.setText(f"GUESS {wrong.label} {next(iter(wrong.FAULTS)).upper()}")
        w._on_command()
        assert len(h.results) == 1 and not h.results[0].passed and w.sounds.played[-1:] == ["fail"]
        w.panel.fault_guessed.emit(broken[0], code)           # เหมือนเลือกจากเมนูคลิกขวา
        assert w.levelp.hunt is None and w.levelp.last_hunt is h and h.stars == 2
        assert not w.panel.sc.faults_hidden and not w.panel.guess_enabled and broken[0].fault == code   # เฉลย
        assert "จุดเสีย" in w.levelp.ai.toPlainText() and w.sounds.played[-1] == "pass"
        assert scores.best_stars()[LV.id] == 2
        assert w.cb_level.itemText(idx).startswith("★★☆")

        w.start_check()                                       # รอบใหม่ = ล้างจุดเดิม สุ่มใหม่
        assert sum(bool(it.fault) for it in w.panel.fault_items()) == 1 and w.levelp.hunt is not None
        w.stop_check()
        assert w.levelp.hunt is None and not any(it.fault for it in w.panel.fault_items())
        assert not w.panel.sc.faults_hidden

        w.start_check()
        w.open_level(0)                                       # เปลี่ยนด่าน → ล้างการหาจุดเสีย
        assert w.levelp.hunt is None and not w.panel.guess_enabled
        assert not any(it.fault for it in w.panel.fault_items())
    finally:
        w.dirty = False
        w.close()


def test_hunt_counts_as_exam_check(app, tmp_state):
    from plc_game.ui.exam import ExamSession, hash_password
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        state.update(teacher_pw=hash_password("1234", iterations=1000))
        w.start_exam(ExamSession.start([LV.id], minutes=10, max_checks=1))
        assert w.levelp.level.id == LV.id
        w.start_check()
        assert w.exam.checks == {LV.id: 1} and w.levelp.hunt is not None
        lab, code = w.levelp.hunt.answer
        w._on_fault_guessed(w.panel.find_item(lab), code)
        assert w.exam.best == {LV.id: 3}
        w.start_check()
        assert w.levelp.hunt is None                          # ครบสิทธิ์แล้ว
        assert w.end_exam("1234")
    finally:
        w.dirty = False
        w.close()
