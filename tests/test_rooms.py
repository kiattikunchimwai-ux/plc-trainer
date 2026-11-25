"""ห้องด่าน · เงื่อนไขแบบประโยค · AI อ่านและเรียนรู้จากเงื่อนไข · พิมพ์ข้อความ."""
import json
import os
import shutil
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QInputMethodEvent, QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.ai import learn, spec  # noqa: E402
from plc_game.levels import conditions as C  # noqa: E402
from plc_game.levels import editor as E  # noqa: E402
from plc_game.levels import rooms, scores  # noqa: E402
from plc_game.levels.engine import LEVEL_DIR, load_all, parse_step  # noqa: E402
from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402
from plc_game.ui.thai_keys import latin_only, to_latin  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lvdir(tmp_path):
    d = tmp_path / "levels"
    shutil.copytree(LEVEL_DIR, d, ignore=shutil.ignore_patterns("rooms", "_trash"))
    return d


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


def draft(lvdir, lid):
    return next(d for d in E.load_drafts(lvdir) if d.id == lid)


# ---------------- ห้อง ----------------
def test_rooms_are_separate_and_readonly_standard(lvdir):
    before = [lv.id for lv in load_all(lvdir)]
    a, b = rooms.create("ห้อง ก", lvdir), rooms.create("ห้อง ข", lvdir)
    with pytest.raises(rooms.RoomError):
        rooms.create(" ห้อง  ก ", lvdir)
    with pytest.raises(rooms.RoomError):
        rooms.create("  ", lvdir)
    src = draft(lvdir, "01_self_hold")
    assert E.is_standard(src.path, lvdir)
    x, y = rooms.copy_level(src, lvdir, a), rooms.copy_level(src, lvdir, b)
    assert not E.is_standard(x.path, lvdir) and x.path.parent == a.path
    la, errs = rooms.load_levels(a)
    assert errs == [] and la[0].id == f"{a.key}__01_self_hold" and la[0].id != rooms.load_levels(b)[0][0].id
    assert la[0].panel and la[0].panel.parent == a.path and y.panel
    assert [lv.id for lv in load_all(lvdir)] == before          # ห้องไม่ปนด่านมาตรฐาน
    assert rooms.copy_level(src, lvdir, a).id == "01_self_hold_2"
    (a.path / "bad.yaml").write_text("{", encoding="utf-8")
    ok, errs = rooms.load_levels(a)
    assert len(ok) == 2 and len(errs) == 1
    assert rooms.rename(a, "ใหม่", lvdir).key == a.key
    rooms.delete(b, lvdir)
    assert [r.name for r in rooms.list_rooms(lvdir)] == ["ใหม่"] and list((lvdir / "_trash").glob("room_*"))


def test_export_import_roundtrip(lvdir, tmp_path):
    r = rooms.create("ส่งออก", lvdir)
    rooms.copy_level(draft(lvdir, "03_timer"), lvdir, r)
    f = rooms.export(r, tmp_path / "x.plcroom")
    n = rooms.import_room(f, lvdir)
    assert n.key != r.key and n.name == "ส่งออก (2)"
    lv = rooms.load_levels(n)[0][0]
    assert lv.checks == rooms.load_levels(r)[0][0].checks and lv.panel.parent == n.path


@pytest.mark.parametrize("files", [
    {"../evil.yaml": "x"}, {"a/b.yaml": "x"}, {"C:evil.yaml": "x"}, {"run.exe": "x"}, {"con.yaml": "id: con"},
    {"room.json": '{"name":"n"}', "l.yaml": "a: &x [1]\nb: *x"}, {"l.yaml": "just text"}, {"p.plcpanel": "{"},
    {"A.yaml": "x", "a.yaml": "x"}, {},
])
def test_import_rejects_bad_files(lvdir, tmp_path, files):
    f = tmp_path / "bad.plcroom"
    with zipfile.ZipFile(f, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    with pytest.raises(rooms.RoomError):
        rooms.import_room(f, lvdir)
    assert rooms.list_rooms(lvdir) == [] and not list(rooms.rooms_dir(lvdir).glob(".tmp*"))
    assert not (tmp_path / "evil.yaml").exists()


def test_import_not_a_zip(lvdir, tmp_path):
    f = tmp_path / "t.plcroom"
    f.write_text("hello", encoding="utf-8")
    with pytest.raises(rooms.RoomError):
        rooms.import_room(f, lvdir)


# ---------------- เงื่อนไข ----------------
def test_sentences_roundtrip_every_level():
    n = 0
    for d in E.load_drafts(LEVEL_DIR):
        for steps in [c.steps for c in d.cases] + [d.reset]:
            acts = C.to_actions(steps)
            assert [s.to_raw() for s in C.to_rows(acts)] == [s.to_raw() for s in steps]      # ไม่แตะ = ไม่เปลี่ยนสักตัว
            for a in acts:
                if a.kind != "raw":
                    a.touch()
                assert C.sentence(a, {})
            assert [parse_step(s.to_raw()) for s in C.to_rows(acts)] == [parse_step(s.to_raw()) for s in steps]
            n += len(steps)
    assert n > 100


def test_nc_button_is_pressed_with_zero():
    rows = C.press_rows("X1", nc=True)
    assert [r.to_raw() for r in rows][0] == "set X1 0" and rows[-1].to_raw() == "set X1 1"
    assert [a.kind for a in C.to_actions(rows, {"X1"})] == ["press"]


@pytest.mark.parametrize("nc", [set(), {"X1"}])
def test_templates_are_valid_and_learnable(lvdir, nc):
    role = {"start": "X0", "stop": "X1", "start2": "X2", "sensor": "X2", "out": "Y0", "out2": "Y1"}
    for t in C.templates():
        use = {k: role[k] for k, _, _ in t.roles} or {"start": "X0", "out": "Y0"}
        d = E.new_draft([])
        d.cases = C.build_cases(t.key, use, {p[0]: p[2] for p in t.params}, nc)
        d.idle = {a: int(a in nc) for a in use.values() if a[0] == "X"}
        d.reset = C.press_rows("X1", nc="X1" in nc)
        assert d.problems(lvdir) == [], t.key
        lv = d.build(lvdir)
        p = spec.analyze_spec(lv)
        p.nc = nc
        assert learn.train(lv, p).status == "ok", t.key


# ---------------- AI ----------------
def lv_of(lid):
    return next(lv for lv in load_all() if lv.id == lid)


def prof(lv):
    return spec.analyze_spec(lv, PanelDoc.load(lv.panel).devices if lv.panel else [])


def test_spec_understands_levels():
    assert {"on", "off", "latch"} <= set(prof(lv_of("01_self_hold")).features())
    assert "interlock" in prof(lv_of("02_interlock")).features()
    p = prof(lv_of("03_timer"))
    d = p.get("delay")[0]
    assert d.lo < 3 < d.hi
    assert "count" in prof(lv_of("04_counter")).features()
    for lv in load_all():
        assert not [i for i in prof(lv).issues if i.level == "error"], lv.id
    for lid in ("05_cylinder_seq", "10_mixing", "13_vfd"):
        assert learn.train(lv_of(lid), prof(lv_of(lid))).status == "physics"


def level(lvdir, *cases, idle=None):
    d = E.new_draft([])
    d.idle = idle or {"X0": 0}
    d.cases = [E.CaseRow(f"c{i}", [E.StepRow.from_raw(s) for s in c]) for i, c in enumerate(cases)]
    return d.build(lvdir)


def test_spec_finds_contradictions(lvdir):
    def keys(lv):
        return [i.key for i in spec.analyze_spec(lv).issues]
    ok = ["pulse X0 0.3", "expect Y0 = 1 within 0.5"]
    assert keys(level(lvdir, ok)) == []
    assert "impossible" in keys(level(lvdir, ["pulse X0 0.3", "expect Y0 = 2 within 0.5"]))
    assert "conflict" in keys(level(lvdir, ["pulse X0 0.3", "expect Y0 = 1 and Y0 = 0 within 0.5"]))
    assert "conflict" in keys(level(lvdir, ["pulse X0 0.3", "hold Y0 = 1 for 1"], ["pulse X0 0.3", "hold Y0 = 0 for 1"]))
    assert "conflict" in keys(level(lvdir, ok, ["pulse X0 0.3", "hold Y0 = 0 for 1"]))
    lv = level(lvdir, ok, ["pulse X0 0.3", "hold Y0 = 0 for 1"])
    assert learn.train(lv, spec.analyze_spec(lv)).status == "unknown"


def test_suggestion_is_a_valid_case(lvdir):
    p = prof(lv_of("02_interlock"))
    assert any(s.key == "stop" for s in p.suggestions)
    d = draft(lvdir, "02_interlock")
    d.cases += [s.case for s in p.suggestions if s.case]
    assert d.problems(lvdir) == []
    lv = d.build(lvdir)
    assert learn.train(lv, prof(lv)).status == "ok"


def test_signature_points_to_the_mistake():
    lv = lv_of("01_self_hold")
    p = prof(lv)
    m = learn.train(lv, p)
    r = learn.simulate(lv, ["LD X0", "OUT Y0"], p.idle)            # ลืมคงสถานะ
    got = learn.match(lv, r, m, learn.Memory())
    assert got and got[0][0].kind == "no_latch" and got[0][1] == 1.0
    assert r.stars < 3                                             # คะแนนมาจากตัวตรวจเท่านั้น
    f = learn.findings(got, p.names)[0]
    assert f.kind == "learned" and "self-holding" in f.text()


def test_loose_level_is_reported(lvdir):
    lv = level(lvdir, ["pulse X0 0.3", "expect Y0 = 1 within 0.5"])
    m = learn.train(lv, spec.analyze_spec(lv))
    assert m.status == "ok" and m.loose


def test_memory_relearns_on_change_and_keeps_no_ladder(tmp_path):
    f = tmp_path / "m.json"
    mem = learn.Memory(f)
    lv = lv_of("01_self_hold")
    p = prof(lv)
    mem.store(lv.id, learn.train(lv, p))
    text = f.read_text(encoding="utf-8")
    assert not any(w in text for w in ("OUT ", "LD ", "ORI", "ANI", "guest"))
    again = learn.Memory(f)
    assert again.model(lv.id, p.hash).mistakes and again.model(lv.id, "x") is None
    lv.cases[0].steps[-1].dur += 1
    assert spec.spec_hash(lv, p.nc) != p.hash                      # เงื่อนไขเปลี่ยน = เรียนใหม่
    again.clear()
    assert not f.exists()


@pytest.mark.parametrize("text", ["", "{", "[]", '{"version":1,"levels":[1],"kinds":{"a":["x"]}}',
                                  '{"version":1,"levels":{"a":{"hash":1}},"tips":{"t":[1,-2]}}', "[" * 5000])
def test_memory_survives_bad_file(tmp_path, text):
    f = tmp_path / "m.json"
    f.write_text(text, encoding="utf-8")
    m = learn.Memory(f)
    assert m.data["levels"] == {} and m.data["tips"] == {}
    m.tip("stop", True)
    assert learn.Memory(f).tip_weight("stop") > 0.5


def test_memory_improves_from_confirmed_fix(tmp_path):
    lv = lv_of("01_self_hold")
    p = prof(lv)
    c = learn.Coach(learn.Memory(tmp_path / "m.json"))
    c.mem.store(lv.id, learn.train(lv, p))
    bad = learn.simulate(lv, ["LD X0", "OUT Y0"], p.idle)
    none = learn.simulate(lv, ["LD X5", "OUT Y0"], p.idle)
    before = c.mem.weight("no_latch", p.features())
    assert c.after_check("s1", lv, bad, p)
    c.after_check("s2", lv, none, p)                               # คนละคน = ไม่นับว่าแก้แล้ว
    assert c.mem.weight("no_latch", p.features()) == before
    c.after_check("s1", lv, bad, p)
    c.after_check("s1", lv, bad, p)                                # ยังไม่หาย = ไม่ได้ยืนยัน
    assert c.mem.weight("no_latch", p.features()) < before
    assert "s1" not in json.dumps(c.mem.data)


def test_training_can_be_cancelled():
    lv = lv_of("03_timer")
    assert learn.train(lv, prof(lv), cancel=lambda: True).status == "cancelled"


def test_no_online_ai(win):
    """ใช้เฉพาะ AI ในโปรแกรม — ไม่มีปุ่มหรือโมดูลที่ส่งข้อมูลออกไปหาบริการ AI."""
    from PySide6.QtWidgets import QAbstractButton
    assert not [b.text() for b in win.findChildren(QAbstractButton) if "claude" in b.text().lower()]
    root = LEVEL_DIR.parent / "plc_game"
    assert not [f.name for f in root.rglob("*.py") if "anthropic" in f.read_text(encoding="utf-8").lower()]


# ---------------- พิมพ์ข้อความ ----------------
def key(w, k, text="", mods=Qt.NoModifier):
    for t in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(w, QKeyEvent(t, k, mods, text))


def ime(w, text):
    e = QInputMethodEvent()
    e.setCommitString(text)
    QApplication.sendEvent(w, e)


def test_thai_layout_types_addresses(app):
    assert to_latin("ปจ") == "x0" and to_latin("X0") == "X0"  # i18n: skip
    ed = latin_only(QLineEdit())
    key(ed, 0, "ป")
    key(ed, 0, "จ")
    assert ed.text() == "x0"


def test_note_typed_on_the_panel(win, app):
    win.set_edit_mode(True)
    win.panel.load_doc(PanelDoc(devices=[DeviceSpec.new("lamp", 0, 0), DeviceSpec.new("note", 200, 0)]))
    win.panel.set_run_mode(False)
    lamp, note = win.panel.items_by_id.values()
    v = win.panel
    assert note.prop("text") == ""
    assert v.edit_text(note) and v.editing_text()
    ime(v._inline, "สวัสดี")
    QTest.keyClicks(v._inline, " abc 1")
    key(v._inline, Qt.Key_Return, "\r")
    QTest.keyClicks(v._inline, "x")
    key(v._inline, Qt.Key_Return, "\r", Qt.ControlModifier)
    assert note.prop("text") == "สวัสดี abc 1\nx" and not v.editing_text()
    v.edit_text(lamp)
    ime(v._inline, "ไฟเขียว")
    key(v._inline, Qt.Key_Return, "\r")
    assert lamp.prop("label") == "ไฟเขียว"
    v.edit_text(lamp)
    QTest.keyClicks(v._inline, "zzz")
    key(v._inline, Qt.Key_Escape)
    assert lamp.prop("label") == "ไฟเขียว"
    v.edit_text(lamp)
    QTest.keyClicks(v._inline, "saved")
    v.flush_commit()                                               # บันทึก/ปิดระหว่างพิมพ์ = ไม่หาย
    assert lamp.prop("label") == "saved"
    v.do_undo()
    assert next(i for i in v.items_by_id.values() if i.spec.kind == "lamp").prop("label") == "ไฟเขียว"
    v.input_locked = True
    assert not v.edit_text(next(iter(v.items_by_id.values())))     # ตอนกำลังตรวจแก้ไม่ได้
    v.input_locked = False


def test_copy_paste_and_shared_edit(win):
    v = win.panel
    v.load_doc(PanelDoc(devices=[DeviceSpec.new("pushbutton", 0, 0, address="X0"), DeviceSpec.new("note", 200, 0, text="a"),
                                 DeviceSpec.new("note", 300, 0, text="b")]))
    v.set_run_mode(False)
    v.select_all()
    assert v.copy_selected() == 3 and v.paste_devices() == 3
    xs = [i.spec.props["address"] for i in v.items_by_id.values() if i.spec.kind == "pushbutton"]
    assert len(set(xs)) == 2
    v.sc.clearSelection()
    notes = [i for i in v.items_by_id.values() if i.spec.kind == "note"]
    old = [n.prop("size") for n in notes]
    for n in notes:
        n.setSelected(True)
    v.bump_size(1)
    assert [n.prop("size") for n in notes] == [s + 2 for s in old]
    v.set_run_mode(True)
    assert v.paste_devices() == 0


# ---------------- ตัวแก้ไข + หน้าต่าง ----------------
def test_builder_edits_the_same_steps(app, lvdir):
    from plc_game.ui.level_editor import LevelEditorDialog
    dlg = LevelEditorDialog(folder=lvdir, select="01_self_hold")
    b = dlg.builder
    assert b.steps() and [s.to_raw() for s in b.steps()] == [s.to_raw() for s in dlg.steps.steps()]
    raw = [s.to_raw() for s in dlg.cur.cases[0].steps]
    assert any("msg_en" in r for r in raw if isinstance(r, dict)) and [s.to_raw() for s in dlg.steps.steps()] == raw
    n = len(raw)
    b.add("expect")
    assert len(dlg.steps.steps()) == n + 1 and dlg.dirty
    b.remove(len(b.actions) - 1)
    assert [s.to_raw() for s in dlg.steps.steps()] == raw
    for ed in b.findChildren(QLineEdit):
        assert ed.isEnabled()
    msg = next(e for e in b.findChildren(QLineEdit) if e.text() == b.actions[1].msg and e.text())
    msg.setFocus()
    msg.clear()
    ime(msg, "ข้อความไทย")
    QTest.keyClicks(msg, " en")
    assert dlg.steps.steps()[1].msg == "ข้อความไทย en"
    for ed in (dlg.ed_title, dlg.ed_desc):
        ed.clear()
        ime(ed, "ทดสอบ")
        QTest.keyClicks(ed, " x")
    assert dlg.ed_title.text() == "ทดสอบ x" and dlg.ed_desc.toPlainText() == "ทดสอบ x"
    dlg.lst_cases.setCurrentRow(1)                                 # เปลี่ยนข้อ = ข้อความไม่หาย
    dlg.lst_cases.setCurrentRow(0)
    assert dlg.steps.steps()[1].msg == "ข้อความไทย en"
    dlg.dirty = False
    dlg.close()
    assert not dlg.isVisible()


def test_enter_and_esc_do_not_lose_text(app, lvdir, monkeypatch):
    from plc_game.ui.level_editor import LevelEditorDialog
    dlg = LevelEditorDialog(folder=lvdir, select="01_self_hold")
    dlg.show()
    n = len(dlg.drafts)
    dlg.ed_title.setFocus()
    QTest.keyClicks(dlg.ed_title, "Z")
    key(dlg.ed_title, Qt.Key_Return, "\r")
    assert len(dlg.drafts) == n and dlg.ed_title.text().endswith("Z")
    asked = []
    monkeypatch.setattr(dlg, "_ask_discard", lambda: asked.append(1))
    key(dlg, Qt.Key_Escape)
    assert asked and dlg.isVisible() and dlg.ed_title.text().endswith("Z")
    dlg.dirty = False
    dlg.close()


def test_room_flow_in_main_window(win, app, lvdir, monkeypatch):
    from plc_game.ui import level_editor
    from plc_game.ui.exam import ExamSession
    win.open_level(0)
    dlg = win.open_level_editor()
    assert dlg.locked() and not dlg.builder.isEnabled() and dlg.b_copy.isEnabled()
    monkeypatch.setattr(level_editor.QInputDialog, "getText", lambda *a, **k: ("ห้องฉัน", True))
    d = dlg.copy_to_room()
    assert dlg.room.name == "ห้องฉัน" and dlg.cur.id == d.id and not dlg.locked() and dlg.ed_title.isEnabled()
    dlg.ed_title.setText("ด่านของฉัน 1")
    dlg._mark()
    dlg.save_and_open() if hasattr(dlg, "save_and_open") else dlg.b_open.click()
    app.processEvents()
    lid = dlg.room.level_id(d.id)
    assert win.levelp.level.id == lid and win.levelp.level.title == "ด่านของฉัน 1"
    assert win.cb_room.currentData() == dlg.room.key and state.load()["room"] == dlg.room.key
    assert "01_self_hold" in [lv.id for lv in load_all(lvdir)] and load_all(lvdir)[0].title != "ด่านของฉัน 1"

    class Fake(level_editor.LevelWizard):
        def exec(self):
            self.ed_title.setText("จากวิซาร์ด")
            self.cb_tpl.setCurrentIndex(0)
            self.finish()
            return QDialog.Accepted if self.draft else QDialog.Rejected
    monkeypatch.setattr(level_editor, "LevelWizard", Fake)
    w = dlg.create_level()
    assert w is not None and dlg.cur.title == "จากวิซาร์ด" and dlg.check() == []
    assert dlg.save() is not None
    dlg.run_ai()
    t = 0
    while dlg._ai is not None and t < 100:
        QTest.qWait(50)
        t += 1
    assert "AI" in dlg.ai_box.toPlainText() and dlg._ai_result[1].status == "ok"
    win.start_exam(ExamSession.start([lid], minutes=5, max_checks=1))
    assert not dlg.isVisible() and not win.cb_room.isEnabled() and win.open_level_editor() is None
    assert not win.set_room("") and state.load()["exam_room"] == dlg.room.key
    win.levelp.learn_now()
    assert win.levelp._learner is None                             # ระหว่างสอบไม่เรียนรู้
    win.exam = None
    win._apply_exam_lock(False)
    win._exam_timer.stop()
    assert win.set_room("") and win.levelp.levels[0].id == "01_self_hold"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg.delete_room()
    assert rooms.list_rooms(lvdir) == [] and win.cb_room.count() == 1
    dlg.dirty = False
    dlg.close()


def test_run_ladder_connects_by_itself(win, app, monkeypatch):
    """กด ▶ รัน Ladder อย่างเดียว: เชื่อม PLC ในตัวเอง ส่ง และ RUN."""
    win.open_level(0)
    v = win.ladderv
    assert not win.send_ladder() and win.soft is None              # ladder ว่าง = ไม่เชื่อม
    _draw(win, app)
    assert win.send_ladder() and win.soft is not None and win.soft.state == "run" and not v.unsent
    assert "RUN" in v.lbl_state.text() or not v.lbl_state.text()
    win._split_ladder()
    assert win.stack.currentWidget() is win.splitter and v.isVisible() and win.panel.isVisible()
    win._split_ladder()
    assert win.stack.currentWidget() is win.space
    win.disconnect_plc()
    win.cb_backend.setCurrentIndex(win.cb_backend.findData("mock"))
    win.connect_plc()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    assert not win.send_ladder() and win.soft is None              # ต่อ PLC อื่นอยู่ = ถามก่อน
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    assert win.send_ladder() and win.soft is not None
    win.disconnect_plc()


def _draw(win, app):
    win.show_ladder()
    cv = win.ladderv.canvas
    for k, text in ((Qt.Key_F5, "X5"), (Qt.Key_F7, "Y7")):
        QTest.keyClick(cv, k)
        QTest.keyClicks(cv.editor, text)
        QTest.keyClick(cv.editor, Qt.Key_Return)
        app.processEvents()


def test_gc_runs_only_in_gui_thread(win):
    """gc ใน thread ของ AI เคยลบวัตถุ Qt ผิด thread จนโปรแกรมปิดตัวเอง."""
    import gc
    assert not gc.isenabled()
    win._gc.check()
    win.shutdown()
    assert gc.isenabled()


def test_standard_panel_is_not_overwritten(win, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    win.open_level(0)
    p = win.panel_path
    old = p.read_bytes()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert not win.save_panel() and p.read_bytes() == old


def test_check_without_open_level_is_safe(win, monkeypatch):
    monkeypatch.setattr(win, "open_level", lambda i: None)
    win.levelp.level = None
    win.start_check()


def test_condition_cards_are_easy_to_click(win, app):
    """คลิกกลางช่องอุปกรณ์ = รายการเปิด, ย้าย/ลบแล้วตำแหน่งเลื่อนไม่เด้งกลับบนสุด."""
    from plc_game.ui.cond_builder import AddrBox, CondBuilder
    b = CondBuilder()
    b.resize(700, 220)
    b.show()
    for _ in range(8):
        b.add("press")
    app.processEvents()
    app.processEvents()
    bar = b.scroll.verticalScrollBar()
    assert bar.value() == bar.maximum() > 0
    pos = bar.value() // 2
    bar.setValue(pos)
    b.move_to(3, 1)
    app.processEvents()
    app.processEvents()
    assert abs(bar.value() - pos) <= 2
    ab = b.cards[0].findChild(AddrBox)
    b.scroll.verticalScrollBar().setValue(0)
    QTest.mouseClick(ab.lineEdit(), Qt.LeftButton)
    app.processEvents()
    assert ab.view().isVisible()
    ab.hidePopup()
    i = next(i for i in range(ab.count()) if ab.itemData(i) is None)
    ab._chosen(i)
    ab.lineEdit().setText("X7")
    ab.lineEdit().editingFinished.emit()
    assert b.actions[0].addr == "X7"
    b.close()


def test_standard_level_shows_what_to_press(win, app):
    d = win.open_level_editor()
    d.set_room("")
    d.lst.setCurrentRow(0)
    app.processEvents()
    assert d.locked() and d.lock_bar.isVisible() and d.b_lock_new.isEnabled() and d.b_lock_copy.isEnabled()
    d.close()
