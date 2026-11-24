from plc_game.panel import DeviceSpec, PanelDoc, blocks_for, conflicts, validate_address


def test_roundtrip(tmp_path):
    doc = PanelDoc(name="ทดสอบ", devices=[
        DeviceSpec.new("pushbutton", 10, 20, address="X0", label="Start"),
        DeviceSpec.new("lamp", 100, 20, address="Y0", color="red"),
        DeviceSpec.new("conveyor", 0, 200, address="Y1", length=300),
    ])
    p = tmp_path / "a.plcpanel"
    doc.save(p)
    back = PanelDoc.load(p)
    assert back.name == "ทดสอบ"
    assert [(d.kind, d.x, d.y, d.props) for d in back.devices] == [(d.kind, d.x, d.y, d.props) for d in doc.devices]
    assert [d.id for d in back.devices] == [d.id for d in doc.devices]


def test_unknown_kind_skipped():
    doc = PanelDoc.from_json('{"version":1,"devices":[{"kind":"spaceship"},{"kind":"lamp","props":{"address":"Y0"}}]}')
    assert [d.kind for d in doc.devices] == ["lamp"]


def test_validate_prefix_and_base():
    assert validate_address("pushbutton", "x0") == (True, "X0")
    ok, msg = validate_address("pushbutton", "Y0")
    assert not ok and "X" in msg
    assert not validate_address("lamp", "Y8", xy_base=8)[0]       # ฐาน 8 ไม่มีเลข 8
    assert validate_address("lamp", "Y8", xy_base=16) == (True, "Y8")
    assert validate_address("display", "CN0") == (True, "CN0")
    assert not validate_address("display", "X0")[0]
    assert not validate_address("lamp", "")[0]


def test_conflicts_only_inputs():
    devs = [DeviceSpec.new("pushbutton", address="X0"), DeviceSpec.new("limit", address="x0"),
            DeviceSpec.new("lamp", address="Y0"), DeviceSpec.new("motor", address="Y0")]
    c = conflicts(devs)
    assert list(c) == ["X0"] and len(c["X0"]) == 2       # Output ใช้ address ซ้ำได้


def test_watch_blocks():
    b = blocks_for(["X0", "X1", "X5", "Y0", "TN0", "CN0"], max_gap=8)
    assert [(x.head, x.count, x.is_bit) for x in b] == [
        ("CN0", 1, False), ("TN0", 1, False), ("X0", 6, True), ("Y0", 1, True)]
    far = blocks_for(["M0", "M100"], max_gap=8)
    assert [(x.head, x.count) for x in far] == [("M0", 1), ("M100", 1)]


def test_watch_octal_names():
    b = blocks_for(["X7", "X10"], xy_base=8)
    assert [(x.head, x.count) for x in b] == [("X7", 2)]
