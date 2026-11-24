"""ladder → คลิปบอร์ด GX Works3: ตารางต้องตรงกับที่ GX Works3 1.110 คัดลอกเองทุกช่อง."""
import os
import random
import struct
from pathlib import Path

import pytest

from plc_game.ladder import gxclip
from plc_game.ladder.csvio import LadderError
from plc_game.ladder.gxclip import Cell
from plc_game.ladder.editor import new_rung, rungs_from_text

# IL | ตารางจาก GX จริง (. ว่าง, - เส้น, | เส้นตั้งซ้ายช่อง, ~ ช่องที่คำสั่งกินที่, * คอยล์)
GOLDEN = [
    ("LD X0;OR M0;ANI X1;OUT M0", ["LD X0,LDI X1,9-,OUT M0*", "LD M0,|.,10."]),
    ("LD X2;OR X3;LD X4;OR X5;ANB;OUT Y1", ["LD X2,LD X4,9-,OUT Y1*", "LD X3,|LD X5,|.,9."]),
    ("LD X0;AND X1;LD X2;ANI X3;ORB;LDI X4;AND X5;ORB;OUT Y2",
     ["LD X0,LD X1,9-,OUT Y2*", "LD X2,LDI X3,|.,9.", "LDI X4,LD X5,|.,9."]),
    ("LD X0;OUT T0 K30", ["LD X0,8-,OUT T0 K30*,2~"]),
    ("LDP X1;RST C0", ["LDP X1,9-,RST C0*,~"]),
    ("LD X3;MOV K10 D0;INC D1", ["LD X3,8-,MOV K10 D0*,2~", ".,|-,8-,INC D1*,~"]),
    ("LD> D0 K5;AND<= D1 K8;OUT Y3", ["LD> D0 K5,2~,LD<= D1 K8,2~,5-,OUT Y3*"]),
    ("LD X0;MPS;AND X1;OUT Y4;MRD;ANI X2;OUT Y5;MPP;AND X3;OUT Y6",
     ["LD X0,LD X1,9-,OUT Y4*", ".,|LDI X2,9-,OUT Y5*", ".,|LD X3,9-,OUT Y6*"]),
    ("LD X0;INV;OUT Y7", ["LD X0,INV,9-,OUT Y7*"]),
    ("LD X6;ORP X7;AND X1;OR M2;OUT M2;+ D0 D1 D2",
     ["LD X6,LD X1,9-,OUT M2*", "LDP X7,|.,|-,5-,+ D0 D1 D2*,3~", "LD M2,-,|.,9."]),
    ("LD X0;OUT Y10;OUT Y11", ["LD X0,10-,OUT Y10*", ".,|-,9-,OUT Y11*"]),
]


def rungs(il):
    return rungs_from_text(il.replace(";", "\n"))


def show(c):
    if c is None:
        return "~"
    return ("|" if c.vline else "") + ({"Blank": ".", "HLine": "-"}.get(c.kind) or c.text) + ("*" if c.coil else "")


def expand(row):
    out = []
    for t in row.split(","):
        n, s = (int(t[:-1]), t[-1]) if t[:-1].isdigit() and t[-1] in ".-~" else (1, t)
        out += [s] * n
    return out


@pytest.mark.parametrize("il,want", GOLDEN)
def test_grid_matches_gx(il, want):
    got = [[show(c) for c in row] for row in gxclip.rungs_grid(rungs(il))]
    assert got == [expand(r) for r in want]


def test_kinds():
    k = [c and c.kind for c in gxclip.rungs_grid(rungs("LD= D0 K1;INV;SET M0"))[0]]
    assert k == ["Command", None, None, "NoArg"] + ["HLine"] * 6 + ["Command", None]


@pytest.mark.parametrize("il", ["LD X0;" + "AND X1;" * 11 + "OUT Y0", "LD X0;" + "AND X1;" * 9 + "MOV K1 D0"])
def test_too_wide(il):
    with pytest.raises(LadderError):
        gxclip.rungs_grid(rungs(il))


def test_exact_width_fits():
    assert gxclip.rungs_grid(rungs("LD X0;" + "AND X1;" * 10 + "OUT Y0"))[0][10].kind == "Single"


def test_refuses_what_gx_cannot_take():
    for r in ([new_rung()], rungs("P0"), rungs("LD X0;LD X1;INV;ORB;OUT Y0"), rungs("LD X0;OUT ?")):
        with pytest.raises(LadderError):
            gxclip.clipboard_bytes(r)


def test_stream_shape():
    b = gxclip.clipboard_bytes(rungs("LD X0;OUT Y0"))
    assert b[:16].hex() == "96a79efd133b7043a67956106bb288fb"
    assert b[16:33] == b"\0" + struct.pack("<4i", 1, -1, 1, 0) and b[-1] == 0x0B
    assert b.count(b"LD X0") == 1 and b.count(b"OUT Y0") == 1
    assert b != gxclip.clipboard_bytes(rungs("LD X0;OUT Y0"))      # Guid ใหม่ทุกครั้ง


# ---------- GX → โปรแกรม ----------
EXTRA = ["LD X0;AND X1;LD X2;AND X3;OR X4;ANB;OR X5;LD M3;OR M4;OR M5;ANB;OUT M10",
         "LD X0;MPS;AND X1;MPS;AND X2;OUT M11;MPP;AND X3;OUT M12;MPP;LD X4;OR X5;ANB;OUT M13;SET M14",
         "LD= D0 K1;OR> D1 K2;OUT M15", "LDPI X0;MEP;PLS M16", "LD SM400;BMOV D0 D10 K4", "FEND"]


@pytest.mark.parametrize("il", [g[0] for g in GOLDEN] + EXTRA)
def test_round_trip(il):
    text, dropped = gxclip.read_text(gxclip.clipboard_bytes(rungs(il)))
    assert text.replace("\n", ";") == il and not dropped


def test_round_trip_many():
    ils = [g[0] for g in GOLDEN] + EXTRA
    text, _ = gxclip.read_text(gxclip.clipboard_bytes([r for il in ils for r in rungs(il)]))
    assert [t.replace("\n", ";") for t in text.split("\n\n")] == ils


def test_reads_real_gx_copy():
    p = Path(__file__).parents[1] / "gx_projects/clip/sample_all_r04.bin"
    if not p.exists():
        pytest.skip("ไม่มีตัวอย่างจาก GX จริง")
    text, _ = gxclip.read_text(p.read_bytes())
    got = [t.replace("\n", ";") for t in text.split("\n\n")]
    assert len(got) == 13 and set(g[0] for g in GOLDEN) <= set(got)


def G(*rows):
    out = []
    for row in rows:
        r = []
        for t in row.split(","):
            v, t = t[0] == "|", t.lstrip("|")
            r.append(None if t == "~" else Cell({".": "Blank", "-": "HLine"}.get(t, "Single"), t.strip(".-*"), t.endswith("*"), v))
        out.append(r)
    return gxclip._MARK + gxclip.serialize(out)


@pytest.mark.parametrize("rows", [
    ["LD X0"],                                                 # ไม่มีคอยล์
    ["LD X0,-,OUT Y0*", ".,|LD X1,."],                         # สายลอย
    ["LD X0,-,LD X1,OUT Y0*", ".,|LD X4,.,|.", "LD X2,-,|LD X3,|."],   # วงจรสะพาน
    ["LD X0,.,OUT Y0*"],                                       # สายขาด
    ["-,-,OUT Y0*"],                                           # ไม่มีหน้าสัมผัส
])
def test_incomplete_is_refused(rows):
    with pytest.raises(LadderError):
        gxclip.read_text(G(*rows))


def test_garbage_is_refused():
    good = gxclip.clipboard_bytes(rungs("LD X0;OR X1;OUT Y0"))
    for b in (b"", b"abc", good[:16], good[:200], good[:-1], good[:40] + b"\xff" * 500):
        with pytest.raises(LadderError):
            gxclip.read_text(b)
    rng = random.Random(1)
    for _ in range(400):                                       # ข้อมูลเพี้ยนต้องไม่ล้ม
        b = bytearray(good)
        for _ in range(3):
            b[rng.randrange(16, len(b))] = rng.randrange(256)
        try:
            gxclip.read_text(bytes(b))
        except LadderError:
            pass


# ---------- Ctrl+C / Ctrl+V ในหน้า Ladder ----------
@pytest.fixture
def view():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from plc_game.ui.ladder_view import LadderView
    v = LadderView(8)
    v.doc.paste_text(0, "LD X0\nOR Y0\nOUT Y0\n\nLD X1\nOUT Y1")
    v.after_edit()
    v.msgs = []
    v.message.connect(v.msgs.append)
    yield v
    v.shutdown()


def test_copy_puts_gx_format_then_paste_back(view):
    from PySide6.QtCore import QMimeData
    from PySide6.QtWidgets import QApplication
    from plc_game.ui.ladder_view import GX_MIME
    view.select_all()
    view.copy_rungs()
    m = QApplication.clipboard().mimeData()
    data = bytes(m.data(GX_MIME))
    assert m.text() and gxclip.read_text(data)[0].startswith("LD X0\nOR Y0\nOUT Y0")
    only = QMimeData()                                          # GX ไม่ใส่ข้อความมาด้วย
    only.setData(GX_MIME, data)
    QApplication.clipboard().setMimeData(only)
    n = len(view.doc.rungs)
    view.paste_rungs()
    assert len(view.doc.rungs) == n + 2 and "GX Works3" in view.msgs[-1]
    view.undo()
    assert len(view.doc.rungs) == n


def test_exam_blocks_gx_both_ways(view):
    from PySide6.QtCore import QMimeData
    from PySide6.QtWidgets import QApplication
    from plc_game.ui.ladder_view import GX_MIME
    data = gxclip.clipboard_bytes(rungs("LD X7;OUT Y7"))
    m = QMimeData()
    m.setData(GX_MIME, data)
    QApplication.clipboard().setMimeData(m)
    view.exam = True
    n = len(view.doc.rungs)
    view.paste_rungs()
    assert len(view.doc.rungs) == n
    view.copy_rungs()
    assert bytes(QApplication.clipboard().mimeData().data(GX_MIME)) == data


def test_unfinished_rung_still_copies_text(view):
    from PySide6.QtWidgets import QApplication
    from plc_game.ui.ladder_view import GX_MIME
    view.insert_rung()
    view.doc.paste_text(0, "LD X0\nOUT ?")
    view.canvas.rung = view.canvas.rung_to = 0
    view.copy_rungs()
    m = QApplication.clipboard().mimeData()
    assert m.text() and not m.hasFormat(GX_MIME)
