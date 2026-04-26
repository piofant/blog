import pytest
from datetime import datetime
from pathlib import Path
from pioblog_sync.converter import (
    rewrite_pioblog_links, build_body, build_post_filename
)
from pioblog_sync.existing import ExistingPost


def _existing(id_, slug="foo", date=datetime(2024, 1, 1)):
    return ExistingPost(
        telegram_id=id_, slug=slug, date=date, path=Path("/x.md"),
        title="t", subtitle=None, thumbnail=None,
    )


def test_rewrite_known_pioblog_link():
    body = "see [past post](https://t.me/pioblog/100) for context"
    idx = {100: _existing(100, "old-100", datetime(2022, 5, 16))}
    out = rewrite_pioblog_links(body, idx)
    assert out == "see [past post](/blog/old-100-2022-05-16/) for context"


def test_rewrite_bare_pioblog_url():
    body = "context: <https://t.me/pioblog/100>"
    idx = {100: _existing(100, "old-100", datetime(2022, 5, 16))}
    out = rewrite_pioblog_links(body, idx)
    assert out == "context: </blog/old-100-2022-05-16/>"


def test_dont_rewrite_unknown_pioblog_link():
    body = "see [post](https://t.me/pioblog/999) here"
    idx = {100: _existing(100)}
    out = rewrite_pioblog_links(body, idx)
    assert out == "see [post](https://t.me/pioblog/999) here"


def test_dont_rewrite_other_channels():
    body = "follow [chan](https://t.me/somechannel/42)"
    idx = {}
    out = rewrite_pioblog_links(body, idx)
    assert out == body


def test_build_body_appends_telegram_link():
    body_md = "Hello world"
    out = build_body(body_md, photos=[], videos=[], voices=[], polls=[], telegram_id=42)
    assert "Hello world" in out
    assert "[Оригинал в Telegram →](https://t.me/pioblog/42)" in out
    assert out.endswith("\n")


def test_build_body_with_photos():
    body_md = "Caption text"
    out = build_body(
        body_md, photos=["/blog/assets/img/posts/foo/photo_1.jpg"],
        videos=[], voices=[], polls=[], telegram_id=1,
    )
    assert "![](/blog/assets/img/posts/foo/photo_1.jpg)" in out


def test_build_body_with_video():
    out = build_body(
        "", photos=[], videos=["/blog/assets/img/posts/foo/video_1.mp4"],
        voices=[], polls=[], telegram_id=1,
    )
    assert '<video controls src="/blog/assets/img/posts/foo/video_1.mp4"></video>' in out


def test_build_post_filename():
    fn = build_post_filename(datetime(2026, 4, 15, 14, 30), "moi-post", 425)
    assert fn == "2026-04-15-moi-post-425.md"
