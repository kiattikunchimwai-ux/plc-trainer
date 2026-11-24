"""อัปโหลดไฟล์ใน release/repo ขึ้น repo ผ่าน GitHub Contents API (ไม่ต้องมี git)."""
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = sys.argv[1]
SRC = Path(sys.argv[2])
MSG = sys.argv[3] if len(sys.argv) > 3 else "Update site"


def gh(*args, input_file=None, check=True):
    cmd = [GH, "api", *args] + (["--input", str(input_file)] if input_file else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise SystemExit(f"gh api {args[:3]} failed: {r.stderr.strip()}")
    return r


for f in sorted(p for p in SRC.rglob("*") if p.is_file()):
    rel = f.relative_to(SRC).as_posix()
    body = {"message": f"{MSG}: {rel}", "content": base64.b64encode(f.read_bytes()).decode()}
    cur = gh(f"repos/{REPO}/contents/{rel}", check=False)
    if cur.returncode == 0:
        body["sha"] = json.loads(cur.stdout)["sha"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as t:
        json.dump(body, t)
    gh("-X", "PUT", f"repos/{REPO}/contents/{rel}", input_file=t.name)
    Path(t.name).unlink()
    print("uploaded", rel)
