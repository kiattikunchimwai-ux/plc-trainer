"""rung ↔ ข้อมูลคลิปบอร์ดของ GX Works3 (ไม่ใช้ Qt): Ctrl+C / Ctrl+V ไปมาได้.

รูปแบบได้จากการคัดลอก ladder ใน GX Works3 1.110 จริงแล้วถอด: ตารางกว้าง 12 ช่อง เป็นวัตถุ .NET (MS-NRBF)
ช่องที่มี vline = เส้นตั้งที่ขอบซ้าย ต่อขึ้นไปหาแถวบน
"""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass

from ..i18n import tr
from .csvio import LadderError
from .editor import (BLANK, INLINE, Branch, Coil, Inline, Leaf, Parallel, Rung, Series, _split, is_blank, rung_code, standalone,
                     walk)
from .model import is_label

_NS = "Melco.GXW3.WorkWindow.Program.Ladder.Editor.Controller.CopyPaste.Data."
FORMAT = _NS + "CopyPasteCells"
COLS = 12
CPU_SERIES = 10


@dataclass
class Cell:
    kind: str = "Blank"          # Blank / HLine / Single / Command / NoArg
    text: str = ""
    coil: bool = False
    vline: bool = False


# ======================= rung → ตาราง =======================
def _w(n) -> int:
    if isinstance(n, Leaf):
        return len(n.args) + 1 if len(n.args) > 1 else 1
    if isinstance(n, Inline):
        return 1
    if isinstance(n, Series):
        return sum(map(_w, n.kids))
    return max(map(_w, n.kids))


def _h(n) -> int:
    if isinstance(n, Series):
        return max(map(_h, n.kids), default=1)
    return sum(map(_h, n.kids)) if isinstance(n, Parallel) else 1


def _bh(b) -> int:
    return max(_h(b.cond), sum(1 if isinstance(x, Coil) else _bh(x) for x in b.outs))


def _single(c: Coil) -> bool:
    return c.op == "OUT" and len(c.args) == 1


class _Grid:
    def __init__(self, rows: int):
        self.rows = [[Cell() for _ in range(COLS)] for _ in range(rows)]
        self.bars: list[tuple[int, int, int]] = []          # (คอลัมน์, แถวบน, แถวล่าง)

    def put(self, y: int, x: int, width: int, cell: Cell):
        if x + width > COLS or any(c is None or c.kind != "Blank" for c in self.rows[y][x:x + width]):
            raise LadderError(tr("rung ยาวเกิน 12 ช่องของ GX Works3 — ใช้ ส่งออก CSV แทน"))
        self.rows[y][x:x + width] = [cell] + [None] * (width - 1)

    def line(self, y: int, x0: int, x1: int):
        for x in range(x0, x1):
            self.put(y, x, 1, Cell("HLine"))

    def series(self, s: Series, y: int, x: int) -> int:
        for k in s.kids:
            w = _w(k)
            if isinstance(k, Leaf):
                self.put(y, x, w, Cell("Single" if w == 1 else "Command", " ".join((k.op("LD"), *k.args))))
            elif isinstance(k, Inline):
                self.put(y, x, 1, Cell("NoArg", k.name))
            else:
                yy = last = y
                for sub in k.kids:
                    self.line(yy, self.series(sub, yy, x), x + w)
                    last, yy = yy, yy + _h(sub)
                self.bars += [(x, y, last), (x + w, y, last)]
            x += w
        return x

    def branch(self, b, y: int, x: int):
        x = self.series(b.cond, y, x)
        yy = last = y
        for o in b.outs:
            last = yy
            if isinstance(o, Coil):
                self.coil(o, yy, x)
                yy += 1
            else:
                self.branch(o, yy, x)
                yy += _bh(o)
        self.bars.append((x, y, last))

    def coil(self, c: Coil, y: int, x: int):
        w = 1 if _single(c) else len(c.args) + 1
        at = max(COLS - w, 0)
        self.line(y, x, at)
        self.put(y, at, w, Cell("Single" if _single(c) else "Command", " ".join((c.op, *c.args)), True))

    def finish(self) -> list[list[Cell | None]]:
        for x, top, bottom in self.bars:
            for y in range(top + 1, bottom + 1):
                c = self.rows[y][x] if 0 < x < COLS else None
                if c is not None:                           # x = 0 คือเส้นไฟซ้าย ไม่ต้องลาก
                    c.vline = True
                elif x:
                    raise LadderError(tr("rung ยาวเกิน 12 ช่องของ GX Works3 — ใช้ ส่งออก CSV แทน"))
        return self.rows


def rung_grid(r: Rung) -> list[list[Cell | None]]:
    """rung เดียว → แถวละ 12 ช่อง (None = ช่องที่คำสั่งทางซ้ายกินที่อยู่)."""
    if r.is_raw:
        code = rung_code(r)
        if len(code) != 1 or is_label(code[0][0]):
            raise LadderError(tr("rung แบบข้อความคัดลอกไป GX ไม่ได้ — ใช้ ส่งออก CSV แทน"))
        g = _Grid(1)
        g.coil(Coil(code[0][0], tuple(code[0][1])), 0, 0)
        return g.finish()
    nodes = [x for x, _, _ in walk(r)]
    if any(BLANK in getattr(x, "args", ()) for x in nodes):
        raise LadderError(tr("ยังมีช่องที่ไม่ได้กรอก (?) — กรอกให้ครบก่อน"))
    if _inline_in_parallel(nodes):
        raise LadderError(tr("INV/MEP/MEF ในวงจรขนานคัดลอกไป GX ไม่ได้ — ใช้ ส่งออก CSV แทน"))
    g = _Grid(_bh(r.body))
    g.branch(r.body, 0, 0)
    return g.finish()


def _inline_in_parallel(nodes) -> bool:
    return any(isinstance(y, Inline) for x in nodes if isinstance(x, Parallel) for s in x.kids for y in _flat(s))


def _flat(n):
    for k in n.kids:
        yield k
        if isinstance(k, (Series, Parallel)):
            yield from _flat(k)


# ======================= ตาราง → MS-NRBF =======================
_LIB, _LIB2 = 2, 3
_CELL = _NS + "Cell."
_ARR = _CELL + "CopyPasteCell[]"
_V = "Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089"
_GX = "Version=1.110.0.1, Culture=neutral, PublicKeyToken=null"
_STR = f"[System.String, mscorlib, {_V}]"
_LISTSTR = f"[System.Collections.Generic.List`1[{_STR}], mscorlib, {_V}]"
_LIST = f"System.Collections.Generic.List`1[[{_ARR}, LadderEditor, {_GX}]]"
_DICT = "System.Collections.Generic.Dictionary`2[{0},{1}]"
_CMP = f"System.Collections.Generic.GenericEqualityComparer`1[{_STR}]"
_GUIDID = "Melco.GXW3.Domain.Managed.Lang.GuidId"
_BOOL, _I32, _I16, _U8 = (0, 1), (0, 8), (0, 7), (0, 2)


def _i(n: int) -> bytes:
    return struct.pack("<i", n)


def _s(t: str) -> bytes:
    b, out = t.encode(), b""
    n = len(b)
    while n > 127:
        out += bytes([n & 127 | 128])
        n >>= 7
    return out + bytes([n]) + b


def _ref(n: int) -> bytes:
    return b"\x09" + _i(n)


def _type(t) -> bytes:
    k, x = t
    return bytes([x]) if k == 0 else _s(x) if k == 3 else _s(x[0]) + _i(x[1]) if k == 4 else b""


class _Writer:
    """เขียนวัตถุตามลำดับ; คลาสเดิมใช้ ClassWithId อ้างตัวแรก."""

    def __init__(self):
        self.out = bytearray(b"\x00" + _i(1) + _i(-1) + _i(1) + _i(0))
        self.first: dict[str, int] = {}

    def lib(self, n: int, name: str):
        self.out += b"\x0c" + _i(n) + _s(name)

    def obj(self, oid: int, name: str, members, data: bytes, lib: int | None = None):
        if name in self.first:
            self.out += b"\x01" + _i(oid) + _i(self.first[name]) + data
            return
        self.first[name] = oid
        self.out += (b"\x04" if lib is None else b"\x05") + _i(oid) + _s(name) + _i(len(members))
        self.out += b"".join(_s(m) for m, _ in members) + bytes(t[0] for _, t in members)
        self.out += b"".join(_type(t) for _, t in members)
        self.out += (b"" if lib is None else _i(lib)) + data


def _bf(n: str) -> str:
    return f"<{n}>k__BackingField"


_BASE = [("CopyPasteCell+" + _bf("Id"), (4, (_GUIDID, _LIB2))), ("CopyPasteCell+" + _bf("IsVLineConnected"), _BOOL),
         ("CopyPasteCell+" + _bf("IsBindLadderBlock"), _BOOL)]
_INSTR = [(_bf("Instruction"), (1, None)), (_bf("NoteCellCopyPasteCell"), (4, (_CELL + "NoteCellCopyPasteCell", _LIB))),
          (_bf("IsCoil"), _BOOL)]
_MEMBERS = {"Blank": _BASE, "HLine": _BASE, "Single": _INSTR + _BASE, "Command": _INSTR + _BASE,
            "NoArg": [(_bf("InstructionName"), (1, None))] + _BASE}
_GUID = [("_a", _I32), ("_b", _I16), ("_c", _I16)] + [("_" + c, _U8) for c in "defghijk"]


def serialize(rows: list[list[Cell | None]]) -> bytes:
    w = _Writer()
    w.lib(_LIB, f"LadderEditor, {_GX}")
    lst, dev, com, items, cmp_ = 4, 5, 6, 7, 8
    ids = iter(range(9, 1 << 30))
    d1, d2 = _DICT.format(_STR, _LISTSTR), _DICT.format(_STR, _STR)
    w.obj(1, FORMAT, [(_bf("LadderViewCellList"), (3, _LIST)), (_bf("CpuSeries"), _I32),
                      (_bf("DeviceCommentList"), (3, d1)), (_bf("CommentList"), (3, d2))],
          _ref(lst) + _i(CPU_SERIES) + _ref(dev) + _ref(com), _LIB)
    w.obj(lst, _LIST, [("_items", (4, (_ARR + "[]", _LIB))), ("_size", _I32), ("_version", _I32)],
          _ref(items) + _i(len(rows)) + _i(len(rows)))
    dm = [("Version", _I32), ("Comparer", (3, _CMP)), ("HashSize", _I32)]
    for n, name in ((dev, d1), (com, d2)):
        w.obj(n, name, dm, _i(0) + _ref(cmp_) + _i(0))
    row_ids = [next(ids) for _ in rows]
    w.out += b"\x07" + _i(items) + b"\x01" + _i(1) + _i(len(rows)) + b"\x04" + _s(_ARR) + _i(_LIB)
    w.out += b"".join(map(_ref, row_ids))
    w.obj(cmp_, _CMP, [], b"")
    cells = []
    for rid, row in zip(row_ids, rows):
        w.out += b"\x07" + _i(rid) + b"\x00" + _i(1) + _i(len(row)) + b"\x04" + _s(_CELL + "CopyPasteCell") + _i(_LIB)
        for c in row:
            if c is None:
                w.out += b"\x0a"
                continue
            cid = next(ids)
            cells.append((cid, c))
            w.out += _ref(cid)
    w.lib(_LIB2, f"Melco.GXW3.Domain.Managed, {_GX}")
    guids = []
    for cid, c in cells:
        gid = next(ids)
        guids.append(gid)
        data = b"\x06" + _i(next(ids)) + _s(c.text) if c.text else b""
        if c.kind in ("Single", "Command"):
            data += b"\x0a" + bytes([c.coil])
        w.obj(cid, f"{_CELL}{c.kind}CellCopyPasteCell", _MEMBERS[c.kind], data + _ref(gid) + bytes([c.vline, 0]), _LIB)
    for gid in guids:
        w.obj(gid, _GUIDID, [(_bf("Guid"), (3, "System.Guid"))], b"", _LIB2)
        w.obj(-next(ids), "System.Guid", _GUID, uuid.uuid4().bytes_le)      # struct ฝังในตัว → id ติดลบ
    return bytes(w.out + b"\x0b")


_MARK = bytes.fromhex("96a79efd133b7043a67956106bb288fb")     # หัวของข้อมูล .NET บนคลิปบอร์ด


def rungs_grid(rungs: list[Rung]) -> list[list[Cell | None]]:
    rows = []
    for n, r in enumerate(rungs, 1):
        if is_blank(r) or r.is_raw and [op for op, _ in r.raw] == ["END"]:
            continue
        try:
            rows += rung_grid(r)
        except LadderError as e:
            raise LadderError(tr("rung {0}: {1}", n, e)) from e
    if not rows:
        raise LadderError(tr("ยังไม่มีคำสั่ง"))
    return rows


def clipboard_bytes(rungs: list[Rung]) -> bytes:
    """ข้อมูลรูปแบบ FORMAT — LadderError ถ้ามี rung ที่ GX แสดงแบบนี้ไม่ได้."""
    return _MARK + serialize(rungs_grid(rungs))


# ======================= MS-NRBF → ตาราง =======================
_PRIM = {1: "<?", 2: "<B", 6: "<d", 7: "<h", 8: "<i", 9: "<q", 10: "<b", 11: "<f", 12: "<q", 13: "<q", 14: "<H", 15: "<I", 16: "<Q"}


class _Reader:
    """อ่านเป็นข้อมูลล้วน — ไม่สร้างวัตถุ .NET และไม่รันอะไร."""

    def __init__(self, data: bytes):
        self.d, self.i = data, 0
        self.cls: dict[int, tuple] = {}
        self.objs: dict[int, object] = {}

    def u(self, f: str):
        v = struct.unpack_from(f, self.d, self.i)[0]
        self.i += struct.calcsize(f)
        return v

    def i4(self) -> int:
        return self.u("<i")

    def size(self) -> int:
        n = self.i4()
        if not 0 <= n <= len(self.d):
            raise ValueError("size")
        return n

    def s(self) -> str:
        n = k = 0
        while True:
            c = self.u("<B")
            n |= (c & 127) << k
            k += 7
            if c < 128:
                break
            if k > 28:
                raise ValueError("string")
        if self.i + n > len(self.d):
            raise ValueError("string")
        v = self.d[self.i:self.i + n].decode()
        self.i += n
        return v

    def prim(self, t: int):
        return self.s() if t == 18 else self.u(_PRIM[t])

    def types(self, n: int) -> list:
        out = []
        for t in [self.u("<B") for _ in range(n)]:
            x = None
            if t in (0, 7):
                x = self.u("<B")
            elif t == 3:
                x = self.s()
            elif t == 4:
                x = (self.s(), self.i4())
            out.append((t, x))
        return out

    def fill(self, oid: int, c: tuple) -> dict:
        o = self.objs[oid] = {"@": c[0]}
        for name, (t, x) in zip(c[1], c[2]):
            o[name] = self.prim(x) if t == 0 else self.rec()
        return o

    def items(self, n: int) -> list:
        v: list = []
        while len(v) < n:
            r = self.rec()
            if isinstance(r, tuple) and r[0] == "nulls":
                if not 0 < r[1] <= n - len(v):
                    raise ValueError("nulls")
                v += [None] * r[1]
            else:
                v.append(r)
        return v

    def rec(self):
        t = self.u("<B")
        if t == 0:
            return [self.i4() for _ in range(4)]
        if t == 12:
            self.i4(), self.s()
            return self.rec()
        if t in (4, 5):
            oid, name = self.i4(), self.s()
            members = [self.s() for _ in range(self.size())]
            c = self.cls[oid] = (name, members, self.types(len(members)))
            if t == 5:
                self.i4()
            return self.fill(oid, c)
        if t == 1:
            oid, mid = self.i4(), self.i4()
            self.cls[oid] = self.cls[mid]
            return self.fill(oid, self.cls[oid])
        if t == 6:
            oid = self.i4()
            self.objs[oid] = self.s()
            return self.objs[oid]
        if t == 8:
            return self.prim(self.u("<B"))
        if t == 9:
            return ("ref", self.i4())
        if t == 10:
            return None
        if t == 11:
            return "END"
        if t in (13, 14):
            return ("nulls", self.u("<B") if t == 13 else self.i4())
        if t == 15:
            oid, n, pt = self.i4(), self.size(), self.u("<B")
            self.objs[oid] = [self.prim(pt) for _ in range(n)]
            return self.objs[oid]
        if t in (16, 17):
            oid, n = self.i4(), self.size()
            self.objs[oid] = self.items(n)
            return self.objs[oid]
        if t == 7:
            oid, at = self.i4(), self.u("<B")
            rank = self.size()
            lens = [self.size() for _ in range(rank)]
            if at >= 3 or rank != 1:
                raise ValueError("array")
            (k, x), = self.types(1)
            self.objs[oid] = [self.prim(x) for _ in range(lens[0])] if k == 0 else self.items(lens[0])
            return self.objs[oid]
        raise ValueError(t)

    def get(self, x):
        return self.objs[x[1]] if isinstance(x, tuple) and x[0] == "ref" else x


def _read_rows(data: bytes) -> tuple[list[list[Cell | None]], int]:
    """→ (ตาราง, จำนวน Note/statement ที่ไม่ได้เอามา)."""
    if data[:16] != _MARK:
        raise ValueError("mark")
    r = _Reader(data[16:])
    while r.rec() != "END":
        pass
    root = r.objs[1]
    lst = r.get(root[_bf("LadderViewCellList")])
    rows, dropped = [], 0
    for raw in r.get(lst["_items"])[:lst["_size"]]:
        row: list[Cell | None] = []
        for x in r.get(raw):
            x = r.get(x)
            if x is None:
                row.append(None)
                continue
            kind = x["@"].rsplit(".", 1)[-1].removesuffix("CellCopyPasteCell")
            if "Statement" in kind:
                row = []
                dropped += 1
                break
            if kind not in _MEMBERS:
                raise LadderError(tr("มีชิ้นส่วนของ GX ที่ยังไม่รองรับ ({0}) — ใช้ Export to File แล้วนำเข้า CSV แทน", kind))
            if x.get(_bf("NoteCellCopyPasteCell")) is not None:
                dropped += 1
            text = r.get(x.get(_bf("Instruction")) or x.get(_bf("InstructionName")) or "")
            row.append(Cell(kind, text.strip(), bool(x.get(_bf("IsCoil"))), bool(x["CopyPasteCell+" + _bf("IsVLineConnected")])))
        if row:
            rows.append(row)
    return rows, dropped


# ======================= ตาราง → rung =======================
def _bad() -> LadderError:
    return LadderError(tr("วงจรไม่ครบหรือซับซ้อนเกินไป — เลือกทั้ง rung ใน GX ตั้งแต่เส้นซ้ายถึงคอยล์แล้วคัดลอกใหม่"))


def _block_rung(rows: list[list[Cell | None]]) -> list[tuple[str, tuple[str, ...]]]:
    """แถวของ rung เดียว → คำสั่ง: หาจุดต่อ แล้วยุบอนุกรม/ขนานจนเหลือต้นไม้."""
    up: dict = {}

    def find(a):
        if a[1] == 0:
            a = (0, 0)                                  # เส้นไฟซ้าย
        while up.get(a, a) != a:
            a = up[a]
        return a

    def join(a, b):
        a, b = sorted((find(a), find(b)))
        up[b] = a

    parts = []                                          # (แถว, ซ้าย, ขวา, ช่อง)
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            c, w = row[x], 1
            if c is None:
                raise _bad()
            while x + w < len(row) and row[x + w] is None:
                w += 1
            if c.vline:
                if not y:
                    raise _bad()
                join((y, x), (y - 1, x))
            if c.kind == "HLine":
                join((y, x), (y, x + 1))
            elif c.kind != "Blank":
                parts.append((y, (y, x), (y, x + w), c))
            x += w

    root = find((0, 0))
    coils: dict = {}
    edges = []                                          # [แถว, ต้น, ปลาย, Series]
    for y, a, b, c in parts:
        words = tuple(c.text.split())
        if not words:
            raise _bad()
        a, b = find(a), find(b)
        if c.kind == "NoArg" and words[0] in INLINE:
            node = Inline(words[0])
        elif c.coil:
            coils.setdefault(a, []).append((y, Coil(words[0], words[1:])))
            continue
        else:
            sp = _split(words[0])
            if not sp or len(words) < 2:
                raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", c.text[:40]))
            node = Leaf(sp[1], words[1:])
        if a == b:
            raise _bad()
        edges.append([y, a, b, Series([node])])
    if not edges:                                       # RET, FEND, END ... ไม่มีหน้าสัมผัส
        if len(coils.get(root, ())) == 1 and len(coils) == 1 and standalone(coils[root][0][1].op):
            c = coils[root][0][1]
            return [(c.op, c.args)]
        if len(coils) == 1 and [k.op for _, k in coils.get(root, ())] == ["END"]:
            return []
        raise _bad()

    while True:
        ends: dict = {}
        for e in edges:
            ends.setdefault((e[1], e[2]), []).append(e)
        if len(ends) < len(edges):                      # ขนาน
            edges = []
            for (a, b), g in ends.items():
                g.sort(key=lambda e: e[0])
                kids = []
                for e in g:
                    only = e[3].kids[0] if len(e[3].kids) == 1 else None
                    kids += only.kids if len(g) > 1 and isinstance(only, Parallel) else [e[3]]
                edges.append([g[0][0], a, b, Series([Parallel(kids)]) if len(g) > 1 else g[0][3]])
            continue
        for n in {e[2] for e in edges}:                 # อนุกรม
            ins, outs = [e for e in edges if e[2] == n], [e for e in edges if e[1] == n]
            if n != root and len(ins) == len(outs) == 1 and n not in coils and ins[0][1] != n:
                e, f = ins[0], outs[0]
                edges = [k for k in edges if k is not e and k is not f]
                edges.append([min(e[0], f[0]), e[1], f[2], Series(e[3].kids + f[3].kids)])
                break
        else:
            break

    heads = [e[2] for e in edges]
    if len(set(heads)) != len(heads) or root in heads or root in coils or sum(e[1] == root for e in edges) != 1:
        raise _bad()                                    # สะพาน / ต่อจากเส้นไฟหลายทาง
    used: list = []

    def branch(e) -> Branch:
        n = e[2]
        outs = [(y, c) for y, c in coils.get(n, ())] + [(k[0], k) for k in edges if k[1] == n]
        if not outs:
            raise _bad()                                # สายลอย ไม่มีคอยล์
        b = Branch(e[3], [])
        for y, o in sorted(outs, key=lambda t: t[0]):
            if isinstance(o, Coil):
                used.append(y)
                b.outs.append(o)
            else:
                b.outs.append(branch(o))
        return b

    body = branch(next(e for e in edges if e[1] == root))
    if used != sorted(used) or len(used) != sum(map(len, coils.values())):
        raise _bad()                                    # ลำดับทำงานจะเปลี่ยน / มีคอยล์ที่ต่อไม่ถึง
    rung = Rung(body)
    if _inline_in_parallel([x for x, _, _ in walk(rung)]) or any(isinstance(x.cond.kids[0], Inline) for x in [body]):
        raise _bad()
    return [(op, args) for op, args, _ in rung_code(rung)]


def read_text(data: bytes) -> tuple[str, int]:
    """คลิปบอร์ดของ GX Works3 → (ข้อความคำสั่ง ว่างหนึ่งบรรทัดระหว่าง rung, จำนวน Note/statement ที่ไม่ได้เอามา)."""
    try:
        rows, dropped = _read_rows(data)
    except LadderError:
        raise
    except (struct.error, ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as e:
        raise LadderError(tr("อ่านข้อมูลที่คัดลอกจาก GX Works3 ไม่ได้ — ใช้ Export to File แล้วนำเข้า CSV แทน")) from e
    blocks: list[list] = []
    for row in rows:
        if blocks and any(c is not None and c.vline for c in row):
            blocks[-1].append(row)
        else:
            blocks.append([row])
    out = []
    for b in blocks:
        if all(c is not None and c.kind == "Blank" for row in b for c in row):
            continue
        code = _block_rung(b)
        if code:
            out.append("\n".join(" ".join((op, *args)) for op, args in code))
    if not out:
        raise LadderError(tr("ยังไม่มีคำสั่ง"))
    return "\n\n".join(out), dropped
