"""จำลองการ scan ของ ladder แบบ 3 ค่า: 0 / 1 / None (ไม่รู้) — สิ่งที่อ่านไม่ออกเป็น None ไม่เดา."""
from __future__ import annotations

from .model import (ARITH, BITS, COMPARE, CONTACT_OPS, OTHER_CONTACT, WIDE_FUNC, WIDE_WORDS, Ladder, Node, base_func, bit_name,
                    pair, shift, word_name)

MAX_SCAN_STEPS = 20000                # กันวนไม่จบในหนึ่ง scan (กระโดดย้อน)
CONST_BITS = {"SM400": 1, "SM401": 0, "SM402": 0, "SM403": 1,           # ระหว่างทำงาน (ไม่ใช่ scan แรก)
              "SM8000": 1, "SM8001": 0, "SM8002": 0, "SM8003": 1}
CMP = {"=": lambda a, b: a == b, "<>": lambda a, b: a != b, ">": lambda a, b: a > b, "<": lambda a, b: a < b,
       ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b}


def k_and(a, b):
    if a == 0 or b == 0:
        return 0
    return None if a is None or b is None else 1


def k_or(a, b):
    if a == 1 or b == 1:
        return 1
    return None if a is None or b is None else 0


def k_not(a):
    return None if a is None else 1 - a


def k_rise(prev, now):
    if now == 0 or prev == 1:
        return 0
    return None if prev is None or now is None else 1


def w16(v):
    return None if v is None else ((int(v) + 0x8000) & 0xFFFF) - 0x8000


def to_bcd(v, digits):
    """12 → 0x12 ; ไม่อยู่ใน 0–9999 / 0–99999999 = None (PLC จริงเกิด operation error)."""
    return int(str(v), 16) if v is not None and 0 <= v < 10 ** digits else None


def from_bcd(v, digits):
    if v is None:
        return None
    s = format(v & (1 << 4 * digits) - 1, "x")
    return int(s) if s.isdigit() else None


def spread(d, w, v) -> dict:
    """ค่า v ลงช่อง w ของปลายทาง d (K4Y0 = ทีละบิต, นอกนั้นทีละ word) — บิตที่เกินถูกตัดทิ้ง."""
    if v is None:
        return {n: None for n in w}
    step = 1 if d[0] == "K" else 16
    return {n: v >> step * j & (1 << step) - 1 for j, n in enumerate(w)}


def divide(a, b):
    """(ผลหาร, เศษ) ปัดเข้าหาศูนย์ เศษเครื่องหมายตามตัวตั้ง."""
    q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
    return q, a - q * b


class Sim:
    def __init__(self, ladder: Ladder, mem: dict | None = None):
        self.L = ladder
        self.mem: dict[str, int | None] = dict(mem or {})
        self.cv: dict[int, int | None] = {}        # ค่าหน้าสัมผัสแต่ละคำสั่งใน scan ล่าสุด
        self.cond: dict[int, int | None] = {}      # เงื่อนไขของ output แต่ละตัว
        self._prev: dict[tuple, int | None] = {}   # ค่า scan ก่อน (ขอบสัญญาณ)
        self._acc: dict[str, float | None] = {}    # เวลาสะสมของ timer (วินาที)
        self._was: dict[str, int | None] = {}
        for n in ladder.written:                   # ค่าเริ่มของสิ่งที่ ladder เขียน ถ้าไม่เคยวัด = ไม่รู้
            self.mem.setdefault(n, None)

    # ---------- หน่วยความจำ ----------
    def get(self, name):
        if name in self.mem:
            return self.mem[name]
        if name in CONST_BITS:
            return CONST_BITS[name]
        if name.startswith(("X", "SM", "SD", "D", "W")):
            return None
        return 0                                   # ไม่มีใครเขียนเลย = ค่าเริ่มต้นของ PLC

    def _bit(self, a):
        if a[0] == "K":
            return None
        v = self.get(bit_name(a))
        return None if v is None else int(bool(v))

    def _digits(self, a, width):
        """ค่าของ K4X0: ครบความกว้าง = มีเครื่องหมาย, น้อยกว่า = เติม 0."""
        bits = [self.get(n) for n in a[2]]
        if None in bits or len(bits) > width:
            return None
        v = sum(bool(b) << j for j, b in enumerate(bits))
        return v - (1 << width) if v >> width - 1 else v

    def _word(self, a):
        if a is None:
            return None
        if not isinstance(a, int) and a[0] == "K":
            return self._digits(a, 16)
        return a if isinstance(a, int) else (None if a[0] in BITS else self.get(word_name(a)))

    def _wide(self, a):
        """ค่า 32 บิตมีเครื่องหมายจาก word คู่."""
        if a is None or isinstance(a, int):
            return a
        if a[0] == "K":
            return self._digits(a, 32)
        if a[0] not in WIDE_WORDS:
            return None
        lo, hi = (self.get(n) for n in pair(a))
        return None if lo is None or hi is None else (w16(hi) << 16) | (int(lo) & 0xFFFF)

    def _edge(self, key, now):
        prev = self._prev.get(key, now)            # scan แรก: ไม่ถือว่ามีขอบ
        self._prev[key] = now
        return prev

    # ---------- scan ----------
    def scan(self, dt: float):
        L, st, mps, mc = self.L, [], [], []
        self.cv, self.cond = {}, {}
        pc, steps, frames, end = 0, 0, [], len(L.instrs)
        while pc < end:
            k, ins = pc, L.instrs[pc]
            kd, op, args = L.kinds[k], ins.op, L.args[k]
            pc, steps = pc + 1, steps + 1
            if steps > MAX_SCAN_STEPS:
                self._runaway(k)
                break
            if kd == "contact":
                head, mod = CONTACT_OPS[op]
                raw = self._bit(args[0]) if args and isinstance(args[0], tuple) else None
                v = raw
                if mod in ("P", "F", "PI", "FI"):
                    prev = self._edge((k,), raw)
                    v = k_rise(prev, raw) if mod[0] == "P" else k_rise(k_not(prev), k_not(raw))
                if mod.endswith("I"):
                    v = k_not(v)
            elif kd == "compare":
                head, o = COMPARE.match(op).groups()
                val = self._wide if o[0] == "D" else self._word
                a, b = (val(x) for x in args) if len(args) == 2 else (None, None)
                v = None if a is None or b is None else int(CMP[o.lstrip("D")](a, b))
            elif kd == "unknown_contact":
                head, v = OTHER_CONTACT.match(op).group(1), None
            elif kd == "stack":
                self._stack(k, op, st, mps)
                continue
            elif kd == "out":
                power = 1
                for p in mc:
                    power = k_and(power, p[1])
                c = k_and(st[-1], power) if st else power
                if op == "MC":
                    self.cond[k] = c
                    if args and len(args) > 1 and isinstance(args[1], tuple):
                        self.mem[args[1][1]] = c
                    mc.append((ins.args[0] if ins.args else "", c))
                elif op == "MCR":
                    lv = ins.args[0] if ins.args else ""
                    cut = next((j for j, p in enumerate(mc) if p[0] == lv), None)
                    if cut is not None:
                        del mc[cut:]
                else:
                    self.cond[k] = c
                    self._output(k, op, args, c, power, dt)
                continue
            else:
                if op in ("END", "FEND"):
                    break
                if kd == "flow":
                    pc = self._jump(k, op, st, mps, frames, pc)
                continue
            self.cv[k] = v
            if head == "LD" or not st:
                st.append(v)
                del st[:-64]
            elif head == "AND":
                st[-1] = k_and(st[-1], v)
            else:
                st[-1] = k_or(st[-1], v)

    def _jump(self, k, op, st, mps, frames, pc) -> int:
        """คำสั่งถัดไปหลังคำสั่งกระโดด — ตัวจำลอง 3 ค่าไม่จำลองการกระโดด."""
        return pc

    def _runaway(self, k):
        pass

    def _stack(self, k, op, st, mps):
        top = st[-1] if st else None
        if op in ("ANB", "ORB"):
            if len(st) >= 2:
                b = st.pop()
                st[-1] = (k_and if op == "ANB" else k_or)(st[-1], b)
        elif op == "MPS":
            mps.append(top)
        elif op in ("MRD", "MPP"):
            if mps and st:
                st[-1] = mps[-1] if op == "MRD" else mps.pop()
        elif st:
            if op == "INV":
                st[-1] = k_not(top)
            else:
                prev = self._edge((k,), top)
                st[-1] = k_rise(prev, top) if op == "MEP" else k_rise(k_not(prev), k_not(top))
            self.cv[k] = st[-1]

    def _output(self, k, op, args, c, power, dt):
        a0 = args[0] if args else None
        if any(isinstance(a, tuple) and a[0] == "K" for a in args) and not self.L.effects(k)[2]:
            if c != 0:
                for n in self.L.effects(k)[0]:
                    self.mem[n] = None
            return
        if op in ("OUT", "OUTH") and isinstance(a0, tuple):
            if a0[0] in ("T", "ST"):
                self._timer(a0, args, c, dt, 0.1 if op == "OUT" else 0.01)
            elif a0[0] == "C":
                self._counter(k, a0, args, c)
            else:
                self.mem[a0[1]] = c
            return
        if op in ("SET", "RST") and isinstance(a0, tuple):
            names = [bit_name(a0), word_name(a0)]
            v = 1 if op == "SET" else 0
            for n in dict.fromkeys(names):
                if c == 1 or c is None and self.mem.get(n) != v:
                    self.mem[n] = v if c == 1 else None
            if op == "RST" and a0[0] in ("T", "ST") and c != 0:
                self._acc[a0[1]] = 0.0 if c == 1 else None
            return
        if op in ("PLS", "PLF") and isinstance(a0, tuple):
            prev = self._edge((k,), c)
            self.mem[a0[1]] = k_rise(prev, c) if op == "PLS" else k_rise(k_not(prev), k_not(c))
            return
        if op == "FF" and isinstance(a0, tuple):
            r = k_rise(self._edge((k,), c), c)
            if r != 0:
                self.mem[a0[1]] = k_not(self._bit(a0)) if r == 1 else None
            return
        f, pulse = base_func(op)
        rep = not pulse and self._edge((k, 0), c) == 1 and self._acc_op(k)
        go = k_rise(self._edge((k,), c), c) if pulse else c
        if go == 0:
            return
        w, _, ok = self.L.effects(k)
        if not ok or rep:              # สะสมทุก scan: ค่าขึ้นกับเวลา scan จริง จึงไม่รู้
            for n in w:
                self.mem[n] = None
            return
        for n, v in self._compute(f, args, w).items():
            v = w16(v)
            self.mem[n] = v if go == 1 or self.mem.get(n) == v else None

    def _acc_op(self, k) -> bool:
        from .static import is_accumulating
        return is_accumulating(self.L, k)

    def _compute(self, f, args, w) -> dict:
        if f in WIDE_FUNC:
            return self._compute_wide(f[1:], args, w)
        val = self._word
        if f in ("INC", "DEC"):
            v = val(args[0])
            return spread(args[0], w, None if v is None else v + (1 if f == "INC" else -1))
        if f == "MOV":
            return spread(args[1], w, val(args[0]))
        if f in ("BCD", "BIN"):
            return spread(args[1], w, (to_bcd if f == "BCD" else from_bcd)(val(args[0]), 4))
        if f == "FMOV":
            v = val(args[0])
            return {n: v for n in w}
        if f == "BMOV":
            src = word_name(args[0])
            return dict(zip(w, [self.get(shift(src, j)) for j in range(len(w))]))
        if f in ARITH:
            a, b = (val(args[0]), val(args[1])) if len(args) == 3 else (val(args[1]), val(args[0]))
            if a is None or b is None or f == "/" and b == 0:
                return {n: None for n in w}
            if f in "+-":
                return spread(args[-1], w, a + b if f == "+" else a - b)
            if f == "*":
                p = a * b
                return {w[0]: p & 0xFFFF, w[1]: p >> 16}
            q, r = divide(a, b)
            return {w[0]: q, w[1]: r}
        return {n: None for n in w}

    def _compute_wide(self, f, args, w) -> dict:
        """คำสั่ง 32 บิต → ค่าแต่ละ word (ตัวล่างก่อน)."""
        none = {n: None for n in w}
        v = [self._wide(a) for a in args]
        if f in ("INC", "DEC"):
            r = None if v[0] is None else v[0] + (1 if f == "INC" else -1)
        elif f == "MOV":
            r = v[0]
        elif f in ("BCD", "BIN"):
            r = (to_bcd if f == "BCD" else from_bcd)(v[0], 8)
        else:
            a, b = v[:2] if len(args) == 3 else (v[1], v[0])
            if a is None or b is None or f == "/" and b == 0:
                return none
            if f == "/":
                q, m = divide(a, b)
                r = (q & 0xFFFFFFFF) | (m & 0xFFFFFFFF) << 32
            else:
                r = a * b if f == "*" else a + b if f == "+" else a - b
        return spread(args[-1], w, r)

    def _timer(self, a0, args, c, dt, unit):
        name, ret = a0[1], a0[0] == "ST"
        preset = self._word(args[1]) if len(args) > 1 else None
        s, n = bit_name(a0), word_name(a0)
        if name not in self._acc:                  # เริ่มจากค่าที่วัดได้ (ถ้ามี)
            v = self.mem.get(n)
            self._acc[name] = None if v is None else v * unit
        was, self._was[name] = self._was.get(name, c), c
        if c is None:
            self._acc[name] = None
        elif c == 0:
            if not ret:
                self._acc[name] = 0.0
        elif self._acc[name] is not None and was == 1:
            self._acc[name] += dt
        acc = self._acc[name]
        if acc is None or preset is None:
            self.mem[n] = self.mem[s] = None
            return
        tn = min(int(acc / unit + 1e-6), max(preset, 0))
        self.mem[n] = tn
        if c == 1:
            self.mem[s] = int(tn >= preset)
        elif not ret:
            self.mem[s] = 0

    def _counter(self, k, a0, args, c):
        preset = self._word(args[1]) if len(args) > 1 else None
        s, n = bit_name(a0), word_name(a0)
        r = k_rise(self._edge((k,), c), c)
        v = self.mem.get(n)
        if r is None:
            v = None
        elif r == 1 and v is not None and preset is not None and v < preset:
            v += 1
        self.mem[n] = v
        self.mem[s] = None if v is None or preset is None else int(v >= preset)

    # ---------- อธิบายวงจร ----------
    def eval(self, node: Node | None):
        if node is None:
            return 1
        if node.kind == "leaf":
            return self.cv.get(node.i)
        if node.kind == "edge":
            return self.cv.get(node.i)
        vals = [self.eval(x) for x in node.kids]
        if node.kind == "not":
            return k_not(vals[0]) if vals else 1
        out = vals[0]
        for v in vals[1:]:
            out = (k_and if node.kind == "and" else k_or)(out, v)
        return out

    def blockers(self, node: Node | None, want: int = 1) -> list[int]:
        """หน้าสัมผัสที่ทำให้วงจรไม่เป็นค่า want ในขณะนี้ (want=1: ตัวที่ตัดวงจร, want=0: ตัวที่จ่ายไฟ)."""
        if node is None or self.eval(node) == want:
            return []
        if node.kind in ("leaf", "edge"):
            return [node.i]
        if node.kind == "not":
            return self.blockers(node.kids[0], 1 - want) if node.kids else []
        out = []
        for x in node.kids:
            out += self.blockers(x, want)
        return list(dict.fromkeys(out))
