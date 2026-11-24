"""โครงสร้าง ladder: แยกชนิดคำสั่ง, address ที่อ่าน/เขียน และเงื่อนไขของแต่ละคอยล์เป็น expression tree."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..plc.device import Device
from .csvio import Instr, Program

CONTACT = re.compile(r"^(LD|AND|OR|AN|OR)(I|P|F|PI|FI)?$")
CONTACT_OPS = {a + b: (a, b) for a in ("LD", "AND", "OR") for b in ("", "I", "P", "F", "PI", "FI")}
CONTACT_OPS.pop("ANDI")
CONTACT_OPS["ANI"] = ("AND", "I")
COMPARE = re.compile(r"^(LD|AND|OR)(D?(?:=|<>|>=|<=|>|<))$")
OTHER_CONTACT = re.compile(r"^(LD|AND|OR)(?!B$).+$")
STACK_OPS = {"ANB", "ORB", "MPS", "MRD", "MPP", "INV", "MEP", "MEF"}
FLOW_OPS = {"CJ", "CJP", "SCJ", "JMP", "CALL", "CALLP", "RET", "SRET", "IRET", "FOR", "NEXT", "BREAK", "GOEND",
            "FCALL", "XCALL", "ECALL", "STL", "RETSTL", "STEP", "BLOCK"}
JUMPS = {"CJ", "CJP", "JMP"}                       # ที่ PLC ในตัวรันได้ (การวินิจฉัยยังไม่จำลอง)
CALLS = {"CALL", "CALLP"}
RETS = {"RET", "SRET"}
IGNORE = {"END", "FEND", "NOP", "NOPLF", "PAGE", "EI", "DI", "WDT"}
ARITH = {"+", "-", "*", "/"}
KNOWN_FUNC = {"MOV", "INC", "DEC", "FMOV", "BMOV", "BCD", "BIN"} | ARITH
WIDE_FUNC = {"D" + f for f in {"MOV", "INC", "DEC", "BCD", "BIN"} | ARITH}       # 32 บิต: ใช้ word คู่ (ตัวล่าง, ตัวถัดไป)
KNOWN_FUNC |= WIDE_FUNC
WIDE_WORDS = {"D", "W", "SD"}

_DEV = re.compile(r"^(SM|SD|ST|X|Y|M|D|L|B|W|T|C|F|V)([0-9A-F]+)$")
BITS = {"X", "Y", "M", "L", "B", "SM", "TS", "CS", "STS", "F", "V"}
HEX_KINDS = {"B", "W"}
_DIGIT = re.compile(r"^K([1-8])((?:SM|X|Y|M|L|B|F|V)[0-9A-F]+)$")
DIGIT_OPS = KNOWN_FUNC - {"FMOV", "BMOV"}       # คำสั่งที่ใช้ K4X0 ได้ (ที่เหลือถือว่าอ่านไม่ออก)


def join_op(kind: str, mod: str) -> str:
    return "ANI" if (kind, mod) == ("AND", "I") else kind + mod


def resolve(arg: str, file_base: int, app_base: int) -> tuple[str, str] | None:
    """ชื่อใน ladder → (ชนิด, ชื่อที่ใช้ในโปรแกรม) ; T0/C0/ST0 คืนชนิดตัวเอง ; อ่านไม่ออก = None."""
    m = _DEV.match(arg)
    if not m:
        return None
    k, num = m.groups()
    try:
        n = int(num, file_base if k in ("X", "Y") else 16 if k in HEX_KINDS else 10)
    except ValueError:
        return None
    return k, (Device(k, n, app_base).name if k in ("X", "Y") else f"{k}{n}")


def digits(arg: str, file_base: int, app_base: int) -> tuple[str, str, tuple[str, ...]] | None:
    """K4X0 = บิตต่อกัน 4×4 ตัว → ("K", ชื่อ, บิตจากต่ำไปสูง) ; ไม่ใช่รูปนี้ = None."""
    m = _DIGIT.match(arg)
    r = resolve(m.group(2), file_base, app_base) if m else None
    if not r:
        return None
    k, name = r
    n, count = int(name[len(k):], app_base if k in ("X", "Y") else 10), 4 * int(m.group(1))
    bits = tuple(Device(k, n + j, app_base).name if k in ("X", "Y") else f"{k}{n + j}" for j in range(count))
    return "K", f"K{m.group(1)}{name}", bits


def constant(arg: str, wide: bool = False) -> int | None:
    half = 1 << (31 if wide else 15)
    try:
        if arg[0] == "K":
            return int(arg[1:])
        if arg[0] == "H":
            v = int(arg[1:], 16)
            return v - 2 * half if half <= v < 2 * half else v          # เกินช่วง = คงไว้ให้ check แจ้ง
    except (ValueError, IndexError):
        pass
    return None


def base_func(op: str) -> tuple[str, bool]:
    """(คำสั่ง, ทำเฉพาะขอบขาขึ้นไหม)  MOVP → (MOV, True)."""
    if op in KNOWN_FUNC:
        return op, False
    if op.endswith("P") and op[:-1] in KNOWN_FUNC:
        return op[:-1], True
    return op, False


def is_label(op: str) -> bool:
    return bool(re.match(r"^P\d+$", op))


def is_wide(op: str) -> bool:
    """คำสั่ง 32 บิตที่รู้จัก (DMOV, D+, LDD= ...)."""
    m = COMPARE.match(op)
    return m.group(2)[0] == "D" if m else base_func(op)[0] in WIDE_FUNC


def kind_of(op: str) -> str:
    """contact / compare / unknown_contact / stack / flow / ignore / out."""
    if op in CONTACT_OPS:
        return "contact"
    if COMPARE.match(op):
        return "compare"
    if op in STACK_OPS:
        return "stack"
    if op in FLOW_OPS:
        return "flow"
    if op in IGNORE or re.match(r"^[PI]\d+$", op):
        return "ignore"
    if OTHER_CONTACT.match(op):
        return "unknown_contact"
    return "out"


# ---------------- expression ----------------
@dataclass
class Node:
    kind: str                         # leaf / and / or / not / edge
    i: int = -1                       # ลำดับคำสั่ง (leaf / edge)
    kids: list["Node"] = field(default_factory=list)


def _and(a: Node | None, b: Node) -> Node:
    return b if a is None else Node("and", kids=[a, b])


class Ladder:
    """Program + address ที่แปลงแล้ว + tree ของแต่ละ output."""

    def __init__(self, prog: Program, app_base: int = 8):
        self.prog, self.app_base = prog, app_base
        self.instrs: list[Instr] = prog.instrs
        self.kinds = [kind_of(i.op) for i in self.instrs]
        self.args: list[list[tuple[str, str] | int | None]] = []
        for ins in self.instrs:
            row = []
            for a in ins.args:
                c = constant(a, is_wide(ins.op))
                row.append(c if c is not None else digits(a, prog.xy_base, app_base) or resolve(a, prog.xy_base, app_base))
            self.args.append(row)
        self.unknown_ops: list[int] = []
        self.flow = [k for k, kd in enumerate(self.kinds) if kd == "flow"]
        self.written: dict[str, list[int]] = {}       # ชื่อหน่วยความจำ → คำสั่งที่เขียน
        self.read: dict[str, list[int]] = {}
        self.tree: dict[int, Node | None] = {}        # output → เงื่อนไข
        self.rung_of: list[int] = []                  # ลำดับคำสั่งแรกของ rung
        self._scan_io()
        self._build()

    # ---------- address ----------
    def _scan_io(self):
        for k, ins in enumerate(self.instrs):
            kd, args = self.kinds[k], self.args[k]
            if kd == "contact" or kd == "unknown_contact" and len(args) == 1:
                if args and isinstance(args[0], tuple) and args[0][0] == "K":
                    self.unknown_ops.append(k)                   # K4X0 เป็นหน้าสัมผัสไม่ได้
                    continue
                if args and isinstance(args[0], tuple):
                    self.read.setdefault(bit_name(args[0]), []).append(k)
                if not args or not isinstance(args[0], tuple) or kd == "unknown_contact":
                    self.unknown_ops.append(k)
            elif kd in ("compare", "unknown_contact"):
                wide = kd == "compare" and is_wide(ins.op)
                for a in args:
                    for n in cells(a, wide) if isinstance(a, tuple) else ():
                        self.read.setdefault(n, []).append(k)
                if kd == "unknown_contact" or any(a is None for a in args) or len(args) != 2 \
                        or any(isinstance(a, tuple) and not (fits(a, wide) if a[0] == "K" or wide else True) for a in args):
                    self.unknown_ops.append(k)
            elif kd == "out":
                w, r, ok = self.effects(k)
                for n in w:
                    self.written.setdefault(n, []).append(k)
                for n in r:
                    self.read.setdefault(n, []).append(k)
                if not ok:
                    self.unknown_ops.append(k)

    def effects(self, k: int) -> tuple[list[str], list[str], bool]:
        """(ที่เขียน, ที่อ่าน, รู้จักคำสั่งครบไหม) ของคำสั่ง output."""
        ins, args = self.instrs[k], self.args[k]
        op, a0 = ins.op, (args[0] if args else None)
        if base_func(op)[0] not in DIGIT_OPS and any(isinstance(a, tuple) and a[0] == "K" for a in args):
            names = [n for a in args if isinstance(a, tuple) for n in dict.fromkeys([bit_name(a), *cells(a)]) if a[0] != "K" or n in a[2]]
            return names, names, False
        dev = isinstance(a0, tuple)
        rest = [word_name(a) for a in args[1:] if isinstance(a, tuple)]
        if op in ("OUT", "OUTH"):
            if not dev:
                return [], rest, False
            if a0[0] in ("T", "C", "ST"):
                ok = len(args) > 1 and args[1] is not None
                return [bit_name(a0), word_name(a0)], rest, ok
            return [a0[1]], [], op == "OUT" and a0[0] in BITS and len(args) == 1 and a0[1] != "SM4095"
        if op in ("SET", "RST", "PLS", "PLF", "FF"):
            if not dev:
                return [], [], False
            if a0[0] in ("T", "C", "ST"):
                return [bit_name(a0), word_name(a0)], [], op == "RST"
            return [a0[1]], [], op == "RST" or a0[0] in BITS
        if op == "MC":
            m = args[1] if len(args) > 1 and isinstance(args[1], tuple) else None
            return ([m[1]] if m else []), [], m is not None
        if op == "MCR":
            return [], [], True
        f, _ = base_func(op)
        words = [a for a in args if isinstance(a, tuple)]
        ok = all(a is not None for a in args) and all(a[0] not in BITS for a in words)
        if any(a[0] == "K" and not fits(a, f in WIDE_FUNC) for a in words):
            ok = False
        if f in WIDE_FUNC:
            r = self._wide_effects(f[1:], args)
            if r:
                return *r, ok and all(fits(a, True) for a in words) and not (f[1:] in ("*", "/") and words[-1][0] == "K")
            if ok:                                   # จำนวน operand ผิด: อย่างน้อยรู้ว่าแตะ word คู่ไหน
                names = [n for a in words for n in cells(a, True)]
                return names, names, False
        if f in ("INC", "DEC") and len(args) == 1 and dev:
            return cells(a0), cells(a0), ok
        if f in ("MOV", "BCD", "BIN") and len(args) == 2 and isinstance(args[1], tuple):
            return cells(args[1]), (cells(a0) if dev else []), ok
        if f in ARITH and len(args) in (2, 3) and isinstance(args[-1], tuple):
            d = args[-1]
            dst = cells(d) + ([shift(word_name(d), 1)] if f in "*/" and d[0] != "K" else [])
            src = args[:2]
            return dst, [n for a in src if isinstance(a, tuple) for n in cells(a)], \
                ok and d[0] in (("D", "W", "SD") if f in "*/" else ("D", "W", "SD", "K"))
        if f in ("FMOV", "BMOV") and len(args) == 3 and isinstance(args[1], tuple) and isinstance(args[2], int) \
                and 0 < args[2] <= 512:
            n = args[2]
            src = ([shift(word_name(a0), j) for j in range(n if f == "BMOV" else 1)] if dev else [])
            return [shift(word_name(args[1]), j) for j in range(n)], src, ok and (f == "FMOV" or dev)
        # คำสั่งที่ไม่รู้จัก: ทุก address ในคำสั่งอาจถูกเขียน
        names = []
        for a in words:
            names += cells(a) if a[0] == "K" else [bit_name(a), word_name(a)] if a[0] in ("T", "C", "ST") else [a[1]]
        return names, names, False

    @staticmethod
    def _wide_effects(f, args) -> tuple[list[str], list[str]] | None:
        """(ที่เขียน, ที่อ่าน) ของคำสั่ง 32 บิต (f = ชื่อไม่มี D); จำนวน operand ผิด = None."""
        if not args or not isinstance(args[-1], tuple):
            return None
        d = args[-1]
        if f in ("INC", "DEC"):
            return (cells(d, True), cells(d, True)) if len(args) == 1 else None
        if f in ARITH:
            if len(args) not in ((2, 3) if f in "+-" else (3,)):
                return None
        elif len(args) != 2:
            return None
        dst = cells(d, True)
        if f in "*/" and d[0] != "K":                                # ผล 64 บิต / ผลหาร + เศษ
            dst += [shift(dst[0], 2), shift(dst[0], 3)]
        src = args[:2] if f in ARITH else args[:1]
        return dst, [n for a in src if isinstance(a, tuple) for n in cells(a, True)]

    # ---------- tree ----------
    def _build(self):
        st: list[Node | None] = []
        mps: list[Node | None] = []
        rung, prev_out = 0, True

        def pop():
            return st.pop() if st else None

        for k, ins in enumerate(self.instrs):
            kd, op = self.kinds[k], ins.op
            if kd in ("contact", "compare", "unknown_contact"):
                head = CONTACT_OPS[op][0] if kd == "contact" else OTHER_CONTACT.match(op).group(1) if kd != "compare" \
                    else COMPARE.match(op).group(1)
                leaf = Node("leaf", k)
                if head == "LD":
                    if prev_out and not mps:
                        rung = k
                    st.append(leaf)
                    del st[:-64]
                elif head == "AND":
                    st.append(_and(pop(), leaf))
                else:
                    a = pop()
                    st.append(leaf if a is None else Node("or", kids=[a, leaf]))
                prev_out = False
            elif op in ("ANB", "ORB"):
                b, a = pop(), pop()
                if a is not None and b is not None:
                    st.append(Node("and" if op == "ANB" else "or", kids=[a, b]))
                else:
                    st.append(a or b)
            elif op == "MPS":
                mps.append(st[-1] if st else None)
            elif op in ("MRD", "MPP"):
                pop()
                st.append(mps[-1] if mps else None)
                if op == "MPP" and mps:
                    mps.pop()
                prev_out = False
            elif op == "INV":
                st.append(Node("not", k, [x for x in (pop(),) if x]))
            elif op in ("MEP", "MEF"):
                st.append(Node("edge", k, [x for x in (pop(),) if x]))
            elif kd == "out":
                if op == "MCR":
                    rung = k
                self.tree[k] = st[-1] if st and op != "MCR" else None
                prev_out = True
            elif kd in ("flow", "ignore"):
                if op not in JUMPS | CALLS or op == "JMP":
                    rung = k                         # ป้าย P / RET / FEND เป็น rung ของตัวเอง
                prev_out = True
            self.rung_of.append(rung)


def bit_name(a: tuple[str, str]) -> str:
    k, n = a[:2]
    return {"T": "TS", "C": "CS", "ST": "STS"}[k] + n[len(k):] if k in ("T", "C", "ST") else n


def word_name(a: tuple[str, str]) -> str:
    k, n = a[:2]
    return {"T": "TN", "C": "CN", "ST": "STN"}[k] + n[len(k):] if k in ("T", "C", "ST") else n


def pair(a: tuple[str, str]) -> list[str]:
    """word คู่ของค่า 32 บิต: [ตัวล่าง, ตัวบน]."""
    n = word_name(a)
    return [n, shift(n, 1)]


def cells(a, wide: bool = False) -> list[str]:
    """ทุกช่องหน่วยความจำของ operand (K4X0 = 16 บิต, 32 บิต = word คู่)."""
    return list(a[2]) if a[0] == "K" else pair(a) if wide else [word_name(a)]


def fits(a, wide: bool) -> bool:
    """operand ใช้กับขนาดข้อมูลนี้ได้ไหม (K5–K8 ต้องเป็นคำสั่ง 32 บิต)."""
    return len(a[2]) <= (32 if wide else 16) if a[0] == "K" else a[0] in WIDE_WORDS or not wide


def shift(name: str, n: int) -> str:
    m = re.match(r"^([A-Z]+)(\d+)$", name)
    return f"{m.group(1)}{int(m.group(2)) + n}" if m else name
