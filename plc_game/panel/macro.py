"""บันทึก/เล่นซ้ำการกด (ไม่ใช้ Qt) + แปลงเป็นด่าน.

บันทึก: input ที่ผู้ใช้กดเอง (ปุ่ม/สวิตช์/ค่าตั้ง) + output ที่ PLC ตอบ (จาก snapshot)
ไฟล์ .plcmacro = JSON {"version":1, "name", "panel", "idle":{addr:val}, "events":[{t, addr, value, word, io}]}
สร้างด่าน: input → set/word + wait · output ที่เปลี่ยนระหว่างช่วง → expect <ค่าสุดท้าย> within <เวลาที่ใช้ + เผื่อ>
(ครูสาธิตด้วย ladder ที่ถูก แล้วได้ด่านที่ตรวจจากผล I/O ไปแก้ต่อในตัวแก้ไขด่าน)
"""
from __future__ import annotations

from ..i18n import tr

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ชนิดที่ผู้ใช้สั่งเอง (ไม่ใช่สัญญาณที่ฟิสิกส์จำลองสร้าง เช่น รีดสวิตช์ เซนเซอร์ตำแหน่ง)
USER_KINDS = {"pushbutton", "selector", "selector3", "estop", "limit", "safety_door", "light_curtain",
              "float_switch", "pot", "setvalue"}
USER_PROPS = {"address", "addr_right", "addr_ch2"}
MARGIN_S = 0.5           # เผื่อเวลาใน expect
MIN_WAIT = 0.05
HOLD_MIN, HOLD_MAX = 0.6, 1.5   # ช่วงนิ่งยาวพอ → ตรวจว่าค่าคงอยู่ (สูงสุด 1.5 s ต่อช่วง)


@dataclass
class MacroEvent:
    t: float
    addr: str
    value: int
    word: bool = False
    io: str = "in"       # in = ผู้ใช้สั่ง · out = PLC ตอบ (ใช้สร้าง expect, ไม่เล่นซ้ำ)


@dataclass
class Macro:
    name: str = tr("การกดที่บันทึก")
    panel: str = ""
    idle: dict = field(default_factory=dict)
    events: list[MacroEvent] = field(default_factory=list)
    duration: float = 0.0

    @property
    def inputs(self) -> list[MacroEvent]:
        return [e for e in self.events if e.io == "in"]

    @property
    def outputs(self) -> list[MacroEvent]:
        return [e for e in self.events if e.io == "out"]

    # ----- ไฟล์ -----
    def to_json(self) -> str:
        return json.dumps({"version": 1, "name": self.name, "panel": self.panel, "idle": self.idle,
                           "duration": round(self.duration, 3),
                           "events": [asdict(e) for e in self.events]}, ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "Macro":
        d = json.loads(text)
        if not isinstance(d, dict) or "events" not in d:
            raise ValueError(tr("ไม่ใช่ไฟล์ .plcmacro"))
        ev = [MacroEvent(float(e["t"]), str(e["addr"]), int(e["value"]), bool(e.get("word", False)),
                         str(e.get("io", "in"))) for e in d["events"]]
        return cls(str(d.get("name", "")), str(d.get("panel", "")), {str(k): int(v) for k, v in d.get("idle", {}).items()},
                   sorted(ev, key=lambda e: e.t), float(d.get("duration", ev[-1].t if ev else 0)))

    def save(self, path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Macro":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    # ----- แปลงเป็นขั้นตอนด่าน -----
    def to_steps(self) -> list[tuple[str, str, str]]:
        """[(คำสั่ง, พารามิเตอร์, ข้อความ)] — ใช้กับ levels.editor.StepRow."""
        ins = self.inputs
        outs = self.outputs
        steps: list[tuple[str, str, str]] = []
        if not ins:
            return steps
        bounds = [e.t for e in ins] + [max(self.duration, ins[-1].t)]
        state = {}
        for e in outs:                                   # ค่าก่อนกดครั้งแรก
            if e.t < ins[0].t:
                state[e.addr] = e.value
        for i, e in enumerate(ins):
            steps.append(("word" if e.word else "set", f"{e.addr} {e.value}", ""))
            t0, t1 = e.t, bounds[i + 1]
            final, last_t = {}, {}
            for o in outs:
                if t0 <= o.t < t1 or (i == len(ins) - 1 and o.t >= t0):
                    final[o.addr] = o.value
                    last_t[o.addr] = o.t - t0
            used = 0.0
            for a in sorted(final):
                if state.get(a, 0) == final[a]:
                    continue                           # เปลี่ยนไปแล้วกลับ = ไม่ตรวจ (ลำดับละเอียดให้ครูเติมเอง)
                within = round(max(last_t[a] - used, 0) + MARGIN_S, 1)
                steps.append(("expect", f"{a} = {final[a]} within {within}", tr("{0} ต้องเป็น {1}", a, final[a])))
                used = max(used, last_t[a])
                state[a] = final[a]
            gap = round(t1 - t0 - used, 1)
            # ช่วงนิ่งหลังการกด: output ต้องคงค่า (เช่น ปล่อย Start แล้วมอเตอร์ยังเดิน = self-hold)
            if state and gap >= HOLD_MIN:
                dur = round(min(gap - 0.2, HOLD_MAX), 1)
                conds = " and ".join(f"{a} = {v}" for a, v in sorted(state.items()))
                steps.append(("hold", f"{conds} for {dur}", tr("ค่า output ต้องคงอยู่หลังการกด")))
                gap = round(gap - dur, 1)
            if i < len(ins) - 1 and gap >= MIN_WAIT:
                steps.append(("wait", f"{gap}", ""))
        return steps


def to_draft(m: Macro, existing: list, panel: str = ""):
    """สร้าง LevelDraft (ยังไม่บันทึก) จากการกดที่บันทึก."""
    from ..levels.editor import CaseRow, StepRow, new_draft
    d = new_draft(existing)
    d.title = tr("ด่าน {0}: {1}", d.order, m.name)
    d.panel = panel or m.panel
    d.desc = tr("สร้างจากการกดที่บันทึกไว้ — แก้โจทย์และข้อความตรวจก่อนใช้")
    d.idle = {a: v for a, v in m.idle.items()}
    d.reset = []
    d.cases = [CaseRow(m.name or tr("ข้อ 1"), [StepRow(op, p, msg) for op, p, msg in m.to_steps()])]
    return d


def is_user_input(kind: str, prop: str, manual: bool = False) -> bool:
    if prop not in USER_PROPS:
        return False
    return kind in USER_KINDS or (kind == "sensor" and manual)
