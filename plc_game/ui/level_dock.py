"""แผงด่าน: โจทย์ + ตรวจคำตอบ (black-box) + ผลรายข้อ + AI วิเคราะห์."""
from __future__ import annotations

from ..i18n import tr

import time
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ..ai import Finding, analyze, analyze_live
from .. import ladder
from ..ladder.model import Ladder
from ..ladder.replay import watch_addresses
from .. import classroom
from ..levels import FaultHunt, LevelRunner, load_all, rooms, scores
from ..ai import learn, spec
from . import state, theme
from .learn_worker import LearnWorker

STAR = "★"
AI_LOCKED_HTML = tr("<p style='color:#FFD43B'>🔒 โหมดสอบ: ปิด AI วิเคราะห์ — ดูผลรายข้อด้านบนได้อย่างเดียว</p>")
LEVEL_HTML = {"error": "#FF8787", "warn": "#FFD43B", "info": "#74C0FC", "ok": "#69DB7C"}


def stars_text(n: int) -> str:
    return STAR * n + "☆" * (3 - n)


def findings_html(findings, link=False) -> str:
    out = []
    for f in findings:
        col = LEVEL_HTML.get(f.level, theme.TEXT)
        items = "".join(f"<li>{_esc(s)}</li>" for s in f.lines)
        head = f"<b style='color:{col}'>{_esc(f.title)}</b>"
        if link and f.step is not None:
            head = f"<a href='step:{f.step}' style='color:{col}'>{head}</a>"
        out.append(f"<p style='margin:6px 0 2px 0'>{head}</p>"
                   + (f"<ul style='margin:0 0 0 -18px'>{items}</ul>" if items else ""))
    return "".join(out)


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _LadderWorker(QThread):
    """จำลอง ladder ซ้ำใน thread แยก (ไม่แตะ widget)."""
    done = Signal(object, list)       # worker, [Finding]

    def __init__(self, prog, level, runner, devices, xy_base, parent=None):
        super().__init__(parent)
        self.args = (prog, level, runner, devices, xy_base)
        self.cancelled = False

    def run(self):
        try:
            out = ladder.diagnose(*self.args, cancel=lambda: self.cancelled)
        except Exception as e:  # noqa: BLE001 — ladder แปลก ๆ ต้องไม่ทำให้โปรแกรมล้ม ผล I/O ยังใช้ได้
            out = [Finding(tr("วิเคราะห์ ladder ไม่สำเร็จ: {0}", e), [], "warn", kind="ladder")]
        self.done.emit(self, out)


class LevelPanel(QWidget):
    message = Signal(str)
    start_requested = Signal()
    stop_requested = Signal()
    finished = Signal()
    step_requested = Signal(int)             # คลิกหัวข้อ ladder → ไปที่ rung ในแท็บ Ladder
    ladder_changed = Signal()                # เลือก/ยกเลิกไฟล์ CSV → ชุด address ที่ต้องอ่านเปลี่ยน
    aborted = Signal(object)                 # LevelRunner ที่ถูกยกเลิก (การเชื่อมต่อหลุด ฯลฯ) — ไม่มีคะแนน
    jump_requested = Signal(float, float)    # คลิกผลตรวจ → ไปช่วงเวลานั้นบนกราฟ

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.levels = []
        self.level = None
        self.runner: LevelRunner | None = None
        self.last_runner: LevelRunner | None = None
        self.hunt: FaultHunt | None = None          # ด่านหาจุดเสียที่กำลังเล่น
        self.last_hunt: FaultHunt | None = None
        self.findings = []
        self.student = scores.GUEST
        self.plc = "none"                # PLC ที่เชื่อมอยู่ (mock / soft / slmp) — จดไว้กับคะแนน
        self._ladder_worker = None
        self._old_workers = []           # ที่สั่งยกเลิกแล้วแต่ thread ยังไม่จบ
        self.ladder_path: Path | None = None
        self.program = None              # ladder.Program ที่อ่านล่าสุด
        self.builtin_on = False          # ใช้ PLC ในตัว: ladder มาจากแท็บ Ladder ไม่ใช่ไฟล์ CSV
        self.builtin = None              # Program ที่อยู่ใน PLC ในตัว
        self._checked = None             # Program จากแท็บ Ladder ตอนเริ่มตรวจครั้งล่าสุด
        self._ladder_stamp = None
        self.ladder_error = ""
        self.coach = learn.Coach()
        self._learner = None
        self.ai_enabled = True           # โหมดสอบปิด AI วิเคราะห์

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.lbl_title = QLabel(tr("ยังไม่ได้เปิดด่าน — คลิก 1 เลือกด่าน ที่แถบขั้นตอนด้านบน"))
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-size:11pt; font-weight:bold;")
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(f"color:{theme.TEXT_DIM};")
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_desc)
        row = QHBoxLayout()
        self.btn_check = QPushButton(tr("▶  ตรวจคำตอบ"))
        self.btn_check.setObjectName("Primary")
        self.btn_check.setMinimumHeight(34)
        self.btn_check.clicked.connect(self.start_requested)
        self.btn_stop = QPushButton(tr("⏹  หยุด"))
        self.btn_stop.clicked.connect(self.stop_requested)
        self.lbl_stars = QLabel()
        self.lbl_stars.setStyleSheet("font-size:16pt; color:#FFD43B;")
        row.addWidget(self.btn_check, 1)
        row.addWidget(self.btn_stop)
        row.addWidget(self.lbl_stars)
        lay.addLayout(row)
        self.ladder_row = QWidget()
        lr = QHBoxLayout(self.ladder_row)
        lr.setContentsMargins(0, 0, 0, 0)
        self.btn_ladder = QPushButton(tr("📄 เลือก CSV ladder"))
        self.btn_ladder.setToolTip(tr("ไม่บังคับ — ช่วยให้ AI ชี้ step ที่น่าจะผิด (ไม่มีผลต่อคะแนน)\nGX Works3: เปิด ladder ที่ Convert แล้ว → Edit → Export to File… → Yes → Save"))
        self.btn_ladder.clicked.connect(lambda: self.choose_ladder())
        self.lbl_ladder = QLabel()
        self.lbl_ladder.setWordWrap(True)
        self.btn_ladder_clear = QPushButton("✕")
        self.btn_ladder_clear.setFixedWidth(30)
        self.btn_ladder_clear.setToolTip(tr("เลิกใช้ไฟล์นี้"))
        self.btn_ladder_clear.clicked.connect(lambda: self.set_ladder(None))
        lr.addWidget(self.btn_ladder)
        lr.addWidget(self.lbl_ladder, 1)
        lr.addWidget(self.btn_ladder_clear)
        lay.addWidget(self.ladder_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)

        split = QSplitter(Qt.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setWordWrap(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        split.addWidget(self.tree)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 4, 0, 0)
        hr = QHBoxLayout()
        t = QLabel(tr("🤖 AI วิเคราะห์"))
        t.setStyleSheet("font-weight:bold;")
        hr.addWidget(t)
        hr.addStretch(1)
        bl.addLayout(hr)
        self.ai = QTextBrowser()
        self.ai.setOpenLinks(False)
        self.ai.anchorClicked.connect(self._on_anchor)
        bl.addWidget(self.ai, 1)
        split.addWidget(box)
        split.setSizes([300, 260])
        lay.addWidget(split, 1)
        self.reload()
        self._sync_buttons()

    # ---------- รายการด่าน ----------
    folder = None                       # None = levels/ ของโปรเจกต์ (test ตั้งเป็นโฟลเดอร์ชั่วคราว)

    xy_base = 8
    room = None                         # rooms.Room ที่เลือก (None = ด่านมาตรฐาน)

    @property
    def root(self) -> Path:
        from ..levels.engine import LEVEL_DIR
        return Path(self.folder or LEVEL_DIR)

    def set_room(self, key: str) -> bool:
        """เลือกห้องด่าน ("" = ด่านมาตรฐาน) — คืน False ถ้าห้องไม่อยู่แล้ว (กลับไปด่านมาตรฐาน)."""
        self.room = rooms.get(key, self.root) if key else None
        self.reload(self.xy_base)
        return bool(self.room) or not key

    def reload(self, xy_base: int = 8):
        self.xy_base = xy_base
        if self.room is not None:
            self.room = rooms.get(self.room.key, self.root)      # ถูกลบ/เปลี่ยนชื่อในตัวแก้ไข
        if self.room is not None:
            self.levels, bad = rooms.load_levels(self.room, xy_base)
            for e in bad:
                self.message.emit(tr("✖ โหลดด่านไม่ได้: {0}", e))
            return self.levels
        try:
            self.levels = load_all(self.root, xy_base=xy_base)
        except (OSError, ValueError) as e:
            self.levels = []
            self.message.emit(tr("✖ โหลดด่านไม่ได้: {0}", e))
        return self.levels

    def best(self) -> dict[str, int]:
        return scores.best_stars(self.student)

    @property
    def busy(self) -> bool:
        """กำลังตรวจคำตอบ หรือกำลังหาจุดเสียอยู่."""
        return self.runner is not None or self.hunt is not None

    # ---------- ไฟล์ ladder (CSV) ----------
    def _ladder_key(self) -> str:
        return f"{self.student}|{self.level.id}"          # เครื่องเดียวหลายคน: จำแยกคนและด่าน

    def restore_ladder(self):
        """ใช้ไฟล์ที่เคยเลือกไว้ของนักเรียนคนนี้ในด่านนี้."""
        self._cancel_ladder()
        saved = state.load().get("ladder_csv")
        p = saved.get(self._ladder_key()) if isinstance(saved, dict) and self.level else None
        self.ladder_path = Path(p) if isinstance(p, str) and p else None
        self._ladder_stamp = None
        self._read_ladder()

    def choose_ladder(self):
        if not self._ladder_allowed():
            return
        start = str(self.ladder_path.parent) if self.ladder_path else ""
        p, _ = QFileDialog.getOpenFileName(self, tr("เลือกไฟล์ CSV ที่ Export จาก GX Works3"), start, "CSV (*.csv)")
        if p:
            self.set_ladder(p)

    def _ladder_allowed(self) -> bool:
        return bool(self.ai_enabled and self.level and not self.level.is_fault_hunt and not self.busy
                    and not self.builtin_on)

    def set_ladder(self, path):
        if not self._ladder_allowed():
            return
        self._cancel_ladder()
        self.ladder_path = Path(path) if path else None
        self._ladder_stamp = None
        saved = state.load().get("ladder_csv")
        saved = dict(saved) if isinstance(saved, dict) else {}
        if self.ladder_path:
            saved[self._ladder_key()] = str(self.ladder_path)
        else:
            saved.pop(self._ladder_key(), None)
        state.update(ladder_csv=saved)
        self._read_ladder()
        if self.program:
            self.message.emit(tr("📄 อ่าน ladder {0} แล้ว ({1} คำสั่ง)", self.ladder_path.name, len(self.program.instrs)))
        elif self.ladder_error:
            self.message.emit(tr("✖ อ่าน ladder ไม่ได้: {0}", self.ladder_error))
        if self.last_runner is not None:
            self.analyze_result()
        self._sync_buttons()
        self.ladder_changed.emit()

    def _read_ladder(self):
        """อ่านไฟล์ใหม่ถ้าไฟล์เปลี่ยน (เรียกก่อนตรวจและก่อนวิเคราะห์)."""
        p = self.ladder_path
        if self.builtin_on:
            self.program = self.builtin if self.ai_enabled else None
            self.ladder_error, self._ladder_stamp = "", None
        elif p is None or not self.ai_enabled:
            self.program, self.ladder_error, self._ladder_stamp = None, "", None
        else:
            try:
                st = p.stat()
                stamp = (st.st_mtime_ns, st.st_size)
            except OSError:
                stamp = ()
            if stamp != self._ladder_stamp:
                self._ladder_stamp = stamp
                self.program, self.ladder_error = None, ""
                try:
                    self.program = ladder.load_csv(p)
                except ladder.LadderError as e:
                    self.ladder_error = str(e)
        self._show_ladder()

    def set_builtin(self, on: bool, prog=None):
        """เปิด/ปิดการใช้ ladder จากแท็บ Ladder (PLC ในตัว)."""
        self.builtin_on, self.builtin = on, prog if on else None
        self._ladder_stamp = None
        self._read_ladder()
        self._sync_buttons()

    def _show_ladder(self):
        p = self.ladder_path
        if self.builtin_on:
            text, col, tip = tr("ใช้ ladder ในแท็บ Ladder"), "#69DB7C", ""
        elif p is None:
            text, col, tip = tr("ไม่บังคับ: ให้ AI ชี้ step ที่น่าจะผิด"), theme.TEXT_DIM, ""
        elif self.ladder_error:
            text, col, tip = tr("⚠ {0}", self.ladder_error), "#FFD43B", str(p)
        elif self.program:
            when = time.strftime("%d/%m %H:%M", time.localtime(self._ladder_stamp[0] / 1e9))
            text, col, tip = tr("{0} · บันทึก {1}", p.name if len(p.name) <= 28 else p.name[:25] + "…", when), "#69DB7C", str(p)
        else:
            text, col, tip = "", theme.TEXT_DIM, ""
        self.lbl_ladder.setText(text)
        self.lbl_ladder.setStyleSheet(f"color:{col};")
        self.lbl_ladder.setToolTip(tip)

    def ladder_watch(self) -> list[str]:
        """address ใน ladder ที่ควรอ่านเพิ่ม (ให้การจำลองมีค่าจริงเทียบ)."""
        if not (self.program and self.ai_enabled and self.level) or self.level.is_fault_hunt:
            return []
        return watch_addresses(Ladder(self.program, self.xy_base))

    def _cancel_ladder(self):
        w, self._ladder_worker = self._ladder_worker, None
        if w is not None:
            w.cancelled = True
            self._old_workers.append(w)

    def _worker_ended(self):
        for w in [w for w in self._old_workers if w.isFinished()]:
            self._old_workers.remove(w)
            w.deleteLater()

    def shutdown(self):
        """ปิดโปรแกรม: รอ thread วิเคราะห์ให้จบก่อน widget ถูกลบ."""
        self._cancel_ladder()
        self._stop_learning()
        for w in list(self._old_workers):
            w.wait(8000)

    def analyze_result(self, score_key=None):
        """ผล I/O ก่อน แล้วค่อยเติมผล ladder เมื่อจำลองเสร็จ (ไม่มีผลต่อคะแนน)."""
        self._cancel_ladder()
        if not (self.ai_enabled and self.level and self.last_runner):
            return
        self._read_ladder()
        prog = self._checked or (None if self.builtin_on else self.program)   # ladder ที่ใช้ตรวจจริง แม้แก้ต่อไปแล้ว
        self.findings = analyze(self.level, self.last_runner, self._devices(), self._learned(score_key is not None))
        html = findings_html(self.findings)
        if self.ladder_path is not None and prog is None and not self.builtin_on:
            html += tr("<p style='color:#FFD43B'>📄 อ่าน ladder ไม่ได้: {0}</p>", _esc(self.ladder_error))
        if prog is not None:
            html += tr("<p style='color:#74C0FC'>📄 กำลังวิเคราะห์ ladder…</p>")
            w = self._ladder_worker = _LadderWorker(prog, self.level, self.last_runner, self._devices(), self.xy_base, self)
            w.score_key = score_key                  # เฉพาะวิเคราะห์ต่อจากการตรวจ (เลือก CSV ทีหลังอาจไม่ใช่ตัวที่ตรวจ)
            w.done.connect(self._ladder_done)
            w.finished.connect(self._worker_ended)      # bound method → รันใน GUI thread
            w.start()
        self.ai.setHtml(html)
        self._sync_buttons()

    def learn_now(self):
        """เรียนรู้จากเงื่อนไขของด่านที่เปิดในเบื้องหลัง (ไม่ทำตอนสอบและตอนกำลังตรวจ)."""
        self._stop_learning()
        if not self.ai_enabled or self.level is None or self.level.is_fault_hunt or self.busy:
            return
        try:
            p = spec.analyze_spec(self.level, self._devices(), self.xy_base)
        except Exception as e:  # noqa: BLE001 — ส่วนเสริม
            self.message.emit(tr("AI เรียนรู้จากเงื่อนไขไม่สำเร็จ: {0}", e))
            return
        if p.physics or self.coach.mem.model(self.level.id, p.hash) is not None:
            return
        w = self._learner = LearnWorker(self.level, p, self.xy_base, self)
        w.done.connect(self._learn_done)
        w.finished.connect(self._worker_ended)
        w.start()

    def _learn_done(self, w, m):
        if w is self._learner and m.status in ("ok", "unknown") and self.ai_enabled:
            self.coach.mem.store(w.level.id, m)
        self._stop_learning()

    def _stop_learning(self):
        w, self._learner = self._learner, None
        if w is not None:
            w.cancelled = True
            self._old_workers.append(w)

    def _learned(self, fresh: bool):
        """สาเหตุที่คาดจากการเรียนรู้เงื่อนไขของด่าน (fresh = เพิ่งตรวจ → จำผลไปปรับความแม่น)."""
        if not self.ai_enabled or self.level.is_fault_hunt:
            return []
        try:
            p = spec.analyze_spec(self.level, self._devices(), self.xy_base)
            mem = self.coach.mem
            self.learn_now()                      # ยังไม่เคยเรียน (เปลี่ยนผัง/เงื่อนไข) → เรียนไว้ใช้ครั้งถัดไป
            if any(it.fault for it in self.view.fault_items()):
                return []                         # ครูใส่ของเสียไว้ อาการไม่ได้มาจาก ladder อย่างเดียว
            if fresh:
                return self.coach.after_check(self.student, self.level, self.last_runner, p)
            return learn.findings(learn.match(self.level, self.last_runner, mem.model(self.level.id, p.hash), mem), p.names)
        except Exception as e:  # noqa: BLE001 — ส่วนเสริม ต้องไม่ทำให้ผลตรวจหาย
            self.message.emit(tr("AI เรียนรู้จากเงื่อนไขไม่สำเร็จ: {0}", e))
            return []

    def _ladder_done(self, w, found):
        if w is not self._ladder_worker:             # ถูกยกเลิก (เปลี่ยนด่าน/ตรวจใหม่/เข้าโหมดสอบ)
            return
        self._ladder_worker = None
        self._old_workers.append(w)
        if self._checked is not None:
            html = tr("<hr><p><b style='color:#74C0FC'>📄 จาก ladder — อธิบายเพิ่ม ไม่มีผลต่อคะแนน (คลิกหัวข้อเพื่อไปที่ rung)</b></p>")
        else:
            html = tr("<hr><p><b style='color:#74C0FC'>📄 จาก ladder (CSV) — อธิบายเพิ่ม ไม่มีผลต่อคะแนน</b></p>")
        html += findings_html(found, self._checked is not None) if found else tr("<p>ไม่พบจุดที่น่าสงสัยใน ladder</p>")
        html += "<hr>" + findings_html(self.findings)      # ladder ชี้ step ได้ จึงอยู่บนสุด
        notes = [f.title + (" — " + f.lines[-2] if len(f.lines) >= 2 and f.level == "error" else "") for f in found if f.level in ("error", "warn")]
        if notes and w.score_key:
            lid, student, stamp = w.score_key
            scores.note_ladder(lid, student, notes, stamp)
        self.findings = self.findings + found
        self.ai.setHtml(html)
        self._sync_buttons()

    def open_level(self, level):
        self.level = level
        self._checked = None
        self.last_runner = None
        self.hunt = self.last_hunt = None
        b = self.best().get(level.id, 0)
        self.lbl_title.setText(level.title)
        self.lbl_desc.setText(level.desc)
        self.lbl_stars.setText(stars_text(b))
        self.lbl_stars.setToolTip(tr("ดีที่สุด {0} ดาว", b)
                                  + self._best_tip(scores.load().get(self.student, {}).get(level.id, {})))
        self.tree.clear()
        self._fill_tree(None)
        self.progress.setValue(0)
        if level.is_fault_hunt:
            self.btn_check.setText(tr("▶  เริ่มหาจุดเสีย"))
            self.progress.setRange(0, level.faults.guesses)
            self.progress.setFormat(tr("ยังไม่ได้เริ่ม · ทายได้ {0} ครั้ง", level.faults.guesses))
            self.ai.setHtml(tr("<span style='color:{0}'>โหลดโปรแกรมที่ทำงานถูกแล้วลง PLC → เชื่อมต่อ → กด ▶ เริ่มหาจุดเสีย<br>กดปุ่มบนผัง ดูมอเตอร์ ไฟ และตาราง I/O แล้ว<b>คลิกขวาอุปกรณ์ที่คิดว่าเสีย</b> → เลือกอาการ</span>", theme.TEXT_DIM))
        else:
            self.btn_check.setText(tr("▶  ตรวจคำตอบ"))
            self.progress.setRange(0, max(1, level.checks))
            self.progress.setFormat(tr("ยังไม่ได้ตรวจ · {0} ข้อ", level.checks))
            self.ai.setHtml(tr("<span style='color:{0}'>เขียน ladder ในแท็บ Ladder (F4 ส่งลง PLC ในตัว) หรือใน GX Works3 (Write ลง PLC) → กด ▶ ตรวจคำตอบ<br>ตัวตรวจจะกดปุ่มบนผังให้เอง ห้ามกดอุปกรณ์ระหว่างตรวจ</span>", theme.TEXT_DIM)
                            + ("" if self.ai_enabled else AI_LOCKED_HTML))
        self.restore_ladder()
        self._sync_buttons()
        QTimer.singleShot(600, self, lambda: self._learner or self.learn_now())       # หลังผังของด่านโหลดเสร็จ

    def set_plc(self, kind: str):
        self.plc = kind
        if self.hunt is not None and kind != "none":     # เริ่มหาก่อนเชื่อมต่อได้ → จดตัวที่ใช้ดูอาการ
            self.hunt.plc = kind

    def _best_tip(self, st: dict) -> str:
        t = classroom.plc_text(st)
        return "\n" + tr("ตรวจกับ: {0}", t) if t else ""

    # ---------- หาจุดเสีย ----------
    def start_hunt(self, hunt: FaultHunt):
        self.hunt = hunt
        hunt.plc = self.plc
        self.last_hunt = None
        self._fill_hunt_tree(hunt)
        self.progress.setRange(0, hunt.guesses_allowed)
        self.progress.setValue(0)
        self.progress.setFormat(tr("กำลังหาจุดเสีย · ทายได้อีก {0} ครั้ง", hunt.left))
        self.ai.setHtml(tr("<span style='color:{0}'>มีอุปกรณ์เสีย 1 จุด (ซ่อนอยู่)<br>กดปุ่ม Start / Stop สังเกตว่าอะไรไม่เป็นไปตามที่ควร แล้วคลิกขวาอุปกรณ์นั้น</span>", theme.TEXT_DIM))
        self._sync_buttons()

    def guess(self, label: str, code: str):
        h = self.hunt
        if h is None:
            return None
        r = h.guess(label, code)
        self._fill_hunt_tree(h)
        self.progress.setValue(len(h.results))
        self.progress.setFormat(tr("ทายได้อีก {0} ครั้ง", h.left))
        self.message.emit(("✔ " if r.passed else "✖ ") + f"{r.msg} → {r.detail}")
        if h.done:
            self._finish_hunt()
        return r

    def _finish_hunt(self):
        h = self.hunt
        self.hunt = None
        self.last_hunt = h
        self.prev_best = self.best().get(self.level.id, 0)
        st = scores.record(self.level.id, h, self.student, plc=getattr(h, "plc", ""))
        self.lbl_stars.setText(stars_text(h.stars))
        self.lbl_stars.setToolTip(tr("ครั้งนี้ {0} ดาว · ดีที่สุด {1} ดาว · เล่นแล้ว {2} ครั้ง", h.stars, st['best_stars'], st['attempts'])
                                  + self._best_tip(st))
        self.progress.setFormat((tr("เจอจุดเสีย") if h.found else tr("ไม่เจอจุดเสีย"))
                                + tr(" · ทาย {0} ครั้ง · {1}", len(h.results), stars_text(h.stars)))
        head = (tr("<p><b style='color:#69DB7C'>✔ เจอแล้ว!</b></p>") if h.found
                else tr("<p><b style='color:#FF8787'>✖ ทายครบ {0} ครั้งแล้ว — เฉลย</b></p>", h.guesses_allowed))
        self.ai.setHtml(head + tr("<p>จุดเสีย: <b>{0}</b> (ป้าย ⚡ บนผัง)</p><p style='color:{1}'>สังเกตอย่างไร: {2}</p>", _esc(h.answer_text()), theme.TEXT_DIM, _esc(h.hint())))
        self.message.emit(f"🏁 {self.level.title}: " + (tr("เจอจุดเสีย") if h.found else tr("ไม่เจอ"))
                          + f" — {h.answer_text()} → {stars_text(h.stars)}")
        self._sync_buttons()
        self.finished.emit()

    def _fill_hunt_tree(self, h: FaultHunt):
        self.tree.clear()
        top = QTreeWidgetItem([tr("หาจุดเสีย · ทายได้ {0} ครั้ง", h.guesses_allowed)])
        f = QFont()
        f.setBold(True)
        top.setFont(0, f)
        for r in h.results:
            it = QTreeWidgetItem([("✔  " if r.passed else "✖  ") + r.msg])
            it.setForeground(0, QBrush(QColor("#69DB7C" if r.passed else "#FF8787")))
            sub = QTreeWidgetItem([r.detail])
            sub.setForeground(0, QBrush(QColor(theme.TEXT_DIM)))
            it.addChild(sub)
            top.addChild(it)
        for _ in range(h.left if not h.done else 0):
            it = QTreeWidgetItem([tr("○  ยังไม่ได้ทาย")])
            it.setForeground(0, QBrush(QColor(theme.TEXT_DIM)))
            top.addChild(it)
        self.tree.addTopLevelItem(top)
        self.tree.expandAll()

    # ---------- ตรวจ ----------
    def start(self, write, action):
        if not self.level:
            return False
        self._cancel_ladder()
        self._stop_learning()               # ไม่แย่ง CPU กับการจับเวลาตอนตรวจ
        self._checked = self.builtin if self.builtin_on and self.ai_enabled else None
        self.runner = LevelRunner(self.level, write, action)
        self.runner.plc = self.plc
        self.tree.clear()
        self._fill_tree(None)
        self.progress.setValue(0)
        self.progress.setFormat(tr("กำลังตรวจ… %v/%m"))
        self.ai.setHtml(tr("<span style='color:{0}'>กำลังตรวจ…</span>", theme.TEXT_DIM))
        self._sync_buttons()
        return True

    def feed(self, snap, t) -> bool:
        r = self.runner
        if r is None:
            return False
        n = len(r.results)
        done = r.feed(snap, t)
        if len(r.results) != n:
            self._fill_tree(r)
        self.progress.setValue(len(r.results))
        if not done:
            self.progress.setFormat(tr("กำลังตรวจ: {0}  (%v/%m)", r.current_case))
        if done:
            self._aborted() if r.aborted else self._finish()
        return done

    def abort(self, reason: str):
        """การเชื่อมต่อหลุดระหว่างตรวจ → ยกเลิก ไม่บันทึกคะแนน."""
        if self.runner is not None:
            self.runner.abort(reason)
            self._aborted()

    def _aborted(self):
        r = self.runner
        self.runner = None
        self.progress.setFormat(tr("ยกเลิกการตรวจ (ไม่บันทึกคะแนน)"))
        self.ai.setHtml(tr("<p><b style='color:#FFD43B'>⚠ ยกเลิกการตรวจ: {0}</b></p><p>ผลที่ได้เชื่อถือไม่ได้จึงไม่บันทึกคะแนน — ตรวจว่า ONLINE และ PLC อยู่ในโหมด RUN แล้วตรวจใหม่</p>", _esc(r.aborted)))
        self.message.emit(tr("⚠ ยกเลิกการตรวจ: {0} (ไม่บันทึกคะแนน)", r.aborted))
        self._sync_buttons()
        self.aborted.emit(r)

    def stop(self):
        if self.hunt:
            self.hunt = None
            self.progress.setFormat(tr("หยุดหาจุดเสียแล้ว (ไม่บันทึกคะแนน)"))
            self.message.emit(tr("⏹ หยุดหาจุดเสียกลางคัน (ไม่บันทึกคะแนน)"))
        if self.runner:
            self.runner.stop()
            self.runner = None
            self.progress.setFormat(tr("หยุดตรวจแล้ว"))
            self.message.emit(tr("⏹ หยุดตรวจกลางคัน (ไม่บันทึกคะแนน)"))
        self._sync_buttons()

    def _finish(self):
        r = self.runner
        self.runner = None
        self.last_runner = r
        self.prev_best = self.best().get(self.level.id, 0)
        st = scores.record(self.level.id, r, self.student, plc=getattr(r, "plc", ""))
        self.lbl_stars.setText(stars_text(r.stars))
        self.lbl_stars.setToolTip(tr("ครั้งนี้ {0} ดาว · ดีที่สุด {1} ดาว · ตรวจแล้ว {2} ครั้ง", r.stars, st['best_stars'], st['attempts'])
                                  + self._best_tip(st))
        self.progress.setFormat(tr("ผ่าน {0}/{1} ข้อ · {2}", r.passed, r.total, stars_text(r.stars)))
        self._fill_tree(r)
        if self.ai_enabled:
            self.analyze_result((self.level.id, self.student, f"{st['last_time']}#{st['attempts']}"))
        else:
            self.findings = []
            self.ai.setHtml(AI_LOCKED_HTML)
        self.message.emit(tr("🏁 {0}: ผ่าน {1}/{2} ข้อ → {3}", self.level.title, r.passed, r.total, stars_text(r.stars)))
        self._sync_buttons()
        self.finished.emit()

    def _devices(self):
        return [it.spec for it in self.view.items_by_id.values()]

    def _fill_tree(self, r):
        self.tree.clear()
        if not self.level or self.level.is_fault_hunt:
            return
        res = {}
        for x in (r.results if r else []):
            res[(x.case_index, x.step_index)] = x
        bold = QFont()
        bold.setBold(True)
        for ci, case in enumerate(self.level.cases):
            top = QTreeWidgetItem([tr("ข้อ {0}: {1}", ci + 1, case.name)])
            top.setFont(0, bold)
            ok_all, any_res = True, False
            for si, step in enumerate(case.steps):
                if not step.is_check:
                    continue
                x = res.get((ci, si))
                if x is None:
                    mark, col, tip = "○", theme.TEXT_DIM, ""
                    ok_all = False
                else:
                    any_res = True
                    ok_all &= x.passed
                    mark = "✔" if x.passed else ("–" if x.skipped else "✖")
                    col = "#69DB7C" if x.passed else ("#868E96" if x.skipped else "#FF8787")
                    tip = x.detail
                it = QTreeWidgetItem([f"{mark}  {step.describe()}"])
                it.setForeground(0, QBrush(QColor(col)))
                span = (x.t_start, x.t_end) if (x is not None and not x.skipped) else None
                if span:
                    it.setData(0, Qt.UserRole, span)
                if tip:
                    it.setToolTip(0, tip + (tr("\nคลิกเพื่อดูช่วง {0:.1f}–{1:.1f} s บนกราฟ", span[0], span[1]) if span else ""))
                    if x is not None and not x.passed and not x.skipped:
                        sub = QTreeWidgetItem([tip])
                        sub.setForeground(0, QBrush(QColor(theme.TEXT_DIM)))
                        sub.setData(0, Qt.UserRole, span)
                        it.addChild(sub)
                elif span:
                    it.setToolTip(0, tr("คลิกเพื่อดูช่วง {0:.1f}–{1:.1f} s บนกราฟ", span[0], span[1]))
                top.addChild(it)
            if any_res:
                top.setForeground(0, QBrush(QColor("#69DB7C" if ok_all else "#FF8787")))
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()

    def _on_anchor(self, url):
        s = url.toString()
        if s.startswith("step:") and s[5:].isdigit():
            self.step_requested.emit(int(s[5:]))

    def _on_item_clicked(self, item, _col=0):
        span = item.data(0, Qt.UserRole)
        if span and self.runner is None:
            self.jump_requested.emit(float(span[0]), float(span[1]))

    def _sync_buttons(self):
        running = self.busy
        self.btn_check.setEnabled(bool(self.level) and not running)
        self.btn_stop.setEnabled(running)
        self.ladder_row.setVisible(bool(self.level) and not self.level.is_fault_hunt)
        self.btn_ladder.setEnabled(self._ladder_allowed())
        self.btn_ladder_clear.setEnabled(self._ladder_allowed())
        self.btn_ladder_clear.setVisible(self.ladder_path is not None)

    def set_ai_enabled(self, on: bool):
        self.ai_enabled = on
        self._ladder_stamp = None
        self._read_ladder()
        if not on:
            self.coach.reset()
            self._stop_learning()
            self._cancel_ladder()
            self.findings = []
            self.ai.setHtml(AI_LOCKED_HTML)
        self._sync_buttons()

    # ---------- AI ----------
    def analyze_live(self, history):
        if not self.ai_enabled:
            self.ai.setHtml(AI_LOCKED_HTML)
            return []
        self._cancel_ladder()
        fs = analyze_live(history, self._devices())
        self.ai.setHtml(tr("<p><i>วิเคราะห์จากสัญญาณที่กดเล่นล่าสุด</i></p>") + findings_html(fs))
        return fs

