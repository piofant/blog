import pytest
from datetime import datetime
from pathlib import Path
from pioblog_sync.audit import find_unrewritten_links
from pioblog_sync.existing import ExistingPost


def _existing(id_, slug, date):
    return ExistingPost(
        telegram_id=id_, slug=slug, date=date, path=Path("/x.md"),
        title="t", subtitle=None, thumbnail=None,
    )


def test_find_unrewritten_pioblog_links():
    body = "see https://t.me/pioblog/100 and [also](https://t.me/pioblog/200)"
    idx = {
        100: _existing(100, "old-100", datetime(2022, 1, 1)),
        200: _existing(200, "old-200", datetime(2023, 5, 1)),
        300: _existing(300, "skip-300", datetime(2024, 1, 1)),
    }
    found = find_unrewritten_links(body, idx)
    assert sorted(found) == [100, 200]


def test_no_unrewritten_when_already_internal():
    body = "see [past](/blog/old-100-2022-01-01/) here"
    idx = {100: _existing(100, "old-100", datetime(2022, 1, 1))}
    found = find_unrewritten_links(body, idx)
    assert found == []


def test_skip_unknown_pioblog_ids():
    body = "see https://t.me/pioblog/999"
    idx = {100: _existing(100, "old-100", datetime(2022, 1, 1))}
    found = find_unrewritten_links(body, idx)
    assert found == []  # 999 not imported, leave as-is
