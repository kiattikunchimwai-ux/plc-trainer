"""แบบวงจรต่อสาย PLC จากผัง (ไม่ใช้ Qt): อุปกรณ์ Input → ขา X, ขา Y → โหลด, S/S ตามชนิดเซนเซอร์ NPN/PNP.

กติกาการต่อ (โมดูล DC input แบบ Mitsubishi ที่สลับ sink/source ได้ด้วย S/S):
- sink (NPN): S/S → +24V · สวิตช์/เซนเซอร์ต่อระหว่างขา X กับ 0V
- source (PNP): S/S → 0V · สวิตช์/เซนเซอร์ต่อระหว่าง +24V กับขา X
- เอาต์พุตรีเลย์: COM → แหล่งจ่ายของโหลด (+24V) · โหลดต่อระหว่างขา Y กับ 0V
- มอเตอร์/ปั๊ม: PLC สั่งคอยล์คอนแทคเตอร์ ไม่ได้จ่ายไฟมอเตอร์ตรง
"""
from __future__ import annotations

from ..i18n import tr

from dataclasses import dataclass, field

from ..plc.device import parse_device
from .catalog import CATALOG
from .iolist import rows as io_rows
from .model import DeviceSpec

SENSOR3 = {"sensor", "encoder", "light_curtain", "barcode", "level_tx"}
LAMP = {"lamp", "tower", "traffic"}
CONTACTOR = {"motor", "motor_rev", "motor_yd", "conveyor", "compressor", "tank", "vfd", "axis", "servo", "pick_place"}
COIL = {"valve", "cylinder", "pusher", "contactor", "timer_relay", "load_cell", "oven",
        "relay", "latch_relay", "ssr", "safety_relay", "vacuum", "dc_motor", "stepper"}
SYM_TH = {"no": tr("หน้าสัมผัส NO"), "nc": tr("หน้าสัมผัส NC"), "sensor": tr("เซนเซอร์ 3 สาย"), "lamp": tr("หลอดไฟ"),
          "buzzer": tr("ออด"), "coil": tr("คอยล์/โซลินอยด์"), "contactor": tr("คอยล์คอนแทคเตอร์ → มอเตอร์")}
_RANK = {"lamp": 0, "buzzer": 1, "coil": 2, "contactor": 3}


@dataclass
class Term:
    addr: str
    label: str
    device: str        # ชื่อชนิด (ไทย)
    role: str          # หน้าที่ของ address ในอุปกรณ์ ("" = หลัก)
    symbol: str        # no | nc | sensor | lamp | buzzer | coil | contactor
    output: str = ""   # npn | pnp (เซนเซอร์)
    device_id: str = ""
    parallel: list[str] = field(default_factory=list)   # โหลดอื่นที่ต่อขนานบนขาเดียวกัน

    @property
    def caption(self) -> str:
        return self.label + (f" · {self.role}" if self.role else "")


@dataclass
class Wiring:
    inputs: list[Term] = field(default_factory=list)
    outputs: list[Term] = field(default_factory=list)
    others: list[str] = field(default_factory=list)      # M / D / analog ที่ไม่ใช่สายจริง
    common: str = "sink"                                 # sink (S/S→+24V) | source (S/S→0V)
    warnings: list[str] = field(default_factory=list)

    @property
    def ss_to(self) -> str:
        return "+24V" if self.common == "sink" else "0V"

    @property
    def switch_from(self) -> str:
        """ขั้วที่สวิตช์ฝั่ง input ต่อไป (อีกขาเข้า X)."""
        return "0V" if self.common == "sink" else "+24V"


def _sym_in(spec: DeviceSpec, prop: str, contact: str) -> str:
    if spec.kind in SENSOR3 and prop == "address":
        return "sensor"
    return "nc" if contact == "NC" else "no"


def _sym_out(kind: str, prop: str) -> str:
    if kind == "buzzer" or prop == "addr_buzzer":
        return "buzzer"
    if kind in LAMP:
        return "lamp"
    if kind in CONTACTOR and prop in ("address", "addr_rev", "addr_drain", "addr_right", "addr_star", "addr_delta"):
        return "contactor" if not (kind == "tank" and prop == "addr_drain") else "coil"
    return "coil"


def build(devices: list[DeviceSpec], xy_base: int = 8) -> Wiring:
    w = Wiring()
    by_id = {d.id: d for d in devices}
    seen_in, seen_out = {}, {}
    kinds_out = set()
    for r in io_rows(devices, xy_base):
        spec = by_id[r.device_id]
        prefix = parse_device(r.address, xy_base).kind
        label = r.label or r.device
        if r.is_reference:
            continue
        if r.io == "in" and prefix == "X":
            t = Term(r.address, label, r.device, r.role, _sym_in(spec, r.prop, r.contact),
                     str(spec.props.get("output", "npn")) if spec.kind in SENSOR3 else "", r.device_id)
            if r.address in seen_in:
                w.warnings.append(tr("{0} ถูกใช้ทั้ง {1} และ {2} — ต่อสายขาเดียวกันไม่ได้", r.address, seen_in[r.address], label))
                continue
            seen_in[r.address] = label
            w.inputs.append(t)
        elif r.io == "out" and prefix == "Y":
            t = Term(r.address, label, r.device, r.role, _sym_out(spec.kind, r.prop), "", r.device_id)
            kinds_out.add(spec.kind)
            old = seen_out.get(r.address)
            if old is None:
                seen_out[r.address] = t
                w.outputs.append(t)
            else:                                   # หลายโหลดบนขาเดียวกัน = ต่อขนาน → วาดโหลดหลัก แล้วบอกตัวที่ขนาน
                main, extra = (t, old) if _RANK[t.symbol] > _RANK[old.symbol] else (old, t)
                main.parallel = old.parallel + t.parallel + [extra.caption]
                if main is t:
                    w.outputs[w.outputs.index(old)] = t
                    seen_out[r.address] = t
        else:
            w.others.append(f"{r.address} {label}" + (f" ({r.role})" if r.role else "")
                            + (tr(" — ผ่านโมดูล Analog/สื่อสาร") if prefix == "D" else tr(" — บิตภายใน ไม่ต่อสาย")))
    outs = {t.output for t in w.inputs if t.symbol == "sensor"}
    if outs == {"pnp"}:
        w.common = "source"
    elif len(outs) == 2:
        w.warnings.append(tr("มีเซนเซอร์ทั้ง NPN และ PNP ในโมดูลเดียว — ต้องแยกกลุ่ม common หรือเปลี่ยนให้เป็นชนิดเดียวกัน"))
    if kinds_out & {"motor_rev"}:
        w.warnings.append(tr("มอเตอร์กลับทาง: ต้องมี interlock ทางไฟฟ้า (NC ของ K1 อนุกรมคอยล์ K2 และกลับกัน) นอกจากใน ladder"))
    if kinds_out & {"motor_yd"}:
        w.warnings.append(tr("สตาร์-เดลต้า: ต้องมี interlock ทางไฟฟ้า (NC ของ KM2 อนุกรมคอยล์ KM3 และกลับกัน) นอกจากใน ladder"))
    return w


def to_text(w: Wiring) -> str:
    """สรุปการต่อสายเป็นข้อความ (ใช้ใน log / test)."""
    lines = [f"S/S → {w.ss_to} ({'NPN/sink' if w.common == 'sink' else 'PNP/source'})"]
    for t in w.inputs:
        if t.symbol == "sensor":
            lines.append(tr("{0} ← {1}: น้ำตาล +24V, น้ำเงิน 0V, ดำ → {2} ({3})", t.addr, t.caption, t.addr, t.output.upper()))
        else:
            lines.append(tr("{0} ← {1}: {2} ต่อจาก {3}", t.addr, t.caption, SYM_TH[t.symbol], w.switch_from))
    lines.append(tr("COM (เอาต์พุต) → +24V"))
    for t in w.outputs:
        lines.append(f"{t.addr} → {t.caption}: {SYM_TH[t.symbol]} → 0V"
                     + (tr(" (ขนานกับ {0})", ', '.join(t.parallel)) if t.parallel else ""))
    return "\n".join(lines + [f"⚠ {x}" for x in w.warnings])
