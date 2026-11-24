"""ตัวตรวจด่านกับการสื่อสารที่ไม่สมบูรณ์: ข้อมูลหน่วง, poller ช้า, ข้อมูลขาดช่วง, โปรแกรมเปล่า."""
from pathlib import Path

import pytest

from plc_game.ai import analyze
from plc_game.levels import LevelRunner
from plc_game.levels.engine import level_from_data
from plc_game.panel import DeviceSpec, PanelDoc
from test_levels import GOOD, LEVELS, app, run, sol_interlock  # noqa: F401


def lv(steps, idle=None, reset=()):
    return level_from_data({"id": "t", "idle": idle or {"X0": 0, "X1": 0}, "settle": 0.3, "reset": list(reset),
                            "cases": [{"name": "c", "steps": steps}]}, Path("t.yaml"))


def self_hold(m):
    m["Y0"] = int((m["X0"] or m["Y0"]) and not m["X1"])


def drive(level, ladder, period=0.1, delay=1, names=("X0", "X1", "Y0"), limit=60.0, gap=None, drop=None):
    """PLC จำลองแบบ poller จริง: เขียนที่ค้างคิวทั้งหมดรวดเดียวต่อรอบ และอ่านได้ค่าเก่า delay รอบ."""
    mem = {n: 0 for n in names}
    queue, snaps, seen, t = [], [], [], 0.0
    r = LevelRunner(level, lambda a, v, w: queue.append((a, v)))
    while not r.done and t < limit:
        for a, v in queue:
            mem[a] = v
        queue.clear()
        for _ in range(5):
            ladder(mem)
        seen.append(dict(mem))
        snaps.append(dict(mem))
        s = dict(snaps[max(0, len(snaps) - 1 - delay)])
        if drop and t >= drop[0]:
            s.pop(drop[1])
        r.feed(s, t)
        t += period
        if gap and gap[0] <= t < gap[0] + period:
            t += gap[1]
    r.seen = seen
    return r


@pytest.mark.parametrize("delay,period", [(0, 0.05), (1, 0.1), (1, 0.15), (2, 0.1)])
def test_stale_snapshot_not_judged(delay, period):
    """หลังสั่ง Start ต้องไม่เอาค่า Y0 = 0 ก่อนสั่งมาตัดสิน."""
    good = drive(lv(["set X0 1", "set X0 0", "hold Y0 = 1 for 1"]), self_hold, period, delay)
    assert [x.passed for x in good.results] == [True]

    def ignores_start(m):
        m["Y0"] = m["X0"]                                   # ไม่มี self-hold
    bad = drive(lv(["set X0 1", "expect Y0 = 0 within 0.5"]), ignores_start, period, delay)
    assert [x.passed for x in bad.results] == [False]       # เดิมผ่านเพราะดูค่าเก่า


def test_pulse_survives_slow_poller():
    """รอบอ่าน 0.4 s > pulse 0.1 s: PLC ต้องเห็น X0 = 1 อย่างน้อย 1 รอบทุก pulse."""
    r = drive(lv(["pulse X0 0.1", "pulse X0 0.1", "expect Y0 = 1 within 1"]), self_hold, 0.4, 0)
    xs = [s["X0"] for s in r.seen]
    assert sum(b > a for a, b in zip(xs, xs[1:])) == 2
    assert r.results[0].passed


def test_gap_aborts_without_score():
    r = drive(lv(["set X0 1", "hold Y0 = 1 for 4"]), self_hold, gap=(2.0, 3.0))
    assert r.done and r.aborted and "ขาดช่วง" in r.aborted and not r.results


def test_missing_address_is_not_zero():
    r = drive(lv(["hold Y0 = 0 for 4"]), lambda m: None, drop=(1.0, "Y0"))
    assert r.aborted and "Y0" in r.aborted and not any(x.passed for x in r.results)


def test_waitfor_timeout_noted():
    level = lv(["set X0 1", "waitfor Y0 = 1 within 0.5", "expect Y0 = 1 within 0.3"])
    r = drive(level, lambda m: None)
    assert len(r.notes) == 1 and len(r.results) == 1        # ไม่นับเป็นข้อคะแนน
    assert any("เครื่องยังไม่พร้อม" in f.title for f in analyze(level, r, []))


def test_barrier_does_not_shift_schedule():
    """expect ที่จริงทันที ไม่ทำให้ hold ถัดไปจบช้าลง (ด่าน Timer จะตกทั้งที่ถูก)."""
    for delay in (0, 1, 2):
        r = drive(lv(["pulse X0 0.3", "expect Y0 = 1 within 0.5", "hold Y0 = 1 for 2"]), self_hold, 0.1, delay)
        e, h = r.results
        assert e.passed and h.passed and h.t_end - e.t_start <= 2.11


@pytest.mark.parametrize("lid", sorted(GOOD))
def test_empty_program_gets_no_star(app, monkeypatch, lid):  # noqa: F811
    from plc_game.ui.panel.view import PanelView
    real = PanelView.spawn_part
    monkeypatch.setattr(PanelView, "spawn_part", lambda s, m="metal": (real(s, m), True)[1])
    r = run(LEVELS[lid], lambda m, now, c: None)
    assert r.stars == 0 and r.passed <= 1, [x.msg for x in r.results if x.passed]


def test_danger_reported_even_when_all_pass(app):  # noqa: F811
    r = run(LEVELS["02_interlock"], sol_interlock)
    r.trace.append((99.0, {**r.trace[-1][1], "Y0": 1, "Y1": 1}))
    fs = analyze(LEVELS["02_interlock"], r, [DeviceSpec.new("motor_rev", address="Y0", addr_rev="Y1")])
    assert fs[0].level == "ok" and any("พร้อมกัน" in f.title for f in fs[1:])


def test_nc_press_is_trigger():
    from plc_game.ai.analyzer import Trace, _last_rising
    trc = Trace([], [(1.0, "X0 ← 1"), (2.0, "X3 ← 0"), (3.0, "X3 ← 1")])
    info = {"X0": ("Start", False), "X3": ("OL", True)}
    assert _last_rising(trc, 5.0, info)[1] == "X3" and _last_rising(trc, 5.0, info)[0] == 2.0


def test_panel_locked_while_checking(app):  # noqa: F811
    from plc_game.ui.panel.view import PanelView
    v = PanelView()
    v.load_doc(PanelDoc.load(LEVELS["01_self_hold"].panel))
    v.set_run_mode(True)
    key = next(it.key for it in v.items_by_id.values() if getattr(it, "key", ""))
    v.input_locked = True
    assert v.key_down(key) is False
    v.input_locked = False
    assert v.key_down(key) is True
    v.release_all_keys()
    v.deleteLater()


def test_abort_refund_only_when_nothing_failed(app, tmp_path, monkeypatch):  # noqa: F811
    """หลุดกลางคันตอนสอบ: ไม่บันทึกคะแนน · คืนสิทธิ์ตรวจเฉพาะเมื่อยังไม่เห็นข้อที่ตก."""
    from types import SimpleNamespace

    from plc_game.ui.exam import ExamSession
    from plc_game.ui.main_window import MainWindow
    for passed, left in (([], 0), ([True], 0), ([True, False], 1)):
        ses = ExamSession(["a"], checks={"a": 1})
        w = SimpleNamespace(panel=SimpleNamespace(input_locked=True), exam=ses, _save_exam=lambda: None,
                            levelp=SimpleNamespace(level=SimpleNamespace(id="a")), log=lambda m: None,
                            _exam_tick=lambda: None)
        MainWindow._on_level_aborted(w, SimpleNamespace(results=[SimpleNamespace(passed=p) for p in passed]))
        assert ses.checks["a"] == left and w.panel.input_locked is False


def test_level_panel_abort_saves_no_score(app, monkeypatch):  # noqa: F811
    from plc_game.levels import scores
    from plc_game.ui.level_dock import LevelPanel
    from plc_game.ui.panel.view import PanelView
    monkeypatch.setattr(scores, "record", lambda *a, **k: pytest.fail("ห้ามบันทึกคะแนน"))
    v = PanelView()
    p = LevelPanel(v)
    got = []
    p.aborted.connect(got.append)
    p.open_level(LEVELS["01_self_hold"])
    p.start(lambda *a: None, lambda *a: None)
    p.feed({a: 0 for a in p.level.addresses()}, 0.0)
    p.abort("หลุด")
    assert len(got) == 1 and p.runner is None and p.last_runner is None and not p.busy
    p.deleteLater()
    v.deleteLater()
