"""หน้าต่างจริงกับ PLC ในตัว: ตัวเลือกการเชื่อมต่อ (ส่วน ladder อยู่ใน test_ladder_editor_ui.py)."""
import time

from PySide6.QtWidgets import QApplication

from test_ladder_ui import win  # noqa: F401


def pump(cond, s=40):
    end = time.monotonic() + s
    while not cond() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    assert cond()


def connect(w):
    w.cb_backend.setCurrentIndex(w.cb_backend.findData("soft"))
    w.connect_plc()
    pump(lambda: w.online, 5)


def test_backend_choice(win):  # noqa: F811
    assert [win.cb_backend.itemData(i) for i in range(3)] == ["slmp", "mock", "soft"]
    assert win.cb_backend.currentData() == "mock"
