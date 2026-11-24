from ..i18n import tr
from .base import PLCClient, PLCError
from .device import Device, parse_device, device_range


def create_client(cfg: dict) -> PLCClient:
    """สร้าง PLC client ตาม config (backend: mock | soft | slmp)."""
    backend = cfg.get("backend", "mock")
    if backend == "mock":
        from .mock_client import MockPLC
        return MockPLC(xy_base=int(cfg.get("xy_base", 8)))
    if backend == "soft":
        from .soft_plc import SoftPLC
        return SoftPLC(xy_base=int(cfg.get("xy_base", 8)))
    if backend == "slmp":
        from .slmp_client import SLMPClient
        return SLMPClient(
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 5511)),
            plc_type=cfg.get("plc_type", "iQ-R"),
            xy_base=int(cfg.get("xy_base", 8)),
            timeout=float(cfg.get("timeout_s", 2.0)),
        )
    raise ValueError(tr("ไม่รู้จัก backend: {0}", backend))


__all__ = ["PLCClient", "PLCError", "Device", "parse_device", "device_range", "create_client"]
