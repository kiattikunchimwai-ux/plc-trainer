"""เช็กเวอร์ชันใหม่ (ไม่ใช้ Qt): อ่าน version.json จาก URL ที่ตั้งใน config.yaml (`update_url`).

รูปแบบ version.json (สร้างโดย tools/make_release.py):
    {"version": "1.1.0", "url": "https://github.com/<owner>/<repo>/releases/tag/v1.1.0",
     "notes": "มีอะไรใหม่", "notes_en": "What's new", "date": "2026-11-18",
     "file": "PLCTrainer-1.1.0-win64.zip", "sha256": "...", "size": 74745485}
เรียกเฉพาะเมื่อผู้ใช้กดปุ่มเช็กเวอร์ชันเท่านั้น — ไม่ส่งข้อมูลผู้ใช้ใด ๆ (GET เปล่า ๆ)
GitHub: update_url = https://github.com/<owner>/<repo>/releases/latest/download/version.json (redirect ไปรุ่นล่าสุดเอง)
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from . import __version__
from .i18n import pick, tr

GITHUB_LATEST = "https://github.com/{0}/releases/latest/download/version.json"
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


def github_update_url(repo: str) -> str:
    """'owner/repo' → ลิงก์ version.json ของรุ่นล่าสุดบน GitHub Releases."""
    repo = repo.strip().strip("/")
    if not REPO_RE.match(repo):
        raise ValueError(tr("ชื่อ repo ต้องเป็นรูปแบบ owner/repo: {0}", repo))
    return GITHUB_LATEST.format(repo)


def parse_version(v: str) -> tuple[int, ...]:
    """'1.2.10' → (1, 2, 10) · ส่วนที่ไม่ใช่ตัวเลขตัดทิ้ง ('v1.2.0-beta' → (1, 2, 0))."""
    nums = re.findall(r"\d+", str(v).split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


@dataclass
class UpdateInfo:
    version: str
    url: str = ""
    notes: str = ""          # ตามภาษาที่เลือกแล้ว
    date: str = ""
    size: int = 0            # ไบต์ของไฟล์ zip (0 = ไม่รู้)

    @property
    def newer(self) -> bool:
        return is_newer(self.version)


def parse_info(data) -> UpdateInfo:
    if not isinstance(data, dict) or not str(data.get("version", "")).strip():
        raise ValueError(tr("version.json ไม่มีช่อง version"))
    url = str(data.get("url", "") or "")
    if url and not url.startswith("https://"):
        url = ""                                         # เปิดเฉพาะลิงก์ https
    notes = pick(str(data.get("notes", "") or ""), str(data.get("notes_en", "") or ""))
    try:
        size = max(0, int(data.get("size", 0) or 0))
    except (TypeError, ValueError):
        size = 0
    return UpdateInfo(str(data["version"]).strip(), url, notes[:500], str(data.get("date", "") or "")[:20], size)


def fetch(url: str, timeout: float = 6.0) -> UpdateInfo:
    """ดึง version.json — ยก ValueError พร้อมข้อความที่แสดงผู้ใช้ได้."""
    if not url:
        raise ValueError(tr("ยังไม่ได้ตั้ง update_url ใน config.yaml"))
    if not url.startswith("https://"):
        raise ValueError(tr("update_url ต้องเป็น https://"))
    req = urllib.request.Request(url, headers={"User-Agent": f"PLCTrainer/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:       # noqa: S310 (https เท่านั้น)
            raw = r.read(64 * 1024)
    except OSError as e:
        raise ValueError(tr("เช็กเวอร์ชันไม่ได้ (ไม่มีอินเทอร์เน็ต?): {0}", e)) from None
    try:
        return parse_info(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(tr("version.json อ่านไม่ได้")) from None
