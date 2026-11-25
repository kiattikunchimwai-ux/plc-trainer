"""วิซาร์ดสร้างด่านในห้องของผู้ใช้: ผัง → แม่แบบ → ชื่อ/โจทย์."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QPlainTextEdit,
    QVBoxLayout,
)

from ..i18n import tr
from ..levels import conditions as C
from ..levels import editor as E
from ..panel import PanelDoc, iolist
from . import theme


class LevelWizard(QDialog):
    """ผลลัพธ์อยู่ที่ self.draft (ยังไม่บันทึก) หลัง accept."""

    def __init__(self, folder: Path, existing: list, xy_base: int = 8, panel: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("➕ สร้างด่าน"))
        self.resize(620, 620)
        self.folder, self.existing, self.xy_base = Path(folder), existing, xy_base
        self.draft: E.LevelDraft | None = None
        self.rows, self.devices = [], []
        self._auto_title = ""
        lay = QVBoxLayout(self)

        g1 = QGroupBox(tr("1  ผังอุปกรณ์"))
        f1 = QFormLayout(g1)
        self.cb_panel = QComboBox()
        for text, val in E.panel_choices(self.folder):
            self.cb_panel.addItem(text, val)
        f1.addRow(tr("ผัง"), self.cb_panel)
        self.lbl_io = QLabel()
        self.lbl_io.setWordWrap(True)
        self.lbl_io.setStyleSheet(f"color:{theme.TEXT_DIM};")
        f1.addRow("", self.lbl_io)
        lay.addWidget(g1)

        g2 = QGroupBox(tr("2  งานแบบไหน"))
        v2 = QVBoxLayout(g2)
        self.cb_tpl = QComboBox()
        self.tpls = C.templates()
        for t in self.tpls:
            self.cb_tpl.addItem(t.name, t.key)
        v2.addWidget(self.cb_tpl)
        self.lbl_help = QLabel()
        self.lbl_help.setStyleSheet(f"color:{theme.TEXT_DIM};")
        v2.addWidget(self.lbl_help)
        self.form = QFormLayout()
        v2.addLayout(self.form)
        lay.addWidget(g2)

        g3 = QGroupBox(tr("3  ชื่อและโจทย์"))
        f3 = QFormLayout(g3)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText(tr("เช่น มอเตอร์สายพานขนของ"))
        self.ed_desc = QPlainTextEdit()
        self.ed_desc.setFixedHeight(80)
        self.ed_desc.setPlaceholderText(tr("เว้นว่างได้ — โปรแกรมเขียนจากแม่แบบให้"))
        f3.addRow(tr("ชื่อด่าน"), self.ed_title)
        f3.addRow(tr("โจทย์"), self.ed_desc)
        lay.addWidget(g3)
        lay.addStretch(1)
        self.lbl_err = QLabel()
        self.lbl_err.setWordWrap(True)
        self.lbl_err.setStyleSheet(f"color:{theme.DANGER};")
        lay.addWidget(self.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("สร้างด่าน"))
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText(tr("ยกเลิก"))
        bb.accepted.connect(self.finish)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.roles: dict[str, QComboBox] = {}
        self.params: dict[str, QDoubleSpinBox] = {}
        self.cb_panel.currentIndexChanged.connect(self._panel_changed)
        self.cb_tpl.currentIndexChanged.connect(self._tpl_changed)
        i = self.cb_panel.findData(panel)
        self.cb_panel.setCurrentIndex(max(0, i))
        self._panel_changed()

    @property
    def tpl(self) -> C.Template:
        return self.tpls[max(0, self.cb_tpl.currentIndex())]

    def _panel_changed(self, _i=0):
        p = E.resolve_panel(self.cb_panel.currentData() or "", self.folder)
        self.devices = []
        if p is not None:
            try:
                self.devices = PanelDoc.load(p).devices
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
        self.rows = iolist.rows(self.devices, self.xy_base)
        self.lbl_io.setText("  ·  ".join(f"<b>{r.address}</b> {r.label or r.device}" for r in self.rows if not r.is_reference)
                            or tr("ผังนี้ยังไม่มี I/O"))
        self._tpl_changed()

    def _tpl_changed(self, _i=0):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.roles, self.params = {}, {}
        t = self.tpl
        self.lbl_help.setText(t.help)
        if self.ed_title.text() == self._auto_title:          # ยังไม่ได้ตั้งเอง → ใช้ชื่อแม่แบบ กดสร้างได้เลย
            self._auto_title = t.name
            self.ed_title.setText(t.name)
        names = C.panel_names(self.rows)
        users = [a for a, _, _ in C.user_inputs(self.devices, self.xy_base)]
        pools = {"in": users + [r.address for r in self.rows if r.io == "in"],
                 "out": [r.address for r in self.rows if r.io == "out" and not r.is_reference]}
        used: set[str] = set()
        for key, title, io in t.roles:
            cb = QComboBox()
            pool = list(dict.fromkeys(pools[io]))
            for a in pool:
                cb.addItem(C.device_name(a, names), a)
            want = None
            if key == "stop":
                want = next((a for a in pool if any(w in names.get(a, "").lower() for w in ("stop", "reset", "หยุด"))), None)  # i18n: skip
            if want is None:
                want = next((a for a in pool if a not in used and not (
                    key != "stop" and any(w in names.get(a, "").lower() for w in ("stop", "หยุด")))), None)  # i18n: skip
            cb.setCurrentIndex(cb.findData(want))
            if want:
                used.add(want)
            self.form.addRow(title, cb)
            self.roles[key] = cb
        for key, title, val, lo, hi, dec in t.params:
            sp = QDoubleSpinBox()
            sp.setDecimals(dec)
            sp.setRange(lo, hi)
            sp.setValue(val)
            self.form.addRow(title, sp)
            self.params[key] = sp

    def finish(self):
        roles = {k: cb.currentData() for k, cb in self.roles.items()}
        t = self.tpl
        if any(not v for v in roles.values()):
            return self.lbl_err.setText(tr("ผังนี้มีอุปกรณ์ไม่พอสำหรับแม่แบบนี้ — เลือกผังอื่น หรือใช้แม่แบบว่าง"))
        if len(set(roles.values())) != len(roles):
            return self.lbl_err.setText(tr("เลือกอุปกรณ์ซ้ำกัน"))
        if not self.ed_title.text().strip():
            self.ed_title.setFocus()
            return self.lbl_err.setText(tr("ยังไม่ได้ตั้งชื่อด่าน"))
        names, nc = C.panel_names(self.rows), C.nc_inputs(self.rows)
        d = E.new_draft(self.existing)
        d.title = self.ed_title.text().strip()
        d.panel = self.cb_panel.currentData() or ""
        use = dict(roles)
        if not use:
            users = C.user_inputs(self.devices, self.xy_base)
            outs = [r.address for r in self.rows if r.io == "out" and not r.is_reference]
            use = {"start": users[0][0] if users else "X0", "out": outs[0] if outs else "Y0"}
        d.cases = C.build_cases(t.key, use, {k: sp.value() for k, sp in self.params.items()}, nc)
        d.idle = {a: int(a in nc) for k, a in use.items() if a.startswith("X")}
        d.reset = C.press_rows(roles["stop"], nc=roles["stop"] in nc) if "stop" in roles else []
        C.auto_setup(d, self.devices, self.xy_base)
        d.desc = self.ed_desc.toPlainText().strip() or (
            t.help + "\n" + " · ".join(f"{title}: {C.device_name(roles[k], names)}" for k, title, _ in t.roles))
        self.draft = d
        self.accept()
