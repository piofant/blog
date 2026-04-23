"""Extract and copy TG media references from a message tag."""
from __future__ import annotations
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from bs4 import Tag


class MediaKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    ROUND_VIDEO = "round_video"
    VOICE = "voice"
    FILE = "file"


@dataclass
class MediaItem:
    kind: MediaKind
    rel_path: str          # path inside dump, relative to export root
    declared_mb: float | None = None  # as declared in HTML (for routing hints)
    orig_filename: str | None = None  # for file attachments


def _declared_mb(wrap: Tag) -> float | None:
    """Parse '5.0 MB' / '235 MB' / '12:34, 45.0 MB' from video_file_extra."""
    status = wrap.find("div", class_="status")
    if not status:
        return None
    txt = status.get_text()
    m = re.search(r"(\d+(?:\.\d+)?)\s*MB", txt, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*KB", txt, re.IGNORECASE)
    if m:
        return float(m.group(1)) / 1024
    return None


def extract_media(msg: Tag) -> list[MediaItem]:
    out: list[MediaItem] = []
    # photos
    for a in msg.find_all("a", class_="photo_wrap"):
        href = a.get("href", "")
        if href and "_thumb" not in href:
            out.append(MediaItem(MediaKind.PHOTO, href))
    # videos
    for a in msg.find_all("a", class_="video_file_wrap"):
        href = a.get("href", "")
        if href:
            out.append(MediaItem(MediaKind.VIDEO, href, declared_mb=_declared_mb(a)))
    # round videos (video messages)
    for a in msg.find_all("a", class_="round_video_message"):
        href = a.get("href", "")
        if href:
            out.append(MediaItem(MediaKind.ROUND_VIDEO, href, declared_mb=_declared_mb(a)))
    # voice
    for a in msg.find_all("a", class_="voice_message"):
        href = a.get("href", "")
        if href:
            out.append(MediaItem(MediaKind.VOICE, href))
    # files (generic attachments)
    for a in msg.find_all("a", class_="file_wrap"):
        href = a.get("href", "")
        if href:
            orig = a.find("div", class_="title")
            fn = orig.get_text().strip() if orig else Path(href).name
            out.append(MediaItem(MediaKind.FILE, href, declared_mb=_declared_mb(a), orig_filename=fn))
    return out
