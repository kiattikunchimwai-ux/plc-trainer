"""จุดเริ่มโปรแกรม:  python -m plc_game.main [--backend mock|slmp] [--connect]"""
from __future__ import annotations

from .i18n import tr

import argparse
import sys
from pathlib import Path

import yaml
from PySide6.QtWidgets import QApplication

from . import paths

CONFIG_PATH = paths.config_path()


def _read_yaml(path: Path) -> dict:
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    return {}


def load_config(path: Path = CONFIG_PATH) -> dict:
    """config ของผู้ใช้ทับค่าที่มากับโปรแกรม — คีย์ที่ผู้ใช้ไม่มีหรือเว้นว่าง (เช่น update_url
    ในไฟล์ที่คัดมาจากรุ่นเก่า) ใช้ค่าของโปรแกรมรุ่นปัจจุบัน."""
    base = paths.app_root() / "plc_game" / "config.yaml"
    cfg = _read_yaml(base) if path != base else {}
    for k, v in _read_yaml(path).items():
        if v is not None and v != "":
            cfg[k] = v
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Educational PLC Simulation Game")
    ap.add_argument("--backend", choices=["mock", "soft", "slmp"])
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--connect", action="store_true", help=tr("เชื่อมต่อทันทีเมื่อเปิดโปรแกรม"))
    ap.add_argument("--demo", action="store_true", help=tr("โหมดสาธิตวิธีใช้งาน (ใช้ Mock PLC)"))
    ap.add_argument("--selftest", metavar="REPORT.json", help=argparse.SUPPRESS)   # ทดสอบ .exe: ตรวจด่าน 1 แล้วปิด
    args = ap.parse_args(argv)
    if args.selftest:
        args.backend = "mock"
    if args.demo and args.backend is None:
        args.backend = "mock"      # สาธิตด้วย PLC จำลอง เว้นแต่ระบุ --backend slmp

    cfg = load_config()
    for k in ("backend", "host", "port"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)

    from PySide6.QtCore import QTimer

    from .ui import state, theme
    from .ui.main_window import MainWindow

    paths.seed_user_dir()          # .exe ครั้งแรก: คัดลอกผังตัวอย่าง/ด่านไป %APPDATA%\PLCTrainer
    updated, kept = paths.update_user_files()     # เปลี่ยนเวอร์ชัน: ด่านที่ผู้ใช้ไม่เคยแก้ → ของใหม่
    from . import i18n
    i18n.apply_qt_locale()         # เลขอารบิกเสมอ (Windows ที่ตั้งตัวเลขไทยจะแสดง ๕๕๑๑)
    app = QApplication(sys.argv if argv is None else ["plc_game"])
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)
    icon = paths.app_root() / "assets" / "icon.png"
    if icon.exists():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icon)))
    win = MainWindow(cfg)
    win.show()
    if updated:
        win.log(tr("✔ อัปเดตด่าน/ผังเป็นรุ่นใหม่ {0} ไฟล์", len(updated)))
    if kept:
        win.log(tr("⚠ ด่าน/ผังที่แก้ไว้เองยังเป็นของเดิม ไม่ได้รับรุ่นใหม่: {0}", ", ".join(n.split("/")[-1] for n in kept)))
    if args.selftest:
        QTimer.singleShot(300, lambda: _selftest(win, Path(args.selftest)))
    elif args.demo:
        from .demo import DemoRunner
        win._demo = DemoRunner(win)
        win._demo.start()
    elif args.connect:
        win.connect_plc()
    elif not state.load().get("tutorial_done") and not win.exam:
        QTimer.singleShot(400, win.start_tutorial)     # เปิดโปรแกรมครั้งแรก → บทเรียนนำทาง (แทนหน้าเริ่มต้น)
    elif state.load().get("quickstart", True):
        QTimer.singleShot(0, win.show_quickstart)     # หน้าเริ่มต้น (ปิดได้ด้วย checkbox ในหน้านั้น)
    return app.exec()


def _selftest(win, report: Path) -> None:
    """เชื่อม Mock → ด่าน 1 → ตรวจ (ไม่มี ladder จึงไม่ผ่าน แต่ต้องบันทึกคะแนน) → ภาพหน้าจอ + รายงาน JSON → ปิด."""
    import json
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import __version__, i18n
    from .levels import scores

    info = {"version": __version__, "frozen": paths.frozen(), "lang": i18n.lang(),
            "app_root": str(paths.app_root()), "data_dir": str(paths.data_dir()),
            "levels": len(win.levelp.levels), "log": win.cmd_history.toPlainText().splitlines()[:8], "errors": []}
    t0 = time.monotonic()

    def finish():
        try:
            info["stars"] = win.levelp.last_runner.stars if win.levelp.last_runner else None
            info["score_saved"] = "01_self_hold" in scores.load().get(scores.GUEST, {})
            info["score_file"] = str(scores.SCORE_FILE)
            info["sounds"] = sorted(p.name for p in (paths.cache_dir() / "sounds").glob("*.wav"))
            win.grab().save(str(report.with_suffix(".png")))
        except Exception as e:      # noqa: BLE001 — รายงานทุกอย่าง
            info["errors"].append(repr(e))
        report.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        win.dirty = False
        win.close()
        QApplication.quit()

    def wait():
        if win.levelp.busy and time.monotonic() - t0 < 60:
            QTimer.singleShot(100, wait)
        else:
            QTimer.singleShot(500, finish)

    def run_check(ok):
        if not ok:
            return
        try:
            win.cmd_input.setText("CHECK")
            win._on_command()
            QTimer.singleShot(500, wait)
        except Exception as e:      # noqa: BLE001
            info["errors"].append(repr(e))
            finish()

    try:
        win.cmd_input.setText("LEVEL 1")
        win._on_command()
        win.connect_plc()
        win.poller.connected.connect(lambda ok: QTimer.singleShot(300, lambda: run_check(ok)))
        def give_up():
            if not win.levelp.busy and win.levelp.last_runner is None:
                info["errors"].append("timeout: PLC not connected / check not started")
                finish()
        QTimer.singleShot(20000, give_up)
    except Exception as e:          # noqa: BLE001
        info["errors"].append(repr(e))
        finish()


if __name__ == "__main__":
    sys.exit(main())
