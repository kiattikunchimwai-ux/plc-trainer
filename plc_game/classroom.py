"""ห้องเรียน: รายชื่อนักเรียน (panels/students.json) + ตารางคะแนนทั้งห้อง + Export Excel."""
from __future__ import annotations

from .i18n import tr

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .levels import scores
from . import paths
from .levels.engine import ROOT

STUDENT_FILE = paths.data_dir() / "students.json"


@dataclass(frozen=True)
class Student:
    sid: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.sid} {self.name}".strip()


def load_students(path: Path | None = None) -> list[Student]:
    try:
        raw = json.loads(Path(path or STUDENT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and str(r.get("id", "")).strip():
            out.append(Student(str(r["id"]).strip(), str(r.get("name", "")).strip()))
    return out


def save_students(students: list[Student], path: Path | None = None) -> None:
    p = Path(path or STUDENT_FILE)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps([{"id": s.sid, "name": s.name} for s in students], ensure_ascii=False, indent=2),
                 encoding="utf-8")


def clean_id(text: str) -> str:
    """รหัสนักเรียน: ตัวอักษร/ตัวเลข/ขีด เท่านั้น (ใช้เป็น key ใน scores.json)."""
    return re.sub(r"[^0-9A-Za-z_\-]", "", text.strip())


def upsert_student(sid: str, name: str, path: Path | None = None) -> Student:
    sid = clean_id(sid)
    if not sid:
        raise ValueError(tr("ต้องใส่รหัสนักเรียน (ตัวเลข/ตัวอักษรอังกฤษ)"))
    if sid == scores.GUEST:
        raise ValueError(tr("ใช้รหัส guest ไม่ได้"))
    lst = load_students(path)
    st = Student(sid, name.strip())
    for i, s in enumerate(lst):
        if s.sid == sid:
            lst[i] = Student(sid, st.name or s.name)
            save_students(lst, path)
            return lst[i]
    lst.append(st)
    save_students(lst, path)
    return st


def plc_label(kind: str) -> str:
    """ชื่อ PLC ที่ใช้ตรวจ (scores.record) สำหรับแสดงผล."""
    return {"mock": "Mock PLC", "soft": tr("PLC ในตัว"), "slmp": "GX Simulator3 / PLC (SLMP)",
            "none": tr("ไม่ได้เชื่อมต่อ PLC")}.get(kind) or tr("ไม่ทราบ")


def plc_text(st: dict) -> str:
    """PLC ที่ได้ดาวดีที่สุด ("" = ยังไม่มีดาว)."""
    return ", ".join(plc_label(p) for p in scores.best_plcs(st))


def class_table(levels, students: list[Student] | None = None, data: dict | None = None):
    """แถว = นักเรียน (ตามรายชื่อ + ใครที่มีคะแนนแต่ไม่อยู่ในรายชื่อ, guest ไว้ท้าย).

    คืน (headers, rows) — row = [รหัส, ชื่อ, ดาวด่าน1.., รวมดาว, ผ่าน 3 ดาว, ตรวจกี่ครั้ง]
    """
    students = load_students() if students is None else students
    data = scores.load() if data is None else data
    names = {s.sid: s.name for s in students}
    order = [s.sid for s in students]
    order += sorted(k for k in data if k not in names and k != scores.GUEST)
    if scores.GUEST in data:
        order.append(scores.GUEST)
    headers = [tr("รหัส"), tr("ชื่อ")] + [f"{lv.order}" for lv in levels] + [tr("รวมดาว"), tr("ผ่าน★★★"), tr("ตรวจ (ครั้ง)")]
    rows = []
    for sid in order:
        d = data.get(sid, {})
        stars = [int(d.get(lv.id, {}).get("best_stars", 0)) for lv in levels]
        tries = sum(int(d.get(lv.id, {}).get("attempts", 0)) for lv in levels)
        rows.append([sid, names.get(sid, tr("(ไม่ลงชื่อ)") if sid == scores.GUEST else ""), *stars,
                     sum(stars), sum(1 for s in stars if s == 3), tries])
    return headers, rows


def weak_points(levels, data: dict | None = None) -> list[dict]:
    """ข้อที่พลาดบ่อย จากการตรวจครั้งล่าสุดของแต่ละคน (ไม่นับ guest และข้อที่ถูกข้าม) เรียงจากพลาดมากสุด."""
    data = scores.load() if data is None else data
    out: dict[tuple, dict] = {}
    for n, lv in enumerate(levels):
        for sid, d in data.items():
            st = d.get(lv.id) if isinstance(d, dict) and sid != scores.GUEST else None
            for it in (st.get("last_detail") or []) if isinstance(st, dict) else []:
                if not isinstance(it, dict) or it.get("passed") is None or it.get("skipped"):
                    continue
                key = (n, str(it.get("case", "")), str(it.get("msg", "")))
                w = out.setdefault(key, {"level": lv.title, "order": n, "case": key[1], "msg": key[2], "tried": 0, "failed": []})
                w["tried"] += 1
                if not it["passed"]:
                    w["failed"].append(sid)
    rows = [w for w in out.values() if w["failed"]]
    return sorted(rows, key=lambda w: (-len(w["failed"]), -len(w["failed"]) / w["tried"], w["order"]))



def weak_table(levels, data: dict | None = None) -> tuple[list[str], list[list]]:
    head = [tr("ด่าน"), tr("ข้อ"), tr("รายการตรวจ"), tr("พลาด (คน)"), tr("ตรวจ (คน)"), tr("พลาด %"), tr("ใครพลาด")]
    return head, [[w["level"], w["case"], w["msg"], len(w["failed"]), w["tried"], round(100 * len(w["failed"]) / w["tried"]),
                   ", ".join(w["failed"])] for w in weak_points(levels, data)]


def export_xlsx(path: Path, levels, students: list[Student] | None = None, data: dict | None = None) -> Path:
    """Excel 3 แผ่น (+ "ข้อที่พลาดบ่อย"): 'สรุป' (ดาวรายด่าน) + 'รายข้อ' (ผลตรวจครั้งล่าสุดทุกข้อ)."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    data = scores.load() if data is None else data
    headers, rows = class_table(levels, students, data)
    wb = Workbook()
    ws = wb.active
    ws.title = tr("สรุป")
    head_fill = PatternFill("solid", fgColor="1F2937")
    head_font = Font(bold=True, color="FFFFFF")
    fills = {3: "B2F2BB", 2: "FFEC99", 1: "FFD8A8", 0: "FFC9C9"}
    ws.append([tr("ด่าน")] + [""] + [lv.title for lv in levels] + ["", "", ""])
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        for r in (1, 2):
            cell = ws.cell(r, c)
            cell.fill, cell.font = head_fill, head_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 48
    nlv = len(levels)
    for row in rows:
        ws.append(row)
        r = ws.max_row
        for i in range(nlv):
            cell = ws.cell(r, 3 + i)
            cell.fill = PatternFill("solid", fgColor=fills[int(row[2 + i])])
            cell.alignment = Alignment(horizontal="center")
            st = data.get(row[0], {}).get(levels[i].id, {})
            if scores.mock_only(st):              # ตัวเลขคงเดิม (รวม/เรียงได้) บอกที่มาด้วยตัวเอียง + หมายเหตุ
                cell.font = Font(italic=True, color="868E96")
            if scores.best_plcs(st):
                cell.comment = Comment(tr("ตรวจกับ: {0}", plc_text(st)), "PLC Trainer")
    ws.append([])
    ws.append([tr("ตัวเอียงสีเทา = ได้ดาวจาก Mock PLC เท่านั้น (Mock มี ladder บางด่านในตัว) · ชี้ช่องดาวเพื่อดู PLC ที่ใช้ตรวจ")])
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 26
    for i in range(nlv + 3):
        ws.column_dimensions[get_column_letter(3 + i)].width = 14
    ws.freeze_panes = "C3"

    det = wb.create_sheet(tr("รายข้อ"))
    det.append([tr("รหัส"), tr("ชื่อ"), tr("ด่าน"), tr("ตรวจล่าสุด"), tr("ดาวล่าสุด"), tr("ดาวดีที่สุด"), tr("ครั้ง"), tr("ข้อ"), tr("รายการตรวจ"),
                tr("ผล"), tr("รายละเอียด"), tr("PLC ล่าสุด"), tr("PLC ที่ได้ดาวดีที่สุด"),
                tr("ข้อสังเกตจาก ladder (ไม่มีผลต่อคะแนน)")])
    for c in range(1, 15):
        det.cell(1, c).fill, det.cell(1, c).font = head_fill, head_font
    names = {r[0]: r[1] for r in rows}
    titles = {lv.id: lv.title for lv in levels}
    for sid in names:
        for lid, st in data.get(sid, {}).items():
            base = [sid, names[sid], titles.get(lid, lid), st.get("last_time", ""), st.get("last_stars", 0),
                    st.get("best_stars", 0), st.get("attempts", 0)]
            items = st.get("last_detail") or [{}]
            for it in items:
                ok = it.get("passed")
                det.append(base + [it.get("case", ""), it.get("msg", ""),
                                   "" if ok is None else (tr("ผ่าน") if ok else tr("ไม่ผ่าน")), it.get("detail", ""),
                                   plc_label(st.get("last_plc", "")), plc_text(st),
                                   "\n".join(st.get("last_ladder") or []) if it is items[0] else ""])
                if ok is not None:
                    det.cell(det.max_row, 10).fill = PatternFill("solid", fgColor="B2F2BB" if ok else "FFC9C9")
    for col, wdt in zip("ABCDEFGHIJKLMN", (14, 22, 34, 20, 10, 10, 8, 26, 44, 10, 50, 26, 34, 70)):
        det.column_dimensions[col].width = wdt
    det.freeze_panes = "A2"

    weak = wb.create_sheet(tr("ข้อที่พลาดบ่อย"))
    head, body = weak_table(levels, data)
    weak.append(head)
    for c in range(1, len(head) + 1):
        weak.cell(1, c).fill, weak.cell(1, c).font = head_fill, head_font
    for row in body:
        weak.append(row)
        weak.cell(weak.max_row, 6).fill = PatternFill("solid", fgColor="FFC9C9" if row[5] >= 50 else "FFEC99")
    for col, wdt in zip("ABCDEFG", (36, 28, 56, 12, 12, 10, 50)):
        weak.column_dimensions[col].width = wdt
    weak.freeze_panes = "A2"
    path = Path(path)
    wb.save(path)
    return path
