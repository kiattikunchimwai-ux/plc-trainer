"""เครื่องมือบนผัง (โหมดแก้ไข): ช่องพิมพ์ข้อความตรงตำแหน่ง · แถบลอยเหนืออุปกรณ์ที่เลือก · มุมลากปรับขนาด."""
from __future__ import annotations

import shiboken6
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QPlainTextEdit, QToolButton, QWidget

from ...i18n import tr
from ...panel.catalog import LAMP_COLORS
from ...panel.specs import COLORABLE
from .. import theme


class InlineEdit(QPlainTextEdit):
    """ช่องพิมพ์บนผัง: คลิกที่อื่น / Ctrl+Enter = ตกลง · Esc = ยกเลิก (บรรทัดเดียว: Enter = ตกลง)."""
    done = Signal(str)
    cancelled = Signal()

    def __init__(self, parent, text: str, multiline: bool, hint: str = ""):
        super().__init__(parent)
        self.multiline = multiline
        self._over = False
        self.setPlainText(text)
        self.setPlaceholderText(hint)
        self.setStyleSheet(f"QPlainTextEdit {{ background:{theme.BG_INPUT}; color:{theme.TEXT};"
                           f" border:2px solid {theme.ACCENT2}; border-radius:6px; padding:2px; }}")
        if not multiline:
            self.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def value(self) -> str:
        t = self.toPlainText()
        return t if self.multiline else " ".join(t.split("\n"))

    def finish(self, ok: bool):
        if self._over:
            return
        self._over = True
        text = self.value()
        self.hide()
        self.deleteLater()
        if ok:
            self.done.emit(text)
        else:
            self.cancelled.emit()

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride:      # ระหว่างพิมพ์ คีย์ลัดของผัง/หน้าต่างต้องไม่ทำงาน
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            return self.finish(False)
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and (not self.multiline or e.modifiers() & Qt.ControlModifier):
            return self.finish(True)
        if e.key() == Qt.Key_Tab:
            return self.finish(True)
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if e.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            self.finish(True)

    def wheelEvent(self, e):
        e.accept()


class _Grip(QWidget):
    """มุมขวาล่างของ note / zone: ลากเพื่อปรับขนาด."""

    def __init__(self, view):
        super().__init__(view.viewport())
        self.view, self.item, self._from = view, None, None
        self._size = (0.0, 0.0)
        self.setFixedSize(14, 14)
        self.setCursor(Qt.SizeFDiagCursor)
        self.setToolTip(tr("ลากเพื่อปรับขนาด"))
        self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#FFFFFF"))
        p.setBrush(QColor(theme.ACCENT2))
        p.drawRoundedRect(1, 1, 12, 12, 3, 3)

    def _scene_pos(self, e):
        return self.view.mapToScene(self.view.viewport().mapFromGlobal(e.globalPosition().toPoint()))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.item is not None:
            r = self.item.mapRectToScene(self.item.body_rect())
            self._from = (r.topLeft(), self._scene_pos(e))
            self._size = (r.width(), r.height())

    def mouseMoveEvent(self, e):
        if self._from is None or self.item is None or not shiboken6.isValid(self.item):
            return
        top_left, start = self._from
        d = self._scene_pos(e) - start
        self.view.resize_item(self.item, top_left, self._size[0] + d.x(), self._size[1] + d.y())

    def mouseReleaseEvent(self, _e):
        if self._from is not None:
            self._from = None
            self.view.commit(tr("ปรับขนาด"))
            self.view._on_selection()


class FloatBar(QFrame):
    """แถบลอยเหนืออุปกรณ์ที่เลือก: แก้ข้อความ / address / สี / ขนาด / ทำซ้ำ / ลบ / ปรับแต่งทั้งหมด."""

    def __init__(self, view):
        super().__init__(view.viewport())
        self.view = view
        self.setObjectName("Floating")
        self.setCursor(Qt.ArrowCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(1)
        self.buttons: dict[str, QToolButton] = {}
        for key, text, tip, fn in (
                ("text", tr("✎ แก้ข้อความ"), tr("แก้ชื่อ/ข้อความ (ดับเบิลคลิก หรือ F2)"), lambda: view.edit_text()),
                ("addr", "X/Y", tr("แก้ Address"), lambda: view._ask_address(view.selected_items()[0])),
                ("color", "🎨", tr("เปลี่ยนสี"), self._colors),
                ("small", "A−", tr("ตัวอักษรเล็กลง"), lambda: view.bump_size(-1)),
                ("big", "A+", tr("ตัวอักษรใหญ่ขึ้น"), lambda: view.bump_size(1)),
                ("dup", "⧉", tr("ทำซ้ำ (Ctrl+D)"), lambda: view.duplicate_selected()),
                ("del", "🗑", tr("ลบ (Delete)"), lambda: view.remove_selected()),
                ("more", "⚙", tr("ปรับแต่งทั้งหมด"), lambda: view.props_requested.emit())):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            h.addWidget(b)
            self.buttons[key] = b
        self.grip = _Grip(view)
        self._shown: tuple = ()
        self.hide()

    def _colors(self):
        from .properties_dock import COLOR_TH
        m = QMenu(self)
        for k, rgb in LAMP_COLORS.items():
            px = QPixmap(16, 16)
            px.fill(QColor(rgb))
            a = QAction(QIcon(px), COLOR_TH.get(k, k), m)
            a.triggered.connect(lambda _=False, k=k: self.view.set_color(k))
            m.addAction(a)
        b = self.buttons["color"]
        m.exec(b.mapToGlobal(b.rect().bottomLeft()))

    def refresh(self):
        """เรียกทุก tick: ตามตำแหน่งอุปกรณ์ที่เลือก (ซ่อนในโหมดใช้งาน)."""
        v = self.view
        sel = [] if v.sc.run_mode or v.input_locked or v.editing_text() else v.selected_items()
        if not sel:
            if not self.isHidden() or not self.grip.isHidden():
                self.hide()
                self.grip.hide()
            self.grip.item = None
            return
        one = sel[0] if len(sel) == 1 else None
        kinds = {it.spec.kind for it in sel}
        on = {"text": one is not None, "addr": one is not None and bool(one.info.prefixes) and one.info.io != "none",
              "color": kinds <= set(COLORABLE), "small": kinds == {"note"}, "big": kinds == {"note"},
              "more": one is not None}
        shown = tuple(k for k in self.buttons if on.get(k, True))
        if shown != self._shown:
            self._shown = shown
            for k, b in self.buttons.items():
                b.setVisible(k in shown)
            self.adjustSize()
        box = QRectF()
        for it in sel:
            box = box.united(it.mapRectToScene(it.body_rect()))
        r = v.mapFromScene(box).boundingRect()
        vp = v.viewport().rect()
        x = max(4, min(r.center().x() - self.width() // 2, vp.width() - self.width() - 4))
        y = r.top() - self.height() - 12
        if y < 4:
            y = max(4, min(r.bottom() + 30, vp.height() - self.height() - 4))
        self.move(x, y)
        if self.isHidden():
            self.show()
            self.raise_()
        g = one if one is not None and one.spec.kind in ("note", "zone") else None
        if self.grip._from is None:
            self.grip.item = g
        if g is not None:
            self.grip.move(r.right() - 7, r.bottom() - 7)
        if self.grip.isHidden() != (g is None):
            self.grip.setVisible(g is not None)
            self.grip.raise_()


class InlineTools:
    """ส่วนเสริมของ PanelView."""

    def _init_inline(self):
        self._inline: InlineEdit | None = None
        self.floatbar = FloatBar(self)

    def editing_text(self) -> bool:
        return self._inline is not None

    def edit_text(self, item=None) -> bool:
        """เปิดช่องพิมพ์บนผังของอุปกรณ์นี้ (ป้ายข้อความ = เนื้อความ, อื่น ๆ = ชื่อ)."""
        if self.sc.run_mode or self.input_locked:
            return False
        if item is None:
            sel = self.selected_items()
            if len(sel) != 1:
                return False
            item = sel[0]
        self.finish_text()
        note = item.spec.kind == "note"
        prop = "text" if note else "label"
        if not item.isSelected():
            self.sc.clearSelection()
            item.setSelected(True)
        ed = InlineEdit(self.viewport(), str(item.prop(prop, "") or ""), note,
                        tr("พิมพ์ข้อความ… (คลิกที่อื่น = ตกลง · Esc = ยกเลิก)") if note else tr("ชื่อที่แสดงบนผัง"))
        f = ed.font()
        f.setPointSizeF(max(9.0, min(28.0, item._font().pointSizeF() * self.transform().m11())) if note else 11.0)
        ed.setFont(f)
        r = self.mapFromScene(item.mapRectToScene(item.body_rect())).boundingRect()
        vp = self.viewport().rect()
        w = max(220, r.width() + 16)
        h = max(90, r.height() + 24) if note else 38
        w, h = max(60, min(w, vp.width() - 8)), max(30, min(h, vp.height() - 8))
        y = r.top() - 6 if note else r.bottom() + 2
        ed.setGeometry(max(4, min(r.center().x() - w // 2, vp.width() - w - 4)), max(4, min(y, vp.height() - h - 4)), w, h)
        self._inline = ed
        ed.done.connect(lambda t, it=item: self._text_done(it, prop, t))
        ed.cancelled.connect(self._text_closed)
        ed.show()
        ed.raise_()
        ed.setFocus(Qt.OtherFocusReason)
        ed.selectAll()
        self.floatbar.refresh()
        return True

    def finish_text(self, ok: bool = True):
        ed = self._inline
        if ed is not None and shiboken6.isValid(ed):
            ed.finish(ok)
        self._inline = None

    def _text_closed(self):
        self._inline = None

    def _text_done(self, item, prop, text):
        self._text_closed()
        if not shiboken6.isValid(item) or self.items_by_id.get(item.spec.id) is not item:
            return
        if text != str(item.prop(prop, "") or ""):
            self._set_prop(item, prop, text, tr("แก้ข้อความ") if prop == "text" else tr("แก้ชื่อ"))

    # ---------- ปรับแต่งหลายชิ้น ----------
    def _set_many(self, changes, label):
        if self.sc.run_mode or self.input_locked or not changes:
            return
        for it, props in changes:
            it.prepareGeometryChange()
            it.spec.props.update(props)
            it.update()
        self.refresh_validation()
        self.commit(label)
        self._on_selection()
        self.changed.emit()

    def set_color(self, color: str):
        self._set_many([(it, {"color": color}) for it in self.selected_items() if it.spec.kind in COLORABLE],
                       tr("เปลี่ยนสี"))

    def bump_size(self, d: int):
        self._set_many([(it, {"size": max(6, min(40, int(float(it.prop("size", 10) or 10)) + 2 * d))})
                        for it in self.selected_items() if it.spec.kind == "note"], tr("เปลี่ยนขนาดตัวอักษร"))

    def resize_item(self, item, top_left: QPointF, w: float, h: float):
        """ปรับขนาด note/zone โดยให้มุมซ้ายบนอยู่ที่เดิม."""
        from . import items as base
        item.prepareGeometryChange()
        if item.spec.kind == "note":
            item.spec.props["width"] = int(max(60, min(1200, (w - 12) / base.SCALE)))
        else:
            item.spec.props["w"], item.spec.props["h"] = int(max(40, min(3000, w))), int(max(40, min(3000, h)))
        now = item.mapRectToScene(item.body_rect()).topLeft()
        self._move_free([(item, top_left.x() - now.x(), top_left.y() - now.y())])
        item.update()
