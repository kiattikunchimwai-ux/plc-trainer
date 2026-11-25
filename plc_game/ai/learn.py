"""AI เรียนรู้จากเงื่อนไขของด่านด้วยการจำลองในเครื่อง (ไม่ใช้ Qt ไม่ใช้อินเทอร์เน็ต).

1) train(): จากงานที่อ่านได้ (spec.Profile) สร้าง ladder ผู้สมัคร → รันบน PLC ในตัวด้วยเวลาเสมือน → ต้องผ่านทุกข้อ
2) ใส่ข้อผิดที่พบบ่อยทีละอย่าง → จำว่า "ผิดแบบนี้ข้อตรวจไหนพัง" (ลายเซ็น)
3) match(): เทียบผลตรวจของนักเรียนกับลายเซ็น → สาเหตุที่น่าจะเป็น (เป็นการคาด ไม่ใช่ค่าที่วัดได้ และไม่มีผลต่อคะแนน)
4) Memory: จำลายเซ็น, ความแม่นของแต่ละสาเหตุ, คำแนะนำที่รับ/ปฏิเสธ ใน panels/ai_memory.json
   — ไม่เก็บชื่อนักเรียน และไม่เก็บ/ไม่แสดง ladder ผู้สมัคร (จะกลายเป็นเฉลย)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from ..i18n import tr
from ..ladder.csvio import Instr, Program
from ..levels.engine import Level, LevelRunner
from ..plc.soft_plc import RUN, SoftPLC
from .analyzer import Finding
from .spec import Profile, is_bit

MEMORY_FILE = paths.data_dir() / "ai_memory.json"
VERSION, MAX_LEVELS, MAX_KINDS, MAX_BYTES = 1, 200, 300, 2_000_000
SCAN_S, POLL_EVERY = 0.02, 2
MIN_MATCH = 0.6


# ======================= ความจำ =======================
class Memory:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.data = self._read()

    def _file(self) -> Path:
        return Path(self.path or MEMORY_FILE)

    def _read(self) -> dict:
        try:
            f = self._file()
            if f.stat().st_size > MAX_BYTES:
                raise ValueError
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            d = {}
        out = {"version": VERSION, "levels": {}, "kinds": {}, "tips": {}}
        if isinstance(d, dict) and d.get("version") == VERSION:
            out["levels"] = {str(k): v for k, v in _dict(d.get("levels")).items() if _good_level(v)}
            for k in ("kinds", "tips"):
                out[k] = {str(n): [int(v[0]), int(v[1])] for n, v in _dict(d.get(k)).items()
                          if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and x >= 0 for x in v)}
        return out

    def save(self):
        lv = self.data["levels"]
        for k in sorted(lv, key=lambda k: lv[k].get("at", 0))[:max(0, len(lv) - MAX_LEVELS)]:
            del lv[k]
        for name in ("kinds", "tips"):
            d = self.data[name]
            for k in sorted(d, key=lambda k: sum(d[k]))[:max(0, len(d) - MAX_KINDS)]:
                del d[k]
        f = self._file()
        tmp = f.with_name(f.name + ".tmp")
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError:
            pass                                   # จำไม่ได้ไม่ใช่เรื่องร้ายแรง — โปรแกรมทำงานต่อ

    def clear(self):
        self.data = {"version": VERSION, "levels": {}, "kinds": {}, "tips": {}}
        self._file().unlink(missing_ok=True)

    # ----- ลายเซ็นของด่าน -----
    def model(self, level_id: str, h: str) -> "Model | None":
        d = self.data["levels"].get(level_id)
        if not d or d.get("hash") != h:            # เงื่อนไขเปลี่ยน = ต้องเรียนใหม่
            return None
        return Model(d["status"], d.get("why", ""), [Mistake(**m) for m in d["mistakes"]], list(d["loose"]), h, list(d["features"]))

    def store(self, level_id: str, m: "Model"):
        self.data["levels"][level_id] = {
            "hash": m.hash, "status": m.status, "why": m.why, "at": int(time.time()), "features": m.features,
            "mistakes": [vars(x) for x in m.mistakes], "loose": m.loose}
        self.save()

    # ----- ความแม่นของสาเหตุ: [ครั้งที่คาด, ครั้งที่ยืนยัน] -----
    def weight(self, kind: str, features) -> float:
        """ความแม่นที่เคยเจอ (0–1, ไม่เคยเจอ = 0.5) — ด่านที่ลักษณะเดียวกันมีน้ำหนักมากกว่า."""
        s = c = 0.0
        for key, mul in ((kind, 1), (kind + "|" + ",".join(features), 2)):
            a, b = self.data["kinds"].get(key, [0, 0])
            s, c = s + mul * a, c + mul * b
        return (c + 1) / (s + 2)

    def observe(self, kinds, features, confirmed=()):
        for k in kinds:
            for key in (k, k + "|" + ",".join(features)):
                v = self.data["kinds"].setdefault(key, [0, 0])
                v[0] += 1
                v[1] += int(k in confirmed)
        if kinds:
            self.save()

    def tip(self, key: str, accepted: bool):
        v = self.data["tips"].setdefault(key, [0, 0])
        v[0] += 1
        v[1] += int(accepted)
        self.save()

    def tip_weight(self, key: str) -> float:
        a, b = self.data["tips"].get(key, [0, 0])
        return (b + 1) / (a + 2)


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _good_level(v) -> bool:
    try:
        return (isinstance(v["hash"], str) and isinstance(v["status"], str) and isinstance(v.get("why", ""), str)
                and all(isinstance(x, str) for x in v["features"]) and all(isinstance(x, str) for x in v["loose"])
                and all(set(m) == {"kind", "out", "inp", "fails"} and isinstance(m["kind"], str) and isinstance(m["out"], str)
                        and isinstance(m["inp"], str) and all(isinstance(x, str) for x in m["fails"]) for m in v["mistakes"]))
    except (TypeError, KeyError, AttributeError):
        return False


# ======================= ผลการเรียนรู้ =======================
@dataclass
class Mistake:
    kind: str
    out: str = ""
    inp: str = ""
    fails: list[str] = field(default_factory=list)        # "ข้อ.ขั้น" ที่ไม่ผ่านจริง (ไม่รวมที่ถูกข้าม)


@dataclass
class Model:
    status: str                                           # ok / physics / unknown / cancelled
    why: str = ""
    mistakes: list[Mistake] = field(default_factory=list)
    loose: list[str] = field(default_factory=list)        # ข้อผิดที่ยังได้ 3 ดาว (kind|out)
    hash: str = ""
    features: list[str] = field(default_factory=list)


# ======================= จำลอง =======================
class Cancelled(Exception):
    pass


def simulate(level: Level, il: list[str], idle: dict[str, int], xy_base: int = 8, cancel=lambda: False,
             limit: float = 180.0) -> LevelRunner | None:
    """รัน ladder บน PLC ในตัวด้วยเวลาเสมือน (ไม่มีอุปกรณ์จริง) — None = ladder ใช้ไม่ได้."""
    ins = []
    for n, line in enumerate([*il, "END"]):
        op, *a = line.split()
        ins.append(Instr(n, op, tuple(a)))
    t = [0.0]
    plc = SoftPLC(clock=lambda: t[0], auto_scan=False, xy_base=xy_base)
    plc.connect()
    try:
        if plc.load(Program("ai", "FX5UCPU" if xy_base == 8 else "RCPU R04", ins)):
            return None
        for a, v in idle.items():
            plc.write_bits(a, [v])
        r = LevelRunner(level, lambda a, v, w: (plc.write_words if w else plc.write_bits)(a, [v]))
        bits = {a: is_bit(a) for a in level.addresses()}
        n = 0
        while not r.done and t[0] < limit:
            plc.scan()
            if plc.state != RUN:
                return None
            if n % POLL_EVERY == 0:
                r.feed({a: (plc.read_bits if b else plc.read_words)(a, 1)[0] for a, b in bits.items()}, t[0])
            n += 1
            t[0] = n * SCAN_S
            if n % 50 == 0 and cancel():
                raise Cancelled
        return r if r.done and not r.aborted else None
    finally:
        plc.close()


def fails_of(level: Level, runner) -> list[str]:
    return [f"{r.case_index}.{r.step_index - level.reset_len}" for r in runner.results if not r.passed and not r.skipped]


# ======================= สร้างผู้สมัคร =======================
@dataclass
class Rule:
    """กฎของ output หนึ่งตัวในภายใน (ไม่แสดงต่อผู้ใช้)."""
    out: str
    mode: str                          # direct / delay / count / seq
    starts: list[str] = field(default_factory=list)
    stops: list[str] = field(default_factory=list)
    latch: bool = False
    lock: list[str] = field(default_factory=list)
    k: float = 0.0
    next: str = ""                     # seq: output ถัดไป
    flip: set = field(default_factory=set)        # input ที่ใส่ NO/NC กลับ


def _rules(p: Profile) -> list[Rule] | None:
    rules: dict[str, Rule] = {}
    ys = [y for y in p.outputs if y.startswith("Y")]
    seq_next = {f.other for f in p.get("sequence")}
    for y in ys:
        stops = list(dict.fromkeys(f.inp for f in p.get("off", y)))
        lock = [f.other if f.out == y else f.out for f in p.get("interlock") if y in (f.out, f.other)]
        delay, cnt, on, seq = p.get("delay", y), p.get("count", y), p.get("on", y), p.get("sequence", y)
        if y in seq_next:
            continue
        if seq:
            f = seq[0]
            rules[y] = Rule(y, "seq", [f.inp], stops or _any_stop(p), True, lock, (f.lo + f.hi) / 2, f.other)
        elif delay:
            f = delay[0]
            rules[y] = Rule(y, "delay", [f.inp], stops, True, lock, (f.lo + f.hi) / 2)
        elif cnt:
            f = cnt[0]
            rules[y] = Rule(y, "count", [f.inp], stops, True, lock, f.lo)
        elif on:
            rules[y] = Rule(y, "direct", list(dict.fromkeys(f.inp for f in on)), stops, bool(p.get("latch", y)), lock)
        else:
            return None
    for r in rules.values():
        r.stops = [s for s in r.stops if s not in r.starts]
        if r.latch and not r.stops:
            r.stops = [s for s in _any_stop(p) if s not in r.starts]
    return list(rules.values()) or None


def _any_stop(p: Profile) -> list[str]:
    return list(dict.fromkeys(f.inp for f in p.get("off")))[:1]


def _compile(rules: list[Rule], p: Profile) -> list[str]:
    out: list[str] = []
    for i, r in enumerate(rules):
        def c(op, a, r=r, active=True):
            """หน้าสัมผัสที่ ON เมื่อกด (active) หรือเมื่อไม่ได้กด."""
            no = active != bool(p.idle.get(a, 0))
            if a in r.flip:
                no = not no
            return f"{op if no else {'LD': 'LDI', 'OR': 'ORI', 'AND': 'ANI'}[op]} {a}"

        def seal(coil, r=r):
            ls = [c("LD" if n == 0 else "OR", x) for n, x in enumerate(r.starts)]
            if r.latch:
                ls.append(f"OR {coil}")
            ls += [c("AND", s, active=False) for s in r.stops]
            return ls

        m, tm = f"M{100 + i}", f"T{100 + i}"
        kt = f"K{max(1, round(r.k * 10))}"
        if r.mode == "direct":
            out += seal(r.out) + [f"ANI {o}" for o in r.lock] + [f"OUT {r.out}"]
        elif r.mode == "delay":
            out += seal(m) + [f"OUT {m}", f"LD {m}", f"OUT {tm} {kt}", f"LD {tm}", *[f"ANI {o}" for o in r.lock], f"OUT {r.out}"]
        elif r.mode == "seq":
            out += seal(m) + [f"OUT {m}", f"LD {m}", f"OUT {tm} {kt}", f"LD {m}", f"ANI {tm}", f"OUT {r.out}",
                              f"LD {m}", f"AND {tm}", f"OUT {r.next}"]
        elif r.mode == "count":
            cn = f"C{100 + i}"
            out += [c("LD", r.starts[0]), f"OUT {cn} K{max(1, round(r.k))}"]
            out += [f"LD {cn}", *[f"ANI {o}" for o in r.lock], f"OUT {r.out}"]
            if r.stops:
                out += [c("LD", r.stops[0]), f"RST {cn}"]
    return out


def _copy(rules: list[Rule], i: int, **kw) -> list[Rule]:
    out = [Rule(r.out, r.mode, list(r.starts), list(r.stops), r.latch, list(r.lock), r.k, r.next, set(r.flip)) for r in rules]
    for k, v in kw.items():
        setattr(out[i], k, v)
    return out


def _variants(rules: list[Rule], p: Profile):
    """ผู้สมัครหลายแบบ (เวลา Timer และการติดค้างที่เป็นไปได้)."""
    yield rules
    for i, r in enumerate(rules):
        if r.mode in ("delay", "seq"):
            f = (p.get("delay", r.out) or p.get("sequence", r.out))[0]
            for q in (0.25, 0.75, 0.9, 0.1):
                yield _copy(rules, i, k=f.lo + (f.hi - f.lo) * q)
        elif r.mode == "direct":
            yield _copy(rules, i, latch=not r.latch)
    direct = [i for i, r in enumerate(rules) if r.mode == "direct"]
    if len(direct) > 1:
        out = rules
        for i in direct:
            out = _copy(out, i, latch=True)
        yield out


def _mutants(rules: list[Rule]):
    for i, r in enumerate(rules):
        x = r.starts[0] if r.starts else ""
        s = r.stops[0] if r.stops else ""
        if r.latch and r.mode != "count":
            yield "no_latch", r.out, x, _copy(rules, i, latch=False)
        if s:
            yield "no_stop", r.out, s, _copy(rules, i, stops=[])
            yield "stop_polarity", r.out, s, _copy(rules, i, flip={s})
        if x:
            yield "start_polarity", r.out, x, _copy(rules, i, flip={x})
        if r.lock:
            yield "no_interlock", r.out, r.lock[0], _copy(rules, i, lock=[])
        if r.mode in ("delay", "seq"):
            yield "time_short", r.out, x, _copy(rules, i, k=r.k * 0.5)
            yield "time_long", r.out, x, _copy(rules, i, k=r.k * 2 + 1)
            yield "no_timer", r.out, x, _copy(rules, i, k=0.1)
        if r.mode == "count":
            yield "count_less", r.out, x, _copy(rules, i, k=max(1, r.k - 1))
            yield "count_more", r.out, x, _copy(rules, i, k=r.k + 1)
        if r.starts:
            yield "not_driven", r.out, x, [q for j, q in enumerate(rules) if j != i]


def train(level: Level, p: Profile, xy_base: int = 8, cancel=lambda: False, budget: float = 12.0) -> Model:
    """เรียนจากเงื่อนไข — จบภายใน budget วินาที (เกิน = จำเท่าที่ได้)."""
    m = Model("unknown", "", hash=p.hash, features=p.features())
    if level.is_fault_hunt:
        m.why = tr("ด่านหาจุดเสียไม่มีเงื่อนไขให้เรียน")
        return m
    if p.physics:
        m.status, m.why = "physics", tr("จำลองเองไม่ได้: ") + p.physics[0]
        return m
    if any(i.level == "error" for i in p.issues):
        m.why = tr("โจทย์ยังมีข้อขัดแย้ง — แก้ก่อนแล้ว AI จะเรียนใหม่เอง")
        return m
    rules = _rules(p)
    if not rules:
        m.why = tr("เงื่อนไขยังไม่พอให้เข้าใจงานทั้งหมด")
        return m
    end = time.monotonic() + budget

    def stop():
        return cancel() or time.monotonic() > end
    good = None
    try:
        for v in _variants(rules, p):
            r = simulate(level, _compile(v, p), p.idle, xy_base, stop)
            if r is not None and r.passed == r.total:
                good = v
                break
        if good is None:
            m.why = tr("ยังหาวิธีทำงานที่ผ่านทุกข้อไม่ได้ — โจทย์อาจซับซ้อนกว่าที่ AI รู้จัก หรือเงื่อนไขขัดกัน")
            return m
        m.status = "ok"
        for kind, out, inp, rules2 in _mutants(good):
            il = _compile(rules2, p) or ["LD SM400", "OUT M199"]
            r = simulate(level, il, p.idle, xy_base, stop)
            if r is None:
                continue
            fails = fails_of(level, r)
            if fails:
                m.mistakes.append(Mistake(kind, out, inp, fails))
            else:
                m.loose.append(f"{kind}|{out}")
    except Cancelled:
        if cancel():
            m.status = "cancelled"
        elif m.status != "ok":
            m.why = tr("ใช้เวลาจำลองนานเกินไป")
    return m


# ======================= ใช้งาน =======================
def mistake_text(kind: str, out: str, inp: str, names: dict[str, str]) -> str:
    def n(a):
        return f"{names[a]} ({a})" if names.get(a) else a
    return {"no_latch": lambda: tr("{0} ไม่มีวงจรคงสถานะ (self-holding)", n(out)),
            "no_stop": lambda: tr("{0} ไม่ได้อยู่ในวงจรตัด {1}", n(inp), n(out)),
            "stop_polarity": lambda: tr("หน้าสัมผัสของ {0} น่าจะใช้ NO/NC กลับด้าน", n(inp)),
            "start_polarity": lambda: tr("หน้าสัมผัสของ {0} น่าจะใช้ NO/NC กลับด้าน", n(inp)),
            "no_interlock": lambda: tr("ไม่มี Interlock ระหว่าง {0} กับ {1}", n(out), n(inp)),
            "time_short": lambda: tr("ค่า K ของ Timer ของ {0} น้อยเกินไป", n(out)),
            "time_long": lambda: tr("ค่า K ของ Timer ของ {0} มากเกินไป", n(out)),
            "no_timer": lambda: tr("{0} ไม่ได้หน่วงเวลาด้วย Timer", n(out)),
            "count_less": lambda: tr("ค่า K ของ Counter ของ {0} น้อยเกินไป", n(out)),
            "count_more": lambda: tr("ค่า K ของ Counter ของ {0} มากเกินไป", n(out)),
            "not_driven": lambda: tr("ยังไม่มีคอยล์ {0} หรือเขียนผิดเลข", n(out))}.get(kind, lambda: kind)()


def match(level: Level, runner, model: Model | None, mem: Memory) -> list[tuple[Mistake, float]]:
    """สาเหตุที่ลายเซ็นใกล้กับผลตรวจ (มากสุด 3) พร้อมความคล้าย 0–1."""
    got = set(fails_of(level, runner))
    if not got or model is None or model.status != "ok":
        return []
    out = []
    for m in model.mistakes:
        want = set(m.fails)
        sim = len(got & want) / len(got | want)
        if sim >= MIN_MATCH:
            out.append((m, sim))
    out.sort(key=lambda x: (-round(x[1], 2), -mem.weight(x[0].kind, model.features)))
    seen, best = set(), []
    for m, sim in out:
        if (m.kind, m.inp if "polarity" in m.kind else m.out) not in seen:
            seen.add((m.kind, m.inp if "polarity" in m.kind else m.out))
            best.append((m, sim))
    return best[:3]


def findings(matches, names: dict[str, str]) -> list[Finding]:
    if not matches:
        return []
    lines = [(tr("ตรงกับอาการที่จำลองไว้ทุกข้อ: ") if sim > 0.999 else tr("ใกล้เคียง {0}%: ", round(sim * 100)))
             + mistake_text(m.kind, m.out, m.inp, names) for m, sim in matches]
    lines.append(tr("เป็นการคาดจากการจำลองเงื่อนไขของด่านนี้ ไม่ใช่ค่าที่วัดได้ — ไม่มีผลต่อคะแนน"))
    return [Finding(tr("🧠 AI เรียนรู้จากเงื่อนไข: สาเหตุที่น่าจะเป็น"), lines, "info", kind="learned")]


class Coach:
    """ตัวเชื่อมกับ UI: เทียบผลตรวจ, จำว่าครั้งถัดไปแก้ตรงที่คาดไหม (จำในหน่วยความจำจนกว่าจะตรวจครั้งต่อไป)."""

    def __init__(self, mem: Memory | None = None):
        self.mem = mem or Memory()
        self._last: tuple | None = None         # (ผู้เรียน, ด่าน, hash, ข้อที่พัง, สาเหตุ) — ไม่บันทึกลงไฟล์

    def reset(self):
        self._last = None

    def after_check(self, who: str, level: Level, runner, p: Profile) -> list[Finding]:
        model = self.mem.model(level.id, p.hash)
        got = set(fails_of(level, runner))
        last, self._last = self._last, None
        if last and last[:3] == (who, level.id, p.hash):
            _, _, _, before, kinds, feats = last
            fixed = not (before & got) and runner.passed > 0
            self.mem.observe(kinds[:1], feats, kinds[:1] if fixed else ())
        ms = match(level, runner, model, self.mem)
        if ms:
            self._last = (who, level.id, p.hash, got, [m.kind for m, _ in ms], model.features)
        return findings(ms, p.names)


def model_lines(m: Model, p: Profile) -> list[str]:
    """สรุปให้ผู้สร้างด่านเห็น (ไม่มี ladder)."""
    if m.status != "ok":
        return [m.why] if m.why else []
    out = [tr("จำลองแล้วทำได้จริง · เรียนรู้ข้อผิดที่พบบ่อย {0} แบบ", len(m.mistakes))]
    for x in m.loose:
        kind, _, y = x.partition("|")
        inp = next((f.inp for f in p.get("off", y) or p.get("on", y)), "")
        if kind == "no_interlock":
            inp = next((f.other if f.out == y else f.out for f in p.get("interlock") if y in (f.out, f.other)), "")
        out.append(tr("โจทย์ยังหลวม: ยังได้ 3 ดาวแม้ ") + mistake_text(kind, y, inp, p.names))
    return out
