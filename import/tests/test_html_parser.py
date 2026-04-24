from pathlib import Path
from datetime import datetime, timezone, timedelta
from lib.html_parser import parse_dump

FIXTURE = Path(__file__).parent / "fixtures" / "messages_sample.html"

def test_parse_dump_returns_all_nonservice_messages():
    messages = parse_dump(FIXTURE)
    ids = [m["id"] for m in messages]
    # excludes service (11) and pure-sticker (12). Includes album head (20) and
    # followers (21, 22) — those are filtered later, at album-merge time.
    assert ids == [10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]


def test_album_follower_flag_on_joined_class():
    msgs = {m["id"]: m for m in parse_dump(FIXTURE)}
    assert msgs[20]["is_album_follower"] is False  # album head
    assert msgs[21]["is_album_follower"] is True   # "joined" class
    assert msgs[22]["is_album_follower"] is True
    # regular messages are not followers
    assert msgs[10]["is_album_follower"] is False

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
    # build a fresh fake dump each run (so adding new fixture messages takes effect)
    fdump = Path(__file__).parent / "fixtures_dump"
    import shutil
    if fdump.exists():
        shutil.rmtree(fdump)
    fdump.mkdir(parents=True)
    (fdump / "messages.html").write_text(
        (Path(__file__).parent / "fixtures" / "messages_sample.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (fdump / "photos").mkdir()
    (fdump / "photos" / "photo_2@18-08-2020.jpg").write_bytes(b"x" * 100)
    for name in ("alb_1.jpg", "alb_2.jpg", "alb_3.jpg"):
        (fdump / "photos" / name).write_bytes(b"y" * 100)
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
    # 11 non-skipped messages from parse_dump; 2 of them (21, 22) are album
    # followers absorbed into the head (20), so 9 final posts.
    assert len(posts) == 9


def test_album_head_post_contains_all_follower_photos(tmp_path, monkeypatch):
    """Message 20 (head) absorbs followers 21, 22 — resulting post has 3 images."""
    from importlib import reload
    import lib.config as cfg
    import shutil
    fdump = Path(__file__).parent / "fixtures_dump"
    if fdump.exists():
        shutil.rmtree(fdump)
    fdump.mkdir(parents=True)
    (fdump / "messages.html").write_text(
        (Path(__file__).parent / "fixtures" / "messages_sample.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (fdump / "photos").mkdir()
    (fdump / "photos" / "photo_2@18-08-2020.jpg").write_bytes(b"x" * 100)
    for name in ("alb_1.jpg", "alb_2.jpg", "alb_3.jpg"):
        (fdump / "photos" / name).write_bytes(b"y" * 100)
    (fdump / "video_files").mkdir()
    (fdump / "video_files" / "video_1.mp4").write_bytes(b"\0" * (5 * 1024 * 1024))
    (fdump / "video_files" / "video_big.mp4").write_bytes(b"\0" * (30 * 1024 * 1024))

    monkeypatch.setattr(cfg, "DUMP_DIR", fdump)
    monkeypatch.setattr(cfg, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(cfg, "STAGING_POSTS", tmp_path / "staging" / "_posts")
    monkeypatch.setattr(cfg, "STAGING_ASSETS", tmp_path / "staging" / "assets")
    monkeypatch.setattr(cfg, "STAGING_SERIES", tmp_path / "staging" / "series")
    monkeypatch.setattr(cfg, "STAGING_DATA", tmp_path / "staging" / "_data")
    monkeypatch.setattr(cfg, "BACKUP_DIR", tmp_path / "backup")
    import parse
    reload(parse)
    parse.main(id_map={}, existing_posts_dir=None)

    # find the head post (id 20 — "Моя подборка фоток")
    head_post = next(p for p in (tmp_path / "staging" / "_posts").glob("*.md")
                     if "-20.md" in p.name and "podborka" in p.name.lower())
    body = head_post.read_text(encoding="utf-8")
    # all 3 album photos show up in the post body
    assert "alb_1.jpg" in body
    assert "alb_2.jpg" in body
    assert "alb_3.jpg" in body
    # follower posts are NOT emitted
    follower_posts = [p for p in (tmp_path / "staging" / "_posts").glob("*.md")
                      if "-21.md" in p.name or "-22.md" in p.name]
    assert follower_posts == []
