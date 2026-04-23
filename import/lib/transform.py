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
