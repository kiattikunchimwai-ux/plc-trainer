"""ด่านหาจุดเสีย (Troubleshooting): สุ่มความผิดปกติ 1 จุดแบบซ่อน แล้วให้นักเรียนทายอุปกรณ์ + อาการ.

ไม่ใช้ Qt — รับแค่ {label: {code: คำอธิบาย}} ของอุปกรณ์บนผัง จึงทดสอบได้โดยไม่ต้องเปิดหน้าต่าง
ผลลัพธ์มี stars / score / results แบบเดียวกับ LevelRunner เพื่อให้ scores.record ใช้ได้เลย
"""
from __future__ import annotations

from ..i18n import tr

import random

from .engine import CheckResult, Level, stars_for

SYMPTOM_HINTS = {
    "stuck_on": tr("Input ค้าง 1 ตลอด — ดูตาราง I/O: X เป็น 1 ทั้งที่ไม่ได้กด"),
    "wire_break": tr("Input ไม่มาเลย — กดปุ่มแล้ว X ในตาราง I/O ไม่ขึ้นเป็น 1"),
    "jammed": tr("Output ทำงาน (Y = 1) แต่มอเตอร์ไม่หมุน — ปัญหาอยู่ที่ตัวมอเตอร์ ไม่ใช่โปรแกรม"),
    "burnt": tr("Output ทำงาน (Y = 1) แต่ไฟไม่ติด — หลอดขาด"),
}


class FaultHunt:
    def __init__(self, level: Level, items: dict[str, dict[str, str]], rng=None):
        if not level.is_fault_hunt:
            raise ValueError(tr("{0} ไม่ใช่ด่านหาจุดเสีย", level.title))
        self.level = level
        self.items = items
        self.guesses_allowed = level.faults.guesses
        cands = [(lab, c) for lab, codes in level.faults.pool if lab in items
                 for c in codes if c in items[lab]]
        if not cands:
            raise ValueError(tr("ผังนี้ไม่มีอุปกรณ์ตาม faults.pool ของด่าน — ตรวจชื่อป้าย (label) ในผัง"))
        self.answer: tuple[str, str] = (rng or random).choice(cands)
        self.results: list[CheckResult] = []
        self.found = False
        self.done = False

    # ---------- ผล (ใช้กับ scores.record / ตารางคะแนน) ----------
    @property
    def wrong(self) -> int:
        return sum(not r.passed for r in self.results)

    @property
    def left(self) -> int:
        return max(0, self.guesses_allowed - len(self.results))

    @property
    def stars(self) -> int:
        return max(1, 3 - self.wrong) if self.found else 0

    @property
    def score(self) -> float:
        return self.stars / 3

    @property
    def total(self) -> int:
        return 1

    @property
    def passed(self) -> int:
        return int(self.found)

    def answer_text(self) -> str:
        lab, code = self.answer
        return f"{lab}: {self.items[lab].get(code, code)}"

    def hint(self) -> str:
        return SYMPTOM_HINTS.get(self.answer[1], "")

    # ---------- ทาย ----------
    def guess(self, label: str, code: str) -> CheckResult:
        if self.done:
            raise ValueError(tr("จบการหาจุดเสียแล้ว — กด ▶ เริ่มหาจุดเสีย เพื่อเล่นรอบใหม่"))
        code = (code or "").lower()
        n = len(self.results) + 1
        what = tr("ทายครั้งที่ {0}: {1} — {2}", n, label, self.items.get(label, {}).get(code, code))
        ok_dev, ok_code = label == self.answer[0], code == self.answer[1]
        if ok_dev and ok_code:
            detail = tr("ถูกต้อง! เจอจุดเสียแล้ว")
        elif ok_dev:
            detail = tr("อุปกรณ์ถูก แต่อาการไม่ใช่ — ลองสังเกตอีกครั้ง")
        else:
            detail = tr("อุปกรณ์นี้ปกติ")
        r = CheckResult(tr("การทาย"), 0, n - 1, "guess", what, ok_dev and ok_code, detail,
                        "" if ok_dev and ok_code else SYMPTOM_HINTS.get(code, ""))
        self.results.append(r)
        if r.passed:
            self.found = self.done = True
        elif self.left == 0:
            self.done = True
        return r


__all__ = ["FaultHunt", "SYMPTOM_HINTS", "stars_for"]
