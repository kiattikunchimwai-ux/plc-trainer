"""อ่านไฟล์ CSV ของ GX Works3: UTF-16 คั่นด้วย Tab, operand ตัวที่ 2 เป็นต้นไปอยู่แถวต่อเนื่อง (ยืนยันกับ 1.110Q)."""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import tr

MAX_BYTES = 4_000_000
HEADER = "Step No."


class LadderError(ValueError):
    """อ่านไฟล์ ladder ไม่ได้ — ข้อความพร้อมแสดงผู้ใช้."""


@dataclass(frozen=True)
class Instr:
    step: int
    op: str
    args: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return " ".join((self.op, *self.args))


@dataclass
class Program:
    name: str = ""
    module: str = ""
    instrs: list[Instr] = field(default_factory=list)
    comments: dict[int, str] = field(default_factory=dict)     # ลำดับคำสั่ง → line statement ที่อยู่ก่อนหน้า
    dropped: int = 0                                           # P/I statement, note ที่ไม่ได้เก็บ

    @property
    def xy_base(self) -> int:
        """เลข X/Y ในไฟล์: FX = ฐาน 8, R/Q/L = ฐาน 16."""
        return 8 if "FX" in self.module.upper() else 16

    def with_instrs(self, instrs) -> "Program":
        return Program(self.name, self.module, list(instrs))


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise LadderError(tr("ไฟล์ใหญ่เกินไป ({0:.1f} MB)", len(data) / 1e6))
    try:
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return data.decode("utf-16")
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise LadderError(tr("อ่านตัวอักษรในไฟล์ไม่ได้ — ใช้ไฟล์ที่ Export จาก GX Works3 โดยตรง")) from None


def parse(text: str, allow_empty: bool = False) -> Program:
    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    start = next((i for i, r in enumerate(rows) if r and r[0].strip() == HEADER), None)
    if start is None:
        raise LadderError(tr("ไม่ใช่ไฟล์ ladder ของ GX Works3 (ไม่พบหัวตาราง Step No.) — ใช้ Edit → Export to File"))
    head = [c.strip() for c in rows[start]]
    try:
        c_op, c_dev = head.index("Instruction"), head.index("I/O (Device)")
    except ValueError:
        raise LadderError(tr("หัวตารางในไฟล์ไม่ครบ (ต้องมี Instruction และ I/O (Device))")) from None
    prog = Program(name=rows[0][0].strip() if start and rows[0] else "")
    for r in rows[:start]:
        if r and r[0].startswith("Module Type") and len(r) > 1:
            prog.module = r[1].strip()
    out: list[list] = []
    for n, r in enumerate(rows[start + 1:], start + 2):
        r = r + [""] * (len(head) - len(r))
        step, op, dev = r[0].strip(), r[c_op].strip().upper(), r[c_dev].strip().upper()
        if op:
            try:
                out.append([int(step), op, [dev] if dev else []])
            except ValueError:
                raise LadderError(tr("แถว {0}: เลข step ไม่ถูกต้อง {1!r}", n, step)) from None
        elif dev:
            if not out:
                raise LadderError(tr("แถว {0}: มี device แต่ไม่มีคำสั่ง", n))
            out[-1][2].append(dev)
        if not op and len(r) > 1 and r[1].strip():             # แถว line statement
            n_op = len(out)
            prog.comments[n_op] = " / ".join(x for x in (prog.comments.get(n_op), r[1].strip()) if x)
        prog.dropped += sum(bool(c.strip()) for c in r[5:7])
    prog.instrs = [Instr(s, o, tuple(a)) for s, o, a in out]
    if not allow_empty and not any(i.op not in ("END", "NOP") for i in prog.instrs):
        raise LadderError(tr("ไม่มีคำสั่งในไฟล์ (ladder ว่าง)"))
    return prog


def load_csv(path, allow_empty: bool = False) -> Program:
    try:
        p = Path(path)
        if p.stat().st_size > MAX_BYTES:
            raise LadderError(tr("ไฟล์ใหญ่เกินไป ({0:.1f} MB)", p.stat().st_size / 1e6))
        data = p.read_bytes()
    except OSError as e:
        raise LadderError(tr("เปิดไฟล์ไม่ได้: {0}", e.strerror or e)) from None
    try:
        return parse(decode(data), allow_empty)
    except csv.Error as e:
        raise LadderError(tr("รูปแบบ CSV ไม่ถูกต้อง: {0}", e)) from None


def to_csv(prog: Program) -> bytes:
    """CSV แบบเดียวกับที่ GX Works3 ส่งออก (เลข step เรียงลำดับ — GX คำนวณใหม่ตอนนำเข้า)."""
    rows = [[prog.name or "ladder"], ["Module Type Information:", prog.module],
            [HEADER, "Line Statement", "Instruction", "I/O (Device)", "Blank", "P/I Statement", "Note"]]
    for k, i in enumerate(prog.instrs):
        if k in prog.comments:
            rows.append([str(k), prog.comments[k], "", "", "", "", ""])
        rows.append([str(k), "", i.op, i.args[0] if i.args else "", "", "", ""])
        rows += [["", "", "", a, "", "", ""] for a in i.args[1:]]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerows([[" ".join(c.split()) for c in r] for r in rows])
    return b"\xff\xfe" + buf.getvalue().encode("utf-16-le")


def save_csv(path, prog: Program) -> None:
    """เขียนไฟล์ชั่วคราวแล้วแทนที่ — ไฟดับกลางคันไฟล์เดิมไม่เสีย."""
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(to_csv(prog))
        os.replace(tmp, p)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise LadderError(tr("บันทึกไฟล์ไม่ได้: {0}", e.strerror or e)) from None
