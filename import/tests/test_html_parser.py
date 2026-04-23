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
