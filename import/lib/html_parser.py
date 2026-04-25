"""Parse Telegram Desktop HTML export into raw message records."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Iterator
from bs4 import BeautifulSoup, Tag


def _parse_date(title: str) -> datetime:
    """'15.08.2020 10:57:36 UTC+03:00' → datetime with tz."""
    # strptime cannot parse '+03:00' format directly before 3.7 reliably; normalize
    dt_part, tz_part = title.rsplit(" UTC", 1)
    sign = 1 if tz_part[0] == "+" else -1
    hh, mm = tz_part[1:].split(":")
    from datetime import timezone, timedelta
    tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    return datetime.strptime(dt_part, "%d.%m.%Y %H:%M:%S").replace(tzinfo=tz)


_MEDIA_CLASSES = [
    "photo_wrap", "video_file_wrap", "voice_message",
    "round_video_message", "file_wrap", "sticker_wrap",
]


def _is_pure_sticker(msg: Tag) -> bool:
    """True if message has no text div AND media is only a sticker."""
    if msg.find("div", class_="text"):
        return False
    stickers = msg.find_all("a", class_="sticker_wrap")
    other_media = msg.find_all(
        "a", class_=["photo_wrap", "video_file_wrap", "voice_message",
                     "round_video_message", "file_wrap"]
    )
    return bool(stickers) and not other_media


def _is_empty(msg: Tag) -> bool:
    """True when a head message carries no text and no embeddable media.

    TG occasionally exports stub `<div class="message default">` blocks with
    neither a text div nor any of the wrapped media anchors. Importing them
    produces a post titled "Запись от …" with an empty body — useless and
    confusing on the feed. Album-followers (`joined`) are exempt: their
    media still gets absorbed into the preceding head.
    """
    if "joined" in msg.get("class", []):
        return False
    if msg.find("div", class_="text"):
        return False
    if msg.find("a", class_=_MEDIA_CLASSES):
        return False
    return True


def parse_dump(html_path: Path) -> list[dict]:
    """Parse all non-service non-pure-sticker messages."""
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    out: list[dict] = []
    for msg in soup.find_all("div", class_="message"):
        classes = msg.get("class", [])
        if "service" in classes:
            continue
        if "default" not in classes:
            continue
        if _is_pure_sticker(msg):
            continue
        if _is_empty(msg):
            continue
        mid_str = msg.get("id", "")
        if not mid_str.startswith("message"):
            continue
        mid = int(mid_str[len("message"):])
        date_div = msg.find("div", class_="date")
        if not date_div or not date_div.get("title"):
            continue
        date = _parse_date(date_div["title"])
        text_div = msg.find("div", class_="text")
        text_html = text_div.decode_contents().strip() if text_div else ""
        is_album_follower = "joined" in classes
        out.append({
            "id": mid,
            "date": date,
            "text_html": text_html,
            "msg_tag": msg,  # keep for later media extraction
            "is_album_follower": is_album_follower,
        })
    return out
