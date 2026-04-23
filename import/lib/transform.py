"""HTML → Markdown + title extraction + link rewriting."""
from __future__ import annotations
import re
from datetime import datetime
from bs4 import BeautifulSoup
from lib.config import TITLE_MAX_CHARS, RU_MONTHS


def _plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # replace <br> with newline so first-line split works
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup.get_text()


def _truncate_at_word(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    cut = s[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip()


def extract_title(text_html: str, fallback_date: datetime | None = None) -> str:
    plain = _plain_text(text_html)
    first = plain.split("\n", 1)[0].strip()
    # strip lines that are empty OR only emoji/punct (no letters or digits)
    if not re.search(r"[\w]", first):
        if fallback_date is None:
            return ""
        m = RU_MONTHS[fallback_date.month]
        return f"Запись от {fallback_date.day} {m} {fallback_date.year}"
    return _truncate_at_word(first, TITLE_MAX_CHARS)


from markdownify import markdownify as _md
from bs4 import NavigableString


def _preprocess_hashtags(html: str) -> str:
    """Replace TG hashtag anchors with plain text #tag."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        onclick = a.get("onclick", "")
        if "ShowHashtag" in onclick:
            tag_text = a.get_text().strip()
            a.replace_with(NavigableString(tag_text))
    return str(soup)


def html_to_markdown(html: str) -> str:
    """Convert TG message HTML → Markdown."""
    if not html:
        return ""
    html = _preprocess_hashtags(html)
    md = _md(
        html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"],
    )
    # markdownify leaves excessive blank lines; collapse 3+
    md = re.sub(r"\n{3,}", "\n\n", md)
    # markdownify uses trailing double-space for <br>; strip trailing whitespace per line
    md = "\n".join(line.rstrip() for line in md.split("\n"))
    return md.strip()


def rewrite_pioblog_links(md: str, link_map: dict[int, str]) -> str:
    """Replace t.me/pioblog/N links with local permalinks where known."""
    pattern = re.compile(r"https?://t\.me/pioblog/(\d+)")
    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        return link_map.get(n, m.group(0))
    return pattern.sub(repl, md)


def extract_hashtags(text_html: str) -> list[str]:
    """Extract hashtag names from TG ShowHashtag anchors, preserving order, deduped."""
    soup = BeautifulSoup(text_html, "html.parser")
    seen: list[str] = []
    for a in soup.find_all("a"):
        onclick = a.get("onclick", "")
        m = re.search(r'ShowHashtag\(&quot;([^&]+)&quot;\)', onclick) \
            or re.search(r'ShowHashtag\("([^"]+)"\)', onclick)
        if m:
            tag = m.group(1)
            if tag not in seen:
                seen.append(tag)
    return seen
