"""ตัวแก้ไขด่านของครู: สร้าง/แก้/ทำสำเนา/ลบด่าน โดยไม่ต้องเขียน YAML เอง.

ซ้าย = รายการด่าน · ขวา = ข้อมูลด่าน + แท็บ ข้อตรวจ / reset / หาจุดเสีย
ทุกขั้นตอนตรวจความถูกต้องทันที (ช่องแดง + tooltip) และตรวจทั้งด่านด้วยตัวโหลดจริงก่อนบันทึก
"""
from __future__ import annotations

from ..i18n import tr

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..levels import editor as E
from ..levels.engine import LEVEL_DIR
from ..panel import PanelDoc
from ..panel import iolist
from . import theme

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
    if tip:
        b.setToolTip(tip)
    return b


class StepTable(QWidget):
    """ตารางขั้นตอน: คำสั่ง | พารามิเตอร์ | ข้อความผลตรวจ | คำใบ้."""
    changed = Signal()

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

    def steps(self) -> list[E.StepRow]:
        out = []
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 0)
            out.append(E.StepRow(cb.currentText(), self._txt(r, 1), self._txt(r, 2), self._txt(r, 3)))
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
        op = self.table.cellWidget(r, 0).currentText()
        th, ex = E.OP_HELP.get(op, ("", ""))
        self.lbl_help.setText(tr("<b>{0}</b> — {1} · ตัวอย่าง: <code>{2}</code>  ·  ตัวเปรียบเทียบ = != >= <= > < · หลายเงื่อนไขใช้ and", op, th, ex))


class LevelEditorDialog(QDialog):
    saved = Signal(str)          # id ของด่านที่บันทึก
    open_requested = Signal(str)

    def __init__(self, parent=None, xy_base: int = 8, folder: Path = LEVEL_DIR, select: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("✏ ตัวแก้ไขด่าน (ครู)"))
        self.resize(1280, 800)
        self.xy_base = xy_base
        self.folder = Path(folder)
        self.drafts: list[E.LevelDraft] = []
        self.cur: E.LevelDraft | None = None
        self.dirty = False
        self._loading = False
        self._case_i = -1
        self._fault_map: dict[str, dict[str, str]] = {}

        root = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ----- ซ้าย: รายการด่าน -----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr("<b>ด่านทั้งหมด</b> (levels/*.yaml)")))
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._on_pick)
        lv.addWidget(self.lst, 1)
        g = QHBoxLayout()
        self.b_new = _btn(tr("📄 ใหม่"), tr("ด่านตรวจผล I/O ใหม่"))
        self.b_new_hunt = _btn(tr("🔍 หาจุดเสียใหม่"))
        self.b_dup = _btn(tr("⧉ ทำสำเนา"))
        self.b_del = _btn(tr("🗑 ลบ"), tr("ย้ายไป levels/_trash (กู้คืนได้)"))
        self.b_new.clicked.connect(lambda: self.new_level(False))
        self.b_new_hunt.clicked.connect(lambda: self.new_level(True))
        self.b_dup.clicked.connect(self.duplicate)
        self.b_del.clicked.connect(self.delete)
        for b in (self.b_new, self.b_new_hunt):
            g.addWidget(b)
        lv.addLayout(g)
        g2 = QHBoxLayout()
        g2.addWidget(self.b_dup)
        g2.addWidget(self.b_del)
        lv.addLayout(g2)
        split.addWidget(left)

        # ----- ขวา: ฟอร์ม -----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        form = QFormLayout()
        self.ed_id = QLineEdit()
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
        form.addRow(tr("ผังอุปกรณ์"), self.cb_panel)
        self.ed_desc = QPlainTextEdit()
        self.ed_desc.setFixedHeight(70)
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
        th.addWidget(self.steps, 1)
        self.tabs.addTab(tc, tr("ข้อตรวจ"))
        # แท็บ reset / ค่าพัก
        tab_reset = QWidget()
        trv = QVBoxLayout(tab_reset)
        f2 = QFormLayout()
        self.ed_idle = QLineEdit()
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
        rv.addWidget(self.tabs, 1)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        rv.addWidget(self.lbl_status)
        br = QHBoxLayout()
        self.b_check = _btn(tr("✔ ตรวจความถูกต้อง"))
        self.b_save = _btn(tr("💾 บันทึก"))
        self.b_save.setObjectName("Primary")
        self.b_open = _btn(tr("📖 บันทึกแล้วเปิดด่านนี้"))
        b_close = _btn(tr("ปิด"))
        self.b_check.clicked.connect(self.check)
        self.b_save.clicked.connect(self.save)
        self.b_open.clicked.connect(self.save_and_open)
        b_close.clicked.connect(self.close)
        br.addWidget(self.b_check)
        br.addStretch(1)
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

        self.reload(select)

    # ================= รายการ =================
    def reload(self, select: str | None = None):
        self.drafts = E.load_drafts(self.folder)
        self._fill_list()
        ids = [d.id for d in self.drafts]
        self.lst.setCurrentRow(ids.index(select) if select in ids else (0 if ids else -1))

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
        if d is None:
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
                                + (tr("ด่านหาจุดเสีย") if d.hunt else tr("{0} ข้อ", len(d.cases))) + "</span>")

    def _case_item(self, name):
        it = QListWidgetItem(name)
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
            self.steps.setEnabled(True)
            self.steps.set_steps(self.cur.cases[row].steps)
        else:
            self.steps.set_steps([])
            self.steps.setEnabled(False)

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
        if d is None:
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
        self.saved.emit(d.id)
        return path

    def save_and_open(self):
        if self.save():
            self.open_requested.emit(self.cur.id)

    def _mark(self):
        if not self._loading and self.cur is not None:
            self.dirty = True

    def closeEvent(self, e):
        if self.cur is not None and self.dirty and not self._ask_discard():
            e.ignore()
            return
        super().closeEvent(e)
