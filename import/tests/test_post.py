from datetime import datetime, timezone, timedelta
from lib.post import Post, render_post_file


def test_render_post_with_full_frontmatter():
    p = Post(
        telegram_id=14,
        telegram_url="https://t.me/pioblog/14",
        date=datetime(2020, 8, 18, 13, 0, 0, tzinfo=timezone(timedelta(hours=3))),
        title="Заголовок",
        slug="2020-08-18-zagolovok-14",
        tags=["whois", "intro"],
        body_md="Первая строка\n\nАбзац два.",
        thumbnail="/assets/img/posts/2020-08-18-zagolovok-14/photo_1.jpg",
    )
    out = render_post_file(p)
    assert out.startswith("---\n")
    assert 'title: "Заголовок"' in out
    assert "date: 2020-08-18 13:00:00 +0300" in out
    assert "tags: [whois, intro]" in out
    assert "telegram_id: 14" in out
    assert "telegram_url: https://t.me/pioblog/14" in out
    assert "thumbnail-img: /assets/img/posts/2020-08-18-zagolovok-14/photo_1.jpg" in out
    assert "Первая строка" in out


def test_render_post_without_optional_fields():
    p = Post(
        telegram_id=5,
        telegram_url="https://t.me/pioblog/5",
        date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        title="T",
        slug="2020-01-01-t-5",
        tags=[],
        body_md="body",
    )
    out = render_post_file(p)
    assert "thumbnail-img" not in out
    assert "tags:" not in out  # empty list → skipped
    assert "series_id" not in out


def test_render_post_series_fields():
    p = Post(
        telegram_id=17,
        telegram_url="https://t.me/pioblog/17",
        date=datetime(2020, 8, 21, tzinfo=timezone.utc),
        title="Часть 1",
        slug="2020-08-21-chast-1-17",
        tags=[],
        body_md="body",
        series_id="univer-story",
        series_part=1,
        series_total=3,
    )
    out = render_post_file(p)
    assert "series_id: univer-story" in out
    assert "series_part: 1" in out
    assert "series_total: 3" in out
