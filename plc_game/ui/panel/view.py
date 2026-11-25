"""พื้นที่วางอุปกรณ์ (model space แบบ AutoCAD): กริด, ซูม/แพน, ลากวาง, โหมด EDIT/RUN, Undo/Redo."""
from __future__ import annotations

from ...i18n import tr

import time

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QInputDialog, QMenu

from ...panel.catalog import CATALOG, CATEGORIES, IN_KINDS
from ...panel.model import DeviceSpec, PanelDoc, conflicts, validate_address
from .. import theme
from .items import ConveyorItem, DeviceItem, InputItem, SensorItem, WorkpieceItem, make_item
from .inline_edit import InlineTools
from .items_ext import PusherItem

MIME = "application/x-plc-device"
CLIP_MIME = "application/x-plc-devices"
HOTKEYS = [str(i) for i in range(1, 10)] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]


class PanelScene(QGraphicsScene):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.run_mode = True
        self.snap = 20
        self.show_grid = True
        self.faults_hidden = False   # โหมดสอบ: ไม่แสดงป้าย ⚡ บนอุปกรณ์
        self.setSceneRect(-3000, -3000, 6000, 6000)

    def item_moved(self):
        self.owner._schedule_changed()

    def drawBackground(self, p: QPainter, rect: QRectF):
        p.fillRect(rect, QColor(theme.BG_CANVAS))
        if not self.show_grid:
            return
        minor, major = 20, 100
        left = int(rect.left()) - int(rect.left()) % minor
        top = int(rect.top()) - int(rect.top()) % minor
        pen_minor = QPen(QColor(theme.GRID_MINOR), 0)
        pen_major = QPen(QColor(theme.GRID_MAJOR), 0)
        x = left
        while x < rect.right():
            p.setPen(pen_major if x % major == 0 else pen_minor)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += minor
        y = top
        while y < rect.bottom():
            p.setPen(pen_major if y % major == 0 else pen_minor)
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += minor


class SnapshotCommand(QUndoCommand):
    """Undo แบบเก็บทั้งผัง (JSON) ก่อน/หลัง — เรียบง่ายและครอบคลุมทุกการแก้ไข."""

    def __init__(self, view, before: str, after: str, text: str):
        super().__init__(text)
        self.view, self.before, self.after = view, before, after
        self._first = True

    def redo(self):
        if self._first:          # ตอน push ผังเปลี่ยนไปแล้ว
            self._first = False
            return
        self.view._restore(self.after)

    def undo(self):
        self.view._restore(self.before)


class PanelView(InlineTools, QGraphicsView):
    changed = Signal()
    props_requested = Signal()            # แถบลอย ⚙ → เปิดแผงคุณสมบัติ
    request_write = Signal(str, int)
    request_write_word = Signal(str, int)
    selection_changed = Signal(object)    # DeviceItem | None
    status = Signal(str)
    edit_requested = Signal()
    faults_changed = Signal()
    fault_guessed = Signal(object, str)   # ด่านหาจุดเสีย: (DeviceItem, รหัสอาการ)
    knowledge_requested = Signal(object)  # คลิกขวา → ใบความรู้ (DeviceItem)

    def __init__(self, xy_base: int = 8, parent=None):
        super().__init__(parent)
        self.xy_base = xy_base
        self.input_locked = False         # True = กำลังตรวจด่าน ไม่รับการกดจากผู้ใช้
        self.guess_enabled = False
        self.sc = PanelScene(self)
        self.setScene(self.sc)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_by_id: dict[str, DeviceItem] = {}
        self._init_inline()
        self.doc_name = tr("ผังใหม่")
        self._pan = None
        self._auto_fit = True       # ปรับผังให้พอดีจอเมื่อขนาดเปลี่ยน จนกว่าผู้ใช้จะซูม/เลื่อนเอง
        self._keys_down: dict[str, DeviceItem] = {}
        self.sc.selectionChanged.connect(self._on_selection)

        self.undo = QUndoStack(self)
        self._last_json = PanelDoc().to_json()
        self._restoring = False
        self._commit_timer = QTimer(self, singleShot=True, interval=700)
        self._pending_text = tr("แก้คุณสมบัติ")
        self._commit_timer.timeout.connect(lambda: self.commit(self._pending_text))

        self._changed_timer = QTimer(self, singleShot=True, interval=250)
        self._changed_timer.timeout.connect(self.changed.emit)
        self._last_tick = time.monotonic()
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(33)

        QShortcut(QKeySequence.Delete, self, activated=self.remove_selected)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self.duplicate_selected)
        self.set_run_mode(True)

    # ================= document =================
    def clear_panel(self):
        for it in list(self.items_by_id.values()):
            self._remove_item(it)
        self.items_by_id.clear()

    def _build(self, doc: PanelDoc):
        self.finish_text(False)
        self.clear_panel()
        self.doc_name = doc.name
        for spec in doc.devices:
            self._add_item(make_item(spec))
        self.refresh_validation()

    def load_doc(self, doc: PanelDoc):
        self._build(doc)
        self.undo.clear()
        self._last_json = self.to_doc().to_json()
        self.undo.setClean()
        self.fit_all()
        self.changed.emit()

    def to_doc(self) -> PanelDoc:
        return PanelDoc(name=self.doc_name, devices=[it.spec for it in self.items_by_id.values()])

    # ================= undo / redo =================
    def commit(self, text: str):
        """บันทึกสถานะผังปัจจุบันเป็น 1 ขั้นของ Undo (ถ้ามีอะไรเปลี่ยน)."""
        if self._restoring:
            return
        self._commit_timer.stop()
        now = self.to_doc().to_json()
        if now != self._last_json:
            self.undo.push(SnapshotCommand(self, self._last_json, now, text))
            self._last_json = now

    def flush_commit(self):
        self.finish_text()
        if self._commit_timer.isActive():
            self.commit(self._pending_text)

    def do_undo(self):
        self.flush_commit()
        if self.undo.canUndo():
            self.status.emit(tr("↶ ย้อนกลับ: {0}", self.undo.undoText()))
            self.undo.undo()

    def do_redo(self):
        self.flush_commit()
        if self.undo.canRedo():
            self.status.emit(tr("↷ ทำซ้ำ: {0}", self.undo.redoText()))
            self.undo.redo()

    def _restore(self, js: str):
        sel = {it.spec.id for it in self.items_by_id.values() if it.isSelected()}
        faults = {it.spec.id: it.fault for it in self.items_by_id.values() if it.fault}
        self._restoring = True
        try:
            self._build(PanelDoc.from_json(js))
            if not self.sc.run_mode:
                for i in sel:
                    if i in self.items_by_id:
                        self.items_by_id[i].setSelected(True)
            for i, code in faults.items():          # Undo ไม่ล้างความผิดปกติที่ครูใส่ไว้
                if i in self.items_by_id:
                    self.items_by_id[i].set_fault(code)
        finally:
            self._restoring = False
        self._last_json = js
        self._on_selection()
        self.changed.emit()

    # ================= items =================
    def _add_item(self, item: DeviceItem) -> DeviceItem:
        self.sc.addItem(item)
        self.items_by_id[item.spec.id] = item
        item.request_write.connect(self.request_write.emit)
        item.request_write_word.connect(self.request_write_word.emit)
        item.setZValue(item.Z)
        self._apply_mode(item)
        return item

    def _apply_mode(self, it: DeviceItem):
        run = self.sc.run_mode
        it.setFlag(it.GraphicsItemFlag.ItemIsMovable, not run)
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, not run)
        it.setCursor(Qt.PointingHandCursor if run else Qt.SizeAllCursor)
        it.update()

    def _remove_item(self, item: DeviceItem):
        if isinstance(item, ConveyorItem):
            item.clear_parts()
        self.items_by_id.pop(item.spec.id, None)
        self._keys_down = {k: v for k, v in self._keys_down.items() if v is not item}
        self.sc.removeItem(item)

    def add_device(self, kind: str, scene_pos: QPointF | None = None) -> DeviceItem:
        if scene_pos is None:
            scene_pos = self.mapToScene(self.viewport().rect().center())
        g = self.sc.snap or 1
        spec = DeviceSpec.new(kind, round(scene_pos.x() / g) * g, round(scene_pos.y() / g) * g)
        self._suggest_inputs(spec)
        if CATALOG[kind].io == "in":
            spec.props["key"] = self._suggest_key()
        item = self._add_item(make_item(spec))
        self.refresh_validation()
        if not self.sc.run_mode:
            self.sc.clearSelection()
            item.setSelected(True)
        self.status.emit(tr("วาง {0} ที่ {1}", CATALOG[kind].name, spec.address))
        self.commit(tr("วาง {0}", CATALOG[kind].name))
        self.changed.emit()
        return item

    def _used_inputs(self) -> set[str]:
        return {a.upper() for it in self.items_by_id.values() for _, io, a in it.spec.all_io() if io in IN_KINDS and a}

    def _suggest_inputs(self, spec: DeviceSpec):
        """ตั้ง address ของทุกช่อง Input ให้เป็นเลขถัดไปที่ยังว่าง (เช่น X0 ใช้แล้ว → X1)."""
        from ...plc.device import parse_device
        used = self._used_inputs()
        for slot in CATALOG[spec.kind].slots():
            if slot.io not in IN_KINDS:
                continue
            default = str(spec.props.get(slot.prop, "") or CATALOG[spec.kind].defaults.get(slot.prop, ""))
            if not default:
                continue          # ช่องเสริมที่เว้นว่างไว้
            try:
                d = parse_device(default, self.xy_base)
            except ValueError:
                continue
            for i in range(256):
                cand = d.offset(i).name
                if cand not in used:
                    spec.props[slot.prop] = cand
                    used.add(cand)
                    break

    def _suggest_key(self) -> str:
        used = {it.key for it in self.items_by_id.values()}
        return next((k for k in HOTKEYS if k not in used), "")

    def selected_items(self) -> list[DeviceItem]:
        return [i for i in self.sc.selectedItems() if isinstance(i, DeviceItem)]

    def remove_selected(self):
        if self.sc.run_mode:
            return
        sel = self.selected_items()
        for it in sel:
            self._remove_item(it)
        if sel:
            self.refresh_validation()
            self.commit(tr("ลบ {0} ชิ้น", len(sel)))
            self.changed.emit()

    def duplicate_selected(self):
        if self.sc.run_mode:
            return
        sel = self.selected_items()
        self._paste_new([it.spec for it in sel], tr("ทำซ้ำ {0} ชิ้น", len(sel)))

    # ---------- จัดวาง (โหมดแก้ไข) ----------
    ALIGN_NAMES = {"left": tr("ชิดซ้าย"), "hcenter": tr("กึ่งกลางแนวตั้ง"), "right": tr("ชิดขวา"),
                   "top": tr("ชิดบน"), "vcenter": tr("กึ่งกลางแนวนอน"), "bottom": tr("ชิดล่าง")}

    @staticmethod
    def _box(it: DeviceItem):
        return it.mapRectToScene(it.body_rect())

    def _move_free(self, moves):
        """ย้ายหลายชิ้นโดยไม่ให้ snap ปัดตำแหน่ง — moves = [(item, dx, dy)]."""
        snap, self.sc.snap = self.sc.snap, 0
        try:
            for it, dx, dy in moves:
                if dx or dy:
                    it.setPos(it.pos().x() + dx, it.pos().y() + dy)
        finally:
            self.sc.snap = snap

    def align(self, mode: str) -> int:
        """จัดแนวชิ้นที่เลือก (ต้อง ≥ 2 ชิ้น) อิงขอบของกลุ่ม."""
        sel = self.selected_items()
        if self.sc.run_mode or len(sel) < 2 or mode not in self.ALIGN_NAMES:
            self.status.emit(tr("เลือกอุปกรณ์อย่างน้อย 2 ชิ้นก่อน (โหมดแก้ไข: ลากกรอบหรือ Ctrl+คลิก)"))
            return 0
        boxes = {it: self._box(it) for it in sel}
        left = min(b.left() for b in boxes.values())
        right = max(b.right() for b in boxes.values())
        top = min(b.top() for b in boxes.values())
        bottom = max(b.bottom() for b in boxes.values())
        cx, cy = (left + right) / 2, (top + bottom) / 2
        moves = []
        for it, b in boxes.items():
            dx = {"left": left - b.left(), "right": right - b.right(), "hcenter": cx - b.center().x()}.get(mode, 0)
            dy = {"top": top - b.top(), "bottom": bottom - b.bottom(), "vcenter": cy - b.center().y()}.get(mode, 0)
            moves.append((it, dx, dy))
        self._move_free(moves)
        self.commit(tr("จัดแนว{0}", tr(self.ALIGN_NAMES[mode])))
        self.status.emit(tr("จัดแนว{0} {1} ชิ้น", tr(self.ALIGN_NAMES[mode]), len(sel)))
        self.changed.emit()
        return len(sel)

    def distribute(self, axis: str) -> int:
        """กระจายระยะห่างให้เท่ากัน (ต้อง ≥ 3 ชิ้น) — axis = 'h' แนวนอน / 'v' แนวตั้ง."""
        sel = self.selected_items()
        if self.sc.run_mode or len(sel) < 3:
            self.status.emit(tr("เลือกอุปกรณ์อย่างน้อย 3 ชิ้นก่อนกระจายระยะ"))
            return 0
        h = axis.lower().startswith("h")
        boxes = sorted(((it, self._box(it)) for it in sel), key=lambda p: p[1].left() if h else p[1].top())
        first, last = boxes[0][1], boxes[-1][1]
        span = (last.right() - first.left()) if h else (last.bottom() - first.top())
        total = sum(b.width() if h else b.height() for _, b in boxes)
        gap = (span - total) / (len(boxes) - 1)
        pos = first.left() if h else first.top()
        moves = []
        for it, b in boxes:
            moves.append((it, pos - b.left(), 0) if h else (it, 0, pos - b.top()))
            pos += (b.width() if h else b.height()) + gap
        self._move_free(moves)
        word = tr("แนวนอน") if h else tr("แนวตั้ง")
        self.commit(tr("กระจายระยะ{0}", word))
        self.status.emit(tr("กระจายระยะ{0} {1} ชิ้น", word, len(sel)))
        self.changed.emit()
        return len(sel)

    def nudge(self, dx: float, dy: float) -> bool:
        sel = self.selected_items()
        if self.sc.run_mode or not sel:
            return False
        self._move_free([(it, dx, dy) for it in sel])
        self._pending_text = tr("ขยับอุปกรณ์")
        self._commit_timer.start()          # กดลูกศรต่อเนื่อง = 1 ขั้น Undo
        self.changed.emit()
        return True

    def select_all(self):
        if self.sc.run_mode:
            return
        for it in self.items_by_id.values():
            it.setSelected(True)

    def keyPressEvent(self, e):
        steps = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in steps and not self.sc.run_mode:
            sx, sy = steps[e.key()]
            g = 1 if (e.modifiers() & Qt.ShiftModifier) or not self.sc.snap else self.sc.snap
            if self.nudge(sx * g, sy * g):
                e.accept()
                return
        if e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier and not self.sc.run_mode:
            self.select_all()
            e.accept()
            return
        if not self.sc.run_mode and not self.input_locked:
            if e.key() == Qt.Key_F2 and self.edit_text():
                e.accept()
                return
            vk = e.nativeVirtualKey() or int(e.key())      # แป้นไทย: ใช้รหัสปุ่มจริง
            if e.modifiers() & Qt.ControlModifier and not e.modifiers() & (Qt.AltModifier | Qt.ShiftModifier):
                fn = {ord("C"): self.copy_selected, ord("V"): self.paste_devices}.get(vk)
                if fn and fn():
                    e.accept()
                    return
        super().keyPressEvent(e)

    def copy_selected(self) -> int:
        sel = self.selected_items()
        if sel:
            md = QMimeData()
            md.setData(CLIP_MIME, PanelDoc(devices=[it.spec for it in sel]).to_json().encode())
            QApplication.clipboard().setMimeData(md)
            self.status.emit(tr("คัดลอก {0} ชิ้น", len(sel)))
        return len(sel)

    def paste_devices(self) -> int:
        """วางอุปกรณ์ที่คัดลอก (input ได้ address ว่างถัดไป, การผูกระหว่างชิ้นที่คัดลอกมาด้วยกันยังอยู่)."""
        md = QApplication.clipboard().mimeData()
        if self.sc.run_mode or md is None or not md.hasFormat(CLIP_MIME):
            return 0
        try:
            src = PanelDoc.from_json(bytes(md.data(CLIP_MIME)).decode()).devices
        except (ValueError, TypeError, AttributeError, KeyError):
            return 0
        self._paste_new(src, tr("วาง {0} ชิ้น", len(src)))
        return len(src)

    def _paste_new(self, src: list, text: str):
        new = [DeviceSpec(kind=d.kind, x=d.x + 40, y=d.y + 40, props=dict(d.props)) for d in src]
        ids = {d.id: n.id for d, n in zip(src, new)}
        self.sc.clearSelection()
        for spec in new:
            for k, v in spec.props.items():
                if isinstance(v, str) and v in ids:
                    spec.props[k] = ids[v]
            self._suggest_inputs(spec)
            if CATALOG[spec.kind].io == "in":
                spec.props["key"] = self._suggest_key()
            self._add_item(make_item(spec)).setSelected(True)
        if new:
            self.refresh_validation()
            self.commit(text)
            self.changed.emit()

    def item_props_changed(self, item: DeviceItem):
        self.refresh_validation()
        item.prepareGeometryChange()
        item.update()
        if isinstance(item, ConveyorItem):
            for wp in item.parts:
                wp.place()
        self._pending_text = tr("แก้คุณสมบัติ")
        self._commit_timer.start()          # รวมการพิมพ์ต่อเนื่องเป็น 1 ขั้น Undo
        self.changed.emit()

    def refresh_validation(self):
        bad = conflicts([it.spec for it in self.items_by_id.values()], self.xy_base)
        bad_ids = {i for ids in bad.values() for i in ids}
        for it in self.items_by_id.values():
            it.slot_ok = {}
            all_ok = True
            for slot in it.info.slots():
                ok, name = validate_address(it.spec.kind, it.spec.props.get(slot.prop, ""), self.xy_base, slot.prop)
                if ok and name:
                    it.spec.props[slot.prop] = name          # ทำให้เป็นชื่อมาตรฐาน เช่น x0 → X0
                it.slot_ok[slot.prop] = (ok and bool(name), name)   # ช่องว่างที่เว้นได้ = ไม่ใช้งาน
                all_ok &= ok
            it.valid = all_ok
            it.conflict = it.spec.id in bad_ids
            it.refresh_tooltip()
            it.update()
        return bad

    # ================= runtime =================
    def set_run_mode(self, run: bool):
        self.flush_commit()
        self.sc.run_mode = run
        if run:
            self.sc.clearSelection()
        self.release_all_keys()
        self.setDragMode(QGraphicsView.NoDrag if run else QGraphicsView.RubberBandDrag)
        for it in self.items_by_id.values():
            self._apply_mode(it)
        self.viewport().update()

    def addresses(self) -> list[str]:
        """address ทั้งหมดที่ถูกต้องในผัง (ใช้กำหนดว่าจะอ่านอะไรจาก PLC)."""
        return sorted({a for it in self.items_by_id.values() for s in it.info.slots() if (a := it.addr_of(s.prop))})

    def input_states(self) -> list[tuple[str, int, bool]]:
        """ค่าปัจจุบันของทุก Input ในผัง: [(address, ค่า, เป็น word)] — เขียนลง PLC ตอนเชื่อมต่อ."""
        return [s for it in self.items_by_id.values() for s in it.input_signals()]

    def apply_snapshot(self, snap: dict):
        stamp = None
        for it in self.items_by_id.values():
            before = it.state_text()
            it.apply_snapshot(snap)
            if it.state_text() != before:
                stamp = stamp or time.strftime("%H:%M:%S")
                it.last_change = stamp
                it.refresh_tooltip()

    def items_at(self, address: str) -> list[DeviceItem]:
        return [it for it in self.items_by_id.values() if it.addr == address.upper()]

    def press(self, address: str, hold_ms: int = 500):
        """สาธิต: กดอุปกรณ์ Input ที่ใช้ address นี้ (ไฮไลต์ให้เห็น)."""
        for it in self.items_at(address):
            if isinstance(it, InputItem):
                it.flash(hold_ms + 300)
                it.set_actuated(True)
                QTimer.singleShot(hold_ms, lambda it=it: it.set_actuated(False))
                return True
        return False

    def drive_input(self, address: str, value: int, is_word: bool = False) -> bool:
        """ตัวตรวจด่านสั่ง input ผ่านอุปกรณ์บนผัง (ให้เห็นปุ่มขยับ) — value คือค่าที่ PLC ต้องเห็น
        ปุ่ม NC จึงถูก "กด" เมื่อ value = 0. คืน False ถ้าไม่มีอุปกรณ์ที่ใช้ address นี้."""
        for it in self.items_at(address):
            if is_word and hasattr(it, "set_value") and it.info.io == "wordin":
                it.set_value(value)
                return True
            if not is_word and isinstance(it, InputItem):
                act = bool(value) != it.nc
                if hasattr(it, "manual"):          # เซนเซอร์: จำว่าเป็นการสั่งด้วยมือ
                    it.manual = act
                it.set_actuated(act or getattr(it, "detected", False))
                return True
        return False

    def spawn_part(self, material: str = "metal") -> bool:
        """ปล่อยชิ้นงานบนสายพานตัวแรก (ใช้ในด่าน)."""
        for it in self.conveyors():
            n = len(it.parts)
            it.spawn()
            if len(it.parts) > n:
                it.parts[-1].set_material(material)
                return True
        return False

    # ---------- คีย์ลัด (เรียกจาก MainWindow) ----------
    def key_down(self, key: str) -> bool:
        if not self.sc.run_mode or not key or self.input_locked:
            return False
        key = key.upper()
        hit = False
        for it in self.items_by_id.values():
            if it.key == key and isinstance(it, InputItem) and key not in self._keys_down:
                it.on_press(QPointF())
                it.flash(250)
                self._keys_down[key] = it
                hit = True
        return hit

    def key_up(self, key: str) -> bool:
        it = self._keys_down.pop(key.upper(), None)
        if it is None:
            return False
        it.on_release(QPointF())
        return True

    def release_all_keys(self):
        for k in list(self._keys_down):
            self.key_up(k)

    def apply_addresses(self, changes: dict[str, dict[str, str]], text: str = ""):
        """เปลี่ยน address หลายช่องพร้อมกันเป็น 1 ขั้น Undo — changes = {device_id: {prop: address}}."""
        text = text or tr("จัด address อัตโนมัติ")
        for i, props in changes.items():
            it = self.items_by_id.get(i)
            if it:
                it.spec.props.update(props)
        if changes:
            self.refresh_validation()
            for it in self.items_by_id.values():
                it.prepareGeometryChange()
                it.update()
            self.commit(text)
            self._on_selection()
            self.changed.emit()

    # ---------- Fault Injection ----------
    def fault_items(self) -> list[DeviceItem]:
        """อุปกรณ์ที่ใส่ความผิดปกติได้ เรียงตามตำแหน่ง (บน→ล่าง ซ้าย→ขวา)."""
        its = [it for it in self.items_by_id.values() if it.FAULTS]
        return sorted(its, key=lambda it: (round(it.y() / 40), it.x()))

    def find_item(self, name: str) -> DeviceItem | None:
        """หาอุปกรณ์จากชื่อ (label) หรือ address หลัก (ไม่สนตัวพิมพ์เล็ก/ใหญ่)."""
        n = name.strip().upper()
        for it in self.fault_items():
            if it.label.upper() == n or it.addr == n:
                return it
        return None

    def set_fault(self, item: DeviceItem, code: str):
        item.set_fault(code)
        self.faults_changed.emit()

    def clear_faults(self) -> int:
        n = 0
        for it in self.items_by_id.values():
            if it.fault:
                it.set_fault("")
                n += 1
        self.faults_changed.emit()
        return n

    def random_fault(self, rng=None) -> tuple[DeviceItem, str] | None:
        """สุ่มใส่ความผิดปกติ 1 จุด ในอุปกรณ์ที่ยังปกติอยู่."""
        import random
        rng = rng or random
        cands = [it for it in self.fault_items() if not it.fault]
        if not cands:
            return None
        it = rng.choice(cands)
        code = rng.choice(list(it.FAULTS))
        self.set_fault(it, code)
        return it, code

    def guess_menu(self, m: QMenu, item: DeviceItem) -> QMenu:
        """เมนูย่อย 'แจ้งว่าอุปกรณ์นี้เสีย' — แสดงอาการทุกแบบของอุปกรณ์นั้น (ไม่บอกว่าแบบไหนจริง)."""
        sub = m.addMenu(tr("🔍 แจ้งว่า '{0}' เสีย", item.shown_label or item.info.name))
        for code, text in item.FAULTS.items():
            sub.addAction(text, lambda it=item, c=code: self.fault_guessed.emit(it, c))
        return sub

    def set_faults_hidden(self, hidden: bool):
        self.sc.faults_hidden = hidden
        for it in self.items_by_id.values():
            it.refresh_tooltip()
            it.update()

    def conveyors(self) -> list[ConveyorItem]:
        return [it for it in self.items_by_id.values() if isinstance(it, ConveyorItem)]

    def _tick(self):
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.1)
        self._last_tick = now
        self.step(dt)
        self.floatbar.refresh()

    def step(self, dt: float):
        """จำลองอุปกรณ์ไปข้างหน้า dt วินาที (เรียกเองได้ใน test ด้วยนาฬิกาจำลอง)."""
        for it in list(self.items_by_id.values()):
            it.tick(dt)
        parts = [i for i in self.sc.items() if isinstance(i, WorkpieceItem)]
        for it in self.items_by_id.values():      # ตัวดันคัดแยก: ยื่นลงชนชิ้นงาน → ชิ้นงานลงถาด
            if isinstance(it, PusherItem) and it.pos_k > 0.3:
                rod = it.rod_scene_rect()
                for wp in [w for w in parts if w.sceneBoundingRect().intersects(rod)]:
                    wp.conveyor.remove_part(wp)
                    parts.remove(wp)
                    it.bin_count += 1
                    it.update()
        for it in self.items_by_id.values():
            if isinstance(it, SensorItem):
                beam = it.beam_scene_rect()
                it.set_detected(any(it.sees(wp) and wp.sceneBoundingRect().intersects(beam) for wp in parts))
            elif hasattr(it, "detect_parts"):          # ม่านแสง / เครื่องอ่านบาร์โค้ด
                it.detect_parts(parts)

    def find_device(self, dev_id: str):
        return self.items_by_id.get(dev_id)

    # ================= view navigation =================
    def fit_all(self):
        self._auto_fit = True
        r = self.sc.itemsBoundingRect()
        if r.isEmpty():
            r = QRectF(-300, -200, 600, 400)
        self.fitInView(r.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)
        if self.transform().m11() > 1.6:
            self.resetTransform()
            self.scale(1.6, 1.6)
            self.centerOn(r.center())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._auto_fit:
            self.fit_all()

    def zoom_by(self, f: float):
        self._auto_fit = False
        s = self.transform().m11() * f
        if 0.2 < s < 4:
            self.scale(f, f)

    def wheelEvent(self, e):
        self.finish_text()
        self._auto_fit = False
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        s = self.transform().m11() * f
        if 0.2 < s < 4:
            self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan = e.position()
            self._auto_fit = False
            self.viewport().setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        if self.input_locked and self.sc.run_mode:       # กำลังตรวจด่าน: ห้ามแทรก input
            self.status.emit(tr("กำลังตรวจคำตอบ — กดอุปกรณ์ไม่ได้จนกว่าจะตรวจเสร็จ"))
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.translate_view(d)
            e.accept()
            return
        sp = self.mapToScene(e.position().toPoint())
        self.status.emit(f"X = {sp.x():.0f}   Y = {-sp.y():.0f}")
        super().mouseMoveEvent(e)

    def translate_view(self, d):
        s = self.transform().m11()
        c = self.mapToScene(self.viewport().rect().center())
        self.centerOn(c - QPointF(d.x() / s, d.y() / s))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton and not self.sc.run_mode:
            self.commit(tr("ย้ายอุปกรณ์"))       # ลากย้ายเสร็จ = 1 ขั้น Undo

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MiddleButton:   # ดับเบิลคลิกปุ่มกลาง = Zoom Extents แบบ AutoCAD
            self.fit_all()
            return
        if self.input_locked and self.sc.run_mode:
            e.accept()
            return
        if not self.sc.run_mode and e.button() == Qt.LeftButton:
            item = self._item_at(e.position().toPoint())
            if item is not None and self.edit_text(item):
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    # ================= เมนูคลิกขวา =================
    def _item_at(self, view_pos) -> DeviceItem | None:
        for gi in self.items(view_pos):
            while gi is not None and not isinstance(gi, DeviceItem):
                gi = gi.parentItem()
            if isinstance(gi, DeviceItem):
                return gi
        return None

    def contextMenuEvent(self, e):
        if self.sc.run_mode:
            m = QMenu(self)
            item = self._item_at(e.pos())
            if item is not None and self.guess_enabled and item.FAULTS:
                self.guess_menu(m, item)
                m.addSeparator()
            if item is not None and item.info.io != "none":
                m.addAction(tr("📘 ใบความรู้อุปกรณ์นี้"), lambda it=item: self.knowledge_requested.emit(it))
            m.addAction(tr("✎ สลับเป็นโหมดแก้ไขผัง"), self.edit_requested.emit)
            m.exec(e.globalPos())
            return
        item = self._item_at(e.pos())
        m = QMenu(self)
        if item is not None:
            if not item.isSelected():
                self.sc.clearSelection()
                item.setSelected(True)
            head = m.addAction(f"{item.shown_label or item.info.name}" + (f"  [{item.addr}]" if item.addr else ""))
            head.setEnabled(False)
            m.addSeparator()
            if item.info.io != "none":
                m.addAction(tr("แก้ Address…"), lambda: self._ask_address(item))
            m.addAction((tr("แก้ข้อความ") if item.spec.kind == "note" else tr("แก้ชื่อ")) + "\tF2", lambda: self.edit_text(item))
            if isinstance(item, InputItem):
                m.addAction(tr("ตั้งคีย์ลัด…"), lambda: self._ask_key(item))
            if item.info.io != "none":
                m.addAction(tr("📘 ใบความรู้"), lambda it=item: self.knowledge_requested.emit(it))
            m.addSeparator()
            m.addAction(tr("ทำซ้ำ\tCtrl+D"), self.duplicate_selected)
            m.addAction(tr("ลบ\tDelete"), self.remove_selected)
            m.addSeparator()
            m.addAction(tr("นำมาไว้หน้าสุด"), lambda: self._reorder(item, True))
            m.addAction(tr("ส่งไปไว้หลังสุด"), lambda: self._reorder(item, False))
        else:
            pos = self.mapToScene(e.pos())
            for cat, title in CATEGORIES:
                sub = m.addMenu(tr("วาง {0}", title))
                for info in CATALOG.values():
                    if info.category == cat:
                        sub.addAction(info.name, lambda k=info.kind: self.add_device(k, pos))
            m.addSeparator()
            m.addAction(tr("ดูทั้งผัง"), self.fit_all)
        m.addSeparator()
        a_u = m.addAction(tr("↶ ย้อนกลับ {0}\tCtrl+Z", self.undo.undoText()), self.do_undo)
        a_u.setEnabled(self.undo.canUndo())
        m.exec(e.globalPos())

    def _set_prop(self, item: DeviceItem, key: str, value, label: str):
        item.spec.props[key] = value
        self.refresh_validation()
        item.prepareGeometryChange()
        item.update()
        self.commit(label)
        self._on_selection()
        self.changed.emit()

    def _ask_address(self, item):
        txt, ok = QInputDialog.getText(self, tr("แก้ Address"), tr("{0} — ใช้ได้: {1}", item.info.name, ' / '.join(item.info.prefixes)),
                                       text=item.addr)
        if ok:
            valid, msg = validate_address(item.spec.kind, txt, self.xy_base)
            if not valid:
                self.status.emit(f"✖ {msg}")
            self._set_prop(item, "address", txt.strip().upper(), tr("แก้ Address"))

    def _ask_key(self, item):
        txt, ok = QInputDialog.getText(self, tr("ตั้งคีย์ลัด"), tr("กดคีย์นี้ในโหมดใช้งาน = กดอุปกรณ์ (1–9, A–Z, เว้นว่าง = ไม่ใช้)"),
                                       text=item.key)
        if ok:
            k = txt.strip().upper()[:1]
            if k and k not in HOTKEYS:
                self.status.emit(tr("✖ คีย์ลัดต้องเป็น 1–9 หรือ A–Z"))
                return
            self._set_prop(item, "key", k, tr("ตั้งคีย์ลัด"))

    def _reorder(self, item: DeviceItem, front: bool):
        """นำมาไว้หน้าสุด / ส่งไปหลังสุด (ลำดับในไฟล์ = ลำดับการวาด)."""
        specs = [it.spec for it in self.items_by_id.values() if it is not item]
        specs = specs + [item.spec] if front else [item.spec] + specs
        self._build(PanelDoc(name=self.doc_name, devices=specs))
        self.commit(tr("จัดลำดับ"))
        self.changed.emit()

    # ================= drag & drop =================
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            kind = bytes(e.mimeData().data(MIME)).decode()
            if kind in CATALOG:
                if self.sc.run_mode:
                    self.status.emit(tr("สลับเป็นโหมดแก้ไข (EDIT) เพื่อจัดผัง"))
                it = self.add_device(kind, self.mapToScene(e.position().toPoint()))
                if kind == "note" and not self.sc.run_mode:      # วางป้ายแล้วพิมพ์ได้เลย
                    QTimer.singleShot(0, it, lambda: self.edit_text(it))
            e.acceptProposedAction()

    def _on_selection(self):
        try:
            sel = self.selected_items()
        except RuntimeError:        # scene ถูกทำลายแล้ว (ตอนปิดหน้าต่าง)
            return
        self.selection_changed.emit(sel[0] if len(sel) == 1 else None)

    def _schedule_changed(self):
        self._changed_timer.start()
