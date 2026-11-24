"""ดูยอดดาวน์โหลด (ทุกเวอร์ชัน) + ยอดเข้าชมหน้า repo 14 วันล่าสุด จาก GitHub.

รัน:  .venv\\Scripts\\python.exe tools\\stats.py
ต้องล็อกอิน gh แล้ว (ยอดเข้าชม repo ต้องเป็นเจ้าของ repo) — ไม่รวมคนเข้าเว็บ github.io (GitHub Pages ไม่เก็บสถิติ)
"""
from __future__ import annotations

import json
import subprocess
import sys

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = sys.argv[1] if len(sys.argv) > 1 else "kiattikunchimwai-ux/plc-trainer"


def api(path: str):
    r = subprocess.run([GH, "api", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"✖ gh api {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def main() -> None:
    total = 0
    print(f"ยอดดาวน์โหลด · {REPO}")
    for rel in api(f"repos/{REPO}/releases"):
        zips = [a for a in rel["assets"] if a["name"].endswith(".zip")]
        n = sum(a["download_count"] for a in zips)
        total += n
        print(f"  {rel['tag_name']:<10} {rel['published_at'][:10]}  {n:>6} ครั้ง")
    print(f"  {'รวม':<10} {'':<10}  {total:>6} ครั้ง")
    try:
        views = api(f"repos/{REPO}/traffic/views")
        refs = api(f"repos/{REPO}/traffic/popular/referrers")
    except SystemExit as e:
        print(e)
        return
    print(f"\nเข้าชมหน้า repo (14 วัน): {views['count']} ครั้ง · {views['uniques']} คน")
    for d in views["views"][-7:]:
        print(f"  {d['timestamp'][:10]}  {d['count']:>4} ครั้ง  {d['uniques']:>4} คน")
    if refs:
        print("มาจาก: " + ", ".join(f"{r['referrer']} ({r['uniques']})" for r in refs[:5]))


if __name__ == "__main__":
    main()
