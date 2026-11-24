"""รวมไฟล์คำแปล {ไทย: English} เข้า i18n/en.json (เฉพาะ key ที่มีอยู่ในโค้ด; รายงาน key ที่ไม่รู้จัก).

    python tools/i18n_merge.py แปล_ชุด1.json [...]
"""
import json
import sys
from pathlib import Path

EN = Path(__file__).resolve().parents[1] / "i18n" / "en.json"


def main(files):
    en = json.loads(EN.read_text(encoding="utf-8"))
    added, unknown = 0, []
    for f in files:
        for k, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if k in en:
                en[k] = v
                added += 1
            else:
                unknown.append(k)
    EN.write_text(json.dumps(en, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"เพิ่ม {added} · ไม่รู้จัก {len(unknown)}")
    for k in unknown[:20]:
        print("  ?", repr(k[:80]))


if __name__ == "__main__":
    main(sys.argv[1:])
