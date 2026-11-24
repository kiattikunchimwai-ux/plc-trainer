"""ปล่อยโปรแกรม: tools/make_release.py (ส่วนไม่แตะไฟล์จริง) + version.json สองภาษา + merge config."""
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_release as mr  # noqa: E402
from plc_game import __version__, i18n, update  # noqa: E402

URL = "https://github.com/someone/plc-trainer/releases/latest/download/version.json"


def test_github_url_and_repo_roundtrip():
    assert update.github_update_url("someone/plc-trainer") == URL
    assert mr.repo_from_url(URL) == "someone/plc-trainer"
    assert mr.repo_from_url("https://example.com/v.json") == ""
    for bad in ("", "noslash", "a/b/c", "../x", "owner/re po"):
        with pytest.raises(ValueError):
            update.github_update_url(bad)


def test_set_update_url_keeps_comments():
    text = (ROOT / "plc_game" / "config.yaml").read_text(encoding="utf-8")
    new = mr.set_update_url(text, URL)
    assert mr.read_update_url(new) == URL
    assert new.count("update_url:") == 1 and "# เช็กเวอร์ชันใหม่" in new and "port: 5511" in new
    assert mr.read_update_url(mr.set_update_url("backend: mock\n", URL)) == URL
    assert mr.read_update_url('update_url: ""  # ปิด') == ""


def test_changelog_has_current_version():
    date, th, en = mr.changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), __version__)
    assert date and th.startswith("- ") and en.startswith("- ")
    assert "ข้อแรก" not in th                       # ตัวอย่างในคอมเมนต์ไม่ถูกนับ
    with pytest.raises(ValueError):
        mr.changelog_section("## 0.1.0\n- x\n", "9.9.9")


def test_changelog_section_boundaries():
    md = "## 2.0.0 — 2027-01-02\n### th\n- ใหม่\n### en\n- new\n\n## 1.0.0\n### th\n- เก่า\n"
    assert mr.changelog_section(md, "2.0.0") == ("2027-01-02", "- ใหม่", "- new")
    assert mr.changelog_section(md, "1.0.0") == ("", "- เก่า", "")
    assert mr.changelog_section("## 1.0.10\n- a\n## 1.0.1\n- b\n", "1.0.1")[1] == "- b"   # ไม่จับ 1.0.10


def test_version_json_parses_in_both_languages(monkeypatch):
    vj = mr.version_json("9.0.0", "someone/plc-trainer", "2027-01-02", "- ไทย\n- สอง", "- English", "z.zip", "ab", 1234)
    assert vj["url"] == "https://github.com/someone/plc-trainer/releases/tag/v9.0.0"
    data = json.loads(json.dumps(vj, ensure_ascii=False))
    monkeypatch.setattr(i18n, "_lang", "th")
    info = update.parse_info(data)
    assert (info.notes, info.date, info.size, info.newer) == ("ไทย", "2027-01-02", 1234, True)
    monkeypatch.setattr(i18n, "_lang", "en")
    assert update.parse_info(data).notes == "English"
    assert update.parse_info({"version": "1", "size": "bad"}).size == 0


def test_release_notes_and_readme():
    notes = mr.release_notes("1.2.3", "o/r", "- ไทย", "- en", "PLCTrainer-1.2.3-win64.zip", "f" * 64)
    assert "https://github.com/o/r/releases/download/v1.2.3/PLCTrainer-1.2.3-win64.zip" in notes
    assert "Run anyway" in notes and "Mitsubishi" in notes
    assert "https://github.com/o/r/releases/latest" in mr.repo_readme("o/r")


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for n, t in files.items():
            zf.writestr(n, t)


def test_zip_problems(tmp_path):
    good = {"PLCTrainer/PLCTrainer.exe": "x", "PLCTrainer/_internal/plc_game/config.yaml": f'update_url: "{URL}"\n'}
    _zip(tmp_path / "ok.zip", good)
    assert mr.zip_problems(tmp_path / "ok.zip", URL) == []
    _zip(tmp_path / "bad.zip", {**good, "PLCTrainer/_internal/plc_game/config.yaml": 'update_url: ""\n',
                                "PLCTrainer/_internal/panels/scores.json": "{}"})
    probs = mr.zip_problems(tmp_path / "bad.zip", URL)
    assert len(probs) == 2


def test_main_without_repo_refuses(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('update_url: ""\n', encoding="utf-8")
    monkeypatch.setattr(mr, "CONFIG", cfg)
    assert mr.main(["--skip-build", "--out", str(tmp_path / "out")]) == 2
    assert cfg.read_text(encoding="utf-8") == 'update_url: ""\n'          # ไม่แตะ config


def test_main_skip_build_end_to_end(monkeypatch, tmp_path):
    """--repo + --skip-build กับ dist ปลอม → ได้ไฟล์ครบและ version.json อ่านกลับได้."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("backend: mock\nupdate_url: \"\"\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    zname = f"PLCTrainer-{__version__}-win64.zip"
    _zip(dist / zname, {"PLCTrainer/PLCTrainer.exe": "x",
                        "PLCTrainer/_internal/plc_game/config.yaml": f'update_url: "{URL}"\n'})
    monkeypatch.setattr(mr, "CONFIG", cfg)
    monkeypatch.setattr(mr, "DIST", dist)
    monkeypatch.setattr(mr, "HASHES", tmp_path / "hashes.json")
    out = tmp_path / "rel"
    assert mr.main(["--repo", "someone/plc-trainer", "--skip-build", "--out", str(out)]) == 0
    assert mr.read_update_url(cfg.read_text(encoding="utf-8")) == URL and "backend: mock" in cfg.read_text(encoding="utf-8")
    d = out / f"v{__version__}"
    vj = json.loads((d / "version.json").read_text(encoding="utf-8"))
    assert vj["sha256"] == mr.sha256_of(d / zname) and vj["size"] == (d / zname).stat().st_size
    assert update.parse_info(vj).version == __version__
    assert (d / "SHA256SUMS.txt").read_text(encoding="utf-8").startswith(vj["sha256"])
    assert (out / "repo" / "README.md").exists() and (d / "RELEASE_NOTES.md").exists()
    # ครั้งที่สองไม่ต้องใส่ --repo (อ่านจาก update_url)
    assert mr.main(["--skip-build", "--out", str(out)]) == 0


def test_site_template_renders(tmp_path):
    src = ROOT / "site"
    html = mr.render_site((src / "index.html").read_text(encoding="utf-8"), "someone/plc-trainer", "1.2.3", 74_745_485)
    assert "https://github.com/someone/plc-trainer/releases/latest" in html
    assert "PLCTrainer-1.2.3-win64.zip · 75 MB" in html and "แม่แบบเว็บ" not in html
    # Facebook/LINE ต้องการลิงก์รูปแบบเต็ม
    assert '<meta property="og:image" content="https://someone.github.io/plc-trainer/img/og.png">' in html
    assert (src / "img" / "og.png").exists()
    for img in ("level1_en", "level1_th", "devices", "faultfind"):
        assert f"img/{img}.png" in html and (src / "img" / f"{img}.png").exists()
    with pytest.raises(ValueError):
        mr.render_site("__NEW_THING__", "o/r", "1", 1)
    mr.write_site(tmp_path / "repo", "o/r", "1.0.0", 1_000_000)
    assert (tmp_path / "repo" / "index.html").exists() and (tmp_path / "repo" / "img" / "devices.png").exists()


def test_load_config_merges_user_over_bundled(monkeypatch, tmp_path):
    from plc_game import main as pm
    app = tmp_path / "app"
    (app / "plc_game").mkdir(parents=True)
    (app / "plc_game" / "config.yaml").write_text(f'port: 5511\nupdate_url: "{URL}"\npoll_ms: 50\n', encoding="utf-8")
    user = tmp_path / "user.yaml"
    user.write_text('port: 6000\nupdate_url: ""\n', encoding="utf-8")       # คัดมาจากรุ่นเก่า
    monkeypatch.setattr(pm.paths, "app_root", lambda: app)
    cfg = pm.load_config(user)
    assert cfg == {"port": 6000, "update_url": URL, "poll_ms": 50}
    assert pm.load_config(app / "plc_game" / "config.yaml")["port"] == 5511


def test_record_hashes(tmp_path):
    from plc_game.paths import content_hash
    z, dst = tmp_path / "a.zip", tmp_path / "h.json"
    _zip(z, {"PLCTrainer/_internal/levels/01_a.yaml": "id: a", "PLCTrainer/_internal/panels/x.plcpanel": "{}",
             "PLCTrainer/_internal/plc_game/config.yaml": "x", "PLCTrainer/PLCTrainer.exe": "x"})
    assert mr.record_hashes(z, dst) == 2 and mr.record_hashes(z, dst) == 0
    _zip(z, {"PLCTrainer/_internal/levels/01_a.yaml": "id: b"})
    assert mr.record_hashes(z, dst) == 1                       # ของรุ่นก่อนยังอยู่
    d = json.loads(dst.read_text(encoding="utf-8"))
    assert d["levels/01_a.yaml"] == [content_hash(b"id: a"), content_hash(b"id: b")] and len(d) == 2


def test_manifest_covers_every_level_of_v1():
    d = json.loads(mr.HASHES.read_text(encoding="utf-8"))
    assert sum(k.endswith(".yaml") for k in d) >= 14 and "panels/default.plcpanel" in d
    assert mr.HASHES in [f for f, _ in __import__("build_exe").data_files()]
