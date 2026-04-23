from pathlib import Path
from datetime import datetime, timezone, timedelta
from lib.html_parser import parse_dump

FIXTURE = Path(__file__).parent / "fixtures" / "messages_sample.html"

def test_parse_dump_returns_all_nonservice_messages():
    messages = parse_dump(FIXTURE)
    ids = [m["id"] for m in messages]
    # excludes service (11) and pure-sticker (12)
    assert ids == [10, 13, 14, 15, 16, 17, 18, 19]

def test_message_has_date_with_tz():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 10)
    assert m["date"] == datetime(2020, 8, 15, 10, 57, 36, tzinfo=timezone(timedelta(hours=3)))

def test_message_has_raw_text_html():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 10)
    assert "Первая строка поста" in m["text_html"]
    assert "<strong>жирная</strong>" in m["text_html"]

def test_message_without_text_has_empty_string():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 13)
    assert m["text_html"] == ""


import subprocess
import sys

def test_parse_script_on_fixture_produces_staging(tmp_path, monkeypatch):
    # redirect config paths via env or module reload
    from importlib import reload
    import lib.config as cfg
    monkeypatch.setattr(cfg, "DUMP_DIR", Path(__file__).parent / "fixtures_dump")
    # build a minimal fake dump
    fdump = Path(__file__).parent / "fixtures_dump"
    if not fdump.exists():
        fdump.mkdir(parents=True)
        (fdump / "messages.html").write_text(
            (Path(__file__).parent / "fixtures" / "messages_sample.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fdump / "photos").mkdir()
        (fdump / "photos" / "photo_2@18-08-2020.jpg").write_bytes(b"x" * 100)
        (fdump / "video_files").mkdir()
        (fdump / "video_files" / "video_1.mp4").write_bytes(b"\0" * (5 * 1024 * 1024))
        (fdump / "video_files" / "video_big.mp4").write_bytes(b"\0" * (30 * 1024 * 1024))
    monkeypatch.setattr(cfg, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(cfg, "STAGING_POSTS", tmp_path / "staging" / "_posts")
    monkeypatch.setattr(cfg, "STAGING_ASSETS", tmp_path / "staging" / "assets")
    monkeypatch.setattr(cfg, "STAGING_SERIES", tmp_path / "staging" / "series")
    monkeypatch.setattr(cfg, "STAGING_DATA", tmp_path / "staging" / "_data")
    monkeypatch.setattr(cfg, "BACKUP_DIR", tmp_path / "backup")
    import parse
    reload(parse)
    parse.main(id_map={}, existing_posts_dir=None)
    assert (tmp_path / "staging" / "_posts").exists()
    posts = list((tmp_path / "staging" / "_posts").glob("*.md"))
    # fixtures have 8 non-skipped messages
    assert len(posts) == 8
