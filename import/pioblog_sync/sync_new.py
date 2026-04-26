"""Orchestrate sync of new posts + classification of holes."""
from __future__ import annotations
import sys
from pathlib import Path

import frontmatter
import pytz

from pioblog_sync.config import POSTS_DIR, ASSETS_DIR, TIMEZONE
from pioblog_sync.classifier import classify, MsgType
from pioblog_sync.entities import entities_to_markdown
from pioblog_sync.converter import build_body, build_post_filename, rewrite_pioblog_links
from pioblog_sync.media import download_media_for_post
from pioblog_sync.llm import generate_title_subtitle
from pioblog_sync.state import State
from pioblog_sync.existing import ExistingPost

# Ensure import/ is on sys.path so `from lib.slugify_ru import ...` works.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.slugify_ru import slugify_ru  # noqa: E402


TZ = pytz.timezone(TIMEZONE)


def _slug_for_message(text: str, telegram_id: int) -> str:
    """Generate slug from first words of text + telegram_id."""
    first_line = text.strip().split("\n", 1)[0] if text else ""
    base = slugify_ru(first_line)[:60] or f"pioblog-{telegram_id}"
    return f"{base}-{telegram_id}"


def _format_poll(poll) -> str:
    """Static snapshot of poll results as markdown."""
    q = poll.poll.question
    results = poll.results
    total = (results.total_voters or 0) if results else 0
    lines = [f"**Опрос:** {q}", ""]
    answers = poll.poll.answers
    if results and results.results:
        for ans, res in zip(answers, results.results):
            pct = (res.voters * 100 // total) if total else 0
            lines.append(f"- {ans.text} — {pct}% ({res.voters} голосов)")
    else:
        for ans in answers:
            lines.append(f"- {ans.text}")
    return "\n".join(lines)


async def import_message_group(client, messages: list, msg_type: MsgType,
                               existing: dict, state: State) -> Path | None:
    """Import a group of messages (single or album) as one Jekyll post.

    Returns path of created file, or None if skipped.
    """
    primary = messages[0]
    text = primary.text or ""
    body_md = entities_to_markdown(text, primary.entities or [])

    # Date in MSK
    tg_date_msk = primary.date.astimezone(TZ)

    # Slug
    slug = _slug_for_message(text, primary.id)

    # Forward marker
    if msg_type == MsgType.FORWARDED and primary.forward:
        try:
            from_chan = primary.forward.chat.username if primary.forward.chat else None
            marker = f"_↻ переслано из @{from_chan}_\n\n" if from_chan else "_↻ переслано_\n\n"
            body_md = marker + body_md
        except Exception:
            body_md = "_↻ переслано_\n\n" + body_md

    # Poll -> static snapshot
    polls_md: list[str] = []
    if msg_type == MsgType.POLL:
        polls_md.append(_format_poll(primary))

    # Download media
    media = await download_media_for_post(client, messages, slug)

    # Rewrite pioblog links
    body_md = rewrite_pioblog_links(body_md, existing)

    # LLM title/subtitle
    ts = generate_title_subtitle(body_md)

    # Build full body
    full_body = build_body(
        body_md=body_md,
        photos=media["photos"],
        videos=media["videos"],
        voices=media["voices"],
        polls=polls_md,
        telegram_id=primary.id,
    )

    # Frontmatter
    post = frontmatter.Post(content=full_body)
    post.metadata["layout"] = "post"
    post.metadata["title"] = ts.title or "(медиа)"
    post.metadata["date"] = tg_date_msk.strftime("%Y-%m-%d %H:%M:%S %z")
    if ts.subtitle:
        post.metadata["subtitle"] = ts.subtitle
    if media["photos"]:
        post.metadata["thumbnail-img"] = media["photos"][0]
    post.metadata["telegram_id"] = primary.id
    post.metadata["telegram_url"] = f"https://t.me/pioblog/{primary.id}"

    # Write file
    fname = build_post_filename(
        tg_date_msk, slug.rsplit(f"-{primary.id}", 1)[0], primary.id
    )
    target = POSTS_DIR / fname
    target.write_text(frontmatter.dumps(post), encoding="utf-8")

    # Mark all member ids as imported
    for m in messages:
        state.set_status(m.id, "imported")
    if primary.grouped_id:
        state.set_album_group(str(primary.grouped_id), [m.id for m in messages])

    return target
