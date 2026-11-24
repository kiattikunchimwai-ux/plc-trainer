"""AI วิเคราะห์ความผิดพลาด — ดูพฤติกรรม I/O (black-box); ladder จาก CSV ใช้อธิบายเพิ่มเท่านั้น (plc_game/ladder) ไม่ใช้ให้คะแนน."""
from .analyzer import Finding, analyze, analyze_live

__all__ = ["Finding", "analyze", "analyze_live"]
