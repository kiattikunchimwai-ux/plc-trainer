"""D1: เทียบเวอร์ชัน + อ่าน version.json + หน้าต่าง About (ไม่เรียกเน็ตจริง)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from plc_game import __version__, update  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_versions():
    assert update.parse_version("v1.2.10-beta") == (1, 2, 10)
    assert update.is_newer("1.0.1", "1.0.0") and update.is_newer("1.10", "1.9.9")
    assert not update.is_newer("1.0", "1.0.0") and not update.is_newer("0.9.9", "1.0.0")


def test_parse_info_and_fetch_guards():
    i = update.parse_info({"version": "9.0.0", "url": "http://evil.example/x.exe", "notes": "n"})
    assert i.newer and i.url == ""                       # ลิงก์ที่ไม่ใช่ https ถูกตัดทิ้ง
    with pytest.raises(ValueError):
        update.parse_info({"url": "https://x"})
    with pytest.raises(ValueError):
        update.fetch("")
    with pytest.raises(ValueError):
        update.fetch("http://example.com/version.json")


def _wait(app, cond, sec=3.0):
    end = time.monotonic() + sec
    while not cond() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_about_dialog(app):
    from plc_game.ui.about_dlg import AboutDialog
    d = AboutDialog(None, "")
    assert not d.btn_check.isEnabled()                   # ไม่ได้ตั้ง update_url → ปิดปุ่ม
    d.deleteLater()

    d = AboutDialog(None, "https://example.com/version.json")
    d.check_update(lambda url: update.UpdateInfo("99.0.0", "https://example.com/dl", "ใหม่"))
    _wait(app, lambda: d.info is not None)
    assert d.info.version == "99.0.0" and not d.btn_download.isHidden() and "99.0.0" in d.lbl_update.text()

    d.check_update(lambda url: update.UpdateInfo(__version__))
    _wait(app, lambda: d.info.version == __version__)
    assert d.btn_download.isHidden()

    def boom(url):
        raise ValueError("offline")
    d.check_update(boom)
    _wait(app, lambda: "offline" in d.lbl_update.text())
    assert d.btn_check.isEnabled()
    d.deleteLater()
