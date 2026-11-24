"""ตัวแก้ไข ladder (ไม่ใช้ Qt): rung = tree อนุกรม/ขนาน + output หลายตัว ↔ คำสั่ง (LD/ANB/ORB/MPS).

- โครงสร้างถูกเสมอ: ช่องที่ยังไม่กรอกเป็น "?" (ตรวจก่อน RUN จะบอกเอง)
- rung ที่แปลงเป็นรูปไม่ได้เก็บเป็นข้อความคำสั่ง (raw) ไม่ทิ้งและไม่เปลี่ยนความหมาย
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field

from ..i18n import tr
from .csvio import Instr, LadderError, Program
from .model import CONTACT_OPS, COMPARE, OTHER_CONTACT, digits, is_label, kind_of, resolve

BLANK = "?"
MAX_COMMENT = 60
MAX_UNDO = 200
INLINE = ("INV", "MEP", "MEF")
STANDALONE = {"MCR", "FOR", "NEXT", "RET", "SRET", "IRET", "JMP", "FEND", "GOEND", "BREAK", "STL", "RETSTL", "EI", "DI", "WDT"}


def standalone(op: str) -> bool:
    """คำสั่งที่เป็น rung ของตัวเอง ไม่มีหน้าสัมผัส (MCR, RET, FEND, ป้าย P0 ...)."""
    return op in STANDALONE or is_label(op)


_uid = itertools.count(1)


def _new_uid() -> int:
    return next(_uid)


# ======================= โครงสร้าง =======================
@dataclass
class Leaf:
    """หน้าสัมผัส: mod = "" / I / P / F / PI / FI หรือเครื่องหมายเปรียบเทียบ (=, <>, …)."""
    mod: str = ""
    args: tuple[str, ...] = (BLANK,)
    uid: int = field(default_factory=_new_uid)

    def op(self, head: str) -> str:
        return "ANI" if (head, self.mod) == ("AND", "I") else head + self.mod


@dataclass
class Inline:
    """INV / MEP / MEF — ทำกับผลของวงจรทางซ้ายทั้งหมด."""
    name: str
    uid: int = field(default_factory=_new_uid)


@dataclass
class Series:
    kids: list = field(default_factory=list)
    uid: int = field(default_factory=_new_uid)


@dataclass
class Parallel:
    kids: list = field(default_factory=list)      # ทุกตัวเป็น Series
    uid: int = field(default_factory=_new_uid)


@dataclass
class Coil:
    op: str = "OUT"
    args: tuple[str, ...] = (BLANK,)
    uid: int = field(default_factory=_new_uid)


@dataclass
class Branch:
    cond: Series = field(default_factory=Series)
    outs: list = field(default_factory=list)      # Coil | Branch ตามลำดับทำงาน
    uid: int = field(default_factory=_new_uid)


@dataclass
class Rung:
    body: Branch | None = None                    # None = raw
    raw: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    comment: str = ""
    uid: int = field(default_factory=_new_uid)

    @property
    def is_raw(self) -> bool:
        return self.body is None


def new_rung() -> Rung:
    return Rung(Branch(Series([Leaf()]), [Coil()]))


def is_blank(r: Rung) -> bool:
    """rung ที่ยังไม่ได้กรอกอะไรเลย (ไม่นับเป็นโปรแกรม)."""
    if r.is_raw:
        return not r.raw
    b = r.body
    return len(b.cond.kids) == 1 and isinstance(b.cond.kids[0], Leaf) and b.cond.kids[0].args == (BLANK,) \
        and not b.cond.kids[0].mod and len(b.outs) == 1 and isinstance(b.outs[0], Coil) \
        and (b.outs[0].op, b.outs[0].args) == ("OUT", (BLANK,))


# ======================= tree → คำสั่ง =======================
def _block(node, out):
    """วงจรเริ่มด้วย LD."""
    if isinstance(node, Leaf):
        out.append((node.op("LD"), node.args, node.uid))
    elif isinstance(node, Series):
        _block(node.kids[0], out)
        _tail(node.kids[1:], out)
    else:
        _block(node.kids[0], out)
        for k in node.kids[1:]:
            if len(k.kids) == 1 and isinstance(k.kids[0], Leaf):
                out.append((k.kids[0].op("OR"), k.kids[0].args, k.kids[0].uid))
            else:
                _block(k, out)
                out.append(("ORB", (), node.uid))


def _tail(kids, out):
    """ต่ออนุกรมกับวงจรที่มีอยู่แล้ว."""
    for k in kids:
        if isinstance(k, Leaf):
            out.append((k.op("AND"), k.args, k.uid))
        elif isinstance(k, Inline):
            out.append((k.name, (), k.uid))
        else:
            _block(k, out)
            out.append(("ANB", (), k.uid))


def _outs(b: Branch, out):
    items = b.outs
    f = next((i for i, x in enumerate(items) if isinstance(x, Branch)), len(items))
    if f == len(items) - 1 and not isinstance(items[f].cond.kids[0], Leaf):
        f = 0                              # LD หลังคอยล์ = ขึ้น rung ใหม่ → ต้องคั่นด้วย MPS/MPP
    for c in items[:f]:
        out.append((c.op, c.args, c.uid))
    rest = items[f:]
    if len(rest) == 1:
        _tail(rest[0].cond.kids, out)
        _outs(rest[0], out)
        return
    for i, x in enumerate(rest):
        coil = isinstance(x, Coil)
        if not (coil and isinstance(rest[i - 1], Coil)):        # คอยล์ติดกันใช้ค่าเดิมต่อได้
            last = not any(isinstance(y, Branch) for y in rest[i + 1:]) and (i == len(rest) - 1 or coil)
            out.append(("MPS" if i == 0 else "MPP" if last else "MRD", (), b.uid))
        if coil:
            out.append((x.op, x.args, x.uid))
        else:
            _tail(x.cond.kids, out)
            _outs(x, out)


def rung_code(r: Rung) -> list[tuple[str, tuple[str, ...], int]]:
    if r.is_raw:
        return [(op, args, r.uid) for op, args in r.raw]
    out: list = []
    _block(r.body.cond, out)
    _outs(r.body, out)
    return out


# ======================= คำสั่ง → tree =======================
class _NoTree(Exception):
    pass


def _split(op: str) -> tuple[str, str] | None:
    if op in CONTACT_OPS:
        return CONTACT_OPS[op]
    m = COMPARE.match(op) or OTHER_CONTACT.match(op)
    return (m.group(1), op[len(m.group(1)):]) if m and kind_of(op) in ("compare", "unknown_contact") else None


def _has_inline(s: Series) -> bool:
    return any(isinstance(k, Inline) for k in s.kids)


def _join(a: Series, b: Series):
    """ANB: a แล้วต่อด้วย b."""
    if _has_inline(b):
        raise _NoTree                      # INV ของก้อน b จะกลายเป็นกลับค่า a ด้วย
    a.kids += b.kids


def _or(a: Series, b: Series) -> Series:
    if len(a.kids) == 1 and isinstance(a.kids[0], Parallel):
        a.kids[0].kids.append(b)
        return a
    return Series([Parallel([a, b])])


def build_rung(code: list[tuple[str, tuple[str, ...]]]) -> Rung:
    """ลำดับคำสั่งของ 1 rung → Rung (แปลงไม่ได้ = raw)."""
    try:
        r = Rung(_build(code))
        if [(o, a) for o, a, _ in rung_code(r)] and _equiv(code, r):
            return r
    except (_NoTree, IndexError):
        pass
    return Rung(None, list(code))


def _equiv(code, r) -> bool:
    """กันพลาด: แปลงกลับแล้วต้องมี operand ชุดเดิมครบตามลำดับ (ไม่หาย ไม่เพิ่ม)."""
    stack = {"ANB", "ORB", "MPS", "MRD", "MPP"}
    old = [a for o, a in code if o not in stack]
    return old == [a for o, a, _ in rung_code(r) if o not in stack]


def _build(code) -> Branch:
    st: list[Series] = []
    root: Branch | None = None
    cur: Branch | None = None
    extra = Series()
    mps: list[Branch] = []

    def settle():
        """ปิดเงื่อนไขที่ค้างก่อนเจอ output/MPS."""
        nonlocal root, cur, extra
        if root is None:
            if len(st) != 1:
                raise _NoTree
            root = cur = Branch(st.pop(), [])
        else:
            if st:
                raise _NoTree
            if extra.kids:
                b = Branch(extra, [])
                cur.outs.append(b)
                cur, extra = b, Series()

    for op, args in code:
        sp = _split(op)
        if sp:
            head, mod = sp
            leaf = Leaf(mod, tuple(args))
            if head == "LD":
                st.append(Series([leaf]))
            elif head == "AND":
                (st[-1] if st else _need(root, extra)).kids.append(leaf)
            else:
                if not st:
                    raise _NoTree
                st[-1] = _or(st[-1], Series([leaf]))
        elif op == "ANB":
            b = st.pop()
            _join(st[-1] if st else _need(root, extra), b)
        elif op == "ORB":
            b = st.pop()
            st[-1] = _or(st[-1], b)
        elif op in INLINE:
            (st[-1] if st else _need(root, extra)).kids.append(Inline(op))
        elif op == "MPS":
            settle()
            mps.append(cur)
        elif op in ("MRD", "MPP"):
            if st or extra.kids or not mps or not cur.outs:
                raise _NoTree
            cur = mps[-1] if op == "MRD" else mps.pop()
        elif kind_of(op) == "out" or op in ("CJ", "CJP", "CALL", "CALLP", "SCJ"):
            settle()
            cur.outs.append(Coil(op, tuple(args)))
        else:
            raise _NoTree
    if root is None or st or extra.kids or mps:
        raise _NoTree
    _check_outs(root)
    return root


def _need(root, extra) -> Series:
    if root is None:
        raise _NoTree
    return extra


def _check_outs(b: Branch):
    if not b.outs:
        raise _NoTree
    for x in b.outs:
        if isinstance(x, Branch):
            _check_outs(x)


def split_rungs(code: list[tuple]) -> list[list[int]]:
    """แบ่งลำดับคำสั่งเป็น rung → [[ลำดับคำสั่ง, …], …]."""
    out: list[list[int]] = []
    cur: list[int] = []
    prev_out, depth = True, 0
    for k, (op, _args) in enumerate(code):
        sp = _split(op)
        alone = op in STANDALONE or kind_of(op) == "ignore"
        if cur and prev_out and depth <= 0 and (alone or sp and sp[0] == "LD"):
            out.append(cur)
            cur, depth = [], 0
        if op == "MPS":
            depth += 1
        elif op == "MPP":
            depth -= 1
        cur.append(k)
        if sp or op in ("MRD", "MPP"):
            prev_out = False
        elif kind_of(op) not in ("stack",):
            prev_out = True
    if cur:
        out.append(cur)
    return out


# ======================= เอกสาร =======================
@dataclass
class Compiled:
    program: Program
    where: list[tuple[int, int]]          # ลำดับคำสั่ง → (ลำดับ rung, uid ของชิ้น)


class LadderDoc:
    def __init__(self, app_base: int = 8, name: str = ""):
        self.app_base, self.name = app_base, name
        self.rungs: list[Rung] = [new_rung()]
        self._undo: list[list[Rung]] = []
        self._redo: list[list[Rung]] = []
        self.revision = 0                 # เพิ่มทุกครั้งที่แก้ (ใช้บอก "แก้แล้วยังไม่ส่ง" / บันทึกอัตโนมัติ)

    @property
    def module(self) -> str:
        return "FX5UCPU" if self.app_base == 8 else "RCPU R04"

    # ---------- แปลง ----------
    def compile(self, keep_blank: bool = False) -> Compiled:
        """keep_blank: เก็บ rung ว่างไว้ด้วย (บันทึกไฟล์) — ตอน RUN rung ว่างไม่นับ."""
        instrs, where, comments = [], [], {}
        for n, r in enumerate(self.rungs):
            if is_blank(r) and not (keep_blank or r.comment):
                continue
            if r.comment:
                comments[len(instrs)] = r.comment
            if is_blank(r) and not keep_blank:
                continue
            for op, args, uid in rung_code(r):
                instrs.append(Instr(len(instrs), op, tuple(args)))
                where.append((n, uid))
        if not instrs or instrs[-1].op != "END":
            instrs.append(Instr(len(instrs), "END"))
            where.append((len(self.rungs) - 1, 0))
        return Compiled(Program(self.name, self.module, instrs, comments), where)

    def load(self, prog: Program) -> int:
        """แทนทั้งเอกสารด้วย Program (ล้าง undo) — คืนจำนวน rung ที่ต้องเก็บเป็นข้อความ."""
        self.rungs = rungs_from(rebase(prog, self.app_base))
        self._undo.clear()
        self._redo.clear()
        self.revision += 1
        return sum(r.is_raw and not _expected_raw(r) for r in self.rungs)

    # ---------- undo ----------
    def _mark(self):
        self._undo.append(copy.deepcopy(self.rungs))
        del self._undo[:-MAX_UNDO]
        self._redo.clear()
        self.revision += 1

    def undo(self) -> bool:
        return self._swap(self._undo, self._redo)

    def redo(self) -> bool:
        return self._swap(self._redo, self._undo)

    def _swap(self, src, dst) -> bool:
        if not src:
            return False
        dst.append(self.rungs)
        self.rungs = src.pop()
        self.revision += 1
        return True

    def merge_undo(self):
        """รวมการแก้ครั้งล่าสุดเข้ากับครั้งก่อนหน้า (undo ครั้งเดียว)."""
        if len(self._undo) >= 2:
            self._undo.pop()

    def drop_redo(self):
        self._redo.clear()

    def replace_all(self, rungs: list[Rung]) -> None:
        """แทนทั้งเอกสาร (undo ได้)."""
        self._mark()
        self.rungs = rungs or [new_rung()]

    # ---------- ค้นหา ----------
    def rung_of(self, uid: int) -> int:
        for n, r in enumerate(self.rungs):
            if r.uid == uid or any(x.uid == uid for x, _, _ in walk(r)):
                return n
        return -1

    def find(self, uid: int):
        """(ชิ้น, list ที่ใส่ชิ้นนั้น, เจ้าของ list) หรือ None."""
        for r in self.rungs:
            for x, box, owner in walk(r):
                if x.uid == uid:
                    return x, box, owner
        return None

    # ---------- แก้หน้าสัมผัส ----------
    def set_leaf(self, uid: int, mod: str, args) -> bool:
        f = self.find(uid)
        if not f or not isinstance(f[0], Leaf):
            return False
        new = (mod, tuple(a.upper() for a in args) or (BLANK,))
        if (f[0].mod, f[0].args) == new:
            return False
        self._mark()
        x = self.find(uid)[0]
        x.mod, x.args = new
        return True

    def add_series(self, uid: int, node, before: bool = False) -> int | None:
        """แทรกหน้าสัมผัส/INV อนุกรมถัดจากชิ้น uid (หน้าสัมผัส, ก้อนขนาน หรือ INV) — uid ของ output = ต่อท้ายเงื่อนไขของมัน."""
        f = self.find(uid)
        if not f:
            return None
        if isinstance(f[0], Coil):
            if isinstance(node, Coil) or not isinstance(f[2], Branch):
                return None
            self._mark()
            self.find(uid)[2].cond.kids.append(node)
            return node.uid
        if not isinstance(f[2], Series):
            return None
        if isinstance(node, Inline) and before and self._first(f):
            return None                                   # INV อยู่หน้าสุดไม่ได้ (ไม่มีวงจรทางซ้าย)
        self._mark()
        _, box, _ = self.find(uid)
        i = _index(box, uid)
        box.insert(i if before else i + 1, node)
        return node.uid

    @staticmethod
    def _first(f) -> bool:
        return _index(f[1], f[0].uid) == 0

    def add_parallel(self, uid: int, node: Leaf | None = None, last_uid: int | None = None) -> int | None:
        """ขนานชิ้น uid (ถึง last_uid ใน Series เดียวกัน) ด้วยหน้าสัมผัสใหม่."""
        f = self.find(uid)
        if not f or not isinstance(f[2], Series):
            return None
        box = f[1]
        i = _index(box, uid)
        j = _index(box, last_uid) if last_uid is not None else i
        if j < 0:
            return None
        i, j = min(i, j), max(i, j)
        if any(isinstance(x, Inline) for x in box[i:j + 1]):
            return None
        node = node or Leaf()
        self._mark()
        _, box, owner = self.find(uid)
        grp = box[i:j + 1]
        if len(grp) == 1 and isinstance(grp[0], Parallel):
            grp[0].kids.append(Series([node]))
        else:
            up = self._parent_parallel(owner)
            if up is not None and i == 0 and j == len(box) - 1:
                up.kids.insert(_index(up.kids, owner.uid) + 1, Series([node]))       # ทั้งกิ่ง → เพิ่มกิ่งข้าง ๆ
            else:
                box[i:j + 1] = [Parallel([Series(grp), Series([node])])]
        return node.uid

    def _parent_parallel(self, s: Series):
        for r in self.rungs:
            for x, _, _ in walk(r):
                if isinstance(x, Parallel) and any(k is s for k in x.kids):
                    return x
        return None

    # ---------- output ----------
    def set_coil(self, uid: int, op: str, args) -> bool:
        f = self.find(uid)
        if not f or not isinstance(f[0], Coil):
            return False
        new = (op.upper(), tuple(a.upper() for a in args))
        if (f[0].op, f[0].args) == new:
            return False
        self._mark()
        x = self.find(uid)[0]
        x.op, x.args = new
        return True

    def add_coil(self, uid: int, coil: Coil | None = None, branch: bool = False) -> int | None:
        """เพิ่ม output ใต้ชิ้น uid (output / หน้าสัมผัสใน rung เดียวกัน); branch = มีหน้าสัมผัสของตัวเอง."""
        n = self.rung_of(uid)
        if n < 0 or self.rungs[n].is_raw:
            return None
        coil = coil or Coil()
        self._mark()
        f = self.find(uid)
        if f and isinstance(f[0], Coil):
            owner, at = f[2], _index(f[1], uid) + 1
        else:
            owner = (f and self._branch_of(n, uid)) or self.rungs[n].body
            at = len(owner.outs)
        item = Branch(Series([Leaf()]), [coil]) if branch else coil
        owner.outs.insert(at, item)
        return item.cond.kids[0].uid if branch else coil.uid

    def _branch_of(self, n: int, uid: int):
        hit = None
        for b in branches(self.rungs[n].body):
            if any(x.uid == uid for x, _, _ in _walk_series(b.cond)):
                hit = b
        return hit

    # ---------- ลบ ----------
    def delete(self, uid: int) -> bool:
        f = self.find(uid)
        if not f:
            return False
        self._mark()
        x, box, owner = self.find(uid)
        del box[_index(box, uid)]
        n = self._rung_index_after_delete(owner, box)
        self._tidy(n)
        return True

    def _rung_index_after_delete(self, owner, box) -> int:
        for n, r in enumerate(self.rungs):
            if not r.is_raw and (any(b is owner for b in branches(r.body))
                                 or any(s.kids is box for b in branches(r.body) for s in _all_series(b.cond))):
                return n
        return -1

    def _tidy(self, n: int):
        if n >= 0 and not self.rungs[n].is_raw:
            _clean_branch(self.rungs[n].body, True)

    # ---------- rung ----------
    def insert_rung(self, at: int, rung: Rung | None = None) -> int:
        self._mark()
        at = max(0, min(at, len(self.rungs)))
        self.rungs.insert(at, rung or new_rung())
        return at

    def delete_rung(self, n: int) -> bool:
        if not 0 <= n < len(self.rungs):
            return False
        self._mark()
        del self.rungs[n]
        if not self.rungs:
            self.rungs.append(new_rung())
        return True

    def delete_rungs(self, first: int, last: int) -> None:
        self._mark()
        del self.rungs[first:last + 1]
        if not self.rungs:
            self.rungs.append(new_rung())

    def move_rung(self, n: int, d: int) -> int:
        m = n + d
        if not (0 <= n < len(self.rungs) and 0 <= m < len(self.rungs)) or not d:
            return n
        self._mark()
        self.rungs.insert(m, self.rungs.pop(n))
        return m

    def set_comment(self, n: int, text: str) -> bool:
        text = " ".join(text.split())[:MAX_COMMENT]
        if not 0 <= n < len(self.rungs) or self.rungs[n].comment == text:
            return False
        self._mark()
        self.rungs[n].comment = text
        return True

    # ---------- ข้อความคำสั่ง ----------
    def rung_text(self, n: int) -> str:
        return "\n".join(" ".join((op, *args)) for op, args, _ in rung_code(self.rungs[n]))

    def set_rung_text(self, n: int, text: str) -> None:
        """แทน rung ด้วยคำสั่งที่พิมพ์ (หลาย rung ได้) — ผิดรูปแบบ = LadderError และไม่เปลี่ยนอะไร."""
        new = rungs_from_text(text)
        if not new:
            raise LadderError(tr("ยังไม่มีคำสั่ง"))
        self._mark()
        new[0].comment = self.rungs[n].comment
        self.rungs[n:n + 1] = new

    def copy_text(self, first: int, last: int) -> str:
        """rung เป็นข้อความสำหรับคลิปบอร์ด (คอมเมนต์ขึ้นต้นด้วย ;)."""
        parts = []
        for n in range(max(first, 0), min(last, len(self.rungs) - 1) + 1):
            c = self.rungs[n].comment
            parts.append((f"; {c}\n" if c else "") + self.rung_text(n))
        return "\n\n".join(parts)

    def paste_text(self, at: int, text: str) -> int:
        new = rungs_from_text(text)
        if not new:
            raise LadderError(tr("ยังไม่มีคำสั่ง"))
        self._mark()
        at = max(0, min(at, len(self.rungs)))
        self.rungs[at:at] = new
        return len(new)


# ======================= ตัวช่วย =======================
def _index(box, uid) -> int:
    return next((i for i, x in enumerate(box) if x.uid == uid), -1)


def _walk_series(s: Series):
    for k in s.kids:
        yield k, s.kids, s
        if isinstance(k, Parallel):
            for sub in k.kids:
                yield from _walk_series(sub)


def _all_series(s: Series):
    yield s
    for k in s.kids:
        if isinstance(k, Parallel):
            for sub in k.kids:
                yield from _all_series(sub)


def branches(b: Branch):
    yield b
    for x in b.outs:
        if isinstance(x, Branch):
            yield from branches(x)


def walk(r: Rung):
    """(ชิ้น, list ที่อยู่, เจ้าของ) ของหน้าสัมผัส/ก้อนขนาน/INV/output ทุกตัวใน rung."""
    if r.is_raw:
        return
    for b in branches(r.body):
        yield from _walk_series(b.cond)
        for x in b.outs:
            if isinstance(x, Coil):
                yield x, b.outs, b


def _clean_series(s: Series):
    out = []
    for k in s.kids:
        if isinstance(k, Parallel):
            for sub in k.kids:
                _clean_series(sub)
            k.kids = [sub for sub in k.kids if sub.kids]
            if not k.kids:
                continue
            if len(k.kids) == 1 and not _has_inline(k.kids[0]):
                out += k.kids[0].kids                    # เหลือกิ่งเดียว = อนุกรม
                continue
            flat = []
            for sub in k.kids:                           # ขนานซ้อนขนานล้วน → ชั้นเดียว
                flat += sub.kids[0].kids if len(sub.kids) == 1 and isinstance(sub.kids[0], Parallel) else [sub]
            k.kids = flat
        out.append(k)
    while out and isinstance(out[0], Inline):            # INV ที่ไม่มีอะไรทางซ้าย
        out.pop(0)
    s.kids = out


def _clean_branch(b: Branch, root: bool):
    """ลบแล้วโครงสร้างต้องยังถูก: เงื่อนไข/คอยล์ที่หายหมดกลายเป็นช่องว่าง ?."""
    if root:
        _clean_series(b.cond)
        if not b.cond.kids:
            b.cond.kids = [Leaf()]
    else:
        out = b.cond.kids
        for k in out:
            if isinstance(k, Parallel):
                tmp = Series([k])
                _clean_series(tmp)
        kids = []
        for k in out:
            if isinstance(k, Parallel):
                if not k.kids:
                    continue
                if len(k.kids) == 1 and not _has_inline(k.kids[0]):
                    kids += k.kids[0].kids
                    continue
            kids.append(k)
        b.cond.kids = kids
    new = []
    for x in b.outs:
        if isinstance(x, Branch):
            _clean_branch(x, False)
            if not x.outs:
                continue
            if not x.cond.kids:
                new += x.outs                            # กิ่งไม่มีหน้าสัมผัสแล้ว → ต่อกับกิ่งแม่
                continue
        new.append(x)
    b.outs = new
    if root and not b.outs:
        b.outs = [Coil()]


def _expected_raw(r: Rung) -> bool:
    return bool(r.raw) and all(op in STANDALONE or kind_of(op) == "ignore" for op, _ in r.raw)


def rungs_from(prog: Program) -> list[Rung]:
    code = [(i.op, i.args) for i in prog.instrs]
    while code and code[-1][0] in ("END", "NOP"):
        code.pop()
    # ความเห็นของบรรทัดที่อยู่กลาง rung ย้ายไปหัว rung นั้น
    out = []
    for ks in split_rungs(code):
        part = [code[k] for k in ks if code[k][0] != "NOP"]
        if not part:
            continue
        r = build_rung(part)
        r.comment = " / ".join(prog.comments[k] for k in ks if k in prog.comments)[:MAX_COMMENT]
        out.append(r)
    return out or [new_rung()]


def parse_line(line: str) -> tuple[str, tuple[str, ...]]:
    p = line.upper().split()
    return p[0], tuple(p[1:])


def rungs_from_text(text: str) -> list[Rung]:
    """คำสั่งบรรทัดละ 1 ตัว (หรือคั่นด้วย ;) — บรรทัดขึ้นต้นด้วย ; เป็นคอมเมนต์ของ rung ถัดไป."""
    code, comments = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(";"):
            c = line.lstrip("; ").strip()
            if c:
                comments[len(code)] = c[:MAX_COMMENT]
            continue
        for part in line.split(";"):
            if part.strip():
                op, args = parse_line(part)
                if len(op) > 16 or len(args) > 8 or any(len(a) > 32 for a in args):
                    raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", part.strip()[:40]))
                code.append((op, args))
    if not code or code and all(op in ("END", "NOP") for op, _ in code):
        return []
    if len(code) > 4000:
        raise LadderError(tr("ladder ยาวเกินไป ({0} คำสั่ง, สูงสุด {1})", len(code), 4000))
    return rungs_from(Program("", "", [Instr(k, o, a) for k, (o, a) in enumerate(code)], comments))


def rebase(prog: Program, app_base: int) -> Program:
    """เปลี่ยนเลข X/Y จากฐานในไฟล์เป็นฐานที่โปรแกรมใช้ (device เดิม)."""
    if not prog.module or prog.xy_base == app_base:
        return prog

    def conv(a):
        if a[:1] in ("X", "Y"):
            r = resolve(a, prog.xy_base, app_base)
            if r:
                return r[1]
        d = digits(a, prog.xy_base, app_base)
        return d[1] if d else a
    return Program(prog.name, prog.module, [Instr(i.step, i.op, tuple(conv(a) for a in i.args)) for i in prog.instrs],
                   dict(prog.comments))
