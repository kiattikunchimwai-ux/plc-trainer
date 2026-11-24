"""คะแนนด่าน: panels/scores.json — {student_id: {level_id: {...}}} (นักเรียนที่ไม่ลงชื่อ = "guest")."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import paths

SCORE_FILE = paths.data_dir() / "scores.json"
GUEST = "guest"


def load(path: Path | None = None) -> dict:
    try:
        data = json.loads(Path(path or SCORE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict, path: Path | None = None):
    p = Path(path or SCORE_FILE)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record(level_id: str, runner, student: str = GUEST, path: Path | None = None, plc: str = "") -> dict:
    """บันทึกผลการตรวจ 1 ครั้ง (เก็บดาวที่ดีที่สุด จำนวนครั้ง และรายข้อของครั้งล่าสุด).

    plc = ตรวจกับ PLC ไหน: mock / soft / slmp / none (ไม่ได้เชื่อมต่อ) / "" (ไม่ทราบ) — บอกที่มาเท่านั้น ไม่มีผลต่อดาว
    """
    data = load(path)
    st = data.setdefault(student or GUEST, {}).setdefault(level_id, {"best_stars": 0, "best_score": 0.0,
                                                                    "attempts": 0})
    by = st.get("by_plc")
    if not isinstance(by, dict):              # คะแนนจากรุ่นเก่า: ดาวเดิมไม่ทราบที่มา
        by = st["by_plc"] = {"": st["best_stars"]} if st["attempts"] else {}
    by[plc] = max(int(by.get(plc, 0)), runner.stars)
    st["last_plc"] = plc
    st["attempts"] += 1
    st["best_stars"] = max(st["best_stars"], runner.stars)
    st["best_score"] = round(max(st["best_score"], runner.score), 3)
    st["last_stars"] = runner.stars
    st["last_score"] = round(runner.score, 3)
    st["last_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    st["last_detail"] = [{"case": r.case, "msg": r.msg, "passed": r.passed, "detail": r.detail,
                          "skipped": bool(getattr(r, "skipped", False))} for r in runner.results]
    st.pop("last_ladder", None)               # ข้อสังเกต ladder ของครั้งก่อน
    save(data, path)
    return st


def note_ladder(level_id: str, student: str, lines: list[str], stamp: str, path: Path | None = None) -> bool:
    """เก็บข้อสังเกตจาก ladder ไว้ให้ครูดู (ไม่มีผลต่อดาว) — เฉพาะเมื่อยังเป็นการตรวจครั้งเดิม."""
    data = load(path)
    st = data.get(student or GUEST, {}).get(level_id)
    if not isinstance(st, dict) or f"{st.get('last_time')}#{st.get('attempts')}" != stamp:
        return False
    st["last_ladder"] = [str(x)[:300] for x in lines[:3]]
    save(data, path)
    return True


def best_plcs(st: dict) -> list[str]:
    """PLC ที่ได้ดาวดีที่สุด (ได้เท่ากันหลายที่ = บอกทุกที่); ยังไม่มีดาว = ว่าง."""
    best = int(st.get("best_stars", 0))
    if best <= 0:
        return []
    by = st.get("by_plc")
    return [p for p, n in by.items() if n == best] if isinstance(by, dict) else [""]


def mock_only(st: dict) -> bool:
    """ดาวดีที่สุดมาจาก Mock PLC อย่างเดียว (Mock มี ladder เฉลยบางด่านในตัว)."""
    return best_plcs(st) == ["mock"]


def best_stars(student: str = GUEST, path: Path | None = None) -> dict[str, int]:
    return {k: v.get("best_stars", 0) for k, v in load(path).get(student or GUEST, {}).items()}
