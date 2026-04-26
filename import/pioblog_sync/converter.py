"""Convert TG message -> Jekyll Post: body assembly + link rewriting."""
from __future__ import annotations
import re
from datetime import datetime

from pioblog_sync.existing import ExistingPost


PIOBLOG_LINK = re.compile(r"https://t\.me/pioblog/(\d+)")


def rewrite_pioblog_links(body: str, existing: dict[int, ExistingPost]) -> str:
    """Replace t.me/pioblog/<N> with internal /blog/<slug>/ when N is imported."""
    def _sub(m: re.Match) -> str:
        tg_id = int(m.group(1))
        post = existing.get(tg_id)
        if post is None:
            return m.group(0)
        return post.permalink()
    return PIOBLOG_LINK.sub(_sub, body)


def build_body(body_md: str, photos: list[str], videos: list[str],
               voices: list[str], polls: list[str], telegram_id: int) -> str:
    """Compose final markdown body with media + footer."""
    chunks: list[str] = []
    if body_md.strip():
        chunks.append(body_md.strip())
    for p in photos:
        chunks.append(f"![]({p})")
    for v in videos:
        chunks.append(f'<video controls src="{v}"></video>')
    for vo in voices:
        chunks.append(f'<audio controls src="{vo}"></audio>')
    for poll_md in polls:
        chunks.append(poll_md)
    chunks.append(f"[Оригинал в Telegram →](https://t.me/pioblog/{telegram_id})")
    return "\n\n".join(chunks) + "\n"


def build_post_filename(date: datetime, slug: str, telegram_id: int) -> str:
    """YYYY-MM-DD-<slug>-<id>.md"""
    return f"{date.strftime('%Y-%m-%d')}-{slug}-{telegram_id}.md"
