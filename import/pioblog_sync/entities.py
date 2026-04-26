"""Convert Telegram MessageEntity list -> markdown text.

Telegram entities use UTF-16 code-unit offsets. We work in UTF-16 internally,
then re-encode to UTF-8 string at the end.
"""
from __future__ import annotations
from typing import Iterable


def _wrap(name: str, ent) -> tuple[str, str]:
    """Return (open, close) markdown for an entity class name."""
    if name == "MessageEntityBold":
        return "**", "**"
    if name == "MessageEntityItalic":
        return "*", "*"
    if name == "MessageEntityCode":
        return "`", "`"
    if name == "MessageEntityPre":
        lang = getattr(ent, "language", "") or ""
        return f"\n```{lang}\n", "\n```\n"
    if name == "MessageEntityStrike":
        return "~~", "~~"
    if name == "MessageEntityUnderline":
        return "<u>", "</u>"
    if name == "MessageEntitySpoiler":
        return '<span class="spoiler">', "</span>"
    if name == "MessageEntityBlockquote":
        return "> ", ""
    return "", ""


def entities_to_markdown(text: str, entities: Iterable) -> str:
    """Apply Telegram entities (UTF-16 offsets) to plain text -> markdown."""
    if not entities:
        return text

    # Convert text to UTF-16 LE bytes for offset arithmetic
    utf16 = text.encode("utf-16-le")
    # Build list of insertions: (utf16_byte_offset, priority, insert_str)
    inserts: list[tuple[int, int, str]] = []

    for ent in entities:
        cls = ent.__class__.__name__
        start = ent.offset * 2  # UTF-16 code units -> bytes
        end = (ent.offset + ent.length) * 2

        if cls == "MessageEntityTextUrl":
            url = getattr(ent, "url", "") or ""
            inserts.append((start, 0, "["))
            inserts.append((end, 1, f"]({url})"))
        elif cls == "MessageEntityUrl":
            # Inline URL: wrap in <...>
            inserts.append((start, 0, "<"))
            inserts.append((end, 1, ">"))
        elif cls == "MessageEntityMention":
            # @username -> [text](https://t.me/username); text already includes @
            mention_bytes = utf16[start:end]
            mention = mention_bytes.decode("utf-16-le")
            handle = mention.lstrip("@")
            inserts.append((start, 0, "["))
            inserts.append((end, 1, f"](https://t.me/{handle})"))
        else:
            o, c = _wrap(cls, ent)
            if o or c:
                inserts.append((start, 0, o))
                inserts.append((end, 1, c))

    # Sort by byte offset; ties -> 'close' (priority 1) before 'open' (0) at same pos
    inserts.sort(key=lambda x: (x[0], -x[1]))

    out = bytearray()
    cursor = 0
    for offset, _, s in inserts:
        out.extend(utf16[cursor:offset])
        out.extend(s.encode("utf-16-le"))
        cursor = offset
    out.extend(utf16[cursor:])
    return out.decode("utf-16-le")
