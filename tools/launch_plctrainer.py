"""ตัวเริ่มโปรแกรมสำหรับ PyInstaller (plc_game.main ใช้ relative import จึงรันเป็นสคริปต์ตรง ๆ ไม่ได้)."""
import sys

from plc_game.main import main

if __name__ == "__main__":
    sys.exit(main())
