"""Match existing Jekyll _posts against TG messages for id_map generation."""
from __future__ import annotations
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from datetime import date


@dataclass
class Candidate:
    telegram_id: int
    post_file: Path
    permalink: str
    score: float


_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)\.md$")
_TITLE_RE = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)


def _read_post_meta(path: Path) -> tuple[date, str, str] | None:
    name = path.name
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    y, mo, d, rest = m.groups()
    post_date = date(int(y), int(mo), int(d))
    slug = rest
    content = path.read_text(encoding="utf-8")
    fm_title = _TITLE_RE.search(content)
    title = fm_title.group(1).strip() if fm_title else slug.replace("-", " ")
    return post_date, slug, title


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_existing_posts(tg_messages: list[dict], posts_dir: Path) -> list[Candidate]:
    out: list[Candidate] = []
    for post in sorted(posts_dir.glob("*.md")):
        meta = _read_post_meta(post)
        if meta is None:
            continue
        post_date, slug, post_title = meta
        best: tuple[float, dict] | None = None
        for msg in tg_messages:
            if msg["date"].date() != post_date:
                continue
            score = _similarity(msg["title"], post_title)
            if best is None or score > best[0]:
                best = (score, msg)
        if best is None or best[0] < 0.45:
            continue
        score, msg = best
        out.append(Candidate(
            telegram_id=msg["id"],
            post_file=post,
            permalink=f"/blog/{slug}/",
            score=score,
        ))
    return out
