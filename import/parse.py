"""Orchestrator: dump → staging/."""
from __future__ import annotations
import yaml
from pathlib import Path
from datetime import date
from lib import config as cfg
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

    # first pass: build minimal message dicts with titles + markers for series
    pre: list[dict] = []
    for m in raw:
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

    # third pass: transform + copy media + assemble Post (skip existing posts)
    for m in pre:
        if m["slug"] is None:
            continue  # existing post — left untouched, already mapped via id_map
        body_html = m["text_html"]
        body_md = html_to_markdown(body_html)
        body_md = rewrite_pioblog_links(body_md, link_map)
        tags = extract_hashtags(body_html)

        # media
        media_items = extract_media(m["msg_tag"])
        thumbnail = None
        media_md_blocks: list[str] = []
        for idx, item in enumerate(media_items):
            r = copy_media(item, cfg.DUMP_DIR, cfg.STAGING_DIR, cfg.BACKUP_DIR,
                           slug=m["slug"], tg_id=m["id"])
            if item.kind == MediaKind.PHOTO and thumbnail is None and r.in_staging:
                thumbnail = f"/assets/img/posts/{m['slug']}/{r.staging_path.name}"
            media_md_blocks.append(render_media_markdown(r, slug=m["slug"], tg_id=m["id"]))

        if media_md_blocks:
            body_md = (body_md + "\n\n" + "\n\n".join(media_md_blocks)).strip()

        sinfo = series_map.get(m["id"])
        post = Post(
            telegram_id=m["id"],
            telegram_url=f"https://t.me/pioblog/{m['id']}",
            date=m["date"],
            title=m["title"],
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
