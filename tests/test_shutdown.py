"""การปิดหน้าต่างอย่างปลอดภัย: คีย์ลัดผ่าน _KeyFilter, shutdown() ถอด filter/ปิดกราฟ, ลบหน้าต่างได้ไม่ abort."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
import shiboken6  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.panel import DeviceSpec, PanelDoc  # noqa: E402
from plc_game.ui import state  # noqa: E402
from plc_game.ui.chart_widget import ChartWidget  # noqa: E402
from plc_game.ui.shell import sidebar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setattr(classroom, "STUDENT_FILE", tmp_path / "students.json")
    monkeypatch.setattr(scores, "SCORE_FILE", tmp_path / "scores.json")
    monkeypatch.setattr(state, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(state, "_OLD_LAST", tmp_path / "last.txt")
    monkeypatch.setattr(sidebar, "ANIMATE", False)
    from plc_game.ui.main_window import MainWindow
    w = MainWindow({"backend": "mock"})
    yield w
    if shiboken6.isValid(w):
        w.shutdown()
        w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _key(kind, key=Qt.Key_1, text="1", mods=Qt.NoModifier, repeat=False):
    return QKeyEvent(kind, key, mods, 0, 0, 0, text, repeat)


def test_hotkey_goes_through_key_filter(win, monkeypatch):
    win.panel.load_doc(PanelDoc(devices=[DeviceSpec.new("pushbutton", 0, 0, address="X0", key="1")]))
    win.panel.set_run_mode(True)
    writes = []
    win.panel.request_write.connect(lambda a, v: writes.append((a, v)))
    monkeypatch.setattr(win, "isActiveWindow", lambda: True)
    f = win._keyfilter
    assert f.eventFilter(win.panel, _key(QEvent.KeyPress)) is True
    assert f.eventFilter(win.panel, _key(QEvent.KeyRelease)) is True
    assert writes == [("X0", 1), ("X0", 0)]
    assert f.eventFilter(win.panel, _key(QEvent.KeyPress, repeat=True)) is False          # กดค้าง: ไม่ส่งซ้ำ
    assert f.eventFilter(win.panel, _key(QEvent.KeyPress, mods=Qt.ControlModifier)) is False   # Ctrl+1 ไม่ใช่คีย์ลัด
    assert f.eventFilter(win.panel, QEvent(QEvent.Leave)) is False                     # event อื่นปล่อยผ่าน
    assert len(writes) == 2


def test_shutdown_detaches_filter_and_closes_chart(win, monkeypatch):
    win.panel.load_doc(PanelDoc(devices=[DeviceSpec.new("pushbutton", 0, 0, address="X0", key="1")]))
    win.panel.set_run_mode(True)
    monkeypatch.setattr(win, "isActiveWindow", lambda: True)
    win.shutdown()
    win.shutdown()                                   # เรียกซ้ำได้
    assert not win._keyfilter.active
    assert win._keyfilter.eventFilter(win.panel, _key(QEvent.KeyPress)) is False
    assert win.chart.view.closed and not win.chart._timer.isActive()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not shiboken6.isValid(win)


def test_chart_owns_pyqtgraph_popups(app):
    """pyqtgraph สร้างเมนู/QWidget ไม่มี parent — ChartWidget ต้องรับเป็นลูก ไม่ให้ค้างเป็นหน้าต่างบนสุด."""
    def parentless():
        return {shiboken6.getCppPointer(w)[0] for w in app.topLevelWidgets() if w.parent() is None}
    before = parentless()
    c = ChartWidget()
    added = parentless() - before
    assert added == {shiboken6.getCppPointer(c)[0]}
    c.shutdown()
    c.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert parentless() - before == set()
    assert all(type(w) is not QWidget or w.parent() is not None or shiboken6.getCppPointer(w)[0] in before
               for w in app.topLevelWidgets())
