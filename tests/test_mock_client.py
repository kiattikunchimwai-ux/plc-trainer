import pytest

from plc_game.plc import PLCError
from plc_game.plc.mock_client import MockPLC


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def plc():
    clock = FakeClock()
    p = MockPLC(clock=clock, auto_scan=False)
    p.connect()
    p.clock = clock
    return p


def test_requires_connect():
    with pytest.raises(PLCError):
        MockPLC(auto_scan=False).read_bits("X0", 1)


def test_self_holding_and_stop(plc):
    plc.write_bits("X0", [1]); plc.scan()
    assert plc.read_bits("Y0", 1) == [1]
    plc.write_bits("X0", [0]); plc.scan()
    assert plc.read_bits("Y0", 1) == [1], "ต้องค้างหลังปล่อย Start"
    plc.write_bits("X1", [1]); plc.scan()
    assert plc.read_bits("Y0", 1) == [0]


def test_timer_3s(plc):
    plc.write_bits("X0", [1]); plc.scan()
    plc.clock.t = 2.9; plc.scan()
    assert plc.read_bits("Y1", 1) == [0]
    assert plc.read_words("TN0", 1) == [29]
    plc.clock.t = 3.0; plc.scan()
    assert plc.read_bits("TS0", 1) == [1]
    assert plc.read_bits("Y1", 1) == [1]


def test_counter_rising_edges_and_reset(plc):
    for _ in range(5):
        plc.write_bits("X2", [1]); plc.scan(); plc.scan()   # ค้างหลายสแกน นับครั้งเดียว
        plc.write_bits("X2", [0]); plc.scan()
    assert plc.read_words("CN0", 1) == [5]
    assert plc.read_bits("Y2", 1) == [1]
    plc.write_bits("X3", [1]); plc.scan()
    assert plc.read_words("CN0", 1) == [0]
    assert plc.read_bits("Y2", 1) == [0]


def test_batch_read_octal_range(plc):
    plc.write_bits("X7", [1, 1])     # X7 และ X10
    assert plc.read_bits("X6", 3) == [0, 1, 1]
