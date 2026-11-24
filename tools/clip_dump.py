"""อ่านข้อมูลทุก format ในคลิปบอร์ด Windows (อ่านอย่างเดียว) — ใช้ดูว่า GX Works3 คัดลอก ladder เป็นรูปแบบไหน.

    .venv\\Scripts\\python.exe tools\\clip_dump.py <โฟลเดอร์ผลลัพธ์>
"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

u, k = ctypes.windll.user32, ctypes.windll.kernel32
u.GetClipboardData.restype = wintypes.HANDLE
u.GetClipboardData.argtypes = [wintypes.UINT]
k.GlobalLock.restype = ctypes.c_void_p
k.GlobalLock.argtypes = [wintypes.HGLOBAL]
k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
k.GlobalSize.restype = ctypes.c_size_t
k.GlobalSize.argtypes = [wintypes.HGLOBAL]
NOT_MEMORY = {2, 3, 9, 14, 0x82, 0x83, 0x8E}        # handle ของรูป/palette ไม่ใช่หน่วยความจำ


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    if not u.OpenClipboard(None):
        print("เปิดคลิปบอร์ดไม่ได้")
        return 1
    try:
        f = 0
        while f := u.EnumClipboardFormats(f):
            buf = ctypes.create_unicode_buffer(256)
            u.GetClipboardFormatNameW(f, buf, 256)
            name, data = buf.value or f"std{f}", b""
            h = None if f in NOT_MEMORY else u.GetClipboardData(f)
            if h and (p := k.GlobalLock(h)):
                data = ctypes.string_at(p, k.GlobalSize(h))
                k.GlobalUnlock(h)
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
            (out / f"{f}_{safe}.bin").write_bytes(data)
            print(f, name, len(data), data[:80])
    finally:
        u.CloseClipboard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
