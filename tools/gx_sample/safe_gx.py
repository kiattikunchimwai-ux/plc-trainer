"""ส่งคีย์/คลิกเฉพาะเมื่อปลายทางเป็นโปรเซส GXW3 (ไม่ใช่ = หยุดทันที)
คำสั่งคั่นด้วย ;; : focus | type TEXT | key ctrl+s | click X Y [double] | wait S | shot FILE | windows
พิกัด click = พิกเซลในภาพ shot ล่าสุด (หน้าต่าง foreground ของ GX)"""
import ctypes, os, sys, time
import pyautogui, win32api, win32con, win32gui, win32process
from PIL import ImageGrab
ctypes.windll.shcore.SetProcessDpiAwareness(2)
pyautogui.PAUSE = 0.04
def exe(h):
    _, pid = win32process.GetWindowThreadProcessId(h)
    try:
        p = win32api.OpenProcess(0x1000, False, pid)
        return os.path.basename(win32process.GetModuleFileNameEx(p, 0)).lower() if False else os.path.basename(qname(p)).lower()
    except Exception: return '?'
def qname(p):
    buf = ctypes.create_unicode_buffer(1024); n = ctypes.c_ulong(1024)
    ctypes.windll.kernel32.QueryFullProcessImageNameW(int(p), 0, buf, ctypes.byref(n)); return buf.value
def ok(h): return exe(h) == 'gxw3.exe'
def guard():
    h = win32gui.GetForegroundWindow()
    if not ok(h): sys.exit(f'STOP: foreground is {exe(h)}')
    return h
def wins():
    out=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h) and ok(h): out.append((h,win32gui.GetWindowText(h),win32gui.GetWindowRect(h)))
    win32gui.EnumWindows(cb,None); return out
def run(a):
    c=a[0]
    if c=='windows':
        for x in wins(): print(x)
    elif c=='focus':
        ws=[x for x in wins() if x[1].startswith('MELSOFT GX Works3')]
        if not ws: sys.exit('no GX')
        ws=[x for x in ws if x[1].startswith('MELSOFT GX Works3 ')] or ws
        h=next((x[0] for x in wins() if x[1] and not x[1].startswith('MELSOFT GX Works3 ')), ws[0][0])
        if win32gui.IsIconic(h): win32gui.ShowWindow(h,9)
        t=win32api.GetCurrentThreadId()
        ft,_=win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
        ctypes.windll.user32.AttachThreadInput(t,ft,True)
        ctypes.windll.user32.BringWindowToTop(h); ctypes.windll.user32.SetForegroundWindow(h)
        ctypes.windll.user32.AttachThreadInput(t,ft,False)
        time.sleep(.5); g=guard()
        if g!=h: sys.exit(f'STOP: got {win32gui.GetWindowText(g)}')
    elif c=='type':
        for ch in a[1]:
            guard(); pyautogui.write(ch)
    elif c=='key':
        for k in a[1:]: guard(); pyautogui.hotkey(*k.split('+')); time.sleep(.15)
    elif c=='click':
        h=guard(); l,t,_,_=win32gui.GetWindowRect(h); p=(l+int(a[1]),t+int(a[2]))
        w=win32gui.GetAncestor(win32gui.WindowFromPoint(p),2)
        if not ok(w): sys.exit(f'STOP: point owned by {exe(w)}')
        (pyautogui.doubleClick if len(a)>3 else pyautogui.click)(*p)
    elif c=='wait': time.sleep(float(a[1]))
    elif c=='shot':
        h=guard(); r=win32gui.GetWindowRect(h); im=ImageGrab.grab(bbox=r,all_screens=True); im.save(a[1]); print('shot',im.size,win32gui.GetWindowText(h))
seg=[]
for tok in sys.argv[1:]+[';;']:
    if tok==';;':
        if seg: run(seg); time.sleep(.15)
        seg=[]
    else: seg.append(tok)

