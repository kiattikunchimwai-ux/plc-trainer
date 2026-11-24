"""โหมดสอบ: รหัสครู (pbkdf2), จำกัดเวลา/จำนวนครั้งตรวจต่อด่าน, ปิด AI, ล็อกการแก้ผัง.

สถานะการสอบเก็บใน panels/ui_state.json (คีย์ "exam") — ปิดแล้วเปิดโปรแกรมใหม่ก็ยังอยู่ในโหมดสอบ
ออกจากโหมดสอบได้ด้วยรหัสครูเท่านั้น
"""
from __future__ import annotations

from ..i18n import tr

import hashlib
import hmac
import os
import time
from dataclasses import asdict, dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QVBoxLayout,
)

from . import theme

ITER = 120_000


# ---------------- รหัสครู ----------------
def hash_password(pw: str, salt: bytes | None = None, iterations: int | None = None) -> str:
    salt = salt or os.urandom(16)
    iterations = iterations or ITER
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    try:
        algo, it, salt, digest = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


# ---------------- การสอบ ----------------
@dataclass
class ExamSession:
    level_ids: list[str]
    minutes: int = 30
    max_checks: int = 3                      # 0 = ไม่จำกัด
    started_at: float = 0.0                  # time.time()
    checks: dict[str, int] = field(default_factory=dict)
    best: dict[str, int] = field(default_factory=dict)
    student: str = ""
    plc: dict[str, str] = field(default_factory=dict)     # ด่าน → PLC ที่ได้ดาวดีที่สุด

    @classmethod
    def start(cls, level_ids, minutes, max_checks, student="", now=None) -> "ExamSession":
        if not level_ids:
            raise ValueError(tr("ต้องเลือกอย่างน้อย 1 ด่าน"))
        if minutes <= 0:
            raise ValueError(tr("เวลาสอบต้องมากกว่า 0 นาที"))
        return cls(list(level_ids), int(minutes), max(0, int(max_checks)),
                   time.time() if now is None else now, {}, {}, student)

    def remaining_s(self, now=None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self.started_at + self.minutes * 60 - now)

    def expired(self, now=None) -> bool:
        return self.remaining_s(now) <= 0

    def allows(self, level_id: str) -> bool:
        return level_id in self.level_ids

    def checks_left(self, level_id: str) -> int | None:
        if not self.max_checks:
            return None
        return max(0, self.max_checks - self.checks.get(level_id, 0))

    def can_check(self, level_id: str, now=None) -> tuple[bool, str]:
        if self.expired(now):
            return False, tr("หมดเวลาสอบแล้ว")
        if not self.allows(level_id):
            return False, tr("ด่านนี้ไม่อยู่ในชุดข้อสอบ")
        if self.checks_left(level_id) == 0:
            return False, tr("ใช้สิทธิ์ตรวจด่านนี้ครบ {0} ครั้งแล้ว", self.max_checks)
        return True, ""

    def use_check(self, level_id: str):
        self.checks[level_id] = self.checks.get(level_id, 0) + 1

    def record(self, level_id: str, stars: int, plc: str = ""):
        old = self.best.get(level_id, -1)
        if stars > old or (stars == old and self.plc.get(level_id) == "mock"):   # เท่ากัน: ตัวที่ไม่ใช่ Mock น่าเชื่อกว่า
            self.plc[level_id] = plc
        self.best[level_id] = max(self.best.get(level_id, 0), int(stars))

    def total_stars(self) -> int:
        return sum(self.best.get(i, 0) for i in self.level_ids)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "ExamSession | None":
        try:
            return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})
        except (TypeError, KeyError):
            return None


def fmt_clock(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


# ---------------- หน้าต่าง ----------------
class ExamSetupDialog(QDialog):
    """ครูตั้งค่าการสอบ: รหัสครู (ตั้งครั้งแรก / ยืนยัน), ด่าน, เวลา, จำนวนครั้งตรวจ."""

    def __init__(self, levels, stored_hash: str | None, parent=None, preselect=()):
        super().__init__(parent)
        self.setWindowTitle(tr("📝 เริ่มโหมดสอบ"))
        self.setMinimumWidth(460)
        self.stored_hash = stored_hash
        self.new_hash: str | None = None
        self.session: ExamSession | None = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("ระหว่างสอบ: ปิด AI วิเคราะห์ · ล็อกการแก้ผัง/ใส่ความผิดปกติ · มีนาฬิกาถอยหลัง\n"
                           "ออกจากโหมดสอบต้องใช้รหัสครู")))
        f = QFormLayout()
        self.ed_pw = QLineEdit()
        self.ed_pw.setEchoMode(QLineEdit.Password)
        self.ed_pw2 = QLineEdit()
        self.ed_pw2.setEchoMode(QLineEdit.Password)
        if stored_hash:
            f.addRow(tr("รหัสครู"), self.ed_pw)
        else:
            self.ed_pw.setPlaceholderText(tr("ตั้งรหัสครูครั้งแรก (อย่างน้อย 4 ตัว)"))
            f.addRow(tr("ตั้งรหัสครู"), self.ed_pw)
            f.addRow(tr("ยืนยันรหัส"), self.ed_pw2)
        self.lst = QListWidget()
        self.lst.setMinimumHeight(220)
        for lv in levels:
            it = QListWidgetItem(lv.title)
            it.setData(Qt.UserRole, lv.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if lv.id in preselect else Qt.Unchecked)
            self.lst.addItem(it)
        f.addRow(tr("ด่านที่สอบ"), self.lst)
        self.sp_min = QSpinBox()
        self.sp_min.setRange(1, 300)
        self.sp_min.setValue(30)
        self.sp_min.setSuffix(tr(" นาที"))
        self.sp_checks = QSpinBox()
        self.sp_checks.setRange(0, 50)
        self.sp_checks.setValue(3)
        self.sp_checks.setSpecialValueText(tr("ไม่จำกัด"))
        self.sp_checks.setSuffix(tr(" ครั้ง/ด่าน"))
        f.addRow(tr("เวลาสอบ"), self.sp_min)
        f.addRow(tr("ตรวจได้"), self.sp_checks)
        v.addLayout(f)
        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet(f"color:{theme.DANGER};")
        v.addWidget(self.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("เริ่มสอบ"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("ยกเลิก"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def selected_ids(self) -> list[str]:
        return [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.Checked]

    def accept(self):
        pw = self.ed_pw.text()
        if self.stored_hash:
            if not verify_password(pw, self.stored_hash):
                self.lbl_err.setText(tr("รหัสครูไม่ถูกต้อง"))
                return
        else:
            if len(pw) < 4:
                self.lbl_err.setText(tr("รหัสครูต้องมีอย่างน้อย 4 ตัวอักษร"))
                return
            if pw != self.ed_pw2.text():
                self.lbl_err.setText(tr("ยืนยันรหัสไม่ตรงกัน"))
                return
            self.new_hash = hash_password(pw)
        try:
            self.session = ExamSession.start(self.selected_ids(), self.sp_min.value(), self.sp_checks.value())
        except ValueError as e:
            self.lbl_err.setText(str(e))
            return
        super().accept()


class TeacherPasswordDialog(QDialog):
    """ถามรหัสครูก่อนออกจากโหมดสอบ."""

    def __init__(self, stored_hash: str | None, parent=None, prompt=""):
        super().__init__(parent)
        prompt = prompt or tr("ใส่รหัสครูเพื่อออกจากโหมดสอบ")
        self.setWindowTitle(tr("รหัสครู"))
        self.stored_hash = stored_hash
        v = QVBoxLayout(self)
        v.addWidget(QLabel(prompt))
        self.ed = QLineEdit()
        self.ed.setEchoMode(QLineEdit.Password)
        v.addWidget(self.ed)
        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet(f"color:{theme.DANGER};")
        v.addWidget(self.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("ตกลง"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("ยกเลิก"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def accept(self):
        if not verify_password(self.ed.text(), self.stored_hash):
            self.lbl_err.setText(tr("รหัสครูไม่ถูกต้อง"))
            self.ed.selectAll()
            return
        super().accept()
