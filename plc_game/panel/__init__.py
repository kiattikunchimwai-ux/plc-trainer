"""ผังอุปกรณ์ (Panel): นักเรียนเลือกอุปกรณ์มาวางและกำหนด address I/O เอง."""
from .catalog import CATALOG, CATEGORIES, KindInfo
from .model import DeviceSpec, PanelDoc, conflicts, validate_address
from .watch import WatchBlock, blocks_for

__all__ = ["CATALOG", "CATEGORIES", "KindInfo", "DeviceSpec", "PanelDoc", "conflicts",
           "validate_address", "WatchBlock", "blocks_for"]
