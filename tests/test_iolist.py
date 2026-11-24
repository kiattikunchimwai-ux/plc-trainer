import csv
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game.panel import DeviceSpec as D, PanelDoc  # noqa: E402
from plc_game.panel.iolist import auto_assign, gx_comments, rows, to_csv, to_gx_comment_csv  # noqa: E402


def sample():
    return [
        D.new("lamp", 300, 0, label="RUN", address="Y5"),
        D.new("pushbutton", 100, 0, label="Stop", address="X7", contact="NC"),
        D.new("pushbutton", 0, 0, label="Start", address="X3"),
        D.new("motor", 300, 200, label="มอเตอร์", address="Y5"),           # ใช้ Y5 ร่วมกับหลอด RUN
        D.new("overload", 0, 200, label="OL1", address="X12", addr_motor="Y5"),
        D.new("cylinder", 0, 400, label="Cyl A", address="Y2", addr_ret="X1", addr_ext="X2"),
        D.new("sevenseg", 300, 400, label="นับ", address="D0"),
        D.new("lamp", 400, 400, label="ภายใน", address="M10"),
        D.new("note", 0, 600),
    ]


def test_rows_sorted_and_described():
    rs = rows(sample())
    assert [r.address for r in rs] == ["X1", "X2", "X3", "X7", "X12", "Y2", "Y5", "Y5", "Y5", "M10", "D0"]
    stop = next(r for r in rs if r.label == "Stop")
    assert stop.contact == "NC" and stop.direction.startswith("Input")
    a1 = next(r for r in rs if r.address == "X2")
    assert "a1" in a1.slot and a1.comment == "Cyl A รีดสวิตช์ยื่น (a1)"


def test_csv_has_bom_and_thai():
    text = to_csv(rows(sample()))
    assert text.startswith("﻿")
    data = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert data[0][0] == "Address" and len(data) == 12
    assert ["X7", "Input → PLC", "Stop"] == data[4][:3]


def test_gx_comments_merge_shared_output():
    c = dict(gx_comments(rows(sample())))
    assert c["Y5"] == "RUN / มอเตอร์"            # OL1 แค่เฝ้า Y5 → ไม่ใส่ในคอมเมนต์
    assert c["X12"] == "OL1"
    only_ref = rows([D.new("overload", address="X0", addr_motor="Y3", label="OL")])
    assert dict(gx_comments(only_ref))["Y3"].startswith("OL")   # ไม่มีเจ้าของ → ใช้ชื่อจากช่องอ้างอิง


def test_clip_keeps_thai_words_whole():
    from plc_game.panel.iolist import _clip
    assert _clip("RUN / มอเตอร์ / OL1 มอเตอร์ที่เฝ้า") == "RUN / มอเตอร์ / OL1"
    s = _clip("ก" * 31 + "ที่")                   # ไม่มีช่องว่าง: ไม่ตัดให้เหลือ "ท" โดยไม่มีสระ
    assert len(s) <= 32 and not s.endswith("ท")
    assert list(csv.reader(io.StringIO(to_gx_comment_csv(rows(sample())).lstrip("﻿"))))[0] == \
        ["Device Name", "Comment"]


def test_auto_assign_keeps_shared_outputs_and_refs():
    devs = sample()
    ch = auto_assign(devs)
    by = {d.props.get("label"): d for d in devs}
    new = lambda lbl, prop="address": ch.get(by[lbl].id, {}).get(prop, by[lbl].props[prop])  # noqa: E731
    # Input เรียงบน→ล่าง ซ้าย→ขวา: Start, Stop (y=0) → OL1 (y=200) → Cyl a0, a1 (y=400)
    assert [new("Start"), new("Stop"), new("OL1"), new("Cyl A", "addr_ret"), new("Cyl A", "addr_ext")] == \
        ["X0", "X1", "X2", "X3", "X4"]
    # Output: RUN/มอเตอร์ ใช้ Y เดียวกันต่อ, OL เฝ้ามอเตอร์ตัวเดิม, กระบอกสูบได้เลขถัดไป
    assert new("RUN") == new("มอเตอร์") == new("OL1", "addr_motor") == "Y0"
    assert new("Cyl A") == "Y1"
    assert by["นับ"].id not in ch and by["ภายใน"].id not in ch       # ไม่แตะ D / M
    assert auto_assign([d for d in devs]) == ch                     # ทำซ้ำได้ผลเดิม (deterministic)


def test_auto_assign_octal_and_hex():
    addrs = ["X100", "X101", "X102", "X103", "X104", "X105", "X106", "X107", "X110", "X111"]  # ใช้ได้ทั้งฐาน 8/16
    devs = [D.new("pushbutton", i * 100, 0, address=a) for i, a in enumerate(addrs)]
    ch8 = auto_assign(devs, 8)
    assert [ch8[d.id]["address"] for d in devs][-2:] == ["X10", "X11"]       # ฐาน 8 ข้าม X8, X9
    ch16 = auto_assign(devs, 16)
    assert [ch16[d.id]["address"] for d in devs][-2:] == ["X8", "X9"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dock_assign_undo_and_export(app, tmp_path, monkeypatch):
    from plc_game.ui import iolist_dock
    from plc_game.ui.iolist_dock import IOListPanel
    from plc_game.ui.panel.view import PanelView
    v = PanelView(xy_base=8)
    v.load_doc(PanelDoc("ทดสอบ", sample()))
    panel = IOListPanel(v)
    assert panel.table.rowCount() == 11
    monkeypatch.setattr(iolist_dock.AssignDialog, "exec", lambda self: iolist_dock.QDialog.Accepted)
    panel.auto_assign()
    assert "X0" in v.addresses() and "X12" not in v.addresses() and v.undo.count() == 1
    assert panel.table.item(0, 0).text() == "X0"                   # ตาราง rebuild ตาม
    v.do_undo()
    assert "X12" in v.addresses()
    panel.update_values({"X1": 1, "Y5": 1, "D0": 42})
    vals = {panel.table.item(r, 0).text(): panel.table.item(r, 5).text() for r in range(panel.table.rowCount())}
    assert vals["D0"] == "42" and vals["Y5"] == "1"
    for fn, name in ((panel.export_csv, "a.csv"), (panel.export_gx, "b.csv"), (panel.export_pdf, "c.pdf")):
        p = fn(tmp_path / name)
        assert p.exists() and p.stat().st_size > 100
