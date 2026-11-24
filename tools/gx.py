"""ควบคุม GX Works3 ผ่าน UI Automation (pywinauto)

  python tools/gx.py menu "Debug->Simulation->Stop Simulation"
  python tools/gx.py tree [depth]        ดูโครงสร้าง control ของหน้าต่างหลัก
  python tools/gx.py dialogs             ดูหน้าต่าง/ไดอะล็อกที่เปิดอยู่ของ GX Works3
"""
import sys
import time

from pywinauto import Application, Desktop

TITLE = r"MELSOFT GX Works3.*"


def app():
    return Application(backend="uia").connect(title_re=TITLE, timeout=10)


def main_win(a=None):
    a = a or app()
    w = a.window(title_re=TITLE)
    w.set_focus()
    return w


def menu(path: str):
    w = main_win()
    w.menu_select(path)
    print("menu ok:", path)


def tree(depth=3):
    w = main_win()
    w.print_control_identifiers(depth=int(depth))


def dialogs():
    a = app()
    for w in a.windows():
        print(repr(w.window_text()), w.element_info.control_type, w.rectangle())
    print("--- desktop top windows with GX/MELSOFT ---")
    for w in Desktop(backend="uia").windows():
        t = w.window_text()
        if any(k in t for k in ("GX", "MELSOFT", "New", "Save", "Simulator")):
            print(repr(t), w.rectangle())


def dlg(title):
    """ไดอะล็อกมาตรฐาน (#32770) หาได้ด้วย backend win32."""
    a = Application(backend="win32").connect(title=title, timeout=10)
    d = a.window(title=title)
    d.wait("exists", timeout=10)
    return d


def win32_settext(title, value, class_name="Edit", index=0):
    d = dlg(title)
    e = d.child_window(class_name=class_name, found_index=int(index))
    e.set_edit_text(value)
    print("set:", e.window_text())


def win32_press(title, button):
    d = dlg(title)
    d.child_window(title=button, class_name="Button").click()
    print("pressed", button)


def settext(title, field, value):
    d = dlg(title)
    e = d.child_window(title=field, control_type="Edit", found_index=0)
    e.set_edit_text(value)
    print("set", field, "=", e.get_value() if hasattr(e, "get_value") else value)


def press(title, button):
    d = dlg(title)
    d.child_window(title=button, control_type="Button", found_index=0).invoke()
    print("pressed", button)


def dump(title, depth=4):
    dlg(title).print_control_identifiers(depth=int(depth))


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["help"]
    if cmd == "settext":
        win32_settext(*rest)
    elif cmd == "press":
        win32_press(*rest)
    elif cmd == "dump":
        dump(*rest)
    elif cmd == "menu":
        menu(rest[0])
    elif cmd == "tree":
        tree(*rest)
    elif cmd == "dialogs":
        dialogs()
    else:
        print(__doc__)
    time.sleep(0.3)
