"""ครอบข้อความไทยในโค้ดด้วย tr() อัตโนมัติ (ใช้ ast หาตำแหน่งที่แน่นอน แล้วแก้จากท้ายไฟล์ขึ้นมา).

    python tools/i18n_wrap.py plc_game/ui/main_window.py [...]   (--dry = แค่รายงาน)

- "ข้อความ"            → tr("ข้อความ")
- f"ผ่าน {a.b}/{c} ข้อ" → tr("ผ่าน {0}/{1} ข้อ", a.b, c)      (format spec / !r คงไว้)
- ข้าม: docstring, ที่อยู่ใน tr() แล้ว, key ของ dict, ตัวห้อย [..], ตัวเปรียบเทียบ (== / in), ค่า default ของพารามิเตอร์,
  f-string ที่ format spec มีนิพจน์ซ้อน, และบรรทัดที่มีคอมเมนต์ `# i18n: skip`
- เพิ่ม `from <..>i18n import tr` ให้เองถ้ายังไม่มี
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

THAI = re.compile(r"[฀-๿]")
ROOT = Path(__file__).resolve().parents[1]


def pyquote(s: str) -> str:
    r = repr(s)
    if r[0] == "'" and '"' not in s:
        r = '"' + r[1:-1].replace("\\'", "'") + '"'
    return r


def _docstring_ids(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, (ast.Constant, ast.JoinedStr)):
                out.add(id(b[0].value))
    return out


def _skip_ids(tree) -> set[int]:
    """โหนดที่ห้ามครอบ (รวมทั้งลูกหลาน)."""
    skip = set()

    def mark(n):
        for x in ast.walk(n):
            skip.add(id(x))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
            mark(node)
        elif isinstance(node, ast.Dict):
            for k in node.keys:
                if k is not None:
                    mark(k)
        elif isinstance(node, ast.Subscript):
            mark(node.slice)
        elif isinstance(node, ast.Compare):
            mark(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for d in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                mark(d)
        elif isinstance(node, ast.JoinedStr):
            for v in node.values:            # ชิ้นส่วนภายใน f-string จัดการที่ตัว JoinedStr เอง
                skip.add(id(v))
                if isinstance(v, ast.FormattedValue):
                    mark(v)
        elif isinstance(node, ast.match_case):
            mark(node.pattern)
    return skip


def _fstring(node: ast.JoinedStr, src: str) -> str | None:
    tmpl, args = [], []
    for v in node.values:
        if isinstance(v, ast.Constant):
            tmpl.append(str(v.value).replace("{", "{{").replace("}", "}}"))
        elif isinstance(v, ast.FormattedValue):
            expr = ast.get_source_segment(src, v.value)
            if expr is None:
                return None
            conv = {-1: "", 115: "!s", 114: "!r", 97: "!a"}[v.conversion]
            spec = ""
            if v.format_spec is not None:
                if any(not isinstance(x, ast.Constant) for x in v.format_spec.values):
                    return None
                spec = ":" + "".join(str(x.value) for x in v.format_spec.values)
            tmpl.append("{" + str(len(args)) + conv + spec + "}")
            args.append(expr.replace("\n", " "))
        else:
            return None
    text = "".join(tmpl)
    if not args:
        return f"tr({pyquote(text.replace('{{', '{').replace('}}', '}'))})"
    return f"tr({pyquote(text)}, " + ", ".join(args) + ")"


def _offsets(src: str) -> list[int]:
    starts, n = [0], 0
    for line in src.splitlines(keepends=True):
        n += len(line)
        starts.append(n)
    return starts


def _abs(starts, lines_b, lineno, col) -> int:
    """ast ให้ col เป็น byte offset (utf-8) → แปลงเป็น index ของ str."""
    line = lines_b[lineno - 1]
    return starts[lineno - 1] + len(line[:col].decode("utf-8"))


def rel_import(path: Path) -> str:
    pkg_parts = path.resolve().relative_to(ROOT).parts[:-1]      # ('plc_game', 'ui', 'panel')
    depth = len(pkg_parts) - 1
    return "from " + "." * (depth + 1) + "i18n import tr"


def wrap_source(src: str, path: Path) -> tuple[str, int, list[str]]:
    if "# i18n: skip-file" in src:
        return src, 0, []
    tree = ast.parse(src)
    docs, skip = _docstring_ids(tree), _skip_ids(tree)
    lines = src.splitlines(keepends=True)
    lines_b = [ln.encode("utf-8") for ln in lines]
    starts = _offsets(src)
    edits, notes = [], []
    for node in ast.walk(tree):
        if id(node) in skip or id(node) in docs:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and THAI.search(node.value):
            new = None
        elif isinstance(node, ast.JoinedStr) and any(isinstance(v, ast.Constant) and THAI.search(str(v.value))
                                                      for v in node.values):
            new = _fstring(node, src)
            if new is None:
                notes.append(f"{path.name}:{node.lineno} f-string ซับซ้อน — ข้าม")
                continue
        else:
            continue
        if "i18n: skip" in lines[node.lineno - 1]:
            continue
        a = _abs(starts, lines_b, node.lineno, node.col_offset)
        b = _abs(starts, lines_b, node.end_lineno, node.end_col_offset)
        if new is None:
            new = "tr(" + src[a:b] + ")"
        edits.append((a, b, new))
    edits.sort(reverse=True)
    out = src
    for a, b, new in edits:
        out = out[:a] + new + out[b:]
    if edits and not re.search(r"^from \.+i18n import .*\btr\b", out, re.M):
        imp = rel_import(path)
        m = re.search(r"^from __future__ import annotations\n", out, re.M)
        if m:
            out = out[:m.end()] + "\n" + imp + "\n" + out[m.end():]
        else:
            t2 = ast.parse(out)
            pos = 0
            if t2.body and isinstance(t2.body[0], ast.Expr) and isinstance(t2.body[0].value, ast.Constant):
                pos = _offsets(out)[t2.body[0].end_lineno]
            out = out[:pos] + imp + "\n" + out[pos:]
    ast.parse(out)                          # ต้อง parse ได้เสมอ
    return out, len(edits), notes


def main(argv):
    dry = "--dry" in argv
    total = 0
    for f in [a for a in argv if not a.startswith("--")]:
        p = Path(f)
        src = p.read_text(encoding="utf-8")
        out, n, notes = wrap_source(src, p)
        total += n
        for x in notes:
            print("  ⚠", x)
        print(f"{p}: {n} จุด")
        if not dry and out != src:
            p.write_text(out, encoding="utf-8", newline="\n")
    print(f"รวม {total} จุด")


if __name__ == "__main__":
    main(sys.argv[1:])
