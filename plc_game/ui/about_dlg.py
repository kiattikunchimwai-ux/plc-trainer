"""หน้าต่าง "เกี่ยวกับ": เวอร์ชัน · ไม่เกี่ยวข้องกับ Mitsubishi · โฟลเดอร์ข้อมูล · เช็กเวอร์ชันใหม่ · ผู้สนับสนุน · ไลเซนส์."""
from __future__ import annotations

import html
import threading

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import __version__, paths, support, update
from ..i18n import tr
from . import theme

LICENSES = [  # (ชื่อ, ไลเซนส์)
    ("Python", "PSF"), ("Qt 6 / PySide6", "LGPL v3"), ("pyqtgraph", "MIT"), ("PyYAML", "MIT"),
    ("pymcprotocol", "MIT"), ("openpyxl", "MIT"), ("qrcode", "BSD"), ("NumPy", "BSD"),
]


class AboutDialog(QDialog):
    _checked = Signal(object)              # UpdateInfo หรือ str (ข้อความผิดพลาด) — ส่งจากเธรดเช็กเวอร์ชัน

    def __init__(self, parent=None, update_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("ℹ เกี่ยวกับ PLC Trainer"))
        self.setMinimumWidth(520)
        self.update_url = update_url or ""
        self.info: update.UpdateInfo | None = None
        v = QVBoxLayout(self)
        v.setSpacing(8)

        head = QLabel(f"<span style='font-size:18pt; font-weight:bold; color:{theme.ACCENT}'>⚡ PLC Trainer</span>"
                      f"&nbsp;&nbsp;<span style='color:{theme.TEXT_DIM}'>v{__version__}</span>")
        v.addWidget(head)
        v.addWidget(self._dim(tr("เกมฝึกเขียนโปรแกรม PLC — ตรวจคำตอบจากผล I/O กับ GX Simulator3 หรือ PLC จำลอง · ใช้ฟรี")))
        note = QLabel(tr("โปรแกรมนี้ไม่ได้เกี่ยวข้องหรือได้รับการรับรองจาก Mitsubishi Electric · "
                         "GX Works3, GX Simulator3, MELSEC iQ-R และ FX5 เป็นเครื่องหมายการค้าของ Mitsubishi Electric Corporation"))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.WARN}; padding:6px; border:1px solid {theme.BORDER}; border-radius:4px;")
        v.addWidget(note)

        # โฟลเดอร์ข้อมูล
        row = QHBoxLayout()
        self.lbl_data = QLabel(tr("ข้อมูลของคุณ (คะแนน/ผัง/การตั้งค่า): {0}", paths.data_dir()))
        self.lbl_data.setWordWrap(True)
        self.lbl_data.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.lbl_data, 1)
        b = QPushButton(tr("📂 เปิดโฟลเดอร์"))
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        row.addWidget(b)
        v.addLayout(row)

        # เช็กเวอร์ชัน
        row = QHBoxLayout()
        self.btn_check = QPushButton(tr("🔄 เช็กเวอร์ชันใหม่"))
        self.btn_check.clicked.connect(self.check_update)
        self.btn_check.setEnabled(bool(self.update_url))
        if not self.update_url:
            self.btn_check.setToolTip(tr("ยังไม่ได้ตั้ง update_url ใน config.yaml"))
        self.btn_download = QPushButton(tr("⬇ ดาวน์โหลด"))
        self.btn_download.setVisible(False)
        self.btn_download.clicked.connect(self._open_download)
        self.lbl_update = QLabel("")
        self.lbl_update.setWordWrap(True)
        row.addWidget(self.btn_check)
        row.addWidget(self.lbl_update, 1)
        row.addWidget(self.btn_download)
        v.addLayout(row)
        self._checked.connect(self._on_checked)

        # ผู้สนับสนุน
        cfg = support.load_support_cfg()
        if cfg.supporters:
            v.addWidget(self._dim(tr("☕ ขอบคุณผู้สนับสนุน: {0}", ", ".join(cfg.supporters))))

        lic = " · ".join(f"{n} ({l})" for n, l in LICENSES)
        v.addWidget(self._dim(tr("สร้างด้วยซอฟต์แวร์โอเพนซอร์ส: {0}", lic)))

        close = QPushButton(tr("ปิด"))
        close.clicked.connect(self.accept)
        v.addWidget(close, 0, Qt.AlignRight)

    @staticmethod
    def _dim(text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.TEXT_DIM};")
        return lb

    # ----- เช็กเวอร์ชัน (ไม่บล็อกหน้าต่าง) -----
    def check_update(self, fetch=None):
        """fetch = ฟังก์ชันแทน update.fetch (ใช้ทดสอบ)."""
        fetch = fetch or update.fetch
        self.btn_check.setEnabled(False)
        self.lbl_update.setText(tr("กำลังเช็ก…"))

        def work():
            try:
                res = fetch(self.update_url)
            except ValueError as e:
                res = str(e)
            self._checked.emit(res)
        threading.Thread(target=work, daemon=True).start()

    def _on_checked(self, res):
        self.btn_check.setEnabled(bool(self.update_url))
        if isinstance(res, str):
            self.lbl_update.setText(f"<span style='color:{theme.DANGER}'>{html.escape(res)}</span>")
            return
        self.info = res
        if res.newer:
            extra = []
            if res.date:
                extra.append(res.date)
            if res.size:
                extra.append(tr("{0} MB", f"{res.size / 1e6:.0f}"))
            head = tr("🎉 มีเวอร์ชันใหม่ v{0}", res.version) + (f" ({' · '.join(extra)})" if extra else "")
            self.lbl_update.setText(html.escape(head + (f" — {res.notes}" if res.notes else "")))  # ข้อความจากเน็ต ไม่ให้เป็น HTML
            self.btn_download.setVisible(bool(res.url))
        else:
            self.lbl_update.setText(tr("✔ เป็นเวอร์ชันล่าสุดแล้ว (v{0})", __version__))
            self.btn_download.setVisible(False)

    def _open_download(self):
        if self.info and self.info.url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(self.info.url))
