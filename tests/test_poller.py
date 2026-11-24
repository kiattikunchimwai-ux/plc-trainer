"""PLCPoller: เวลาใน snapshot = เวลาที่ข้อมูลมาถึง (GX Simulator3 ตอบ SLMP เป็นช่วง ๆ ทุก ~100 ms)."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402 — ต้องเป็น QApplication: test อื่นที่รันต่อสร้าง widget

from plc_game.panel.watch import WatchBlock  # noqa: E402
from plc_game.plc.base import PLCClient  # noqa: E402
from plc_game.plc.poller import PLCPoller  # noqa: E402

WINDOW = 0.1


class BurstySim(PLCClient):
    """จำลองพฤติกรรมที่วัดได้จาก GX Simulator3: ตอบได้เฉพาะช่วงสั้น ๆ ทุก 100 ms (ในช่วงนั้นตอบ ~1 ms)."""
    name = "bursty"

    def __init__(self):
        self.t0 = time.monotonic()

    def connect(self):
        pass

    def close(self):
        pass

    @property
    def is_connected(self):
        return True

    def _serve(self):
        phase = (time.monotonic() - self.t0) % WINDOW
        if phase > 0.01:                          # นอกช่วงตอบ → รอถึงช่วงถัดไป
            time.sleep(WINDOW - phase)

    def read_bits(self, head, count):
        self._serve()
        self.last_done = time.monotonic()
        return [0] * count

    def read_words(self, head, count):
        self._serve()
        self.last_done = time.monotonic()
        return [0] * count

    def write_bits(self, head, values):
        self._serve()

    def write_words(self, head, values):
        self._serve()


def test_snapshot_time_is_arrival_time():
    app = QApplication.instance() or QApplication([])
    watch = [WatchBlock("X0", 8, True), WatchBlock("Y0", 8, True), WatchBlock("TN0", 4, False)]
    sim = BurstySim()
    p = PLCPoller(sim, poll_ms=50, watch=watch)
    got = []
    # DirectConnection: บันทึกใน thread ของ poller ทันที (ไม่ขึ้นกับความหน่วงของ event loop ตอนเครื่องยุ่ง)
    p.snapshot.connect(lambda s, t: got.append((t, sim.last_done)), Qt.DirectConnection)
    p.start()
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.002)
    p.stop()
    app.processEvents()
    got = got[2:]
    assert len(got) >= 8
    lag = [(arr - got[0][1]) - (t - got[0][0]) for t, arr in got]
    # เดิม (เวลาต้นรอบ) เพี้ยนแบบสุ่มได้ถึง ~100 ms · ตอนนี้ = เวลาที่คำขอสุดท้ายของรอบได้คำตอบ
    assert max(lag) - min(lag) < 0.01, f"เวลาเพี้ยน {max(lag) - min(lag):.3f} s"
