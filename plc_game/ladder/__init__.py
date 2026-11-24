"""วิเคราะห์ ladder ของนักเรียนจาก CSV ที่ GX Works3 ส่งออก (Edit → Export to File) — ไม่ใช้ Qt.

ใช้ "อธิบายสาเหตุ" หลังตรวจ I/O แล้วเท่านั้น ห้ามนำไปให้คะแนน (คะแนนมาจากผล I/O)
"""
from .csvio import LadderError, Program, load_csv
from .replay import diagnose
from .sim import Sim
from .static import static_findings

__all__ = ["LadderError", "Program", "Sim", "diagnose", "load_csv", "static_findings"]
