"""ธีม "เกมฝึก" ทันสมัย: พื้นน้ำเงินเข้ม, การ์ดมุมมน, accent ไล่สี cyan→blue, สีสถานะสด.
ชื่อตัวแปรคงเดิม (BG_PANEL, ACCENT, ...) เพื่อให้โค้ดเก่าใช้ต่อได้."""
# i18n: skip-file  (ไทยในไฟล์นี้เป็นแค่คอมเมนต์ใน stylesheet)

# ---------- พื้นผิว ----------
BG_CANVAS = "#111722"     # พื้นที่ผัง
BG_APP = "#141A24"        # พื้นหลังโปรแกรม
BG_PANEL = "#1E2633"      # การ์ด / แผง
BG_PANEL_DARK = "#171E2A" # แผงด้านใน
CARD = BG_PANEL
CARD_HI = "#263043"       # การ์ดตอน hover
BG_INPUT = "#0F141D"
BORDER = "#2B3546"
TEXT = "#E8EDF5"
TEXT_DIM = "#93A0B5"

# ---------- accent / สถานะ ----------
ACCENT = "#3B82F6"
ACCENT2 = "#22D3EE"
SUCCESS = "#22C55E"
WARN = "#F59E0B"
DANGER = "#EF4444"
RADIUS = 10

GRID_MAJOR = "#1F2A3A"
GRID_MINOR = "#18202D"

# สีสัญญาณบนกราฟ
SIGNAL_COLORS = {
    "X": "#38D9F5",   # input
    "Y": "#4ADE80",   # output
    "M": "#FACC15",   # internal relay
    "TS": "#FB923C",  # timer contact
    "CS": "#E879F9",  # counter contact
    "TN": "#FB923C",
    "CN": "#E879F9",
}

# Segoe UI ก่อน → ตัวเลขเป็นอารบิกเสมอ; ข้อความไทยจะ fallback ไป Leelawadee UI / Tahoma
FONT_FAMILY = "'Segoe UI', 'Leelawadee UI', Tahoma"
GRAD = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT})"


def make_qss(scale: float = 1.0) -> str:
    """สร้าง stylesheet; scale > 1 = โหมดตัวใหญ่ (โปรเจกเตอร์)."""
    fs, fs_s, fs_l = round(10 * scale, 1), round(8.5 * scale, 1), round(12 * scale, 1)
    return f"""
* {{ font-family: {FONT_FAMILY}; font-size: {fs}pt; color: {TEXT}; }}
QMainWindow, QWidget {{ background: {BG_APP}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QToolTip {{ background: {BG_PANEL}; color: {TEXT}; border: 1px solid {ACCENT}; border-radius: 6px; padding: 6px; }}

/* ----- แถบบน ----- */
QFrame#TopBar {{ background: {BG_PANEL_DARK}; border-bottom: 1px solid {BORDER}; }}
QLabel#Logo {{ font-size: {fs_l}pt; font-weight: bold; color: white; padding: 0 6px; }}
QLabel#DocName {{ color: {TEXT_DIM}; }}
QFrame#Pill {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}
QToolButton#Seg {{ border-radius: 14px; padding: 4px 14px; background: transparent; border: none; font-weight: bold; }}
QToolButton#Seg:checked {{ background: {GRAD}; color: white; }}
QLabel#Online {{ border-radius: 10px; padding: 2px 10px; font-weight: bold; color: white; }}

/* ----- Ribbon ----- */
QTabWidget#Ribbon::pane {{ background: {BG_APP}; border: none; border-bottom: 1px solid {BORDER}; }}
QTabWidget#Ribbon QTabBar::tab {{
    background: transparent; color: {TEXT_DIM}; padding: 5px 16px; margin: 4px 2px 2px 2px;
    border-radius: 13px; border: none;
}}
QTabWidget#Ribbon QTabBar::tab:hover {{ background: {BG_PANEL}; color: {TEXT}; }}
QTabWidget#Ribbon QTabBar::tab:selected {{ background: {GRAD}; color: white; font-weight: bold; }}
QFrame#RibbonGroup {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; margin: 4px 3px; }}
QFrame#RibbonGroup QLabel {{ color: {TEXT}; }}
QLabel#RibbonGroupTitle {{ color: {TEXT_DIM}; font-size: {fs_s}pt; background: transparent; padding: 0 0 2px 0; }}

/* ----- ปุ่ม ----- */
QPushButton, QToolButton {{
    background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background: #2F3B52; border-color: {ACCENT2}; }}
QPushButton:pressed, QToolButton:pressed, QPushButton:checked, QToolButton:checked {{
    background: {GRAD}; color: white; border-color: {ACCENT};
}}
QPushButton:disabled, QToolButton:disabled {{ color: #586378; background: {BG_PANEL_DARK}; }}
QPushButton#Primary {{ background: {GRAD}; color: white; font-weight: bold; border: none; }}
QPushButton#Primary:hover {{ border: 1px solid white; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; padding: 4px 8px; border-radius: 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT2}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {BG_PANEL}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; }}

/* ----- แถบไอคอน + แผงข้าง ----- */
QFrame#ActivityBar {{ background: {BG_PANEL_DARK}; border: none; }}
QFrame#ActivityBar[side="left"] {{ border-right: 1px solid {BORDER}; }}
QFrame#ActivityBar[side="right"] {{ border-left: 1px solid {BORDER}; }}
QToolButton#Activity {{
    background: transparent; border: none; border-radius: 10px; font-size: {round(15 * scale)}pt;
    min-width: 40px; min-height: 40px; max-width: 40px; max-height: 40px; padding: 0;
}}
QToolButton#Activity:hover {{ background: {BG_PANEL}; }}
QToolButton#Activity:checked {{ background: {BG_PANEL}; border-left: 3px solid {ACCENT2}; }}
QFrame#SidePane {{ background: {BG_PANEL_DARK}; border: none; }}
QLabel#PaneTitle {{ font-weight: bold; font-size: {fs_s}pt; color: {TEXT_DIM}; letter-spacing: 1px; padding: 8px 10px; }}
QToolButton#PaneClose {{ background: transparent; border: none; color: {TEXT_DIM}; padding: 2px 8px; }}
QToolButton#PaneClose:hover {{ color: white; background: {BG_PANEL}; }}

/* ----- การ์ด / กลุ่ม ----- */
QFrame#Card {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}
QGroupBox {{
    background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    margin-top: 16px; padding: 10px 6px 6px 6px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT2}; font-weight: bold; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px; border: 1px solid #5B6880; background: {BG_INPUT}; border-radius: 4px;
}}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT2}; }}
QTreeWidget, QTableWidget, QListWidget {{
    background: {BG_PANEL_DARK}; border: none; alternate-background-color: {BG_PANEL};
}}
QHeaderView::section {{ background: {BG_PANEL}; border: none; border-bottom: 1px solid {BORDER}; padding: 4px; color: {TEXT_DIM}; }}
QProgressBar {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px; text-align: center; min-height: 18px; }}
QProgressBar::chunk {{ background: {GRAD}; border-radius: 7px; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {BG_PANEL_DARK}; color: {TEXT_DIM}; padding: 4px 8px; }}

/* ----- พื้นที่ผัง ----- */
QTabWidget#Space::pane {{ border: none; background: {BG_CANVAS}; }}
QTabWidget#Space QTabBar::tab {{
    background: transparent; color: {TEXT_DIM}; padding: 4px 18px; margin: 3px 2px; border-radius: 11px;
}}
QTabWidget#Space QTabBar::tab:selected {{ background: {BG_PANEL}; color: {TEXT}; font-weight: bold; }}
QFrame#Floating {{ background: rgba(30, 38, 51, 225); border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Floating QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 4px 8px; }}
QFrame#Floating QToolButton:hover {{ background: {CARD_HI}; }}
QFrame#Floating QToolButton:checked {{ background: {GRAD}; }}
QLabel#Banner {{
    background: {BG_PANEL}; color: #FFE58A; font-size: {fs_l}pt; padding: 10px 16px;
    border: 1px solid {BORDER}; border-left: 5px solid {ACCENT2}; border-radius: {RADIUS}px; margin: 6px;
}}

/* ----- บรรทัดคำสั่ง ----- */
QFrame#CmdBar {{ background: {BG_PANEL_DARK}; border-top: 1px solid {BORDER}; }}
QPlainTextEdit#CmdHistory {{
    background: {BG_INPUT}; color: {TEXT_DIM}; border: none; border-radius: 0; font-family: Consolas, {FONT_FAMILY};
}}
QLineEdit#CmdInput {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 8px; font-family: Consolas, {FONT_FAMILY}; }}
QLabel#CmdPrompt {{ color: {ACCENT2}; padding: 0 6px; font-family: Consolas; font-weight: bold; }}

/* ----- Status bar ----- */
QStatusBar {{ background: {BG_PANEL_DARK}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QToolButton {{ padding: 1px 10px; margin: 2px 1px; border-radius: 9px; font-size: {fs_s}pt; font-weight: bold; }}
QStatusBar QLabel {{ color: {TEXT_DIM}; padding: 0 6px; }}

QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #38445A; min-height: 24px; border-radius: 4px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #38445A; min-width: 24px; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QMenu {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QDialog {{ background: {BG_APP}; }}
"""


QSS = make_qss()
LARGE_SCALE = 1.35


def color_for(name: str) -> str:
    for p in ("TS", "TN", "CS", "CN", "X", "Y", "M"):
        if name.startswith(p):
            return SIGNAL_COLORS[p]
    return TEXT
