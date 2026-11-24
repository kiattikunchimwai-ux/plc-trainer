"""เชื่อมต่อ GX Simulator3 / PLC จริง ผ่าน SLMP (MC Protocol 3E frame, binary).

ใช้ไลบรารี pymcprotocol ซึ่งตีความเลข X/Y เป็นฐาน 16 เสมอ
แต่ FX5 ใช้ฐาน 8 จึงต้องแปลงเลขจริงเป็นสตริงฐาน 16 ก่อนส่ง
เช่น X10 (ฐาน 8) = 8 → ส่ง "X8" ให้ pymcprotocol
"""
from __future__ import annotations

from ..i18n import tr

from .base import PLCClient, PLCError
from .device import OCTAL_KINDS, parse_device


class SLMPClient(PLCClient):
    name = "SLMP"

    def __init__(self, host="127.0.0.1", port=5511, plc_type="iQ-R", xy_base=8, timeout=2.0):
        self.host, self.port = host, port
        self.plc_type = plc_type
        self.xy_base = xy_base
        self.timeout = timeout
        self._mc = None

    def connect(self) -> None:
        try:
            import pymcprotocol
        except ImportError as e:
            raise PLCError(tr("ยังไม่ได้ติดตั้ง pymcprotocol (pip install pymcprotocol)")) from e
        mc = pymcprotocol.Type3E(plctype=self.plc_type)
        mc.soc_timeout = self.timeout
        try:
            mc.connect(self.host, self.port)
        except OSError as e:
            raise PLCError(
                tr("เชื่อมต่อ {0}:{1} ไม่ได้ — เปิด GX Simulator3 แล้วกด Start Simulation หรือยัง?", self.host, self.port)
            ) from e
        self._mc = mc

    def close(self) -> None:
        if self._mc is not None:
            try:
                self._mc.close()
            except OSError:
                pass
        self._mc = None

    @property
    def is_connected(self) -> bool:
        return self._mc is not None and bool(getattr(self._mc, "_is_connected", True))

    def _wire(self, head: str) -> str:
        """แปลงชื่ออุปกรณ์ให้อยู่ในรูปที่ pymcprotocol ต้องการ."""
        d = parse_device(head, self.xy_base)
        if d.kind in OCTAL_KINDS:
            return f"{d.kind}{d.number:X}"
        return f"{d.kind}{d.number}"

    def _call(self, fn, *args, **kw):
        if self._mc is None:
            raise PLCError(tr("ยังไม่ได้เชื่อมต่อ PLC"))
        try:
            return fn(*args, **kw)
        except Exception as e:  # socket error หรือ MC error code จาก PLC
            self.close()
            raise PLCError(tr("สื่อสารกับ PLC ล้มเหลว: {0}", e)) from e

    def read_bits(self, head: str, count: int) -> list[int]:
        return self._call(lambda: self._mc.batchread_bitunits(headdevice=self._wire(head), readsize=count))

    def read_words(self, head: str, count: int) -> list[int]:
        return self._call(lambda: self._mc.batchread_wordunits(headdevice=self._wire(head), readsize=count))

    def write_bits(self, head: str, values: list[int]) -> None:
        vals = [1 if v else 0 for v in values]
        self._call(lambda: self._mc.batchwrite_bitunits(headdevice=self._wire(head), values=vals))

    def write_words(self, head: str, values: list[int]) -> None:
        self._call(lambda: self._mc.batchwrite_wordunits(headdevice=self._wire(head), values=list(values)))
