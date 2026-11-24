"""D2: สนับสนุนผู้พัฒนา — PromptPay payload (CRC), ค่าตั้ง support.json, กติกาชวนแบบไม่รบกวน, หน้าต่าง + toast."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import classroom, support  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.ui import state  # noqa: E402
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
    cfg = tmp_path / "support.json"
    cfg.write_text(json.dumps({"promptpay_id": "0812345678", "promptpay_name": "ทดสอบ",
                               "links": [{"label": "Ko-fi", "url": "https://ko-fi.com/x"},
                                         {"label": "bad", "url": "http://insecure"}],
                               "goal": {"text": "Ladder", "target": 100, "current": 40}}), encoding="utf-8")
    monkeypatch.setattr(support, "SUPPORT_FILE", cfg)
    return tmp_path


def _crc_ok(payload: str) -> bool:
    body, crc = payload[:-4], payload[-4:]
    return body.endswith("6304") and f"{support.crc16_ccitt(body.encode()):04X}" == crc


def test_crc_check_value():
    assert support.crc16_ccitt(b"123456789") == 0x29B1          # ค่าตรวจมาตรฐาน CRC-16/CCITT-FALSE


def test_promptpay_phone_static():
    p = support.promptpay_payload("081-234-5678")
    assert p.startswith("000201010211")
    assert "29370016A000000677010111011300668123456785802TH5303764" in p
    assert "54" + "06" not in p and _crc_ok(p)


def test_promptpay_amount_and_ids():
    p = support.promptpay_payload("0812345678", 99)
    assert p.startswith("000201010212") and "540599.00" in p and _crc_ok(p)
    assert "0213" + "1234567890123" in support.promptpay_payload("1-2345-67890-12-3")
    assert "0315" + "123456789012345" in support.promptpay_payload("123456789012345")
    for bad in ("", "12345", "1234567890"):
        with pytest.raises(ValueError):
            support.promptpay_payload(bad)


def test_load_cfg(tmp_state):
    c = support.load_support_cfg()
    assert c.has_promptpay and c.goal_target == 100 and [x["label"] for x in c.links] == ["Ko-fi"]
    assert not support.load_support_cfg(tmp_state / "missing.json").has_promptpay


def test_nudge_rules():
    kw = dict(prev_stars=0, new_stars=3, three_star_count=1, blocked=False, now=1_000_000)
    assert support.nudge_reason({}, **kw) == "first3"
    assert support.nudge_reason({}, **{**kw, "blocked": True}) is None
    assert support.nudge_reason({"support_never": True}, **kw) is None
    assert support.nudge_reason({}, **{**kw, "new_stars": 2}) is None
    assert support.nudge_reason({}, **{**kw, "prev_stars": 3}) is None          # เคยได้ 3 ดาวแล้ว
    st = support.mark_shown({}, "first3", now=1_000_000)
    assert support.nudge_reason(st, **{**kw, "now": 1_000_000 + 3600}) is None  # ยังไม่ครบ 7 วัน
    assert support.nudge_reason(st, **{**kw, "now": 1_000_000 + support.NUDGE_GAP_S}) == "first3"
    r = support.nudge_reason(st, **{**kw, "three_star_count": 5, "now": 1_000_000 + 60})
    assert r == "milestone:5"                                                    # milestone ไม่ติด 7 วัน
    st.update(support.mark_shown(st, r, now=1_000_060))
    assert st["support_milestones"] == [5]
    assert support.nudge_reason(st, **{**kw, "three_star_count": 5, "now": 1_000_120}) is None


def test_dialog(app, tmp_state):
    from plc_game.ui.support_dlg import SupportDialog
    d = SupportDialog()
    try:
        assert d.qr.matrix and d.qr.payload == support.promptpay_payload("0812345678")
        d.amount_buttons[1].click()
        assert d.amount == 99 and "540599.00" in d.qr.payload
        d.sp_amount.setValue(250)
        assert d.amount == 250 and not any(b.isChecked() for b in d.amount_buttons)
        d.copy_id()
        assert QApplication.clipboard().text() == "0812345678"
        assert d.goal_bar.value() == 40
    finally:
        d.deleteLater()
    empty = SupportDialog(cfg=support.SupportConfig())
    try:
        assert not empty.qr.matrix and not empty.btn_copy.isEnabled()
    finally:
        empty.deleteLater()


def test_window_nudge(app, tmp_state):
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock", "xy_base": 8})
    try:
        w.levelp.prev_best = 0
        t = w._maybe_nudge_support(3)
        assert t is not None and t.isVisibleTo(w) and "3 ดาว" in t.lbl.text()
        assert state.load()["support_last_shown"] > 0
        t.close()
        assert w._maybe_nudge_support(3) is None                     # เพิ่งชวนไป
        state.update(support_last_shown=0)
        classroom.upsert_student("66001", "สมชาย")
        w._set_student("66001")
        assert w._maybe_nudge_support(3) is None                     # มีนักเรียนลงชื่อ = ห้องเรียน
        w._set_student(scores.GUEST)
        t = w._maybe_nudge_support(3)
        t.btn_never.click()
        assert state.load()["support_never"] is True
        dlg = w.show_support()
        assert dlg.isVisible()
        dlg.close()
        w.cmd_input.setText("SUPPORT")
        w._on_command()
    finally:
        for wd in QApplication.topLevelWidgets():
            if wd.__class__.__name__ == "SupportDialog":
                wd.close()
        w.close()
