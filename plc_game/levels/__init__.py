"""ระบบด่าน: โจทย์ + ตรวจคำตอบแบบ black-box จากผล I/O (ไม่ดูรูปแบบ ladder)."""
from .engine import (LEVEL_DIR, CheckResult, FaultSpec, Level, LevelRunner, Segment, expected_segments, fail_spans,
                     load_all, load_level, stars_for)
from .faultfind import SYMPTOM_HINTS, FaultHunt

__all__ = ["LEVEL_DIR", "CheckResult", "FaultHunt", "FaultSpec", "Level", "LevelRunner", "SYMPTOM_HINTS", "Segment",
           "expected_segments", "fail_spans", "load_all", "load_level", "stars_for"]
