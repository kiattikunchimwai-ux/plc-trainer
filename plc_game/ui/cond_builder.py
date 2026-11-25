"""ตัวสร้างเงื่อนไขแบบประโยค: เลือกจากรายการแทนการพิมพ์คำสั่ง (แปลงไป-กลับกับ StepRow เดิม)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSpinBox,
    QToolButton, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..levels import conditions as C
from ..levels.engine import Cond, parse_conds
from ..plc.device import parse_device
from . import theme
from .flow_layout import FlowLayout
from .thai_keys import latin_only


class _Combo(QComboBox):
    def wheelEvent(self, e):
        e.ignore()


class _Sec(QDoubleSpinBox):
    def __init__(self, value: float, lo=0.05):
        super().__init__()
        self.setRange(lo, 600)
        self.setDecimals(2)
        self.setSingleStep(0.1)
        self.setSuffix(tr(" วินาที"))
        self.setValue(value)

    def wheelEvent(self, e):
        e.ignore()


def _is_bit(a: str) -> bool:
    try:
        return parse_device(a, 16).is_bit
    except ValueError:
        return False


class AddrBox(_Combo):
    """เลือกอุปกรณ์จากผัง หรือพิมพ์ address เอง (แป้นไทยก็พิมพ์ได้)."""
    picked = Signal(str)

    def __init__(self, addr: str, items: list[tuple[str, str]], xy_base: int):
        super().__init__()
        self.xy_base = xy_base
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(150)
        latin_only(self.lineEdit())
        for a, text in items:
            self.addItem(text, a)
        i = self.findData(addr)
        if i < 0 and addr:
            self.addItem(addr, addr)
            i = self.count() - 1
        self.setCurrentIndex(i)
        self.activated.connect(lambda i: self._emit(self.itemData(i)))
        self.lineEdit().editingFinished.connect(self._typed)
        self._addr = addr

    def _typed(self):
        t = self.currentText().strip()
        i = self.findText(t)
        if i >= 0:
            return self._emit(self.itemData(i))
        try:
            self._emit(parse_device(t.upper(), self.xy_base).name)
            self.lineEdit().setStyleSheet("")
        except ValueError as e:
            self.lineEdit().setStyleSheet(f"border:1px solid {theme.DANGER};")
            self.setToolTip(str(e))

    def _emit(self, a):
        if a and a != self._addr:
            self._addr = a
            self.picked.emit(a)


class CondBuilder(QWidget):
    changed = Signal()

    def __init__(self, xy_base: int = 8, parent=None):
        super().__init__(parent)
        self.xy_base = xy_base
        self.actions: list[C.Action] = []
        self.names: dict[str, str] = {}
        self.nc: set[str] = set()
        self.inputs: list[str] = []
        self.outputs: list[str] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        v.addWidget(self.scroll, 1)
        row = QHBoxLayout()
        self.b_do = QPushButton(tr("➕ สิ่งที่ทำ"))
        self.b_do.setToolTip(tr("กดปุ่ม ปล่อยปุ่ม รอเวลา ฯลฯ"))
        self.b_check = QPushButton(tr("➕ สิ่งที่ต้องเกิด"))
        self.b_check.setToolTip(tr("ตรวจว่าเอาต์พุตติด/ดับตามเวลา (★ = นับคะแนน)"))
        for b, kinds in ((self.b_do, C.DO), (self.b_check, C.CHECK)):
            m = QMenu(b)
            for k in kinds:
                m.addAction(C.kind_name(k), lambda k=k: self.add(k))
            b.setMenu(m)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.load([])

    # ---------- ข้อมูล ----------
    def set_io(self, rows):
        """แถว I/O ของผัง (iolist.rows) → รายชื่ออุปกรณ์และปุ่ม NC."""
        src = C.to_rows(self.actions, self.nc)
        self.names, self.nc = C.panel_names(rows), C.nc_inputs(rows)
        self.inputs = list(dict.fromkeys(r.address for r in rows if r.io == "in"))
        self.outputs = list(dict.fromkeys(r.address for r in rows if r.io == "out" and not r.is_reference))
        self.load(src)

    def load(self, steps):
        self.actions = C.to_actions(list(steps), self.nc, self.xy_base)
        self._rebuild()

    def steps(self):
        return C.to_rows(self.actions, self.nc)

    # ---------- แก้ ----------
    def add(self, kind: str):
        self.actions.append(C.default_action(kind, self.inputs, self.outputs))
        self._rebuild()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        self.changed.emit()

    def remove(self, i: int):
        del self.actions[i]
        self._rebuild()
        self.changed.emit()

    def move_to(self, i: int, d: int):
        n = i + d
        if 0 <= n < len(self.actions):
            a = self.actions
            a[i], a[n] = a[n], a[i]
            self._rebuild()
            self.changed.emit()

    def _set(self, a: C.Action, rebuild=False, **kw):
        for k, v in kw.items():
            setattr(a, k, v)
        a.touch()
        if rebuild:
            self._rebuild()
        self.changed.emit()

    def _set_cond(self, a: C.Action, i: int, rebuild=False, **kw):
        c = a.conds[i]
        d = {"addr": c.addr, "op": c.op, "value": c.value, "rel": c.rel, **kw}
        if _is_bit(d["addr"]) != _is_bit(c.addr):
            d.update(op="=", value=1, rel=False)
            rebuild = True
        conds = list(a.conds)
        conds[i] = Cond(**d)
        self._set(a, rebuild, conds=conds)

    # ---------- วาด ----------
    def _items(self, which: str) -> list[tuple[str, str]]:
        addrs = {"in": self.inputs, "out": self.outputs + [a for a in self.names if a not in self.outputs]}[which]
        return [(a, C.device_name(a, self.names)) for a in dict.fromkeys(addrs)]

    def _rebuild(self):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self.cards: list[QFrame] = []
        if not self.actions:
            lab = QLabel(tr("ยังไม่มีเงื่อนไข — กด ➕ สิ่งที่ทำ (เช่น กดปุ่ม Start) แล้ว ➕ สิ่งที่ต้องเกิด (เช่น มอเตอร์ติด)"))
            lab.setWordWrap(True)
            lab.setStyleSheet(f"color:{theme.TEXT_DIM};")
            lay.addWidget(lab)
        for i, a in enumerate(self.actions):
            card = self._card(i, a)
            self.cards.append(card)
            lay.addWidget(card)
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def _card(self, i: int, a: C.Action) -> QFrame:
        f = QFrame()
        col = theme.SUCCESS if a.is_check else theme.ACCENT2 if a.kind in C.CHECK else theme.TEXT_DIM
        f.setObjectName("CondCard")
        f.setStyleSheet(f"QFrame#CondCard {{ background:{theme.BG_INPUT}; border-left:4px solid {col}; border-radius:6px; }}")
        v = QVBoxLayout(f)
        v.setContentsMargins(8, 4, 6, 4)
        v.setSpacing(3)
        top = QHBoxLayout()
        flow = FlowLayout()
        flow.setSpacing(4)
        head = QLabel(f"{i + 1}")
        head.setStyleSheet(f"color:{col}; font-weight:bold;")
        flow.addWidget(head)
        if a.kind == "raw":
            flow.addWidget(QLabel(tr("คำสั่งเขียนเอง: {0}  (แก้ในโหมดขั้นสูง)", a.rows[0].text)))
        else:
            self._fields(flow, a)
        box = QWidget()
        box.setLayout(flow)
        top.addWidget(box, 1)
        for text, tip, fn in (("▲", tr("เลื่อนขึ้น"), lambda: self.move_to(i, -1)), ("▼", tr("เลื่อนลง"), lambda: self.move_to(i, 1)),
                              ("✖", tr("ลบ"), lambda: self.remove(i))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            top.addWidget(b, 0, Qt.AlignTop)
        v.addLayout(top)
        if a.is_check:
            ed = QLineEdit(a.msg)
            ed.setPlaceholderText(tr("ข้อความที่นักเรียนเห็น (เว้นว่าง = {0})", C.sentence(a, self.names)))
            ed.textEdited.connect(lambda t: self._set(a, msg=t.strip()))
            hint = QLineEdit(a.hint)
            hint.setPlaceholderText(tr("คำใบ้เมื่อไม่ผ่าน (เว้นว่างได้)"))
            hint.textEdited.connect(lambda t: self._set(a, hint=t.strip()))
            r2 = QHBoxLayout()
            r2.addWidget(ed, 1)
            r2.addWidget(hint, 1)
            v.addLayout(r2)
        return f

    def _fields(self, flow, a: C.Action):
        group = C.CHECK if a.kind in C.CHECK else C.DO
        cb = _Combo()
        for k in group:
            cb.addItem(C.kind_name(k), k)
        cb.setCurrentIndex(group.index(a.kind))
        cb.activated.connect(lambda _i: self._change_kind(a, cb.currentData()))
        flow.addWidget(cb)
        if a.kind in ("press", "down", "up", "word"):
            ab = AddrBox(a.addr, self._items("in"), self.xy_base)
            ab.picked.connect(lambda t: self._set(a, addr=t))
            flow.addWidget(ab)
        if a.kind == "word":
            sp = QSpinBox()
            sp.setRange(-32768, 32767)
            sp.setValue(a.value)
            sp.valueChanged.connect(lambda n: self._set(a, value=n))
            flow.addWidget(sp)
        if a.kind == "part":
            pb = _Combo()
            pb.addItem(tr("โลหะ"), "metal")
            pb.addItem(tr("พลาสติก"), "plastic")
            pb.setCurrentIndex(max(0, pb.findData(a.arg)))
            pb.activated.connect(lambda _i: self._set(a, arg=pb.currentData()))
            flow.addWidget(pb)
        if a.kind in C.CHECK:
            for n in range(len(a.conds)):
                if n:
                    flow.addWidget(QLabel(tr("และ")))
                self._cond(flow, a, n)
            b = QToolButton()
            b.setText(tr("+ และ"))
            b.setToolTip(tr("เพิ่มเงื่อนไขในประโยคเดียวกัน"))
            b.clicked.connect(lambda: self._set(a, True, conds=[*a.conds, Cond((self.outputs or ["Y0"])[-1], "=", 0)]))
            flow.addWidget(b)
        if a.kind in ("press", "wait", *C.CHECK):
            word = {"press": tr("นาน"), "wait": "", "hold": tr("ตลอด")}.get(a.kind, tr("ภายใน"))
            if word:
                flow.addWidget(QLabel(word))
            sec = _Sec(a.dur)
            sec.valueChanged.connect(lambda x: self._set(a, dur=round(x, 3)))
            flow.addWidget(sec)

    def _cond(self, flow, a: C.Action, n: int):
        c = a.conds[n]
        ab = AddrBox(c.addr, self._items("out"), self.xy_base)
        ab.picked.connect(lambda t: self._set_cond(a, n, addr=t))
        flow.addWidget(ab)
        if _is_bit(c.addr) and c.op in ("=", "==") and c.value in (0, 1) and not c.rel:
            cb = _Combo()
            cb.addItem(tr("ติด (1)"), 1)
            cb.addItem(tr("ดับ (0)"), 0)
            cb.setCurrentIndex(0 if c.value else 1)
            cb.activated.connect(lambda _i: self._set_cond(a, n, value=cb.currentData()))
            flow.addWidget(cb)
        else:
            op = _Combo()
            for o, t in (("=", "="), ("!=", "≠"), (">=", "≥"), ("<=", "≤"), (">", ">"), ("<", "<")):
                op.addItem(t, (o, False))
            op.addItem(tr("เพิ่มขึ้น ≥"), (">=", True))
            op.addItem(tr("เพิ่มขึ้น ="), ("=", True))
            want = ("=" if c.op == "==" else c.op, c.rel)
            idx = next((i for i in range(op.count()) if tuple(op.itemData(i)) == want), -1)
            if idx < 0:
                op.addItem((tr("เพิ่มขึ้น ") if c.rel else "") + c.op, want)
                idx = op.count() - 1
            op.setCurrentIndex(idx)
            op.activated.connect(lambda _i: self._set_cond(a, n, op=op.currentData()[0], rel=op.currentData()[1]))
            flow.addWidget(op)
            sp = QSpinBox()
            sp.setRange(-32768, 32767)
            sp.setValue(c.value)
            sp.valueChanged.connect(lambda x: self._set_cond(a, n, value=x))
            flow.addWidget(sp)
        if len(a.conds) > 1:
            b = QToolButton()
            b.setText("−")
            b.setToolTip(tr("เอาเงื่อนไขนี้ออก"))
            b.clicked.connect(lambda: self._set(a, True, conds=[x for i, x in enumerate(a.conds) if i != n]))
            flow.addWidget(b)

    def _change_kind(self, a: C.Action, kind: str):
        if kind == a.kind:
            return
        d = C.default_action(kind, self.inputs, self.outputs)
        self._set(a, True, kind=kind, addr=a.addr or d.addr, dur=d.dur, arg=a.arg or d.arg, conds=a.conds or d.conds)


def describe(text: str, xy_base: int = 8) -> str:
    """เงื่อนไขข้อความ → ประโยค (ใช้ใน tooltip)."""
    try:
        return " / ".join(C.cond_sentence(c, {}) for c in parse_conds(text, xy_base))
    except ValueError:
        return text
