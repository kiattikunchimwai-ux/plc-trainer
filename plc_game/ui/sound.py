"""เสียงประกอบ: ตรวจผ่าน / ไม่ผ่าน / ออด — สร้างไฟล์ WAV เองครั้งแรก (assets/sounds) ไม่ต้องมีไฟล์เสียงภายนอก."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .. import paths

SOUND_DIR = paths.cache_dir() / "sounds"
RATE = 22050

# (ความถี่ Hz, ระยะเวลา s) ต่อโน้ต — 0 Hz = เงียบ
TONES = {
    "pass": [(660, .09), (880, .09), (1320, .22)],
    "fail": [(392, .16), (0, .04), (277, .32)],
    "click": [(1800, .015)],
    "buzzer": [(440, .35)],
    "start": [(988, .07), (1318, .10)],
}


def _write_wav(path: Path, notes) -> None:
    frames = bytearray()
    for f, dur in notes:
        n = int(RATE * dur)
        for i in range(n):
            env = min(1.0, i / 200, (n - i) / 400)          # กันเสียงแตกตอนเริ่ม/จบโน้ต
            v = 0.0 if f == 0 else env * (0.55 * math.sin(2 * math.pi * f * i / RATE)
                                          + 0.15 * math.sin(4 * math.pi * f * i / RATE))
            frames += struct.pack("<h", int(v * 32767 * 0.6))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def ensure_files() -> dict[str, Path]:
    out = {}
    for name, notes in TONES.items():
        p = SOUND_DIR / f"{name}.wav"
        if not p.exists():
            _write_wav(p, notes)
        out[name] = p
    return out


class Sounds:
    """play(name) แบบไม่บล็อก; ปิดเสียงได้ด้วย enabled = False."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.played: list[str] = []          # สำหรับทดสอบ
        self._fx = {}
        try:
            self.files = ensure_files()
        except OSError:
            self.files = {}
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            for name, p in self.files.items():
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(str(p)))
                fx.setVolume(0.6)
                self._fx[name] = fx
        except Exception:                    # ไม่มี QtMultimedia → ใช้ winsound
            self._fx = {}

    def play(self, name: str) -> None:
        if not self.enabled or name not in self.files:
            return
        self.played.append(name)
        fx = self._fx.get(name)
        if fx is not None:
            fx.play()
            return
        try:
            import winsound
            winsound.PlaySound(str(self.files[name]), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass
