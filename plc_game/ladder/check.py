"""ตรวจ ladder ก่อน RUN ใน PLC ในตัว — คำสั่งที่ตัวรันไม่รู้จักต้องไม่ให้ RUN (ไม่เดา)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..i18n import tr
from ..plc.device import parse_device
from .editor import BLANK
from .model import (BITS, CALLS, COMPARE, CONTACT_OPS, DIGIT_OPS, JUMPS, KNOWN_FUNC, OTHER_CONTACT, RETS, WIDE_WORDS, Ladder,
                    base_func, bit_name, fits, is_label, is_wide, pair, word_name)

LIMIT = {"X": 1023, "Y": 1023, "M": 7679, "L": 7679, "B": 1023, "F": 1023, "V": 1023, "D": 7999, "W": 511,
         "T": 511, "ST": 511, "C": 255, "SM": 8511, "SD": 8511}
WORDS = {"D", "W", "SD", "T", "C", "ST"}
MAX_STEPS = 2000
MAX_DEPTH = 15
MAX_LABEL = 4095


@dataclass(frozen=True)
class Problem:
    k: int            # ลำดับคำสั่ง (-1 = ทั้งโปรแกรม)
    text: str


def number(name: str, base: int) -> tuple[str, int]:
    """ชื่อที่แปลงแล้ว (T5 / STS5 / D10 / X1F) → (ชนิด, เลข)."""
    if name[0] in "XY":
        d = parse_device(name, base)
        return d.kind, d.number
    m = re.match(r"^([A-Z]+)(\d+)$", name)
    return m.group(1), int(m.group(2))


def check(L: Ladder) -> list[Problem]:
    out: list[Problem] = []

    def bad(k, text):
        if len(out) < 50:
            out.append(Problem(k, text))

    if not any(kd == "out" for kd in L.kinds):
        return [Problem(-1, tr("ladder ว่าง — ยังไม่มีคอยล์หรือคำสั่ง"))]
    if len(L.instrs) > MAX_STEPS:
        return [Problem(-1, tr("ladder ยาวเกินไป ({0} คำสั่ง, สูงสุด {1})", len(L.instrs), MAX_STEPS))]

    depth, mps, prev_out, mcs = 0, [], True, []
    last = -1
    for k, ins in enumerate(L.instrs):
        kd, op, args = L.kinds[k], ins.op, L.args[k]
        if op == "END":
            break
        if op in ("NOP", "NOPLF", "PAGE"):
            continue
        last = k
        if op == "FEND" or op in RETS | {"JMP"} or is_label(op):
            if not prev_out or mps:
                bad(k, tr("{0} ต้องอยู่ต้น rung (วงจรก่อนหน้ายังไม่จบ)", ins.text))
            if mcs:
                bad(k, tr("ใช้ {0} ระหว่าง MC กับ MCR ไม่ได้", ins.text))
            if op == "JMP" and L.app_base == 8:          # ยืนยันกับ GX Works3: FX5U ไม่รับ JMP
                bad(k, tr("FX5 ไม่มีคำสั่ง JMP — ใช้ LD SM400 แล้วตามด้วย CJ {0} แทน", ins.args[0] if ins.args else "P0"))
            if len(ins.args) != (op == "JMP"):
                bad(k, tr("operand ของ {0} ไม่ถูกต้อง", ins.text))
            depth, prev_out = 0, True
            mps.clear()
            continue
        if op in JUMPS | CALLS:
            if len(ins.args) != 1:
                bad(k, tr("{0}: ต้องระบุป้าย P 1 ตัว เช่น {1} P0", ins.text, op))
            if depth != 1:
                bad(k, tr("{0} ไม่มีเงื่อนไข (ต้องมีหน้าสัมผัสอย่างน้อย 1 ตัว เช่น SM400)", ins.text) if depth < 1
                    else tr("วงจรก่อน {0} ยังต่อกันไม่ครบ (ANB/ORB)", ins.text))
            if mcs:
                bad(k, tr("ใช้ {0} ระหว่าง MC กับ MCR ไม่ได้", ins.text))
            prev_out = True
            continue
        if kd in ("flow", "ignore", "unknown_contact"):
            bad(k, tr("PLC ในตัวยังไม่รองรับคำสั่ง {0}", ins.text))
        else:
            _operands(L, k, bad)

        # ---- โครงสร้าง (stack) ----
        if kd in ("contact", "compare", "unknown_contact"):
            head = CONTACT_OPS[op][0] if kd == "contact" else (COMPARE if kd == "compare" else OTHER_CONTACT).match(op).group(1)
            if head == "LD":
                depth = 1 if prev_out and not mps else depth + 1
            elif depth < 1 or prev_out and not mps and _starts_rung(L, k):
                bad(k, tr("{0} ต้องต่อจาก LD", ins.text))
            prev_out = False
        elif op in ("ANB", "ORB"):
            if depth < 2:
                bad(k, tr("{0} ไม่มีวงจรให้ต่อ (ต้องมี 2 ก้อน)", op))
            else:
                depth -= 1
        elif op == "MPS":
            if depth < 1:
                bad(k, tr("{0} ต้องต่อจาก LD", op))
            mps.append(depth)
            if len(mps) > MAX_DEPTH:
                bad(k, tr("แยกวงจรซ้อนลึกเกินไป"))
        elif op in ("MRD", "MPP"):
            if not mps:
                bad(k, tr("{0} ไม่มี MPS คู่กัน", op))
            else:
                if depth != mps[-1]:
                    bad(k, tr("วงจรก่อน {0} ยังต่อกันไม่ครบ (ANB/ORB)", op))
                depth = mps[-1] if op == "MRD" else mps.pop()
            prev_out = False
        elif kd == "stack":
            if depth < 1:
                bad(k, tr("{0} ต้องต่อจาก LD", op))
        elif kd == "out" and op == "MCR":
            lv = ins.args[0] if ins.args else ""
            if lv not in mcs:
                bad(k, tr("MCR {0} ไม่มี MC คู่กัน", lv))
            else:
                del mcs[mcs.index(lv):]
            depth, prev_out = 0, True
        elif kd == "out":
            if depth < 1:
                bad(k, tr("{0} ไม่มีเงื่อนไข (ต้องมีหน้าสัมผัสอย่างน้อย 1 ตัว เช่น SM400)", ins.text))
            elif depth > 1:
                bad(k, tr("วงจรก่อน {0} ยังต่อกันไม่ครบ (ANB/ORB)", ins.text))
                depth = 1
            if op == "MC":
                mcs.append(ins.args[0] if ins.args else "")
            prev_out = True
    if last >= 0 and not prev_out:
        bad(last, tr("rung สุดท้ายไม่มีคอยล์หรือคำสั่ง"))
    if mps:
        bad(last, tr("MPS ไม่มี MPP ปิด"))
    for lv in mcs:
        bad(last, tr("MC {0} ไม่มี MCR ปิด", lv))
    _flow(L, bad)
    return out


def _flow(L: Ladder, bad) -> None:
    """ป้าย P, FEND และโปรแกรมย่อย: ช่วง 0 = โปรแกรมหลัก (ก่อน FEND), ช่วงถัดไป = โปรแกรมย่อยทีละตัว (จบด้วย RET)."""
    labels, jumps, region, fend, opened = {}, [], 0, False, -1
    for k, ins in enumerate(L.instrs):
        op = ins.op
        if op == "END":
            break
        if op in ("NOP", "NOPLF", "PAGE"):
            continue
        if op == "FEND":
            if fend:
                bad(k, tr("มี FEND ได้ตัวเดียว"))
            fend, region = True, region + 1
            continue
        if fend and opened < 0:
            opened = k
            if not is_label(op):
                bad(k, tr("หลัง FEND ต้องเริ่มด้วยป้าย P ของโปรแกรมย่อย ({0})", ins.text))
        if is_label(op):
            if op in labels:
                bad(k, tr("ป้าย {0} ซ้ำกัน", op))
            elif int(op[1:]) > MAX_LABEL or op != f"P{int(op[1:])}":
                bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, op))
            labels.setdefault(op, region)
        elif op in RETS:
            if not fend:
                bad(k, tr("{0} ต้องอยู่ในโปรแกรมย่อยหลัง FEND", op))
            else:
                region, opened = region + 1, -1
        elif op in JUMPS | CALLS and len(ins.args) == 1:
            jumps.append((k, region))
    if opened >= 0:
        bad(opened, tr("โปรแกรมย่อยไม่มี RET ปิด ({0})", L.instrs[opened].text))
    for k, at in jumps:
        op, (p,) = L.instrs[k].op, L.instrs[k].args
        if p not in labels:
            bad(k, tr("{0}: ไม่พบป้าย {1}", L.instrs[k].text, p))
        elif op in CALLS and labels[p] == 0:
            bad(k, tr("{0}: โปรแกรมย่อย {1} ต้องอยู่หลัง FEND", L.instrs[k].text, p))
        elif op in JUMPS and labels[p] != at:
            bad(k, tr("{0}: กระโดดข้ามระหว่างโปรแกรมหลักกับโปรแกรมย่อยไม่ได้", L.instrs[k].text))


def _starts_rung(L: Ladder, k: int) -> bool:
    """คำสั่งก่อนหน้าเป็น MCR (หลัง MCR ต้องเริ่ม LD ใหม่) — หลัง OUT ปกติ AND ต่อได้."""
    return k > 0 and L.instrs[k - 1].op == "MCR"


def _operands(L: Ladder, k: int, bad) -> None:
    ins, kd, op, args = L.instrs[k], L.kinds[k], L.instrs[k].op, L.args[k]
    if BLANK in ins.args:
        bad(k, tr("{0}: ยังไม่ได้กรอกช่อง ?", ins.text))
        return
    if kd == "stack":
        if args:
            bad(k, tr("{0} ต้องไม่มี operand", op))
        return
    if op in ("MC", "MCR"):
        if not ins.args or not re.match(r"^N([0-9]|1[0-4])$", ins.args[0]):
            bad(k, tr("{0} ต้องระบุ N0–N14", op))
            return
        if len(ins.args) != (2 if op == "MC" else 1):
            bad(k, tr("operand ของ {0} ไม่ถูกต้อง", ins.text))
            return
        if op == "MCR":
            return
        args = args[1:]
        if not (isinstance(args[0], tuple) and args[0][0] in ("M", "Y", "L", "B", "F")):
            bad(k, tr("operand ของ {0} ไม่ถูกต้อง", ins.text))
            return
    wide = is_wide(op)
    half = 1 << (31 if wide else 15)
    for a, raw in zip(args, ins.args[-len(args):] if args else ()):
        if a is None:
            bad(k, tr("{0}: ไม่รู้จัก device {1}", ins.text, raw))
            return
        if isinstance(a, int):
            if not -half <= a < half:
                bad(k, tr("{0}: ค่า {1} เกิน 32 บิต", ins.text, raw) if wide else tr("{0}: ค่า {1} เกิน 16 บิต", ins.text, raw))
                return
        elif a[0] == "K":
            if kd != "compare" and base_func(op)[0] not in DIGIT_OPS:
                bad(k, tr("{0}: ใช้ {1} กับคำสั่งนี้ไม่ได้", ins.text, raw))
                return
            if not fits(a, wide):
                bad(k, tr("{0}: {1} เกิน 16 บิต (ใช้ K1–K4 หรือคำสั่ง 32 บิต)", ins.text, raw))
                return
            kind, n = number(a[2][-1], L.app_base)
            if n > LIMIT.get(kind, -1):
                bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, a[2][-1]))
                return
        else:
            kind, n = number(a[1], L.app_base)
            if n > LIMIT.get(kind, -1):
                bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, raw))
                return
            if wide and kind not in WIDE_WORDS:
                bad(k, tr("{0}: คำสั่ง 32 บิตใช้ได้กับ D, W, SD และค่าคงที่ K/H ({1} ไม่ได้)", ins.text, raw))
                return
            if wide and n + 1 > LIMIT[kind]:                  # ใช้ word ถัดไปด้วย
                bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, pair(a)[1]))
                return
    a0 = args[0] if args else None
    if kd == "contact":
        if len(args) != 1 or not isinstance(a0, tuple) or a0[0] not in BITS | {"T", "C", "ST"}:
            bad(k, tr("{0}: หน้าสัมผัสต้องเป็น device แบบบิต 1 ตัว", ins.text))
        return
    if kd == "compare":
        if len(args) != 2 or any(isinstance(a, tuple) and a[0] not in WORDS | {"K"} for a in args):
            bad(k, tr("{0}: คำสั่งเปรียบเทียบต้องมีค่า 2 ตัว (D, T, C, K)", ins.text))
        return
    w, _, ok = L.effects(k)
    if op in ("PLS", "PLF", "FF", "SET", "RST", "INC", "DEC", "INCP", "DECP") and len(args) != 1:
        ok = False
    if op in ("OUT", "OUTH") and isinstance(a0, tuple):
        if a0[0] in ("T", "C", "ST"):
            p = args[1] if len(args) == 2 else None
            ok = ok and len(args) == 2 and not (op == "OUTH" and a0[0] == "C") \
                and (p >= 0 if isinstance(p, int) else p is not None and p[0] in ("D", "W"))
        else:
            ok = ok and a0[0] in BITS
    f, _ = base_func(op)
    if f in KNOWN_FUNC:
        ok = ok and all(not isinstance(a, tuple) or a[0] in WORDS | {"K"} for a in args)
    if not ok:
        bad(k, tr("{0}: PLC ในตัวยังไม่รองรับ หรือ operand ไม่ถูกต้อง", ins.text))
        return
    for n in w:
        kind, num = number(n, L.app_base)
        base = kind[:-1] if kind in ("TS", "TN", "CS", "CN", "STS", "STN") else kind
        if base in ("SM", "SD", "X"):
            bad(k, tr("{0}: ห้ามเขียนค่าให้ {1}", ins.text, n))
            return
        if num > LIMIT.get(base, -1):
            bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, n))
            return
    if f in ("BMOV",):
        for a in (args[0],):
            kind, num = number(word_name(a), L.app_base)
            base = kind[:-1] if kind in ("TN", "CN", "STN") else kind
            if num + args[2] - 1 > LIMIT.get(base, -1):
                bad(k, tr("{0}: {1} เกินช่วงที่ใช้ได้", ins.text, bit_name(a)))
                return
