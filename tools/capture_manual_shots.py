"""ถ่ายภาพหน้าจอสำหรับคู่มือการใช้งาน (ใช้ Mock PLC, ไม่บันทึกผัง/การตั้งค่าใดๆ)

  .venv\\Scripts\\python tools\\capture_manual_shots.py
ผลลัพธ์: docs/images/manual/*.png
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["PLC_LANG"] = "th"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images" / "manual"
OUT.mkdir(parents=True, exist_ok=True)

from PySide6.QtCore import QLocale, QPoint, QPointF, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
app = QApplication([])
from plc_game import classroom  # noqa: E402
from plc_game.levels import scores  # noqa: E402
from plc_game.ui import state, theme  # noqa: E402

# สถานะ/คะแนน/ผังอยู่ในโฟลเดอร์ชั่วคราว — เปิดโปรแกรมจริงค้างไว้ก็ไม่ชนกัน
tmp = tempfile.TemporaryDirectory()
TMP = Path(tmp.name)
shutil.copy(ROOT / "panels" / "default.plcpanel", TMP / "default.plcpanel")
state.PANEL_DIR, state.STATE_FILE, state._OLD_LAST = TMP, TMP / "ui_state.json", TMP / "last_panel.txt"
scores.SCORE_FILE, classroom.STUDENT_FILE = TMP / "scores.json", TMP / "students.json"
state.update(sound=False, tutorial_done=True, last_panel=str(TMP / "default.plcpanel"))
from plc_game.ui.main_window import MainWindow  # noqa: E402

app.setStyle("Fusion")
app.setStyleSheet(theme.QSS)
w = MainWindow({"backend": "mock", "xy_base": 8, "poll_ms": 50})
w.set_split(False)
w.set_large(False)
w.resize(1500, 900)
w.show()
p = w.panel


def rect_of(widget) -> QRect:
    tl = widget.mapTo(w, QPoint(0, 0))
    return QRect(tl, widget.size())


def annotate(pm, marks):
    """วาดกรอบ + เลขกำกับ (callout) บนภาพ."""
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    for n, r in marks:
        qp.setPen(QPen(QColor("#FFD43B"), 3))
        qp.setBrush(Qt.NoBrush)
        qp.drawRect(r.adjusted(2, 2, -2, -2))
        c = QPoint(r.right() - 26, r.top() + 22)
        if n == 4:                                  # ไม่บังไอคอนแถบขวา
            c.setX(r.left() + 26)
            c.setY(r.bottom() - 26)
        elif r.height() < 44:                       # แถบเตี้ย: ไว้ซ้าย กลางแถบ
            c = QPoint(r.left() + 26, r.center().y())
        qp.setPen(QPen(QColor("#10151B"), 2))
        qp.setBrush(QColor("#FFD43B"))
        qp.drawEllipse(c, 15, 15)
        qp.setFont(QFont("Segoe UI", 13, QFont.Bold))
        qp.setPen(QColor("#10151B"))
        qp.drawText(QRect(c.x() - 15, c.y() - 15, 30, 30), Qt.AlignCenter, str(n))
    qp.end()
    return pm


def save(name, pm=None):
    (pm or w.grab()).save(str(OUT / name))
    print("saved", name)


steps = []


def step(ms):
    def deco(fn):
        steps.append((ms, fn))
        return fn
    return deco


@step(600)
def s_connect():
    w.connect_plc()


@step(900)
def s_start():
    p.press("X0", 400)
    for k in range(3):
        QTimer.singleShot(700 + k * 650, p.conveyors()[0].spawn)


@step(3200)
def s_overview():
    pm = w.grab()
    marks = [
        (1, QRect(QPoint(0, 0), rect_of(w.ribbon).bottomRight())),
        (2, rect_of(w.side_l.bar).united(rect_of(w.side_l.pane))),
        (3, rect_of(w.stack)),
        (4, rect_of(w.side_r.bar).united(rect_of(w.side_r.pane))),
        (5, rect_of(w.cmd_bar)),
        (6, rect_of(w.statusBar())),
    ]
    save("01_overview.png", annotate(pm, marks))
    save("02_run.png")


@step(300)
def s_edit():
    w.set_edit_mode(True)
    w.d_props.show()
    it = p.items_at("X0")[0]
    it.setSelected(True)


@step(500)
def s_edit_shot():
    save("03_edit.png")


@step(200)
def s_bad_addr():
    w.props.ed_addr.setText("X1")
    w.props._addr_edited("X1")        # ชนกับปุ่ม Stop


@step(500)
def s_bad_shot():
    pm = w.grab(rect_of(w.side_r.pane))
    save("04_props_conflict.png", pm)
    p.do_undo()                         # คืน X0 (ไม่บันทึกผัง)


@step(400)
def s_menu():
    it = p.items_at("Y0")[0]
    p.sc.clearSelection()
    it.setSelected(True)
    pos = p.mapFromScene(it.scenePos())

    def grab_menu():
        m = QApplication.activePopupWidget()
        if m:
            save("05_context_menu.png", m.grab())
            m.close()
    QTimer.singleShot(400, grab_menu)
    from PySide6.QtGui import QContextMenuEvent
    ev = QContextMenuEvent(QContextMenuEvent.Mouse, pos, p.viewport().mapToGlobal(pos))
    p.contextMenuEvent(ev)


@step(400)
def s_menu_empty():
    pos = p.mapFromScene(QPointF(-200, 250))

    def grab_menu():
        m = QApplication.activePopupWidget()
        if m:
            sub = m.actions()[0].menu()
            m.setActiveAction(m.actions()[0])
            sub.popup(m.mapToGlobal(QPoint(m.width(), 0)))
            QTimer.singleShot(250, lambda: (save("06_context_add.png", m.grab()), save("06b_context_add_sub.png", sub.grab()),
                                            sub.close(), m.close()))
    QTimer.singleShot(400, grab_menu)
    from PySide6.QtGui import QContextMenuEvent
    ev = QContextMenuEvent(QContextMenuEvent.Mouse, pos, p.viewport().mapToGlobal(pos))
    p.contextMenuEvent(ev)


@step(800)
def s_split():
    p.sc.clearSelection()
    w.set_edit_mode(False)
    w.set_split(True)
    p.press("X1", 300)


@step(1500)
def s_split_shot():
    save("07_split.png")
    w.set_split(False)
    w.show_view(w.chart)


@step(800)
def s_chart():
    save("08_chart.png")
    w.show_view(p)
    w.set_large(True)


@step(800)
def s_large():
    save("09_large.png")
    w.set_large(False)


@step(300)
def s_tooltip():
    it = p.items_at("X0")[0]
    print("tooltip:", it.toolTip())


@step(200)
def s_done():
    w.disconnect_plc()
    w.dirty = False
    w.shutdown()
    app.quit()


def run(i=0):
    if i >= len(steps):
        return
    ms, fn = steps[i]
    QTimer.singleShot(ms, lambda: (fn(), run(i + 1)))


run()
app.exec()
tmp.cleanup()
