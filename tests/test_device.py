import pytest

from plc_game.plc.device import device_range, parse_device


def test_octal_xy():
    d = parse_device("X10")
    assert d.kind == "X" and d.number == 8 and d.name == "X10"


def test_invalid_octal_digit():
    with pytest.raises(ValueError):
        parse_device("X8")


def test_decimal_m_and_timer_prefix():
    assert parse_device("M100").number == 100
    d = parse_device("TN3")
    assert d.kind == "TN" and d.number == 3 and not d.is_bit
    assert parse_device("ts0").kind == "TS"


def test_range_crosses_octal_boundary():
    names = [d.name for d in device_range("X6", 4)]
    assert names == ["X6", "X7", "X10", "X11"]


def test_hex_base_for_iqr():
    assert parse_device("X1F", xy_base=16).number == 31


def test_slmp_wire_name():
    from plc_game.plc.slmp_client import SLMPClient
    c = SLMPClient(xy_base=8)
    assert c._wire("X17") == "XF"     # ฐาน 8: 15 → ส่งเป็นฐาน 16 ให้ pymcprotocol
    assert c._wire("M100") == "M100"
    assert c._wire("TN0") == "TN0"
