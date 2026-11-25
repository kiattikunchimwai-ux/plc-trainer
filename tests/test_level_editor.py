"""M11 ตัวแก้ไขด่านของครู: แบบร่าง YAML ไป-กลับ, ตรวจความถูกต้อง, บันทึก/ทำสำเนา/ลบ (ถังขยะ), หน้าต่างแก้ไข."""
import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
import yaml  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import editor as E  # noqa: E402
from plc_game.levels import load_all, scores  # noqa: E402
from plc_game.levels.engine import LEVEL_DIR, load_level  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lvdir(tmp_path):
    d = tmp_path / "levels"
    shutil.copytree(LEVEL_DIR, d, ignore=shutil.ignore_patterns("_trash"))
    return d


def _sig(lv):
    return (lv.title, lv.desc, lv.idle, lv.checks, lv.faults,
            [[(s.op, s.addr, s.value, s.dur, [str(c) for c in s.conds], s.msg, s.hint) for s in c.steps]
             for c in lv.cases])


def test_roundtrip_all_levels(lvdir):
    for d in E.load_drafts(lvdir):
        orig = load_level(d.path)
        assert d.problems(lvdir) == [], d.id
        d.save(lvdir)                                   # เขียนทับด้วยตัวแก้ไข → โหลดได้ผลเดิม
        assert _sig(load_level(d.path)) == _sig(orig), d.id
        assert d.path.read_text(encoding="utf-8").startswith("#")   # คอมเมนต์ต้นไฟล์ยังอยู่


def test_problems_reported_in_thai(lvdir):
    d = E.new_draft(E.load_drafts(lvdir))
    assert d.problems(lvdir) == []
    d.id = "มีช่องว่าง x"
    d.title = ""
    d.cases[0].steps = [E.StepRow("expect", "Y0 = within"), E.StepRow("pulse", "X0 0.3")]
    d.reset = [E.StepRow("hold", "Y0 = 0 for 1")]
    d.panel = "ไม่มี.plcpanel"
    p = d.problems(lvdir)
    assert any("รหัสด่าน" in x for x in p) and any("ชื่อด่าน" in x for x in p)
    assert any("ข้อ 1 ขั้น 1" in x for x in p) and any("reset ขั้น 1" in x for x in p)
    assert any("ไม่พบไฟล์ผัง" in x for x in p)
    d2 = E.new_draft([])
    d2.cases[0].steps = [E.StepRow("pulse", "X0 0.3")]
    assert any("expect หรือ hold" in x for x in d2.problems(lvdir))
    assert any("ซ้ำ" in x for x in E.new_draft([]).problems(lvdir, others=["01_new"]))


def test_step_row_and_idle():
    s = E.StepRow.from_raw({"do": "expect Y0 = 1 within 0.5", "msg": "ก", "hint": "ข"})
    assert (s.op, s.params, s.msg, s.hint) == ("expect", "Y0 = 1 within 0.5", "ก", "ข") and s.is_check
    assert E.StepRow.from_raw("pulse X0 0.3").to_raw() == "pulse X0 0.3"
    assert E.text_to_idle("X0=0, X1=1 x10=1") == {"X0": 0, "X1": 1, "X10": 1}
    with pytest.raises(ValueError):
        E.text_to_idle("X0")
    assert E.idle_to_text({"X0": 0, "X1": 1}) == "X0=0, X1=1"


def test_save_rename_duplicate_trash(lvdir):
    ds = E.load_drafts(lvdir)
    d = next(x for x in ds if x.id == "01_self_hold")
    d.id = "01_renamed"
    d.save(lvdir)
    assert (lvdir / "01_renamed.yaml").exists() and not (lvdir / "01_self_hold.yaml").exists()
    assert list((lvdir / "_trash").glob("01_self_hold_*.yaml"))
    c = E.duplicate(d, ds)
    assert c.id == "01_renamed_copy" and c.path is None and c.order == 15
    c.save(lvdir)
    E.trash(c.path, lvdir)
    ids = [lv.id for lv in load_all(lvdir)]
    assert "01_renamed" in ids and "01_renamed_copy" not in ids and len(ids) == 14


def test_new_hunt_draft_saves(lvdir):
    d = E.new_draft(E.load_drafts(lvdir), hunt=True)
    d.panel = "14_fault_find.plcpanel"
    assert any("รายการอุปกรณ์" in x for x in d.problems(lvdir))
    d.pool = [("Start", ["stuck_on"])]
    assert d.problems(lvdir) == []
    d.save(lvdir)
    lv = load_level(d.path)
    assert lv.is_fault_hunt and [(a, list(b)) for a, b in lv.faults.pool] == [("Start", ["stuck_on"])]
    data = yaml.safe_load(d.path.read_text(encoding="utf-8"))
    assert "cases" not in data and data["faults"]["guesses"] == 3


# ---------------- หน้าต่าง ----------------
def test_dialog_edit_and_save(app, lvdir, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from plc_game.ui.level_editor import LevelEditorDialog
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    dlg = LevelEditorDialog(folder=lvdir, select="03_timer")
    dlg.show()
    app.processEvents()
    assert dlg.cur.id == "03_timer" and dlg.lst_cases.count() == len(dlg.cur.cases)
    assert "X0" in dlg.lbl_io.text()                     # แสดง I/O ของผัง
    # แก้พารามิเตอร์ให้ผิด → ช่องแดง + บันทึกไม่ได้
    dlg.lst_cases.setCurrentRow(0)
    dlg.steps.table.item(1, 1).setText("Y0 = 1 within")
    assert dlg.steps.validate() == 1 and dlg.dirty
    assert dlg.save() is None and "ยังบันทึกไม่ได้" in dlg.lbl_status.text()
    # แก้ให้ถูก + เพิ่มข้อใหม่ → บันทึก
    dlg.steps.table.item(1, 1).setText("Y0 = 1 within 0.6")
    dlg.add_case()
    dlg.ed_title.setText("ด่าน 3: แก้แล้ว")
    got = []
    dlg.saved.connect(got.append)
    assert dlg.save() is not None and got == ["03_timer"] and not dlg.dirty
    lv = load_level(lvdir / "03_timer.yaml")
    assert lv.title == "ด่าน 3: แก้แล้ว" and lv.cases[0].steps[1].dur == pytest.approx(0.6)
    assert lv.cases[-1].name == f"ข้อ {len(lv.cases)}"
    # ด่านใหม่ → ยังไม่บันทึก → เลือกด่านอื่น → ถามทิ้ง → หายจากรายการ
    n = dlg.lst.count()
    dlg.new_level(False)
    assert dlg.lst.count() == n + 1 and dlg.dirty
    dlg.lst.setCurrentRow(0)
    assert dlg.lst.count() == n and not dlg.dirty
    dlg.dirty = False
    dlg.close()


def test_dialog_hunt_pool_and_delete(app, lvdir, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from plc_game.ui.level_editor import LevelEditorDialog
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg = LevelEditorDialog(folder=lvdir, select="14_fault_find")
    assert dlg.cur.hunt and dlg.tabs.currentIndex() == 2 and not dlg.tabs.isTabEnabled(0)
    assert "Start" in dlg._fault_map and dlg.tbl_pool.rowCount() == 6
    dlg.tbl_pool.cellWidget(0, 0).setCurrentText("ไม่มีอุปกรณ์นี้")
    assert any("ไม่มีอุปกรณ์ป้าย" in p for p in dlg.check())
    dlg.fill_pool_from_panel()
    assert dlg.check() == [] and dlg.save() is not None
    dlg.delete()
    assert not (lvdir / "14_fault_find.yaml").exists() and list((lvdir / "_trash").glob("14_fault_find_*"))
    assert "14_fault_find" not in [d.id for d in dlg.drafts]
    dlg.dirty = False
    dlg.close()


@pytest.fixture
def win(app, tmp_path, lvdir, monkeypatch):
    from plc_game.ui.level_dock import LevelPanel
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    monkeypatch.setattr(LevelPanel, "folder", lvdir)
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def test_main_window_integration(app, win, lvdir):
    from plc_game.ui.exam import ExamSession
    win.open_level(0)
    dlg = win.open_level_editor()
    assert dlg is not None and dlg.folder == lvdir and dlg.cur.id == "01_self_hold"
    assert dlg.locked() and not dlg.ed_title.isEnabled() and dlg.save() is None      # ด่านมาตรฐานแก้ไม่ได้
    dlg.lock_standard = False
    dlg.ed_title.setText("ด่าน 1: ชื่อใหม่")
    dlg.save()
    app.processEvents()
    assert win.levelp.levels[0].title == "ด่าน 1: ชื่อใหม่"
    assert win.levelp.level.title == "ด่าน 1: ชื่อใหม่"       # ด่านที่เปิดอยู่โหลดใหม่
    assert "ด่าน 1: ชื่อใหม่" in win.cb_level.itemText(0)
    assert win.open_level_editor() is dlg                    # เปิดซ้ำได้หน้าต่างเดิม
    dlg.close()
    app.processEvents()
    win.start_exam(ExamSession.start([win.levelp.levels[0].id], minutes=10, max_checks=1))
    assert win.open_level_editor() is None and not win.b_level_edit.isEnabled()
