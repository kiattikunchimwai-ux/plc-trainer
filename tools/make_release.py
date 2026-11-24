"""เตรียมไฟล์ปล่อยโปรแกรมขึ้น GitHub Releases (ไม่ต้องมี git — อัปโหลดผ่านเว็บได้).

รันครั้งแรก (ตั้งชื่อ repo แล้วจำไว้ใน config.yaml → update_url):
    .venv\\Scripts\\python.exe tools\\make_release.py --repo <owner>/<repo>
ครั้งต่อไป (แก้ __version__ + CHANGELOG.md ก่อน):
    .venv\\Scripts\\python.exe tools\\make_release.py
ตัวเลือก: --skip-build (ใช้ dist\\ ที่ build ไว้แล้ว — ต้องมี update_url ตรงกัน), --out <โฟลเดอร์> (ค่าเริ่มต้น release\\)

ผลลัพธ์ใน release\\v<ver>\\ :
    PLCTrainer-<ver>-win64.zip · version.json · SHA256SUMS.txt · RELEASE_NOTES.md
และ release\\repo\\README.md (หน้าแรกของ repo สาธารณะที่มีแค่ไฟล์แจก)
ขั้นตอนอัปโหลด: docs\\release_guide.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from plc_game import __version__  # noqa: E402
from plc_game.update import REPO_RE, github_update_url  # noqa: E402

NAME = "PLCTrainer"
CONFIG = ROOT / "plc_game" / "config.yaml"
HASHES = ROOT / "plc_game" / "shipped_hashes.json"
CHANGELOG = ROOT / "CHANGELOG.md"
DIST = ROOT / "dist"
URL_LINE = re.compile(r'^update_url:.*$', re.M)
LATEST_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/releases/latest/download/version\.json$")


# ---------------- ส่วนที่ไม่แตะไฟล์ (ทดสอบได้) ----------------
def repo_from_url(url: str) -> str:
    m = LATEST_RE.match((url or "").strip())
    return m.group(1) if m else ""


def read_update_url(text: str) -> str:
    m = URL_LINE.search(text)
    if not m:
        return ""
    val = m.group(0).split(":", 1)[1].split("#", 1)[0].strip()
    return val.strip("'\"")


def set_update_url(text: str, url: str) -> str:
    """แทนบรรทัด update_url ใน config.yaml (คงคอมเมนต์อื่นไว้) — ไม่มีบรรทัดก็ต่อท้าย."""
    line = f'update_url: "{url}"'
    if URL_LINE.search(text):
        return URL_LINE.sub(line, text, count=1)
    return text.rstrip("\n") + "\n" + line + "\n"


def changelog_section(text: str, version: str) -> tuple[str, str, str]:
    """คืน (วันที่, ข้อความไทย, ข้อความอังกฤษ) ของ '## <version>' — ยก ValueError ถ้าไม่มี."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    m = re.search(rf"^##\s+v?{re.escape(version)}\b(.*)$", text, re.M)
    if not m:
        raise ValueError(f"CHANGELOG.md ไม่มีหัวข้อ '## {version}'")
    date_m = re.search(r"\d{4}-\d{2}-\d{2}", m.group(1))
    nxt = re.search(r"^##\s", text[m.end():], re.M)
    body = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    parts = {"th": "", "en": ""}
    for lang_m in re.finditer(r"^###\s+(th|en)\s*$(.*?)(?=^###\s|\Z)", body, re.M | re.S):
        parts[lang_m.group(1)] = lang_m.group(2).strip()
    if not parts["th"]:
        parts["th"] = body.strip()
    return (date_m.group(0) if date_m else ""), parts["th"], parts["en"]


def first_bullet(md: str) -> str:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            return line[2:].strip()[:300]
    return md.strip().splitlines()[0][:300] if md.strip() else ""


def version_json(version: str, repo: str, date: str, notes_th: str, notes_en: str,
                 zip_name: str, sha: str, size: int) -> dict:
    return {"version": version,
            "url": f"https://github.com/{repo}/releases/tag/v{version}",
            "notes": first_bullet(notes_th), "notes_en": first_bullet(notes_en),
            "date": date, "file": zip_name, "sha256": sha, "size": size}


def release_notes(version: str, repo: str, notes_th: str, notes_en: str, zip_name: str, sha: str) -> str:
    dl = f"https://github.com/{repo}/releases/download/v{version}/{zip_name}"
    return (f"## PLC Trainer v{version}\n\n"
            f"**ดาวน์โหลด / Download:** [{zip_name}]({dl}) — Windows 10/11 64-bit\n\n"
            "แตกไฟล์ zip แล้วดับเบิลคลิก `PLCTrainer.exe` · Unzip and double-click `PLCTrainer.exe`\n\n"
            f"### มีอะไรใหม่\n{notes_th}\n\n### What's new\n{notes_en or notes_th}\n\n"
            "> Windows อาจขึ้น \"Windows protected your PC\" เพราะโปรแกรมยังไม่ได้เซ็นดิจิทัล → "
            "กด *More info* → *Run anyway*  \n"
            "> Windows SmartScreen may warn because the app is not code-signed → *More info* → *Run anyway*\n\n"
            f"SHA-256 `{zip_name}`: `{sha}`\n\n"
            "_Not affiliated with Mitsubishi Electric. GX Works3 / GX Simulator3 are trademarks of "
            "Mitsubishi Electric Corporation._\n")


def repo_readme(repo: str) -> str:
    latest = f"https://github.com/{repo}/releases/latest"
    return f"""# ⚡ PLC Trainer

เกมฝึกเขียนโปรแกรม PLC สำหรับนักเรียนช่างไฟฟ้า/เมคคาทรอนิกส์ — **ใช้ฟรี ไม่มีโฆษณา**
A free game for learning PLC ladder programming — Thai / English.

## ⬇ ดาวน์โหลด / Download
**[รุ่นล่าสุด / Latest release]({latest})** → `PLCTrainer-x.y.z-win64.zip` (Windows 10/11 64-bit)

1. แตกไฟล์ zip ไว้ที่ไหนก็ได้ · Unzip anywhere
2. ดับเบิลคลิก `PLCTrainer.exe` · Double-click `PLCTrainer.exe`
3. ถ้า Windows เตือน "Windows protected your PC" กด *More info* → *Run anyway* (โปรแกรมยังไม่ได้เซ็นดิจิทัล)

เช็กเวอร์ชันใหม่ได้ในโปรแกรม: ช่วยเหลือ → ℹ เกี่ยวกับ → 🔄 เช็กเวอร์ชันใหม่
Check for updates in the app: Help → ℹ About → 🔄 Check for updates

## ✨ มีอะไรบ้าง / Features
- 14 ด่าน ตรวจคำตอบจาก**ผล I/O** — เขียน ladder แบบไหนก็ได้ · 14 levels graded by I/O behaviour, any ladder style is fine
- ต่อกับ **GX Simulator3** (GX Works3, โปรเจกต์ RCPU ผ่าน SLMP) หรือใช้ **PLC จำลองในตัว** · Works with GX Simulator3 or the built-in simulated PLC
- อุปกรณ์สมจริงกว่า 40 ชนิด ลากวางเอง · 40+ realistic drag-and-drop devices
- กราฟ timing สด, AI วิเคราะห์ข้อผิดพลาด · Live timing chart, mistake analysis
- เครื่องมือครู: โหมดสอบ, ตารางคะแนน (Excel), จำลองอุปกรณ์เสีย, ตัวแก้ไขด่าน · Teacher tools: exam mode, score table, fault injection, level editor

## ☕ สนับสนุน / Support
โปรแกรมใช้ฟรี ถ้าช่วยให้เรียน/สอนง่ายขึ้น สนับสนุนได้จากปุ่ม ☕ ในโปรแกรม
The app is free — if it helps you, use the ☕ button in the app to support development.

## 🐞 แจ้งปัญหา / Issues
แจ้งที่แท็บ [Issues](https://github.com/{repo}/issues) · Please report bugs under Issues.

---
_Not affiliated with or endorsed by Mitsubishi Electric. GX Works3, GX Simulator3, MELSEC iQ-R and FX5 are
trademarks of Mitsubishi Electric Corporation._
"""


SITE = ROOT / "site"
SITE_COMMENT = re.compile(r"<!--\s*แม่แบบเว็บ.*?-->\n?", re.S)


def render_site(text: str, repo: str, version: str, size: int) -> str:
    """แม่แบบ site/index.html → หน้าเว็บจริง (แทน __REPO__ __VERSION__ __SIZE_MB__)."""
    out = SITE_COMMENT.sub("", text, count=1)
    owner, name = repo.split("/", 1)
    out = (out.replace("__SITE__", f"https://{owner.lower()}.github.io/{name}/").replace("__REPO__", repo).replace("__VERSION__", version)
              .replace("__SIZE_MB__", f"{size / 1e6:.0f}"))
    left = re.findall(r"__[A-Z_]+__", out)
    if left:
        raise ValueError(f"site/index.html ยังมีตัวแปรที่ไม่รู้จัก: {sorted(set(left))}")
    return out


def write_site(dst: Path, repo: str, version: str, size: int, src: Path = SITE) -> None:
    """คัดเว็บไป release/repo/ (index.html + img/) — GitHub Pages เปิดจาก root ของ branch gh-pages."""
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "index.html").write_text(render_site((src / "index.html").read_text(encoding="utf-8"), repo, version, size),
                                    encoding="utf-8")
    for f in src.rglob("*"):
        if f.is_file() and f.name != "index.html":
            t = dst / f.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
    cname = SITE / "CNAME"
    if not cname.exists():
        (dst / "CNAME").unlink(missing_ok=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_problems(zpath: Path, url: str) -> list[str]:
    """ตรวจ zip ที่จะแจก: มี exe, มี config ที่ update_url ตรง, ไม่มีข้อมูลส่วนตัวของเครื่องนี้."""
    out = []
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
        if f"{NAME}/{NAME}.exe" not in names:
            out.append(f"ไม่มี {NAME}/{NAME}.exe ใน zip")
        cfg = f"{NAME}/_internal/plc_game/config.yaml"
        if cfg not in names:
            out.append("ไม่มี config.yaml ใน zip")
        elif read_update_url(zf.read(cfg).decode("utf-8")) != url:
            out.append("update_url ใน zip ไม่ตรง (build ใหม่ — อย่าใช้ --skip-build)")
        for bad in ("scores.json", "students.json", "ui_state.json"):
            if any(n.endswith("/" + bad) for n in names):
                out.append(f"มีไฟล์ข้อมูลของเครื่องนี้ติดไปด้วย: {bad}")
    return out


def record_hashes(zpath: Path, dst: Path) -> int:
    """จดแฮชด่าน/ผังที่แจกใน zip นี้ → เวอร์ชันถัดไปรู้ว่าไฟล์ของผู้ใช้เป็นต้นฉบับ (อัปเดตได้) หรือแก้แล้ว."""
    from plc_game.paths import content_hash
    data = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
    added = 0
    with zipfile.ZipFile(zpath) as zf:
        for n in zf.namelist():
            m = re.match(rf"^{NAME}/_internal/((?:levels|panels)/[^/]+\.(?:yaml|plcpanel))$", n)
            if m:
                h = content_hash(zf.read(n))
                if h not in data.setdefault(m.group(1), []):
                    data[m.group(1)].append(h)
                    added += 1
    dst.write_text(json.dumps(dict(sorted(data.items())), indent=1) + "\n", encoding="utf-8")
    return added


# ---------------- ทำงานจริง ----------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="เตรียมไฟล์ปล่อยขึ้น GitHub Releases")
    ap.add_argument("--repo", help="owner/repo บน GitHub (ครั้งแรก) — จำไว้ใน config.yaml")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "release"))
    a = ap.parse_args(argv)

    cfg_text = CONFIG.read_text(encoding="utf-8")
    repo = (a.repo or repo_from_url(read_update_url(cfg_text))).strip().strip("/")
    if not REPO_RE.match(repo or ""):
        print("✖ ยังไม่รู้ชื่อ repo — รันครั้งแรกด้วย --repo <owner>/<repo> (ดู docs\\release_guide.md)")
        return 2
    url = github_update_url(repo)
    date, th, en = changelog_section(CHANGELOG.read_text(encoding="utf-8"), __version__)
    if not en:
        print("⚠ CHANGELOG ไม่มีส่วน ### en — ใช้ข้อความไทยแทน")
    if read_update_url(cfg_text) != url:
        CONFIG.write_text(set_update_url(cfg_text, url), encoding="utf-8")
        print(f"✔ ตั้ง update_url = {url}")

    if not a.skip_build:
        import build_exe
        if build_exe.WORK.exists():
            shutil.rmtree(build_exe.WORK, ignore_errors=True)
        build_exe.build(True)
    zip_name = f"{NAME}-{__version__}-win64.zip"
    src = DIST / zip_name
    if not src.exists():
        print(f"✖ ไม่พบ {src} — รันใหม่โดยไม่ใส่ --skip-build")
        return 2
    probs = zip_problems(src, url)
    if probs:
        print("✖ " + "\n✖ ".join(probs))
        return 1

    print(f"✔ จดแฮชด่าน/ผังที่แจก +{record_hashes(src, HASHES)}")
    out = Path(a.out) / f"v{__version__}"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / zip_name
    shutil.copy2(src, dst)
    sha, size = sha256_of(dst), dst.stat().st_size
    date = date or dt.date.today().isoformat()
    (out / "version.json").write_text(json.dumps(version_json(__version__, repo, date, th, en, zip_name, sha, size),
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "SHA256SUMS.txt").write_text(f"{sha}  {zip_name}\n", encoding="utf-8")
    (out / "RELEASE_NOTES.md").write_text(release_notes(__version__, repo, th, en, zip_name, sha), encoding="utf-8")
    rdir = Path(a.out) / "repo"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "README.md").write_text(repo_readme(repo), encoding="utf-8")
    if SITE.exists():
        write_site(rdir, repo, __version__, size)
        print(f"✔ เว็บ: {rdir / 'index.html'} → https://{repo.split('/')[0].lower()}.github.io/{repo.split('/')[1]}/")

    print(f"\n✔ พร้อมปล่อย v{__version__} → {out}")
    print(f"  1) GitHub → {repo} → Releases → Draft a new release → Tag: v{__version__}")
    print(f"  2) Title: PLC Trainer v{__version__} · คัดข้อความจาก RELEASE_NOTES.md")
    print(f"  3) แนบไฟล์: {zip_name}, version.json, SHA256SUMS.txt → Publish release")
    print(f"  4) ตรวจ: .venv\\Scripts\\python.exe tools\\make_release.py --check")
    return 0


def check_online() -> int:
    """หลังอัปโหลด: ดึง version.json จริงแบบเดียวกับปุ่มในโปรแกรม."""
    from plc_game import update
    url = read_update_url(CONFIG.read_text(encoding="utf-8"))
    try:
        info = update.fetch(url)
    except ValueError as e:
        print(f"✖ {e}")
        return 1
    ok = update.parse_version(info.version) == update.parse_version(__version__)
    print(f"{'✔' if ok else '✖'} ออนไลน์: v{info.version} ({info.date}) · ในเครื่อง: v{__version__} · {info.url}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        raise SystemExit(check_online())
    raise SystemExit(main())
