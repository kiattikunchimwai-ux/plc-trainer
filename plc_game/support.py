"""สนับสนุนผู้พัฒนา (โดเนท): PromptPay QR payload + ค่าตั้ง support.json + กติกาการชวนแบบไม่รบกวน (ไม่ใช้ Qt)."""
from __future__ import annotations

from .i18n import tr

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

SUPPORT_FILE = Path(__file__).with_name("support.json")

AID_PROMPTPAY = "A000000677010111"
NUDGE_GAP_S = 7 * 24 * 3600        # ชวนไม่เกิน 1 ครั้ง / 7 วัน
MILESTONES = (5, 10, 14)           # ผ่านครบ 3★ กี่ด่านแล้วชวน (ไม่ติดกติกา 7 วัน)
AMOUNTS = (39, 99, 199)


# ---------- PromptPay (EMVCo) ----------
def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) ตามมาตรฐาน EMVCo QR."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def promptpay_target(pid: str) -> tuple[str, str]:
    """แปลงรหัสพร้อมเพย์เป็น (sub-tag, ค่า): เบอร์มือถือ 10 หลัก → 01, เลขบัตร/ภาษี 13 หลัก → 02, e-Wallet 15 หลัก → 03."""
    d = re.sub(r"\D", "", pid or "")
    if len(d) == 10 and d.startswith("0"):
        return "01", ("0066" + d[1:]).rjust(13, "0")
    if len(d) == 13:
        return "02", d
    if len(d) == 15:
        return "03", d
    raise ValueError(tr("รหัสพร้อมเพย์ต้องเป็นเบอร์มือถือ 10 หลัก, เลขประจำตัว 13 หลัก หรือ e-Wallet 15 หลัก"))


def promptpay_payload(pid: str, amount: float | None = None) -> str:
    """ข้อความที่ใส่ใน QR พร้อมเพย์ (แอปธนาคารไทยทุกแอปสแกนได้)."""
    sub, val = promptpay_target(pid)
    s = _tlv("00", "01") + _tlv("01", "12" if amount else "11")
    s += _tlv("29", _tlv("00", AID_PROMPTPAY) + _tlv(sub, val))
    s += _tlv("58", "TH") + _tlv("53", "764")
    if amount:
        if amount <= 0:
            raise ValueError(tr("จำนวนเงินต้องมากกว่า 0"))
        s += _tlv("54", f"{amount:.2f}")
    s += "6304"
    return s + f"{crc16_ccitt(s.encode('ascii')):04X}"


# ---------- ค่าตั้ง ----------
@dataclass
class SupportConfig:
    promptpay_id: str = ""
    promptpay_name: str = ""              # ชื่อบัญชีที่ผู้โดเนทจะเห็นในแอปธนาคาร (แสดงให้ตรวจก่อนโอน)
    links: list[dict] = field(default_factory=list)   # [{"label": "Ko-fi", "url": "https://..."}]
    goal_text: str = ""
    goal_target: int = 0
    goal_current: int = 0
    supporters: list[str] = field(default_factory=list)

    @property
    def has_promptpay(self) -> bool:
        try:
            promptpay_target(self.promptpay_id)
            return True
        except ValueError:
            return False


def load_support_cfg(path: Path | None = None) -> SupportConfig:
    path = path or SUPPORT_FILE
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SupportConfig()
    if not isinstance(d, dict):
        return SupportConfig()
    goal = d.get("goal") or {}
    links = [x for x in d.get("links", []) if isinstance(x, dict) and str(x.get("url", "")).startswith("https://")]
    return SupportConfig(
        promptpay_id=str(d.get("promptpay_id", "")),
        promptpay_name=str(d.get("promptpay_name", "")),
        links=links,
        goal_text=str(goal.get("text", "")),
        goal_target=int(goal.get("target", 0) or 0),
        goal_current=int(goal.get("current", 0) or 0),
        supporters=[str(s) for s in d.get("supporters", [])],
    )


# ---------- กติกาการชวน ----------
def nudge_reason(st: dict, *, prev_stars: int, new_stars: int, three_star_count: int,
                 blocked: bool, now: float | None = None) -> str | None:
    """คืนเหตุผลที่ควรชวน (ข้อความ key) หรือ None.

    ชวนเฉพาะตอนได้ 3★ ครั้งแรกของด่านนั้น; ถ้าจำนวนด่าน 3★ ถึง MILESTONES ชวนได้แม้ยังไม่ครบ 7 วัน
    (แต่ละ milestone ครั้งเดียว). ไม่ชวนเลยถ้า blocked (สอบ/บทเรียน/HMI/มีนักเรียนลงชื่อ) หรือผู้ใช้กด 'ไม่ต้องเตือนอีก'.
    """
    if blocked or st.get("support_never") or new_stars < 3 or prev_stars >= 3:
        return None
    now = time.time() if now is None else now
    seen = set(st.get("support_milestones", []))
    if three_star_count in MILESTONES and three_star_count not in seen:
        return f"milestone:{three_star_count}"
    if now - float(st.get("support_last_shown", 0)) >= NUDGE_GAP_S:
        return "first3"
    return None


def mark_shown(st: dict, reason: str, now: float | None = None) -> dict:
    """ค่าที่ต้องบันทึกลง ui_state หลังแสดงคำชวน."""
    upd = {"support_last_shown": time.time() if now is None else now}
    if reason.startswith("milestone:"):
        upd["support_milestones"] = sorted(set(st.get("support_milestones", [])) | {int(reason.split(":")[1])})
    return upd
