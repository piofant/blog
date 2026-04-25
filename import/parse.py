"""Orchestrator: dump → staging/."""
from __future__ import annotations
import re
import yaml
from pathlib import Path
from datetime import date
from lib import config as cfg
from lib.config import SUBTITLE_MAX_CHARS
from lib.html_parser import parse_dump
from lib.transform import (
    extract_title, html_to_markdown, rewrite_pioblog_links, extract_hashtags,
)
from lib.slugify_ru import slugify_ru
from lib.media import extract_media, copy_media, render_media_markdown, MediaKind
from lib.post import Post, render_post_file
from lib.series import detect_series_marker, group_series
from lib.dedup import match_existing_posts


def _build_slug(title: str, post_date: date, tg_id: int) -> str:
    base = slugify_ru(title, max_length=50)
    if not base:
        base = f"post"
    return f"{post_date.isoformat()}-{base}-{tg_id}"


def _strip_title_from_body(body_md: str, title: str) -> str:
    """If the body's first non-empty line is (or embeds) the title, drop it.

    Title comes from the plain-text decoding of the first TG line, while
    body_md keeps markdown (links as [text](url), bold as **x**, etc).

    Two cases worth distinguishing:
    * Title equals the whole first line — drop the line, body keeps line 2+
    * Title is a *prefix* of the first line (because TITLE_MAX_CHARS truncated
      a long sentence) — keep only the suffix on line 1. Otherwise we lose
      "сделать меня счастливым…" / "редактуры. Лайфстайл, …" / etc.
    """
    if not body_md.strip():
        return body_md
    lines = body_md.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        first_text = _markdown_to_plain(line)
        title_text = _markdown_to_plain(title)
        if not title_text:
            break
        if first_text == title_text:
            return "\n".join(lines[i + 1:]).lstrip("\n")
        if first_text.startswith(title_text):
            # Truncated title — keep the suffix in body. We need to slice the
            # ORIGINAL markdown line by char count. The plain-text title and
            # markdown line align character-by-character only when there is
            # no inline markup before the cut, but the typical case is plain
            # text + maybe a trailing link. Slice by plain-text length and
            # walk markdown to the same position.
            suffix_md = _slice_markdown_after_plain_prefix(line, title_text)
            if suffix_md is None:
                # markdown alignment failed (decoration before truncation
                # point). Conservatively drop the line — same as before.
                return "\n".join(lines[i + 1:]).lstrip("\n")
            tail = "\n".join(lines[i + 1:])
            if suffix_md and tail:
                return suffix_md + "\n" + tail.lstrip("\n")
            return (suffix_md or "") + ("\n" + tail.lstrip("\n") if tail else "")
        break
    return body_md


def _slice_markdown_after_plain_prefix(md_line: str, plain_prefix: str) -> str | None:
    """Return the part of ``md_line`` whose plain text comes after ``plain_prefix``.

    Walks the markdown char-by-char, skipping ``*`` / ``_`` / ``\`` / ``~`` /
    backtick decoration and link/image syntax — collecting the same plain
    sequence the title was derived from. Returns the remaining markdown when
    it has consumed ``len(plain_prefix)`` plain chars. Returns ``None`` if the
    plain prefix doesn't align (e.g., heading marker before truncation).
    """
    consumed = 0
    i = 0
    n = len(md_line)
    target = len(plain_prefix)
    while i < n and consumed < target:
        ch = md_line[i]
        if ch in "*_`~":
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            consumed += 1
            continue
        if ch == "[":
            # markdown link [text](url) — consume only the text
            close = md_line.find("](", i)
            if close == -1:
                return None
            text = md_line[i + 1:close]
            url_close = md_line.find(")", close + 2)
            if url_close == -1:
                return None
            if consumed + len(text) <= target:
                consumed += len(text)
                i = url_close + 1
                continue
            # truncation falls inside the link text — too messy, bail out
            return None
        i += 1
        consumed += 1
    if consumed < target:
        return None
    # skip whitespace immediately after the prefix
    while i < n and md_line[i] in " \t":
        i += 1
    return md_line[i:]


def _extract_subtitle_and_body(body_md: str, title: str) -> tuple[str | None, str]:
    """Split body_md into (subtitle, remaining_body).

    - First non-empty line (after title-strip) → subtitle (stripped of
      markdown decoration), up to SUBTITLE_MAX_CHARS.
    - That same line is then removed from the body, so the rendered post
      page doesn't echo the subtitle immediately below its title.
    - Returns (None, original_body) if there is no meaningful line to use.
    """
    remainder = _strip_title_from_body(body_md, title)
    stripped = remainder.lstrip("\n")
    if not stripped.strip():
        # Title-strip already left the body empty — there's nothing more to
        # split off. Revert: keep the full body so the post isn't blank.
        return None, body_md
    first_line, _, rest = stripped.partition("\n")
    plain = _markdown_to_plain(first_line)
    if not plain:
        return None, remainder
    truncated = False
    if len(plain) > SUBTITLE_MAX_CHARS:
        plain = plain[:SUBTITLE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",.;: ")
        truncated = True
    has_links = bool(re.search(r"!?\[[^\]]+\]\([^)]+\)", first_line))
    new_body = rest.lstrip("\n")
    # If consuming the line as subtitle would empty the body, OR the line
    # carries inline links / got truncated, keep it in the body. The
    # subtitle still acts as a clean plain-text preview for cards.
    if has_links or truncated or not new_body.strip():
        return plain, remainder
    return plain, new_body


def _markdown_to_plain(s: str) -> str:
    """Drop markdown decoration from a short line for frontmatter display."""
    # [text](url) → text
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    # ![alt](url) → alt (fallback "")
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", s)
    # strip heading markers, list bullets, blockquotes, code fences, emphasis
    s = re.sub(r"^[#>\-*]+\s*", "", s)
    s = re.sub(r"[*_`~]", "", s)
    # bare [section-heading] → section-heading (TG author convention)
    s = re.sub(r"\[([^\[\]]+)\]", r"\1", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _slug_to_url(slug: str) -> str:
    """Jekyll permalink format is /:title-:year-:month-:day/.
    Our filename is YYYY-MM-DD-title-tgid.md; Jekyll strips the date
    prefix and uses the rest as :title, resulting in /title-tgid-YYYY-MM-DD/.
    """
    # slug = "YYYY-MM-DD-title-tgid"
    assert len(slug) >= 11 and slug[4] == "-" and slug[7] == "-" and slug[10] == "-"
    date_part = slug[:10]
    title_part = slug[11:]
    return f"/blog/{title_part}-{date_part}/"


def main(id_map: dict[int, str] | None = None,
         existing_posts_dir: Path | None = None):
    cfg.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    cfg.STAGING_POSTS.mkdir(parents=True, exist_ok=True)
    cfg.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    raw = parse_dump(cfg.DUMP_DIR / "messages.html")

    # album merge: TG Desktop marks album continuation messages with
    # the "joined" CSS class. Merge each follower into its preceding head:
    # - the head keeps text + title, absorbs follower media
    # - the follower is dropped from the post list
    # - the follower's tg_id maps to the head's URL (so any t.me/pioblog/{follower}
    #   links from elsewhere resolve to the head post)
    pre: list[dict] = []
    absorbed_map: dict[int, int] = {}  # follower_id → head_id
    for m in raw:
        if m.get("is_album_follower") and pre:
            head = pre[-1]
            head.setdefault("album_follower_tags", []).append(m["msg_tag"])
            absorbed_map[m["id"]] = head["id"]
            continue
        title = extract_title(m["text_html"], fallback_date=m["date"])
        marker = detect_series_marker(title)
        pre.append({**m, "title": title, "marker": marker})

    # series groups
    groups = group_series(pre)
    series_map: dict[int, tuple[str, int, int]] = {}  # tg_id → (series_id, part, total)
    series_data: dict[str, dict] = {}
    for g in groups:
        first = g["parts"][0]
        sid = slugify_ru(first["title"], max_length=50) or f"series-{first['id']}"
        series_data[sid] = {
            "title": first["title"],
            "total": g["total"],
            "parts": [],
        }
        for i, part in enumerate(g["parts"], start=1):
            series_map[part["id"]] = (sid, i, g["total"])

    # build link_map: id_map is authoritative; generated slugs fill in the rest
    id_map = id_map or {}
    link_map: dict[int, str] = dict(id_map)

    # second pass: generate slugs, register in link_map ONLY for non-existing posts
    posts: list[tuple[dict, Post]] = []
    for m in pre:
        if m["id"] in id_map:
            m["slug"] = None  # flag: do not write, do not copy media
            continue
        slug = _build_slug(m["title"], m["date"].date(), m["id"])
        link_map[m["id"]] = _slug_to_url(slug)
        m["slug"] = slug

    # also route any absorbed follower ids to their head's URL
    for follower_id, head_id in absorbed_map.items():
        if head_id in link_map:
            link_map[follower_id] = link_map[head_id]

    # third pass: transform + copy media + assemble Post (skip existing posts)
    for m in pre:
        if m["slug"] is None:
            continue  # existing post — left untouched, already mapped via id_map
        body_html = m["text_html"]
        body_md = html_to_markdown(body_html)
        body_md = rewrite_pioblog_links(body_md, link_map)
        tags = extract_hashtags(body_html)

        # Split title (line 1) and subtitle (line 2) out of the body so
        # home-feed cards don't echo them and so the post page doesn't
        # repeat the title-subtitle pair right above its own content.
        subtitle, body_md = _extract_subtitle_and_body(body_md, m["title"])

        # media from head + any absorbed album followers
        media_items = extract_media(m["msg_tag"])
        for follower_tag in m.get("album_follower_tags", []):
            media_items.extend(extract_media(follower_tag))
        thumbnail = None
        media_md_blocks: list[str] = []
        for idx, item in enumerate(media_items):
            r = copy_media(item, cfg.DUMP_DIR, cfg.STAGING_DIR, cfg.BACKUP_DIR,
                           slug=m["slug"], tg_id=m["id"])
            if item.kind == MediaKind.PHOTO and thumbnail is None and r.in_staging:
                thumbnail = f"{cfg.SITE_BASEURL}/assets/img/posts/{m['slug']}/{r.staging_path.name}"
            media_md_blocks.append(render_media_markdown(r, slug=m["slug"], tg_id=m["id"]))

        if media_md_blocks:
            body_md = (body_md + "\n\n" + "\n\n".join(media_md_blocks)).strip()

        sinfo = series_map.get(m["id"])
        post = Post(
            telegram_id=m["id"],
            telegram_url=f"https://t.me/pioblog/{m['id']}",
            date=m["date"],
            title=m["title"],
            subtitle=subtitle,
            slug=m["slug"],
            tags=tags,
            body_md=body_md,
            thumbnail=thumbnail,
            series_id=sinfo[0] if sinfo else None,
            series_part=sinfo[1] if sinfo else None,
            series_total=sinfo[2] if sinfo else None,
        )
        posts.append((m, post))

    # write posts
    for m, post in posts:
        (cfg.STAGING_POSTS / f"{post.slug}.md").write_text(
            render_post_file(post), encoding="utf-8"
        )

    # write _data/series.yml
    if series_data:
        cfg.STAGING_DATA.mkdir(parents=True, exist_ok=True)
        # fill in parts after slugs generated
        for m, post in posts:
            if post.series_id:
                series_data[post.series_id]["parts"].append({
                    "part": post.series_part,
                    "telegram_id": post.telegram_id,
                    "permalink": _slug_to_url(post.slug),
                    "title": post.title,
                    "date": post.date.isoformat(),
                })
        for sid in series_data:
            series_data[sid]["parts"].sort(key=lambda p: p["part"])
        (cfg.STAGING_DATA / "series.yml").write_text(
            yaml.dump(series_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        # write landing pages
        cfg.STAGING_SERIES.mkdir(parents=True, exist_ok=True)
        for sid, sd in series_data.items():
            (cfg.STAGING_SERIES / f"{sid}.md").write_text(
                f"---\nlayout: series\ntitle: \"{sd['title']}\"\n"
                f"series_id: {sid}\npermalink: /series/{sid}/\n---\n",
                encoding="utf-8",
            )

    print(f"Parsed {len(posts)} posts → {cfg.STAGING_POSTS}")
    if series_data:
        print(f"Detected {len(series_data)} series")


if __name__ == "__main__":
    # load id_map.yml if present
    id_map_path = Path(__file__).parent / "id_map.yml"
    id_map: dict[int, str] = {}
    if id_map_path.exists():
        raw = yaml.safe_load(id_map_path.read_text(encoding="utf-8")) or {}
        id_map = {int(k): v for k, v in raw.items()}
    main(id_map=id_map, existing_posts_dir=Path(__file__).resolve().parents[1] / "_posts")
