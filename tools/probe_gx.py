"""หาพอร์ต SLMP ของ GX Simulator3 อัตโนมัติ แล้วทดสอบอ่าน/เขียน.

รัน:  .venv\\Scripts\\python tools\\probe_gx.py [port ...]
ถ้าไม่ระบุพอร์ต จะหาพอร์ต TCP ที่เปิดรอโดยโปรแกรมในโฟลเดอร์ MELSOFT
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plc_game.plc.slmp_client import SLMPClient  # noqa: E402

PS = r"""
Get-NetTCPConnection -State Listen | ForEach-Object {
  $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  [pscustomobject]@{port=$_.LocalPort; addr=$_.LocalAddress; name=$p.ProcessName; path=$p.Path}
} | ConvertTo-Json -Compress
"""


def melsoft_ports():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", PS], capture_output=True, text=True).stdout
    rows = json.loads(out or "[]")
    rows = rows if isinstance(rows, list) else [rows]
    hits = [r for r in rows if r.get("path") and "MELSOFT" in r["path"].upper()]
    for r in hits:
        print(f"  พบ: {r['name']}  {r['addr']}:{r['port']}")
    return sorted({r["port"] for r in hits})


def probe(port, plc_type):
    c = SLMPClient(port=port, plc_type=plc_type, timeout=1.5, xy_base=16 if plc_type == "iQ-R" else 8)
    try:
        c.connect()
        sm = c.read_bits("SM400", 1)       # SM400 = ON เสมอเมื่อ CPU RUN
        return c, sm
    except Exception as e:
        c.close()
        return None, e


def main():
    ports = [int(a) for a in sys.argv[1:]] or melsoft_ports() or [5511]
    print("ทดสอบพอร์ต:", ports)
    for port in ports:
        for plc_type in ("iQ-R", "Q"):
            c, res = probe(port, plc_type)
            if c is None:
                print(f"  ✖ {port} ({plc_type}): {res}")
                continue
            print(f"  ✔ {port} ({plc_type}): SM400 = {res}  → เชื่อมต่อสำเร็จ")
            print("    X0-X7 :", c.read_bits("X0", 8))
            print("    Y0-Y7 :", c.read_bits("Y0", 8))
            try:
                c.write_bits("X0", [1]); time.sleep(0.3)
                y = c.read_bits("Y0", 8)
                c.write_bits("X0", [0]); time.sleep(0.3)
                print("    เขียน X0=1 แล้วอ่าน Y:", y, "| หลังปล่อย X0:", c.read_bits("Y0", 8))
            except Exception as e:
                print("    ✖ เขียน X ไม่ได้:", e, "→ ใช้ input_device: M ใน config.yaml")
            c.close()
            print(f"\nตั้งค่าใน config.yaml:  port: {port}  plc_type: {plc_type}")
            return 0
    print("\nไม่พบ GX Simulator3 ที่ตอบ SLMP — กด Start Simulation ใน GX Works3 แล้วหรือยัง?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
