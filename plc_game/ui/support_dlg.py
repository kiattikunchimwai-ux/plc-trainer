"""หน้าต่าง "☕ สนับสนุนผู้พัฒนา" (QR พร้อมเพย์ + ลิงก์) และ toast ชวนแบบไม่รบกวน."""
from __future__ import annotations

from ..i18n import tr

import qrcode
from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import support
from . import theme


class QRWidget(QWidget):
    """วาด QR จาก payload ด้วย QPainter (ขาว-ดำ พร้อมขอบ quiet zone)."""

    def __init__(self, parent=None, size: int = 240):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.matrix: list[list[bool]] = []
        self.payload = ""

    def set_payload(self, payload: str):
        self.payload = payload
        if payload:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=3)
            qr.add_data(payload)
            qr.make(fit=True)
            self.matrix = qr.get_matrix()
        else:
            self.matrix = []
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("white") if self.matrix else QColor(theme.BG_INPUT))
        if not self.matrix:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, tr("ยังไม่ได้ตั้งค่า\nพร้อมเพย์"))
            return
        n = len(self.matrix)
        cell = self.width() / n
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("black"))
        for r, row in enumerate(self.matrix):
            for c, on in enumerate(row):
                if on:
                    p.drawRect(QRectF(c * cell, r * cell, cell + 0.5, cell + 0.5))


class SupportDialog(QDialog):
    def __init__(self, parent=None, cfg: support.SupportConfig | None = None):
        super().__init__(parent)
        self.cfg = cfg or support.load_support_cfg()
        self.setWindowTitle(tr("☕ สนับสนุนผู้พัฒนา"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setSpacing(10)

        head = QLabel(tr("<b style='font-size:15pt'>PLC Trainer ใช้ฟรี ไม่มีโฆษณา</b><br><span style='color:{0}'>ถ้าโปรแกรมช่วยให้เรียน/สอน PLC ได้ง่ายขึ้น ร่วมสนับสนุนเพื่อให้มีด่านใหม่ อุปกรณ์ใหม่ และอัปเดตต่อไปได้</span>", theme.TEXT_DIM))
        head.setWordWrap(True)
        v.addWidget(head)

        if self.cfg.goal_text and self.cfg.goal_target > 0:
            g = QFrame()
            g.setObjectName("card")
            gl = QVBoxLayout(g)
            gl.addWidget(QLabel(tr("🎯 เป้าหมายถัดไป: <b>{0}</b>", self.cfg.goal_text)))
            self.goal_bar = QProgressBar()
            self.goal_bar.setRange(0, self.cfg.goal_target)
            self.goal_bar.setValue(min(self.cfg.goal_current, self.cfg.goal_target))
            self.goal_bar.setFormat(tr("฿{0:,} / ฿{1:,}", self.cfg.goal_current, self.cfg.goal_target))
            gl.addWidget(self.goal_bar)
            v.addWidget(g)

        row = QHBoxLayout()
        left = QVBoxLayout()
        self.qr = QRWidget(self)
        left.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.lbl_amount = QLabel()
        self.lbl_amount.setAlignment(Qt.AlignCenter)
        left.addWidget(self.lbl_amount)
        row.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel(tr("<b>พร้อมเพย์</b> — สแกนด้วยแอปธนาคารใดก็ได้")))
        amt = QHBoxLayout()
        self.amount_buttons: list[QPushButton] = []
        for a in support.AMOUNTS:
            b = QPushButton(tr("฿{0}", a))
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, a=a: self.set_amount(a))
            amt.addWidget(b)
            self.amount_buttons.append(b)
        self.sp_amount = QSpinBox()
        self.sp_amount.setRange(0, 100000)
        self.sp_amount.setPrefix(tr("฿"))
        self.sp_amount.setSpecialValueText(tr("ใส่เอง"))
        self.sp_amount.setToolTip(tr("0 = ให้ผู้โอนใส่จำนวนเงินเองในแอป"))
        self.sp_amount.valueChanged.connect(lambda val: self.set_amount(val or None, from_spin=True))
        amt.addWidget(self.sp_amount)
        right.addLayout(amt)
        self.lbl_name = QLabel()
        self.lbl_name.setWordWrap(True)
        right.addWidget(self.lbl_name)
        self.btn_copy = QPushButton(tr("📋 คัดลอกเลขพร้อมเพย์"))
        self.btn_copy.clicked.connect(self.copy_id)
        right.addWidget(self.btn_copy)

        if self.cfg.links:
            right.addSpacing(6)
            right.addWidget(QLabel(tr("<b>ช่องทางอื่น</b> (บัตรเครดิต / ต่างประเทศ)")))
            for ln in self.cfg.links:
                b = QPushButton(f"🔗 {ln.get('label', ln['url'])}")
                b.clicked.connect(lambda _=False, u=ln["url"]: QDesktopServices.openUrl(QUrl(u)))
                right.addWidget(b)
        right.addStretch(1)
        row.addLayout(right, 1)
        v.addLayout(row)

        use = QLabel(tr("<span style='color:{0}'>เงินสนับสนุนใช้ทำ: ด่านและอุปกรณ์ใหม่ · Ladder ในตัว · ค่าเซิร์ฟเวอร์อัปเดต · ภาษาอังกฤษ</span>", theme.TEXT_DIM))
        use.setWordWrap(True)
        v.addWidget(use)
        if self.cfg.supporters:
            s = QLabel(tr("💛 ขอบคุณ: ") + ", ".join(self.cfg.supporters[:30]))
            s.setWordWrap(True)
            v.addWidget(s)
        close = QPushButton(tr("ปิด"))
        close.clicked.connect(self.accept)
        v.addWidget(close, 0, Qt.AlignRight)

        self.amount: int | None = None
        self.set_amount(None)

    def set_amount(self, amount: int | None, from_spin: bool = False):
        self.amount = amount or None
        for b, a in zip(self.amount_buttons, support.AMOUNTS):
            b.setChecked(a == self.amount)
        if not from_spin:
            self.sp_amount.blockSignals(True)
            self.sp_amount.setValue(0)
            self.sp_amount.blockSignals(False)
        ok = self.cfg.has_promptpay
        self.btn_copy.setEnabled(ok)
        if ok:
            self.qr.set_payload(support.promptpay_payload(self.cfg.promptpay_id, self.amount))
            self.lbl_amount.setText(tr("<b>฿{0:,}</b>", self.amount) if self.amount else tr("ใส่จำนวนเงินเองในแอป"))
            self.lbl_name.setText(tr("ชื่อบัญชี: <b>{0}</b> — ตรวจให้ตรงก่อนโอน", self.cfg.promptpay_name)
                                  if self.cfg.promptpay_name else "")
        else:
            self.qr.set_payload("")
            self.lbl_amount.setText("")
            self.lbl_name.setText(tr("<span style='color:{0}'>ผู้พัฒนายังไม่ได้ใส่เลขพร้อมเพย์ใน plc_game/support.json</span>", theme.WARN))

    def copy_id(self):
        QGuiApplication.clipboard().setText(self.cfg.promptpay_id)
        self.btn_copy.setText(tr("✔ คัดลอกแล้ว"))
        QTimer.singleShot(1500, lambda: self.btn_copy.setText(tr("📋 คัดลอกเลขพร้อมเพย์")))


class SupportToast(QFrame):
    """กล่องเล็กมุมขวาล่าง — หายเองใน 15 วินาที. support → เปิดหน้าโดเนท, never → ไม่ต้องเตือนอีก."""
    support_clicked = Signal()
    never_clicked = Signal()
    TIMEOUT_MS = 15000

    def __init__(self, parent: QWidget, text: str):
        super().__init__(parent)
        self.setObjectName("supportToast")
        self.setStyleSheet(f"#supportToast{{background:{theme.BG_PANEL};border:1px solid {theme.ACCENT};"
                           f"border-radius:{theme.RADIUS}px;}}")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        self.lbl = QLabel(text)
        self.lbl.setWordWrap(True)
        self.lbl.setMaximumWidth(320)
        v.addWidget(self.lbl)
        h = QHBoxLayout()
        self.btn_support = QPushButton(tr("☕ สนับสนุน"))
        self.btn_support.setObjectName("primary")
        self.btn_later = QPushButton(tr("ไว้ทีหลัง"))
        self.btn_never = QPushButton(tr("ไม่ต้องเตือนอีก"))
        for b in (self.btn_support, self.btn_later, self.btn_never):
            h.addWidget(b)
        v.addLayout(h)
        self.btn_support.clicked.connect(lambda: (self.close(), self.support_clicked.emit()))
        self.btn_later.clicked.connect(self.close)
        self.btn_never.clicked.connect(lambda: (self.close(), self.never_clicked.emit()))
        self.setAttribute(Qt.WA_DeleteOnClose)
        QTimer.singleShot(self.TIMEOUT_MS, self.close)

    def popup(self):
        self.adjustSize()
        p = self.parentWidget()
        bottom = p.height() - 24
        cmd = getattr(p, "cmd_input", None)        # อยู่เหนือ command line + status bar ของ MainWindow
        if cmd is not None and cmd.isVisible():
            bottom = cmd.mapTo(p, cmd.rect().topLeft()).y() - 12
        self.move(p.width() - self.width() - 24, bottom - self.height())
        self.show()
        self.raise_()
