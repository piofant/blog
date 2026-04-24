"""Post dataclass and frontmatter writer."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    telegram_id: int
    telegram_url: str
    date: datetime
    title: str
    slug: str
    tags: list[str]
    body_md: str
    subtitle: str | None = None
    thumbnail: str | None = None
    series_id: str | None = None
    series_part: int | None = None
    series_total: int | None = None


def _escape_yaml_string(s: str) -> str:
    # double-quoted: backslash-escape backslashes and double quotes
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _format_date(dt: datetime) -> str:
    # Jekyll-friendly: 2020-08-18 13:00:00 +0300
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def render_post_file(p: Post) -> str:
    lines = ["---", "layout: post",
             f'title: "{_escape_yaml_string(p.title)}"',
             f"date: {_format_date(p.date)}"]
    if p.subtitle:
        lines.append(f'subtitle: "{_escape_yaml_string(p.subtitle)}"')
    if p.tags:
        lines.append("tags: [" + ", ".join(p.tags) + "]")
    if p.thumbnail:
        lines.append(f"thumbnail-img: {p.thumbnail}")
    lines.append(f"telegram_id: {p.telegram_id}")
    lines.append(f"telegram_url: {p.telegram_url}")
    if p.series_id:
        lines.append(f"series_id: {p.series_id}")
        lines.append(f"series_part: {p.series_part}")
        lines.append(f"series_total: {p.series_total}")
    lines.append("---")
    lines.append("")
    lines.append(p.body_md)
    lines.append("")
    return "\n".join(lines)
