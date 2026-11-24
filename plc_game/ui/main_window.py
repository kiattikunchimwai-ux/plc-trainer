"""หน้าต่างหลักสไตล์ AutoCAD:
  Ribbon (บน) | Tool Palette (ซ้าย) | Panel / Chart (กลาง) | Properties + Layers (ขวา)
  Command line (ล่าง) | Status bar
"""
from __future__ import annotations

from ..i18n import tr

import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDialog, QDockWidget, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTextEdit,
    QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from .. import classroom, i18n, support
from ..ai import llm
from ..levels import FaultHunt, scores
from ..ladder.check import check as check_ladder
from ..ladder.model import Ladder
from ..panel import PanelDoc, blocks_for, iolist
from ..plc import PLCError, create_client, parse_device
from ..plc.soft_plc import SoftPLC
from ..plc.poller import PLCPoller
from . import state, theme
from .chart_widget import ChartWidget
from .classroom_dlg import LoginDialog, ScoreDialog
from .exam import ExamSession, ExamSetupDialog, TeacherPasswordDialog, fmt_clock
from .tutorial import TStep, TutorialOverlay
from .sound import Sounds
from .support_dlg import SupportDialog, SupportToast
from .fault_dock import FaultPanel
from .iolist_dock import IOListPanel
from .ladder_view import LadderView
from .level_dock import LevelPanel, stars_text
from .macro_ctl import MacroController
from .quickstart import QuickStartDialog, remember_recent
from .shell import PaneHandle, SideDock
from .panel import items as panel_items
from .panel.library_dock import LibraryPanel
from .panel.properties_dock import PropertiesPanel
from .panel.view import PanelView

PANEL_DIR = state.PANEL_DIR
DEFAULT_PANEL = PANEL_DIR / "default.plcpanel"
EXTRA_SIGNALS = ["TS0", "CS0", "TN0", "CN0"]     # สัญญาณที่มีให้เลือกบนกราฟเสมอ

HELP = tr("""คำสั่งที่ใช้ได้:
  CONNECT / DISCONNECT        เชื่อม/ตัดการเชื่อมต่อ PLC
  SET X0  |  RST X0           สั่งอุปกรณ์บิต ON / OFF
  PULSE X2                    ON แล้ว OFF
  EDIT  |  RUN                โหมดแก้ไขผัง / โหมดใช้งาน
  U  |  REDO                  ย้อนกลับ / ทำซ้ำคำสั่ง (Ctrl+Z / Ctrl+Y)
  SPLIT  |  BIG               แบ่งจอผัง+กราฟ / โหมดตัวใหญ่
  ZOOM E                      ดูทั้งผัง (Zoom Extents)
  PAUSE  |  RESUME  |  CLEAR  ควบคุมกราฟ
  WINDOW 20                   ช่วงเวลาที่แสดงบนกราฟ (วินาที)
  IO  |  ASSIGN               ตาราง I/O ทั้งผัง / จัด address อัตโนมัติ
  ALIGN L|R|T|B|C|M           จัดแนวชิ้นที่เลือก (ซ้าย/ขวา/บน/ล่าง/กึ่งกลาง)
  DIST H  |  DIST V           กระจายระยะเท่ากัน แนวนอน / แนวตั้ง
  SCENES                      หน้าเริ่มต้น: ผังล่าสุด + ฉากโรงงานสำเร็จรูป
  LEVEL 1  |  CHECK  |  STOP  เปิดด่านที่ 1 / ตรวจคำตอบ / หยุดตรวจ
  ANALYZE  |  ANALYZE LIVE    AI วิเคราะห์ผลตรวจล่าสุด / สัญญาณที่กดเล่นอยู่
  LADDER  |  LADDER CLEAR     เลือกไฟล์ CSV ของ ladder ให้ AI อ่าน / เลิกใช้ไฟล์
  FAULT                       รายการความผิดปกติที่ใส่ได้ (โหมดครู)
  FAULT <ชื่อ|address> <รหัส>  ใส่ความผิดปกติ เช่น FAULT PS1 STUCK_ON
  FAULT RANDOM | FAULT CLEAR  สุ่ม 1 จุด / ล้างทั้งหมด
  GUESS <ชื่อ> <อาการ>         ด่านหาจุดเสีย: ทายว่าอุปกรณ์ไหนเสีย เช่น GUESS Start WIRE_BREAK
  LOGIN  |  SCORES  |  HMI    ลงชื่อนักเรียน / ตารางคะแนนทั้งห้อง / HMI เต็มจอ (F11)
  TUTORIAL  |  TUTORIAL LADDER    บทเรียนนำทาง / บทเรียนเขียน ladder (ทำตามทีละขั้น)
  LEVELEDIT                          ตัวแก้ไขด่านของครู (สร้าง/แก้/ลบด่าน ไม่ต้องเขียน YAML)
  WIRING  |  KNOW                    แบบวงจรต่อสาย PLC ของผังนี้ / ใบความรู้อุปกรณ์ (เลือกอุปกรณ์ก่อน)
  AB [ON|OFF]                        เคอร์เซอร์ A/B บนกราฟ วัด Δt
  REC  |  PLAY  |  MACROLEVEL        บันทึกการกด / เล่นซ้ำ / สร้างด่านจากการกดที่บันทึก
  EXAM  |  EXAM END  |  EXAM STATUS   เริ่มโหมดสอบ (ครู) / จบการสอบ (ใช้รหัสครู) / ดูเวลาและสิทธิ์ตรวจ
  SUPPORT                            ☕ สนับสนุนผู้พัฒนา (โปรแกรมใช้ฟรี)
  ABOUT                              เวอร์ชัน / โฟลเดอร์ข้อมูล / เช็กเวอร์ชันใหม่
  LANG TH | LANG EN                  เปลี่ยนภาษา / change language (เปิดโปรแกรมใหม่)
  HELP                     แสดงคำสั่งทั้งหมด""") + "\n" + tr("  DRAW                     เขียน ladder ในโปรแกรม (แท็บ Ladder)")


def ribbon_group(title: str, widgets_grid) -> QFrame:
    f = QFrame()
    f.setObjectName("RibbonGroup")
    v = QVBoxLayout(f)
    v.setContentsMargins(6, 6, 6, 0)
    v.setSpacing(4)
    g = QGridLayout()
    g.setHorizontalSpacing(6)
    for r, row in enumerate(widgets_grid):
        for c, w in enumerate(row):
            if w is not None:
                g.addWidget(w, r, c)
    v.addLayout(g)
    v.addStretch(1)
    t = QLabel(title)
    t.setObjectName("RibbonGroupTitle")
    t.setAlignment(Qt.AlignCenter)
    v.addWidget(t)
    return f


def tool_button(text: str, checkable=False) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    b.setCheckable(checkable)
    b.setToolButtonStyle(Qt.ToolButtonTextOnly)
    return b


class _KeyFilter(QObject):
    """event filter ระดับแอป (คีย์ลัดกดอุปกรณ์ + จัดปุ่มลอยเมื่อผังเปลี่ยนขนาด).

    แยกเป็นวัตถุลูกตัวแรกของหน้าต่าง: Qt ลบลูกตามลำดับที่สร้าง จึงถอด filter นี้ออกจากแอปก่อนลูกอื่นจะถูกลบ
    ถ้าให้ MainWindow เป็น filter เอง ตอนหน้าต่างกำลังถูกทำลาย Qt ยังส่ง event ของลูก ๆ เข้า eventFilter
    ของ Python บนวัตถุที่ตายครึ่งตัว → process abort (เจอตอนจบ pytest แบบสุ่ม)
    """

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self._win = win
        self.active = True

    def eventFilter(self, obj, e):
        if not self.active:
            return False
        t = e.type()
        if t in (QEvent.KeyPress, QEvent.KeyRelease):
            return self._win._on_key_event(e)
        if t in (QEvent.Resize, QEvent.Show) and obj is getattr(self._win, "panel", None):
            self._win._place_floating()
        return False


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        i18n.apply_qt_locale()                  # ก่อน super().__init__ — ลูกทุกตัวรับ locale จากหน้าต่าง (กันตัวเลขไทย ๕๕๑๑)
        super().__init__()
        self._keyfilter = _KeyFilter(self)      # ต้องสร้างก่อนลูกตัวอื่น (ดูคำอธิบายในคลาส)
        self.cfg = cfg
        self.xy_base = int(cfg.get("xy_base", 8))
        self.poller: PLCPoller | None = None
        self.soft: SoftPLC | None = None       # PLC ในตัวที่เชื่อมอยู่
        self.online = False
        self.panel_path: Path | None = None
        self.dirty = False
        self.resize(1500, 900)

        self.chart = ChartWidget(window_s=float(cfg.get("chart_window_s", 10)))
        self.panel = PanelView(xy_base=self.xy_base)
        self.ladderv = LadderView(self.xy_base)
        self.ladderv.message.connect(lambda m: self.log(m))
        self.ladderv.send_requested.connect(lambda: self.send_ladder())
        self.ladderv.learn_requested.connect(lambda: self.start_tutorial(ladder=True))
        self.ladderv.control.connect(lambda what: self.soft_control(what))
        self.ladderv.soft = lambda: self.soft
        self._checked_ladder = None            # Compiled ตอนเริ่มตรวจ (คลิกผลวินิจฉัย → rung)
        self.library = LibraryPanel()
        self.props = PropertiesPanel(self.panel)
        self.faults = FaultPanel(self.panel)
        self.faults.message.connect(lambda m: self.log(m))
        self.iolist = IOListPanel(self.panel)
        self.iolist.message.connect(lambda m: self.log(m))
        self.levelp = LevelPanel(self.panel)
        self.levelp.message.connect(lambda m: self.log(m))
        self.levelp.start_requested.connect(self.start_check)
        self.levelp.stop_requested.connect(self.stop_check)
        self.levelp.finished.connect(self._on_level_finished)
        self.levelp.aborted.connect(self._on_level_aborted)
        self.levelp.ladder_changed.connect(self._on_ladder_changed)
        self.levelp.jump_requested.connect(self.show_result_at)
        self.levelp.step_requested.connect(lambda step: self.goto_ladder_step(step))
        self.ladderv.locked = lambda: self.levelp.runner is not None
        self._history: deque = deque(maxlen=3000)      # สัญญาณล่าสุด สำหรับ AI วิเคราะห์ขณะกดเล่น
        self._unchecked: set[str] = set()
        self._sig_checks: dict[str, QCheckBox] = {}
        self.sounds = Sounds(enabled=bool(state.load().get("sound", True)))
        self.hmi = False
        self.exam: ExamSession | None = None
        self.tutorial: TutorialOverlay | None = None
        self._exam_over = False
        self._exam_timer = QTimer(self)
        self._exam_timer.setInterval(1000)
        self._exam_timer.timeout.connect(self._exam_tick)

        self.panel.request_write.connect(self._write)
        self.panel.request_write_word.connect(self._write_word)
        self.macro = MacroController(self.panel, self)          # M7 บันทึก/เล่นซ้ำการกด
        self.panel.request_write.connect(lambda a, v: self.macro.on_write(a, v, False))
        self.panel.request_write_word.connect(lambda a, v: self.macro.on_write(a, v, True))
        self.macro.message.connect(lambda s: self.log(s))
        self.macro.state_changed.connect(lambda s: self._on_macro_state(s))
        self.panel.selection_changed.connect(self.props.set_item)
        self.panel.changed.connect(self._on_panel_changed)
        self.panel.status.connect(lambda s: self.lbl_cursor.setText(s))
        self.library.add_requested.connect(self._add_from_library)

        self._build_ribbon()
        self._fill_levels()
        self._build_space()
        self._build_docks()
        self._build_cmdline()
        self._build_statusbar()

        self.chart.cursor_moved.connect(self._on_cursor)
        self.panel.edit_requested.connect(lambda: self.set_edit_mode(True))
        self.panel.fault_guessed.connect(self._on_fault_guessed)
        self.panel.knowledge_requested.connect(lambda it: self.show_knowledge(item=it))
        self.panel.undo.cleanChanged.connect(self._on_clean_changed)
        QShortcut(QKeySequence.Undo, self, activated=lambda: self.exam or self.panel.do_undo())
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=lambda: self.exam or self.panel.do_redo())
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=lambda: self.exam or self.panel.do_redo())
        QApplication.instance().installEventFilter(self._keyfilter)   # คีย์ลัดกดอุปกรณ์ + ปุ่มลอยบนผัง

        self._open_startup_panel()
        ui = state.load()
        self.btn_split.setChecked(bool(ui.get("split")))
        self.btn_large.setChecked(bool(ui.get("large")))
        self.set_ribbon_collapsed(bool(ui.get("ribbon_collapsed")), save=False)
        self._set_student(ui.get("student") or scores.GUEST, save=False)
        QShortcut(QKeySequence("F11"), self, activated=lambda: self.set_hmi(not self.hmi))
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.hmi and self.set_hmi(False))
        saved_exam = ExamSession.from_dict(ui.get("exam")) if ui.get("exam") else None
        if saved_exam:                               # ปิดโปรแกรมกลางการสอบ → กลับเข้าโหมดสอบเดิม
            self.start_exam(saved_exam, resumed=True)
        self.dirty = False
        self._update_title()
        self.log(tr("PLC Trainer พร้อมใช้งาน — พิมพ์ HELP เพื่อดูคำสั่ง"))

    # ================= layout =================
    RIBBON_H = 128

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 5, 10, 5)
        h.setSpacing(10)
        logo = QLabel("⚡ PLC Trainer")
        logo.setObjectName("Logo")
        h.addWidget(logo)

        # ----- โหมด ใช้งาน / แก้ไข (segmented) -----
        seg = QFrame()
        seg.setObjectName("Pill")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.btn_run = QToolButton()
        self.btn_run.setObjectName("Seg")
        self.btn_run.setText(tr("▶  ใช้งาน"))
        self.btn_run.setCheckable(True)
        self.btn_run.setChecked(True)
        self.btn_run.setToolTip(tr("โหมดใช้งาน: คลิกอุปกรณ์เพื่อกด/สับสวิตช์"))
        self.btn_run.clicked.connect(lambda: self.set_edit_mode(False))
        self.btn_edit = QToolButton()
        self.btn_edit.setObjectName("Seg")
        self.btn_edit.setText(tr("✎  แก้ไขผัง"))
        self.btn_edit.setCheckable(True)
        self.btn_edit.setToolTip(tr("โหมดแก้ไข: ลากวาง/ย้าย/ลบอุปกรณ์"))
        self.btn_edit.toggled.connect(self.set_edit_mode)
        sl.addWidget(self.btn_run)
        sl.addWidget(self.btn_edit)
        h.addWidget(seg)

        # ----- การเชื่อมต่อ PLC (pill) -----
        pill = QFrame()
        pill.setObjectName("Pill")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(8, 3, 3, 3)
        pl.setSpacing(6)
        self.cb_backend = QComboBox()
        self.cb_backend.addItem("GX Simulator3 (SLMP)", "slmp")
        self.cb_backend.addItem(tr("Mock PLC (ทดสอบ)"), "mock")
        self.cb_backend.addItem(tr("PLC ในตัว (รัน ladder)"), "soft")
        self.cb_backend.setCurrentIndex(max(0, self.cb_backend.findData(self.cfg.get("backend", "mock"))))
        self.ed_host = QLineEdit(str(self.cfg.get("host", "127.0.0.1")))
        self.ed_host.setFixedWidth(120)
        self.ed_host.setStyleSheet("font-family: Consolas;")
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(int(self.cfg.get("port", 5511)))
        net = QToolButton()
        net.setText("⚙")
        net.setToolTip(tr("ตั้งค่า Host / Port ของ GX Simulator3"))
        net.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(net)
        box = QWidget()
        f = QFormLayout(box)
        f.setContentsMargins(10, 8, 10, 8)
        f.addRow("Host", self.ed_host)
        f.addRow("Port", self.sp_port)
        act = QWidgetAction(menu)
        act.setDefaultWidget(box)
        menu.addAction(act)
        net.setMenu(menu)
        self.btn_connect = QPushButton(tr("⏻  เชื่อมต่อ"))
        self.btn_connect.setObjectName("Primary")
        self.btn_connect.setCheckable(True)
        self.btn_connect.toggled.connect(self._on_connect_toggled)
        self.lbl_online = QLabel("OFFLINE")
        self.lbl_online.setObjectName("Online")
        for w in (QLabel("PLC"), self.cb_backend, net, self.btn_connect, self.lbl_online):
            pl.addWidget(w)
        h.addWidget(pill)

        self.lbl_doc = QLabel()
        self.lbl_doc.setObjectName("DocName")
        h.addWidget(self.lbl_doc, 1)
        self.lbl_exam = QLabel()
        self.lbl_exam.setObjectName("ExamClock")
        self.lbl_exam.setToolTip(tr("โหมดสอบ — เวลาที่เหลือ (ออกจากโหมดสอบต้องใช้รหัสครู)"))
        self.lbl_exam.hide()
        h.addWidget(self.lbl_exam)
        self.btn_student = QPushButton(tr("👤  ลงชื่อนักเรียน"))
        self.btn_student.setToolTip(tr("ลงชื่อเพื่อบันทึกคะแนนด่านตามรหัสนักเรียน"))
        self.btn_student.clicked.connect(self.login_student)
        h.addWidget(self.btn_student)
        self.btn_support = QToolButton()
        self.btn_support.setText("☕")
        self.btn_support.setToolTip(tr("สนับสนุนผู้พัฒนา — โปรแกรมนี้ใช้ฟรี (พิมพ์ SUPPORT ก็ได้)"))
        self.btn_support.clicked.connect(self.show_support)
        h.addWidget(self.btn_support)
        self.btn_ribbon = QToolButton()
        self.btn_ribbon.setText("˄")
        self.btn_ribbon.setToolTip(tr("ยุบ / กาง แถบเครื่องมือ (Ctrl+F1 หรือดับเบิลคลิกแท็บ)"))
        self.btn_ribbon.clicked.connect(lambda: self.set_ribbon_collapsed(not self.ribbon_collapsed))
        h.addWidget(self.btn_ribbon)
        return bar

    def set_ribbon_collapsed(self, on: bool, save: bool = True):
        self.ribbon_collapsed = on
        self._apply_ribbon_height()
        self.btn_ribbon.setText("˅" if on else "˄")
        if save:
            state.update(ribbon_collapsed=on)

    def _apply_ribbon_height(self):
        scale = 1.25 if self.btn_large.isChecked() else 1.0
        tab_h = self.ribbon.tabBar().sizeHint().height() + 4
        self.ribbon.setFixedHeight(tab_h if self.ribbon_collapsed else round(self.RIBBON_H * scale))

    def _on_ribbon_tab_clicked(self, _i):
        if self.ribbon_collapsed:            # คลิกแท็บตอนยุบ = กางกลับ
            self.set_ribbon_collapsed(False)

    def _build_ribbon(self):
        self.ribbon_collapsed = False
        self.ribbon = QTabWidget()
        self.ribbon.setObjectName("Ribbon")
        self.ribbon.setFixedHeight(self.RIBBON_H)
        self.ribbon.tabBar().tabBarDoubleClicked.connect(
            lambda _i: self.set_ribbon_collapsed(not self.ribbon_collapsed))
        self.ribbon.tabBar().tabBarClicked.connect(self._on_ribbon_tab_clicked)
        top = self._build_topbar()
        home = QWidget()
        h = QHBoxLayout(home)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(0)

        b_new, b_open = tool_button(tr("📄  ใหม่")), tool_button(tr("📂  เปิด"))
        b_save, b_saveas = tool_button(tr("💾  บันทึก")), tool_button(tr("💾  บันทึกเป็น"))
        b_new.clicked.connect(self.new_panel)
        b_open.clicked.connect(self.open_panel)
        b_save.clicked.connect(self.save_panel)
        b_saveas.clicked.connect(lambda: self.save_panel(as_new=True))
        b_fit = tool_button(tr("⛶  ดูทั้งผัง"))
        b_fit.clicked.connect(self.panel.fit_all)
        self.b_undo, self.b_redo = tool_button(tr("↶  ย้อนกลับ")), tool_button(tr("↷  ทำซ้ำ"))
        self.b_undo.clicked.connect(lambda: self._exam_locked(tr("ย้อนกลับ")) or self.panel.do_undo())
        self.b_redo.clicked.connect(lambda: self._exam_locked(tr("ทำซ้ำ")) or self.panel.do_redo())
        self.b_undo.setToolTip("Ctrl+Z")
        self.b_redo.setToolTip("Ctrl+Y")
        self.panel.undo.canUndoChanged.connect(self.b_undo.setEnabled)
        self.panel.undo.canRedoChanged.connect(self.b_redo.setEnabled)
        self.b_undo.setEnabled(False)
        self.b_redo.setEnabled(False)
        b_scene = tool_button(tr("🏭  ฉาก\nตัวอย่าง"))
        b_scene.setMinimumHeight(52)
        b_scene.setToolTip(tr("เปิดหน้าเริ่มต้น: ผังล่าสุด + ฉากโรงงานสำเร็จรูป 13 ฉาก"))
        b_scene.clicked.connect(self.show_quickstart)
        h.addWidget(ribbon_group(tr("ผังอุปกรณ์"), [
            [b_scene, b_new, b_open, self.b_undo],
            [None, b_save, b_saveas, self.b_redo],
        ]))
        b_io = tool_button(tr("☰  ตาราง I/O"))
        b_io.setToolTip(tr("ตาราง address ทั้งผัง + ค่าสด + Export CSV / GX Works3 / PDF"))
        b_io.clicked.connect(self.show_iolist)
        h.addWidget(ribbon_group("I/O", [[b_io]]))

        self.btn_split = tool_button(tr("◫  แบ่งจอ"), checkable=True)
        self.btn_split.setToolTip(tr("แสดงผังอุปกรณ์และกราฟพร้อมกัน"))
        self.btn_large = tool_button(tr("🔍  ตัวใหญ่"), checkable=True)
        self.btn_large.setToolTip(tr("ขยายตัวอักษรทั้งโปรแกรม สำหรับฉายโปรเจกเตอร์"))
        self.btn_split.toggled.connect(self.set_split)
        self.btn_large.toggled.connect(self.set_large)
        b_hmi = tool_button(tr("🖥  HMI เต็มจอ"))
        b_hmi.setToolTip(tr("แสดงเฉพาะผังอุปกรณ์เต็มจอ เหมือนหน้าจอ HMI (F11 / Esc ออก)"))
        b_hmi.clicked.connect(lambda: self.set_hmi(True))
        h.addWidget(ribbon_group(tr("มุมมอง"), [[self.btn_split, b_fit], [self.btn_large, b_hmi]]))

        self.sp_poll = QSpinBox()
        self.sp_poll.setRange(20, 1000)
        self.sp_poll.setSuffix(" ms")
        self.sp_poll.setValue(int(self.cfg.get("poll_ms", 50)))
        h.addWidget(ribbon_group(tr("การอ่านข้อมูล"), [[QLabel(tr("รอบอ่าน"))], [self.sp_poll]]))

        self.btn_pause = tool_button(tr("⏸  หยุดกราฟ"), checkable=True)
        self.btn_pause.toggled.connect(self._set_paused)
        btn_clear = tool_button(tr("🗑  ล้างกราฟ"))
        btn_clear.clicked.connect(self.chart.clear)
        self.sp_window = QDoubleSpinBox()
        self.sp_window.setRange(2, 120)
        self.sp_window.setSuffix(" s")
        self.sp_window.setValue(self.chart.window_s)
        self.sp_window.valueChanged.connect(self.chart.set_window)
        h.addWidget(ribbon_group(tr("กราฟ"), [
            [self.btn_pause, btn_clear],
            [QLabel(tr("ช่วงเวลา")), self.sp_window],
        ]))
        b_tut = tool_button(tr("🎓  บทเรียน\nนำทาง"))
        b_tut.setMinimumHeight(52)
        b_tut.setToolTip(tr("พาทำทีละขั้น: เชื่อม PLC → เปิดด่าน 1 → กดปุ่ม → ดูกราฟ → ตรวจคำตอบ (พิมพ์ TUTORIAL ก็ได้)"))
        b_tut.clicked.connect(self.start_tutorial)
        b_sup = tool_button(tr("☕  สนับสนุน\nผู้พัฒนา"))
        b_sup.setMinimumHeight(52)
        b_sup.setToolTip(tr("โปรแกรมนี้ใช้ฟรี — ร่วมสนับสนุนด้วยพร้อมเพย์/ช่องทางอื่น (พิมพ์ SUPPORT ก็ได้)"))
        b_sup.clicked.connect(self.show_support)
        self.b_lang = tool_button("🌐  ภาษา\nLanguage")    # i18n: skip (สองภาษาเสมอ)
        self.b_lang.setMinimumHeight(52)
        self.b_lang.setToolTip("ไทย / English — เปลี่ยนแล้วเปิดโปรแกรมใหม่ (restart required)")   # i18n: skip
        lang_menu = QMenu(self.b_lang)
        for code, name in i18n.LANGS.items():
            act = lang_menu.addAction(("✔ " if code == i18n.lang() else "   ") + name)
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
        self.b_lang.setMenu(lang_menu)
        self.b_lang.setPopupMode(QToolButton.InstantPopup)
        b_about = tool_button("ℹ")              # ปุ่มแคบ — ribbon ภาษาอังกฤษเต็มแล้ว (ป้ายยาวจะโดนตัดเป็น …)
        b_about.setMinimumHeight(52)
        b_about.setFixedWidth(34)
        b_about.setToolTip(tr("เวอร์ชัน · โฟลเดอร์ข้อมูล · เช็กเวอร์ชันใหม่ (พิมพ์ ABOUT ก็ได้)"))
        b_about.clicked.connect(self.show_about)
        h.addWidget(ribbon_group(tr("ช่วยเหลือ"), [[b_tut, b_sup, self.b_lang, b_about]]))
        h.addStretch(1)
        self.ribbon.addTab(home, tr("หน้าแรก"))
        self.ribbon.addTab(self._build_edit_tab(), tr("แก้ไขผัง"))
        self.ribbon.addTab(self._build_level_tab(), tr("ด่าน / ภารกิจ"))
        self.ribbon.addTab(self._build_teacher_tab(), tr("ครู"))
        self.ribbon.addTab(self._build_ai_tab(), tr("AI วิเคราะห์"))
        self.ribbon.addTab(self._build_teach_tab(), tr("สื่อการสอน"))
        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(0)
        hv.addWidget(top)
        hv.addWidget(self.ribbon)
        self.setMenuWidget(head)
        QShortcut(QKeySequence("Ctrl+F1"), self, activated=lambda: self.set_ribbon_collapsed(not self.ribbon_collapsed))

    # ---------- แก้ไขผัง ----------
    def _build_edit_tab(self) -> QWidget:
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.btn_edit2 = tool_button(tr("✎  โหมด\nแก้ไขผัง"), checkable=True)
        self.btn_edit2.setMinimumHeight(52)
        self.btn_edit2.toggled.connect(self.set_edit_mode)
        b_all = tool_button(tr("⬚  เลือกทั้งหมด"))
        b_all.setToolTip(tr("Ctrl+A (คลิกที่ผังก่อน)"))
        b_all.clicked.connect(lambda: (self.set_edit_mode(True), self.panel.select_all()))
        b_dup = tool_button(tr("⧉  ทำซ้ำ"))
        b_dup.setToolTip("Ctrl+D")
        b_dup.clicked.connect(self.panel.duplicate_selected)
        b_del = tool_button(tr("✖  ลบ"))
        b_del.setToolTip("Delete")
        b_del.clicked.connect(self.panel.remove_selected)
        h.addWidget(ribbon_group(tr("เลือก"), [[self.btn_edit2, b_all, b_dup], [None, None, b_del]]))

        grid = []
        for row in (("left", tr("⇤  ชิดซ้าย")), ("hcenter", tr("⇹  กึ่งกลาง")), ("right", tr("⇥  ชิดขวา"))), \
                   (("top", tr("⤒  ชิดบน")), ("vcenter", tr("⇕  กึ่งกลาง")), ("bottom", tr("⤓  ชิดล่าง"))):
            line = []
            for mode, text in row:
                b = tool_button(text)
                b.setToolTip(tr("จัดแนว{0} (เลือก ≥ 2 ชิ้น)", tr(self.panel.ALIGN_NAMES[mode])))
                b.clicked.connect(lambda _=False, m=mode: self.panel.align(m))
                line.append(b)
            grid.append(line)
        h.addWidget(ribbon_group(tr("จัดแนว"), grid))
        b_dh = tool_button(tr("↔  กระจายแนวนอน"))
        b_dh.clicked.connect(lambda: self.panel.distribute("h"))
        b_dv = tool_button(tr("↕  กระจายแนวตั้ง"))
        b_dv.clicked.connect(lambda: self.panel.distribute("v"))
        for b in (b_dh, b_dv):
            b.setToolTip(tr("ระยะห่างเท่ากัน (เลือก ≥ 3 ชิ้น)"))
        tips = [QLabel(tr("ลูกศร = ขยับทีละช่อง")), QLabel(tr("Shift+ลูกศร = ทีละ 1 px"))]
        for t in tips:
            t.setStyleSheet(f"color:{theme.TEXT_DIM};")
        h.addWidget(ribbon_group(tr("กระจายระยะ / ขยับ"), [[b_dh, tips[0]], [b_dv, tips[1]]]))

        b_note = tool_button(tr("🗒  ข้อความ"))
        b_note.setToolTip(tr("ป้ายข้อความอธิบายโจทย์ / I/O"))
        b_note.clicked.connect(lambda: self._add_annotation("note"))
        b_zone = tool_button(tr("▭  กรอบโซน"))
        b_zone.setToolTip(tr("กรอบแบ่งสถานีงาน"))
        b_zone.clicked.connect(lambda: self._add_annotation("zone"))
        h.addWidget(ribbon_group(tr("คำอธิบาย"), [[b_note], [b_zone]]))

        b_io = tool_button(tr("☰  ตาราง I/O"))
        b_io.clicked.connect(self.show_iolist)
        b_assign = tool_button(tr("🔢  จัด Address"))
        b_assign.setToolTip(tr("เรียงเลข X / Y ใหม่ตามตำแหน่งบนผัง (บน→ล่าง, ซ้าย→ขวา)"))
        b_assign.clicked.connect(self.iolist.auto_assign)
        h.addWidget(ribbon_group("I/O", [[b_io], [b_assign]]))
        h.addStretch(1)
        return tab

    def _add_annotation(self, kind: str):
        self.set_edit_mode(True)
        self._add_from_library(kind)
        self.library.remember(kind)

    # ---------- ด่าน ----------
    def _build_level_tab(self) -> QWidget:
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.cb_level = QComboBox()
        self.cb_level.setMinimumWidth(360)
        b_open = tool_button(tr("📖  เปิดด่าน"))
        b_open.setToolTip(tr("โหลดผังของด่านและแสดงโจทย์"))
        b_open.clicked.connect(lambda: self.open_level(self.cb_level.currentIndex()))
        self.b_level_open = b_open
        b_reload = tool_button(tr("🔄  โหลดรายการใหม่"))
        b_reload.setToolTip(tr("อ่านไฟล์ levels/*.yaml ใหม่ (ครูแก้/เพิ่มด่านเองได้)"))
        b_reload.clicked.connect(self._fill_levels)
        h.addWidget(ribbon_group(tr("เลือกด่าน"), [[self.cb_level, b_open], [None, b_reload]]))
        self.b_check = tool_button(tr("▶  ตรวจคำตอบ"))
        self.b_check.setMinimumHeight(52)
        self.b_check.setToolTip(tr("ตัวตรวจจะกดปุ่มตามลำดับแล้วดูผล Output (ไม่ดูรูปแบบ ladder)"))
        self.b_check.clicked.connect(self.start_check)
        b_stop = tool_button(tr("⏹  หยุดตรวจ"))
        b_stop.clicked.connect(self.stop_check)
        b_res = tool_button(tr("☰  ผลตรวจ"))
        b_res.clicked.connect(self.show_levels)
        h.addWidget(ribbon_group(tr("ตรวจคำตอบ"), [[self.b_check, b_stop], [None, b_res]]))
        tip = QLabel(tr("ขั้นตอน: เปิดด่าน → เขียน ladder ใน GX Works3 ตาม I/O ของโจทย์ → Write ลง PLC\n"
                     "→ เชื่อมต่อ → ▶ ตรวจคำตอบ · ตรวจจากผล I/O เท่านั้น เขียนแบบไหนก็ได้ที่ทำงานถูก\n"
                     "ผ่านทุกข้อ = ★★★ · ≥ 70% = ★★ · ≥ 40% = ★"))
        tip.setStyleSheet(f"color:{theme.TEXT_DIM}; padding:6px 12px;")
        h.addWidget(tip)
        h.addStretch(1)
        return tab

    # ---------- สื่อการสอน (M7) ----------
    def _build_teach_tab(self) -> QWidget:
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.b_ab = tool_button(tr("📏  เคอร์เซอร์\nA / B"), checkable=True)
        self.b_ab.setMinimumHeight(52)
        self.b_ab.setToolTip(tr("เส้น A/B ลากได้บนกราฟ วัดช่วงเวลา Δt (ปล่อยใกล้ขอบสัญญาณ = ดูดเข้าขอบ) · กราฟหยุดให้อัตโนมัติ"))
        self.b_ab.toggled.connect(self.set_ab_cursors)
        b_png, b_csv = tool_button(tr("🖼  กราฟเป็น PNG")), tool_button(tr("📄  ข้อมูลเป็น CSV"))
        b_png.clicked.connect(lambda: self.export_chart("png"))
        b_csv.clicked.connect(lambda: self.export_chart("csv"))
        h.addWidget(ribbon_group(tr("กราฟ"), [[self.b_ab, b_png], [None, b_csv]]))
        b_wire = tool_button(tr("🔌  วงจร\nต่อสาย"))
        b_wire.setMinimumHeight(52)
        b_wire.setToolTip(tr("แบบวงจรต่อสาย PLC จากผังปัจจุบัน (X/Y, S/S ตามเซนเซอร์ NPN/PNP) + Export PNG/PDF"))
        b_wire.clicked.connect(self.show_wiring)
        b_know = tool_button(tr("📘  ใบความรู้\nอุปกรณ์"))
        b_know.setMinimumHeight(52)
        b_know.setToolTip(tr("หลักการทำงาน การต่อสาย ข้อควรระวัง และสเปก — เลือกอุปกรณ์บนผังก่อนเพื่อเปิดหน้านั้น"))
        b_know.clicked.connect(lambda: self.show_knowledge())
        h.addWidget(ribbon_group(tr("อุปกรณ์"), [[b_wire, b_know], [None, None]]))
        self.b_rec = tool_button(tr("⏺  บันทึกการกด"), checkable=True)
        self.b_play = tool_button(tr("▶  เล่นซ้ำ"), checkable=True)
        b_mopen, b_msave = tool_button(tr("📂  เปิด")), tool_button(tr("💾  บันทึก"))
        self.b_mlevel = tool_button(tr("🧩  สร้างด่าน\nจากการกด"))
        self.b_mlevel.setMinimumHeight(52)
        self.b_mlevel.setToolTip(tr("แปลงการกดที่บันทึก + output ที่ PLC ตอบ เป็นด่านใหม่ แล้วเปิดในตัวแก้ไขด่าน"))
        self.b_rec.toggled.connect(self._toggle_record)
        self.b_play.toggled.connect(self._toggle_play)
        b_mopen.clicked.connect(lambda: self.open_macro())
        b_msave.clicked.connect(lambda: self.save_macro())
        self.b_mlevel.clicked.connect(self.macro_to_level)
        h.addWidget(ribbon_group(tr("บันทึก / เล่นซ้ำการกด (.plcmacro)"), [
            [self.b_rec, b_mopen, self.b_mlevel], [self.b_play, b_msave, None]]))
        self._teacher_lockables.append(self.b_mlevel)
        h.addStretch(1)
        return tab

    def set_ab_cursors(self, on: bool):
        if on and not self.chart.paused and not self.chart.result_mode:
            self.btn_pause.setChecked(True)
        self.chart.set_ab(on)
        if self.b_ab.isChecked() != on:
            self.b_ab.setChecked(on)
        if on and not self.chart.isVisible():
            self.set_split(True)

    def export_chart(self, kind: str, path: str | None = None) -> str | None:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export กราฟ"), f"chart_{time.strftime('%Y%m%d_%H%M%S')}.{kind}",
                                                  "PNG (*.png)" if kind == "png" else "CSV (*.csv)")
        if not path:
            return None
        if kind == "png":
            self.chart.export_png(path)
        else:
            self.chart.export_csv(path)
        self.log(tr("บันทึกกราฟ: {0}", path))
        return path

    def show_wiring(self):
        from ..panel.wiring import build
        from .wiring_view import WiringDialog
        w = build(self.panel.to_doc().devices, self.xy_base)
        title = self.panel_path.stem if self.panel_path else tr("ผังใหม่")
        dlg = WiringDialog(w, title, self)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        self._wiring_dlg = dlg
        return dlg

    def show_knowledge(self, kind: str | None = None, item=None):
        """ใบความรู้: item (คลิกขวาบนผัง) > อุปกรณ์ที่เลือกในโหมดแก้ไข > หน้าแรก."""
        from .knowledge_dlg import KnowledgeDialog
        props = None
        if item is None and kind is None:
            sel = self.panel.selected_items()
            item = sel[0] if sel else None
        if item is not None:
            kind, props = item.info.kind, dict(item.spec.props)
        dlg = KnowledgeDialog(self, kind, props)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        self._know_dlg = dlg
        return dlg

    def _toggle_record(self, on: bool):
        if on:
            if self.levelp.busy or self.macro.state == "play":
                self.log(tr("บันทึกการกดไม่ได้ขณะตรวจด่าน/เล่นซ้ำ"))
                self.b_rec.setChecked(False)
                return
            self.macro.start_record(self._macro_panel_name())
        elif self.macro.state == "rec":
            self.macro.stop_record()

    def _toggle_play(self, on: bool):
        if on:
            if self.levelp.busy or not self.macro.play():
                if not self.macro.macro:
                    self.log(tr("ยังไม่มีการกดที่บันทึกไว้ — กด ⏺ บันทึกการกด หรือ 📂 เปิดไฟล์ .plcmacro"))
                self.b_play.setChecked(False)
        elif self.macro.state == "play":
            self.macro.stop_play()

    def _on_macro_state(self, s: str):
        for b, want in ((self.b_rec, "rec"), (self.b_play, "play")):
            b.blockSignals(True)
            b.setChecked(s == want)
            b.blockSignals(False)
        self.b_rec.setText(tr("⏹  หยุดบันทึก") if s == "rec" else tr("⏺  บันทึกการกด"))
        self.b_play.setText(tr("⏹  หยุดเล่น") if s == "play" else tr("▶  เล่นซ้ำ"))

    def _macro_panel_name(self) -> str:
        return self.panel_path.name if self.panel_path else ""

    def save_macro(self, path: str | None = None) -> str | None:
        m = self.macro.macro
        if m is None:
            self.log(tr("ยังไม่มีการกดที่บันทึกไว้"))
            return None
        if path is None:
            base = Path(self.panel_path).stem if self.panel_path else "macro"
            path, _ = QFileDialog.getSaveFileName(self, tr("บันทึกการกด"), str(state.PANEL_DIR / f"{base}.plcmacro"),
                                                  tr("การกด (*.plcmacro)"))
        if not path:
            return None
        m.save(path)
        self.log(tr("💾 บันทึกการกด: {0}", Path(path).name))
        return path

    def open_macro(self, path: str | None = None):
        from ..panel.macro import Macro
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, tr("เปิดการกด"), str(state.PANEL_DIR), tr("การกด (*.plcmacro)"))
        if not path:
            return None
        try:
            m = Macro.load(path)
        except (OSError, ValueError, KeyError) as e:
            self.log(tr("✖ เปิดไฟล์การกดไม่ได้: {0}", e))
            return None
        self.macro.macro = m
        self.log(tr("📂 เปิดการกด {0}: {1} การกด · {2:.1f} s", Path(path).name, len(m.inputs), m.duration)
                 + (tr(" (บันทึกจากผัง {0})", m.panel) if m.panel and m.panel != self._macro_panel_name() else ""))
        return m

    def macro_to_level(self):
        from ..panel.macro import to_draft
        if self._exam_locked(tr("สร้างด่าน")):
            return None
        m = self.macro.macro
        if m is None:
            self.log(tr("ยังไม่มีการกดที่บันทึกไว้ — กด ⏺ บันทึกการกด ก่อน (เชื่อม PLC ด้วย จะได้ expect จาก output)"))
            return None
        dlg = self.open_level_editor()
        if dlg is None:
            return None
        panel = ""
        if self.panel_path is not None:
            from ..levels.editor import panel_choices
            vals = [v for _, v in panel_choices(dlg.folder)]
            name = self.panel_path.name
            panel = name if name in vals else (f"panels/{name}" if f"panels/{name}" in vals else "")
        d = to_draft(m, dlg.drafts, panel)
        dlg.add_draft(d)
        return d

    def _build_ai_tab(self) -> QWidget:
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        b_last = tool_button(tr("🤖  วิเคราะห์\nผลตรวจล่าสุด"))
        b_last.setMinimumHeight(52)
        b_last.clicked.connect(self.analyze_last)
        b_live = tool_button(tr("🔎  วิเคราะห์สัญญาณ\nที่กดเล่นอยู่"))
        b_live.setMinimumHeight(52)
        b_live.setToolTip(tr("ดูสัญญาณ 60 วินาทีล่าสุด หาอาการผิดปกติ เช่น ลัดวงจร, กระบอกสูบไม่ถึงปลาย, output กระพริบ"))
        b_live.clicked.connect(self.analyze_live)
        b_ladder = tool_button(tr("📄  เลือก CSV\nladder"))
        b_ladder.setMinimumHeight(52)
        b_ladder.clicked.connect(self.choose_ladder)
        b_claude = tool_button(tr("💬  ให้ Claude\nอธิบายเพิ่ม"))
        b_claude.setMinimumHeight(52)
        b_claude.clicked.connect(lambda: (self.show_levels(), self.levelp.ask_claude()))
        h.addWidget(ribbon_group(tr("วิเคราะห์ความผิดพลาด (คะแนนดูจาก I/O เท่านั้น)"), [[b_last, b_live, b_ladder, b_claude]]))
        ok, why = llm.available()
        self.lbl_ai = QLabel(tr("ตัววิเคราะห์ในเครื่อง: พร้อมใช้ (ไม่ต้องใช้อินเทอร์เน็ต)\n")
                             + (tr("Claude: พร้อมใช้") if ok else tr("Claude: ยังไม่พร้อม — {0}", why)))
        self.lbl_ai.setStyleSheet(f"color:{theme.TEXT_DIM}; padding:6px 12px;")
        h.addWidget(self.lbl_ai)
        h.addStretch(1)
        return tab

    def _fill_levels(self):
        levels = self.levelp.reload(self.xy_base)
        best = self.levelp.best()
        cur = self.cb_level.currentIndex()
        self.cb_level.clear()
        for lv in levels:
            self.cb_level.addItem(f"{stars_text(best.get(lv.id, 0))}  {lv.title}", lv.id)
        if 0 <= cur < self.cb_level.count():
            self.cb_level.setCurrentIndex(cur)
        return levels

    def show_levels(self):
        self.d_level.show()
        self.d_level.raise_()

    # ---------- ตัวแก้ไขด่าน (ครู) ----------
    def open_level_editor(self, select: str | None = None):
        if self._exam_locked(tr("เปิดตัวแก้ไขด่าน")):
            return None
        from .level_editor import LevelEditorDialog
        if select is None and self.levelp.level is not None:
            select = self.levelp.level.id
        dlg = getattr(self, "_level_editor", None)
        if dlg is None:
            from ..levels.engine import LEVEL_DIR
            dlg = LevelEditorDialog(self, self.xy_base, folder=self.levelp.folder or LEVEL_DIR, select=select)
            dlg.saved.connect(self._on_level_saved)
            dlg.open_requested.connect(self._open_level_by_id)
            dlg.finished.connect(lambda _r: setattr(self, "_level_editor", None))
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            self._level_editor = dlg
        dlg.show()
        dlg.raise_()
        return dlg

    def _on_level_saved(self, lid: str):
        cur = self.levelp.level.id if self.levelp.level is not None else None
        levels = self._fill_levels()
        if lid:
            self.log(tr("✏ บันทึกด่าน {0} แล้ว — โหลดรายการด่านใหม่ ({1} ด่าน)", lid, len(levels)))
        if cur and cur == lid and not self.levelp.busy:
            self._open_level_by_id(lid)            # ด่านที่เปิดอยู่ถูกแก้ → เปิดใหม่ให้เห็นโจทย์ล่าสุด

    def _open_level_by_id(self, lid: str):
        ids = [lv.id for lv in self.levelp.levels]
        if lid in ids:
            self.open_level(ids.index(lid))

    def open_level(self, index: int):
        levels = self.levelp.levels
        if not 0 <= index < len(levels):
            raise ValueError(tr("ไม่มีด่านที่ {0} (มี {1} ด่าน)", index + 1, len(levels)))
        lv = levels[index]
        if self.exam and not self.exam.allows(lv.id):
            self.log(tr("🔒 โหมดสอบ: {0} ไม่อยู่ในชุดข้อสอบ", lv.title))
            return
        if self.levelp.busy:
            self.stop_check()
        self._clear_hunt_fault()              # ก่อนเปลี่ยนผัง: ล้างจุดเสียที่ด่านหาจุดเสียใส่ไว้
        if lv.panel and (self.panel_path is None or self.panel_path.resolve() != lv.panel):
            if not self._confirm_discard():
                return
            self._load_panel(lv.panel)
        self.cb_level.setCurrentIndex(index)
        self.levelp.open_level(lv)
        self.set_edit_mode(False)
        self.show_view(self.panel)
        self.show_banner(f"🎯 {lv.title}\n{lv.desc}")
        self.show_levels()
        self._open_ladder()
        if self.poller:
            self.poller.set_watch(self._watch_blocks())
        if lv.is_fault_hunt:
            self.log(tr("เปิด{0} — กด ▶ เริ่มหาจุดเสีย แล้วคลิกขวาอุปกรณ์ที่คิดว่าเสีย (หรือพิมพ์ GUESS <ชื่อ> <อาการ>)", lv.title))
        else:
            self.log(tr("เปิด{0} — ตรวจ {1} ข้อ · เขียน ladder แล้วกด ▶ ตรวจคำตอบ", lv.title, lv.checks))

    def start_check(self):
        if not self.levelp.level:
            if self.levelp.levels:
                self.open_level(max(0, self.cb_level.currentIndex()))
            else:
                self.log(tr("✖ ไม่พบไฟล์ด่านในโฟลเดอร์ levels/"))
                return
        hunt = self.levelp.level.is_fault_hunt
        if not self.online and not hunt:
            self.log(tr("✖ ต้องเชื่อมต่อ PLC ก่อนตรวจ (กด ⏻ เชื่อมต่อ ที่แท็บหน้าแรก)"))
            return
        if self.levelp.busy:
            return
        if self.soft is not None and not hunt:
            if self.ladderv.unsent:               # ตรวจ ladder เก่าแทนของที่เห็นบนจอ = ผลลวง
                self.log(tr("✖ แก้ ladder แล้วยังไม่ได้ส่งลง PLC — กด F4 ในแท็บ Ladder ก่อนตรวจ"))
                self.show_ladder()
                return
            if self.soft.state != "run":          # ก่อนหักสิทธิ์ตรวจของโหมดสอบ
                self.log(tr("✖ PLC ในตัวยังไม่ RUN — {0}", self.soft.fault or tr("ไม่มี ladder ที่รันได้")))
                return
        if self.exam:
            lid = self.levelp.level.id
            ok, why = self.exam.can_check(lid)
            if not ok:
                self.log(f"🔒 {why}")
                return
            self.exam.use_check(lid)
            self._save_exam()
            left = self.exam.checks_left(lid)
            if left is not None:
                self.log(tr("📝 ใช้สิทธิ์ตรวจด่านนี้ไป {0} ครั้ง · เหลือ {1} ครั้ง", self.exam.checks[lid], left))
            self._exam_tick()
        self.set_edit_mode(False)
        self.panel.sc.clearSelection()
        if hunt:
            self._start_hunt()
            return
        self.levelp._read_ladder()            # นักเรียนอาจ Export ไฟล์ใหม่ทับ
        self.poller.set_watch(self._watch_blocks())
        self._write_input_states()            # เริ่มตรวจจากค่าจริงของอุปกรณ์บนผัง ไม่ใช่ค่าเก่าที่ค้างใน PLC
        self.chart.exit_result()              # ระหว่างตรวจ กราฟกลับมาแสดงสัญญาณสด
        n_fault = sum(1 for it in self.panel.fault_items() if it.fault)
        if n_fault:
            self.log(tr("⚠ บนผังมีความผิดปกติที่ครูใส่ไว้ {0} จุด — ผลตรวจอาจไม่ผ่านแม้ ladder ถูก", n_fault))
        self.panel.release_all_keys()
        self.panel.input_locked = True
        self._checked_ladder = self.ladderv.sent
        self.ladderv.canvas.close_editor()
        if self.levelp.start(self._level_write, self._level_action):
            self.show_levels()
            self.log(tr("▶ เริ่มตรวจ{0} — ห้ามกดอุปกรณ์บนผังระหว่างตรวจ", self.levelp.level.title))

    def stop_check(self):
        was_hunt = self.levelp.hunt is not None
        self.levelp.stop()
        self.panel.input_locked = False
        if was_hunt:
            self._clear_hunt_fault()

    # ---------- ด่านหาจุดเสีย ----------
    def _start_hunt(self):
        self._clear_hunt_fault()
        items = {it.label: dict(it.FAULTS) for it in self.panel.fault_items() if it.label}
        try:
            hunt = FaultHunt(self.levelp.level, items)
        except ValueError as e:
            self.log(f"✖ {e}")
            return
        label, code = hunt.answer
        item = next(it for it in self.panel.fault_items() if it.label == label)
        self.faults.cb_hidden.blockSignals(True)
        self.faults.cb_hidden.setChecked(True)
        self.faults.cb_hidden.blockSignals(False)
        self.faults.set_hidden_quiet(True)
        self.panel.set_fault(item, code)
        self._hunt_item = item
        self.panel.guess_enabled = True
        self.levelp.start_hunt(hunt)
        self.show_levels()
        self.log(tr("🔍 เริ่มหาจุดเสีย — มีอุปกรณ์เสีย 1 จุด (ซ่อนอยู่) · กดปุ่มสังเกตอาการ แล้วคลิกขวาอุปกรณ์ที่คิดว่าเสีย"))
        if not self.online:
            self.log(tr("⚠ ยังไม่ได้เชื่อมต่อ PLC — เชื่อมต่อก่อนจึงจะเห็นอาการจากโปรแกรมจริง"))

    def _on_fault_guessed(self, item, code: str):
        if self.levelp.hunt is None:
            return
        r = self.levelp.guess(item.label, code)
        if r is not None and not r.passed and self.levelp.hunt is not None:
            self.sounds.play("fail")

    def _clear_hunt_fault(self):
        """ล้างจุดเสียที่ด่านหาจุดเสียใส่ไว้ และกลับมาแสดงป้าย ⚡ ตามปกติ."""
        item = getattr(self, "_hunt_item", None)
        self._hunt_item = None
        self.panel.guess_enabled = False
        if item is not None and item.spec.id in self.panel.items_by_id:
            self.panel.set_fault(item, "")
        if self.faults.cb_hidden.isChecked():
            self.faults.cb_hidden.blockSignals(True)
            self.faults.cb_hidden.setChecked(False)
            self.faults.cb_hidden.blockSignals(False)
            self.faults.set_hidden_quiet(False)

    def _reveal_hunt(self):
        """จบด่านหาจุดเสีย: เฉลยด้วยป้าย ⚡ บนอุปกรณ์ที่เสีย (ความผิดปกติยังอยู่จนเริ่มรอบใหม่/เปลี่ยนด่าน)."""
        self.panel.guess_enabled = False
        self.faults.cb_hidden.blockSignals(True)
        self.faults.cb_hidden.setChecked(False)
        self.faults.cb_hidden.blockSignals(False)
        self.faults.set_hidden_quiet(False)

    def _level_write(self, addr: str, value: int, is_word: bool):
        if not self.panel.drive_input(addr, value, is_word):
            (self._write_word if is_word else self._write)(addr, value, quiet=True)

    def _level_action(self, name: str, arg: str):
        if name == "part" and not self.panel.spawn_part(arg):
            self.log(tr("✖ ด่านนี้ต้องมีสายพานบนผังเพื่อปล่อยชิ้นงาน"))

    def _on_level_aborted(self, runner):
        self.panel.input_locked = False
        # คืนสิทธิ์เฉพาะเมื่อยังไม่เห็นข้อที่ตก (ไม่ให้ตัดการเชื่อมต่อเพื่อดูผลฟรี)
        if self.exam and self.levelp.level and all(r.passed for r in runner.results):
            lid = self.levelp.level.id
            if self.exam.checks.get(lid, 0) > 0:
                self.exam.checks[lid] -= 1
                self._save_exam()
                self.log(tr("📝 คืนสิทธิ์ตรวจ 1 ครั้ง"))
                self._exam_tick()

    def _on_level_finished(self):
        self.panel.input_locked = False
        self._fill_levels()
        h = self.levelp.last_hunt
        if h is not None and self.levelp.level and self.levelp.level.is_fault_hunt:
            self._reveal_hunt()
            self.sounds.play("pass" if h.found else "fail")
            if self.exam:
                self.exam.record(self.levelp.level.id, h.stars, getattr(h, "plc", ""))
                self._save_exam()
            self._maybe_nudge_support(h.stars)
            return
        self.show_level_result()
        r = self.levelp.last_runner
        if r is not None and r.results:
            self.sounds.play("pass" if r.stars == 3 else "fail")
        if self.exam and r is not None and self.levelp.level:
            self.exam.record(self.levelp.level.id, r.stars, getattr(r, "plc", ""))
            self._save_exam()
        if r is not None:
            self._maybe_nudge_support(r.stars)

    # ---------- ภาษา ----------
    def set_language(self, code: str, ask_restart: bool = True) -> bool:
        """บันทึกภาษาลง ui_state — มีผลเมื่อเปิดโปรแกรมใหม่ (ถามว่าจะเปิดใหม่เลยไหม)."""
        if code not in i18n.LANGS:
            return False
        state.update(lang=code)
        if code == i18n.lang():
            self.log(f"🌐 {i18n.LANGS[code]}")
            return False
        msg = ("เปลี่ยนเป็นภาษาไทยแล้ว — เปิดโปรแกรมใหม่เลยไหม?" if code == "th"  # i18n: skip (ใช้ภาษาปลายทาง)
               else "Language set to English — restart PLC Trainer now?")
        self.log("🌐 " + msg)
        if ask_restart and QMessageBox.question(self, "🌐", msg) == QMessageBox.Yes:
            self.restart_app()
        return True

    def restart_app(self):
        import sys
        from PySide6.QtCore import QProcess
        from .. import paths
        args = [] if paths.frozen() else ["-m", "plc_game.main"]
        if self.close():           # closeEvent ถามบันทึกผังเอง — ยกเลิก = ไม่เปิดใหม่
            QProcess.startDetached(sys.executable, args, str(paths.app_root()))
            QApplication.quit()

    # ---------- สนับสนุนผู้พัฒนา ----------
    def show_about(self):
        from .about_dlg import AboutDialog
        dlg = AboutDialog(self, str(self.cfg.get("update_url", "") or ""))
        dlg.show()
        return dlg

    def show_support(self) -> SupportDialog:
        dlg = SupportDialog(self)
        dlg.show()
        return dlg

    def _support_blocked(self) -> bool:
        """ไม่ชวนโดเนทระหว่างสอบ/บทเรียน/HMI หรือเมื่อมีนักเรียนลงชื่อ (กำลังใช้ในห้องเรียน)."""
        return bool(self.exam or self.tutorial is not None or self.hmi or self.levelp.student != scores.GUEST)

    def _maybe_nudge_support(self, new_stars: int) -> SupportToast | None:
        st = state.load()
        three = sum(1 for s in self.levelp.best().values() if s >= 3)
        reason = support.nudge_reason(st, prev_stars=getattr(self.levelp, "prev_best", 0), new_stars=new_stars,
                                      three_star_count=three, blocked=self._support_blocked())
        if reason is None:
            return None
        state.update(**support.mark_shown(st, reason))
        if reason.startswith("milestone:"):
            text = tr("🏆 ผ่าน 3 ดาวครบ <b>{0} ด่าน</b> แล้ว! เก่งมาก<br>", three)
        else:
            text = tr("⭐ ได้ 3 ดาว! ยินดีด้วย<br>")
        text += tr("PLC Trainer ใช้ฟรี — ถ้าชอบ ร่วมสนับสนุนให้มีด่านใหม่ ๆ ได้นะ")
        toast = SupportToast(self, text)
        toast.support_clicked.connect(self.show_support)
        toast.never_clicked.connect(lambda: (state.update(support_never=True),
                                             self.log(tr("☕ ปิดการเตือนสนับสนุนแล้ว (เปิดหน้าสนับสนุนได้ที่ปุ่ม ☕ หรือ SUPPORT)"))))
        toast.popup()
        self._support_toast = toast
        return toast

    # ---------- ห้องเรียน ----------
    def _set_student(self, sid: str, save: bool = True):
        sid = sid or scores.GUEST
        st = next((s for s in classroom.load_students() if s.sid == sid), None)
        if sid != scores.GUEST and st is None:
            sid = scores.GUEST
        self.levelp.student = sid
        self.levelp.restore_ladder()
        self._open_ladder()
        self.levelp._sync_buttons()
        self.btn_student.setText(f"👤  {st.label}" if st else tr("👤  ลงชื่อนักเรียน"))
        self._fill_levels()
        if save:
            state.update(student=sid)
            self.log(tr("ลงชื่อ: {0}", st.label) if st else tr("ไม่ลงชื่อ — คะแนนบันทึกเป็น guest"))

    def login_student(self):
        if self._exam_locked(tr("เปลี่ยนชื่อผู้สอบ")):
            return
        dlg = LoginDialog(self, current=self.levelp.student)
        res = dlg.exec()
        if res == QDialog.Accepted and dlg.student:
            self._set_student(dlg.student.sid)
        elif res == 2:
            self._set_student(scores.GUEST)

    def show_scores(self) -> ScoreDialog:
        dlg = ScoreDialog(self.levelp.levels, self)
        dlg.show()
        return dlg

    def set_sound(self, on: bool):
        self.sounds.enabled = on
        state.update(sound=on)

    def set_hmi(self, on: bool):
        """HMI เต็มจอ: เหลือแต่ผังอุปกรณ์ (F11 / Esc ออก)."""
        if on == self.hmi:
            return
        self.hmi = on
        if on:
            self._hmi_saved = {"max": self.isMaximized(), "split": self.btn_split.isChecked(),
                               "vis": {w: not w.isHidden() for w in self._hmi_widgets()}}
            self.set_split(False)
            self.set_edit_mode(False)
            self.show_view(self.panel)
            for w in self._hmi_widgets():
                w.hide()
            self.showFullScreen()
            self.panel.fit_all()
            self.log(tr("โหมด HMI เต็มจอ — กด F11 หรือ Esc เพื่อออก"))
        else:
            sv = getattr(self, "_hmi_saved", {"max": False, "split": False, "vis": {}})
            for w, vis in sv["vis"].items():
                w.setVisible(vis)
            self.showMaximized() if sv["max"] else self.showNormal()
            self.set_split(sv["split"])

    def _hmi_widgets(self):
        return [self.menuWidget(), self.side_l.bar, self.side_r.bar, self.side_l.pane, self.side_r.pane,
                self.cmd_bar, self.statusBar(), self.banner, self.space.tabBar(), self.floating]

    def show_level_result(self) -> bool:
        """กราฟผลตรวจล่าสุด: สัญญาณจริง + เส้นประค่าคาดหวัง + แถบแดงช่วงที่ไม่ผ่าน."""
        r, lv = self.levelp.last_runner, self.levelp.level
        if r is None or lv is None:
            return False
        self.chart.show_level_result(r, is_bit=lambda a: parse_device(a, self.xy_base).is_bit, title=lv.title)
        return True

    def show_result_at(self, t0: float, t1: float):
        """คลิกข้อในผลตรวจ → เปิดกราฟผลตรวจที่ช่วงเวลานั้น."""
        if not self.chart.result_mode and not self.show_level_result():
            return
        self.show_view(self.chart)
        self.chart.focus_time(t0, t1)

    # ---------- บทเรียนนำทาง ----------
    def tutorial_steps(self) -> list[TStep]:
        first = self.levelp.levels[0] if self.levelp.levels else None

        def snap_y0():
            return bool(self._history) and bool(self._history[-1][1].get("Y0"))

        def to_ribbon(i):
            def f():
                self.set_hmi(False)
                if self.ribbon_collapsed:
                    self.set_ribbon_collapsed(False)
                self.ribbon.setCurrentIndex(i)
            return f

        def prep_level():
            to_ribbon(2)()
            if first:
                self.cb_level.setCurrentIndex(0)

        return [
            TStep(tr("ยินดีต้อนรับสู่ PLC Trainer 👋"),
                  tr("บทเรียนนี้จะพาทำ 6 ขั้นสั้น ๆ (ประมาณ 2 นาที):<br>"
                  "เชื่อม PLC → เปิดด่าน 1 → กดปุ่มบนผัง → ดูกราฟ → ตรวจคำตอบ<br><br>"
                  "ทำตามกรอบสีฟ้าที่ไฮไลต์ไว้ — คลิกได้เฉพาะในกรอบ")),
            TStep(tr("1. เลือก PLC จำลอง"),
                  tr("เลือก <b>Mock PLC (ทดสอบ)</b> — PLC จำลองในโปรแกรม มีโปรแกรมเฉลยด่าน 1 อยู่แล้ว<br>"
                  "<span style='color:#93A0B5'>ใช้จริงในห้องเรียนให้เลือก GX Simulator3 (SLMP) "
                  "แล้วเขียน ladder ใน GX Works3</span>"),
                  target=lambda: self.cb_backend,
                  done=lambda: self.online or self.cb_backend.currentData() == "mock"),
            TStep(tr("2. เชื่อมต่อ"),
                  tr("กดปุ่ม <b>⏻ เชื่อมต่อ</b> — ป้ายข้างปุ่มจะเปลี่ยนเป็น ONLINE สีเขียว"),
                  target=lambda: self.btn_connect, done=lambda: self.online),
            TStep(tr("3. เปิดด่าน 1"),
                  tr("แท็บ <b>ด่าน / ภารกิจ</b> เลือกด่าน 1 แล้วกด <b>📖 เปิดด่าน</b><br>"
                  "ผังอุปกรณ์ของด่านจะโหลดขึ้นมา พร้อมโจทย์ด้านบน"),
                  target=lambda: self.b_level_open, prepare=prep_level,
                  done=lambda: bool(first) and self.levelp.level is not None and self.levelp.level.id == first.id),
            TStep(tr("4. ลองกดปุ่มบนผัง"),
                  tr("คลิกปุ่ม <b>Start</b> สีเขียว (หรือกดเลข <b>1</b> บนคีย์บอร์ด)<br>"
                  "PLC จะสั่ง Y0 → มอเตอร์หมุน และไฟ RUN ติดค้างแม้ปล่อยปุ่ม (Self-holding)"),
                  target=lambda: self.panel, prepare=lambda: (self.set_edit_mode(False), self.show_view(self.panel)),
                  done=snap_y0),
            TStep(tr("5. ดูสัญญาณบนกราฟ"),
                  tr("กด <b>◫ แบ่งจอ</b> เพื่อดูผังและกราฟพร้อมกัน<br>"
                  "กราฟ Timing แสดงว่าสัญญาณ X0 / Y0 เปลี่ยนเมื่อไร — ใช้หาว่าโปรแกรมผิดตรงไหน"),
                  target=lambda: self.btn_split, prepare=to_ribbon(0), done=lambda: self.btn_split.isChecked()),
            TStep(tr("6. ตรวจคำตอบ"),
                  tr("กด <b>▶ ตรวจคำตอบ</b> แล้วรอประมาณ 10 วินาที<br>"
                  "ตัวตรวจจะกดปุ่มบนผังให้เอง แล้วดูผล Output (ไม่ดูรูปแบบ ladder) — ระหว่างตรวจห้ามกดอุปกรณ์"),
                  target=lambda: self.levelp.btn_check, prepare=self.show_levels,
                  done=lambda: self.levelp.last_runner is not None and not self.levelp.busy),
            TStep(tr("เยี่ยมมาก! 🎉"),
                  tr("ผลตรวจรายข้อและดาวอยู่ในแผงนี้ — ข้อที่ผิดคลิกเพื่อดูช่วงเวลาบนกราฟ<br>"
                  "แท็บ <b>AI วิเคราะห์</b> ช่วยบอกว่าผิดเพราะอะไร<br><br>"
                  "ด่านต่อไป: เขียน ladder ใน GX Works3 ตาม I/O ของโจทย์ แล้วตรวจแบบเดียวกัน<br>"
                  "พิมพ์ <b>HELP</b> ที่ช่องคำสั่งด้านล่างเพื่อดูคำสั่งทั้งหมด · เปิดบทเรียนนี้อีกครั้งได้ที่ "
                  "แท็บหน้าแรก → 🎓 บทเรียนนำทาง"),
                  target=lambda: self.levelp),
        ]

    def ladder_tutorial_steps(self) -> list[TStep]:
        """วาด ladder แรก (X0 → Y0) แล้วรันใน PLC ในตัว — ไม่ใช่คำตอบของด่าน."""
        first = self.levelp.levels[0] if self.levelp.levels else None
        v = self.ladderv

        def ops():
            return [op for op, args in v.code() if args and "?" not in args]

        def ribbon(i):
            def f():
                self.set_hmi(False)
                if self.ribbon_collapsed:
                    self.set_ribbon_collapsed(False)
                self.ribbon.setCurrentIndex(i)
                if i == 2 and first:
                    self.cb_level.setCurrentIndex(0)
            return f

        def to_panel():
            self.set_edit_mode(False)
            self.show_view(self.panel)

        return [
            TStep(tr("เขียน ladder แรกของคุณ 🪜"),
                  tr("บทเรียนนี้ใช้ <b>PLC ในตัว</b> ไม่ต้องมี GX Works3:<br>วาดหน้าสัมผัสและคอยล์ → ส่งลง PLC → ดูไฟวิ่งบน ladder<br><br>"
                     "ตัวอย่างเป็นวงจรง่าย ๆ ยังไม่ใช่คำตอบของด่าน")),
            TStep(tr("1. เลือก PLC ในตัว"), tr("เลือก <b>PLC ในตัว (รัน ladder)</b>"),
                  target=lambda: self.cb_backend, done=lambda: self.soft is not None or self.cb_backend.currentData() == "soft"),
            TStep(tr("2. เชื่อมต่อ"), tr("กดปุ่ม <b>⏻ เชื่อมต่อ</b> — ป้ายข้างปุ่มจะเปลี่ยนเป็น ONLINE สีเขียว"),
                  target=lambda: self.btn_connect, done=lambda: self.online and self.soft is not None),
            TStep(tr("3. เปิดด่าน 1"), tr("กด <b>📖 เปิดด่าน</b> เพื่อให้มีปุ่มและมอเตอร์ไว้ลอง"),
                  target=lambda: self.b_level_open, prepare=ribbon(2),
                  done=lambda: bool(first) and self.levelp.level is not None and self.levelp.level.id == first.id),
            TStep(tr("4. ใส่หน้าสัมผัส"),
                  tr("ช่องแรกเลือกไว้แล้ว พิมพ์ <b>X0</b> แล้วกด <b>Enter</b><br>X0 คือปุ่ม Start — หน้าสัมผัสปิดเมื่อกดปุ่ม<br>"
                     "<span style='color:#93A0B5'>พิมพ์ไม่ติดให้คลิกที่ช่องก่อน และสลับแป้นเป็นอังกฤษ</span>"),
                  target=lambda: v, prepare=self.show_ladder, done=lambda: any(o.startswith("LD") for o in ops())),
            TStep(tr("5. ใส่คอยล์"), tr("เลื่อนไปช่องขวาสุด พิมพ์ <b>Y0</b> แล้วกด <b>Enter</b><br>Y0 คือคอยล์ที่สั่งมอเตอร์"),
                  target=lambda: v, prepare=self.show_ladder, done=lambda: any(o in ("OUT", "SET") for o in ops())),
            TStep(tr("6. ส่งลง PLC"), tr("กด <b>F4</b> — โปรแกรมตรวจ ladder ก่อน ถ้าถูกรูปแบบจะส่งลง PLC ในตัวและ RUN"),
                  target=lambda: v, prepare=self.show_ladder,
                  done=lambda: self.soft is not None and self.soft.state == "run" and not v.unsent),
            TStep(tr("7. ลองกดปุ่ม"), tr("กดปุ่ม <b>Start</b> บนผังค้างไว้ (หรือกดเลข <b>1</b>) แล้วดูมอเตอร์"),
                  target=lambda: self.panel, prepare=to_panel,
                  done=lambda: bool(self._history) and bool(self._history[-1][1].get("X0"))),
            TStep(tr("8. ดูสถานะสด"),
                  tr("บน ladder เส้นและหน้าสัมผัส<b>สีเขียว</b>คือมีไฟ ตัวเลขสีเหลืองคือค่าของ T/C/D<br>"
                     "ปล่อยปุ่มแล้วไฟดับ เพราะวงจรนี้ยังไม่ค้างตัวเอง"),
                  target=lambda: v, prepare=self.show_ladder),
            TStep(tr("พร้อมแล้ว! 🎉"),
                  tr("ต่อไปลองทำให้มอเตอร์ค้างแม้ปล่อยปุ่ม และหยุดด้วยปุ่ม Stop แล้วกด <b>▶ ตรวจคำตอบ</b><br><br>"
                     "แก้ ladder แล้วต้องกด <b>F4</b> ใหม่ทุกครั้ง · ผิดตรงไหนแท็บ <b>AI วิเคราะห์</b> จะชี้ rung ให้"),
                  prepare=self.show_levels),
        ]

    def start_tutorial(self, ladder: bool = False):
        if self._exam_locked(tr("เปิดบทเรียนนำทาง")):
            return None
        if self.tutorial is not None:
            self.tutorial.raise_()
            return self.tutorial
        self.tutorial = TutorialOverlay(self, self.ladder_tutorial_steps() if ladder else self.tutorial_steps(),
                                        tr("บทเรียน ladder") if ladder else tr("บทเรียนนำทาง: เริ่มต้นใช้งาน"))
        self.tutorial.finished.connect(self._on_tutorial_finished)
        self.tutorial.start()
        self.log(tr("🎓 เริ่มบทเรียนนำทาง — ทำตามกรอบสีฟ้า (กด 'ข้ามบทเรียน' เพื่อออก)"))
        return self.tutorial

    def _on_tutorial_finished(self, completed: bool):
        self.tutorial = None
        state.update(tutorial_done=True)
        self.log(tr("🎓 จบบทเรียนนำทาง") if completed else tr("🎓 ข้ามบทเรียนนำทาง — เปิดใหม่ได้ที่แท็บหน้าแรก → 🎓 บทเรียนนำทาง"))

    # ---------- โหมดสอบ ----------
    def _exam_locked(self, what: str) -> bool:
        if self.exam:
            self.log(tr("🔒 โหมดสอบ: {0}ไม่ได้", what))
            return True
        return False

    def setup_exam(self) -> ExamSetupDialog | None:
        if self.exam:
            self.log(tr("กำลังอยู่ในโหมดสอบแล้ว — พิมพ์ EXAM STATUS ดูเวลาที่เหลือ"))
            return None
        lv = self.levelp.level
        dlg = ExamSetupDialog(self.levelp.levels, state.load().get("teacher_pw"), self,
                              preselect=(lv.id,) if lv else ())
        if dlg.exec() == QDialog.Accepted and dlg.session:
            if dlg.new_hash:
                state.update(teacher_pw=dlg.new_hash)
            self.start_exam(dlg.session)
        return dlg

    def start_exam(self, session: ExamSession, resumed: bool = False):
        if self.tutorial is not None:
            self.tutorial.finish(False)
        if self.levelp.busy:
            self.stop_check()
        self.set_hmi(False)
        if not resumed:
            session.student = self.levelp.student
        elif session.student:
            self._set_student(session.student, save=False)
        self.exam = session
        self._exam_over = False
        self._save_exam()
        self.set_edit_mode(False)
        self._apply_exam_lock(True)
        self._exam_timer.start()
        titles = {lv.id: lv.title for lv in self.levelp.levels}
        if self.levelp.level is None or not session.allows(self.levelp.level.id):
            idx = next((i for i, lv in enumerate(self.levelp.levels) if lv.id == session.level_ids[0]), None)
            if idx is not None:
                self.open_level(idx)
        self.log((tr("📝 กลับเข้าโหมดสอบ") if resumed else tr("📝 เริ่มโหมดสอบ"))
                 + tr(" — {0} นาที · ตรวจได้ ", session.minutes)
                 + (tr("{0} ครั้ง/ด่าน", session.max_checks) if session.max_checks else tr("ไม่จำกัด"))
                 + tr(" · ด่าน: ") + ", ".join(titles.get(i, i) for i in session.level_ids))
        if session.student == scores.GUEST:
            self.log(tr("⚠ ผู้สอบยังไม่ได้ลงชื่อ — คะแนนจะบันทึกเป็น guest"))
        self._exam_tick()

    def end_exam(self, password: str | None = None) -> bool:
        """จบการสอบ: ต้องใส่รหัสครู (ส่ง password มาตรง ๆ ได้ — ใช้ในคำสั่ง/ทดสอบ)."""
        if not self.exam:
            return False
        stored = state.load().get("teacher_pw")
        if password is None:
            if TeacherPasswordDialog(stored, self).exec() != QDialog.Accepted:
                return False
        else:
            from .exam import verify_password
            if not verify_password(password, stored):
                self.log(tr("✖ รหัสครูไม่ถูกต้อง"))
                return False
        if self.levelp.busy:
            self.stop_check()
        summary = self.exam_summary()
        self.exam = None
        self._exam_over = False
        self._exam_timer.stop()
        state.update(exam=None)
        self._apply_exam_lock(False)
        self.log(tr("🔓 จบการสอบ\n") + summary)
        return True

    def exam_summary(self) -> str:
        ex = self.exam
        if not ex:
            return ""
        titles = {lv.id: lv.title for lv in self.levelp.levels}
        lines = [tr("  {0}: {1} (ตรวจ {2} ครั้ง)", titles.get(i, i), stars_text(ex.best.get(i, 0)), ex.checks.get(i, 0))
                 + (" · " + classroom.plc_label(ex.plc[i]) if ex.plc.get(i) else "")
                 for i in ex.level_ids]
        lines.append(tr("  รวม {0}/{1} ดาว", ex.total_stars(), 3 * len(ex.level_ids)))
        return "\n".join(lines)

    def _save_exam(self):
        if self.exam:
            state.update(exam=self.exam.to_dict())

    def _apply_exam_lock(self, on: bool):
        for i in (1, 4):                                   # แท็บ แก้ไขผัง / AI วิเคราะห์
            self.ribbon.setTabEnabled(i, not on)
        if on and self.ribbon.currentIndex() in (1, 4):
            self.ribbon.setCurrentIndex(2)
        for w in (self.btn_edit, self.btn_edit2, self.st_mode, self.btn_student, self.library, self.faults,
                  *self._teacher_lockables):
            w.setEnabled(not on)
        self.b_exam_end.setEnabled(on)
        self.levelp.set_ai_enabled(not on)
        self._open_ladder()
        self.lbl_exam.setVisible(on)
        if not on:
            self.lbl_exam.clear()

    def _exam_tick(self):
        ex = self.exam
        if not ex:
            return
        rem = ex.remaining_s()
        lv = self.levelp.level
        left = ex.checks_left(lv.id) if (lv and ex.allows(lv.id)) else None
        extra = tr("  ·  ตรวจได้อีก {0}", left) if left is not None else ""
        if rem <= 0:
            self.lbl_exam.setText(tr("📝 หมดเวลา") + extra)
            col = theme.DANGER
            if not self._exam_over:
                self._exam_over = True
                self.sounds.play("buzzer")
                self.log(tr("⏰ หมดเวลาสอบ — ตรวจคำตอบเพิ่มไม่ได้แล้ว (การตรวจที่กำลังทำอยู่จะทำต่อจนจบ)\n")
                         + self.exam_summary())
        else:
            self.lbl_exam.setText(f"📝 {fmt_clock(rem)}" + extra)
            col = theme.DANGER if rem <= 60 else (theme.WARN if rem <= 300 else theme.SUCCESS)
        self.lbl_exam.setStyleSheet(f"font-weight:bold; font-family:Consolas; font-size:12pt; color:{col};"
                                    f" border:1px solid {col}; border-radius:8px; padding:2px 10px;")

    def analyze_last(self):
        if self._exam_locked(tr("ใช้ AI วิเคราะห์")):
            return
        self.show_levels()
        lp = self.levelp
        if lp.last_runner and lp.level:
            lp.analyze_result()
        else:
            self.log(tr("ยังไม่มีผลตรวจ — เปิดด่านแล้วกด ▶ ตรวจคำตอบก่อน (หรือใช้ 🔎 วิเคราะห์สัญญาณที่กดเล่นอยู่)"))

    def choose_ladder(self):
        if self._exam_locked(tr("ใช้ AI วิเคราะห์")):
            return
        self.show_levels()
        if not self.levelp._ladder_allowed():
            self.log(tr("เปิดด่านก่อน (และต้องไม่กำลังตรวจ) แล้วจึงเลือกไฟล์ CSV"))
            return
        self.levelp.choose_ladder()

    def _on_ladder_changed(self):
        if self.poller and not self.levelp.busy:
            self.poller.set_watch(self._watch_blocks())

    def analyze_live(self):
        if self._exam_locked(tr("ใช้ AI วิเคราะห์")):
            return
        self.show_levels()
        fs = self.levelp.analyze_live(list(self._history))
        for f in fs:
            self.log("🤖 " + f.text())

    def _build_teacher_tab(self) -> QWidget:
        tab = QWidget()
        h = QHBoxLayout(tab)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        b_show = tool_button(tr("⚡  แผงความผิดปกติ"))
        b_show.setMinimumHeight(52)
        b_show.setToolTip(tr("เปิดแผง FAULTS ด้านขวา เลือกความผิดปกติรายอุปกรณ์"))
        b_show.clicked.connect(self.show_faults)
        b_rand, b_clear = tool_button(tr("🎲  สุ่ม 1 จุด")), tool_button(tr("✔  ล้างทั้งหมด"))
        b_rand.clicked.connect(self.faults.random_fault)
        b_clear.clicked.connect(self.faults.clear_all)
        self.btn_hide_faults = tool_button(tr("🙈  ซ่อนจากนักเรียน"), checkable=True)
        self.btn_hide_faults.setToolTip(tr("ไม่แสดงป้าย ⚡ บนอุปกรณ์ — ใช้สอบหาจุดเสีย"))
        self.btn_hide_faults.toggled.connect(self.faults.cb_hidden.setChecked)
        self.faults.cb_hidden.toggled.connect(self.btn_hide_faults.setChecked)
        h.addWidget(ribbon_group(tr("Fault Injection — ใส่ความผิดปกติ"), [
            [b_show, b_rand, self.btn_hide_faults],
            [None, b_clear, None],
        ]))
        b_scores = tool_button(tr("🏆  ตารางคะแนน\nทั้งห้อง"))
        b_scores.setMinimumHeight(52)
        b_scores.setToolTip(tr("ดาวรายด่านของนักเรียนทุกคน + Export Excel"))
        b_scores.clicked.connect(self.show_scores)
        b_xlsx = tool_button("📊  Export Excel")
        b_xlsx.clicked.connect(lambda: self.show_scores().export())
        h.addWidget(ribbon_group(tr("ห้องเรียน"), [[b_scores, b_xlsx], [None, None]]))
        self.b_exam = tool_button(tr("📝  เริ่ม\nโหมดสอบ"))
        self.b_exam.setMinimumHeight(52)
        self.b_exam.setToolTip(tr("จำกัดเวลา/จำนวนครั้งตรวจ · ปิด AI · ล็อกการแก้ผัง — ออกได้ด้วยรหัสครู"))
        self.b_exam.clicked.connect(self.setup_exam)
        self.b_exam_end = tool_button(tr("🔓  จบการสอบ"))
        self.b_exam_end.setEnabled(False)
        self.b_exam_end.clicked.connect(self.end_exam)
        h.addWidget(ribbon_group(tr("โหมดสอบ"), [[self.b_exam, self.b_exam_end], [None, None]]))
        self.b_level_edit = tool_button(tr("✏  ตัวแก้ไข\nด่าน"))
        self.b_level_edit.setMinimumHeight(52)
        self.b_level_edit.setToolTip(tr("สร้าง/แก้/ทำสำเนา/ลบด่าน โดยไม่ต้องเขียน YAML (ตรวจจากผล I/O)"))
        self.b_level_edit.clicked.connect(lambda: self.open_level_editor())
        h.addWidget(ribbon_group(tr("ด่าน"), [[self.b_level_edit], [None]]))
        self._teacher_lockables = [b_show, b_rand, b_clear, self.btn_hide_faults, b_scores, b_xlsx, self.b_exam,
                                   self.b_level_edit]
        tip = QLabel(tr("ตัวอย่างการฝึก:\n• เซนเซอร์ค้าง ON → โปรแกรมต้องไม่สั่งงานผิดลำดับ\n"
                     "• ลมไม่มา → ตั้ง Timer เฝ้า ถ้า a1 ไม่มาใน 3 วินาทีให้เตือน\n"
                     "• OL ทริป → หยุดมอเตอร์ + ไฟแดง/ออด"))
        tip.setStyleSheet(f"color:{theme.TEXT_DIM}; padding:6px 12px;")
        h.addWidget(tip)
        h.addStretch(1)
        return tab

    def show_faults(self):
        self.d_faults.show()
        self.d_faults.raise_()

    def show_iolist(self):
        self.d_iolist.show()
        self.d_iolist.raise_()

    def _build_space(self):
        self.space = QTabWidget()
        self.space.setObjectName("Space")
        self.space.setTabPosition(QTabWidget.South)
        self.space.addTab(self.panel, "Panel")
        self.space.addTab(self.chart, "Chart")
        self.space.addTab(self.ladderv, "Ladder")
        self.space.currentChanged.connect(lambda _i: self._on_space_tab(self.space))
        self.split_tabs = QTabWidget()             # แบ่งจอ: ผังบน · กราฟ/Ladder ล่าง
        self.split_tabs.setObjectName("Space")
        self.split_tabs.setTabPosition(QTabWidget.South)
        self.split_tabs.currentChanged.connect(lambda _i: self._on_space_tab(self.split_tabs))
        center = QWidget()
        v = QVBoxLayout(center)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.banner = QLabel()
        self.banner.setObjectName("Banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        v.addWidget(self.banner)
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setHandleWidth(5)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.space)
        self.stack.addWidget(self.splitter)
        v.addWidget(self.stack, 1)

        # ----- แผงซ้าย | ผัง | แผงขวา (แผงยุบได้) -----
        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.setHandleWidth(3)
        self.hsplit.setChildrenCollapsible(False)
        self.side_l = SideDock("left", self.hsplit, 0)
        self.side_r = SideDock("right", self.hsplit, 2)
        self.hsplit.addWidget(self.side_l.pane)
        self.hsplit.addWidget(center)
        self.hsplit.addWidget(self.side_r.pane)
        self.hsplit.setStretchFactor(1, 1)
        for s in (self.side_l, self.side_r):
            s.pane.setMinimumWidth(0)
            s.on_change = self._on_side_change
        self.hsplit.setCollapsible(0, True)
        self.hsplit.setCollapsible(2, True)
        self.hsplit.splitterMoved.connect(lambda *_: self._save_sides())

        wrap = QWidget()
        self._central_v = QVBoxLayout(wrap)
        self._central_v.setContentsMargins(0, 0, 0, 0)
        self._central_v.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.side_l.bar)
        row.addWidget(self.hsplit, 1)
        row.addWidget(self.side_r.bar)
        self._central_v.addLayout(row, 1)
        self.setCentralWidget(wrap)
        self._build_floating()

    def _build_floating(self):
        """แถบลอยมุมขวาล่างของผัง: ซูม / ดูทั้งผัง / แบ่งจอ / ป้ายโหมด."""
        f = QFrame(self.panel)
        f.setObjectName("Floating")
        h = QHBoxLayout(f)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(2)
        self.lbl_mode_chip = QLabel("RUN")
        self.lbl_mode_chip.setStyleSheet(f"font-weight:bold; color:{theme.SUCCESS}; padding:0 6px;")
        h.addWidget(self.lbl_mode_chip)
        for text, tip, fn in (("−", tr("ซูมออก"), lambda: self.panel.zoom_by(1 / 1.25)),
                              ("+", tr("ซูมเข้า"), lambda: self.panel.zoom_by(1.25)),
                              ("⛶", tr("ดูทั้งผัง (ดับเบิลคลิกปุ่มกลางเมาส์)"), self.panel.fit_all)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
        self.fl_split = QToolButton()
        self.fl_split.setText("◫")
        self.fl_split.setToolTip(tr("แบ่งจอ ผัง + กราฟ"))
        self.fl_split.setCheckable(True)
        self.fl_split.toggled.connect(self.set_split)
        h.addWidget(self.fl_split)
        f.adjustSize()
        self.floating = f
        self._place_floating()       # ขนาดผังเปลี่ยน → _KeyFilter (filter ระดับแอป) เรียกซ้ำให้

    def _place_floating(self):
        f, p = self.floating, self.panel
        f.adjustSize()
        f.move(max(4, p.width() - f.width() - 14), max(4, p.height() - f.height() - 14))
        f.raise_()

    def _on_side_change(self, side, key, is_open):
        self._save_sides()

    def _save_sides(self):
        if getattr(self, "_restoring_sides", False):
            return
        for s in (self.side_l, self.side_r):
            s.save()

    def set_split(self, on: bool):
        """แบ่งจอ: ผังด้านบน + กราฟด้านล่าง แทนการสลับแท็บ."""
        if on and self.stack.currentWidget() is not self.splitter:
            self.space.clear()
            self.splitter.addWidget(self.panel)
            self.splitter.addWidget(self.split_tabs)
            self.split_tabs.addTab(self.chart, "Chart")
            self.split_tabs.addTab(self.ladderv, "Ladder")
            self.split_tabs.show()
            self.panel.show()       # QTabWidget ซ่อนหน้าที่ไม่ได้เลือกไว้
            self.splitter.setSizes([520, 480])
            self.stack.setCurrentWidget(self.splitter)
        elif not on and self.stack.currentWidget() is not self.space:
            self.split_tabs.clear()
            self.space.addTab(self.panel, "Panel")
            self.space.addTab(self.chart, "Chart")
            self.space.addTab(self.ladderv, "Ladder")
            self.stack.setCurrentWidget(self.space)
        for b in (self.btn_split, self.st_split, self.fl_split):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        state.update(split=on)

    def show_view(self, widget):
        """แสดงผังหรือกราฟ (ในโหมดแบ่งจอเห็นทั้งคู่อยู่แล้ว)."""
        if self.stack.currentWidget() is self.space:
            self.space.setCurrentWidget(widget)
        elif widget is not self.panel:
            self.split_tabs.setCurrentWidget(widget)

    def _on_space_tab(self, tabs):
        if tabs.currentWidget() is self.ladderv and tabs.isVisible():
            self._fill_ladder_addresses()
            self.ladderv.setFocus()

    def set_large(self, on: bool):
        scale = theme.LARGE_SCALE if on else 1.0
        QApplication.instance().setStyleSheet(theme.make_qss(scale))
        panel_items.set_font_scale(scale)
        self.chart.set_scale(scale)
        for b in (self.btn_large, self.st_large):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        self._apply_ribbon_height()
        for it in self.panel.items_by_id.values():
            it.prepareGeometryChange()
            it.update()
        self.panel.viewport().update()
        for b in (self.btn_large, self.st_large):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        state.update(large=on)

    def show_banner(self, text: str):
        self.banner.setText(text)
        self.banner.setVisible(bool(text))

    def _dock(self, title, widget, area, min_w=None):
        d = QDockWidget(title, self)
        d.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        d.setWidget(widget)
        if min_w:
            d.setMinimumWidth(min_w)
        self.addDockWidget(area, d)
        return d

    def _build_docks(self):
        """แผงข้าง: ซ้าย = เครื่องมือ/ข้อมูลผัง · ขวา = คุณสมบัติ/ด่าน/ครู."""
        self.layers_box = QWidget()
        self.layers_grid = QGridLayout(self.layers_box)
        self.layers_grid.setAlignment(Qt.AlignTop)
        s2 = QScrollArea()
        s2.setWidgetResizable(True)
        s2.setWidget(self.layers_box)
        s2.setFrameShape(QFrame.NoFrame)
        L, R = self.side_l, self.side_r
        L.add("library", "🧰", tr("อุปกรณ์"), self.library, tr("อุปกรณ์ — ลากไปวางบนผัง (Ctrl+B ยุบ/กาง)"))
        L.add("iolist", "☰", tr("ตาราง I/O"), self.iolist, tr("ตาราง I/O + ค่าสด + Export"))
        L.add("layers", "📈", tr("สัญญาณบนกราฟ"), s2, tr("เลือกสัญญาณที่แสดงบนกราฟ Timing"))
        R.add("props", "⚙", tr("คุณสมบัติ"), self.props, tr("คุณสมบัติ / สเปกของอุปกรณ์ที่เลือก"))
        R.add("level", "🎯", tr("ด่าน / ผลตรวจ / AI"), self.levelp, tr("ด่าน ผลตรวจ และ AI วิเคราะห์"))
        R.add("faults", "⚡", tr("ความผิดปกติ (ครู)"), self.faults, tr("Fault Injection — ใส่ความผิดปกติ (ครู)"))
        self.d_iolist = PaneHandle(L, "iolist")
        self.d_layers = PaneHandle(L, "layers")
        self.d_props = PaneHandle(R, "props")
        self.d_level = PaneHandle(R, "level")
        self.d_faults = PaneHandle(R, "faults")
        self._restoring_sides = True
        L.restore(default_open=True)
        R.restore(default_open=True)
        self._restoring_sides = False
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self._toggle_side(self.side_l))
        QShortcut(QKeySequence("Ctrl+Alt+B"), self, activated=lambda: self._toggle_side(self.side_r))

    def _toggle_side(self, side):
        side.collapse() if side.is_open else side.open()

    def _build_cmdline(self):
        bar = self.cmd_bar = QFrame()
        bar.setObjectName("CmdBar")
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.cmd_history = QPlainTextEdit()
        self.cmd_history.setObjectName("CmdHistory")
        self.cmd_history.setReadOnly(True)
        self.cmd_history.setMaximumBlockCount(500)
        self.cmd_history.setFixedHeight(110)
        row = QHBoxLayout()
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)
        self.btn_cmd = QToolButton()
        self.btn_cmd.setText("⌨")
        self.btn_cmd.setCheckable(True)
        self.btn_cmd.setToolTip(tr("แสดง/ซ่อน ประวัติคำสั่งและข้อความ (Ctrl+`)"))
        self.btn_cmd.toggled.connect(self.set_cmd_history)
        prompt = QLabel(tr("▸ คำสั่ง"))
        prompt.setObjectName("CmdPrompt")
        self.cmd_input = QLineEdit()
        self.cmd_input.setObjectName("CmdInput")
        self.cmd_input.setPlaceholderText(tr("พิมพ์คำสั่ง เช่น SET X0, EDIT, RUN, HELP"))
        self.cmd_input.returnPressed.connect(self._on_command)
        self.lbl_last = QLabel()
        self.lbl_last.setStyleSheet(f"color:{theme.TEXT_DIM};")
        self.lbl_last.setMaximumWidth(520)
        row.addWidget(self.btn_cmd)
        row.addWidget(prompt)
        row.addWidget(self.cmd_input, 1)
        row.addWidget(self.lbl_last)
        v.addWidget(self.cmd_history)
        v.addLayout(row)
        self._central_v.addWidget(bar)
        on = state.load().get("cmd_history", True)
        self.btn_cmd.setChecked(on)
        self.cmd_history.setVisible(on)
        QShortcut(QKeySequence("Ctrl+`"), self, activated=self.btn_cmd.toggle)

    def set_cmd_history(self, on: bool):
        self.cmd_history.setVisible(on)
        self.lbl_last.setVisible(not on)
        state.update(cmd_history=on)

    def _build_statusbar(self):
        sb = self.statusBar()
        self.lbl_cursor = QLabel("")
        self.lbl_cursor.setMinimumWidth(420)
        sb.addWidget(self.lbl_cursor, 1)
        self.lbl_rate = QLabel("— Hz")
        self.st_mode = tool_button("RUN", checkable=True)
        self.st_mode.toggled.connect(self.btn_edit.setChecked)
        self.st_snap = tool_button("SNAP", checkable=True)
        self.st_snap.setChecked(True)
        self.st_snap.toggled.connect(lambda on: setattr(self.panel.sc, "snap", 20 if on else 0))
        self.st_grid = tool_button("GRID", checkable=True)
        self.st_grid.setChecked(True)
        self.st_grid.toggled.connect(self._set_grid)
        self.st_rec = tool_button("REC", checkable=True)
        self.st_rec.setChecked(True)
        self.st_rec.toggled.connect(lambda on: self.btn_pause.setChecked(not on))
        self.st_online = tool_button("OFFLINE")
        self.st_online.setEnabled(False)
        self.st_split = tool_button("SPLIT", checkable=True)
        self.st_split.toggled.connect(self.set_split)
        self.st_large = tool_button("BIG", checkable=True)
        self.st_large.toggled.connect(self.set_large)
        self.st_sound = tool_button("SOUND", checkable=True)
        self.st_sound.setToolTip(tr("เสียงประกอบ: ตรวจผ่าน / ไม่ผ่าน / ออด"))
        self.st_sound.setChecked(self.sounds.enabled)
        self.st_sound.toggled.connect(self.set_sound)
        for w in (self.lbl_rate, self.st_mode, self.st_snap, self.st_grid, self.st_split, self.st_large,
                  self.st_sound, self.st_rec, self.st_online):
            sb.addPermanentWidget(w)
        self._set_online(False)
        self._n_snap = 0
        self._rate_timer = QTimer(self)
        self._rate_timer.timeout.connect(self._update_rate)
        self._rate_timer.start(1000)

    # ================= panel file =================
    def _open_startup_panel(self):
        path = None
        last = state.load().get("last_panel")
        if last and Path(last).exists():
            path = Path(last)
        path = path or (DEFAULT_PANEL if DEFAULT_PANEL.exists() else None)
        if path:
            self._load_panel(path)
        else:
            self.panel.load_doc(PanelDoc())

    def _load_panel(self, path: Path):
        try:
            doc = PanelDoc.load(path)
        except (OSError, ValueError) as e:
            self.log(tr("✖ เปิดผังไม่ได้: {0}", e))
            return
        self.panel.load_doc(doc)
        self.panel_path = Path(path)
        self._remember(path)
        self.dirty = False
        self._update_title()
        if self.poller:                       # เปลี่ยนผังขณะเชื่อมต่อ: อ่าน address ชุดใหม่
            self.poller.set_watch(self._watch_blocks())
        if self.online:                       # ส่งค่า Input ของผังใหม่ (เช่น อุณหภูมิเตา) ทับค่าเก่าที่ค้างใน PLC
            self._write_input_states()
        self.log(tr("เปิดผัง: {0} ({1} อุปกรณ์)", Path(path).name, len(doc.devices)))

    def _remember(self, path):
        state.update(last_panel=str(Path(path).resolve()))
        remember_recent(path)

    def show_quickstart(self):
        """หน้าเริ่มต้น: เลือกผังล่าสุด / ฉากตัวอย่าง แล้วเชื่อมต่อ PLC ให้เลย."""
        dlg = QuickStartDialog(self, current_backend=self.cb_backend.currentData())
        if dlg.exec() != QDialog.Accepted:
            return
        if dlg.action == "new":
            self.new_panel()
        elif dlg.action == "browse":
            self.open_panel()
        elif dlg.path and self._confirm_discard():
            self._load_panel(dlg.path)
            self.set_edit_mode(False)
            self.show_view(self.panel)
        if dlg.backend:
            if self.poller and self.cb_backend.currentData() != dlg.backend:
                self.disconnect_plc()
            self.cb_backend.setCurrentIndex(self.cb_backend.findData(dlg.backend))
            self.connect_plc()

    def _on_clean_changed(self, clean: bool):
        self.dirty = not clean
        self._update_title()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, tr("ผังยังไม่ได้บันทึก"), tr("บันทึกผังปัจจุบันก่อนไหม?"),
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_panel()
        return r == QMessageBox.Discard

    def new_panel(self):
        if self._exam_locked(tr("สร้างผังใหม่")) or not self._confirm_discard():
            return
        self.panel.load_doc(PanelDoc())
        self.panel_path = None
        self.dirty = False
        self.btn_edit.setChecked(True)
        self._update_title()
        self.log(tr("ผังใหม่ — ลากอุปกรณ์จาก TOOL PALETTE มาวางได้เลย"))

    def open_panel(self):
        if self._exam_locked(tr("เปิดผังอื่น")) or not self._confirm_discard():
            return
        PANEL_DIR.mkdir(exist_ok=True)
        fn, _ = QFileDialog.getOpenFileName(self, tr("เปิดผังอุปกรณ์"), str(PANEL_DIR), tr("ผังอุปกรณ์ (*.plcpanel)"))
        if fn:
            self._load_panel(Path(fn))

    def save_panel(self, as_new=False) -> bool:
        path = self.panel_path
        if as_new or path is None:
            PANEL_DIR.mkdir(exist_ok=True)
            fn, _ = QFileDialog.getSaveFileName(self, tr("บันทึกผังอุปกรณ์"), str(PANEL_DIR / tr("ผังใหม่.plcpanel")),
                                                tr("ผังอุปกรณ์ (*.plcpanel)"))
            if not fn:
                return False
            path = Path(fn)
            if path.suffix != ".plcpanel":
                path = path.with_suffix(".plcpanel")
            self.panel.doc_name = path.stem
        self.panel.flush_commit()
        self.panel.to_doc().save(path)
        self.panel.undo.setClean()
        self.panel_path = path
        self._remember(path)
        self.dirty = False
        self._update_title()
        self.log(tr("บันทึกผัง: {0}", path.name))
        return True

    def _update_title(self):
        name = self.panel_path.name if self.panel_path else tr("ผังใหม่")
        self.setWindowTitle(f"PLC Trainer — {name}{' *' if self.dirty else ''}")
        self.lbl_doc.setText(f"📐 {name}{'  ●' if self.dirty else ''}")
        self.lbl_doc.setToolTip(tr("มีการแก้ไขที่ยังไม่บันทึก") if self.dirty else "")

    def set_edit_mode(self, edit: bool):
        if edit and self.exam:
            self.log(tr("🔒 โหมดสอบ: แก้ไขผังไม่ได้"))
            edit = False
        self.panel.set_run_mode(not edit)
        for b in (self.btn_edit, self.btn_edit2, self.st_mode):
            b.blockSignals(True)
            b.setChecked(edit)
            b.blockSignals(False)
        self.btn_run.setChecked(not edit)
        self.st_mode.setText("EDIT" if edit else "RUN")
        self.lbl_mode_chip.setText("✎ EDIT" if edit else "▶ RUN")
        self.lbl_mode_chip.setStyleSheet(
            f"font-weight:bold; color:{theme.WARN if edit else theme.SUCCESS}; padding:0 6px;")
        self._place_floating()
        if edit and not self.side_l.is_open:
            self.side_l.open("library")          # แก้ไขผัง = ต้องใช้แผงอุปกรณ์
        if edit:
            self.show_view(self.panel)
        self.log(tr("โหมดแก้ไขผัง: ลากวาง/ย้าย/ลบอุปกรณ์ได้") if edit else tr("โหมดใช้งาน: คลิกอุปกรณ์เพื่อกด/สับสวิตช์"))

    def _add_from_library(self, kind):
        if self._exam_locked(tr("เพิ่มอุปกรณ์")):
            return
        if not self.btn_edit.isChecked():
            self.set_edit_mode(True)
        self.show_view(self.panel)
        self.panel.add_device(kind)

    def _on_panel_changed(self):
        self.dirty = not self.panel.undo.isClean() or self.panel._commit_timer.isActive()
        self._update_title()
        self._rebuild_layers()
        if self.poller:
            self.poller.set_watch(self._watch_blocks())
        if self.online:
            self._write_input_states()

    def _signal_names(self) -> list[str]:
        names = list(self.panel.addresses())
        for s in EXTRA_SIGNALS:
            if s not in names:
                names.append(s)
        return names

    def _watch_blocks(self):
        names = self._signal_names()
        if self.levelp.level:                 # ด่าน: อ่าน X0–X17 / Y0–Y17 ด้วย (ให้ AI เห็นคอยล์ที่เขียนผิดเลข)
            names = list(dict.fromkeys(names + self.levelp.level.watch_addresses(self.xy_base)))
        names = list(dict.fromkeys(names + self.levelp.ladder_watch()))
        return blocks_for(names, self.xy_base)

    def _write_input_states(self):
        for addr, val, is_word in self.panel.input_states():
            (self._write_word if is_word else self._write)(addr, val, quiet=True)

    # ================= PLC =================
    def _on_connect_toggled(self, on: bool):
        if on:
            self.connect_plc()
        else:
            self.disconnect_plc()

    def connect_plc(self):
        if self.poller:
            return
        cfg = dict(self.cfg)
        cfg.update(backend=self.cb_backend.currentData(), host=self.ed_host.text().strip(),
                   port=self.sp_port.value())
        try:
            client = create_client(cfg)
        except ValueError as e:
            self.log(f"✖ {e}")
            return
        self.poller = PLCPoller(client, poll_ms=self.sp_poll.value(), watch=self._watch_blocks(),
                                xy_base=self.xy_base)
        self.poller.snapshot.connect(self._on_snapshot)
        self.poller.connected.connect(self._set_online)
        self.poller.error.connect(lambda m: self.log(f"✖ {m}"))
        self.chart.clear()
        self.soft = client if isinstance(client, SoftPLC) else None
        if self.soft is not None:
            self.ladderv.mark_sent(None)
            self.levelp.set_builtin(True)
            self._open_ladder()
            self.send_ladder(auto=True)
        self.poller.start()
        self.log(tr("กำลังเชื่อมต่อ {0} …", client.name))
        for w in (self.cb_backend, self.ed_host, self.sp_port, self.sp_poll):
            w.setEnabled(False)
        self.btn_connect.blockSignals(True)
        self.btn_connect.setChecked(True)
        self.btn_connect.setText(tr("⏻  ตัดการเชื่อมต่อ"))
        self.btn_connect.blockSignals(False)

    def disconnect_plc(self):
        if self.poller:
            self.poller.stop()
            self.poller = None
            self.soft = None
            self.levelp.set_builtin(False)
            self.ladderv.mark_sent(None)
            self.log(tr("ตัดการเชื่อมต่อแล้ว"))
        self._set_online(False)
        for w in (self.cb_backend, self.ed_host, self.sp_port, self.sp_poll):
            w.setEnabled(True)
        self.btn_connect.blockSignals(True)
        self.btn_connect.setChecked(False)
        self.btn_connect.setText(tr("⏻  เชื่อมต่อ"))
        self.btn_connect.blockSignals(False)

    # ---------- เขียน ladder / PLC ในตัว ----------
    def _ladder_path(self) -> Path:
        """ladder แยกคน แยกด่าน (สอบ: แยกโฟลเดอร์ เริ่มจากว่าง ของเดิมไม่ถูกแตะ)."""
        sid = classroom.clean_id(self.levelp.student) or scores.GUEST
        lid = "".join(c if c.isalnum() or c in "_-" else "_" for c in (self.levelp.level.id if self.levelp.level else "free"))
        p = state.PANEL_DIR / "ladders" / sid
        if self.exam:
            p = p / f"exam_{int(self.exam.started_at)}"
        return p / f"{lid}.csv"

    def _open_ladder(self):
        """นักเรียน/ด่าน/โหมดสอบเปลี่ยน → เปิด ladder ของคู่นั้น และ PLC ในตัวต้องไม่รันของเก่าค้าง."""
        path = self._ladder_path()
        if path == self.ladderv.file and bool(self.exam) == self.ladderv.exam:
            return
        self._checked_ladder = None
        self.ladderv.open_file(path, exam=bool(self.exam))
        self._fill_ladder_addresses()
        if self.soft is not None:
            self.soft.unload()
            self.levelp.set_builtin(True)
            self.send_ladder(auto=True)

    def _fill_ladder_addresses(self):
        rows = iolist.rows([it.spec for it in self.panel.items_by_id.values()], self.xy_base)
        self.ladderv.set_addresses(iolist.gx_comments(rows))      # หลายอุปกรณ์ใช้ address เดียว = รวมชื่อ

    def show_ladder(self):
        if self.hmi:
            self.set_hmi(False)
        self._fill_ladder_addresses()
        self.show_view(self.ladderv)
        self.ladderv.setFocus()

    def send_ladder(self, auto: bool = False) -> bool:
        """F4: ตรวจแล้วส่งลง PLC ในตัว — มีปัญหา = ไม่ส่ง (ของที่รันอยู่ไม่เปลี่ยน)."""
        v = self.ladderv
        if auto and v.empty:
            return False
        if not v.editable():
            return False
        v.canvas.close_editor()
        c = v.doc.compile()
        probs = check_ladder(Ladder(c.program, self.xy_base))
        v.show_problems(c, probs, [] if probs else v.notes(c))
        if probs:
            k = probs[0].k
            n, uid = c.where[k] if 0 <= k < len(c.where) else (0, 0)
            self.log(tr("✖ ladder ยังส่งไม่ได้ ({0} จุด) — rung {1}: {2}", len(probs), n + 1, probs[0].text))
            if not auto:
                v.goto_uid(uid, n)
            return False
        if self.soft is None:
            self.log(tr("✔ ladder ถูกรูปแบบ — เลือก PLC ในตัว ที่มุมบนแล้วกดเชื่อมต่อเพื่อรัน"))
            return False
        self.soft.load(c.program)
        v.mark_sent(c)
        v.flush()
        self.levelp.set_builtin(True, c.program)
        if self.poller:
            self.poller.set_watch(self._watch_blocks())
        if self.online:
            self._write_input_states()
        self.log(tr("✔ PLC ในตัว RUN: {0} คำสั่ง", len(c.program.instrs)))
        return True

    def soft_control(self, what: str):
        if self.soft is None or not self.ladderv.editable():
            return
        if what == "run":
            self.soft.run_plc()
        elif what == "stop":
            self.soft.stop_plc()
        else:
            self.soft.reset_plc()
            self._write_input_states()
        self.ladderv.refresh_monitor()

    def goto_ladder_step(self, step: int):
        self.show_ladder()
        self.ladderv.goto_step(step, self._checked_ladder)

    def _offline_warn(self, quiet: bool) -> bool:
        """คืน True ถ้ายังไม่ได้เชื่อมต่อ (เตือนไม่เกิน 1 ครั้งต่อ 5 วินาที)."""
        if self.poller:
            return False
        import time
        now = time.monotonic()
        if not quiet and now - getattr(self, "_warned_at", -99) > 5:
            self._warned_at = now
            self.log(tr("✖ ยังไม่ได้เชื่อมต่อ PLC — กดปุ่ม 'เชื่อมต่อ' หรือพิมพ์ CONNECT"))
        return True

    def _write(self, device: str, value: int, quiet: bool = False):
        if not self._offline_warn(quiet):
            self.poller.write_bit(device, value)

    def _write_word(self, device: str, value: int, quiet: bool = False):
        if not self._offline_warn(quiet):
            self.poller.write_word(device, value)

    def _on_snapshot(self, snap: dict, t: float):
        self._n_snap += 1
        self.panel.apply_snapshot(snap)
        self.chart.add_snapshot(snap, t)
        self.macro.on_snapshot(snap)
        if self.d_iolist.isVisible():
            self.iolist.update_values(snap)
        if not self._history or self._history[-1][1] != snap:
            self._history.append((t, snap))
            while self._history and t - self._history[0][0] > 60:
                self._history.popleft()
        if self.levelp.runner is not None:
            self.levelp.feed(snap, t)

    def _set_online(self, on: bool):
        was = self.online
        self.online = on
        if not on:
            self.levelp.abort(tr("การเชื่อมต่อ PLC หลุด"))
        self.levelp.set_plc(self.cb_backend.currentData() if on else "none")    # ช่องเลือกถูกล็อกขณะเชื่อมต่อ
        self.st_online.setText("ONLINE" if on else "OFFLINE")
        self.st_online.setStyleSheet(f"background:{theme.SUCCESS if on else theme.DANGER}; color:white;")
        self.lbl_online.setText("● ONLINE" if on else "○ OFFLINE")
        self.lbl_online.setStyleSheet(f"background:{theme.SUCCESS if on else '#4B5568'};")
        if on and not was:
            self.log(tr("✔ เชื่อมต่อ PLC สำเร็จ"))
            self._write_input_states()   # ให้ PLC เห็นสถานะเริ่มต้น (เช่น NC = ON)

    def _update_rate(self):
        self.lbl_rate.setText(f"{self._n_snap} Hz")
        sim = self.cb_backend.currentData() == "slmp" and str(self.cfg.get("host", "127.0.0.1")) in ("127.0.0.1", "localhost")
        self.lbl_rate.setToolTip(
            tr("จำนวนครั้งที่อ่านค่าจาก PLC ต่อวินาที")
            + (tr("\nGX Simulator3 ตอบ SLMP เป็นช่วง ๆ ทุก ~100 ms → ค่าใหม่จริงราว 10 ครั้ง/วินาที "
               "(เวลาบนกราฟใช้เวลาที่ข้อมูลมาถึง จึงยังแม่น) · PLC จริงผ่าน Ethernet อ่านได้เร็วกว่านี้") if sim else ""))
        self._n_snap = 0

    # ================= chart / layers =================
    def _rebuild_layers(self):
        names = self._signal_names()
        old = {n for n, cb in self._sig_checks.items() if not cb.isChecked()}
        self._unchecked |= old
        while self.layers_grid.count():
            w = self.layers_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._sig_checks = {}
        for i, name in enumerate(names):
            cb = QCheckBox(name)
            cb.setStyleSheet(f"color:{theme.color_for(name)};")
            cb.setChecked(name not in self._unchecked)
            cb.toggled.connect(lambda on, n=name: (self._unchecked.discard(n) if on else self._unchecked.add(n),
                                                   self._apply_signal_selection()))
            self._sig_checks[name] = cb
            self.layers_grid.addWidget(cb, i // 3, i % 3)
        self._apply_signal_selection()

    def _apply_signal_selection(self):
        sel = [n for n, cb in self._sig_checks.items() if cb.isChecked()]
        bits, words = [], []
        for n in sel:
            try:
                (bits if parse_device(n, self.xy_base).is_bit else words).append(n)
            except ValueError:
                pass
        self.chart.set_signals(bits, words)

    def _set_paused(self, paused: bool):
        self.chart.set_paused(paused)
        self.st_rec.blockSignals(True)
        self.st_rec.setChecked(not paused)
        self.st_rec.blockSignals(False)
        self.btn_pause.setText(tr("▶  เล่นต่อ") if paused else tr("⏸  หยุดกราฟ"))

    def _set_grid(self, on: bool):
        for p in (self.chart.timing, self.chart.trend):
            p.showGrid(x=on, y=on, alpha=0.18)
        self.panel.sc.show_grid = on
        self.panel.viewport().update()

    def _on_cursor(self, t: float, values: str):
        self.lbl_cursor.setText(f"t = {t:7.2f} s    {values}")

    # ================= command line =================
    def log(self, text: str):
        self.cmd_history.appendPlainText(text)
        last = text.splitlines()[0] if text else ""
        self.lbl_last.setText(last if len(last) < 90 else last[:88] + "…")

    def _on_command(self):
        raw = self.cmd_input.text().strip()
        self.cmd_input.clear()
        if not raw:
            return
        self.log(tr("คำสั่ง: {0}", raw))
        parts = raw.upper().split()
        cmd, args = parts[0], parts[1:]
        try:
            if cmd == "HELP":
                self.log(HELP)
            elif cmd == "CONNECT":
                self.connect_plc()
            elif cmd == "DISCONNECT":
                self.disconnect_plc()
            elif cmd in ("SET", "RST", "PULSE"):
                if not args:
                    raise ValueError(tr("ต้องระบุอุปกรณ์ เช่น {0} X0", cmd))
                dev = parse_device(args[0], self.xy_base)
                if not dev.is_bit:
                    raise ValueError(tr("{0} ไม่ใช่อุปกรณ์บิต", dev.name))
                if self.levelp.runner is not None:
                    raise ValueError(tr("กำลังตรวจคำตอบ — เขียนค่าเองไม่ได้"))
                if cmd == "PULSE":
                    self._write(dev.name, 1)
                    QTimer.singleShot(200, lambda: self._write(dev.name, 0))
                else:
                    self._write(dev.name, 1 if cmd == "SET" else 0)
            elif cmd == "EDIT":
                self.set_edit_mode(True)
            elif cmd == "RUN":
                self.set_edit_mode(False)
            elif cmd in ("ZOOM", "Z"):
                self.panel.fit_all()
            elif cmd in ("U", "UNDO"):
                self._exam_locked(tr("ย้อนกลับ")) or self.panel.do_undo()
            elif cmd == "REDO":
                self._exam_locked(tr("ทำซ้ำ")) or self.panel.do_redo()
            elif cmd == "SPLIT":
                self.set_split(not self.btn_split.isChecked())
            elif cmd == "BIG":
                self.set_large(not self.btn_large.isChecked())
            elif cmd == "HMI":
                self.set_hmi(not self.hmi)
            elif cmd == "LOGIN":
                self.login_student()
            elif cmd == "SCORES":
                self.show_scores()
            elif cmd == "PAUSE":
                self.btn_pause.setChecked(True)
            elif cmd == "RESUME":
                self.btn_pause.setChecked(False)
            elif cmd == "CLEAR":
                self.chart.clear()
            elif cmd == "WINDOW" and args:
                self.sp_window.setValue(float(args[0]))
            elif cmd == "FAULT":
                if not self._exam_locked(tr("ใส่ความผิดปกติ")):
                    self._fault_command(raw.split()[1:])
            elif cmd in ("TUTORIAL", "TOUR"):
                self.start_tutorial(ladder=bool(args) and args[0].upper() == "LADDER")
            elif cmd in ("SUPPORT", "DONATE"):
                self.show_support()
            elif cmd in ("ABOUT", "VERSION"):
                self.show_about()
            elif cmd == "LANG":
                if not args or args[0].lower() not in i18n.LANGS:
                    raise ValueError("LANG TH | LANG EN")
                self.set_language(args[0].lower())
            elif cmd == "GUESS":
                self._guess_command(raw.split()[1:])
            elif cmd in ("LEVELEDIT", "EDITLEVEL"):
                self.open_level_editor()
            elif cmd in ("WIRING", "WIRE"):
                self.show_wiring()
            elif cmd in ("KNOW", "SHEET"):
                self.show_knowledge()
            elif cmd == "AB":
                self.set_ab_cursors(not self.chart.ab_on if not args else args[0] in ("ON", "1"))
            elif cmd == "REC":
                self.b_rec.setChecked(self.macro.state != "rec")
            elif cmd == "PLAY":
                self.b_play.setChecked(self.macro.state != "play")
            elif cmd == "MACROLEVEL":
                self.macro_to_level()
            elif cmd == "EXAM":
                sub = args[0] if args else ""
                if sub in ("END", "STOP", "OFF"):
                    self.end_exam()          # ถามรหัสในหน้าต่าง ไม่รับรหัสทางบรรทัดคำสั่ง (จะค้างในประวัติ)
                elif sub == "STATUS":
                    if self.exam:
                        self.log(tr("📝 เหลือเวลา {0}\n", fmt_clock(self.exam.remaining_s())) + self.exam_summary())
                    else:
                        self.log(tr("ไม่ได้อยู่ในโหมดสอบ"))
                else:
                    self.setup_exam()
            elif cmd in ("IO", "IOLIST"):
                self.show_iolist()
                for r in self.iolist.rows:
                    self.log(f"  {r.address:<6} {r.direction:<14} {r.label or r.device}"
                             + (f" · {r.slot}" if r.prop != "address" else "") + (f" ({r.contact})" if r.contact else ""))
            elif cmd == "ASSIGN":
                self.iolist.auto_assign()
            elif cmd == "ALIGN":
                modes = {"L": "left", "R": "right", "T": "top", "B": "bottom", "C": "hcenter", "M": "vcenter"}
                if not args or args[0][:1] not in modes:
                    raise ValueError(tr("ใช้ ALIGN L / R / T / B / C (กึ่งกลางแนวตั้ง) / M (กึ่งกลางแนวนอน)"))
                self.panel.align(modes[args[0][:1]])
            elif cmd in ("DIST", "DISTRIBUTE"):
                self.panel.distribute("v" if args[:1] == ["V"] else "h")
            elif cmd in ("START", "SCENES", "SCENE"):
                self.show_quickstart()
            elif cmd in ("LEVEL", "LEVELS"):
                if not args:
                    for i, lv in enumerate(self.levelp.levels):
                        self.log(f"  {i + 1}. {stars_text(self.levelp.best().get(lv.id, 0))}  {lv.title}")
                else:
                    self.open_level(int(args[0]) - 1)
            elif cmd == "CHECK":
                self.start_check()
            elif cmd == "STOP":
                self.stop_check()
            elif cmd == "DRAW":
                self.show_ladder()
            elif cmd == "LADDER":
                self.levelp.set_ladder(None) if args[:1] == ["CLEAR"] else self.choose_ladder()
            elif cmd == "ANALYZE":
                self.analyze_live() if args[:1] == ["LIVE"] else self.analyze_last()
            else:
                self.log(tr("✖ ไม่รู้จักคำสั่ง '{0}' — พิมพ์ HELP", cmd))
        except (ValueError, PLCError) as e:
            self.log(f"✖ {e}")

    def _guess_command(self, args: list[str]):
        """GUESS <ชื่อ|address> <รหัสอาการ> — ทายจุดเสีย (ด่านหาจุดเสีย)."""
        if self.levelp.hunt is None:
            raise ValueError(tr("ยังไม่ได้เริ่มหาจุดเสีย — เปิดด่านหาจุดเสียแล้วกด ▶ เริ่มหาจุดเสีย"))
        if len(args) < 2:
            raise ValueError(tr("ใช้: GUESS <ชื่ออุปกรณ์> <อาการ> เช่น GUESS Start STUCK_ON (พิมพ์ FAULT ดูรหัสอาการ)"))
        it = self.panel.find_item(" ".join(args[:-1]))
        if it is None:
            raise ValueError(tr("ไม่พบอุปกรณ์ '{0}'", ' '.join(args[:-1])))
        code = args[-1].lower()
        if code not in it.FAULTS:
            raise ValueError(tr("{0} มีอาการให้เลือก: ", it.label) + ", ".join(c.upper() for c in it.FAULTS))
        self._on_fault_guessed(it, code)

    def _fault_command(self, args: list[str]):
        """FAULT | FAULT CLEAR | FAULT RANDOM | FAULT <ชื่อ|address> <รหัส|OK>."""
        sub = args[0].upper() if args else ""
        if not args or sub == "LIST":
            items = self.panel.fault_items()
            if not items:
                self.log(tr("ผังนี้ไม่มีอุปกรณ์ที่ใส่ความผิดปกติได้"))
            for it in items:
                now = tr("  ← ตอนนี้: {0}", it.fault.upper()) if it.fault and not self.panel.sc.faults_hidden else ""
                self.log(f"  {it.label or it.info.name} [{it.addr}]: " + ", ".join(c.upper() for c in it.FAULTS) + now)
            self.log(tr("ใช้: FAULT <ชื่อ|address> <รหัส>  ·  FAULT <ชื่อ> OK = ล้าง  ·  FAULT RANDOM  ·  FAULT CLEAR"))
        elif sub == "CLEAR":
            self.faults.clear_all()
        elif sub == "RANDOM":
            self.faults.random_fault()
        else:
            if len(args) < 2:
                raise ValueError(tr("ต้องระบุรหัสความผิดปกติ เช่น FAULT PS1 STUCK_ON (พิมพ์ FAULT ดูรายการ)"))
            it = self.panel.find_item(" ".join(args[:-1]))
            if it is None:
                raise ValueError(tr("ไม่พบอุปกรณ์ชื่อ/address '{0}' ที่ใส่ความผิดปกติได้", ' '.join(args[:-1])))
            code = args[-1].lower()
            if code in ("ok", "normal", "clear"):
                code = ""
            elif code not in it.FAULTS:
                raise ValueError(tr("{0} ใช้ได้เฉพาะ: ", it.label) + ", ".join(c.upper() for c in it.FAULTS))
            self.faults._chosen(it, code)

    # ================= คีย์ลัดกดอุปกรณ์ =================
    def _on_key_event(self, e) -> bool:
        """KeyPress/KeyRelease จาก _KeyFilter → True ถ้าใช้กดอุปกรณ์บนผัง (กิน event)."""
        if e.isAutoRepeat() or e.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            return False
        fw = QApplication.focusWidget()
        if fw is not None and self.ladderv.isAncestorOf(fw):
            return False
        typing = isinstance(fw, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit, QComboBox))
        if typing or QApplication.activeModalWidget() is not None or not self.isActiveWindow():
            return False
        key = self._key_name(e)
        if not key:
            return False
        return bool(self.panel.key_down(key) if e.type() == QEvent.KeyPress else self.panel.key_up(key))

    @staticmethod
    def _key_name(e) -> str:
        """ใช้รหัสปุ่มจริง (Windows virtual key) จึงใช้ได้แม้คีย์บอร์ดเป็นภาษาไทย."""
        for k in (e.nativeVirtualKey(), int(e.key())):
            if 0x30 <= k <= 0x39 or 0x41 <= k <= 0x5A:     # VK_0..9 / VK_A..Z = รหัส ASCII
                return chr(k)
            if 0x60 <= k <= 0x69:                          # VK_NUMPAD0..9
                return str(k - 0x60)
        return ""

    def closeEvent(self, e):
        if not self._confirm_discard():
            e.ignore()
            return
        self.shutdown()
        super().closeEvent(e)

    def shutdown(self) -> None:
        """เตรียมหน้าต่างก่อนถูกลบ (ปิดโปรแกรม / จบ test): ตัดการเชื่อมต่อ, ถอด filter ระดับแอป, ปิดกราฟ pyqtgraph.

        ถ้าไม่ทำ การลบหน้าต่างที่ยังมี filter/กราฟทำงานอยู่ทำให้ process abort แบบสุ่มตอนปิด (เรียกซ้ำได้)
        """
        self.disconnect_plc()
        self.ladderv.shutdown()
        self.levelp.shutdown()
        self._keyfilter.active = False
        QApplication.instance().removeEventFilter(self._keyfilter)
        self.chart.shutdown()
