"""แผง FAULTS (โหมดครู): ใส่ความผิดปกติให้อุปกรณ์บนผัง เพื่อฝึกนักเรียนเขียนโปรแกรมรับมือ/หาจุดเสีย."""
from __future__ import annotations

from ..i18n import tr

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import theme

NORMAL = tr("— ปกติ —")


class FaultPanel(QWidget):
    message = Signal(str)          # ข้อความสำหรับ command line

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self._combos: dict[str, QComboBox] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        hint = QLabel(tr("ครูเลือกความผิดปกติให้อุปกรณ์ แล้วให้นักเรียนสังเกต/หาจุดเสีย\n"
                      "หรือเขียนโปรแกรมให้ตรวจจับได้ (เช่น สั่งกระบอกสูบแล้ว a1 ไม่มาใน 3 วินาที → เตือน)\n"
                      "ความผิดปกติไม่ถูกบันทึกลงไฟล์ผัง"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        lay.addWidget(hint)
        row = QHBoxLayout()
        self.btn_random = QPushButton(tr("🎲 สุ่ม 1 จุด"))
        self.btn_clear = QPushButton(tr("✔ ล้างทั้งหมด"))
        self.cb_hidden = QCheckBox(tr("ซ่อนจากนักเรียน"))
        self.cb_hidden.setToolTip(tr("ไม่แสดงป้าย ⚡ บนอุปกรณ์ — ใช้สอบหาจุดเสีย"))
        self.btn_random.clicked.connect(self.random_fault)
        self.btn_clear.clicked.connect(self.clear_all)
        self.cb_hidden.toggled.connect(self.set_hidden)
        self.btn_reveal = QPushButton(tr("👁 เฉลย"))
        self.btn_reveal.setCheckable(True)
        self.btn_reveal.setToolTip(tr("แสดงคอลัมน์ความผิดปกติชั่วคราว (ตอนซ่อนจากนักเรียน)"))
        self.btn_reveal.toggled.connect(lambda on: self.table.setColumnHidden(2, self.cb_hidden.isChecked() and not on))
        self.btn_reveal.setVisible(False)
        row.addWidget(self.btn_random)
        row.addWidget(self.btn_clear)
        row.addStretch(1)
        row.addWidget(self.btn_reveal)
        row.addWidget(self.cb_hidden)
        lay.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("อุปกรณ์"), "Address", tr("ความผิดปกติ")])
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        self.lbl_count = QLabel()
        lay.addWidget(self.lbl_count)
        view.changed.connect(self.rebuild)
        view.faults_changed.connect(self.sync)
        self.rebuild()

    # ---------- ตาราง ----------
    def rebuild(self):
        items = self.view.fault_items()
        self.table.setRowCount(len(items))
        self._combos = {}
        for r, it in enumerate(items):
            name = QTableWidgetItem(it.shown_label or it.info.name)
            name.setToolTip(it.info.name)
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem(it.caption_tag()))
            cb = QComboBox()
            cb.addItem(NORMAL, "")
            for code, text in it.FAULTS.items():
                cb.addItem("⚡ " + text, code)
            cb.setCurrentIndex(max(0, cb.findData(it.fault)))
            cb.currentIndexChanged.connect(lambda i, cb=cb, it=it: self._chosen(it, cb.itemData(i)))
            self.table.setCellWidget(r, 2, cb)
            self._combos[it.spec.id] = cb
        self.sync()

    def sync(self):
        """อัปเดต combo ตามสถานะจริง (เมื่อเปลี่ยนจากคำสั่ง/สุ่ม)."""
        n = 0
        for it in self.view.fault_items():
            cb = self._combos.get(it.spec.id)
            if cb is None:
                continue
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(it.fault)))
            cb.blockSignals(False)
            cb.setStyleSheet("color:#FF6B6B; font-weight:bold;" if it.fault else "")
            n += bool(it.fault)
        self.lbl_count.setText(tr("มีความผิดปกติ {0} จุด", n) if n else tr("อุปกรณ์ทั้งหมดปกติ"))
        self.lbl_count.setStyleSheet(f"color:{'#FF6B6B' if n else '#5EE36A'};")

    # ---------- การกระทำ ----------
    def _chosen(self, item, code):
        self.view.set_fault(item, code or "")
        name = item.label or item.info.name
        if self.cb_hidden.isChecked():
            self.message.emit(tr("⚡ เปลี่ยนความผิดปกติแล้ว (ซ่อนอยู่)"))
        else:
            self.message.emit(f"⚡ {name}: {item.FAULTS[code]}" if code else tr("✔ {0}: กลับเป็นปกติ", name))

    def random_fault(self):
        res = self.view.random_fault()
        if res is None:
            self.message.emit(tr("ไม่มีอุปกรณ์ที่ใส่ความผิดปกติเพิ่มได้"))
            return
        it, code = res
        if self.cb_hidden.isChecked():
            self.message.emit(tr("🎲 สุ่มใส่ความผิดปกติแล้ว 1 จุด (ซ่อนอยู่) — ให้นักเรียนหาจุดเสีย"))
        else:
            self.message.emit(f"🎲 {it.shown_label or it.info.name}: {it.FAULTS[code]}")

    def clear_all(self):
        n = self.view.clear_faults()
        self.message.emit(tr("✔ ล้างความผิดปกติ {0} จุด — อุปกรณ์ทั้งหมดปกติ", n))

    def set_hidden(self, hidden: bool):
        self.set_hidden_quiet(hidden)
        self.message.emit(tr("ซ่อนป้าย ⚡ จากนักเรียนแล้ว") if hidden else tr("แสดงป้าย ⚡ บนอุปกรณ์"))

    def set_hidden_quiet(self, hidden: bool):
        """ซ่อน/แสดงป้าย ⚡ โดยไม่เขียนข้อความลง command line (ใช้ในด่านหาจุดเสีย)."""
        self.view.set_faults_hidden(hidden)
        self.btn_reveal.setChecked(False)
        self.btn_reveal.setVisible(hidden)
        self.table.setColumnHidden(2, hidden)
