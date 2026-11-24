"""รวบรวมข้อความ tr("...") ทั้งโปรเจกต์ลง i18n/en.json (คงคำแปลเดิม) + รายงานที่ยังไม่แปล / ข้อความไทยที่ยังไม่ครอบ tr.

    python tools/i18n_extract.py            เติม key ใหม่ (ค่าว่าง) + ลบ key ที่ไม่ใช้แล้ว + รายงาน
    python tools/i18n_extract.py --missing  พิมพ์ key ที่ยังไม่แปล (JSON) ไว้ส่งให้คนแปล
    python tools/i18n_extract.py --raw      พิมพ์ข้อความไทยที่ยังไม่ได้ครอบ tr (ไม่นับ docstring)
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from i18n_wrap import THAI, _docstring_ids  # noqa: E402

EN = ROOT / "i18n" / "en.json"
SKIP_FILES = {"i18n.py"}


def py_files():
    return [p for p in sorted((ROOT / "plc_game").rglob("*.py")) if p.name not in SKIP_FILES]


def scan(path: Path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    keys, raw = [], []
    inside = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
            for x in ast.walk(node):
                inside.add(id(x))
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.append(node.args[0].value)
    docs = _docstring_ids(tree)
    if "# i18n: skip-file" in src:
        return keys, raw
    lines = src.splitlines()
    for node in ast.walk(tree):
        if id(node) in inside or id(node) in docs:
            continue
        if isinstance(node, ast.Constant) and "# i18n: skip" in lines[node.lineno - 1]:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and THAI.search(node.value):
            raw.append((node.lineno, node.value))
    return keys, raw


def collect():
    keys, raw = {}, []
    for p in py_files():
        k, r = scan(p)
        for x in k:
            keys.setdefault(x, p.relative_to(ROOT).as_posix())
        raw += [(p.relative_to(ROOT).as_posix(), ln, v) for ln, v in r]
    return keys, raw


def load_en() -> dict:
    try:
        return json.loads(EN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def example_panels() -> list[Path]:
    """ผังตัวอย่าง/ผังด่านที่มากับโปรแกรม (ชื่อจาก tools/make_example_panels.py) — ผังที่ผู้ใช้สร้างเองไม่นับ."""
    src = (ROOT / "tools" / "make_example_panels.py").read_text(encoding="utf-8")
    names = set(re.findall(r'"([\w\-]+\.plcpanel)"', src))
    return [p for d in ("panels", "levels") for p in sorted((ROOT / d).glob("*.plcpanel")) if p.name in names]


def data_keys() -> set[str]:
    """ข้อความในผังตัวอย่างที่แปลตอนแสดงผล (label / text / unit / ข้อความของ messages)."""
    out = set()
    for p in example_panels():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if THAI.search(str(d.get("name", ""))):
            out.add(str(d["name"]))
        for dv in d.get("devices", []):
            props = dv.get("props") or {}
            for k in ("label", "text", "unit"):
                v = props.get(k)
                if isinstance(v, str) and THAI.search(v):
                    out.add(v)
            for part in str(props.get("messages", "") or "").replace("\n", ";").split(";"):
                _, eq, txt = part.partition("=")
                if eq and THAI.search(txt):
                    out.add(txt.strip())
    return out


def extra_keys() -> set[str]:
    """key ที่ไม่ได้มาจาก tr("...") ในโค้ด: ข้อความในผังตัวอย่าง + i18n/extra_keys.txt (บรรทัดละ key)."""
    f = ROOT / "i18n" / "extra_keys.txt"
    try:
        lines = {ln for ln in f.read_text(encoding="utf-8").split("\n") if ln.strip()}
    except OSError:
        lines = set()
    return lines | data_keys()


def main(argv):
    keys, raw = collect()
    if "--raw" in argv:
        for f, ln, v in raw:
            print(f"{f}:{ln}: {v[:90]!r}")
        print(f"รวม {len(raw)} ข้อความ")
        return
    en = load_en()
    wanted = set(keys) | extra_keys()
    if "--missing" in argv:
        miss = {k: "" for k in sorted(wanted, key=lambda k: keys.get(k, "~")) if not en.get(k)}
        print(json.dumps(miss, ensure_ascii=False, indent=1))
        return
    merged = {k: en.get(k, "") for k in sorted(wanted, key=lambda k: (keys.get(k, "~"), k))}
    EN.parent.mkdir(exist_ok=True)
    EN.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    done = sum(1 for v in merged.values() if v)
    print(f"en.json: {len(merged)} key · แปลแล้ว {done} · ยังไม่แปล {len(merged) - done} · ไทยที่ยังไม่ครอบ tr {len(raw)}")


if __name__ == "__main__":
    main(sys.argv[1:])
