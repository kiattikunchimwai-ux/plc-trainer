"""แผง I/O LIST: ตาราง address ทั้งผัง + ค่าปัจจุบันสด (Watch) + Export + จัด address อัตโนมัติ."""
from __future__ import annotations

from ..i18n import tr, tr_data

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMenu, QPushButton, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from ..panel import iolist
from . import state, theme
from .panel.items import InputItem

COLS = ["Address", tr("ทิศทาง"), tr("ชื่อ"), tr("อุปกรณ์ / หน้าที่"), "NO/NC", tr("ค่า")]
VAL = 5


class AssignDialog(QDialog):
    """แสดงตาราง address เดิม → ใหม่ ก่อนยืนยัน."""

    def __init__(self, view, changes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("จัด Address อัตโนมัติ"))
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("เรียงอุปกรณ์จากบนลงล่าง ซ้ายไปขวา แล้วให้เลข Input = X0, X1… และ Output = Y0, Y1…\n"
                             "Output ที่ใช้ address เดียวกันอยู่แล้วจะยังใช้ร่วมกัน · ไม่เปลี่ยน M / D / T / C\n"
                             "กด Ctrl+Z เพื่อย้อนกลับได้")))
        rows = []
        for i, props in changes.items():
            it = view.items_by_id[i]
            for prop, new in props.items():
                slot = it.info.slot(prop)
                rows.append((it.shown_label or it.info.name, slot.label if prop != "address" else it.info.main_label,
                             str(it.spec.props.get(prop, "")), new))
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels([tr("อุปกรณ์"), tr("ช่อง"), tr("เดิม"), tr("ใหม่")])
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if c == 3:
                    cell.setForeground(QColor("#5EE36A"))
                t.setItem(r, c, cell)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("เปลี่ยน {0} ช่อง", len(rows)))
        bb.button(QDialogButtonBox.Cancel).setText(tr("ยกเลิก"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class IOListPanel(QWidget):
    message = Signal(str)

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.rows: list[iolist.IORow] = []
        self._values: dict[str, int] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.btn_assign = QPushButton(tr("🔢 จัด Address อัตโนมัติ"))
        self.btn_assign.setToolTip(tr("เรียงเลข X / Y ใหม่ตามตำแหน่งบนผัง (ย้อนกลับได้ด้วย Ctrl+Z)"))
        self.btn_assign.clicked.connect(self.auto_assign)
        exp = QToolButton()
        exp.setText("⇩ Export")
        exp.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(exp)
        m.addAction(tr("ตาราง I/O (CSV สำหรับ Excel)…"), self.export_csv)
        m.addAction(tr("Device Comment สำหรับ GX Works3 (CSV)…"), self.export_gx)
        m.addAction(tr("พิมพ์ / PDF…"), self.export_pdf)
        exp.setMenu(m)
        bar.addWidget(self.btn_assign)
        bar.addStretch(1)
        bar.addWidget(exp)
        lay.addLayout(bar)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        hh = self.table.horizontalHeader()
        for c in range(len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.cellClicked.connect(self._clicked)
        self.table.cellDoubleClicked.connect(self._double)
        lay.addWidget(self.table, 1)
        tip = QLabel(tr("คลิกแถว = ชี้อุปกรณ์บนผัง · ดับเบิลคลิกแถว Input = สลับ ON/OFF"))
        tip.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        lay.addWidget(tip)
        view.changed.connect(self.rebuild)
        self.rebuild()

    # ---------- ตาราง ----------
    def rebuild(self):
        specs = [it.spec for it in self.view.items_by_id.values()]
        self.rows = iolist.rows(specs, self.view.xy_base)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            what = row.device if row.prop == "address" else f"{row.device} · {row.slot}"
            vals = [row.address, row.direction, row.label, what, row.contact, ""]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if c == 0:
                    cell.setForeground(QColor(theme.color_for(row.address)))
                    f = cell.font()
                    f.setBold(True)
                    cell.setFont(f)
                self.table.setItem(r, c, cell)
        self.update_values(self._values)

    def update_values(self, snap: dict):
        self._values = snap
        for r, row in enumerate(self.rows):
            cell = self.table.item(r, VAL)
            if cell is None:
                continue
            v = snap.get(row.address)
            txt = "-" if v is None else str(v)
            if cell.text() != txt:
                cell.setText(txt)
                on = v not in (None, 0) and row.io in ("in", "out")
                cell.setBackground(QColor("#2F6B3A") if on else QColor(0, 0, 0, 0))

    def _item_of(self, r):
        row = self.rows[r]
        return row, self.view.items_by_id.get(row.device_id)

    def _clicked(self, r, c):
        row, it = self._item_of(r)
        if it is None:
            return
        it.flash(900)
        self.view.centerOn(it)
        if not self.view.sc.run_mode:
            self.view.sc.clearSelection()
            it.setSelected(True)

    def _double(self, r, c):
        row, it = self._item_of(r)
        if isinstance(it, InputItem) and row.prop == "address":
            it.set_actuated(not it.actuated)
            self.message.emit(f"{row.address} ← {it.signal()} ({row.label or row.device})")

    # ---------- จัด address ----------
    def auto_assign(self):
        specs = [it.spec for it in self.view.items_by_id.values()]
        changes = iolist.auto_assign(specs, self.view.xy_base)
        if not changes:
            self.message.emit(tr("✔ address เรียงตามตำแหน่งอยู่แล้ว ไม่ต้องเปลี่ยน"))
            return
        if AssignDialog(self.view, changes, self).exec() == QDialog.Accepted:
            self.view.apply_addresses(changes)
            n = sum(len(p) for p in changes.values())
            self.message.emit(tr("🔢 จัด address อัตโนมัติแล้ว {0} ช่อง — อย่าลืมแก้ ladder ให้ตรง (Ctrl+Z = ย้อนกลับ)", n))

    # ---------- export ----------
    def _ask(self, title, suffix, filt) -> Path | None:
        name = (self.view.doc_name or "panel").replace("/", "-") + suffix
        path, _ = QFileDialog.getSaveFileName(self, title, str(state.PANEL_DIR / name), filt)
        return Path(path) if path else None

    def export_csv(self, path: Path | None = None):
        path = path or self._ask(tr("Export ตาราง I/O"), "_IO.csv", "CSV (*.csv)")
        if path:
            path.write_text(iolist.to_csv(self.rows), encoding="utf-8", newline="")
            self.message.emit(tr("⇩ บันทึกตาราง I/O: {0}", path))
        return path

    def export_gx(self, path: Path | None = None):
        path = path or self._ask("Export Device Comment (GX Works3)", "_comment.csv", "CSV (*.csv)")
        if path:
            path.write_text(iolist.to_gx_comment_csv(self.rows), encoding="utf-8", newline="")
            self.message.emit(tr("⇩ บันทึก Device Comment: {0} — เปิดใน Excel แล้วคัดลอก 2 คอลัมน์ ไปวางในตาราง Device Comment ของ GX Works3", path))
        return path

    def export_pdf(self, path: Path | None = None):
        path = path or self._ask(tr("พิมพ์ตาราง I/O เป็น PDF"), "_IO.pdf", "PDF (*.pdf)")
        if path:
            from PySide6.QtGui import QPageSize, QPdfWriter
            doc = QTextDocument()
            doc.setHtml(iolist.to_html(self.rows, tr_data(self.view.doc_name)))
            w = QPdfWriter(str(path))
            w.setPageSize(QPageSize(QPageSize.A4))
            w.setResolution(120)
            doc.setPageSize(w.pageLayout().paintRectPixels(w.resolution()).size().toSizeF())
            doc.print_(w)
            self.message.emit(tr("⇩ บันทึก PDF: {0}", path))
        return path
