import pytest
from pioblog_sync.entities import entities_to_markdown


class _FakeEntity:
    """Stand-in for telethon entity classes; class name is the type discriminator."""

    def __init__(self, offset, length, **kwargs):
        self.offset = offset
        self.length = length
        # default attrs the converter may probe
        self.url = None
        self.user_id = None
        self.language = ""
        for k, v in kwargs.items():
            setattr(self, k, v)


def _ent(cls_name, offset, length, **kwargs):
    """Dynamically create a class with the given Telegram entity name."""
    cls = type(cls_name, (_FakeEntity,), {})
    return cls(offset, length, **kwargs)


def test_no_entities():
    assert entities_to_markdown("hello world", []) == "hello world"


def test_bold():
    text = "hello world"
    e = _ent("MessageEntityBold", 0, 5)
    assert entities_to_markdown(text, [e]) == "**hello** world"


def test_italic():
    text = "hello world"
    e = _ent("MessageEntityItalic", 6, 5)
    assert entities_to_markdown(text, [e]) == "hello *world*"


def test_code():
    text = "use foo() here"
    e = _ent("MessageEntityCode", 4, 5)
    assert entities_to_markdown(text, [e]) == "use `foo()` here"


def test_text_url():
    text = "see Google"
    e = _ent("MessageEntityTextUrl", 4, 6, url="https://google.com")
    assert entities_to_markdown(text, [e]) == "see [Google](https://google.com)"


def test_url_inline():
    text = "go https://x.com now"
    e = _ent("MessageEntityUrl", 3, 13)
    assert entities_to_markdown(text, [e]) == "go <https://x.com> now"


def test_mention():
    text = "ping @user"
    e = _ent("MessageEntityMention", 5, 5)
    assert entities_to_markdown(text, [e]) == "ping [@user](https://t.me/user)"


def test_strike():
    text = "old new"
    e = _ent("MessageEntityStrike", 0, 3)
    assert entities_to_markdown(text, [e]) == "~~old~~ new"


def test_overlapping_entities():
    text = "hello world"
    bold = _ent("MessageEntityBold", 0, 5)
    italic = _ent("MessageEntityItalic", 6, 5)
    assert entities_to_markdown(text, [bold, italic]) == "**hello** *world*"


def test_unicode_offsets():
    """Telegram entity offsets are UTF-16 code units, not Python str chars."""
    # Russian: 'привет мир' — Cyrillic letters are BMP single units in UTF-16.
    text = "привет мир"
    e = _ent("MessageEntityBold", 0, 6)  # 'привет'
    assert entities_to_markdown(text, [e]) == "**привет** мир"
