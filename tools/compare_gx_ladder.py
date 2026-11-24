"""เทียบตัวจำลอง ladder กับ GX Simulator3 จริง: กด X แบบสุ่มผ่าน SLMP บันทึกค่า แล้วเล่น CSV ซ้ำเทียบทีละ address.

    python tools/compare_gx_ladder.py <ไฟล์.csv> [วินาที] [--mock] [--xs=X2,X5] [--seed=2] [--drop=BCD]     (เขียนเฉพาะ X ในเครื่องนี้ 127.0.0.1:5511)
"""
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from plc_game.ladder import load_csv  # noqa: E402
from plc_game.ladder.model import Ladder  # noqa: E402
from plc_game.ladder.replay import Recording, _readable, mismatches, simulate  # noqa: E402
from plc_game.panel.watch import blocks_for  # noqa: E402
from plc_game.plc.device import device_range  # noqa: E402

BASE = 16
args = [a for a in sys.argv[1:] if not a.startswith("--")]
prog = load_csv(args[0])
sec = float(args[1]) if len(args) > 1 else 60.0
opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
prog = prog.with_instrs(i for i in prog.instrs if i.op not in opt.get("drop", "").split(","))   # ตัดคำสั่งที่อ่านไม่ออกออกจากฝั่งจำลอง
L = Ladder(prog, BASE)
if "--mock" in sys.argv:
    from ladder_kit import as_mock
    from plc_game.plc.mock_client import MockPLC
    c = MockPLC(program=as_mock(L), xy_base=BASE)
else:
    from plc_game.plc.slmp_client import SLMPClient
    c = SLMPClient(host="127.0.0.1", port=5511, xy_base=BASE)
c.connect()
names = [n for n in dict.fromkeys([*L.written, *L.read]) if _readable(n, BASE)]      # อ่านครบ ไม่จำกัดจำนวนก้อน
xs = [n for n in names if n.startswith("X") and n not in L.written]
if "xs" in opt:
    xs = opt["xs"].split(",")
blocks = blocks_for(names, BASE)
trace, events, last = [], [], None
rnd = random.Random(int(opt.get("seed", 1)))
t0 = time.monotonic()
nxt = t0 + 1.0          # ให้ได้ค่าตั้งต้นที่นิ่งก่อนกดตัวแรก
try:
    for x in xs:
        c.write_bits(x, [0])
    while (now := time.monotonic()) - t0 < sec:
        if now >= nxt:
            x = rnd.choice(xs)
            v = 1 - (last or {}).get(x, 0)
            c.write_bits(x, [v])
            events.append((now - t0, f"{x} ← {v}"))
            nxt = now + rnd.choice((0.4, 0.7, 1.2, 4.0))       # 4 s ให้ timer ครบเวลา
        snap = {}
        for b in blocks:
            vals = (c.read_bits if b.is_bit else c.read_words)(b.head, b.count)
            snap.update(zip((d.name for d in device_range(b.head, b.count, BASE)), vals))
        snap = {n: snap[n] for n in names}
        if snap != last:
            trace.append((time.monotonic() - t0, snap))
            last = snap
        time.sleep(0.02)
finally:
    for x in xs:
        try:
            c.write_bits(x, [0])
        except Exception:  # noqa: BLE001
            break
    c.close()
runner = SimpleNamespace(trace=trace, events=events, results=[])
out = ROOT / "gx_projects" / "samples" / ("compare_mock.json" if "--mock" in sys.argv else f"compare_gx_{opt.get('seed', 1)}.json")
out.write_text(json.dumps({"csv": Path(args[0]).name, "trace": trace, "events": events}, ensure_ascii=False), encoding="utf-8")
rec = Recording(runner)
track = [n for n in names if n in L.written]
run = simulate(L, rec, track)
bad = mismatches(L, rec, run, rec.end)
print(f"snapshot {len(trace)} · {len(trace) / sec:.1f} Hz · X {xs}")
for n in track:
    ch = sum(a[1][n] != b[1][n] for a, b in zip(trace, trace[1:]))
    unk = sum(v[n] is None for v in run.v) / len(run.v)
    print(f"{n:6} เปลี่ยน {ch:3} ครั้ง · ไม่รู้ {unk:4.0%}")
print("ไม่ตรง:", bad or "ไม่มี")
