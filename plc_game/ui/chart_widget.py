"""กราฟเรียลไทม์: Timing Diagram 0/1 (บน) + Trend ค่า Timer/Counter (ล่าง).

พื้นหลังและ crosshair ตามสไตล์ model space ของ AutoCAD
"""
from __future__ import annotations

from ..i18n import tr

from collections import deque

import numpy as np
import pyqtgraph as pg
import shiboken6
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

LANE_GAP = 1.5      # ระยะห่างระหว่างเลนของแต่ละสัญญาณ
HIGH = 1.0


def _step(t: np.ndarray, v: np.ndarray):
    """แปลงจุด sample เป็นเส้นขั้นบันได (ค่าคงที่จนกว่าจะเปลี่ยน)."""
    if len(t) < 2:
        return t, v
    xs = np.repeat(t, 2)[1:]
    ys = np.repeat(v, 2)[:-1]
    return xs, ys


class ChartWidget(QWidget):
    cursor_moved = Signal(float, str)   # เวลา, ข้อความสถานะใต้ cursor
    ab_changed = Signal(str)            # ข้อความ Δt ของเคอร์เซอร์ A/B

    def __init__(self, window_s: float = 10.0, max_rate_hz: int = 50, parent=None):
        super().__init__(parent)
        self.window_s = window_s
        self._maxlen = int(window_s * max_rate_hz * 3)
        self._t: deque[float] = deque(maxlen=self._maxlen)
        self._data: dict[str, deque] = {}
        self.bit_signals: list[str] = []
        self.word_signals: list[str] = []
        self.paused = False
        self._dirty = False
        self._scale = 1.0

        pg.setConfigOptions(antialias=False)
        app = QApplication.instance()
        tops_before = {shiboken6.getCppPointer(w)[0] for w in app.topLevelWidgets()} if app else set()
        self.view = pg.GraphicsLayoutWidget()
        self.view.setBackground(theme.BG_CANVAS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

        self.timing = self.view.addPlot(row=0, col=0)
        self.view.nextRow()
        self.trend = self.view.addPlot(row=1, col=0)
        self.view.ci.layout.setRowStretchFactor(0, 3)
        self.view.ci.layout.setRowStretchFactor(1, 1)
        self.trend.setXLink(self.timing)

        self._titles = ((self.timing, "TIMING DIAGRAM (0/1)"), (self.trend, tr("TREND  T / C  (ค่าปัจจุบัน)")))
        for p, title in self._titles:
            p.showGrid(x=True, y=True, alpha=0.18)
            p.setTitle(title, color=theme.TEXT_DIM, size="9pt")
            p.setMenuEnabled(False)
            p.hideButtons()
            for ax in ("left", "bottom"):
                a = p.getAxis(ax)
                a.setPen(pg.mkPen(theme.GRID_MAJOR))
                a.setTextPen(pg.mkPen(theme.TEXT_DIM))
        self.trend.setLabel("bottom", tr("เวลา (s)"), color=theme.TEXT_DIM)
        self.timing.getAxis("bottom").setStyle(showValues=False)
        self.timing.setMouseEnabled(x=True, y=False)
        self.trend.setMouseEnabled(x=True, y=False)
        self.trend_legend = self.trend.addLegend(offset=(5, 5), labelTextColor=theme.TEXT, brush=theme.BG_PANEL_DARK)
        # pyqtgraph สร้าง widget ไม่มี parent ไว้ ~17 ตัวต่อกราฟ (เมนู Plot Options + เมนูย่อย, เมนู ViewBox,
        # QWidget ว่างที่ใช้เป็นฟอร์มชั่วคราว) — อยู่นานกว่ากราฟแล้วถูก GC ลบทีหลังแบบไม่มีลำดับ
        # → Qt abort ตอนปิดโปรแกรมแบบสุ่ม จึงรับมาเป็นลูกของ ChartWidget ให้ถูกลบพร้อมกราฟเสมอ
        # (เมนูพวกนี้เราปิดไว้อยู่แล้ว: setMenuEnabled(False))
        if app:
            for w in app.topLevelWidgets():
                if w is not self and w.parent() is None and shiboken6.getCppPointer(w)[0] not in tops_before:
                    w.setParent(self, w.windowFlags())
                    w.hide()

        self._curves: dict[str, pg.PlotDataItem] = {}

        # Crosshair แบบ AutoCAD
        pen = pg.mkPen("#FFFFFF", width=1)
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self._vline2 = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self.timing.addItem(self._vline, ignoreBounds=True)
        self.timing.addItem(self._hline, ignoreBounds=True)
        self.trend.addItem(self._vline2, ignoreBounds=True)
        for ln in (self._vline, self._hline, self._vline2):
            ln.setVisible(False)   # แสดงเมื่อเมาส์เข้ามาในกราฟ
        self._proxy = pg.SignalProxy(self.view.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._redraw)
        self._timer.start(33)   # ~30 fps

        # โหมดผลตรวจด่าน: เส้นประค่าคาดหวัง + แถบแดงช่วงที่ไม่ผ่าน
        self.result_mode = False
        self._overlays: list[tuple[pg.PlotItem, pg.GraphicsObject]] = []
        self.fail_regions: list[tuple[float, float, str]] = []
        self._saved_signals: tuple[list[str], list[str]] | None = None
        self.btn_live = QPushButton(tr("◀  กลับไปกราฟสด"), self)
        self.btn_live.setToolTip(tr("ออกจากผลตรวจ แล้วแสดงสัญญาณเรียลไทม์ต่อ"))
        self.btn_live.setCursor(Qt.PointingHandCursor)
        self.btn_live.clicked.connect(self.exit_result)
        self.btn_live.hide()

        # เคอร์เซอร์ A/B (สร้างเมื่อเปิดใช้ครั้งแรก)
        self._ab = None
        self.ab_on = False
        self.lbl_ab = QLabel(self)
        self.lbl_ab.setStyleSheet(f"background:{theme.BG_PANEL_DARK}; color:{theme.TEXT}; border:1px solid "
                                  f"{theme.ACCENT}; border-radius:6px; padding:4px 8px;")
        self.lbl_ab.hide()
        self.ab_changed.connect(self._show_ab_label)

    def shutdown(self) -> None:
        """ปิดกราฟอย่างปลอดภัยก่อนถูกลบ (เรียกซ้ำได้).

        ถ้าปล่อยให้ Qt ลบ scene ของ pyqtgraph ระหว่างทำลายหน้าต่าง layout จะเรียก sizeHint() ของ LabelItem
        (เขียนด้วย Python) บนวัตถุที่ตายครึ่งตัว → process abort; view.close() ของ pyqtgraph ล้าง scene
        ตอนที่ทุกอย่างยังมีชีวิตอยู่
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._timer.stop()
        self._proxy.disconnect()
        self.view.close()

    def _show_ab_label(self, text: str):
        self.lbl_ab.setVisible(bool(text))
        self.lbl_ab.setText(text)
        self.lbl_ab.adjustSize()
        self.lbl_ab.move(70, 30)
        self.lbl_ab.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.btn_live.adjustSize()
        self.btn_live.move(self.width() - self.btn_live.width() - 12, 8)

    # ---------- configuration ----------
    def set_signals(self, bits: list[str], words: list[str]) -> None:
        if self.result_mode:               # ระหว่างดูผลตรวจ: จำไว้ใช้ตอนกลับไปกราฟสด
            self._saved_signals = (list(bits), list(words))
            return
        self._apply_signals(bits, words)

    def _apply_signals(self, bits: list[str], words: list[str]) -> None:
        self.bit_signals, self.word_signals = list(bits), list(words)
        for c in self._curves.values():
            c.getViewBox().removeItem(c) if c.getViewBox() else None
        self._curves.clear()
        self.trend_legend.clear()

        ticks = []
        for i, name in enumerate(self.bit_signals):
            base = (len(self.bit_signals) - 1 - i) * LANE_GAP
            c = self.timing.plot(pen=pg.mkPen(theme.color_for(name), width=2 * self._scale))
            self._curves[name] = c
            ticks.append((base + HIGH / 2, name))
        self.timing.getAxis("left").setTicks([ticks, []])
        top = max(len(self.bit_signals), 1) * LANE_GAP
        self.timing.setYRange(-0.3, top - LANE_GAP + HIGH + 0.3, padding=0)

        palette = ["#FF7A59", "#E879F9", "#4FD1FF", "#F2D648", "#5EE36A", "#FFFFFF"]
        for i, name in enumerate(self.word_signals):
            c = self.trend.plot(pen=pg.mkPen(palette[i % len(palette)], width=2 * self._scale), name=name)
            self._curves[name] = c
        self._dirty = True

    def set_scale(self, scale: float) -> None:
        """โหมดตัวใหญ่: ขยายตัวอักษรแกน/หัวกราฟ และความหนาเส้น."""
        from PySide6.QtGui import QFont
        self._scale = scale
        for p, title in self._titles:
            p.setTitle(title, color=theme.TEXT_DIM, size=f"{round(9 * scale)}pt")
            for ax in ("left", "bottom"):
                p.getAxis(ax).setStyle(tickFont=QFont("Segoe UI", round(8 * scale)))
        self._apply_signals(self.bit_signals, self.word_signals)
        self._dirty = True
        self._redraw()

    def set_window(self, seconds: float) -> None:
        self.window_s = seconds
        self._dirty = True

    def set_paused(self, paused: bool) -> None:
        if self.result_mode and not paused:   # กด "เล่นต่อ" ระหว่างดูผลตรวจ = กลับไปกราฟสด
            self.exit_result()
            return
        self.paused = paused

    def clear(self) -> None:
        if self.result_mode:
            self.exit_result()
            return
        self._t.clear()
        for d in self._data.values():
            d.clear()
        self._dirty = True

    # ---------- data ----------
    def add_snapshot(self, snap: dict, t: float) -> None:
        if self.paused:
            return
        self._t.append(t)
        for name, val in snap.items():
            d = self._data.get(name)
            if d is None:
                d = self._data[name] = deque([0] * (len(self._t) - 1), maxlen=self._t.maxlen)
            d.append(val)
        self._dirty = True

    def _redraw(self) -> None:
        if not self._dirty or not self._t:
            return
        self._dirty = False
        t = np.fromiter(self._t, float)
        n = len(self.bit_signals)
        for i, name in enumerate(self.bit_signals):
            d = self._data.get(name)
            if d is None:
                continue
            base = (n - 1 - i) * LANE_GAP
            v = np.fromiter(d, float)[-len(t):] * HIGH + base
            self._curves[name].setData(*_step(t[-len(v):], v))
        for name in self.word_signals:
            d = self._data.get(name)
            if d is None:
                continue
            v = np.fromiter(d, float)[-len(t):]
            self._curves[name].setData(*_step(t[-len(v):], v))
        if not self.paused:
            end = t[-1]
            self.timing.setXRange(max(0.0, end - self.window_s), max(self.window_s, end), padding=0)

    # ---------- ผลตรวจด่าน ----------
    def show_level_result(self, runner, is_bit=None, title: str = "") -> None:
        """แสดงสัญญาณตลอดการตรวจ + เส้นประค่าที่ต้องเป็น + แถบแดงช่วงที่ไม่ผ่าน (เวลา 0 = เริ่มตรวจ)."""
        from ..levels import expected_segments, fail_spans
        from ..plc.device import parse_device
        if not runner.trace:
            return
        if is_bit is None:
            def is_bit(a):
                return parse_device(a).is_bit
        if not self.result_mode:
            self._saved_signals = (list(self.bit_signals), list(self.word_signals))
        self._remove_overlays()
        segs = expected_segments(runner, is_bit)
        names = list(dict.fromkeys(runner.level.addresses() + list(segs)))
        seen = set().union(*(s.keys() for _, s in runner.trace))
        names = [n for n in names if n in seen]
        bits = [n for n in names if is_bit(n)]
        words = [n for n in names if not is_bit(n)]
        self.result_mode = True
        self._apply_signals(bits, words)
        self._show_trend(bool(words))       # ด่านที่ไม่มีค่าตัวเลข ไม่ต้องเสียที่ให้กราฟล่าง

        # ข้อมูลทั้งการตรวจ (trace เก็บเฉพาะจังหวะที่ค่าเปลี่ยน)
        end = max([runner.trace[-1][0]] + [r.t_end for r in runner.results]) + 0.5
        size = len(runner.trace) + 2
        self._t = deque(maxlen=size)
        self._data = {}
        self.paused = False
        for t, snap in runner.trace:
            self.add_snapshot(snap, t)
        self.add_snapshot(runner.trace[-1][1], end)
        self.paused = True
        self._dirty = True
        self._redraw()

        n = len(bits)
        for addr, lst in segs.items():
            for s in lst:
                if addr in bits:
                    plot, y = self.timing, (n - 1 - bits.index(addr)) * LANE_GAP + s.value * HIGH
                elif addr in words:
                    plot, y = self.trend, s.value
                else:
                    continue
                col = "#FFFFFF" if s.passed else "#FFC9C9"
                item = pg.PlotDataItem([s.t0, s.t1], [y, y],
                                       pen=pg.mkPen(col, width=2.5 if s.passed else 3.5, style=Qt.DashLine))
                item.setZValue(5)
                plot.addItem(item)
                self._overlays.append((plot, item))
        self.fail_regions = fail_spans(runner)
        top = (max(n, 1) - 1) * LANE_GAP + HIGH + 0.25
        for t0, t1, msg in self.fail_regions:
            for plot in (self.timing, self.trend):
                reg = pg.LinearRegionItem((t0, t1), movable=False, brush=pg.mkBrush(239, 68, 68, 55),
                                          pen=pg.mkPen(239, 68, 68, 170))
                reg.setZValue(-10)
                plot.addItem(reg)
                self._overlays.append((plot, reg))
            txt = pg.TextItem("✖ " + (msg if len(msg) <= 38 else msg[:37] + "…"), color=theme.DANGER, anchor=(0, 0))
            txt.setPos(t0, top)
            self.timing.addItem(txt)
            self._overlays.append((self.timing, txt))
        self.timing.setTitle(tr("ผลตรวจ {0}  ·  เส้นประขาว = ค่าที่ต้องเป็น (ผ่าน) · แดง = ไม่ผ่าน", title),
                             color=theme.TEXT, size=f"{round(9 * self._scale)}pt")
        self.timing.setXRange(0, end, padding=0.01)
        self.btn_live.adjustSize()
        self.btn_live.move(self.width() - self.btn_live.width() - 12, 8)
        self.btn_live.show()
        self.btn_live.raise_()

    def focus_time(self, t0: float, t1: float) -> None:
        """เลื่อนกราฟไปช่วงเวลานั้น (เผื่อขอบซ้ายขวา)."""
        pad = max(1.0, (t1 - t0) * 0.5)
        self.timing.setXRange(max(0.0, t0 - pad), t1 + pad, padding=0)

    def _remove_overlays(self) -> None:
        for plot, item in self._overlays:
            plot.removeItem(item)
        self._overlays.clear()
        self.fail_regions = []

    def exit_result(self) -> None:
        if not self.result_mode:
            return
        self._remove_overlays()
        self.result_mode = False
        self._t = deque(maxlen=self._maxlen)
        self._data = {}
        self.paused = False
        self.timing.setTitle(self._titles[0][1], color=theme.TEXT_DIM, size=f"{round(9 * self._scale)}pt")
        bits, words = self._saved_signals or ([], [])
        self._saved_signals = None
        self._apply_signals(bits, words)
        self._show_trend(True)
        self.btn_live.hide()

    def _show_trend(self, on: bool) -> None:
        self.trend.setVisible(on)
        self.timing.getAxis("bottom").setStyle(showValues=not on)
        self.timing.setLabel("bottom", "" if on else tr("เวลา (s)"), color=theme.TEXT_DIM)

    # ---------- เคอร์เซอร์ A/B วัด Δt ----------
    def set_ab(self, on: bool) -> None:
        """แสดงเส้น A/B ที่ลากได้ (ปล่อยเมาส์ใกล้ขอบสัญญาณ = ดูดเข้าขอบ) + ข้อความ Δt."""
        if self._ab is None:
            self._ab = {}
            for key, col in (("A", "#F2D648"), ("B", "#4FD1FF")):
                ln = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(col, width=2),
                                     hoverPen=pg.mkPen(col, width=4),
                                     label=key, labelOpts={"position": 0.97, "color": col, "fill": theme.BG_PANEL_DARK})
                ln.setZValue(20)
                mirror = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(col, width=1.5, style=Qt.DashLine))
                self.timing.addItem(ln, ignoreBounds=True)
                self.trend.addItem(mirror, ignoreBounds=True)
                ln.sigPositionChanged.connect(lambda l, m=mirror: (m.setPos(l.value()), self._emit_ab()))
                ln.sigPositionChangeFinished.connect(self._snap)
                self._ab[key] = (ln, mirror)
        if on and not self.ab_on:
            x0, x1 = self.timing.vb.viewRange()[0]
            self.set_ab_pos(x0 + (x1 - x0) * 0.3, x0 + (x1 - x0) * 0.6)
        self.ab_on = on
        for ln, m in self._ab.values():
            ln.setVisible(on)
            m.setVisible(on)
        self._emit_ab()

    def set_ab_pos(self, a: float, b: float) -> None:
        if self._ab is None:
            self.set_ab(True)
        self._ab["A"][0].setValue(a)
        self._ab["B"][0].setValue(b)

    def ab_pos(self) -> tuple[float, float]:
        return self._ab["A"][0].value(), self._ab["B"][0].value()

    def edges(self) -> list[float]:
        """เวลาที่สัญญาณบนกราฟเปลี่ยนค่า (ใช้ดูดเคอร์เซอร์เข้าขอบ)."""
        if len(self._t) < 2:
            return []
        t = np.fromiter(self._t, float)
        out = set()
        for name in self.bit_signals + self.word_signals:
            d = self._data.get(name)
            if d is None:
                continue
            v = np.fromiter(d, float)[-len(t):]
            tt = t[-len(v):]
            out.update(tt[1:][np.diff(v) != 0].tolist())
        return sorted(out)

    def _snap(self, ln) -> None:
        x0, x1 = self.timing.vb.viewRange()[0]
        tol = (x1 - x0) * 0.03
        es = self.edges()
        if es:
            e = min(es, key=lambda v: abs(v - ln.value()))
            if abs(e - ln.value()) <= tol:
                ln.setValue(e)

    def ab_text(self) -> str:
        if not self.ab_on or self._ab is None:
            return ""
        a, b = self.ab_pos()
        dt = abs(b - a)
        s = f"A = {a:.2f} s · B = {b:.2f} s · Δt = {dt:.3f} s"
        if dt > 1e-6:
            s += f" ({dt * 1000:.0f} ms)"
        va, vb = self._values_at(a), self._values_at(b)
        if va or vb:
            s += tr("\nที่ A: {0}\nที่ B: {1}", va or '-', vb or '-')
        return s

    def _emit_ab(self) -> None:
        self.ab_changed.emit(self.ab_text())

    # ---------- Export ----------
    def to_csv(self) -> str:
        """เวลา + ทุกสัญญาณบนกราฟ (เฉพาะจังหวะที่บันทึกไว้) — ขึ้นต้นด้วย BOM ให้ Excel อ่านไทยได้."""
        import csv
        import io
        names = self.bit_signals + self.word_signals
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow([tr("เวลา (s)")] + names)
        t = list(self._t)
        cols = []
        for nm in names:
            d = list(self._data.get(nm, []))[-len(t):] if t else []
            cols.append([""] * (len(t) - len(d)) + d)          # ชิดท้าย (ข้อมูลล่าสุดตรงกับเวลาล่าสุด)
        for i, ti in enumerate(t):
            w.writerow([f"{ti:.3f}"] + [c[i] for c in cols])
        return "﻿" + buf.getvalue()

    def export_csv(self, path) -> None:
        from pathlib import Path
        Path(path).write_text(self.to_csv(), encoding="utf-8")

    def export_png(self, path) -> bool:
        self._redraw()
        return self.view.grab().save(str(path))

    # ---------- crosshair ----------
    def _on_mouse(self, evt):
        pos = evt[0]
        for plot in (self.timing, self.trend):
            if plot.sceneBoundingRect().contains(pos):
                for ln in (self._vline, self._hline, self._vline2):
                    ln.setVisible(True)
                p = plot.vb.mapSceneToView(pos)
                self._vline.setPos(p.x())
                self._vline2.setPos(p.x())
                if plot is self.timing:
                    self._hline.setPos(p.y())
                self.cursor_moved.emit(p.x(), self._values_at(p.x()))
                return

    def _values_at(self, x: float) -> str:
        if not self._t:
            return ""
        t = np.fromiter(self._t, float)
        idx = int(np.searchsorted(t, x, side="right")) - 1
        if idx < 0:
            return ""
        parts = []
        for name in self.bit_signals + self.word_signals:
            d = self._data.get(name)
            if d is not None and idx < len(d):
                parts.append(f"{name}={d[idx]}")
        return "  ".join(parts)
