"""ตัวแก้ไขด่านของครู: สร้าง/แก้/ทำสำเนา/ลบด่าน โดยไม่ต้องเขียน YAML เอง.

ซ้าย = รายการด่าน · ขวา = ข้อมูลด่าน + แท็บ ข้อตรวจ / reset / หาจุดเสีย
ทุกขั้นตอนตรวจความถูกต้องทันที (ช่องแดง + tooltip) และตรวจทั้งด่านด้วยตัวโหลดจริงก่อนบันทึก
"""
from __future__ import annotations

from ..i18n import tr

import copy
import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from ..ai import learn, spec
from ..levels import conditions as C
from ..levels import editor as E
from ..levels import rooms
from ..levels.engine import LEVEL_DIR
from ..panel import PanelDoc
from ..panel import iolist
from . import theme
from .cond_builder import CondBuilder
from .learn_worker import LearnWorker
from .level_wizard import LevelWizard
from .thai_keys import latin_only

BAD = QColor("#5A1E24")


def panel_info(path: Path | None, xy_base: int = 8) -> tuple[list, dict[str, dict[str, str]]]:
    """(แถว I/O ของผัง, {ป้ายอุปกรณ์: {รหัสอาการ: คำอธิบาย}})."""
    if path is None:
        return [], {}
    try:
        doc = PanelDoc.load(path)
    except (OSError, ValueError):
        return [], {}
    rows = iolist.rows(doc.devices, xy_base)
    from .panel.view import PanelView
    v = PanelView(xy_base=xy_base)
    v.load_doc(doc)
    faults = {it.label: dict(it.FAULTS) for it in v.fault_items() if it.label}
    v.deleteLater()
    return rows, faults


def _btn(text, tip=""):
    b = QPushButton(text)
    b.setAutoDefault(False)          # ไม่งั้นกด Enter ในช่องพิมพ์ = กดปุ่มแรกของหน้าต่าง (ข้อความที่พิมพ์หาย)
    if tip:
        b.setToolTip(tip)
    return b


def _load_devices(path: Path | None) -> list:
    try:
        return PanelDoc.load(path).devices if path else []
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


class StepTable(QWidget):
    """ตารางขั้นตอน: คำสั่ง | พารามิเตอร์ | ข้อความผลตรวจ | คำใบ้."""
    changed = Signal()
    loaded = Signal()

    def __init__(self, xy_base: int = 8, allow_checks: bool = True, parent=None):
        super().__init__(parent)
        self.xy_base = xy_base
        self.allow_checks = allow_checks
        self._loading = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("คำสั่ง"), tr("พารามิเตอร์"), tr("ข้อความในผลตรวจ"), tr("คำใบ้เมื่อไม่ผ่าน")])
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_help(r))
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_add = _btn(tr("➕ เพิ่มขั้น"))
        self.b_del = _btn(tr("✖ ลบ"))
        self.b_up = _btn("▲")
        self.b_down = _btn("▼")
        self.b_add.clicked.connect(self.add_row)
        self.b_del.clicked.connect(self.remove_row)
        self.b_up.clicked.connect(lambda: self.move_row(-1))
        self.b_down.clicked.connect(lambda: self.move_row(1))
        for b in (self.b_add, self.b_del, self.b_up, self.b_down):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.lbl_help = QLabel()
        self.lbl_help.setWordWrap(True)
        self.lbl_help.setStyleSheet(f"color:{theme.TEXT_DIM};")
        v.addWidget(self.lbl_help)

    # ----- ข้อมูล -----
    def set_steps(self, steps: list[E.StepRow]):
        self._loading = True
        self.table.setRowCount(0)
        for s in steps:
            self._insert(self.table.rowCount(), s)
        self._loading = False
        self.validate()
        self.loaded.emit()

    def steps(self) -> list[E.StepRow]:
        out = []
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 0)
            out.append(E.StepRow(cb.currentText(), self._txt(r, 1), self._txt(r, 2), self._txt(r, 3),
                                 dict(self.table.item(r, 1).data(Qt.UserRole) or {})))
        return out

    def _txt(self, r, c) -> str:
        it = self.table.item(r, c)
        return it.text().strip() if it else ""

    def _insert(self, r: int, s: E.StepRow):
        self.table.insertRow(r)
        cb = QComboBox()
        ops = E.OPS if self.allow_checks else [o for o in E.OPS if o not in E.CHECK_OPS]
        cb.addItems(ops)
        if s.op not in ops:
            cb.addItem(s.op)
        cb.setCurrentText(s.op)
        cb.currentTextChanged.connect(self._on_op_changed)
        self.table.setCellWidget(r, 0, cb)
        for c, text in enumerate((s.params, s.msg, s.hint), 1):
            self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.item(r, 1).setData(Qt.UserRole, dict(s.extra))      # msg_en / hint_en ฯลฯ ต้องไม่หายตอนบันทึก

    def add_row(self):
        r = self.table.currentRow() + 1 if self.table.currentRow() >= 0 else self.table.rowCount()
        self._loading = True
        self._insert(r, E.StepRow("expect" if self.allow_checks else "wait",
                                  "Y0 = 1 within 0.5" if self.allow_checks else "0.5"))
        self._loading = False
        self.table.setCurrentCell(r, 1)
        self._emit()

    def remove_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._emit()

    def move_row(self, d: int):
        r = self.table.currentRow()
        n = r + d
        if r < 0 or not 0 <= n < self.table.rowCount():
            return
        st = self.steps()
        st[r], st[n] = st[n], st[r]
        self.set_steps(st)
        self.table.setCurrentCell(n, 1)
        self._emit()

    # ----- ตรวจ -----
    def _on_item_changed(self, _it):
        if not self._loading:
            self._emit()

    def _on_op_changed(self, _t):
        if not self._loading:
            self._show_help(self.table.currentRow())
            self._emit()

    def _emit(self):
        self.validate()
        self.changed.emit()

    def validate(self) -> int:
        bad = 0
        self._loading = True
        for r, s in enumerate(self.steps()):
            err = s.error(self.xy_base)
            if not err and s.is_check and not self.allow_checks:
                err = tr("ใช้ {0} ใน reset ไม่ได้ (ใช้ waitfor แทน)", s.op)
            it = self.table.item(r, 1)
            if it is None:
                continue
            it.setBackground(QBrush(BAD) if err else QBrush())
            it.setToolTip(err or (tr("นับคะแนน") if s.is_check else ""))
            bad += bool(err)
        self._loading = False
        return bad

    def _show_help(self, r: int):
        if r < 0 or r >= self.table.rowCount():
            self.lbl_help.setText(tr("เลือกแถวเพื่อดูวิธีเขียนพารามิเตอร์"))
            return
        cb = self.table.cellWidget(r, 0)
        if cb is None:                       # แถวกำลังถูกสร้าง ยังไม่มีช่องคำสั่ง
            return
        op = cb.currentText()
        th, ex = E.OP_HELP.get(op, ("", ""))
        self.lbl_help.setText(tr("<b>{0}</b> — {1} · ตัวอย่าง: <code>{2}</code>  ·  ตัวเปรียบเทียบ = != >= <= > < · หลายเงื่อนไขใช้ and", op, th, ex))


class LevelEditorDialog(QDialog):
    saved = Signal(str)          # id ของด่านที่บันทึก
    open_requested = Signal(str)

    try_requested = Signal(str)
    rooms_changed = Signal()

    def __init__(self, parent=None, xy_base: int = 8, folder: Path = LEVEL_DIR, select: str | None = None,
                 room: str = "", lock_standard: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("✏ ตัวแก้ไขด่าน (ครู)"))
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        scr = (parent or self).screen().availableGeometry()
        self.resize(min(1500, int(scr.width() * .94)), min(1000, int(scr.height() * .92)))
        self.xy_base = xy_base
        self.root = Path(folder)                 # levels/ (ด่านมาตรฐาน)
        self.room = rooms.get(room, self.root) if room else None
        self.folder = self.room.path if self.room else self.root
        self.lock_standard = lock_standard
        self.current_panel = None                # ฟังก์ชันคืน (PanelDoc, ชื่อ) ของผังที่เปิดอยู่
        self._devices: list = []
        self._ai: LearnWorker | None = None
        self._old_ai: list = []
        self._ai_profile = None
        self._ai_tips: list = []
        self._ai_result = None
        self.memory = learn.Memory()
        self.drafts: list[E.LevelDraft] = []
        self.cur: E.LevelDraft | None = None
        self.dirty = False
        self._loading = False
        self._case_i = -1
        self._from_builder = False
        self._closing = False
        self._fault_map: dict[str, dict[str, str]] = {}

        root = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ----- ซ้าย: รายการด่าน -----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr("<b>ห้องด่าน</b>")))
        rr = QHBoxLayout()
        self.cb_room = QComboBox()
        self.b_room = QToolButton()
        self.b_room.setText("⋯")
        self.b_room.setToolTip(tr("สร้าง / เปลี่ยนชื่อ / ลบ / ส่งออก / นำเข้าห้อง"))
        self.b_room.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.b_room)
        self.a_room_new = m.addAction(tr("➕ สร้างห้องใหม่…"), lambda: self.create_room())
        self.a_room_ren = m.addAction(tr("✎ เปลี่ยนชื่อห้อง…"), lambda: self.rename_room())
        self.a_room_exp = m.addAction(tr("📤 ส่งออกห้อง (.plcroom)…"), lambda: self.export_room())
        self.a_room_imp = m.addAction(tr("📥 นำเข้าห้อง (.plcroom)…"), lambda: self.import_room())
        self.a_room_del = m.addAction(tr("🗑 ลบห้อง…"), lambda: self.delete_room())
        self.b_room.setMenu(m)
        rr.addWidget(self.cb_room, 1)
        rr.addWidget(self.b_room)
        lv.addLayout(rr)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._on_pick)
        lv.addWidget(self.lst, 1)
        g = QHBoxLayout()
        self.b_new = _btn(tr("➕ สร้างด่าน"), tr("สร้างด่านใหม่ในห้องของคุณ ทีละขั้น"))
        self.b_new.setObjectName("Primary")
        self.b_new_hunt = _btn(tr("🔍 หาจุดเสียใหม่"))
        self.b_dup = _btn(tr("⧉ ทำสำเนา"))
        self.b_del = _btn(tr("🗑 ลบ"), tr("ย้ายไป levels/_trash (กู้คืนได้)"))
        self.b_new.clicked.connect(lambda: self.create_level())
        self.b_new_hunt.clicked.connect(lambda: self.create_hunt())
        self.b_dup.clicked.connect(self.duplicate)
        self.b_del.clicked.connect(self.delete)
        for b in (self.b_new, self.b_new_hunt):
            g.addWidget(b)
        lv.addLayout(g)
        g2 = QHBoxLayout()
        g2.addWidget(self.b_dup)
        g2.addWidget(self.b_del)
        lv.addLayout(g2)
        self.b_copy = _btn(tr("📋 ทำสำเนาไปห้องของฉัน"), tr("ด่านมาตรฐานแก้ไม่ได้ — ทำสำเนา (พร้อมผัง) ไปแก้ในห้องของคุณ"))
        self.b_copy.clicked.connect(lambda: self.copy_to_room())
        lv.addWidget(self.b_copy)
        split.addWidget(left)

        # ----- ขวา: ฟอร์ม -----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.lock_bar = QFrame()                        # ด่านมาตรฐาน: บอกให้ชัดว่าต้องกดอะไร
        self.lock_bar.setObjectName("LockBar")
        self.lock_bar.setStyleSheet(f"QFrame#LockBar {{ border:1px solid {theme.WARN}; border-radius:8px; }}")
        lb = QHBoxLayout(self.lock_bar)
        lt = QLabel(tr("🔒 ด่านมาตรฐานแก้ไม่ได้ ช่องด้านล่างจึงกดไม่ได้ — สร้างด่านใหม่ หรือทำสำเนาไปแก้"))
        lt.setWordWrap(True)
        lb.addWidget(lt, 1)
        self.b_lock_new, self.b_lock_copy = _btn(tr("➕ สร้างด่าน")), _btn(tr("📋 ทำสำเนาไปห้องของฉัน"))
        self.b_lock_new.setObjectName("Primary")
        self.b_lock_new.clicked.connect(lambda: self.create_level())
        self.b_lock_copy.clicked.connect(lambda: self.copy_to_room())
        lb.addWidget(self.b_lock_new)
        lb.addWidget(self.b_lock_copy)
        rv.addWidget(self.lock_bar)
        form = QFormLayout()
        self.ed_id = latin_only(QLineEdit())
        self.ed_id.setToolTip(tr("ชื่อไฟล์ levels/<รหัส>.yaml · เปลี่ยนรหัสแล้วคะแนนเก่าจะไม่ผูกกับด่านนี้"))
        self.sp_order = QSpinBox()
        self.sp_order.setRange(0, 999)
        idrow = QHBoxLayout()
        idrow.addWidget(self.ed_id, 1)
        idrow.addWidget(QLabel(tr("ลำดับ")))
        idrow.addWidget(self.sp_order)
        form.addRow(tr("รหัสด่าน"), idrow)
        self.ed_title = QLineEdit()
        form.addRow(tr("ชื่อด่าน"), self.ed_title)
        self.cb_panel = QComboBox()
        self.cb_panel.setEditable(False)
        prow = QHBoxLayout()
        prow.addWidget(self.cb_panel, 1)
        self.b_use_panel = _btn(tr("📐 ใช้ผังที่เปิดอยู่"), tr("คัดลอกผังที่เปิดในหน้าต่างหลักเข้าห้องนี้"))
        self.b_use_panel.clicked.connect(lambda: self.use_current_panel())
        self.b_auto = _btn(tr("✨ เติมค่าพัก/reset"), tr("ตั้งค่าพักของทุกปุ่มและขั้นตอน reset จากผังให้อัตโนมัติ"))
        self.b_auto.clicked.connect(lambda: self.auto_fill())
        prow.addWidget(self.b_use_panel)
        prow.addWidget(self.b_auto)
        form.addRow(tr("ผังอุปกรณ์"), prow)
        self.ed_desc = QPlainTextEdit()
        self.ed_desc.setFixedHeight(58)
        self.ed_desc.setPlaceholderText(tr("โจทย์ที่นักเรียนเห็น (หลายบรรทัดได้)"))
        form.addRow(tr("โจทย์"), self.ed_desc)
        self.lbl_io = QLabel()
        self.lbl_io.setWordWrap(True)
        self.lbl_io.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_io.setStyleSheet(f"color:{theme.TEXT_DIM};")
        form.addRow(tr("I/O บนผัง"), self.lbl_io)
        rv.addLayout(form)

        self.tabs = QTabWidget()
        # แท็บข้อตรวจ
        tc = QWidget()
        th = QHBoxLayout(tc)
        cbox = QVBoxLayout()
        cbox.addWidget(QLabel(tr("ข้อตรวจ (case)")))
        self.lst_cases = QListWidget()
        self.lst_cases.setMaximumWidth(260)
        self.lst_cases.currentRowChanged.connect(self._on_case)
        self.lst_cases.itemChanged.connect(self._on_case_renamed)
        cbox.addWidget(self.lst_cases, 1)
        cr = QHBoxLayout()
        self.b_case_add, self.b_case_del = _btn("➕"), _btn("✖")
        self.b_case_up, self.b_case_down = _btn("▲"), _btn("▼")
        self.b_case_add.clicked.connect(self.add_case)
        self.b_case_del.clicked.connect(self.remove_case)
        self.b_case_up.clicked.connect(lambda: self.move_case(-1))
        self.b_case_down.clicked.connect(lambda: self.move_case(1))
        for b in (self.b_case_add, self.b_case_del, self.b_case_up, self.b_case_down):
            cr.addWidget(b)
        cbox.addLayout(cr)
        hint = QLabel(tr("ทุกข้อเริ่มด้วย: คืนค่าพัก → ขั้นตอน reset → รอให้นิ่ง\nดับเบิลคลิกเพื่อเปลี่ยนชื่อข้อ"))
        hint.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        cbox.addWidget(hint)
        th.addLayout(cbox)
        self.steps = StepTable(xy_base)
        self.steps.changed.connect(self._on_steps_changed)
        self.builder = CondBuilder(xy_base)
        self.builder.changed.connect(self._on_builder_changed)
        self.steps.loaded.connect(self._builder_load)
        cv = QVBoxLayout()
        mode = QHBoxLayout()
        mode.addWidget(QLabel(tr("<b>เงื่อนไขของข้อนี้</b>")), 1)
        self.b_adv = _btn(tr("⌨ โหมดขั้นสูง"), tr("สลับเป็นตารางคำสั่ง (พิมพ์เอง)"))
        self.b_adv.setCheckable(True)
        self.b_adv.toggled.connect(lambda on: (self.mode_stack.setCurrentIndex(int(on)), on or self._builder_load()))
        mode.addWidget(self.b_adv)
        cv.addLayout(mode)
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self.builder)
        self.mode_stack.addWidget(self.steps)
        cv.addWidget(self.mode_stack, 1)
        th.addLayout(cv, 1)
        self.tabs.addTab(tc, tr("ข้อตรวจ"))
        # แท็บ reset / ค่าพัก
        tab_reset = QWidget()
        trv = QVBoxLayout(tab_reset)
        f2 = QFormLayout()
        self.ed_idle = latin_only(QLineEdit())
        self.ed_idle.setPlaceholderText("X0=0, X1=0")
        self.ed_idle.setToolTip(tr("ค่า input ตอนพัก — ตัวตรวจคืนค่านี้ก่อนเริ่มทุกข้อ"))
        self.sp_settle = QDoubleSpinBox()
        self.sp_settle.setRange(0, 10)
        self.sp_settle.setSingleStep(0.1)
        self.sp_settle.setSuffix(" s")
        f2.addRow(tr("ค่าพัก (idle)"), self.ed_idle)
        f2.addRow(tr("รอให้นิ่ง (settle)"), self.sp_settle)
        trv.addLayout(f2)
        trv.addWidget(QLabel(tr("ขั้นตอน reset (ทำก่อนทุกข้อ — ห้ามใช้ expect/hold)")))
        self.reset = StepTable(xy_base, allow_checks=False)
        self.reset.changed.connect(self._mark)
        trv.addWidget(self.reset, 1)
        self.tabs.addTab(tab_reset, tr("ค่าพัก / reset"))
        # แท็บหาจุดเสีย
        tf = QWidget()
        tfv = QVBoxLayout(tf)
        f3 = QFormLayout()
        self.sp_guess = QSpinBox()
        self.sp_guess.setRange(1, 10)
        f3.addRow(tr("ทายได้"), self.sp_guess)
        tfv.addLayout(f3)
        self.tbl_pool = QTableWidget(0, 2)
        self.tbl_pool.setHorizontalHeaderLabels([tr("อุปกรณ์ (ป้ายบนผัง)"), tr("อาการที่สุ่มได้ (คั่นด้วย ,)")])
        self.tbl_pool.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_pool.itemChanged.connect(lambda _i: self._mark())
        tfv.addWidget(self.tbl_pool, 1)
        pr = QHBoxLayout()
        self.b_pool_add = _btn(tr("➕ เพิ่มอุปกรณ์"))
        self.b_pool_all = _btn(tr("⚡ ใส่ทุกอุปกรณ์บนผัง"))
        self.b_pool_del = _btn(tr("✖ ลบ"))
        self.b_pool_add.clicked.connect(lambda: self._add_pool_row("", []))
        self.b_pool_all.clicked.connect(self.fill_pool_from_panel)
        self.b_pool_del.clicked.connect(lambda: (self.tbl_pool.removeRow(self.tbl_pool.currentRow()), self._mark()))
        for b in (self.b_pool_add, self.b_pool_all, self.b_pool_del):
            pr.addWidget(b)
        pr.addStretch(1)
        tfv.addLayout(pr)
        self.lbl_faults = QLabel()
        self.lbl_faults.setWordWrap(True)
        self.lbl_faults.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_faults.setStyleSheet(f"color:{theme.TEXT_DIM};")
        tfv.addWidget(self.lbl_faults)
        self.tabs.addTab(tf, tr("หาจุดเสีย"))
        vs = QSplitter(Qt.Vertical)                     # ลากเส้นแบ่งให้เงื่อนไขหรือ AI สูงขึ้นได้
        vs.setChildrenCollapsible(False)
        vs.setHandleWidth(8)
        vs.addWidget(self.tabs)
        self.ai_box = QTextBrowser()
        self.ai_box.setOpenLinks(False)
        self.ai_box.setMinimumHeight(60)
        self.ai_box.anchorClicked.connect(lambda u: self._ai_link(u.toString()))
        vs.addWidget(self.ai_box)
        vs.setStretchFactor(0, 1)
        vs.setSizes([600, 100])
        rv.addWidget(vs, 1)
        self._ai_timer = QTimer(self, singleShot=True, interval=600)
        self._ai_timer.timeout.connect(self.run_ai)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        rv.addWidget(self.lbl_status)
        br = QHBoxLayout()
        self.b_check = _btn(tr("✔ ตรวจความถูกต้อง"))
        self.b_save = _btn(tr("💾 บันทึก"))
        self.b_save.setObjectName("Primary")
        self.b_open = _btn(tr("📖 บันทึกแล้วเปิดด่านนี้"))
        self.b_try = _btn(tr("▶ บันทึกแล้วลองตรวจ"), tr("เปิดด่านนี้แล้วตรวจกับ PLC ที่เชื่อมอยู่ทันที"))
        self.b_try.clicked.connect(lambda: self.save() and self.try_requested.emit(self.runtime_id()))
        b_close = _btn(tr("ปิด"))
        self.b_check.clicked.connect(self.check)
        self.b_save.clicked.connect(self.save)
        self.b_open.clicked.connect(self.save_and_open)
        b_close.clicked.connect(self.close)
        br.addWidget(self.b_check)
        br.addStretch(1)
        br.addWidget(self.b_try)
        br.addWidget(self.b_open)
        br.addWidget(self.b_save)
        br.addWidget(b_close)
        rv.addLayout(br)
        split.addWidget(right)
        split.setSizes([300, 980])

        for w in (self.ed_id, self.ed_title, self.ed_idle):
            w.textEdited.connect(lambda _t: self._mark())
        self.ed_title.textEdited.connect(self._live_title)
        self.ed_desc.textChanged.connect(self._mark)
        self.sp_order.valueChanged.connect(lambda _v: self._mark())
        self.sp_settle.valueChanged.connect(lambda _v: self._mark())
        self.sp_guess.valueChanged.connect(lambda _v: self._mark())
        self.cb_panel.currentIndexChanged.connect(self._on_panel_changed)

        self.cb_room.activated.connect(lambda _i: self.set_room(self.cb_room.currentData()))
        self._fill_rooms()
        self.reload(select)

    # ================= ห้อง =================
    def runtime_id(self, lid: str | None = None) -> str:
        """รหัสที่หน้าต่างหลัก/คะแนนใช้ (มีรหัสห้องนำหน้า)."""
        lid = lid if lid is not None else (self.cur.id if self.cur else "")
        return self.room.level_id(lid) if self.room and lid else lid

    def _fill_rooms(self):
        self.cb_room.blockSignals(True)
        self.cb_room.clear()
        self.cb_room.addItem(tr("📚 ด่านมาตรฐาน"), "")
        for r in rooms.list_rooms(self.root):
            self.cb_room.addItem("🏠 " + r.name, r.key)
        self.cb_room.setCurrentIndex(max(0, self.cb_room.findData(self.room.key if self.room else "")))
        self.cb_room.blockSignals(False)
        for a in (self.a_room_ren, self.a_room_exp, self.a_room_del):
            a.setEnabled(self.room is not None)

    def set_room(self, key: str, select: str | None = None) -> bool:
        if self.cur is not None and self.dirty and not self._ask_discard():
            self._fill_rooms()
            return False
        self.dirty = False
        self.cur = None
        self.room = rooms.get(key, self.root) if key else None
        self.folder = self.room.path if self.room else self.root
        self._fill_rooms()
        self.reload(select)
        return True

    def _ask_name(self, title: str, text: str = "") -> str:
        t, ok = QInputDialog.getText(self, title, tr("ชื่อห้อง"), text=text)
        return t.strip() if ok else ""

    def create_room(self, name: str = ""):
        name = name or self._ask_name(tr("สร้างห้องด่านใหม่"), tr("ด่านของฉัน"))
        if not name:
            return None
        try:
            r = rooms.create(name, self.root)
        except (rooms.RoomError, OSError) as e:
            QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
            return None
        self.set_room(r.key)
        self.rooms_changed.emit()
        return self.room

    def rename_room(self, name: str = ""):
        if self.room is None:
            return
        name = name or self._ask_name(tr("เปลี่ยนชื่อห้อง"), self.room.name)
        if name:
            try:
                self.room = rooms.rename(self.room, name, self.root)
            except (rooms.RoomError, OSError) as e:
                QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
            self._fill_rooms()
            self.rooms_changed.emit()

    def delete_room(self):
        if self.room is None or QMessageBox.question(
                self, tr("ลบห้อง"), tr("ลบห้อง '{0}' พร้อมทุกด่านในห้อง?\nไฟล์จะถูกย้ายไป levels/_trash (กู้คืนได้)", self.room.name),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            rooms.delete(self.room, self.root)
        except OSError as e:
            QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
            return
        self.dirty = False
        self.set_room("")
        self.rooms_changed.emit()

    def export_room(self, path: str = ""):
        if self.room is None or (self.dirty and self.save() is None):
            return None
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("ส่งออกห้อง"), f"{self.room.name}.plcroom", tr("ห้องด่าน (*.plcroom)"))
        if not path:
            return None
        try:
            out = rooms.export(self.room, Path(path).with_suffix(".plcroom"))
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
            return None
        self.lbl_status.setText(tr("📤 ส่งออกห้องแล้ว: {0}", out.name))
        return out

    def import_room(self, path: str = ""):
        if self.cur is not None and self.dirty and not self._ask_discard():
            return None
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("นำเข้าห้อง"), "", tr("ห้องด่าน (*.plcroom)"))
        if not path:
            return None
        try:
            r = rooms.import_room(Path(path), self.root, self.xy_base)
        except (rooms.RoomError, OSError) as e:
            QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
            return None
        self.set_room(r.key)
        self.rooms_changed.emit()
        return r

    def _need_room(self) -> bool:
        """ต้องอยู่ในห้องของผู้ใช้ก่อนสร้างด่าน — ยังไม่มีห้อง = สร้างให้."""
        if self.room is not None:
            return True
        have = rooms.list_rooms(self.root)
        return self.set_room(have[0].key) if have else self.create_room() is not None

    def create_level(self):
        if self.cur is not None and self.dirty and not self._ask_discard():
            return None
        if not self._need_room():
            return None
        panel = ""
        if self.current_panel is not None:
            doc, name = self.current_panel()
            if doc is not None and doc.devices:
                before = {p.name for p in self.folder.glob("*.plcpanel")}
                panel = rooms.add_panel(self.room, doc, name)
        w = LevelWizard(self.folder, self.drafts, self.xy_base, panel, self)
        if w.exec() != QDialog.Accepted or w.draft is None:
            if panel and panel not in before:
                (self.folder / panel).unlink(missing_ok=True)       # ยกเลิก = ไม่ทิ้งผังค้างในห้อง
            return None
        w.draft.id = rooms.new_id(self.room, w.draft.id)
        self.add_draft(w.draft)
        return w.draft

    def create_hunt(self):
        if self._need_room():
            self.new_level(True)

    def copy_to_room(self):
        d = self.cur
        if d is None or d.path is None:
            return None
        src = self.folder
        have = rooms.list_rooms(self.root)
        r = self.room or (have[0] if have else None)
        if r is None:
            name = self._ask_name(tr("สร้างห้องด่านใหม่"), tr("ด่านของฉัน"))
            if not name:
                return None
            try:
                r = rooms.create(name, self.root)
            except (rooms.RoomError, OSError) as e:
                QMessageBox.warning(self, tr("ห้องด่าน"), str(e))
                return None
        new = rooms.copy_level(d, src, r)
        self.set_room(r.key, new.id)
        self.rooms_changed.emit()
        return new

    def use_current_panel(self):
        if self.room is None or self.cur is None or self.current_panel is None:
            return
        doc, name = self.current_panel()
        fn = rooms.add_panel(self.room, doc, name)
        if self.cb_panel.findData(fn) < 0:
            self.cb_panel.addItem(fn, fn)
        self.cb_panel.setCurrentIndex(self.cb_panel.findData(fn))

    def auto_fill(self):
        d = self.collect()
        if d is None:
            return
        C.auto_setup(d, self._devices, self.xy_base)
        self.ed_idle.setText(E.idle_to_text(d.idle))
        self.reset.set_steps(d.reset)
        self._mark()
        self.lbl_status.setText(tr("✨ เติมค่าพัก: {0}", E.idle_to_text(d.idle)))

    def locked(self) -> bool:
        return bool(self.lock_standard and self.room is None and self.cur is not None
                    and E.is_standard(self.cur.path, self.root))

    # ================= เงื่อนไขแบบประโยค =================
    def _builder_load(self):
        if not self._from_builder:
            self.builder.load(self.steps.steps())

    def _on_builder_changed(self):
        self._from_builder = True
        try:
            self.steps.set_steps(self.builder.steps())
        finally:
            self._from_builder = False
        self._on_steps_changed()

    # ================= AI =================
    def run_ai(self):
        """อ่านเงื่อนไขที่กำลังแก้ → บอกว่าเข้าใจว่าอะไร แล้วเรียนรู้จากการจำลองในเบื้องหลัง."""
        self._stop_ai()
        self._ai_profile = self._ai_result = None
        self._ai_tips = []
        d = self.cur
        if d is None or d.hunt:
            self.ai_box.setHtml("")
            return
        self._store_case()
        d = copy.deepcopy(d)
        try:
            d.settle, d.reset = round(self.sp_settle.value(), 3), self.reset.steps()
            d.idle = E.text_to_idle(self.ed_idle.text(), self.xy_base)
            lv = d.build(self.folder, self.xy_base)
        except (ValueError, TypeError) as e:
            self.ai_box.setHtml(tr("<b>🧠 AI</b> — ยังอ่านเงื่อนไขไม่ได้: {0}", html.escape(str(e))))
            return
        lv.id = self.runtime_id(self.ed_id.text().strip())
        p = self._ai_profile = spec.analyze_spec(lv, self._devices, self.xy_base)
        self._ai_tips = sorted(p.suggestions, key=lambda s: -self.memory.tip_weight(s.key))
        m = self.memory.model(lv.id, p.hash)
        self._show_ai(m)
        if m is None:
            w = self._ai = LearnWorker(lv, p, self.xy_base, self)
            w.done.connect(self._ai_done)
            w.finished.connect(self._ai_ended)
            w.start()
        else:
            self._ai_result = (lv.id, m)

    def _stop_ai(self):
        w, self._ai = self._ai, None
        if w is not None:
            w.cancelled = True
            self._old_ai.append(w)

    def _ai_ended(self):
        for w in [w for w in self._old_ai if w.isFinished()]:
            self._old_ai.remove(w)
            w.deleteLater()

    def _ai_done(self, w, m):
        if w is not self._ai:
            return
        self._ai = None
        self._old_ai.append(w)
        self._ai_result = (w.level.id, m)
        if not self.dirty:
            self._remember()
        self._show_ai(m)

    def _remember(self):
        if self._ai_result is not None and self._ai_result[1].status in ("ok", "unknown", "physics"):
            self.memory.store(*self._ai_result)

    def _show_ai(self, m):
        p = self._ai_profile
        if p is None:
            return
        esc = html.escape
        out = [tr("<b>🧠 AI เข้าใจงานนี้ว่า</b>")]
        facts = spec.summary_lines(p)
        out += [f"• {esc(x)}" for x in facts] or [tr("• ยังสรุปไม่ได้ — เพิ่มเงื่อนไขอีก")]
        for i in p.issues:
            col = {"error": theme.DANGER, "warn": theme.WARN}.get(i.level, theme.TEXT_DIM)
            out.append(f"<span style='color:{col}'>⚠ {esc(i.text)}</span>")
        lock = self.locked()
        for n, s in enumerate(self._ai_tips):
            links = f" <a href='add:{n}' style='color:{theme.SUCCESS}'>{tr('[เพิ่มข้อนี้]')}</a>" if s.case is not None and not lock else ""
            if not lock:
                links += f" <a href='no:{n}' style='color:{theme.TEXT_DIM}'>{tr('[ไม่ต้อง]')}</a>"
            out.append(f"💡 {esc(s.text)}{links}")
        if m is None:
            out.append(tr("<i>กำลังเรียนรู้จากการจำลองเงื่อนไข…</i>"))
        else:
            out += [f"<span style='color:{theme.ACCENT2}'>🎓 {esc(x)}</span>" for x in learn.model_lines(m, p)]
        out.append(f"<a href='clear:0' style='color:{theme.TEXT_DIM}'>{tr('ล้างสิ่งที่ AI จำไว้ทั้งหมด')}</a>")
        self.ai_box.setHtml("<br>".join(out))

    def _ai_link(self, url: str):
        act, _, n = url.partition(":")
        if act == "clear":
            if QMessageBox.question(self, tr("ล้างความจำ AI"), tr("ล้างทุกอย่างที่ AI เรียนรู้ไว้ในเครื่องนี้?\n(คะแนนและด่านไม่ถูกลบ)"),
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.memory.clear()
                self.run_ai()
            return
        if self.cur is None or not n.isdigit() or int(n) >= len(self._ai_tips) or self.locked():
            return
        s = self._ai_tips.pop(int(n))
        self.memory.tip(s.key, act == "add")
        if act == "add" and s.case is not None:
            self._store_case()
            self.cur.cases.append(copy.deepcopy(s.case))
            self.lst_cases.blockSignals(True)
            self._case_item(s.case.name)
            self.lst_cases.blockSignals(False)
            self._case_i = -1
            self.lst_cases.setCurrentRow(len(self.cur.cases) - 1)
            self._mark()
        else:
            self._show_ai(self._ai_result[1] if self._ai_result else None)

    # ================= รายการ =================
    def reload(self, select: str | None = None):
        self.drafts = E.load_drafts(self.folder)
        self._fill_list()
        ids = [d.id for d in self.drafts]
        row = ids.index(select) if select in ids else (0 if ids else -1)
        if self.lst.currentRow() == row:         # _fill_list คืนแถวเดิมแบบไม่ส่งสัญญาณ (สลับห้อง = คนละด่าน)
            self._on_pick(row)
        else:
            self.lst.setCurrentRow(row)

    def _fill_list(self):
        self.lst.blockSignals(True)
        cur = self.lst.currentRow()
        self.lst.clear()
        for d in self.drafts:
            it = QListWidgetItem(("🔍 " if d.hunt else "") + d.title + ("" if d.path else tr("  (ยังไม่บันทึก)")))
            it.setToolTip(f"{d.id}.yaml")
            self.lst.addItem(it)
        self.lst.setCurrentRow(cur)
        self.lst.blockSignals(False)

    def _live_title(self, text: str):
        it = self.lst.currentItem()
        if it is not None and self.cur is not None:
            it.setText(("🔍 " if self.cur.hunt else "") + (text.strip() or tr("(ไม่มีชื่อ)")) + "  •")

    def _on_pick(self, row: int):
        if self._loading:
            return
        if self.cur is not None and self.dirty and not self._ask_discard():
            self.lst.blockSignals(True)
            self.lst.setCurrentRow(self.drafts.index(self.cur) if self.cur in self.drafts else -1)
            self.lst.blockSignals(False)
            return
        self._load(self.drafts[row] if 0 <= row < len(self.drafts) else None)

    def _ask_discard(self) -> bool:
        r = QMessageBox.question(self, tr("ยังไม่ได้บันทึก"), tr("ด่าน '{0}' มีการแก้ไขที่ยังไม่บันทึก\nทิ้งการแก้ไข?", self.cur.title),
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if r != QMessageBox.Discard:
            return False
        if self.cur.path is None:                     # ด่านใหม่ที่ไม่บันทึก → เอาออกจากรายการ
            self.drafts.remove(self.cur)
        else:
            i = self.drafts.index(self.cur)
            self.drafts[i] = E.LevelDraft.load(self.cur.path)
        self.dirty = False
        self.cur = None
        self._fill_list()
        return True

    # ================= โหลด / เก็บฟอร์ม =================
    def _load(self, d: E.LevelDraft | None):
        self._loading = True
        self.cur = d
        on = d is not None
        for w in (self.ed_id, self.sp_order, self.ed_title, self.cb_panel, self.ed_desc, self.tabs,
                  self.b_save, self.b_open, self.b_check, self.b_dup, self.b_del):
            w.setEnabled(on)
        lock = self.locked()
        for w in (self.ed_id, self.sp_order, self.ed_title, self.cb_panel, self.ed_desc, self.b_save, self.b_open, self.b_try,
                  self.b_del, self.b_dup, self.b_auto, self.builder, self.steps, self.reset, self.ed_idle, self.sp_settle,
                  self.b_case_add, self.b_case_del, self.b_case_up, self.b_case_down, self.tbl_pool, self.sp_guess,
                  self.b_pool_add, self.b_pool_all, self.b_pool_del):
            w.setEnabled(on and not lock)
        self.lock_bar.setVisible(lock)
        self.b_use_panel.setVisible(self.room is not None)
        self.b_copy.setVisible(self.room is None)
        self.b_copy.setEnabled(on and d.path is not None)
        self._ai_timer.start()
        if d is None:
            self._stop_ai()
            self.ai_box.setHtml("")
            self._loading = False
            return
        self.ed_id.setText(d.id)
        self.sp_order.setValue(d.order)
        self.ed_title.setText(d.title)
        self.ed_desc.setPlainText(d.desc)
        self.cb_panel.blockSignals(True)
        self.cb_panel.clear()
        self.cb_panel.addItem(tr("— ไม่มีผัง —"), "")
        for text, val in E.panel_choices(self.folder):
            self.cb_panel.addItem(text, val)
        i = self.cb_panel.findData(d.panel)
        if i < 0 and d.panel:
            self.cb_panel.addItem(tr("{0} (ไม่พบไฟล์)", d.panel), d.panel)
            i = self.cb_panel.count() - 1
        self.cb_panel.setCurrentIndex(max(0, i))
        self.cb_panel.blockSignals(False)
        self.ed_idle.setText(E.idle_to_text(d.idle))
        self.sp_settle.setValue(d.settle)
        self.reset.set_steps(d.reset)
        self.lst_cases.blockSignals(True)
        self.lst_cases.clear()
        for c in d.cases:
            self._case_item(c.name)
        self.lst_cases.blockSignals(False)
        self._case_i = -1
        self.sp_guess.setValue(d.guesses)
        self.tbl_pool.blockSignals(True)
        self.tbl_pool.setRowCount(0)
        for dev, codes in d.pool:
            self._add_pool_row(dev, codes, mark=False)
        self.tbl_pool.blockSignals(False)
        self.tabs.setTabEnabled(0, not d.hunt)
        self.tabs.setTabEnabled(1, not d.hunt)
        self.tabs.setTabEnabled(2, d.hunt)
        self.tabs.setCurrentIndex(2 if d.hunt else 0)
        self._refresh_panel_info()
        self._loading = False
        if d.cases:
            self.lst_cases.setCurrentRow(0)
        else:
            self.steps.set_steps([])
        self.dirty = False
        self.lbl_status.setText(f"<span style='color:{theme.TEXT_DIM}'>{d.id}.yaml · "
                                + (tr("ด่านหาจุดเสีย") if d.hunt else tr("{0} ข้อ", len(d.cases)))
                                + (tr(" · 🔒 ด่านมาตรฐาน แก้ไม่ได้ — กด 📋 ทำสำเนาไปห้องของฉัน") if lock else "") + "</span>")

    def _case_item(self, name):
        it = QListWidgetItem(name)
        if not self.locked():
            it.setFlags(it.flags() | Qt.ItemIsEditable)
        self.lst_cases.addItem(it)

    def collect(self) -> E.LevelDraft | None:
        """เก็บค่าจากฟอร์มลงแบบร่างปัจจุบัน (คืน None ถ้าค่าพักผิดรูปแบบ — แสดงในสถานะ)."""
        d = self.cur
        if d is None:
            return None
        self._store_case()
        d.id = self.ed_id.text().strip()
        d.order = self.sp_order.value()
        d.title = self.ed_title.text().strip()
        d.desc = self.ed_desc.toPlainText().strip()
        d.panel = self.cb_panel.currentData() or ""
        d.settle = round(self.sp_settle.value(), 3)
        d.reset = self.reset.steps()
        d.guesses = self.sp_guess.value()
        d.pool = []
        for r in range(self.tbl_pool.rowCount()):
            dev = self._pool_text(r, 0)
            codes = [c.strip().lower() for c in self._pool_text(r, 1).split(",") if c.strip()]
            if dev or codes:
                d.pool.append((dev, codes))
        try:
            d.idle = E.text_to_idle(self.ed_idle.text(), self.xy_base)
        except ValueError as e:
            self._status([str(e)])
            return None
        return d

    def _pool_text(self, r, c):
        w = self.tbl_pool.cellWidget(r, c)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        it = self.tbl_pool.item(r, c)
        return it.text().strip() if it else ""

    # ================= ข้อตรวจ =================
    def _store_case(self):
        if self.cur is not None and 0 <= self._case_i < len(self.cur.cases):
            self.cur.cases[self._case_i].steps = self.steps.steps()

    def _on_case(self, row: int):
        if self._loading:
            return
        self._store_case()
        self._case_i = row
        if self.cur is not None and 0 <= row < len(self.cur.cases):
            self.steps.setEnabled(not self.locked())
            self.builder.setEnabled(not self.locked())
            self.steps.set_steps(self.cur.cases[row].steps)
        else:
            self.steps.set_steps([])
            self.steps.setEnabled(False)
            self.builder.setEnabled(False)

    def _on_case_renamed(self, it):
        r = self.lst_cases.row(it)
        if self.cur is not None and 0 <= r < len(self.cur.cases):
            self.cur.cases[r].name = it.text().strip() or tr("ข้อ {0}", r + 1)
            self._mark()

    def add_case(self):
        if self.cur is None:
            return
        self._store_case()
        n = len(self.cur.cases) + 1
        self.cur.cases.append(E.CaseRow(tr("ข้อ {0}", n), [E.StepRow("pulse", "X0 0.3"),
                                                      E.StepRow("expect", "Y0 = 1 within 0.5")]))
        self.lst_cases.blockSignals(True)
        self._case_item(tr("ข้อ {0}", n))
        self.lst_cases.blockSignals(False)
        self._case_i = -1
        self.lst_cases.setCurrentRow(n - 1)
        self._mark()

    def remove_case(self):
        r = self.lst_cases.currentRow()
        if self.cur is None or r < 0:
            return
        self.cur.cases.pop(r)
        self._case_i = -1
        self.lst_cases.blockSignals(True)
        self.lst_cases.takeItem(r)
        self.lst_cases.blockSignals(False)
        self.lst_cases.setCurrentRow(min(r, len(self.cur.cases) - 1))
        self._on_case(self.lst_cases.currentRow())
        self._mark()

    def move_case(self, delta: int):
        r = self.lst_cases.currentRow()
        n = r + delta
        if self.cur is None or r < 0 or not 0 <= n < len(self.cur.cases):
            return
        self._store_case()
        cs = self.cur.cases
        cs[r], cs[n] = cs[n], cs[r]
        self.lst_cases.blockSignals(True)
        self.lst_cases.clear()
        for c in cs:
            self._case_item(c.name)
        self.lst_cases.blockSignals(False)
        self._case_i = -1
        self.lst_cases.setCurrentRow(n)
        self._mark()

    def _on_steps_changed(self):
        self._store_case()
        self._mark()

    # ================= ผัง / หาจุดเสีย =================
    def _on_panel_changed(self, _i):
        if self._loading:
            return
        self._refresh_panel_info()
        self._mark()

    def _refresh_panel_info(self):
        path = E.resolve_panel(self.cb_panel.currentData() or "", self.folder)
        rows, self._fault_map = panel_info(path, self.xy_base)
        self._devices = _load_devices(path)
        self.builder.set_io(rows)
        if not rows:
            self.lbl_io.setText(tr("— (เลือกผังเพื่อดู address ที่ใช้ได้)"))
        else:
            self.lbl_io.setText("  ·  ".join(f"<b>{r.address}</b> {r.label or r.device}"
                                             + (f" ({r.role})" if r.role else "") for r in rows))
        if self._fault_map:
            self.lbl_faults.setText(tr("อาการที่ใส่ได้: ") + "<br>".join(
                f"<b>{lab}</b>: " + ", ".join(f"{c} = {t}" for c, t in fs.items())
                for lab, fs in self._fault_map.items()))
        else:
            self.lbl_faults.setText(tr("ผังนี้ไม่มีอุปกรณ์ที่ใส่ความผิดปกติได้"))
        for r in range(self.tbl_pool.rowCount()):
            self._pool_combo(r, self._pool_text(r, 0))

    def _pool_combo(self, r, current):
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItems(sorted(self._fault_map))
        cb.setCurrentText(current)
        cb.currentTextChanged.connect(lambda _t: self._mark())
        self.tbl_pool.setCellWidget(r, 0, cb)

    def _add_pool_row(self, dev, codes, mark=True):
        r = self.tbl_pool.rowCount()
        self.tbl_pool.insertRow(r)
        self._pool_combo(r, dev)
        self.tbl_pool.setItem(r, 1, QTableWidgetItem(", ".join(codes)))
        if mark:
            self._mark()

    def fill_pool_from_panel(self):
        self.tbl_pool.setRowCount(0)
        for lab, fs in self._fault_map.items():
            self._add_pool_row(lab, list(fs), mark=False)
        self._mark()

    # ================= ปุ่ม =================
    def new_level(self, hunt: bool):
        if self.cur is not None and self.dirty and not self._ask_discard():
            return
        d = E.new_draft(self.drafts, hunt)
        if hunt:
            d.panel = "14_fault_find.plcpanel" if (self.folder / "14_fault_find.plcpanel").exists() else ""
            d.desc = tr("กด ▶ เริ่มหาจุดเสีย → สังเกตอาการ → คลิกขวาอุปกรณ์ที่คิดว่าเสีย")
        else:
            d.panel = "01_self_hold.plcpanel" if (self.folder / "01_self_hold.plcpanel").exists() else ""
        self.drafts.append(d)
        self._fill_list()
        self._loading = False
        self.lst.setCurrentRow(len(self.drafts) - 1)
        if hunt:
            self.fill_pool_from_panel()
        self.dirty = True

    def add_draft(self, d: E.LevelDraft) -> bool:
        """เพิ่มแบบร่างจากภายนอก (เช่น สร้างจากการกดที่บันทึก) — ยังไม่บันทึกจนครูกดบันทึก."""
        if self.cur is not None and self.dirty and not self._ask_discard():
            return False
        self.drafts.append(d)
        self._fill_list()
        self.lst.setCurrentRow(len(self.drafts) - 1)
        self.dirty = True
        self.check()
        return True

    def duplicate(self):
        d = self.collect()
        if d is None:
            return
        c = E.duplicate(d, self.drafts)
        if self.dirty and not self._ask_discard():
            return
        self.drafts.append(c)
        self._fill_list()
        self.lst.setCurrentRow(len(self.drafts) - 1)
        self.dirty = True

    def delete(self):
        d = self.cur
        if d is None or self.locked():
            return
        if QMessageBox.question(self, tr("ลบด่าน"), tr("ลบ '{0}'?\nไฟล์จะถูกย้ายไป levels/_trash (กู้คืนได้)", d.title),
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.delete_current()

    def delete_current(self):
        d = self.cur
        if d.path is not None and Path(d.path).exists():
            E.trash(Path(d.path), self.folder)
        self.drafts.remove(d)
        self.cur = None
        self.dirty = False
        self._fill_list()
        self.lst.setCurrentRow(min(self.lst.count() - 1, 0))
        self._load(self.drafts[self.lst.currentRow()] if self.drafts else None)
        self.saved.emit("")

    def check(self) -> list[str]:
        d = self.collect()
        if d is None:
            return [tr("ค่าพักไม่ถูกต้อง")]
        others = [x.id for x in self.drafts if x is not d]
        probs = d.problems(self.folder, self.xy_base, others)
        if not probs and d.hunt:
            probs = self._hunt_problems(d)
        self._status(probs, ok_text="" if probs else self._summary(d))
        return probs

    def _hunt_problems(self, d) -> list[str]:
        out = []
        for dev, codes in d.pool:
            if dev not in self._fault_map:
                out.append(tr("หาจุดเสีย: ไม่มีอุปกรณ์ป้าย '{0}' บนผัง", dev))
                continue
            bad = [c for c in codes if c not in self._fault_map[dev]]
            if bad:
                out.append(tr("หาจุดเสีย: '{0}' ไม่มีอาการ {1} (ใช้ได้: {2})", dev, ', '.join(bad), ', '.join(self._fault_map[dev])))
        return out

    def _summary(self, d) -> str:
        if d.hunt:
            return tr("✔ ถูกต้อง — หาจุดเสีย {0} แบบ · ทายได้ {1} ครั้ง", sum(len(c) for _, c in d.pool), d.guesses)
        lv = d.build(self.folder, self.xy_base)
        return tr("✔ ถูกต้อง — {0} ข้อ · นับคะแนน {1} จุด", len(lv.cases), lv.checks)

    def _status(self, probs, ok_text=""):
        if probs:
            self.lbl_status.setText(tr("<span style='color:{0}'><b>ยังบันทึกไม่ได้:</b><br>", theme.DANGER)
                                    + "<br>".join(f"• {p}" for p in probs[:8])
                                    + (tr("<br>… อีก {0} ข้อ", len(probs) - 8) if len(probs) > 8 else "") + "</span>")
        else:
            self.lbl_status.setText(f"<span style='color:{theme.SUCCESS}'>{ok_text}</span>")

    def save(self) -> Path | None:
        if self.cur is None or self.locked():
            return None
        probs = self.check()
        if probs:
            return None
        d = self.cur
        old = d.path
        path = d.save(self.folder)
        self.dirty = False
        self._fill_list()
        self.lbl_status.setText(self.lbl_status.text() + tr("<br><span style='color:{0}'>💾 บันทึก {1}", theme.SUCCESS, path.name) + (tr(" (ไฟล์เดิม {0} ย้ายไป _trash)", Path(old).name)
                                                  if old and Path(old).name != path.name else "") + "</span>")
        self._remember()
        self.saved.emit(self.runtime_id())
        return path

    def save_and_open(self):
        if self.save():
            self.open_requested.emit(self.runtime_id())

    def _mark(self):
        if not self._loading and self.cur is not None:
            self.dirty = True
            self._ai_timer.start()

    def reject(self):
        if self._closing:        # QDialog.closeEvent เรียก reject() เองเพื่อซ่อนหน้าต่าง
            return super().reject()
        self.close()             # Esc = ปิดแบบถามก่อนทิ้งการแก้ไข (QDialog ปกติปิดทันที ข้อความที่พิมพ์หาย)

    def closeEvent(self, e):
        if self.cur is not None and self.dirty and not self._ask_discard():
            e.ignore()
            return
        self.stop_threads()
        self._closing = True
        super().closeEvent(e)
        self._closing = False

    def hide_for_exam(self):
        """เริ่มสอบ: ซ่อนไว้ (งานที่ยังไม่บันทึกอยู่ครบ เปิดต่อได้หลังสอบ)."""
        self.stop_threads()
        self.hide()

    def stop_threads(self):
        """รอ thread ของ AI จบก่อน widget ถูกลบ."""
        self._ai_timer.stop()
        self._stop_ai()
        for w in list(self._old_ai):
            w.wait(8000)
