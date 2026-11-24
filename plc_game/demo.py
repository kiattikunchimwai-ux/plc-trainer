"""โหมดสาธิต: โปรแกรมกดอุปกรณ์บนผังเองทีละขั้น พร้อมคำอธิบายบนจอ
รัน:  python -m plc_game.main --demo [--backend slmp]
ใช้ผัง panels/default.plcpanel (Start X0, Stop X1, Reset X3, Sensor X2 บนสายพาน Y0)
"""
from __future__ import annotations

from .i18n import tr

from PySide6.QtCore import QObject, QTimer


class DemoRunner(QObject):
    def __init__(self, win, on_step=None, speed: float = 1.0):
        super().__init__(win)
        self.win = win
        self.on_step = on_step          # callback(index, text) ใช้ตอนถ่ายภาพหน้าจอ
        self.speed = speed
        self._i = 0
        self.steps = [
            (4000, tr("👋 ยินดีต้อนรับสู่ PLC Trainer — โหมดสาธิต\n"
                   "ผังนี้มีปุ่มกด หลอดไฟ มอเตอร์ เซนเซอร์ และสายพาน ที่ต่อกับ address ของ PLC"), self._prepare),
            (3500, tr("ขั้นที่ 1 · เชื่อมต่อ PLC\nกด ‘เชื่อมต่อ’ ที่ Ribbon → ไฟ ONLINE ขวาล่างเป็นสีเขียว"), self._connect),
            (3000, tr("ขั้นที่ 2 · กดปุ่ม Start (X0) บนผัง\nโหมดใช้งาน (RUN): คลิกที่อุปกรณ์เพื่อกด — ปล่อยแล้วสัญญาณ X0 กลับเป็น 0"),
             lambda: self._press("X0", 600)),
            (4000, tr("หลอด RUN (Y0) ติดค้าง + มอเตอร์หมุน + สายพานเดิน\nเพราะ ladder มีวงจร Self-Holding และอุปกรณ์ทั้ง 3 ต่อกับ Y0 💡"),
             lambda: None),
            (3000, tr("ขั้นที่ 3 · Timer\nตัวแสดงค่า Timer T0 นับขึ้นถึง 30 (= 3 วินาที) → หลอด ‘T0 ครบ’ (Y1) ติด"), lambda: None),
            (8000, tr("ขั้นที่ 4 · สายพาน + เซนเซอร์\nกด ‘+ ชิ้นงาน’ ที่หัวสายพาน 5 ครั้ง — ชิ้นงานที่ตัดลำแสงเซนเซอร์ (X2) จะถูก Counter C0 นับ"),
             self._five_parts),
            (3000, tr("C0 นับครบ 5 → หลอด ‘นับครบ 5’ (Y2) ติด\nดูตัวแสดงค่า Counter C0"), lambda: None),
            (3000, tr("ขั้นที่ 5 · กดปุ่ม Stop (X1)\nY0 ดับ → สายพานและมอเตอร์หยุด, Timer รีเซ็ต"), lambda: self._press("X1", 500)),
            (3000, tr("ขั้นที่ 6 · กด Reset C0 (X3)\nCounter กลับเป็น 0 และหลอด Y2 ดับ"), lambda: self._press("X3", 500)),
            (4500, tr("ขั้นที่ 7 · ดูกราฟ\nแท็บกราฟด้านบน: Timing Diagram ของทุกสัญญาณในผัง (เลือกได้ที่แผง LAYERS)"),
             self._show_chart),
            (5000, tr("ขั้นที่ 8 · จัดผังเอง\nกด ‘✎ แก้ไขผัง’ → ลากอุปกรณ์จาก TOOL PALETTE มาวาง แล้วเลือกอุปกรณ์เพื่อแก้ Address ใน PROPERTIES"),
             self._show_edit),
            (0, tr("✅ จบการสาธิต — ลองเองได้เลย!\nกด ▶ ใช้งาน แล้วคลิกอุปกรณ์บนผัง · บันทึกผังของคุณด้วยปุ่ม 💾"), self._finish),
        ]

    # ---------- actions ----------
    def _prepare(self):
        self.win.set_edit_mode(False)
        self.win.show_view(self.win.panel)
        self.win.panel.fit_all()

    def _connect(self):
        backend = self.win.cfg.get("backend", "mock")
        self.win.cb_backend.setCurrentIndex(self.win.cb_backend.findData(backend))
        self.win.connect_plc()

    def _press(self, addr: str, hold_ms: int):
        if self.win.panel.press(addr, int(hold_ms / self.speed)):
            self.win.log(tr("[สาธิต] กด {0}", addr))
        else:
            self.win.log(tr("[สาธิต] ไม่พบอุปกรณ์ Input ที่ใช้ {0} บนผัง", addr))

    def _five_parts(self):
        convs = self.win.panel.conveyors()
        if not convs:
            return
        c = convs[0]
        c.flash(800)
        for k in range(5):
            QTimer.singleShot(int(k * 700 / self.speed), c.spawn)

    def _show_chart(self):
        self.win.show_view(self.win.chart)

    def _show_edit(self):
        self.win.show_view(self.win.panel)
        self.win.set_edit_mode(True)
        lamps = self.win.panel.items_at("Y0")
        if lamps:
            lamps[0].setSelected(True)

    def _finish(self):
        self.win.panel.sc.clearSelection()
        self.win.set_edit_mode(False)
        self.win.dirty = False
        self.win._update_title()

    # ---------- runner ----------
    def start(self):
        self._i = 0
        self._next()

    def _next(self):
        if self._i >= len(self.steps):
            return
        wait, text, action = self.steps[self._i]
        self.win.show_banner(text)
        self.win.log("▶ " + text.replace("\n", " — "))
        action()
        idx = self._i
        self._i += 1
        if self.on_step:
            QTimer.singleShot(max(int(wait / self.speed) - 150, 50), lambda: self.on_step(idx, text))
        if self._i < len(self.steps):
            QTimer.singleShot(int(wait / self.speed), self._next)
        elif self.on_step:
            QTimer.singleShot(1500, lambda: self.on_step(-1, ""))
