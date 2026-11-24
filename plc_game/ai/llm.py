"""ชั้นเสริม: ให้ Claude อธิบายผลตรวจเป็นภาษาไทยแบบครูสอน (ใช้ได้เมื่อมีอินเทอร์เน็ต + API key).

ข้อมูลที่ส่ง: โจทย์ด่าน, ตาราง I/O ของผัง, ผลตรวจรายข้อ, ผลวิเคราะห์ในเครื่อง และลำดับเหตุการณ์ I/O
ไม่ส่งชื่อ/รหัสนักเรียน · ถ้าเลือก CSV ไว้ ส่งเฉพาะผลวิเคราะห์ ladder (step ที่เกี่ยวข้อง) ไม่ส่งไฟล์ ชื่อไฟล์ หรือ statement

ตั้งค่า: ติดตั้ง `pip install anthropic` แล้วตั้งตัวแปร ANTHROPIC_API_KEY (หรือ `ant auth login`)
"""
from __future__ import annotations

from ..i18n import tr

import os

MODEL = "claude-opus-5-5"

SYSTEM = tr("""คุณเป็นครูสอนวิชา PLC ระดับ ปวช. ที่ใจเย็นและอธิบายเก่ง
นักเรียนเขียนโปรแกรม ladder ใน GX Works3 (Mitsubishi FX5/iQ-R) แล้วระบบตรวจคำตอบแบบ black-box:
กด input ตามลำดับแล้วดูว่า output ถูกต้องไหม คุณไม่เห็น ladder ทั้งวงจร เห็นพฤติกรรม I/O และบางครั้งมีหัวข้อ "ผลวิเคราะห์ ladder" จากการจำลองในเครื่อง (อาจผิดได้ ให้ดูระดับความมั่นใจ)

หน้าที่ของคุณ:
1. อธิบายเป็นภาษาไทยง่ายๆ ว่าโปรแกรมของนักเรียน "ทำงานอย่างไร" จากหลักฐานที่วัดได้ (เวลา, ค่า)
2. บอกสาเหตุที่น่าจะเป็นที่สุดของข้อที่ไม่ผ่าน เรียงจากสิ่งที่ควรแก้ก่อน (ข้อหลังๆ มักพังตามข้อแรก)
3. ให้คำใบ้ทีละขั้นว่าควรตรวจ/แก้ส่วนไหนของ ladder ใช้ชื่อ address จริงจากโจทย์
4. ห้ามเขียนเฉลย ladder ทั้งวงจร — ให้แค่แนวคิดหรือตัวอย่างหน้าสัมผัส 1-2 ตัวที่เกี่ยวข้อง
5. ถ้าหลักฐานไม่พอ ให้บอกตรงๆ และแนะนำวิธีทดสอบเพิ่ม (เช่น ดูกราฟ Timing, กดปุ่มเอง)

รูปแบบ: หัวข้อสั้นๆ + bullet ไม่เกิน ~250 คำ ใช้คำว่า "หน้าสัมผัส NO/NC", "คอยล์", "self-holding", "interlock" ตามที่เรียนในห้อง""")


class LLMUnavailable(RuntimeError):
    """ใช้ Claude ไม่ได้ (ยังไม่ติดตั้ง/ไม่มี key) — ข้อความเป็นภาษาไทยสำหรับแสดงผู้ใช้."""


def available() -> tuple[bool, str]:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, tr("ยังไม่ได้ติดตั้งแพ็กเกจ anthropic (.venv\\Scripts\\pip install anthropic)")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("ANTHROPIC_PROFILE") or _has_profile()):
        return False, tr("ยังไม่ได้ตั้ง ANTHROPIC_API_KEY (หรือ ant auth login)")
    return True, ""


def _has_profile() -> bool:
    from pathlib import Path
    return (Path.home() / ".config" / "anthropic").exists()


def build_prompt(level, runner, findings, devices=None, max_events: int = 120) -> str:
    """รวมหลักฐานทั้งหมดเป็นข้อความเดียว (ทดสอบได้โดยไม่ต้องเรียก API)."""
    from ..panel.iolist import rows
    lines = [tr("# โจทย์: {0}", level.title), level.desc.strip(), ""]
    if devices:
        lines.append(tr("## ตาราง I/O บนผัง"))
        for r in rows(devices):
            lines.append(f"- {r.address} {r.direction}: {r.label or r.device}"
                         + (f" ({r.role})" if r.role else "") + (f" [{r.contact}]" if r.contact else ""))
        lines.append("")
    lines.append(tr("## ผลตรวจ: ผ่าน {0}/{1} ข้อ ({2} ดาว)", runner.passed, runner.total, runner.stars))
    for r in runner.results:
        mark = tr("ผ่าน") if r.passed else (tr("ข้าม") if r.skipped else tr("ไม่ผ่าน"))
        lines.append(f"- [{mark}] {r.case} › {r.msg}" + (f" — {r.detail}" if r.detail and not r.passed else ""))
    lines.append("")
    lines.append(tr("## ผลวิเคราะห์อัตโนมัติ (กฎในเครื่อง)"))
    lines += [f"- {f.text()}" for f in findings if f.kind != "ladder"]
    lines.append("")
    lad = [f for f in findings if f.kind == "ladder"]
    if lad:
        lines.append(tr("## ผลวิเคราะห์ ladder (จำลองจากไฟล์ CSV ของ GX Works3)"))
        lines += [f"- {f.text()}" for f in lad]
        lines.append("")
    lines.append(tr("## ลำดับเหตุการณ์ (วินาที: ตัวตรวจเขียน input / ค่าที่อ่านจาก PLC เปลี่ยน)"))
    lines += _timeline(runner, max_events)
    return "\n".join(lines)


def _timeline(runner, max_events):
    ev = [(t, e) for t, e in runner.events]
    prev: dict = {}
    for t, snap in runner.trace:
        diff = [f"{k}={v}" for k, v in snap.items() if prev.get(k) != v and (prev or v)]
        if diff:
            ev.append((t, "PLC: " + " ".join(diff)))
        prev = snap
    ev.sort(key=lambda x: x[0])
    if len(ev) > max_events:
        ev = ev[:max_events // 2] + [(ev[max_events // 2][0], tr("… (ตัดช่วงกลาง)"))] + ev[-max_events // 2:]
    return [f"{t:6.2f}  {e}" for t, e in ev]


def explain(prompt: str, timeout: float = 90.0) -> str:
    """เรียก Claude — ยก LLMUnavailable พร้อมข้อความไทยถ้าใช้ไม่ได้."""
    ok, why = available()
    if not ok:
        raise LLMUnavailable(why)
    import anthropic
    client = anthropic.Anthropic(timeout=timeout)
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",            # ถ้าถูกปฏิเสธ ให้ server ส่งต่อรุ่นสำรองอัตโนมัติ
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise LLMUnavailable(tr("API key ไม่ถูกต้อง")) from None
    except anthropic.RateLimitError:
        raise LLMUnavailable(tr("เรียกใช้ถี่เกินไป รอสักครู่แล้วลองใหม่")) from None
    except anthropic.APIConnectionError:
        raise LLMUnavailable(tr("เชื่อมต่ออินเทอร์เน็ตไม่ได้ — ใช้ผลวิเคราะห์ในเครื่องแทน")) from None
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(tr("Claude API ตอบกลับผิดพลาด ({0})", e.status_code)) from None
    if resp.stop_reason == "refusal":
        raise LLMUnavailable(tr("Claude ปฏิเสธคำขอนี้"))
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()
