"""ตัวบันทึก/เล่นซ้ำการกดบนผัง (ใช้ใน MainWindow) — ข้อมูลอยู่ใน panel/macro.py."""
from __future__ import annotations

from ..i18n import tr

import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..panel.catalog import IN_KINDS
from ..panel.macro import Macro, MacroEvent, is_user_input


class MacroController(QObject):
    state_changed = Signal(str)          # idle | rec | play
    message = Signal(str)

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.state = "idle"
        self.macro: Macro | None = None   # การกดล่าสุด (บันทึกเสร็จ / เปิดจากไฟล์)
        self._rec: Macro | None = None
        self._t0 = 0.0
        self._out_addrs: set[str] = set()
        self._last_out: dict[str, int] = {}
        self._timers: list[QTimer] = []
        self.clock = time.monotonic

    # ---------- บันทึก ----------
    def start_record(self, panel_name: str = "") -> bool:
        if self.state != "idle":
            return False
        idle = {a: v for a, v, word in self.panel.input_states() if not word and self._user_slot(a)}
        self._rec = Macro(panel=panel_name, idle=idle)
        self._out_addrs = {a for it in self.panel.items_by_id.values() for s in it.info.slots()
                           if s.io == "out" and s.prop != "addr_motor" and (a := it.addr_of(s.prop))}
        self._last_out = {}
        self._t0 = self.clock()
        self._set("rec")
        self.message.emit(tr("⏺ เริ่มบันทึกการกด — กดปุ่มบนผังได้เลย (กดอีกครั้งเพื่อหยุด)"))
        return True

    def stop_record(self) -> Macro | None:
        if self.state != "rec":
            return None
        m = self._rec
        m.duration = round(self.clock() - self._t0, 3)
        self._rec = None
        self._set("idle")
        if not m.inputs:
            self.message.emit(tr("⏹ หยุดบันทึก — ไม่มีการกดเลย"))
            return None
        self.macro = m
        self.message.emit(tr("⏹ บันทึกแล้ว {0} การกด · {1:.1f} วินาที", len(m.inputs), m.duration)
                          + (tr(" · เห็น output เปลี่ยน {0} ครั้ง", len(m.outputs)) if m.outputs else
                             tr(" (ไม่ได้เชื่อม PLC — ไม่มีผล output)")))
        return m

    def _user_slot(self, addr: str):
        """(kind, prop) ถ้า address นี้เป็นอุปกรณ์ที่ผู้ใช้สั่งเอง."""
        for it in self.panel.items_by_id.values():
            for s in it.info.slots():
                if s.io in IN_KINDS and it.addr_of(s.prop) == addr and \
                        is_user_input(it.info.kind, s.prop, bool(getattr(it, "manual", False))):
                    return it.info.kind, s.prop
        return None

    def on_write(self, addr: str, value: int, word: bool = False) -> None:
        if self.state != "rec" or not self._user_slot(addr):
            return
        ev = self._rec.events
        last = next((e for e in reversed(ev) if e.io == "in" and e.addr == addr), None)
        if last is not None and last.value == int(value):
            return                                    # ค่าเดิมซ้ำ (เช่น เขียนซ้ำตอนเชื่อมต่อ)
        if last is None and self._rec.idle.get(addr) == int(value) and not word:
            return
        ev.append(MacroEvent(round(self.clock() - self._t0, 3), addr, int(value), word, "in"))

    def on_snapshot(self, snap: dict) -> None:
        if self.state != "rec":
            return
        t = round(self.clock() - self._t0, 3)
        for a in self._out_addrs:
            if a not in snap:
                continue
            v = int(snap[a])
            if self._last_out.get(a) != v:
                first = a not in self._last_out
                self._last_out[a] = v
                self._rec.events.append(MacroEvent(0.0 if first else t, a, v, False, "out"))

    # ---------- เล่นซ้ำ ----------
    def play(self, m: Macro | None = None) -> bool:
        m = m or self.macro
        if m is None or self.state != "idle" or not m.inputs:
            return False
        self.macro = m
        for a, v in m.idle.items():
            self.panel.drive_input(a, v)
        missing = sorted({e.addr for e in m.inputs if not self.panel.items_at(e.addr) and not self._any_slot(e.addr)})
        if missing:
            self.message.emit(tr("⚠ ผังนี้ไม่มีอุปกรณ์ที่ {0} — ข้ามการกดเหล่านั้น", ', '.join(missing)))
        start = 0.4                                   # ให้ค่าพักถึง PLC ก่อน
        for e in m.inputs:
            self._later(start + e.t - m.inputs[0].t, lambda e=e: self._apply(e))
        self._later(start + max(m.duration, m.inputs[-1].t) - m.inputs[0].t + 0.2, self._play_done)
        self._set("play")
        self.message.emit(tr("▶ เล่นซ้ำ {0} การกด ({1:.1f} s)", len(m.inputs), m.duration))
        return True

    def _any_slot(self, addr):
        return any(it.addr_of(s.prop) == addr for it in self.panel.items_by_id.values() for s in it.info.slots())

    def _apply(self, e: MacroEvent):
        if self.state == "play":
            self.panel.drive_input(e.addr, e.value, e.word)

    def _later(self, sec: float, fn):
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(fn)
        t.start(max(0, int(sec * 1000)))
        self._timers.append(t)

    def _play_done(self):
        self.stop_play(done=True)

    def stop_play(self, done: bool = False):
        for t in self._timers:
            t.stop()
            t.deleteLater()
        self._timers.clear()
        if self.state == "play":
            self._set("idle")
            self.message.emit(tr("✔ เล่นซ้ำจบ") if done else tr("⏹ หยุดเล่นซ้ำ"))

    def stop(self):
        if self.state == "rec":
            self.stop_record()
        elif self.state == "play":
            self.stop_play()

    def _set(self, s: str):
        self.state = s
        self.state_changed.emit(s)
