"""D1: ที่อยู่ไฟล์ตอนรันจาก .exe (จำลอง sys.frozen + _MEIPASS) และการคัดลอกไฟล์ตัวอย่างครั้งแรก."""
import json
import sys

from plc_game import paths


def _fake_frozen(monkeypatch, tmp_path):
    bundle, home = tmp_path / "bundle", tmp_path / "home"
    (bundle / "panels").mkdir(parents=True)
    (bundle / "levels").mkdir()
    (bundle / "panels" / "sorting.plcpanel").write_text("{}", encoding="utf-8")
    (bundle / "panels" / "ui_state.json").write_text("{}", encoding="utf-8")      # ไม่ใช่ตัวอย่าง → ไม่คัด
    (bundle / "levels" / "01_a.yaml").write_text("id: a", encoding="utf-8")
    (bundle / "levels" / "01_a.plcpanel").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PLCTRAINER_HOME", str(home))
    return bundle, home


def test_source_layout_unchanged():
    root = paths.app_root()
    assert (root / "plc_game").is_dir()
    assert paths.data_dir() == root / "panels" and paths.levels_dir() == root / "levels"
    assert paths.config_path() == root / "plc_game" / "config.yaml"
    assert paths.seed_user_dir() == []


def test_frozen_layout_and_seed(monkeypatch, tmp_path):
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    assert paths.app_root() == bundle
    assert paths.data_dir() == home / "panels" and paths.levels_dir() == home / "levels"
    assert paths.cache_dir() == home / "cache"
    copied = paths.seed_user_dir()
    assert sorted(p.name for p in copied) == ["01_a.plcpanel", "01_a.yaml", "sorting.plcpanel"]
    assert not (home / "panels" / "ui_state.json").exists()
    # ครูแก้ด่านแล้ว → เปิดโปรแกรมใหม่ต้องไม่ทับ
    (home / "levels" / "01_a.yaml").write_text("id: edited", encoding="utf-8")
    assert paths.seed_user_dir() == []
    assert (home / "levels" / "01_a.yaml").read_text(encoding="utf-8") == "id: edited"
    # config ของผู้ใช้มาก่อนของที่มากับโปรแกรม
    assert paths.config_path() == bundle / "plc_game" / "config.yaml"
    (home / "config.yaml").write_text("backend: mock", encoding="utf-8")
    assert paths.config_path() == home / "config.yaml"


# ---------------- อัปเดตด่านของผู้ใช้เมื่อเปลี่ยนเวอร์ชัน ----------------
OLD_L, NEW_L = "id: a\npanel: 01_a.plcpanel\n", "id: a\npanel: 01_a.plcpanel\nfixed: 1\n"


def _upgrade(monkeypatch, tmp_path, new_panel="{}"):
    """ผู้ใช้มีของรุ่นเก่า แล้วโปรแกรมเป็นรุ่นใหม่."""
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    (bundle / "levels" / "01_a.yaml").write_bytes(OLD_L.encode())
    paths.seed_user_dir()
    h = {"levels/01_a.yaml": [paths.content_hash(OLD_L.encode())], "levels/01_a.plcpanel": [paths.content_hash(b"{}")],
         "panels/sorting.plcpanel": [paths.content_hash(b"{}")]}
    (bundle / "plc_game").mkdir()
    (bundle / "plc_game" / "shipped_hashes.json").write_text(json.dumps(h), encoding="utf-8")
    (bundle / "levels" / "01_a.yaml").write_bytes(NEW_L.encode())
    (bundle / "levels" / "01_a.plcpanel").write_bytes(new_panel.encode())
    return bundle, home / "levels" / "01_a.yaml", home / "levels" / "01_a.plcpanel"


def test_update_untouched_level(monkeypatch, tmp_path):
    _, y, p = _upgrade(monkeypatch, tmp_path)
    y.write_bytes(OLD_L.replace("\n", "\r\n").encode())            # ต่างแค่ตัวขึ้นบรรทัด = ไม่ได้แก้
    assert paths.seed_user_dir() == []
    assert paths.update_user_files() == (["levels/01_a.yaml"], [])
    assert y.read_bytes() == NEW_L.encode() and not list(y.parent.glob("*.tmp"))
    assert paths.update_user_files() == ([], [])


def test_update_keeps_edited_level_and_tells_once(monkeypatch, tmp_path):
    bundle, y, p = _upgrade(monkeypatch, tmp_path)
    y.write_text("id: mine", encoding="utf-8")
    assert paths.update_user_files() == ([], ["levels/01_a.yaml"])
    assert paths.update_user_files() == ([], [])                  # แจ้งครั้งเดียว
    assert y.read_text(encoding="utf-8") == "id: mine"
    (bundle / "levels" / "01_a.yaml").write_text("id: newer", encoding="utf-8")
    assert paths.update_user_files() == ([], ["levels/01_a.yaml"])   # รุ่นถัดไปแจ้งใหม่


def test_level_and_its_panel_stay_together(monkeypatch, tmp_path):
    _, y, p = _upgrade(monkeypatch, tmp_path, new_panel='{"v": 2}')
    p.write_text('{"mine": 1}', encoding="utf-8")
    for _ in range(2):                                             # ครั้งที่สองก็ต้องไม่อัปเดตครึ่งเดียว
        assert paths.update_user_files()[0] == []
    assert y.read_bytes() == OLD_L.encode() and p.read_text(encoding="utf-8") == '{"mine": 1}'


def test_edited_panel_that_release_did_not_change_does_not_block(monkeypatch, tmp_path):
    _, y, p = _upgrade(monkeypatch, tmp_path)
    p.write_text('{"mine": 1}', encoding="utf-8")
    assert paths.update_user_files() == (["levels/01_a.yaml"], [])
    assert p.read_text(encoding="utf-8") == '{"mine": 1}'


def test_update_is_safe_when_manifest_or_disk_fails(monkeypatch, tmp_path):
    bundle, y, _ = _upgrade(monkeypatch, tmp_path)
    m = bundle / "plc_game" / "shipped_hashes.json"
    good = m.read_text(encoding="utf-8")
    for bad in ("{", "[]", '{"levels/01_a.yaml": 5}'):
        m.write_text(bad, encoding="utf-8")
        assert paths.update_user_files() == ([], [])
    m.write_text(good, encoding="utf-8")

    def boom(*a):
        raise PermissionError(13, "denied")
    with monkeypatch.context() as mp:
        mp.setattr(paths.os, "replace", boom)
        assert paths.update_user_files() == ([], [])
    assert y.read_bytes() == OLD_L.encode() and not list(y.parent.glob("*.tmp"))
    assert paths.update_user_files()[0] == ["levels/01_a.yaml"]


def test_update_does_nothing_from_source():
    assert paths.update_user_files() == ([], [])


# ---------------- ด่านที่ครูลบ/เปลี่ยนรหัสต้องไม่กลับมา ----------------
def test_deleted_level_stays_deleted(monkeypatch, tmp_path):
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    (bundle / "levels" / "02_b.yaml").write_text("id: b", encoding="utf-8")
    paths.seed_user_dir()
    lv = home / "levels"
    (lv / "02_b.yaml").unlink()
    (lv / "01_a.plcpanel").unlink()
    assert [p.name for p in paths.seed_user_dir()] == ["01_a.plcpanel"]       # ผังยังคัดให้เสมอ
    assert not (lv / "02_b.yaml").exists()
    (bundle / "levels" / "03_c.yaml").write_text("id: c", encoding="utf-8")   # ด่านใหม่ของรุ่นใหม่ยังได้
    assert [p.name for p in paths.seed_user_dir()] == ["03_c.yaml"]
    assert paths.seed_user_dir() == [] and not (lv / "02_b.yaml").exists()


def test_renamed_level_does_not_come_back(monkeypatch, tmp_path):
    from plc_game.levels import editor as E
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    src = paths.Path(__file__).resolve().parents[1] / "levels"
    for n in ("01_self_hold", "02_interlock"):
        (bundle / "levels" / f"{n}.yaml").write_bytes((src / f"{n}.yaml").read_bytes())
    paths.seed_user_dir()
    lv = home / "levels"
    d = E.LevelDraft.load(lv / "01_self_hold.yaml")
    d.id = "01_mine"
    assert d.save(lv).name == "01_mine.yaml" and not (lv / "01_self_hold.yaml").exists()
    assert paths.seed_user_dir() == []
    assert not (lv / "01_self_hold.yaml").exists() and (lv / "_trash").is_dir()


def test_old_user_without_record_and_lost_folder(monkeypatch, tmp_path):
    import shutil
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    (bundle / "levels" / "02_b.yaml").write_text("id: b", encoding="utf-8")
    paths.seed_user_dir()
    rec, lv = home / "seeded.json", home / "levels"
    rec.unlink()                                                 # ผู้ใช้ v1.0.0: ไม่มีบันทึก
    assert paths.seed_user_dir() == [] and rec.exists()
    (lv / "02_b.yaml").unlink()
    assert paths.seed_user_dir() == []
    for bad in ("{", "[]", '{"levels": 3}'):                     # บันทึกเสีย → ไม่ล้ม คัดให้ใหม่
        rec.write_text(bad, encoding="utf-8")
        (lv / "02_b.yaml").unlink(missing_ok=True)
        assert [p.name for p in paths.seed_user_dir()] == ["02_b.yaml"]
    shutil.rmtree(lv)                                            # โฟลเดอร์ด่านหาย → ได้ครบ
    assert sorted(p.name for p in paths.seed_user_dir()) == ["01_a.plcpanel", "01_a.yaml", "02_b.yaml"]


def test_failed_copy_is_retried(monkeypatch, tmp_path):
    bundle, home = _fake_frozen(monkeypatch, tmp_path)
    (bundle / "levels" / "02_b.yaml").write_text("id: b", encoding="utf-8")
    real = paths.shutil.copy2

    def flaky(a, b):
        if paths.Path(a).name == "02_b.yaml":
            raise PermissionError(13, "denied")
        return real(a, b)
    with monkeypatch.context() as m:
        m.setattr(paths.shutil, "copy2", flaky)
        paths.seed_user_dir()
    assert [p.name for p in paths.seed_user_dir()] == ["02_b.yaml"]
