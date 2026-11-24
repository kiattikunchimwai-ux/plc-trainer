import sys
from pywinauto import Desktop
for w in Desktop(backend='win32').windows(title=sys.argv[1]):
    for e in w.descendants():
        if e.class_name()=='Edit' and e.parent().class_name()=='ComboBox':
            if not e.is_visible(): continue
            e.set_edit_text(sys.argv[2]); print('set',e.window_text())

