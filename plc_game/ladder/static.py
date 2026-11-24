"""ข้อสังเกตจากตัว ladder เอง (ไม่ต้องจำลอง) — เป็นคำเตือน ไม่ใช่ตัวตัดสินว่าผิด."""
from __future__ import annotations

import re

from ..ai.analyzer import Finding
from ..i18n import tr
from .model import ARITH, Ladder, base_func


def where(L: Ladder, k: int) -> str:
    return tr("step {0}: {1}", L.instrs[k].step, L.instrs[k].text)


def _steps(L, ks) -> str:
    return ", ".join(where(L, k) for k in ks[:4])


def _f(title, lines, level, step=None) -> Finding:
    return Finding(title, lines, level, kind="ladder", step=step)


ACCUMULATE = {p + f for p in ("", "D") for f in {"INC", "DEC", "BCD", "BIN"} | ARITH}


def is_accumulating(L: Ladder, k: int) -> bool:
    """INC / DEC / D0+K1→D0 แบบไม่มี P (ผลย้อนเข้าค่าต้นทาง) — ทำซ้ำทุก scan ที่เงื่อนไขจริง."""
    f, pulse = base_func(L.instrs[k].op)
    if pulse or f not in ACCUMULATE:
        return False
    w, r, ok = L.effects(k)
    if not ok or not w:
        return False
    if not any(n in r for n in w):
        return False
    # ค่าต้นทางเพิ่งถูกคำนวณใหม่ใน rung เดียวกันก่อนหน้า (เช่น - D20 T1 D21 แล้ว + D21 K9 D21) = ไม่สะสมข้าม scan
    node, fresh = L.tree.get(k), set()
    for j in range(k - 1, -1, -1):
        if L.kinds[j] != "out" or L.tree.get(j) is not node:
            break
        f2, p2 = base_func(L.instrs[j].op)
        w2, r2, ok2 = L.effects(j)
        if ok2 and not p2 and f2 in ACCUMULATE | {"MOV", "DMOV"} and not any(n in r2 for n in w2):
            fresh |= set(w2)
    return not all(n in fresh for n in w if n in r)


def _one_shot(L: Ladder, node) -> bool:
    """เงื่อนไขมีขอบสัญญาณคุมอยู่ไหม (LDP ฯลฯ หรือ M ที่มาจาก PLS/PLF)."""
    if node is None:
        return False
    if node.kind == "edge":
        return True
    if node.kind == "leaf":
        op = L.instrs[node.i].op
        if L.kinds[node.i] == "contact":
            if op.endswith(("P", "F", "PI", "FI")):
                return True
            a = L.args[node.i][0] if L.args[node.i] else None
            if isinstance(a, tuple) and a[0] not in ("T", "C", "ST") and not op.endswith("I"):
                ws = L.written.get(a[1], [])
                return bool(ws) and all(L.instrs[w].op in ("PLS", "PLF")
                                        or L.instrs[w].op == "OUT" and _edge_only(L, L.tree.get(w)) for w in ws)
        return False
    if node.kind == "and":
        return any(_one_shot(L, x) for x in node.kids)
    if node.kind == "or":
        return all(_one_shot(L, x) for x in node.kids)
    return False


def _edge_only(L, node) -> bool:
    """หนึ่งชั้น: คอยล์ M ที่ขับด้วย LDP/LDF (ไม่ไล่ต่อ กันวนซ้ำ)."""
    if node is None:
        return False
    if node.kind == "leaf":
        return L.kinds[node.i] == "contact" and L.instrs[node.i].op.endswith(("P", "F", "PI", "FI"))
    if node.kind == "edge":
        return True
    if node.kind == "and":
        return any(_edge_only(L, x) for x in node.kids)
    return node.kind == "or" and all(_edge_only(L, x) for x in node.kids)


def static_findings(L: Ladder, level=None, known: set[str] | None = None) -> list[Finding]:
    out: list[Finding] = []
    I = L.instrs

    bad = [k for k, i in enumerate(I) if "SM4095" in i.args]
    if bad:
        out.append(_f(tr("มีคำสั่งที่ GX Works3 แทนด้วย OUT SM4095 (คำสั่งผิดหรือ PLC รุ่นนี้ไม่มี)"),
                      [_steps(L, bad)], "warn", I[bad[0]].step))

    if L.prog.module and L.prog.xy_base != L.app_base:
        big = [k for k, row in enumerate(L.args) for a, raw in zip(row, I[k].args)
               if isinstance(a, tuple) and a[0] in ("X", "Y", "K") and a[1] != raw]
        if big:
            out.append(_f(tr("เลข X/Y ใน CSV ({0}) เป็นฐาน {1} แต่โปรแกรมตั้งไว้ฐาน {2}", L.prog.module, L.prog.xy_base, L.app_base),
                          [tr("ตรวจ xy_base ในหน้าตั้งค่า — {0}", _steps(L, big))], "warn"))

    # ---- output ที่โจทย์ต้องการแต่ไม่มีใครเขียน ----
    if level is not None:
        need = list(dict.fromkeys(c.addr for cs in level.cases for s in cs.steps if s.is_check for c in s.conds))
        miss = [a for a in need if a.startswith("Y") and a not in L.written]
        if miss and not L.flow:
            out.append(_f(tr("ไม่มีคำสั่งเขียน {0} ใน ladder", ", ".join(miss)),
                          [tr("โจทย์ตรวจ output นี้ แต่ไม่พบคอยล์/SET ที่ใช้ address นี้ในไฟล์ CSV")], "warn"))

    for name, ks in L.written.items():
        outs = [k for k in ks if I[k].op in ("OUT", "OUTH") and not name.startswith(("TN", "CN", "STN"))]
        if len(outs) > 1:
            out.append(_f(tr("ใช้คอยล์ {0} ซ้ำ {1} ที่ (double coil)", name, len(outs)),
                          [_steps(L, outs), tr("คำสั่งที่อยู่ล่างสุดจะชนะ — ปกติควรรวมเงื่อนไขไว้ rung เดียว")], "warn", I[outs[0]].step))
        if name.startswith("X"):
            out.append(_f(tr("ladder เขียนค่าให้ input {0}", name), [_steps(L, ks)], "warn", I[ks[0]].step))
        sets = [k for k in ks if I[k].op == "SET"]
        if sets and len(sets) == len(ks):
            out.append(_f(tr("SET {0} แต่ไม่มีคำสั่ง RST", name), [_steps(L, sets)], "info", I[sets[0]].step))

    for name, ks in L.read.items():
        ks = [k for k in ks if not any(isinstance(a, tuple) and a[0] == "K" for a in L.args[k])]
        if not ks:                                   # อ่านผ่าน K4X0 ทั้งกลุ่ม: บิตที่ไม่ได้ต่อใช้เป็นเรื่องปกติ
            continue
        if name.startswith(("TS", "CS", "STS", "M", "L")) and not name.startswith("SM") and name not in L.written \
                and name not in (known or ()) and not L.flow:
            out.append(_f(tr("ใช้หน้าสัมผัส {0} แต่ไม่มีคำสั่งเขียน", _show(name)), [_steps(L, ks)], "warn", I[ks[0]].step))
        elif known and name.startswith("X") and name not in known:
            out.append(_f(tr("{0} ไม่มีอุปกรณ์บนผัง", name), [_steps(L, ks)], "info", I[ks[0]].step))

    for name, ks in L.written.items():
        if name.startswith(("TS", "CS", "STS")) and name not in L.read and _show_word(name) not in L.read \
                and not {name, _show_word(name)} & set(known or ()):
            on = [k for k in ks if I[k].op in ("OUT", "OUTH")]
            if on:
                out.append(_f(tr("{0} ไม่ถูกนำไปใช้ในเงื่อนไขใด", _show(name)), [_steps(L, on)], "info", I[on[0]].step))

    for k in range(len(I)):
        if L.kinds[k] == "out" and is_accumulating(L, k) and not _one_shot(L, L.tree.get(k)):
            out.append(_f(tr("{0} ทำงานซ้ำทุก scan ขณะเงื่อนไขเป็นจริง", I[k].text),
                          [where(L, k), tr("ถ้าต้องการให้ทำครั้งเดียวต่อการกด ใช้ขอบขาขึ้น (LDP / คำสั่งลงท้าย P)")], "warn", I[k].step))

    opened = [k for k, i in enumerate(I) if i.op == "MC"]
    closed = {i.args[0] for i in I if i.op == "MCR" and i.args}
    for k in opened:
        if I[k].args and I[k].args[0] not in closed:
            out.append(_f(tr("MC {0} ไม่มี MCR ปิด", I[k].args[0]), [where(L, k)], "warn", I[k].step))
    return out


def _show(name: str) -> str:
    return re.sub(r"^(ST|T|C)S(?=\d)", r"\1", name)


def _show_word(name: str) -> str:
    return re.sub(r"^(ST|T|C)S(?=\d)", r"\1N", name)
