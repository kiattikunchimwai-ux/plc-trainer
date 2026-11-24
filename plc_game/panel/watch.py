"""รวม address ที่ต้องอ่านให้เป็นช่วงต่อเนื่อง (batch read) เพื่อลดจำนวน request ต่อรอบ."""
from __future__ import annotations

from dataclasses import dataclass

from ..plc.device import Device, parse_device


@dataclass(frozen=True)
class WatchBlock:
    head: str
    count: int
    is_bit: bool


def blocks_for(addresses, xy_base: int = 8, max_gap: int = 8) -> list[WatchBlock]:
    """addresses → list[WatchBlock]; ช่วงที่ห่างกันไม่เกิน max_gap จะรวมเป็นก้อนเดียว."""
    by_kind: dict[str, set[int]] = {}
    for a in addresses:
        try:
            d = parse_device(a, xy_base)
        except ValueError:
            continue
        by_kind.setdefault(d.kind, set()).add(d.number)

    blocks: list[WatchBlock] = []
    for kind in sorted(by_kind):
        nums = sorted(by_kind[kind])
        start = prev = nums[0]
        for n in nums[1:] + [None]:
            if n is not None and n - prev <= max_gap:
                prev = n
                continue
            dev = Device(kind, start, xy_base)
            blocks.append(WatchBlock(dev.name, prev - start + 1, dev.is_bit))
            if n is not None:
                start = prev = n
    return blocks
