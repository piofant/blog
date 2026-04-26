import pytest
from pathlib import Path
from datetime import datetime
from pioblog_sync.existing import build_index, ExistingPost


def test_build_index_finds_telegram_id(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "sample_post.md"
    target = posts_dir / "2024-06-07-foo-157.md"
    target.write_text(fixture.read_text(), encoding="utf-8")

    idx = build_index(posts_dir)
    assert 157 in idx
    p = idx[157]
    assert isinstance(p, ExistingPost)
    assert p.telegram_id == 157
    assert p.slug == "foo-157"
    assert p.date.isoformat().startswith("2024-06-07")
    assert p.path == target


def test_build_index_skips_underscore_files(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "_draft.md").write_text(
        "---\ntelegram_id: 99\n---\nbody", encoding="utf-8"
    )
    idx = build_index(posts_dir)
    assert 99 not in idx


def test_build_index_skips_posts_without_telegram_id(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-01-03-define-self-reflexion.md").write_text(
        "---\nlayout: post\ntitle: 'No TG'\ndate: 2022-01-03\n---\nbody",
        encoding="utf-8",
    )
    idx = build_index(posts_dir)
    assert idx == {}


def test_permalink_for_post():
    """Jekyll permalink format from _config.yml: /:title-:year-:month-:day/"""
    p = ExistingPost(
        telegram_id=157,
        slug="foo-157",
        date=datetime(2024, 6, 7, 12, 0),
        path=Path("/tmp/x.md"),
        title="Test",
        subtitle=None,
        thumbnail=None,
    )
    assert p.permalink() == "/blog/foo-157-2024-06-07/"
