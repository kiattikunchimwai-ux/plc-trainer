import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# test ส่วนใหญ่ตรวจข้อความไทย — ไม่ให้ภาษาที่ผู้ใช้เลือกไว้ใน ui_state มีผล
# (PLC_LANG=pseudo ตั้งเองได้ เพื่อหาโค้ดที่ตัดสินใจจากข้อความที่แปลแล้ว)
if os.environ.get("PLC_LANG") != "pseudo":
    os.environ["PLC_LANG"] = "th"


import tempfile  # noqa: E402

import pytest  # noqa: E402

from plc_game.ai import learn as _learn  # noqa: E402

_learn.MEMORY_FILE = Path(tempfile.gettempdir()) / "plc_test_ai_memory.json"      # timer ที่ยิงหลัง fixture คืนค่า


@pytest.fixture(autouse=True)
def _no_real_ai_memory(tmp_path_factory, monkeypatch):
    """ไม่แตะความจำ AI จริงของผู้ใช้ (panels/ai_memory.json)."""
    from plc_game.ai import learn
    monkeypatch.setattr(learn, "MEMORY_FILE", tmp_path_factory.mktemp("ai") / "ai_memory.json")


def pytest_sessionfinish(session, exitstatus):
    """ลบ widget ที่ test ทิ้งไว้ตอนจบ session ขณะ QApplication ยังอยู่ ตามลำดับที่ปลอดภัย.

    ไม่งั้นตอนปิด process จะเหลือ widget หลายร้อยตัว (PanelView ของ test_levels.run(), MainWindow ฯลฯ)
    ให้ GC ของ Python ลบแบบไม่มีลำดับ → เคย abort แบบสุ่ม (exit 0xC0000409 / 0xC0000374) แม้ test ผ่านหมด
    สาเหตุจริงแก้ในโค้ดแล้ว (MainWindow._KeyFilter, ChartWidget.shutdown, รับเมนู pyqtgraph เป็นลูก)
    ส่วนนี้แค่ทำให้การปิดเป็นลำดับเดียวกับโปรแกรมจริง: shutdown() → ลบ
    """
    if "PySide6.QtWidgets" not in sys.modules:
        return
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        if not shiboken6.isValid(w) or w.parent() is not None:   # ถูกลบไปพร้อมตัวอื่นแล้ว / มี parent ดูแล
            continue
        if callable(getattr(w, "shutdown", None)):                # MainWindow / ChartWidget
            w.shutdown()
        w.hide()
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
