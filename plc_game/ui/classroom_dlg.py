"""หน้าต่างห้องเรียน: ลงชื่อนักเรียน + ตารางคะแนนทั้งห้อง (Export Excel)."""
from __future__ import annotations

from ..i18n import tr

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout)

from .. import classroom
from ..levels import scores
from . import theme

STAR_COL = {3: "#2F9E44", 2: "#E8A317", 1: "#E8590C", 0: "#3A4250"}


class LoginDialog(QDialog):
    """เลือกชื่อจากรายชื่อ หรือพิมพ์รหัส+ชื่อใหม่ (บันทึกลง panels/students.json)."""

    def __init__(self, parent=None, current: str = scores.GUEST):
        super().__init__(parent)
        self.setWindowTitle(tr("ลงชื่อนักเรียน"))
        self.setMinimumWidth(420)
        self.student: classroom.Student | None = None
        self.students = classroom.load_students()
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("คะแนนของแต่ละด่านจะบันทึกตามรหัสนักเรียน")))
        f = QFormLayout()
        self.cb = QComboBox()
        self.cb.addItem(tr("— นักเรียนใหม่ / พิมพ์เอง —"), None)
        for s in self.students:
            self.cb.addItem(s.label, s.sid)
        self.ed_id = QLineEdit()
        self.ed_id.setPlaceholderText(tr("เช่น 66301001"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText(tr("ชื่อ-นามสกุล"))
        f.addRow(tr("รายชื่อ"), self.cb)
        f.addRow(tr("รหัส"), self.ed_id)
        f.addRow(tr("ชื่อ"), self.ed_name)
        v.addLayout(f)
        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet(f"color:{theme.DANGER};")
        v.addWidget(self.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("ลงชื่อ"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("ยกเลิก"))
        self.btn_guest = bb.addButton(tr("ไม่ลงชื่อ (guest)"), QDialogButtonBox.ResetRole)
        self.btn_guest.clicked.connect(self._as_guest)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.cb.currentIndexChanged.connect(self._on_pick)
        i = self.cb.findData(current)
        if i > 0:
            self.cb.setCurrentIndex(i)

    def _on_pick(self, _i):
        sid = self.cb.currentData()
        s = next((s for s in self.students if s.sid == sid), None)
        self.ed_id.setText(s.sid if s else "")
        self.ed_name.setText(s.name if s else "")

    def _as_guest(self):
        self.student = None
        self.done(2)

    def accept(self):
        try:
            self.student = classroom.upsert_student(self.ed_id.text(), self.ed_name.text())
        except ValueError as e:
            self.lbl_err.setText(str(e))
            return
        super().accept()


class ScoreDialog(QDialog):
    """ตารางดาวทั้งห้อง แยกรายด่าน + Export .xlsx."""

    def __init__(self, levels, parent=None):
        super().__init__(parent)
        self.levels = levels
        self.setWindowTitle(tr("ตารางคะแนนทั้งห้อง"))
        self.resize(1100, 600)
        v = QVBoxLayout(self)
        self.lbl = QLabel()
        v.addWidget(self.lbl)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.weak = QTableWidget()
        self.weak.setEditTriggers(QTableWidget.NoEditTriggers)
        self.weak.verticalHeader().hide()
        self.weak.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, tr("คะแนน"))
        self.tabs.addTab(self.weak, tr("ข้อที่พลาดบ่อย"))
        v.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        b_ref = QPushButton(tr("🔄  รีเฟรช"))
        b_ref.clicked.connect(self.refresh)
        self.b_xlsx = QPushButton("📊  Export Excel (.xlsx)")
        self.b_xlsx.setObjectName("Primary")
        self.b_xlsx.clicked.connect(self.export)
        b_close = QPushButton(tr("ปิด"))
        b_close.clicked.connect(self.accept)
        row.addWidget(b_ref)
        row.addStretch(1)
        row.addWidget(self.b_xlsx)
        row.addWidget(b_close)
        v.addLayout(row)
        self.refresh()

    def refresh(self):
        data = scores.load()
        headers, rows = classroom.class_table(self.levels, data=data)
        nlv = len(self.levels)
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(headers)
        for i, lv in enumerate(self.levels):
            self.table.horizontalHeaderItem(2 + i).setToolTip(lv.title)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if 2 <= c < 2 + nlv:
                    st = data.get(row[0], {}).get(self.levels[c - 2].id, {})
                    it = QTableWidgetItem(("★" * val if val else "—") + (" Mock" if scores.mock_only(st) else ""))
                    if scores.best_plcs(st):
                        it.setToolTip(tr("ตรวจกับ: {0}", classroom.plc_text(st)))
                    it.setData(Qt.UserRole, val)
                    it.setBackground(QBrush(QColor(STAR_COL[val])))
                    it.setTextAlignment(Qt.AlignCenter)
                elif isinstance(val, int):
                    it = QTableWidgetItem()
                    it.setData(Qt.DisplayRole, val)
                    it.setTextAlignment(Qt.AlignCenter)
                else:
                    it = QTableWidgetItem(str(val))
                self.table.setItem(r, c, it)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)                     # ชื่อต้องเห็นเต็ม แม้ช่องดาวกว้างขึ้นเพราะมีคำว่า Mock
        self.table.setSortingEnabled(True)
        self.lbl.setText(tr("นักเรียน {0} คน · {1} ด่าน · ★★★ = ผ่านทุกข้อ (คลิกหัวคอลัมน์เพื่อเรียง · ชี้หัวคอลัมน์เลขด่านเพื่อดูชื่อด่าน)", len(rows), nlv)
                         + "\n" + tr("Mock = ได้ดาวจาก Mock PLC เท่านั้น (Mock มี ladder บางด่านในตัว) · ชี้ช่องดาวเพื่อดู PLC ที่ใช้ตรวจ"))
        self.rows = rows
        self._fill_weak(data)

    def _fill_weak(self, data):
        head, body = classroom.weak_table(self.levels, data)
        names = {r[0]: r[1] for r in self.rows}
        self.weak.clear()
        self.weak.setColumnCount(len(head))
        self.weak.setRowCount(len(body))
        self.weak.setHorizontalHeaderLabels(head)
        for r, row in enumerate(body):
            for c, val in enumerate(row):
                it = QTableWidgetItem(str(val))
                if c == 5 and val >= 50:
                    it.setBackground(QBrush(QColor(theme.DANGER)))
                it.setToolTip("\n".join(f"{s} {names.get(s, '')}".strip() for s in val.split(", ")) if c == 6 else str(val))
                self.weak.setItem(r, c, it)
        hh = self.weak.horizontalHeader()
        for c, w in enumerate((210, 130, 220, 105, 115, 70)):
            self.weak.setColumnWidth(c, w)
        hh.setStretchLastSection(True)

    def export(self, path: str | None = None) -> Path | None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export คะแนน"), str(Path.home() / "Documents" / tr("คะแนน.xlsx")),
                                                  "Excel (*.xlsx)")
            if not path:
                return None
        try:
            out = classroom.export_xlsx(Path(path), self.levels)
        except Exception as e:      # ไฟล์เปิดค้างใน Excel ฯลฯ
            QMessageBox.warning(self, tr("Export ไม่สำเร็จ"), str(e))
            return None
        self.lbl.setText(tr("✔ บันทึก {0}", out))
        return out
