"""ตัวช่วยควบคุมหน้าจอ (ใช้สั่ง GX Works3 อัตโนมัติ)
พิกัดทั้งหมดอยู่ในระบบของภาพ screenshot (ย่อเหลือ 1280 กว้าง) แล้วแปลงเป็นพิกัดจริงให้เอง

  python tools/gui.py shot OUT.png                 ถ่ายทั้งจอ
  python tools/gui.py click X Y [right|double]
  python tools/gui.py type "text"
  python tools/gui.py key ctrl+n | enter | f4 ...
  python tools/gui.py windows                      รายชื่อหน้าต่าง
  python tools/gui.py focus "ชื่อหน้าต่างบางส่วน"
"""
import sys
import time

import pyautogui
from PIL import ImageGrab

pyautogui.FAILSAFE = True   # เลื่อนเมาส์ไปมุมซ้ายบนเพื่อหยุดฉุกเฉิน
pyautogui.PAUSE = 0.15
W, H = pyautogui.size()
SHOT_W = 1280
SCALE = W / SHOT_W


def real(x, y):
    return int(float(x) * SCALE), int(float(y) * SCALE)


def main(a):
    cmd = a[0]
    if cmd == "shot":
        img = ImageGrab.grab(all_screens=False)
        img = img.resize((SHOT_W, int(img.height / SCALE)))
        img.save(a[1])
        print("saved", a[1], img.size)
    elif cmd == "click":
        x, y = real(a[1], a[2])
        mode = a[3] if len(a) > 3 else ""
        if mode == "right":
            pyautogui.rightClick(x, y)
        elif mode == "double":
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        print("clicked", x, y, mode)
    elif cmd == "move":
        x, y = real(a[1], a[2])
        pyautogui.moveTo(x, y, duration=0.25)
        print("moved", x, y)
    elif cmd == "type":
        pyautogui.typewrite(a[1], interval=0.03)
        print("typed", a[1])
    elif cmd == "key":
        for combo in a[1:]:
            pyautogui.hotkey(*combo.split("+"))
            time.sleep(0.2)
        print("keys", a[1:])
    elif cmd == "windows":
        from pywinauto import Desktop
        for w in Desktop(backend="uia").windows():
            t = w.window_text()
            if t:
                r = w.rectangle()
                print(f"{t!r}  ({r.left},{r.top},{r.right},{r.bottom})")
    elif cmd == "focus":
        from pywinauto import Desktop
        for w in Desktop(backend="uia").windows():
            if a[1].lower() in w.window_text().lower():
                w.set_focus()
                print("focused", w.window_text())
                return
        print("not found")
    else:
        print(__doc__)


if __name__ == "__main__":
    # หลายคำสั่งต่อกันในโปรเซสเดียว คั่นด้วย ";;"  เช่น  focus GX ;; key alt+d ;; wait 1 ;; shot a.png
    seg, args = [], sys.argv[1:]
    for tok in args + [";;"]:
        if tok == ";;":
            if seg:
                if seg[0] == "wait":
                    time.sleep(float(seg[1]))
                else:
                    main(seg)
                    time.sleep(0.4)
            seg = []
        else:
            seg.append(tok)
