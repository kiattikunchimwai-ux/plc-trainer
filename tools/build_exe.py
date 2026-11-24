"""สร้างโปรแกรม Windows (.exe แบบโฟลเดอร์) + ไฟล์ .zip พร้อมแจก.

รัน:  .venv\\Scripts\\pip install -r requirements-build.txt
      .venv\\Scripts\\python.exe tools\\build_exe.py            → dist\\PLCTrainer\\PLCTrainer.exe + dist\\PLCTrainer-<ver>-win64.zip
      .venv\\Scripts\\python.exe tools\\build_exe.py --no-zip

ใส่ไปด้วย: levels/ (ด่าน+ผัง), ผังตัวอย่างใน panels/ (เฉพาะที่ make_example_panels สร้าง + default) — ไม่เอาคะแนน/ui_state ของเครื่องนี้,
assets/icon.*, i18n/*.json, plc_game/config.yaml, plc_game/support.json, คู่มือ PDF
แบบโฟลเดอร์ (one-folder): เปิดเร็วกว่า one-file และไฟล์ Qt แยกอยู่ ตรงตามเงื่อนไข LGPL ของ Qt/PySide6
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from plc_game import __version__  # noqa: E402

NAME = "PLCTrainer"
DIST, WORK = ROOT / "dist", ROOT / "build"
EXCLUDES = ["tkinter", "pytest", "_pytest", "PyQt5", "PyQt6", "PySide2", "matplotlib", "IPython",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick3D",
            "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth"]
HIDDEN = ["pymcprotocol", "openpyxl", "qrcode", "yaml"]


def data_files() -> list[tuple[Path, str]]:
    """(ไฟล์ต้นทาง, โฟลเดอร์ปลายทางในโปรแกรม)."""
    import i18n_extract
    out = []
    for f in sorted((ROOT / "levels").glob("*")):
        if f.suffix in (".yaml", ".plcpanel"):
            out.append((f, "levels"))
    examples = {p.name for p in i18n_extract.example_panels() if p.parent.name == "panels"} | {"default.plcpanel"}
    out += [(ROOT / "panels" / n, "panels") for n in sorted(examples) if (ROOT / "panels" / n).exists()]
    out += [(f, "assets") for f in (ROOT / "assets").glob("icon.*")]
    out += [(f, "i18n") for f in (ROOT / "i18n").glob("*.json")]
    out += [(ROOT / "plc_game" / n, "plc_game") for n in ("config.yaml", "support.json", "shipped_hashes.json")]
    out += [(f, "docs") for f in (ROOT / "docs").glob("คู่มือ*.pdf")]
    return out


def build(make_zip: bool = True) -> Path:
    import PyInstaller.__main__
    args = [str(ROOT / "tools" / "launch_plctrainer.py"), "--name", NAME, "--noconfirm", "--clean", "--windowed",
            "--onedir", "--icon", str(ROOT / "assets" / "icon.ico"), "--paths", str(ROOT),
            "--distpath", str(DIST), "--workpath", str(WORK), "--specpath", str(WORK),
            "--collect-submodules", "plc_game"]
    for src, dst in data_files():
        args += ["--add-data", f"{src}{';'}{dst}"]
    for m in HIDDEN:
        args += ["--hidden-import", m]
    for m in EXCLUDES:
        args += ["--exclude-module", m]
    PyInstaller.__main__.run(args)
    app = DIST / NAME
    exe = app / f"{NAME}.exe"
    if not exe.exists():
        raise SystemExit(f"build ไม่สำเร็จ: ไม่พบ {exe}")
    (app / "README.txt").write_text(
        f"PLC Trainer v{__version__}\r\n\r\n"
        "เปิดโปรแกรม: ดับเบิลคลิก PLCTrainer.exe (ห้ามย้าย .exe ออกจากโฟลเดอร์นี้)\r\n"
        "ข้อมูลของผู้ใช้ (คะแนน/ผัง/การตั้งค่า/ด่านที่ครูแก้): %APPDATA%\\PLCTrainer\r\n"
        "เอาด่านต้นฉบับที่ลบไปกลับมา: ปิดโปรแกรม ลบไฟล์ %APPDATA%\\PLCTrainer\\seeded.json แล้วเปิดใหม่\r\n"
        "ตั้งค่าการเชื่อมต่อ: คัดลอก _internal\\plc_game\\config.yaml ไปที่ %APPDATA%\\PLCTrainer\\config.yaml แล้วแก้\r\n\r\n"
        "Run: double-click PLCTrainer.exe (keep it inside this folder)\r\n"
        "Your data: %APPDATA%\\PLCTrainer\r\n"
        "Restore deleted built-in levels: close the app, delete %APPDATA%\\PLCTrainer\\seeded.json, reopen\r\n\r\n"
        "Not affiliated with Mitsubishi Electric. GX Works3 / GX Simulator3 are trademarks of Mitsubishi Electric Corporation.\r\n",
        encoding="utf-8")
    # version.json จริงสร้างโดย tools/make_release.py (ลบตัวอย่างเก่าที่เคยวางไว้ใน dist)
    (DIST / "version.json").unlink(missing_ok=True)
    if make_zip:
        z = DIST / f"{NAME}-{__version__}-win64.zip"
        z.unlink(missing_ok=True)
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for f in sorted(app.rglob("*")):
                if f.is_file():
                    zf.write(f, Path(NAME) / f.relative_to(app))
        print(f"zip: {z} ({z.stat().st_size / 1e6:.1f} MB)")
    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    print(f"exe: {exe}  (โฟลเดอร์ {size / 1e6:.0f} MB)")
    return exe


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true")
    a = ap.parse_args()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    build(not a.no_zip)
