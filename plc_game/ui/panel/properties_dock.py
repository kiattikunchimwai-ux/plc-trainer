"""Properties: การ์ด ทั่วไป / การต่อสาย I/O / สเปกอุปกรณ์ (ดาต้าชีท) / การจำลอง — สร้างจาก KindInfo.specs.
มี "รุ่นสำเร็จรูป" ให้เลือกสเปกทั้งชุดในคลิกเดียว (1 ขั้น Undo)."""
from __future__ import annotations

from ...i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QLabel, QLineEdit, QPlainTextEdit, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)

from ...panel.catalog import CATALOG, IN_KINDS, LAMP_COLORS
from ...panel.model import conflicts, validate_address
from ...panel.presets import presets_for
from ...panel.specs import COLORABLE
from .. import theme

COLOR_TH = {"green": tr("เขียว"), "red": tr("แดง"), "orange": tr("ส้ม"), "yellow": tr("เหลือง"), "blue": tr("น้ำเงิน"), "white": tr("ขาว")}
IO_HINT = {"in": "→ PLC", "out": "PLC →", "word": "PLC →", "wordin": "→ PLC"}
GROUP_TITLE = {"spec": tr("📄 สเปกอุปกรณ์ (ดาต้าชีท)"), "sim": tr("⚙ การจำลอง")}

RUN_HINT = {"tank": tr("โหมดใช้งาน: คลิกที่ถัง = เปิด/ปิดก๊อกใช้น้ำ"),
            "overload": tr("โหมดใช้งาน: คลิก = ทริป / รีเซ็ต (ถ้ายังร้อนจะรีเซ็ตไม่ได้)"),
            "contactor": tr("หน้าสัมผัสช่วยจะ ON ตามคอยล์ (ใช้ทำ self-hold / ตรวจสอบได้)"),
            "pot": tr("โหมดใช้งาน: กดแล้วลากรอบปุ่มเพื่อหมุน"),
            "pusher": tr("วางเหนือสายพานให้แผ่นดันแตะชิ้นงานเมื่อยื่น · คลิกถาด = เทถาด"),
            "encoder": tr("ส่งพัลส์เมื่อมอเตอร์ที่ผูกไว้ ON · คลิก = ส่งพัลส์เอง"),
            "vfd": tr("ความถี่สั่งเป็น Hz×10 เช่น ค่า 500 = 50.0 Hz"),
            "conveyor": tr("ผูก D ความเร็วได้: 500 (50.0 Hz) = ความเร็วที่ตั้งไว้")}


class _NoWheel:
    """spinbox/combo ที่ไม่เปลี่ยนค่าเมื่อเลื่อนล้อเมาส์ผ่าน (ยกเว้นคลิกเลือกไว้แล้ว)."""

    def wheelEvent(self, e):  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class SpinBox(_NoWheel, QSpinBox):
    pass


class DoubleSpinBox(_NoWheel, QDoubleSpinBox):
    pass


class ComboBox(_NoWheel, QComboBox):
    pass


def _card(title: str) -> tuple[QGroupBox, QFormLayout]:
    g = QGroupBox(title)
    f = QFormLayout(g)
    f.setLabelAlignment(Qt.AlignRight)
    f.setContentsMargins(8, 6, 8, 6)
    f.setHorizontalSpacing(8)
    f.setVerticalSpacing(5)
    return g, f


class PropertiesPanel(QWidget):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.item = None
        self._addr_fields: dict[str, tuple[QLineEdit, QLabel]] = {}
        self.fields: dict[str, QWidget] = {}
        self.cb_preset: QComboBox | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)
        self._body = QWidget()
        self.scroll.setWidget(self._body)
        self.set_item(None)

    # ================= สร้างฟอร์ม =================
    def set_item(self, item):
        self.item = item
        self._addr_fields = {}
        self.fields = {}
        self.cb_preset = None
        self.ed_addr = self.addr_msg = None
        self._body = QWidget()
        lay = QVBoxLayout(self._body)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(6)
        self.scroll.setWidget(self._body)
        if item is None:
            msg = QLabel(tr("เลือกอุปกรณ์บนผังเพื่อแก้ไข\n\n• สลับเป็นโหมด ✎ แก้ไขผัง ก่อน\n"
                         "• Delete = ลบ   Ctrl+D = ทำซ้ำ\n• Ctrl+Z = ย้อนกลับ   Ctrl+Y = ทำซ้ำคำสั่ง\n"
                         "• ลูกศร = ขยับ   Ctrl+A = เลือกทั้งหมด\n"
                         "• คลิกขวา = เมนูอุปกรณ์ / วางอุปกรณ์\n"
                         "• ล้อเมาส์ = ซูม   ปุ่มกลางลาก = เลื่อน\n"
                         "• โหมดใช้งาน: กดคีย์ลัด (ป้ายขาวมุมอุปกรณ์) = กดปุ่ม"))
            msg.setStyleSheet(f"color:{theme.TEXT_DIM};")
            msg.setWordWrap(True)
            lay.addWidget(msg)
            lay.addStretch(1)
            return
        info = item.info

        # ---------- หัวการ์ด ----------
        head = QLabel(f"<b style='font-size:11pt'>{info.name}</b><br>"
                      f"<span style='color:{theme.TEXT_DIM}'>{info.desc}</span>")
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        presets = presets_for(item.spec.kind)
        if presets:
            cb = ComboBox()
            cb.addItem(tr("📦 เลือกรุ่นสำเร็จรูป…"), None)
            for name, _ in presets:
                cb.addItem(name, name)
            cb.setToolTip(tr("ตั้งสเปกทั้งชุดตามอุปกรณ์ทั่วไปในตลาด (ย้อนกลับได้ด้วย Ctrl+Z)"))
            cb.activated.connect(self._preset_chosen)
            self.cb_preset = cb
            lay.addWidget(cb)

        # ---------- ทั่วไป ----------
        g, form = _card(tr("ทั่วไป"))
        ed_label = QLineEdit(item.label)
        ed_label.textEdited.connect(lambda t: self._set("label", t))
        form.addRow(tr("ชื่อ"), ed_label)
        self.fields["label"] = ed_label
        if item.spec.kind in COLORABLE:
            cb = ComboBox()
            for k in LAMP_COLORS:
                cb.addItem(COLOR_TH[k], k)
            cb.setCurrentIndex(max(0, cb.findData(item.prop("color", "green"))))
            cb.currentIndexChanged.connect(lambda i, cb=cb: self._set("color", cb.itemData(i)))
            form.addRow(tr("สี"), cb)
            self.fields["color"] = cb
        if info.io == "in":
            cb = ComboBox()
            cb.addItem(tr("NO (ปกติเปิด)"), "NO")
            cb.addItem(tr("NC (ปกติปิด)"), "NC")
            cb.setCurrentIndex(1 if str(item.prop("contact", "NO")).upper() == "NC" else 0)
            cb.setToolTip(tr("NO = กด/ทำงานแล้วส่ง 1 · NC = ปกติส่ง 1 กด/ทำงานแล้วส่ง 0\n"
                          "อุปกรณ์ความปลอดภัย (Stop, E-Stop, OL) ใช้ NC: สายขาด = หยุด"))
            cb.currentIndexChanged.connect(lambda i, cb=cb: self._set("contact", cb.itemData(i)))
            form.addRow(tr("หน้าสัมผัส"), cb)
            self.fields["contact"] = cb
            ed_key = QLineEdit(item.key)
            ed_key.setMaxLength(1)
            ed_key.setFixedWidth(44)
            ed_key.setStyleSheet("font-family: Consolas;")
            ed_key.setToolTip(tr("โหมดใช้งาน: กดคีย์นี้บนคีย์บอร์ด = กดอุปกรณ์ (1–9, A–Z)"))
            ed_key.textEdited.connect(lambda t: (ed_key.setText(t.upper()), self._set("key", t.upper())))
            form.addRow(tr("คีย์ลัด"), ed_key)
        self._add_fields(form, [f for f in info.specs if f.group == "general"])
        lay.addWidget(g)

        # ---------- การต่อสาย I/O ----------
        slots = info.slots()
        if slots:
            g, form = _card(tr("🔌 การต่อสาย I/O"))
            for slot in slots:
                ed = QLineEdit(str(item.prop(slot.prop, "") or ""))
                ed.setStyleSheet("font-family: Consolas;")
                ed.setPlaceholderText(" / ".join(slot.prefixes) + (tr(" (เว้นว่างได้)") if slot.optional else ""))
                msg = QLabel()
                msg.setWordWrap(True)
                ed.textEdited.connect(lambda t, prop=slot.prop: self._slot_edited(prop, t))
                name = "Address" if len(slots) == 1 else f"{slot.label} {IO_HINT[slot.io]}"
                form.addRow(name, ed)
                form.addRow("", msg)
                self._addr_fields[slot.prop] = (ed, msg)
            self.ed_addr, self.addr_msg = self._addr_fields.get("address", (None, None))
            self._refresh_addr_states()
            lay.addWidget(g)

        # ---------- สเปก / การจำลอง ----------
        for grp in ("spec", "sim"):
            fs = [f for f in info.specs if f.group == grp]
            if fs:
                g, form = _card(GROUP_TITLE[grp])
                self._add_fields(form, fs)
                lay.addWidget(g)

        # ---------- คำอธิบาย ----------
        hint = {"in": tr("PLC อ่านสัญญาณจากอุปกรณ์นี้ (โปรแกรมเขียนค่าลง PLC)"),
                "out": tr("อุปกรณ์นี้ทำงานตามค่าจาก PLC"),
                "word": tr("แสดงค่าตัวเลขจาก PLC"),
                "wordin": tr("ตั้งค่าตัวเลขแล้วเขียนลง PLC"),
                "none": tr("ไม่ต่อกับ PLC — ใช้อธิบาย/จัดกลุ่มบนผัง")}[info.io]
        if len(slots) > 1:
            hint = tr("→ PLC = โปรแกรมเขียนค่าลง PLC (Input ของ ladder)\nPLC → = ทำงานตามค่าจาก PLC (Output ของ ladder)")
        extra = RUN_HINT.get(item.spec.kind, "")
        h = QLabel(hint + ("\n" + extra if extra else ""))
        h.setWordWrap(True)
        h.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:8pt;")
        lay.addWidget(h)
        lay.addStretch(1)

    def _add_fields(self, form: QFormLayout, fields):
        item = self.item
        for f in fields:
            val = item.sprop(f.prop)
            if f.type == "num":
                sp = DoubleSpinBox() if f.dec else SpinBox()
                if f.dec:
                    sp.setDecimals(f.dec)
                    sp.setRange(f.lo, f.hi)
                else:
                    sp.setRange(int(f.lo), int(f.hi))
                sp.setSingleStep(f.step)
                sp.setSuffix(f.unit)
                if f.special:
                    sp.setSpecialValueText(f.special)
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    num = f.lo
                sp.setValue(num if f.dec else int(round(num)))
                sp.valueChanged.connect(lambda v, prop=f.prop: self._set(prop, v))
                w = sp
            elif f.type == "choice":
                w = ComboBox()
                for v, txt in f.choices:
                    w.addItem(txt, v)
                w.setCurrentIndex(max(0, w.findData(str(val))))
                w.currentIndexChanged.connect(lambda i, w=w, prop=f.prop: self._set(prop, w.itemData(i)))
            elif f.type == "link":
                w = ComboBox()
                w.addItem(tr("— ไม่ผูก —"), "")
                for it in self.view.items_by_id.values():
                    if it.spec.kind in f.links and it is not item:
                        w.addItem(f"{it.shown_label or '-'} ({CATALOG[it.spec.kind].name})", it.spec.id)
                w.setCurrentIndex(max(0, w.findData(str(item.prop(f.prop, "") or ""))))
                w.currentIndexChanged.connect(lambda i, w=w, prop=f.prop: self._set(prop, w.itemData(i)))
            elif f.type == "mtext":
                w = QPlainTextEdit(str(val or ""))
                w.setFixedHeight(90)
                w.textChanged.connect(lambda w=w, prop=f.prop: self._set(prop, w.toPlainText()))
            else:
                w = QLineEdit(str(val or ""))
                w.textEdited.connect(lambda t, prop=f.prop: self._set(prop, t))
            if f.help:
                w.setToolTip(f.help)
            lab = QLabel(f.label + (" ⓘ" if f.help else ""))
            if f.help:
                lab.setToolTip(f.help)
            form.addRow(lab, w)
            self.fields[f.prop] = w

    # ================= รุ่นสำเร็จรูป =================
    def _preset_chosen(self, index: int):
        name = self.cb_preset.itemData(index) if self.cb_preset else None
        if name:
            self.apply_preset(name)

    def apply_preset(self, name: str) -> bool:
        """ตั้งค่าทั้งชุดของรุ่นที่เลือก แล้วบันทึกเป็น 1 ขั้น Undo."""
        if self.item is None:
            return False
        props = dict(presets_for(self.item.spec.kind)).get(name)
        if props is None:
            return False
        self.view.flush_commit()
        self.item.spec.props.update(props)
        self.view.item_props_changed(self.item)
        self.view._pending_text = tr("ใช้รุ่น: {0}", name)
        self.view.flush_commit()
        self.view.status.emit(tr("📦 ตั้งสเปกตามรุ่น: {0}", name))
        self.set_item(self.item)
        return True

    # ================= แก้ค่า =================
    def _set(self, key, value):
        if self.item is None:
            return
        self.item.spec.props[key] = value
        self.view.item_props_changed(self.item)

    def _addr_edited(self, text):
        """แก้ address หลัก (คงไว้ให้สคริปต์/เทสต์เดิมเรียกได้)."""
        self._slot_edited("address", text)

    def _slot_edited(self, prop, text):
        if self.item is None:
            return
        self.item.spec.props[prop] = text.strip().upper()
        self.view.item_props_changed(self.item)
        self._refresh_addr_states()

    def _refresh_addr_states(self):
        item = self.item
        bad = conflicts([it.spec for it in self.view.items_by_id.values()], self.view.xy_base)
        for prop, (ed, lab) in self._addr_fields.items():
            slot = item.info.slot(prop)
            ok, msg = validate_address(item.spec.kind, ed.text(), self.view.xy_base, prop)
            if ok and not msg:
                msg, color = tr("ไม่ใช้"), theme.TEXT_DIM
            elif ok and slot.io in IN_KINDS and msg in bad:
                ok, color = False, theme.DANGER
                msg = tr("⚠ {0} ถูกใช้โดย Input อื่นแล้ว (สัญญาณจะเขียนทับกัน)", msg)
            elif ok:
                msg, color = tr("✔ ต่อกับ {0}", msg), theme.SUCCESS
            else:
                color = theme.DANGER
            ed.setStyleSheet("font-family: Consolas;" + ("" if ok else f"border:1px solid {theme.DANGER};"))
            lab.setText(msg)
            lab.setStyleSheet(f"color:{color}; font-size:8pt;")
