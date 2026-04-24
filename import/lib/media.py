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


from lib.config import VIDEO_EMBED_THRESHOLD_BYTES, FILE_EMBED_THRESHOLD_BYTES


@dataclass
class MediaCopyResult:
    item: MediaItem
    in_staging: bool        # copied to assets under staging_dir?
    embed: bool             # render as TG-embed iframe instead of inline?
    staging_path: Path | None   # absolute path in staging
    backup_path: Path | None    # absolute path in backup


_SUBDIRS = {
    MediaKind.PHOTO: ("img", "posts"),
    MediaKind.VIDEO: ("video", "posts"),
    MediaKind.ROUND_VIDEO: ("video", "posts"),
    MediaKind.VOICE: ("audio", "posts"),
    MediaKind.FILE: ("files", "posts"),
}


def copy_media(
    item: MediaItem,
    dump_dir: Path,
    staging_dir: Path,
    backup_dir: Path,
    slug: str,
    tg_id: int,
) -> MediaCopyResult:
    src = dump_dir / item.rel_path
    actual_size = src.stat().st_size if src.exists() else 0

    should_embed = False
    if item.kind == MediaKind.VIDEO:
        should_embed = actual_size >= VIDEO_EMBED_THRESHOLD_BYTES
    elif item.kind == MediaKind.FILE:
        should_embed = actual_size >= FILE_EMBED_THRESHOLD_BYTES

    # backup ALL videos + files (offline copy, outside repo)
    backup_path = None
    if item.kind in (MediaKind.VIDEO, MediaKind.FILE):
        bdir = backup_dir / slug
        bdir.mkdir(parents=True, exist_ok=True)
        backup_path = bdir / src.name
        if src.exists():
            shutil.copy2(src, backup_path)

    if should_embed:
        return MediaCopyResult(item, in_staging=False, embed=True,
                               staging_path=None, backup_path=backup_path)

    sub = _SUBDIRS[item.kind]
    dest_dir = staging_dir / "assets" / sub[0] / sub[1] / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.exists():
        shutil.copy2(src, dest)
    return MediaCopyResult(item, in_staging=True, embed=False,
                           staging_path=dest, backup_path=backup_path)


def render_media_markdown(r: MediaCopyResult, slug: str, tg_id: int) -> str:
    """Produce the Markdown/HTML fragment to embed this media in a post.

    Paths are emitted with the site baseurl prefix because Jekyll is served
    under /blog/ and kramdown does not process Liquid inside markdown images.
    """
    from lib.config import SITE_BASEURL
    base = SITE_BASEURL
    kind = r.item.kind
    if kind == MediaKind.PHOTO:
        fname = r.staging_path.name
        return f"![]({base}/assets/img/posts/{slug}/{fname})"
    if kind == MediaKind.VIDEO:
        if r.embed:
            return (
                f'<script async src="https://telegram.org/js/telegram-widget.js?22"\n'
                f'        data-telegram-post="pioblog/{tg_id}" data-width="100%"></script>\n\n'
                f'[Оригинал в Telegram →](https://t.me/pioblog/{tg_id})'
            )
        fname = r.staging_path.name
        return (
            f'<video controls preload="metadata" style="width:100%;max-width:620px">\n'
            f'  <source src="{base}/assets/video/posts/{slug}/{fname}" type="video/mp4">\n'
            f'</video>\n\n'
            f'[Оригинал в Telegram →](https://t.me/pioblog/{tg_id})'
        )
    if kind == MediaKind.ROUND_VIDEO:
        fname = r.staging_path.name
        return (
            f'<video controls preload="metadata" style="width:240px;border-radius:50%">\n'
            f'  <source src="{base}/assets/video/posts/{slug}/{fname}" type="video/mp4">\n'
            f'</video>'
        )
    if kind == MediaKind.VOICE:
        fname = r.staging_path.name
        return f'<audio controls src="{base}/assets/audio/posts/{slug}/{fname}"></audio>'
    if kind == MediaKind.FILE:
        if r.embed:
            return f'📎 [Файл в Telegram →](https://t.me/pioblog/{tg_id})'
        fname = r.staging_path.name
        name = r.item.orig_filename or fname
        return f'📎 [{name}]({base}/assets/files/posts/{slug}/{fname})'
    raise ValueError(f"Unknown kind {kind}")
