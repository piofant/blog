"""Index of existing _posts/*.md by telegram_id."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date as date_cls
from pathlib import Path
import re

import frontmatter


SLUG_FROM_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")


@dataclass
class ExistingPost:
    telegram_id: int
    slug: str
    date: datetime
    path: Path
    title: str
    subtitle: str | None
    thumbnail: str | None

    def permalink(self) -> str:
        """Match _config.yml: /:title-:year-:month-:day/ with /blog prefix."""
        d = self.date.strftime("%Y-%m-%d")
        return f"/blog/{self.slug}-{d}/"


def _coerce_date(value, fallback_str: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date_cls):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.split(" +")[0].replace(" ", "T"))
        except ValueError:
            pass
    return datetime.fromisoformat(fallback_str)


def build_index(posts_dir: Path) -> dict[int, ExistingPost]:
    """Scan _posts/ for .md files with telegram_id; return id -> ExistingPost."""
    out: dict[int, ExistingPost] = {}
    for p in sorted(posts_dir.glob("*.md")):
        if p.name.startswith("_"):
            continue
        try:
            post = frontmatter.load(str(p))
        except Exception:
            continue
        tg_id = post.metadata.get("telegram_id")
        if tg_id is None:
            continue

        m = SLUG_FROM_FILENAME.match(p.name)
        if not m:
            continue
        date_str, slug = m.group(1), m.group(2)

        fm_date = post.metadata.get("date")
        date = _coerce_date(fm_date, date_str)

        out[int(tg_id)] = ExistingPost(
            telegram_id=int(tg_id),
            slug=slug,
            date=date,
            path=p,
            title=str(post.metadata.get("title", "")),
            subtitle=post.metadata.get("subtitle"),
            thumbnail=post.metadata.get("thumbnail-img"),
        )
    return out
