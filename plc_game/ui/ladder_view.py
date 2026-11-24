"""แท็บ Ladder: วาด ladder ด้วยคีย์บอร์ด/เมาส์, ส่งลง PLC ในตัว (F4), monitor สด, บันทึกอัตโนมัติ.

ตัวเอกสารและกฎโครงสร้างอยู่ใน ladder/editor.py — ไฟล์นี้มีแค่การวาดและรับคำสั่ง
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QScrollArea, QSplitter, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..ladder.check import check
from ..ladder.csvio import LadderError, load_csv, save_csv
from ..ladder.editor import (BLANK, INLINE, Branch, Coil, Inline, LadderDoc, Leaf, Parallel, Rung, Series,
                             is_blank, standalone, rebase, rung_code, rungs_from, walk)
from ..ladder.model import CONTACT_OPS, KNOWN_FUNC, WIDE_WORDS, Ladder, digits, is_label, is_wide, kind_of, pair, resolve, word_name
from ..ladder.static import static_findings
from . import theme

CW, CH = 96.0, 66.0            # ขนาดช่อง
LEFT, TOP = 64.0, 10.0         # ขอบซ้าย (เลข step) / บน
COIL_W = 2.4                   # ความกว้างคอยล์ (ช่อง)
MIN_COLS = 5
AUTOSAVE_MS = 700
_INFIX = re.compile(r"^(\S+?)\s*(<>|>=|<=|=|>|<)\s*(\S+)$")
_PREFIX = re.compile(r"^(?:LD|AND|OR)?(D?(?:<>|>=|<=|=|>|<))\s+(\S+)\s+(\S+)$")


# ======================= ข้อความที่พิมพ์ → คำสั่ง =======================
def parse_entry(text: str, base: int) -> tuple[str, object]:
    """ข้อความในช่องแก้ไข → ("leaf"|"or"|"inline"|"coil", ชิ้น) — อ่านไม่ออก = LadderError."""
    t = " ".join(text.upper().split())
    if not t:
        raise LadderError(tr("ยังไม่ได้พิมพ์"))
    if not t.isascii():
        raise LadderError(tr("พิมพ์เป็นภาษาอังกฤษ เช่น X0, ANI X1, OUT T0 K30 (กด ~ สลับแป้น)"))
    _clean(t)
    if m := _PREFIX.match(t):
        return ("or" if t.startswith("OR") else "leaf"), Leaf(m.group(1), (m.group(2), m.group(3)))
    if (m := _INFIX.match(t)) and " " not in m.group(1) and _value(m.group(1), base):
        return "leaf", Leaf(m.group(2), (m.group(1), m.group(3)))
    p = t.split()
    op, args = p[0], tuple(p[1:])
    if op in INLINE and not args:
        return "inline", Inline(op)
    if op in CONTACT_OPS:
        head, mod = CONTACT_OPS[op]
        if len(args) != 1:
            raise LadderError(tr("{0} ต้องตามด้วย device 1 ตัว เช่น {0} X0", op))
        return ("or" if head == "OR" else "leaf"), Leaf(mod, args)
    if t.startswith("/") and len(p) == 1:
        return "leaf", Leaf("I", (t[1:],))
    r = None if op in KNOWN_FUNC else resolve(op, base, base)      # BCD อ่านเป็น device B0CD ได้ด้วย
    if r:
        if len(args) == 0:
            return "device", (op,)
        if r[0] in ("T", "C", "ST") and len(args) == 1:
            return "coil", Coil("OUT", (op, *args))
        raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", t[:40]))
    if standalone(op) and not args and (is_label(op) or op == "FEND"):
        return "coil", Coil(op, ())
    if kind_of(op) in ("stack", "ignore"):
        raise LadderError(tr("ใส่ {0} ตรงนี้ไม่ได้ — วาดเป็นอนุกรม/ขนานแทน", op))
    if kind_of(op) in ("compare", "unknown_contact"):
        raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", t[:40]))
    if not args and op not in ("MCR", "WDT") and kind_of(op) == "out":
        raise LadderError(tr("ไม่รู้จัก device {0}", op))
    if len(op) > 16 or len(args) > 6:
        raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", t[:40]))
    return "coil", Coil(op, args)


def _clean(t: str):
    """กันข้อความที่ไม่ใช่คำสั่งเดียว (ยาวเกิน, หลายคำสั่งคั่นด้วย ;, อักขระที่ทำให้ CSV เพี้ยน)."""
    if len(t) > 80 or not t.isascii() or any(c in t for c in ';",?') or len(t.split()) > 7 or not t.split():
        raise LadderError(tr("ไม่ใช่คำสั่ง ladder: {0}", t[:40]))


def _value(s: str, base: int) -> bool:
    return bool(resolve(s, base, base) or digits(s, base, base) or re.match(r"^K-?\d+$|^H[0-9A-F]+$", s))


# ======================= ผืนวาด =======================
class LadderCanvas(QWidget):
    selected = Signal()
    message = Signal(str)

    def __init__(self, view: "LadderView"):
        super().__init__()
        self.view = view
        self.doc: LadderDoc = view.doc
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.scale = 1.0
        self.uid = 0                        # ชิ้นที่เลือก (0 = ทั้ง rung)
        self.last = 0                       # ปลายช่วงที่เลือก (Shift+→)
        self.rung = 0
        self.rung_to = 0                    # ช่วง rung ที่เลือก (Shift+↑↓)
        self.boxes: dict[int, QRectF] = {}
        self.box_rung: dict[int, int] = {}
        self._sel: set[int] = set()
        self.rung_y: list[tuple[float, float]] = []
        self.right = LEFT + CW * (MIN_COLS + COIL_W)
        self.cv: dict[int, int] = {}        # uid → ค่า (monitor)
        self.cond: dict[int, int] = {}
        self.values: dict[str, int] = {}
        self.live = False
        self.problems: dict[int, str] = {}  # uid → ข้อความ
        self.labels: dict[str, str] = {}    # address → ป้ายอุปกรณ์
        self.editor: QLineEdit | None = None
        self._commit = None
        self.relayout()

    # ---------- ขนาด ----------
    def _w(self, n) -> float:
        if isinstance(n, Leaf):
            return 1.5 if len(n.args) > 1 else 1.0
        if isinstance(n, Inline):
            return 0.8
        if isinstance(n, Series):
            return sum(self._w(k) for k in n.kids)
        return max(self._w(k) for k in n.kids) + 0.3      # Parallel: เผื่อเส้นแนวตั้ง

    def _h(self, n) -> float:
        if isinstance(n, (Leaf, Inline)):
            return 1
        if isinstance(n, Series):
            return max((self._h(k) for k in n.kids), default=1)
        return sum(self._h(k) for k in n.kids)

    def _bw(self, b: Branch) -> float:
        return self._w(b.cond) + 0.25 + max((self._bw(x) for x in b.outs if isinstance(x, Branch)), default=0)

    def _bh(self, b: Branch) -> float:
        return max(self._h(b.cond), sum(self._bh(x) if isinstance(x, Branch) else 1 for x in b.outs))

    def _rung_h(self, r: Rung) -> float:
        body = max(1, len(r.raw)) * 24 + 14 if r.is_raw else self._bh(r.body) * CH
        return body + 24

    def relayout(self):
        cols = max([MIN_COLS] + [self._bw(r.body) for r in self.doc.rungs if not r.is_raw])
        wide = COIL_W
        for r in self.doc.rungs:
            for x, _, _ in walk(r):
                if isinstance(x, Coil):
                    wide = max(wide, (len(" ".join((x.op, *x.args))) * 8.6 + 30) / CW)
        self.coil_w = wide
        self.right = LEFT + CW * (cols + wide) + 10
        y, self.rung_y = TOP, []
        for r in self.doc.rungs:
            h = self._rung_h(r)
            self.rung_y.append((y, h))
            y += h
        self.boxes, self.box_rung = {}, {}
        for n, r in enumerate(self.doc.rungs):
            if not r.is_raw:
                self._branch(None, r.body, LEFT, self.rung_y[n][0] + 24, 1)
                for uid in list(self.boxes)[len(self.box_rung):]:
                    self.box_rung[uid] = n
        self.rung = max(0, min(self.rung, len(self.doc.rungs) - 1))
        self.rung_to = max(0, min(self.rung_to, len(self.doc.rungs) - 1))
        if self.uid and self.uid not in self.boxes:
            self.uid = self.last = 0
        if self.last and self.last not in self.boxes:
            self.last = self.uid
        self.setMinimumSize(int((self.right + 24) * self.scale), int((y + 60) * self.scale))
        self.update()

    def minimumSizeHint(self):
        return self.minimumSize()

    # ---------- วาด (p=None = คำนวณตำแหน่งอย่างเดียว) ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG_CANVAS))
        p.scale(self.scale, self.scale)
        clip = QRectF(0, e.rect().top() / self.scale, 1e6, e.rect().height() / self.scale)
        step = 0
        self._sel = set(self.sel_range())
        for n, r in enumerate(self.doc.rungs):
            y, h = self.rung_y[n]
            size = 0 if is_blank(r) else self.view.rung_len(r)
            if y + h >= clip.top() and y <= clip.bottom():
                self._rung(p, n, r, y, h, step)
            step += size
        p.end()

    def _rung(self, p, n, r, y, h, step):
        a, b = sorted((self.rung, self.rung_to))
        if a <= n <= b:
            p.fillRect(QRectF(4, y + 2, self.right + 8, h - 4), QColor(theme.CARD if a == b else theme.CARD_HI))
        if r.uid in self.problems:
            p.fillRect(QRectF(4, y + 2, 4, h - 4), QColor(theme.DANGER))
        f = QFont(p.font())
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRectF(8, y + 24 + CH / 2 - 18, LEFT - 18, 16), Qt.AlignRight, f"{n + 1}")
        p.drawText(QRectF(8, y + 24 + CH / 2, LEFT - 18, 16), Qt.AlignRight, f"({step})")
        if r.comment:
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.setPen(QColor("#A3E635"))
            p.drawText(QRectF(LEFT + 6, y + 3, self.right - LEFT, 20), Qt.AlignLeft | Qt.AlignVCenter, r.comment)
        on = QPen(QColor(theme.SUCCESS if self.live else theme.BORDER).lighter(100 if self.live else 160), 3)
        p.setPen(on)
        p.drawLine(QPointF(LEFT, y), QPointF(LEFT, y + h))
        p.setPen(QPen(QColor(theme.BORDER).lighter(160), 3))
        p.drawLine(QPointF(self.right, y), QPointF(self.right, y + h))
        if r.is_raw:
            f = QFont("Consolas")
            f.setPointSizeF(10)
            p.setFont(f)
            p.setPen(QPen(QColor(theme.BORDER), 1))
            p.setBrush(QColor(theme.BG_INPUT))
            box = QRectF(LEFT + 14, y + 26, 380, h - 34)
            p.drawRoundedRect(box, 6, 6)
            p.setBrush(Qt.NoBrush)
            p.setPen(QColor(theme.TEXT))
            p.drawText(box.adjusted(10, 4, -6, 0), Qt.AlignLeft, "\n".join(" ".join((o, *a)) for o, a in r.raw))
        else:
            self._branch(p, r.body, LEFT, y + 24, 1)

    def _pen(self, power):
        if self.live and power:
            return QPen(QColor(theme.SUCCESS), 3)
        return QPen(QColor(theme.TEXT_DIM), 1.6)

    def _line(self, p, x0, y0, x1, y1, power):
        if p is not None:
            p.setPen(self._pen(power))
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def _branch(self, p, b: Branch, x, y, power):
        mid = CH / 2
        out = self._series(p, b.cond, x, y, power)
        jx = x + self._w(b.cond) * CW + 0.125 * CW
        self._line(p, jx - 0.125 * CW, y + mid, jx, y + mid, out)
        oy, last = y, y
        for o in b.outs:
            if isinstance(o, Branch):
                self._line(p, jx, oy + mid, jx + 0.125 * CW, oy + mid, out)
                self._branch(p, o, jx + 0.125 * CW, oy, out)
                h = self._bh(o) * CH
            else:
                cx = self.right - self.coil_w * CW
                power_c = self.cond.get(o.uid, out) if self.live else 0
                self._line(p, jx, oy + mid, cx, oy + mid, out)
                self._coil(p, o, QRectF(cx, oy, self.coil_w * CW, CH), power_c)
                h = CH
            last = oy
            oy += h
        self._line(p, jx, y + mid, jx, last + mid, out)

    def _series(self, p, s: Series, x, y, power):
        for k in s.kids:
            w = self._w(k) * CW
            if isinstance(k, Parallel):
                iw = w - 0.3 * CW
                x0, x1 = x + 0.15 * CW, x + w - 0.15 * CW
                self._line(p, x, y + CH / 2, x0, y + CH / 2, power)
                yy, outs, last = y, [], y
                for sub in k.kids:
                    o = self._series(p, sub, x0, yy, power)
                    outs.append(o)
                    self._line(p, x0 + self._w(sub) * CW, yy + CH / 2, x0 + iw, yy + CH / 2, o)
                    last = yy
                    yy += self._h(sub) * CH
                got = int(any(outs))
                self._line(p, x0, y + CH / 2, x0, last + CH / 2, power)
                self._line(p, x1, y + CH / 2, x1, last + CH / 2, got)
                self._line(p, x1, y + CH / 2, x + w, y + CH / 2, got)
                power = got
            else:
                v = self.cv.get(k.uid, 0)
                new = v if isinstance(k, Inline) else int(bool(power and v))
                self._contact(p, k, QRectF(x, y, w, CH), power, new, v)
                power = new
            x += w
        return power

    def _frame(self, p, uid, box):
        if uid in self._sel:
            p.setPen(QPen(QColor(theme.ACCENT2), 2))
            p.setBrush(QColor(34, 211, 238, 36))
            p.drawRoundedRect(box.adjusted(2, 2, -2, -2), 6, 6)
        if uid in self.problems:
            p.setPen(QPen(QColor(theme.DANGER), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box.adjusted(3, 3, -3, -3), 6, 6)
        p.setBrush(Qt.NoBrush)

    def _text(self, p, rect, text, size=9.5, color=theme.TEXT, bold=False, flag=Qt.AlignCenter):
        f = QFont("Segoe UI")
        f.setPointSizeF(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, flag, QFontMetricsF(f).elidedText(text, Qt.ElideRight, rect.width()))

    def _live_text(self, args, wide: bool = False) -> str:
        """ค่าปัจจุบันของ T/C/D ใน operand."""
        if not self.live:
            return ""
        out = []
        for a in args:
            d = digits(a, self.doc.app_base, self.doc.app_base)
            if d and all(self.values.get(n) is not None for n in d[2]):
                v, full = sum(bool(self.values[n]) << j for j, n in enumerate(d[2])), 32 if wide else 16
                out.append(str(v - (1 << full) if v >> full - 1 else v))
            r = resolve(a, self.doc.app_base, self.doc.app_base)
            if r and r[0] in ("T", "C", "ST", "D", "W"):
                v = self.values.get(word_name(r))
                if wide and r[0] in WIDE_WORDS:
                    hi = self.values.get(pair(r)[1])
                    v = None if v is None or hi is None else (hi << 16) | (v & 0xFFFF)
                if v is not None:
                    out.append(str(v))
        return " · ".join(out)

    def _contact(self, p, k, box, pin, pout, v):
        self.boxes[k.uid] = box
        if p is None:
            return
        self._frame(p, k.uid, box)
        cx, cy = box.center().x(), box.top() + CH / 2
        if isinstance(k, Inline) or len(k.args) > 1 or k.mod and k.mod not in ("I", "P", "F", "PI", "FI"):
            hw = 24 if isinstance(k, Inline) else box.width() / 2 - 12
            self._line(p, box.left(), cy, cx - hw, cy, pin)
            self._line(p, cx + hw, cy, box.right(), cy, pout)
            p.setPen(self._pen(v))
            p.setBrush(QColor(theme.BG_INPUT))
            p.drawRoundedRect(QRectF(cx - hw, cy - 13, hw * 2, 26), 8, 8)
            p.setBrush(Qt.NoBrush)
            txt = k.name if isinstance(k, Inline) else f"{k.args[0]} {k.mod} {' '.join(k.args[1:])}"
            self._text(p, QRectF(cx - hw, cy - 13, hw * 2, 26), txt, 9, theme.TEXT, True)
            if not isinstance(k, Inline):
                self._text(p, QRectF(box.left(), cy + 14, box.width(), 16), self._live_text(k.args, k.mod.startswith("D")), 8.5, theme.WARN)
            return
        gap = 9
        self._line(p, box.left(), cy, cx - gap, cy, pin)
        self._line(p, cx + gap, cy, box.right(), cy, pout)
        pen = QPen(QColor(theme.SUCCESS if self.live and v else theme.TEXT), 2.4)
        p.setPen(pen)
        if self.live and v:
            p.fillRect(QRectF(cx - gap, cy - 11, gap * 2, 22), QColor(34, 197, 94, 110))
        for x in (cx - gap, cx + gap):
            p.drawLine(QPointF(x, cy - 12), QPointF(x, cy + 12))
        if k.mod in ("I", "PI", "FI"):
            p.drawLine(QPointF(cx - gap - 4, cy + 12), QPointF(cx + gap + 4, cy - 12))
        if k.mod[:1] in ("P", "F"):
            self._text(p, QRectF(cx - 8, cy - 10, 16, 20), "↑" if k.mod[0] == "P" else "↓", 11, theme.TEXT, True)
        blank = k.args == (BLANK,)
        self._text(p, QRectF(box.left(), box.top() + 1, box.width(), 18), k.args[0], 10,
                   theme.WARN if blank else theme.TEXT, True)
        lab = self._live_text(k.args) or self.labels.get(k.args[0], "")
        self._text(p, QRectF(box.left() + 2, cy + 13, box.width() - 4, 17), lab, 8,
                   theme.WARN if self._live_text(k.args) else theme.TEXT_DIM)

    def _coil(self, p, c: Coil, box, on):
        self.boxes[c.uid] = box
        if p is None:
            return
        self._frame(p, c.uid, box)
        cy = box.top() + CH / 2
        simple = c.op == "OUT" and len(c.args) == 1
        col = QColor(theme.SUCCESS if self.live and on else theme.TEXT)
        if simple:
            cx = box.right() - 46
            self._line(p, box.left(), cy, cx - 15, cy, on)
            self._line(p, cx + 15, cy, box.right(), cy, on)
            p.setPen(QPen(col, 2.4))
            p.setBrush(QColor(34, 197, 94, 130) if self.live and on else QColor(theme.BG_INPUT))
            p.drawEllipse(QPointF(cx, cy), 15, 13)
            p.setBrush(Qt.NoBrush)
            self._text(p, QRectF(cx - 46, box.top() + 1, 92, 18), c.args[0], 10,
                       theme.WARN if c.args == (BLANK,) else theme.TEXT, True)
            self._text(p, QRectF(box.left(), cy + 13, box.width() - 4, 17), self.labels.get(c.args[0], ""), 8,
                       theme.TEXT_DIM, flag=Qt.AlignRight | Qt.AlignVCenter)
            return
        rc = QRectF(box.left() + 12, cy - 15, box.width() - 24, 30)
        self._line(p, box.left(), cy, rc.left(), cy, on)
        self._line(p, rc.right(), cy, box.right(), cy, on)
        p.setPen(QPen(col, 2))
        p.setBrush(QColor(34, 197, 94, 60) if self.live and on else QColor(theme.BG_INPUT))
        p.drawRoundedRect(rc, 8, 8)
        p.setBrush(Qt.NoBrush)
        self._text(p, rc, " ".join((c.op, *c.args)), 9.5, theme.TEXT, True)
        live = self._live_text(c.args, is_wide(c.op))
        self._text(p, QRectF(box.left(), cy + 15, box.width() - 14, 16), live, 8.5, theme.WARN,
                   flag=Qt.AlignRight | Qt.AlignVCenter)

    # ---------- เลือก ----------
    def sel_range(self) -> list[int]:
        f = self.doc.find(self.uid) if self.uid else None
        if not f or not self.last or not isinstance(f[2], Series):
            return [self.uid] if self.uid else []
        ids = [x.uid for x in f[1]]
        if self.last not in ids:
            return [self.uid]
        i, j = sorted((ids.index(self.uid), ids.index(self.last)))
        return ids[i:j + 1]

    def select(self, uid: int = 0, rung: int | None = None):
        self.uid = uid
        self.last = uid
        if rung is None and uid:
            rung = self.doc.rung_of(uid)
        if rung is not None and rung >= 0:
            self.rung = self.rung_to = rung
        self._reveal()
        self.update()
        self.selected.emit()

    def first_uid(self, n: int) -> int:
        r = self.doc.rungs[n]
        if r.is_raw:
            return 0
        x = r.body.cond.kids[0]
        while isinstance(x, (Parallel, Series)):
            x = x.kids[0]
        return x.uid

    def _reveal(self):
        sc = self.view.area
        if 0 <= self.rung < len(self.rung_y):
            y, h = self.rung_y[self.rung]
            box = self.boxes.get(self.uid) or QRectF(LEFT, y, 80, h)
            c = box.center() * self.scale
            sc.ensureVisible(int(c.x()), int(c.y()), int(box.width() * self.scale / 2 + 30),
                             int(box.height() * self.scale / 2 + 30))

    def _at(self, pos):
        q = QPointF(pos) / self.scale
        for uid, b in self.boxes.items():
            if b.contains(q):
                return uid, self.box_rung[uid]
        for n, (y, h) in enumerate(self.rung_y):
            if y <= q.y() < y + h:
                return 0, n
        return 0, None

    def mousePressEvent(self, e):
        self.close_editor()
        self.setFocus()
        uid, n = self._at(e.position())
        if n is None:
            return
        if e.modifiers() & Qt.ShiftModifier and uid and self.uid and n == self.rung:
            self.last = uid
            self.update()
        elif e.modifiers() & Qt.ShiftModifier and not uid:
            self.rung_to, self.uid, self.last = n, 0, 0
            self.update()
        else:
            self.select(uid, n)

    def mouseDoubleClickEvent(self, e):
        uid, n = self._at(e.position())
        if n is not None:
            q = e.position().y() / self.scale - self.rung_y[n][0]
            if not uid and q < 24:
                self.view.edit_comment()
            else:
                self.view.edit_current()

    def mouseMoveEvent(self, e):
        uid, n = self._at(e.position())
        r = self.doc.rungs[n].uid if n is not None else 0
        tip = self.problems.get(uid) or self.problems.get(r) or ""
        if not tip and uid:
            x = self.doc.find(uid)[0]
            tip = " · ".join(f"{a}: {self.labels[a]}" for a in getattr(x, "args", ()) if a in self.labels)
        QToolTip.showText(e.globalPosition().toPoint(), tip, self)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom(1.1 if e.angleDelta().y() > 0 else 1 / 1.1)
            e.accept()
        else:
            super().wheelEvent(e)

    def zoom(self, k):
        self.close_editor()
        self.scale = max(0.5, min(2.0, self.scale * k))
        self.relayout()

    # ---------- เลื่อนตำแหน่ง ----------
    def go(self, dx: int, dy: int, extend=False):
        if extend and dx:
            f = self.doc.find(self.uid) if self.uid else None
            if f and isinstance(f[2], Series):
                ids = [x.uid for x in f[1]]
                i = ids.index(self.last) if self.last in ids else ids.index(self.uid)
                self.last = ids[max(0, min(len(ids) - 1, i + dx))]
                self.update()
            return
        if extend and dy:
            self.rung_to = max(0, min(len(self.doc.rungs) - 1, self.rung_to + dy))
            self.uid = self.last = 0
            self.update()
            return
        cur = self.boxes.get(self.uid)
        if dx:
            if cur is None:
                if not self.doc.rungs[self.rung].is_raw:
                    self.select(self.first_uid(self.rung))
                return
            c = cur.center()
            best = None
            for uid, b in self.boxes.items():
                d = (b.center().x() - c.x()) * dx
                if uid == self.uid or self.box_rung[uid] != self.rung or d < 5:
                    continue
                k = (abs(b.center().y() - c.y()) * 2 + d, d)
                if best is None or k < best[0]:
                    best = (k, uid)
            if best:
                self.select(best[1])
            return
        best = None
        if cur is not None:
            c = cur.center()
            for uid, b in self.boxes.items():
                d = (b.center().y() - c.y()) * dy
                if d > 5 and self.box_rung[uid] == self.rung:
                    k = (d, abs(b.center().x() - c.x()))
                    if best is None or k < best[0]:
                        best = (k, uid)
        if best:
            self.select(best[1])
            return
        n = self.rung + dy
        if n >= len(self.doc.rungs):
            if not is_blank(self.doc.rungs[-1]) and self.view.editable(quiet=True):
                self.doc.insert_rung(n)
                self.view.after_edit()
                self.select(self.first_uid(n), n)
            return
        if n < 0:
            return
        x = cur.center().x() if cur is not None else 0
        cands = [(abs(b.center().x() - x), u) for u, b in self.boxes.items() if self.box_rung[u] == n]
        if cur is None or not cands:
            self.select(0 if not cands else self.first_uid(n), n)
        else:
            self.select(min(cands)[1], n)

    # ---------- ช่องพิมพ์ ----------
    def open_editor(self, box: QRectF, text: str, commit, hint=""):
        self.close_editor(done=True)
        ed = QLineEdit(self)
        ed.setObjectName("LadderEdit")
        ed.setStyleSheet(f"QLineEdit {{ font-family:Consolas; font-size:11pt; background:{theme.BG_INPUT}; color:{theme.TEXT};"
                         f" border:2px solid {theme.ACCENT2}; border-radius:6px; padding:3px 6px; }}")
        ed.setPlaceholderText(hint)
        ed.setMaxLength(90)
        ed.setText(text)
        k = self.scale
        w = max(190, int(box.width() * k))
        x = max(4, min(int(box.center().x() * k - w / 2), self.width() - w - 4))
        ed.setGeometry(x, int(box.center().y() * k - 17), w, 34)
        ed.installEventFilter(self)
        self.editor, self._commit = ed, commit
        ed.show()
        ed.setFocus()
        if len(text) > 1:
            ed.selectAll()

    def _enter(self):
        ed, fn = self.editor, self._commit
        if ed is None or fn is None:
            return
        try:
            fn(ed.text())
        except LadderError as e:
            self.message.emit(f"✖ {e}")
            QToolTip.showText(ed.mapToGlobal(ed.rect().bottomLeft()), str(e), ed)
            ed.setStyleSheet(ed.styleSheet().replace(theme.ACCENT2, theme.DANGER))
            return
        if self.editor is ed:                 # คำสั่งอาจเปิดช่องใหม่ไปแล้ว
            self.close_editor(done=True)

    def close_editor(self, done=False):
        """done=False = ยกเลิก (ชิ้นที่เพิ่งแทรกไว้ถูกถอนคืน)."""
        ed, self.editor, self._commit = self.editor, None, None
        if ed is not None:
            ed.removeEventFilter(self)
            ed.hide()
            ed.deleteLater()
            if not done:
                self.view.entry_cancelled()
            self.setFocus()

    def eventFilter(self, obj, e):
        if self.editor is not None and obj is self.editor:
            if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Escape, Qt.Key_F4):
                e.accept()
                return True
            if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                self.close_editor()
                return True
            if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                self._enter()              # กิน event ไว้ ไม่งั้นหลุดไปถึงผืนวาดแล้วเปิดช่องใหม่
                return True
        return super().eventFilter(obj, e)

    # ---------- คีย์ ----------
    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and self.view.wants_key(e):
            e.accept()                    # ให้คีย์ของแท็บนี้มาก่อนคีย์ลัดของหน้าต่าง (เช่น Ctrl+Z ของผัง)
            return True
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.go(1 if e.key() == Qt.Key_Tab else -1, 0)
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if not self.view.handle_key(e):
            super().keyPressEvent(e)


# ======================= แท็บ =======================
_FLIP = {"": "I", "I": "", "P": "PI", "PI": "P", "F": "FI", "FI": "F"}


class LadderView(QWidget):
    send_requested = Signal()
    control = Signal(str)                     # run / stop / reset
    learn_requested = Signal()                # ปุ่ม 🎓 บทเรียน ladder
    message = Signal(str)

    def __init__(self, xy_base: int = 8, parent=None):
        super().__init__(parent)
        self.doc = LadderDoc(xy_base)
        self.file: Path | None = None
        self.exam = False
        self.locked = lambda: False           # กำลังตรวจด่าน → แก้ไม่ได้
        self.soft = lambda: None
        self.sent = None                      # Compiled ที่อยู่ใน PLC ในตัว
        self._sent_code: list | None = None
        self._cur_code: list = []
        self._pending = None                  # (uid ที่เพิ่งแทรก, uid เดิมที่เลือก) ระหว่างพิมพ์ — Esc = ถอนคืน
        self._clip = ""
        self._save_blocked = False
        self._saved_rev = self.doc.revision
        self._len_cache: dict = {}
        self._uid_cache = (-1, [])
        self.save_error = ""

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        bar1, bar2 = QHBoxLayout(), QHBoxLayout()
        for b in (bar1, bar2):
            b.setSpacing(4)
            v.addLayout(b)
        self.buttons: dict[str, QToolButton] = {}

        def btn(bar, key, text, tip, fn):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda *_: fn())
            bar.addWidget(b)
            self.buttons[key] = b

        B = bar1
        btn(B, "no", "┤ ├ F5", tr("หน้าสัมผัส NO ต่ออนุกรม (Ctrl+F5 = แทรกก่อน)"), lambda: self.add_contact(""))
        btn(B, "nc", "┤/├ F6", tr("หน้าสัมผัส NC ต่ออนุกรม (Ctrl+F6 = แทรกก่อน)"), lambda: self.add_contact("I"))
        btn(B, "pno", "└┤ ├┘ Shift+F5", tr("ต่อขนานด้วย NO (เลือกช่วงด้วย Shift+→ ก่อนได้)"),
            lambda: self.add_contact("", parallel=True))
        btn(B, "pnc", "└┤/├┘ Shift+F6", tr("ต่อขนานด้วย NC"), lambda: self.add_contact("I", parallel=True))
        btn(B, "coil", "( ) F7", tr("คอยล์ / output เพิ่มอีกตัว"), lambda: self.add_coil())
        btn(B, "branch", "├( ) Shift+F7", tr("output ที่มีหน้าสัมผัสของตัวเอง (แยกกิ่ง)"), lambda: self.add_coil(branch=True))
        btn(B, "func", "[ ] F8", tr("คำสั่ง เช่น MOV K10 D0, SET M0, RST C0"), lambda: self.add_coil(func=True))
        btn(B, "learn", "🎓", tr("บทเรียน ladder: วาด ladder แรก ส่งลง PLC ในตัว แล้วดูสถานะสด"), self.learn_requested.emit)
        btn(B, "ins", "+ rung", tr("แทรก rung ใต้ rung นี้ (Insert, Shift+Insert = เหนือ)"), lambda: self.insert_rung())
        btn(B, "del", tr("ลบ"), tr("ลบชิ้นที่เลือก (Delete) / ทั้ง rung (Ctrl+Delete)"), lambda: self.delete())
        btn(B, "undo", "↶", tr("ย้อนกลับ (Ctrl+Z)"), lambda: self.undo())
        btn(B, "redo", "↷", tr("ทำซ้ำ (Ctrl+Y)"), lambda: self.redo())
        btn(B, "note", tr("คอมเมนต์"), tr("คอมเมนต์ของ rung (กด ;)"), lambda: self.edit_comment())
        btn(B, "text", tr("ข้อความ"), tr("แก้ rung นี้เป็นคำสั่งแบบข้อความ"), lambda: self.edit_text())
        B.addStretch(1)
        B = bar2
        btn(B, "send", tr("▶ F4 ส่งลง PLC"), tr("ตรวจ ladder แล้วส่งลง PLC ในตัว (ล้าง M/T/C/D แล้ว RUN)"),
            lambda: self.send_requested.emit())
        btn(B, "run", "RUN", tr("ให้ PLC ในตัวทำงาน"), lambda: self.control.emit("run"))
        btn(B, "stop", "STOP", tr("หยุด PLC ในตัว (Y ดับหมด)"), lambda: self.control.emit("stop"))
        btn(B, "reset", "RESET", tr("ล้าง M/T/C/D และข้อผิดพลาด แล้วหยุด"), lambda: self.control.emit("reset"))
        self.lbl_state = QLabel()
        B.addWidget(self.lbl_state)
        self.lbl_file = QLabel()
        self.lbl_file.setStyleSheet(f"color:{theme.TEXT_DIM};")
        B.addWidget(self.lbl_file, 1)
        btn(B, "import", tr("นำเข้า CSV"), tr("เปิด CSV ที่ Export จาก GX Works3 (แทนที่ ladder นี้ กด Ctrl+Z ย้อนได้)"),
            lambda: self.import_csv())
        btn(B, "export", tr("ส่งออก CSV"), tr("บันทึก CSV ไปนำเข้าใน GX Works3: Edit → Import File\nตรวจ ladder หลังนำเข้า (คำสั่งที่ PLC รุ่นนั้นไม่มีจะเป็น OUT SM4095)"),
            lambda: self.export_csv())

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFocusPolicy(Qt.NoFocus)
        self.canvas = LadderCanvas(self)
        self.canvas.message.connect(self.message)
        self.area.setWidget(self.canvas)
        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(QLabel(tr("อุปกรณ์บนผัง (ดับเบิลคลิก = ใช้)")))
        self.addr = QListWidget()
        self.addr.setFocusPolicy(Qt.NoFocus)
        self.addr.itemDoubleClicked.connect(lambda it: self.use_address(it.data(Qt.UserRole)))
        sv.addWidget(self.addr, 3)
        sv.addWidget(QLabel(tr("ผลตรวจ ladder")))
        self.probs = QListWidget()
        self.probs.setWordWrap(True)
        self.probs.setFocusPolicy(Qt.NoFocus)
        self.probs.itemClicked.connect(lambda it: self.goto_uid(*it.data(Qt.UserRole)))
        sv.addWidget(self.probs, 2)
        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self.area)
        sp.addWidget(side)
        sp.setStretchFactor(0, 1)
        sp.setSizes([900, 220])
        v.addWidget(sp, 1)
        self.setFocusProxy(self.canvas)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTOSAVE_MS)
        self._save_timer.timeout.connect(self.flush)
        self._mon = QTimer(self)
        self._mon.setInterval(100)
        self._mon.timeout.connect(self.refresh_monitor)
        self._mon.start()
        self.canvas.select(self.canvas.first_uid(0), 0)
        self._state()

    # ---------- สถานะ ----------
    def editable(self, quiet=False) -> bool:
        if self.locked():
            if not quiet:
                self.message.emit(tr("🔒 กำลังตรวจคำตอบ — แก้ ladder ไม่ได้"))
            return False
        return True

    def rung_len(self, r: Rung) -> int:
        key = (self.doc.revision, r.uid)
        if key not in self._len_cache:
            if len(self._len_cache) > 3000:
                self._len_cache.clear()
            self._len_cache[key] = len(rung_code(r))
        return self._len_cache[key]

    def code(self) -> list:
        return [(i.op, i.args) for i in self.doc.compile().program.instrs]

    @property
    def unsent(self) -> bool:
        return (not self.empty) if self._sent_code is None else self._cur_code != self._sent_code

    @property
    def empty(self) -> bool:
        return all(is_blank(r) for r in self.doc.rungs)

    def mark_sent(self, compiled):
        self.sent = compiled
        self._sent_code = [(i.op, i.args) for i in compiled.program.instrs] if compiled else None
        self._cur_code = self.code()
        self._state()

    def after_edit(self):
        self._cur_code = self.code()
        self.canvas.problems = {}
        self.probs.clear()
        self.canvas.relayout()
        self._save_timer.start()
        self._state()

    def _state(self):
        s = self.soft()
        if s is None:
            text, col = tr("PLC ในตัวยังไม่ได้เชื่อมต่อ"), theme.TEXT_DIM
        elif s.state == "error":
            text, col = "✖ " + s.fault, theme.DANGER
        elif self.unsent:
            text, col = tr("● แก้แล้วยังไม่ส่ง — กด F4"), theme.WARN
        else:
            text, col = {"run": ("● RUN", theme.SUCCESS), "stop": ("■ STOP", theme.WARN)}.get(
                s.state, (tr("ยังไม่มี ladder ใน PLC"), theme.TEXT_DIM))
        if text != self.lbl_state.text():
            self.lbl_state.setText(text)
            self.lbl_state.setStyleSheet(f"color:{col}; font-weight:bold; padding:0 8px;")
        st = s.state if s else ""
        ed = not self.locked()
        for k, on in (("run", st == "stop" and ed), ("stop", st == "run" and ed),
                      ("reset", st in ("run", "stop", "error") and ed), ("import", ed and not self.exam),
                      ("export", not self.exam), ("text", ed and not self.exam), ("send", ed)):
            self.buttons[k].setEnabled(on)
        for k in ("no", "nc", "pno", "pnc", "coil", "branch", "func", "ins", "del", "undo", "redo", "note"):
            self.buttons[k].setEnabled(ed)

    def refresh_monitor(self):
        s, c = self.soft(), self.canvas
        self._state()
        if not (s and s.state == "run" and self.sent and not self.unsent):
            if c.live:
                c.live = False
                c.cv, c.cond, c.values = {}, {}, {}
                c.update()
            return
        if not self.isVisible():
            return
        m, now = s.monitor(), self._uids()          # โค้ดเท่าที่ส่ง → ลำดับคำสั่งตรงกัน
        c.cv = {now[k]: v for k, v in m["cv"].items() if k < len(now)}
        c.cond = {now[k]: v for k, v in m["cond"].items() if k < len(now)}
        c.values, c.live = m["values"], True
        c.update()

    def _uids(self):
        if self._uid_cache[0] != self.doc.revision:
            self._uid_cache = (self.doc.revision, [u for _, u in self.doc.compile().where])
        return self._uid_cache[1]

    # ---------- ไฟล์ ----------
    def open_file(self, path: Path, exam: bool = False):
        """เปลี่ยนไปใช้ ladder ของนักเรียน/ด่านนี้ (บันทึกของเดิมก่อน)."""
        path = Path(path)
        if path == self.file and exam == self.exam:
            return
        self.canvas.close_editor()
        self.flush()
        if exam or self.exam:
            self._clip = ""                       # ห้ามนำวงจรข้ามด่านในการสอบ
        self.file, self.exam, self._save_blocked, self.save_error = path, exam, False, ""
        rev = self.doc.revision
        self.doc = self.canvas.doc = LadderDoc(self.doc.app_base)
        self.doc.revision = rev + 1
        if path.exists():
            try:
                self.doc.load(load_csv(path, allow_empty=True))
            except LadderError as e:
                bad = path.with_name(path.name + ".bad")
                try:
                    path.replace(bad)
                    self.message.emit(tr("⚠ อ่าน ladder ที่บันทึกไว้ไม่ได้ ({0}) — เก็บไว้ที่ {1} แล้วเริ่มใหม่", e, bad.name))
                except OSError:
                    self._save_blocked = True     # อ่านไม่ได้และย้ายไม่ได้: ห้ามเขียนทับงานเดิม
                    self.message.emit(tr("⚠ อ่าน ladder ที่บันทึกไว้ไม่ได้ ({0}) — จะไม่บันทึกทับ", e))
        self._saved_rev = self.doc.revision
        self.mark_sent(None)
        c = self.canvas
        c.problems = {}
        self.probs.clear()
        c.uid = c.last = c.rung = c.rung_to = 0
        c.relayout()
        c.select(c.first_uid(0), 0)
        self._file_label()

    def flush(self):
        """บันทึกถ้ามีการแก้ (เรียกอัตโนมัติ, ก่อนเปลี่ยนด่าน/นักเรียน และตอนปิด)."""
        self._save_timer.stop()
        if self.file is None or self._save_blocked or self.doc.revision == self._saved_rev:
            return
        if self.empty and not self.file.exists() and not any(r.comment for r in self.doc.rungs):
            return
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            save_csv(self.file, self.doc.compile(keep_blank=True).program)
            self._saved_rev, self.save_error = self.doc.revision, ""
        except (LadderError, OSError) as e:
            if self.save_error != str(e):
                self.message.emit(f"✖ {e}")
            self.save_error = str(e)
        self._file_label()

    def _file_label(self):
        if self.save_error:
            self.lbl_file.setText(tr("⚠ ยังไม่ได้บันทึก: {0}", self.save_error))
        else:
            self.lbl_file.setText((tr("📝 สอบ · ") if self.exam else "") + (self.file.stem if self.file else ""))

    def import_csv(self, path=None):
        if self.exam or not self.editable():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, tr("เลือกไฟล์ CSV ที่ Export จาก GX Works3"), "", "CSV (*.csv)")
            if not path:
                return
        self.canvas.close_editor()
        try:
            prog = load_csv(path)
            new = rungs_from(rebase(prog, self.doc.app_base))
        except LadderError as e:
            self.message.emit(f"✖ {e}")
            return
        self.doc.replace_all(new)
        self.after_edit()
        self.canvas.select(self.canvas.first_uid(0), 0)
        self.message.emit(tr("📄 นำเข้า {0} แล้ว ({1} rung)", Path(path).name, len(new)))
        if prog.dropped:
            self.message.emit(tr("⚠ Note / P/I statement {0} รายการไม่ถูกนำเข้า", prog.dropped))

    def export_csv(self, path=None):
        if self.exam:
            return
        c = self.doc.compile()
        if any(BLANK in i.args for i in c.program.instrs):
            self.show_problems(c, check(Ladder(c.program, self.doc.app_base)))
            self.message.emit(tr("✖ ยังมีช่องที่ไม่ได้กรอก (?) — กรอกให้ครบก่อนส่งออก"))
            return
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("ส่งออก CSV"), (self.file.stem if self.file else "ladder") + ".csv",
                                                  "CSV (*.csv)")
            if not path:
                return
        try:
            save_csv(path, c.program)
        except (LadderError, OSError) as e:
            self.message.emit(f"✖ {e}")
            return
        self.message.emit(tr("💾 ส่งออก {0} แล้ว — ใน GX Works3 เลือก Edit → Import File ({1})", Path(path).name, c.program.module))

    # ---------- ปัญหา / address ----------
    def show_problems(self, compiled, problems, notes=()):
        self.probs.clear()
        self.canvas.problems = {}
        for p in problems:
            n, uid = compiled.where[p.k] if 0 <= p.k < len(compiled.where) else (self.canvas.rung, 0)
            n = min(n, len(self.doc.rungs) - 1)
            if uid:
                self.canvas.problems[uid] = p.text
            self.canvas.problems.setdefault(self.doc.rungs[n].uid, p.text)
            self._prob_item(f"✖ rung {n + 1}: {p.text}", theme.DANGER, uid, n)
        for f in notes:
            n, uid = compiled.where[f.step] if f.step is not None and 0 <= f.step < len(compiled.where) else (0, 0)
            self._prob_item(f"⚠ {f.title}", theme.WARN, uid, n)
        if not problems and not notes:
            self._prob_item(tr("✔ ไม่พบปัญหา"), theme.SUCCESS, 0, self.canvas.rung)
        self.canvas.update()

    def _prob_item(self, text, col, uid, n):
        it = QListWidgetItem(text)
        it.setForeground(QColor(col))
        it.setData(Qt.UserRole, (uid, n))
        self.probs.addItem(it)

    def notes(self, compiled) -> list:
        """คำเตือนอ่านจากโค้ด เช่น double coil (โหมดสอบไม่บอก)."""
        if self.exam:
            return []
        return [f for f in static_findings(Ladder(compiled.program, self.doc.app_base)) if f.level in ("warn", "error")]

    def goto_uid(self, uid: int, rung: int = -1):
        self.canvas.close_editor()
        n = self.doc.rung_of(uid) if uid else -1
        n = n if n >= 0 else min(max(rung, 0), len(self.doc.rungs) - 1)
        self.canvas.select(uid if uid in self.canvas.boxes else 0, n)
        self.canvas.setFocus()

    def goto_step(self, step: int, compiled=None):
        c = compiled or self.sent
        if c and 0 <= step < len(c.where):
            self.goto_uid(c.where[step][1], c.where[step][0])

    def set_addresses(self, rows):
        """[(address, ป้าย)] ของอุปกรณ์บนผัง — ผังเก็บ TS0/TN0 แต่ ladder เขียน T0."""
        lab: dict[str, str] = {}
        for a, t in rows:
            lab.setdefault(re.sub(r"^(T|C)[SN](?=\d)", r"\1", a), t)
        if lab == self.canvas.labels:
            return
        self.canvas.labels = lab
        self.addr.clear()
        for a, t in lab.items():
            it = QListWidgetItem(f"{a}   {t}")
            it.setData(Qt.UserRole, a)
            self.addr.addItem(it)
        self.canvas.update()

    def use_address(self, a: str):
        c = self.canvas
        if c.editor is not None:
            t = c.editor.text()
            c.editor.setText(t + a if not t or t.endswith((" ", "/")) else f"{t} {a}")
            c.editor.setFocus()
            return
        f = self._cur()
        if f and self.editable():
            x = f[0]
            if isinstance(x, Leaf) and len(x.args) == 1:
                self.doc.set_leaf(x.uid, x.mod, [a])
            elif isinstance(x, Coil) and x.op in ("OUT", "SET", "RST", "PLS", "PLF", "FF") and len(x.args) <= 1:
                self.doc.set_coil(x.uid, x.op, [a])
            else:
                return
            self.after_edit()
            c.go(1, 0)
        c.setFocus()

    # ---------- แก้ไข ----------
    def _cur(self):
        c = self.canvas
        return self.doc.find(c.uid) if c.uid else None

    def _need_item(self):
        """ชิ้นที่เลือก (ไม่ได้เลือก = คอยล์ท้ายของ rung)."""
        f = self._cur()
        if f is None:
            r = self.doc.rungs[self.canvas.rung]
            if r.is_raw:
                self.message.emit(tr("rung นี้เป็นข้อความคำสั่ง — กด Enter เพื่อแก้"))
                return None
            b = r.body
            while isinstance(b.outs[-1], Branch):
                b = b.outs[-1]
            self.canvas.select(b.outs[-1].uid)
            f = self._cur()
        return f

    def add_contact(self, mod: str, parallel=False, before=False, leaf: Leaf | None = None) -> bool:
        """leaf=None: แทรกช่องว่างแล้วเปิดช่องพิมพ์ · มี leaf: ใส่ทันที."""
        if leaf is None:
            self.canvas.close_editor()
        if not self.editable():
            return False
        f = self._need_item()
        if f is None:
            return False
        x, _box, owner = f
        if isinstance(x, Leaf) and x.args == (BLANK,) and not parallel and not before:
            if leaf is None:
                self._open_leaf(x.uid, mod=mod)
            else:
                self.doc.set_leaf(x.uid, leaf.mod, leaf.args)
                self.after_edit()
                self.canvas.go(1, 0)
            return True
        new = leaf or Leaf(mod)
        if not parallel:
            uid = self.doc.add_series(x.uid, new, before)
        elif isinstance(x, Coil):                          # คอยล์: ขนานเงื่อนไขทั้งหมดของมัน
            k = owner.cond.kids
            uid = self.doc.add_parallel(k[0].uid, new, k[-1].uid)
        else:
            uid = self.doc.add_parallel(x.uid, new, self.canvas.last or None)
        if uid is None:
            self.message.emit(tr("✖ ขนานตรงนี้ไม่ได้ (มี INV/MEP/MEF หรือเลือกคนละแนว)") if parallel
                              else tr("✖ แทรกตรงนี้ไม่ได้"))
            return False
        self.after_edit()
        self.canvas.select(uid)
        if leaf is None:
            self._pending = (uid, x.uid)
            self._open_leaf(uid, mod=mod)
        else:
            self.canvas.go(1, 0)
        return True

    def add_inline(self, node: Inline):
        f = self._need_item()
        if f is None or not self.editable():
            return
        uid = self.doc.add_series(f[0].uid, node)
        if uid:
            self.after_edit()
            self.canvas.go(1, 0)

    def add_coil(self, branch=False, func=False, coil: Coil | None = None):
        c = self.canvas
        if coil is None:
            c.close_editor()
        if not self.editable():
            return
        if coil is not None and standalone(coil.op):
            return self._add_standalone(coil)
        f = self._need_item()
        if f is None:
            return
        x = f[0]
        hint = tr("เช่น MOV K10 D0 · SET M0 · RST C0") if func else tr("เช่น Y0 · T0 K30 · SET M0")
        if not branch:
            blank = x if isinstance(x, Coil) and x.args == (BLANK,) else None
            if blank is None and not isinstance(x, Coil):
                blank = next((y for y, _, _ in walk(self.doc.rungs[c.rung]) if isinstance(y, Coil) and y.args == (BLANK,)), None)
            if blank is not None:
                c.select(blank.uid)
                if coil is None:
                    self._open_coil(blank.uid, hint)
                else:
                    self.doc.set_coil(blank.uid, coil.op, coil.args)
                    self.after_edit()
                return
        uid = self.doc.add_coil(x.uid, coil, branch)
        if uid is None:
            return
        self.after_edit()
        c.select(uid)
        if coil is None:
            self._pending = (uid, x.uid)
            self._open_leaf(uid) if branch else self._open_coil(uid, hint)

    def _add_standalone(self, coil: Coil):
        n = self.canvas.rung
        raw = Rung(None, [(coil.op, tuple(coil.args))])
        if is_blank(self.doc.rungs[n]):
            self.doc.set_rung_text(n, " ".join((coil.op, *coil.args)))
        else:
            n = self.doc.insert_rung(n + 1, raw)
        self.after_edit()
        self.canvas.select(0, n)

    def _open_leaf(self, uid, text="", mod=None):
        f, box = self.doc.find(uid), self.canvas.boxes.get(uid)
        if not f or box is None:
            return
        x = f[0]
        if not text and x.args != (BLANK,):
            text = x.args[0] if len(x.args) < 2 else f"{x.mod} {x.args[0]} {x.args[1]}" if x.mod.startswith("D") \
                else f"{x.args[0]}{x.mod}{x.args[1]}"
        m = x.mod if mod is None else mod
        self.canvas.open_editor(box, text, lambda t: self._set_leaf(uid, t, m), tr("เช่น X0 · /X1 · D0>=K5"))

    def _set_leaf(self, uid, text, mod):
        kind, obj = parse_entry(text, self.doc.app_base)
        pend = self._pending if self._pending and self._pending[0] == uid else None
        if kind in ("coil", "inline"):
            if not pend:
                raise LadderError(tr("ช่องนี้เป็นหน้าสัมผัส — พิมพ์ device เช่น X0"))
            self._rollback()
            self.canvas.select(pend[1])
            self.add_coil(coil=obj) if kind == "coil" else self.add_inline(obj)
            return
        if kind == "device":
            done = self.doc.set_leaf(uid, mod if mod in _FLIP else "", obj)
        else:
            done = self.doc.set_leaf(uid, obj.mod, obj.args)
        self._merge(pend and done)
        self.after_edit()
        self.canvas.select(uid)
        self.canvas.go(1, 0)

    def _open_coil(self, uid, hint=""):
        f, box = self.doc.find(uid), self.canvas.boxes.get(uid)
        if not f or box is None:
            return
        x = f[0]
        text = "" if x.args == (BLANK,) else " ".join(x.args if x.op == "OUT" else (x.op, *x.args))
        self.canvas.open_editor(box, text, lambda t: self._set_coil(uid, t), hint or tr("เช่น Y0 · T0 K30 · SET M0"))

    def _set_coil(self, uid, text):
        kind, obj = parse_entry(text, self.doc.app_base)
        pend = self._pending if self._pending and self._pending[0] == uid else None
        if kind == "device":
            done = self.doc.set_coil(uid, "OUT", obj)
        elif kind != "coil":
            raise LadderError(tr("ช่องนี้เป็นคอยล์/คำสั่ง — พิมพ์ เช่น Y0, T0 K30, MOV K1 D0"))
        elif standalone(obj.op):
            if pend:
                self._rollback()
                self.canvas.select(pend[1])
            self._add_standalone(obj)
            return
        else:
            done = self.doc.set_coil(uid, obj.op, obj.args)
        self._merge(pend and done)
        self.after_edit()
        self.canvas.select(uid)

    def _merge(self, both):
        """การแทรก + การกรอก = undo ครั้งเดียว."""
        if both:
            self.doc.merge_undo()
        self._pending = None

    def _rollback(self):
        self._pending = None
        if self.doc.undo():
            self.doc.drop_redo()
            self.after_edit()

    def entry_cancelled(self):
        if self._pending:
            back, n = self._pending[1], self.canvas.rung
            self._rollback()
            self.canvas.select(back if self.doc.find(back) else 0, n)

    def edit_current(self):
        if not self.editable():
            return
        c = self.canvas
        r = self.doc.rungs[c.rung]
        if r.is_raw:
            if len(r.raw) > 1:
                return self.edit_text()
            y, _h = c.rung_y[c.rung]
            op, args = r.raw[0]
            c.open_editor(QRectF(LEFT + 14, y + 20, 260, 40), " ".join((op, *args)), self._set_raw)
            return
        f = self._cur()
        if f is None:
            c.select(c.first_uid(c.rung))
            f = self._cur()
        x = f[0]
        if isinstance(x, Leaf):
            self._open_leaf(x.uid)
        elif isinstance(x, Coil):
            self._open_coil(x.uid)

    def _set_raw(self, text):
        t = " ".join(text.upper().split())
        _clean(t)
        self.doc.set_rung_text(self.canvas.rung, t)
        self.after_edit()

    def typed(self, ch: str):
        """พิมพ์ตัวอักษร: ช่องว่างอยู่ = กรอก, ไม่ว่าง = เพิ่มชิ้นใหม่ถัดจากที่เลือกตามคำสั่งที่พิมพ์."""
        if not self.editable():
            return
        f = self._need_item()
        if f is None:
            return
        x = f[0]
        box = self.canvas.boxes[x.uid]
        blank = getattr(x, "args", None) == (BLANK,)
        if isinstance(x, Leaf) and blank:
            self._open_leaf(x.uid, ch)
        elif isinstance(x, Coil) and blank:
            self.canvas.open_editor(box, ch, lambda t: self._typed_on_coil(x.uid, t), tr("เช่น Y0 · T0 K30 · SET M0"))
        else:
            self.canvas.open_editor(box, ch, lambda t: self._typed_new(x.uid, t), tr("เช่น ANI X1 · OR Y0 · OUT Y1"))

    def _typed_on_coil(self, uid, text):
        kind, _obj = parse_entry(text, self.doc.app_base)
        if kind in ("device", "coil"):
            return self._set_coil(uid, text)
        self._typed_new(uid, text)

    def _typed_new(self, uid, text):
        kind, obj = parse_entry(text, self.doc.app_base)
        self.canvas.select(uid)
        x = self.doc.find(uid)[0]
        if kind == "device":
            if isinstance(x, Coil):
                self.add_coil(coil=Coil("OUT", tuple(obj)))
            else:
                self.add_contact("", leaf=Leaf("", tuple(obj)))
        elif kind == "coil":
            self.add_coil(coil=obj)
        elif kind == "inline":
            self.add_inline(obj)
        else:
            self.add_contact(obj.mod, parallel=kind == "or", leaf=obj)

    def toggle(self):
        f = self._cur()
        if f and isinstance(f[0], Leaf) and f[0].mod in _FLIP and self.editable():
            self.doc.set_leaf(f[0].uid, _FLIP[f[0].mod], f[0].args)
            self.after_edit()

    def delete(self, rung=False):
        if not self.editable():
            return
        c = self.canvas
        c.close_editor()
        n = c.rung
        if rung or not c.uid or is_blank(self.doc.rungs[n]):
            a, b = sorted((c.rung, c.rung_to))
            self.doc.delete_rungs(a, b)
            self.after_edit()
            n = min(a, len(self.doc.rungs) - 1)
            c.select(c.first_uid(n), n)
            return
        pos = c.boxes[c.uid].center()
        done = 0
        for u in c.sel_range():
            if self.doc.delete(u):
                done += 1
                if done > 1:
                    self.doc.merge_undo()              # ลบหลายตัว = undo ครั้งเดียว
        self.after_edit()
        near = [(abs(b.center().x() - pos.x()) + abs(b.center().y() - pos.y()), u) for u, b in c.boxes.items()
                if c.box_rung[u] == n]
        c.select(min(near)[1] if near else 0, n)

    def insert_rung(self, above=False):
        if not self.editable():
            return
        self.canvas.close_editor()
        n = self.doc.insert_rung(self.canvas.rung + (0 if above else 1))
        self.after_edit()
        self.canvas.select(self.canvas.first_uid(n), n)

    def move_rung(self, d):
        if self.editable():
            n = self.doc.move_rung(self.canvas.rung, d)
            self.after_edit()
            self.canvas.select(self.canvas.uid, n)

    def undo(self, redo=False):
        if not self.editable():
            return
        if self.canvas.editor is not None:
            self.canvas.close_editor()             # กำลังพิมพ์อยู่: ย้อน = ยกเลิกการพิมพ์
            return
        if self.doc.redo() if redo else self.doc.undo():
            self.after_edit()

    def redo(self):
        self.undo(True)

    def edit_comment(self):
        if not self.editable():
            return
        self.canvas.close_editor()
        n = self.canvas.rung
        t, ok = QInputDialog.getText(self, tr("คอมเมนต์"), tr("คอมเมนต์ของ rung {0}", n + 1), text=self.doc.rungs[n].comment)
        if ok and self.doc.set_comment(n, t):
            self.after_edit()

    def edit_text(self):
        if self.exam or not self.editable():
            return
        self.canvas.close_editor()
        n = self.canvas.rung
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("แก้ rung {0} เป็นข้อความ", n + 1))
        dlg.resize(420, 380)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(tr("คำสั่งบรรทัดละ 1 ตัว เช่น LD X0 — ใส่หลาย rung ได้")))
        te = QPlainTextEdit("" if is_blank(self.doc.rungs[n]) else self.doc.rung_text(n))
        te.setStyleSheet("font-family:Consolas;")
        lay.addWidget(te)
        err = QLabel()
        err.setWordWrap(True)
        err.setStyleSheet(f"color:{theme.DANGER};")
        lay.addWidget(err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.rejected.connect(dlg.reject)

        def ok():
            try:
                self.doc.set_rung_text(n, te.toPlainText())
            except LadderError as e:
                err.setText(str(e))
                return
            dlg.accept()
        bb.accepted.connect(ok)
        if dlg.exec() == QDialog.Accepted:
            self.after_edit()
            self.canvas.select(0, n)

    # ---------- คลิปบอร์ด ----------
    def copy_rungs(self):
        a, b = sorted((self.canvas.rung, self.canvas.rung_to))
        self._clip = self.doc.copy_text(a, b)
        if not self.exam:
            QApplication.clipboard().setText(self._clip)
        self.message.emit(tr("คัดลอก {0} rung", b - a + 1))

    def paste_rungs(self):
        if not self.editable():
            return
        text = self._clip if self.exam else QApplication.clipboard().text()      # สอบ: วางได้เฉพาะที่คัดลอกในด่านนี้
        at = self.canvas.rung + (0 if is_blank(self.doc.rungs[self.canvas.rung]) else 1)
        try:
            n = self.doc.paste_text(at, text)
        except LadderError as e:
            self.message.emit(tr("✖ วางไม่ได้: {0}", e))
            return
        self.after_edit()
        self.canvas.select(self.canvas.first_uid(at), at)
        self.canvas.rung_to = at + n - 1

    def cut_rungs(self):
        if self.editable():
            self.copy_rungs()
            self.delete(rung=True)

    # ---------- คีย์ ----------
    def wants_key(self, e) -> bool:
        k, m = e.key(), e.modifiers()
        if m & Qt.ControlModifier:
            return self._letter(e) in tuple("ZYCXV") or k in (Qt.Key_Delete, Qt.Key_F5, Qt.Key_F6)
        return k in (Qt.Key_F4, Qt.Key_F5, Qt.Key_F6, Qt.Key_F7, Qt.Key_F8, Qt.Key_Delete, Qt.Key_Insert, Qt.Key_Space)

    @staticmethod
    def _letter(e) -> str:
        for k in (e.nativeVirtualKey(), int(e.key())):       # แป้นไทย: ใช้รหัสปุ่มจริง
            if 0x41 <= k <= 0x5A:
                return chr(k)
        return ""

    def handle_key(self, e) -> bool:
        k, m = e.key(), e.modifiers()
        ctrl, shift, alt = bool(m & Qt.ControlModifier), bool(m & Qt.ShiftModifier), bool(m & Qt.AltModifier)
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if k in arrows and not ctrl:
            if alt and arrows[k][1]:
                self.move_rung(arrows[k][1])
            else:
                self.canvas.go(*arrows[k], extend=shift)
            return True
        if ctrl:
            fn = {Qt.Key_Delete: lambda: self.delete(rung=True), Qt.Key_F5: lambda: self.add_contact("", before=True),
                  Qt.Key_F6: lambda: self.add_contact("I", before=True),
                  Qt.Key_Home: lambda: self.canvas.select(self.canvas.first_uid(0), 0),
                  Qt.Key_End: lambda: self.canvas.select(0, len(self.doc.rungs) - 1)}.get(k)
            fn = fn or {"Z": lambda: self.undo(shift), "Y": self.redo, "C": self.copy_rungs, "V": self.paste_rungs,
                        "X": self.cut_rungs}.get(self._letter(e))
            if fn:
                fn()
            return bool(fn)
        fn = {Qt.Key_F4: self.send_requested.emit, Qt.Key_F5: lambda: self.add_contact("", parallel=shift),
              Qt.Key_F6: lambda: self.add_contact("I", parallel=shift), Qt.Key_F7: lambda: self.add_coil(branch=shift),
              Qt.Key_F8: lambda: self.add_coil(func=True), Qt.Key_Return: self.edit_current, Qt.Key_Enter: self.edit_current,
              Qt.Key_F2: self.edit_current, Qt.Key_Delete: self.delete, Qt.Key_Insert: lambda: self.insert_rung(shift),
              Qt.Key_Space: self.toggle}.get(k)
        if fn:
            fn()
            return True
        t = e.text()
        if t == ";":
            self.edit_comment()
            return True
        if t and (t.isalnum() and t.isascii() or t in "/=<>+-*"):
            self.typed(t)
            return True
        if t and not t.isascii():
            self.message.emit(tr("พิมพ์เป็นภาษาอังกฤษ เช่น X0, ANI X1, OUT T0 K30 (กด ~ สลับแป้น)"))
            return True
        return False

    def shutdown(self):
        self._mon.stop()
        self.canvas.close_editor()
        self.flush()
