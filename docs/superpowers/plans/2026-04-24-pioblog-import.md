# Pioblog → Jekyll Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Импортировать 376 сообщений Telegram-канала pioblog в Jekyll-блог с сохранением текста, медиа, хронологии, ссылок и серий — через staging pipeline с валидатором.

**Architecture:** Python HTML-парсер читает дамп Telegram Desktop → собирает `Post` объекты → пишет markdown в `import/staging/` → валидатор проверяет целостность → `promote` копирует в реальный репо → коммит батчами по годам.

**Tech Stack:** Python 3.9, BeautifulSoup4, markdownify, python-slugify, PyYAML, pytest, Make, Jekyll (существующий).

**Spec:** `docs/superpowers/specs/2026-04-24-pioblog-import-design.md`

---

## File Structure

```
import/
├── Makefile                   # parse, validate, promote, clean, test
├── requirements.txt           # bs4, markdownify, python-slugify, pyyaml, pytest
├── conftest.py                # pytest configuration (sys.path)
├── pyproject.toml             # project config
├── id_map.yml                 # hand-edited: telegram_id → existing jekyll permalink
├── parse.py                   # entrypoint: dump → staging/
├── validate.py                # entrypoint: check staging/
├── promote.py                 # entrypoint: staging → real repo
├── lib/
│   ├── __init__.py
│   ├── config.py              # constants (paths, thresholds)
│   ├── html_parser.py         # BS4 parsing of messages.html
│   ├── post.py                # Post dataclass + frontmatter writer
│   ├── slugify_ru.py          # custom slugify for cyrillic titles
│   ├── transform.py           # HTML→Markdown + link rewriting
│   ├── media.py               # photo/video/audio/file handling
│   ├── series.py              # series detection + landing page generation
│   └── dedup.py               # match existing posts → id_map candidates
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   └── messages_sample.html     # 10 synthetic messages covering all cases
    ├── test_html_parser.py
    ├── test_slugify_ru.py
    ├── test_transform.py
    ├── test_media.py
    ├── test_series.py
    └── test_dedup.py

_layouts/series.html                  # new layout for /series/{id}/
_includes/series-nav.html             # rendered at bottom of series-part posts
assets/css/overrides.css              # ADD series-nav styles
```

---

## Task 1: Project scaffold + dependencies

**Files:**
- Create: `import/requirements.txt`
- Create: `import/pyproject.toml`
- Create: `import/conftest.py`
- Create: `import/Makefile`
- Create: `import/lib/__init__.py`
- Create: `import/tests/__init__.py`
- Create: `import/tests/fixtures/messages_sample.html`
- Create: `import/lib/config.py`

- [ ] **Step 1: Write fixture file**

Create `import/tests/fixtures/messages_sample.html` with this exact content (10 synthetic messages covering all edge cases we handle):

```html
<!DOCTYPE html>
<html><body><div class="page_body chat_page">
<!-- 1: plain text -->
<div class="message default clearfix" id="message10">
  <div class="body">
    <div class="pull_right date details" title="15.08.2020 10:57:36 UTC+03:00">10:57</div>
    <div class="text">Первая строка поста<br>Вторая <strong>жирная</strong> строка с <a href="https://example.com">ссылкой</a><br>И <em>курсив</em>.<br><br><a href="" onclick="return ShowHashtag(&quot;рефлексия&quot;)">#рефлексия</a> <a href="" onclick="return ShowHashtag(&quot;whois&quot;)">#whois</a></div>
  </div>
</div>
<!-- 2: service message -->
<div class="message service" id="message11">
  <div class="body details"><div class="body">Channel photo changed</div></div>
</div>
<!-- 3: pure sticker (no text div) -->
<div class="message default clearfix" id="message12">
  <div class="body">
    <div class="pull_right date details" title="16.08.2020 11:00:00 UTC+03:00">11:00</div>
    <div class="media_wrap clearfix"><a class="sticker_wrap clearfix pull_left" href="stickers/sticker.webp"><img class="sticker" src="stickers/sticker.webp" style="width: 128px; height: 128px"/></a></div>
  </div>
</div>
<!-- 4: photo only, no text -->
<div class="message default clearfix" id="message13">
  <div class="body">
    <div class="pull_right date details" title="17.08.2020 12:00:00 UTC+03:00">12:00</div>
    <div class="media_wrap clearfix"><a class="photo_wrap clearfix pull_left" href="photos/photo_1@17-08-2020.jpg"><img class="photo" src="photos/photo_1@17-08-2020_thumb.jpg" style="width: 260px"/></a></div>
  </div>
</div>
<!-- 5: text + photo + internal pioblog link -->
<div class="message default clearfix" id="message14">
  <div class="body">
    <div class="pull_right date details" title="18.08.2020 13:00:00 UTC+03:00">13:00</div>
    <div class="text">Заголовок<br>Смотри <a href="https://t.me/pioblog/10">прошлый пост</a> и <a href="https://t.me/pioblog/999">удалённый</a>.</div>
    <div class="media_wrap clearfix"><a class="photo_wrap clearfix pull_left" href="photos/photo_2@18-08-2020.jpg"><img class="photo" src="photos/photo_2@18-08-2020_thumb.jpg"/></a></div>
  </div>
</div>
<!-- 6: small video (simulated 5MB) -->
<div class="message default clearfix" id="message15">
  <div class="body">
    <div class="pull_right date details" title="19.08.2020 14:00:00 UTC+03:00">14:00</div>
    <div class="text">Короткое видео</div>
    <div class="media_wrap clearfix"><a class="video_file_wrap clearfix pull_left" href="video_files/video_1.mp4"><div class="video_file_extra title bold">Video file</div><div class="video_file_extra status details">00:30, 5.0 MB</div></a></div>
  </div>
</div>
<!-- 7: large video (simulated 50MB) -->
<div class="message default clearfix" id="message16">
  <div class="body">
    <div class="pull_right date details" title="20.08.2020 15:00:00 UTC+03:00">15:00</div>
    <div class="text">Лекция</div>
    <div class="media_wrap clearfix"><a class="video_file_wrap clearfix pull_left" href="video_files/video_big.mp4"><div class="video_file_extra title bold">Video file</div><div class="video_file_extra status details">45:00, 50.0 MB</div></a></div>
  </div>
</div>
<!-- 8: series part 1/3 with explicit marker -->
<div class="message default clearfix" id="message17">
  <div class="body">
    <div class="pull_right date details" title="21.08.2020 10:00:00 UTC+03:00">10:00</div>
    <div class="text">Как я поступал в универ (1/3)<br>Первая часть текста.</div>
  </div>
</div>
<!-- 9: series part 2/3 -->
<div class="message default clearfix" id="message18">
  <div class="body">
    <div class="pull_right date details" title="21.08.2020 10:05:00 UTC+03:00">10:05</div>
    <div class="text">Продолжение (2/3)<br>Вторая часть.</div>
  </div>
</div>
<!-- 10: series part 3/3 -->
<div class="message default clearfix" id="message19">
  <div class="body">
    <div class="pull_right date details" title="21.08.2020 10:10:00 UTC+03:00">10:10</div>
    <div class="text">Финал (3/3)<br>Третья часть.</div>
  </div>
</div>
</div></body></html>
```

- [ ] **Step 2: Write requirements.txt**

Create `import/requirements.txt`:

```
beautifulsoup4==4.12.3
markdownify==0.11.6
python-slugify==8.0.4
PyYAML==6.0.1
pytest==8.0.0
```

- [ ] **Step 3: Write pyproject.toml**

Create `import/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 4: Write conftest.py**

Create `import/conftest.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 5: Create Makefile skeleton**

Create `import/Makefile`:

```makefile
.PHONY: help venv install test parse validate promote clean all

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "Targets: install test parse validate promote clean all"

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m pytest -v

parse:
	$(PYTHON) parse.py

validate:
	$(PYTHON) validate.py

promote:
	$(PYTHON) promote.py

clean:
	rm -rf staging/
	find . -name __pycache__ -exec rm -rf {} +

all: parse validate
```

- [ ] **Step 6: Create config.py**

Create `import/lib/config.py`:

```python
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORT_ROOT = Path(__file__).resolve().parents[1]
DUMP_DIR = REPO_ROOT / "ChatExport_2026-04-24 pioblog"
STAGING_DIR = IMPORT_ROOT / "staging"
STAGING_POSTS = STAGING_DIR / "_posts"
STAGING_ASSETS = STAGING_DIR / "assets"
STAGING_SERIES = STAGING_DIR / "series"
STAGING_DATA = STAGING_DIR / "_data"
BACKUP_DIR = Path.home() / "piofant-media"

# Thresholds
VIDEO_EMBED_THRESHOLD_BYTES = 25 * 1024 * 1024  # 25 MB
FILE_EMBED_THRESHOLD_BYTES = 25 * 1024 * 1024
TITLE_MAX_CHARS = 80

# Channel
TG_CHANNEL = "pioblog"
TG_URL_PATTERN = r"https?://t\.me/pioblog/(\d+)"

# Russian month names
RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
```

- [ ] **Step 7: Create package __init__ files**

Create empty `import/lib/__init__.py` and `import/tests/__init__.py` (just `touch`).

- [ ] **Step 8: Install and verify**

```bash
cd import && make install && .venv/bin/python -c "import bs4, markdownify, slugify, yaml, pytest; print('OK')"
```

Expected: `OK`.

- [ ] **Step 9: Commit**

```bash
cd /Users/piofant/cursor/vedulix-blog
git add import/
git commit -m "import: scaffold parser project with fixtures"
```

---

## Task 2: HTML parser — extract raw message records

**Files:**
- Create: `import/lib/html_parser.py`
- Create: `import/tests/test_html_parser.py`

- [ ] **Step 1: Write failing test**

Create `import/tests/test_html_parser.py`:

```python
from pathlib import Path
from datetime import datetime, timezone, timedelta
from lib.html_parser import parse_dump

FIXTURE = Path(__file__).parent / "fixtures" / "messages_sample.html"

def test_parse_dump_returns_all_nonservice_messages():
    messages = parse_dump(FIXTURE)
    ids = [m["id"] for m in messages]
    # excludes service (11) and pure-sticker (12)
    assert ids == [10, 13, 14, 15, 16, 17, 18, 19]

def test_message_has_date_with_tz():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 10)
    assert m["date"] == datetime(2020, 8, 15, 10, 57, 36, tzinfo=timezone(timedelta(hours=3)))

def test_message_has_raw_text_html():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 10)
    assert "Первая строка поста" in m["text_html"]
    assert "<strong>жирная</strong>" in m["text_html"]

def test_message_without_text_has_empty_string():
    m = next(x for x in parse_dump(FIXTURE) if x["id"] == 13)
    assert m["text_html"] == ""
```

- [ ] **Step 2: Run test, verify fails**

```bash
cd import && make test
```

Expected: `ModuleNotFoundError: No module named 'lib.html_parser'` or similar.

- [ ] **Step 3: Implement parser**

Create `import/lib/html_parser.py`:

```python
"""Parse Telegram Desktop HTML export into raw message records."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Iterator
from bs4 import BeautifulSoup, Tag


def _parse_date(title: str) -> datetime:
    """'15.08.2020 10:57:36 UTC+03:00' → datetime with tz."""
    # strptime cannot parse '+03:00' format directly before 3.7 reliably; normalize
    dt_part, tz_part = title.rsplit(" UTC", 1)
    sign = 1 if tz_part[0] == "+" else -1
    hh, mm = tz_part[1:].split(":")
    from datetime import timezone, timedelta
    tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    return datetime.strptime(dt_part, "%d.%m.%Y %H:%M:%S").replace(tzinfo=tz)


def _is_pure_sticker(msg: Tag) -> bool:
    """True if message has no text div AND media is only a sticker."""
    if msg.find("div", class_="text"):
        return False
    stickers = msg.find_all("a", class_="sticker_wrap")
    other_media = msg.find_all(
        "a", class_=["photo_wrap", "video_file_wrap", "voice_message",
                     "round_video_message", "file_wrap"]
    )
    return bool(stickers) and not other_media


def parse_dump(html_path: Path) -> list[dict]:
    """Parse all non-service non-pure-sticker messages."""
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    out: list[dict] = []
    for msg in soup.find_all("div", class_="message"):
        classes = msg.get("class", [])
        if "service" in classes:
            continue
        if "default" not in classes:
            continue
        if _is_pure_sticker(msg):
            continue
        mid_str = msg.get("id", "")
        if not mid_str.startswith("message"):
            continue
        mid = int(mid_str[len("message"):])
        date_div = msg.find("div", class_="date")
        if not date_div or not date_div.get("title"):
            continue
        date = _parse_date(date_div["title"])
        text_div = msg.find("div", class_="text")
        text_html = text_div.decode_contents().strip() if text_div else ""
        out.append({
            "id": mid,
            "date": date,
            "text_html": text_html,
            "msg_tag": msg,  # keep for later media extraction
        })
    return out
```

- [ ] **Step 4: Run test, verify pass**

```bash
cd import && make test
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/piofant/cursor/vedulix-blog
git add import/lib/html_parser.py import/tests/test_html_parser.py
git commit -m "import: html parser extracts non-service messages with date"
```

---

## Task 3: Slugify — cyrillic → latin slug

**Files:**
- Create: `import/lib/slugify_ru.py`
- Create: `import/tests/test_slugify_ru.py`

- [ ] **Step 1: Write failing test**

Create `import/tests/test_slugify_ru.py`:

```python
from lib.slugify_ru import slugify_ru

def test_cyrillic_transliterated():
    assert slugify_ru("Про Ingress как кусок моего детства") == "pro-ingress-kak-kusok-moego-detstva"

def test_truncation_to_50_chars_at_word_boundary():
    long = "Очень длинный заголовок про многое интересное и немного про жизнь"
    slug = slugify_ru(long, max_length=50)
    assert len(slug) <= 50
    assert not slug.endswith("-")

def test_emoji_stripped():
    assert slugify_ru("📍 Популярные посты") == "populiarnye-posty"

def test_fallback_empty():
    # only emoji/punctuation → empty
    assert slugify_ru("📍🐳!") == ""
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `import/lib/slugify_ru.py`:

```python
"""Cyrillic-aware slugifier."""
from slugify import slugify


def slugify_ru(text: str, max_length: int = 60) -> str:
    """Transliterate Russian → latin, lowercase, dash-separated."""
    return slugify(text, max_length=max_length, word_boundary=True, save_order=True)
```

- [ ] **Step 4: Run test, verify pass**

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add import/lib/slugify_ru.py import/tests/test_slugify_ru.py
git commit -m "import: slugify with cyrillic transliteration"
```

---

## Task 4: Title extraction

**Files:**
- Create: `import/lib/transform.py`
- Create: `import/tests/test_transform.py`

- [ ] **Step 1: Write failing test (title only)**

Create `import/tests/test_transform.py`:

```python
from datetime import datetime, timezone
from lib.transform import extract_title

def test_first_line_no_markup():
    assert extract_title("<p>Простой текст<br>вторая строка</p>") == "Простой текст"

def test_strips_bold_italic_but_keeps_text():
    assert extract_title("<strong>Жирный</strong> заголовок<br>остальное") == "Жирный заголовок"

def test_truncates_at_word_boundary():
    long_line = "Очень длинный заголовок с кучей слов который точно не влезет в восемьдесят символов никак"
    title = extract_title(long_line + "<br>more")
    assert len(title) <= 80
    assert not title.endswith(" ")

def test_empty_text_fallback_to_russian_date():
    dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
    assert extract_title("", fallback_date=dt) == "Запись от 15 июня 2024"

def test_only_emoji_fallback():
    dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
    assert extract_title("🐳 👀", fallback_date=dt) == "Запись от 15 июня 2024"
```

- [ ] **Step 2: Run test, verify fails**

- [ ] **Step 3: Implement extract_title**

Create `import/lib/transform.py`:

```python
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
```

- [ ] **Step 4: Run test, verify pass**

```bash
cd import && make test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add import/lib/transform.py import/tests/test_transform.py
git commit -m "import: title extraction with russian date fallback"
```

---

## Task 5: HTML → Markdown body conversion

**Files:**
- Modify: `import/lib/transform.py`
- Modify: `import/tests/test_transform.py`

- [ ] **Step 1: Append tests**

Append to `import/tests/test_transform.py`:

```python
from lib.transform import html_to_markdown

def test_bold_italic_link():
    assert html_to_markdown("<strong>жирный</strong>") == "**жирный**"
    assert html_to_markdown("<em>курсив</em>") == "*курсив*"
    assert html_to_markdown('<a href="https://x.com">link</a>') == "[link](https://x.com)"

def test_br_becomes_newline():
    assert html_to_markdown("line1<br>line2") == "line1\nline2"

def test_code_and_blockquote():
    assert html_to_markdown("<code>x</code>") == "`x`"
    assert html_to_markdown("<blockquote>quoted</blockquote>").strip().startswith(">")

def test_hashtag_link_becomes_plain_tag():
    html = '<a href="" onclick="return ShowHashtag(&quot;рефлексия&quot;)">#рефлексия</a>'
    assert html_to_markdown(html).strip() == "#рефлексия"

def test_emoji_preserved():
    assert html_to_markdown("текст 🐳 текст") == "текст 🐳 текст"

def test_preserves_external_link_with_bold_inside():
    html = '<a href="https://x.com"><strong>link</strong></a>'
    md = html_to_markdown(html)
    assert "[**link**](https://x.com)" in md or "**[link](https://x.com)**" in md
```

- [ ] **Step 2: Run, verify new tests fail**

- [ ] **Step 3: Add html_to_markdown to transform.py**

Append to `import/lib/transform.py`:

```python
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
    return md.strip()
```

- [ ] **Step 4: Run tests**

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add import/lib/transform.py import/tests/test_transform.py
git commit -m "import: html → markdown body conversion"
```

---

## Task 6: Link rewriting (t.me/pioblog/N → local permalink)

**Files:**
- Modify: `import/lib/transform.py`
- Modify: `import/tests/test_transform.py`

- [ ] **Step 1: Append tests**

```python
from lib.transform import rewrite_pioblog_links

def test_rewrite_known_link():
    link_map = {10: "/blog/first-post/", 14: "/blog/later-post/"}
    md = "Смотри [прошлый](https://t.me/pioblog/10) и [ещё](https://t.me/pioblog/14)."
    out = rewrite_pioblog_links(md, link_map)
    assert "(/blog/first-post/)" in out
    assert "(/blog/later-post/)" in out
    assert "t.me/pioblog" not in out

def test_unknown_id_preserved():
    link_map = {10: "/blog/x/"}
    md = "[удалённый](https://t.me/pioblog/999)"
    assert "https://t.me/pioblog/999" in rewrite_pioblog_links(md, link_map)

def test_preserves_other_tg_channels():
    link_map = {}
    md = "[отсюда](https://t.me/not_tldr/5)"
    assert rewrite_pioblog_links(md, link_map) == md

def test_also_rewrites_in_html_anchor_forms():
    link_map = {10: "/blog/x/"}
    md = 'Ссылка: <a href="https://t.me/pioblog/10">link</a>'
    assert "/blog/x/" in rewrite_pioblog_links(md, link_map)
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Implement rewrite_pioblog_links**

Append to `import/lib/transform.py`:

```python
def rewrite_pioblog_links(md: str, link_map: dict[int, str]) -> str:
    """Replace t.me/pioblog/N links with local permalinks where known."""
    pattern = re.compile(r"https?://t\.me/pioblog/(\d+)")
    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        return link_map.get(n, m.group(0))
    return pattern.sub(repl, md)
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/transform.py import/tests/test_transform.py
git commit -m "import: rewrite internal pioblog links via link_map"
```

---

## Task 7: Hashtag extraction for frontmatter tags

**Files:**
- Modify: `import/lib/transform.py`
- Modify: `import/tests/test_transform.py`

- [ ] **Step 1: Append tests**

```python
from lib.transform import extract_hashtags

def test_extract_multiple_hashtags():
    html = '<a onclick="return ShowHashtag(&quot;whois&quot;)">#whois</a> <a onclick="return ShowHashtag(&quot;intro&quot;)">#intro</a>'
    assert extract_hashtags(html) == ["whois", "intro"]

def test_deduplicates_preserving_order():
    html = '<a onclick="ShowHashtag(&quot;a&quot;)">#a</a> <a onclick="ShowHashtag(&quot;b&quot;)">#b</a> <a onclick="ShowHashtag(&quot;a&quot;)">#a</a>'
    assert extract_hashtags(html) == ["a", "b"]

def test_empty_when_none():
    assert extract_hashtags("<p>plain text</p>") == []
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement**

Append to `import/lib/transform.py`:

```python
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
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/transform.py import/tests/test_transform.py
git commit -m "import: extract hashtags for frontmatter tags"
```

---

## Task 8: Media extraction (photos, videos, voice, round, files)

**Files:**
- Create: `import/lib/media.py`
- Create: `import/tests/test_media.py`

- [ ] **Step 1: Write failing test**

Create `import/tests/test_media.py`:

```python
from pathlib import Path
from bs4 import BeautifulSoup
from lib.media import extract_media, MediaItem, MediaKind

FIXTURE = Path(__file__).parent / "fixtures" / "messages_sample.html"

def _msg(mid: int):
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
    return soup.find("div", id=f"message{mid}")

def test_photo_extracted_fullquality_not_thumb():
    items = extract_media(_msg(14))
    assert len(items) == 1
    assert items[0].kind == MediaKind.PHOTO
    assert items[0].rel_path == "photos/photo_2@18-08-2020.jpg"
    assert "_thumb" not in items[0].rel_path

def test_video_small_declared_size_parsed():
    items = extract_media(_msg(15))
    assert len(items) == 1
    v = items[0]
    assert v.kind == MediaKind.VIDEO
    assert v.rel_path == "video_files/video_1.mp4"
    # parser extracts declared size for routing hint (real size checked on copy)
    assert v.declared_mb == 5.0

def test_video_large_declared_50mb():
    v = extract_media(_msg(16))[0]
    assert v.declared_mb == 50.0

def test_no_media_in_text_only():
    assert extract_media(_msg(10)) == []

def test_no_media_in_photo_only_no_text():
    # message 13 has only photo → still returns it as media
    items = extract_media(_msg(13))
    assert len(items) == 1
    assert items[0].kind == MediaKind.PHOTO
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement media extraction**

Create `import/lib/media.py`:

```python
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
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/media.py import/tests/test_media.py
git commit -m "import: media extraction (photos, videos, voice, round, files)"
```

---

## Task 9: Media copying with size-based routing

**Files:**
- Modify: `import/lib/media.py`
- Modify: `import/tests/test_media.py`

- [ ] **Step 1: Append tests**

```python
import tempfile
from lib.media import copy_media, MediaCopyResult

def test_copy_small_video_goes_to_staging_and_backup(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    (dump / "video_files").mkdir(parents=True)
    f = dump / "video_files" / "v.mp4"
    f.write_bytes(b"\0" * (5 * 1024 * 1024))  # 5 MB
    item = MediaItem(MediaKind.VIDEO, "video_files/v.mp4", declared_mb=5.0)
    r = copy_media(item, dump, staging, backup, slug="my-post", tg_id=42)
    assert r.in_staging is True
    assert r.embed is False
    assert (staging / "assets" / "video" / "posts" / "my-post").exists()
    assert (backup / "my-post").exists()

def test_copy_large_video_only_backup_and_embed(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    (dump / "video_files").mkdir(parents=True)
    f = dump / "video_files" / "big.mp4"
    f.write_bytes(b"\0" * (30 * 1024 * 1024))  # 30 MB
    item = MediaItem(MediaKind.VIDEO, "video_files/big.mp4", declared_mb=30.0)
    r = copy_media(item, dump, staging, backup, slug="lecture", tg_id=100)
    assert r.in_staging is False
    assert r.embed is True
    assert not (staging / "assets" / "video" / "posts" / "lecture").exists()
    assert (backup / "lecture" / "big.mp4").exists()

def test_photo_always_copied(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    (dump / "photos").mkdir(parents=True)
    (dump / "photos" / "p.jpg").write_bytes(b"x" * 1000)
    item = MediaItem(MediaKind.PHOTO, "photos/p.jpg")
    r = copy_media(item, dump, staging, tmp_path / "backup", slug="post", tg_id=1)
    assert r.in_staging is True
    assert (staging / "assets" / "img" / "posts" / "post" / "p.jpg").exists()
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement copy_media**

Append to `import/lib/media.py`:

```python
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
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/media.py import/tests/test_media.py
git commit -m "import: media copy with size-based routing + backup"
```

---

## Task 10: Media rendering in markdown body

**Files:**
- Modify: `import/lib/media.py`
- Modify: `import/tests/test_media.py`

- [ ] **Step 1: Append tests**

```python
from lib.media import render_media_markdown

def test_render_photo():
    item = MediaItem(MediaKind.PHOTO, "photos/p.jpg")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/img/posts/post/p.jpg"), None)
    md = render_media_markdown(r, slug="post", tg_id=1)
    assert md == "![](/assets/img/posts/post/p.jpg)"

def test_render_video_selfhosted():
    item = MediaItem(MediaKind.VIDEO, "video_files/v.mp4", declared_mb=5.0)
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/video/posts/post/v.mp4"), None)
    md = render_media_markdown(r, slug="post", tg_id=10)
    assert '<video controls' in md
    assert 'src="/assets/video/posts/post/v.mp4"' in md
    assert 'https://t.me/pioblog/10' in md  # "Оригинал"

def test_render_video_embed_for_large():
    item = MediaItem(MediaKind.VIDEO, "video_files/big.mp4", declared_mb=50.0)
    r = MediaCopyResult(item, False, True, None, Path("/backup/big.mp4"))
    md = render_media_markdown(r, slug="lecture", tg_id=100)
    assert 'data-telegram-post="pioblog/100"' in md
    assert 'telegram-widget.js' in md

def test_render_voice():
    item = MediaItem(MediaKind.VOICE, "voice_messages/v.ogg")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/audio/posts/post/v.ogg"), None)
    assert '<audio controls' in render_media_markdown(r, slug="post", tg_id=1)

def test_render_file_attachment():
    item = MediaItem(MediaKind.FILE, "files/doc.pdf", orig_filename="doc.pdf")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/files/posts/post/doc.pdf"), None)
    md = render_media_markdown(r, slug="post", tg_id=1)
    assert "📎" in md
    assert "(/assets/files/posts/post/doc.pdf)" in md
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement render_media_markdown**

Append to `import/lib/media.py`:

```python
def render_media_markdown(r: MediaCopyResult, slug: str, tg_id: int) -> str:
    """Produce the Markdown/HTML fragment to embed this media in a post."""
    kind = r.item.kind
    if kind == MediaKind.PHOTO:
        fname = r.staging_path.name
        return f"![](/assets/img/posts/{slug}/{fname})"
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
            f'  <source src="/assets/video/posts/{slug}/{fname}" type="video/mp4">\n'
            f'</video>\n\n'
            f'[Оригинал в Telegram →](https://t.me/pioblog/{tg_id})'
        )
    if kind == MediaKind.ROUND_VIDEO:
        fname = r.staging_path.name
        return (
            f'<video controls preload="metadata" style="width:240px;border-radius:50%">\n'
            f'  <source src="/assets/video/posts/{slug}/{fname}" type="video/mp4">\n'
            f'</video>'
        )
    if kind == MediaKind.VOICE:
        fname = r.staging_path.name
        return f'<audio controls src="/assets/audio/posts/{slug}/{fname}"></audio>'
    if kind == MediaKind.FILE:
        if r.embed:
            return f'📎 [Файл в Telegram →](https://t.me/pioblog/{tg_id})'
        fname = r.staging_path.name
        name = r.item.orig_filename or fname
        return f'📎 [{name}](/assets/files/posts/{slug}/{fname})'
    raise ValueError(f"Unknown kind {kind}")
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/media.py import/tests/test_media.py
git commit -m "import: render media as markdown/html fragments"
```

---

## Task 11: Series detection

**Files:**
- Create: `import/lib/series.py`
- Create: `import/tests/test_series.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests/test_series.py`:

```python
from lib.series import detect_series_marker, group_series


def test_marker_parens():
    r = detect_series_marker("Заголовок (1/5)\nтекст")
    assert r == (1, 5)

def test_marker_brackets():
    assert detect_series_marker("Серия [2/3]") == (2, 3)

def test_marker_russian_chast():
    assert detect_series_marker("часть 3 из 5\nтекст") == (3, 5)

def test_marker_russian_chast_no_total():
    assert detect_series_marker("часть 2") == (2, None)

def test_no_marker():
    assert detect_series_marker("Обычный пост без маркера") is None

def test_group_series_consecutive_parts():
    msgs = [
        {"id": 100, "title": "Часть (1/3)", "marker": (1, 3)},
        {"id": 101, "title": "Часть (2/3)", "marker": (2, 3)},
        {"id": 102, "title": "Часть (3/3)", "marker": (3, 3)},
        {"id": 103, "title": "Независимый", "marker": None},
    ]
    groups = group_series(msgs)
    assert len(groups) == 1
    assert [m["id"] for m in groups[0]["parts"]] == [100, 101, 102]
    assert groups[0]["total"] == 3

def test_group_series_ignores_broken_sequence():
    msgs = [
        {"id": 100, "title": "A (1/3)", "marker": (1, 3)},
        {"id": 101, "title": "Other (1/5)", "marker": (1, 5)},  # different total
        {"id": 102, "title": "B (2/3)", "marker": (2, 3)},
    ]
    groups = group_series(msgs)
    # only the (1/5) is its own dangling single-part group? No — we require ≥2 parts to form a series
    ids = [[m["id"] for m in g["parts"]] for g in groups]
    assert ids == []  # no complete group
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement**

Create `import/lib/series.py`:

```python
"""Detect and group multi-part series in consecutive messages."""
from __future__ import annotations
import re
from typing import TypedDict


_MARKER_RES = [
    re.compile(r"\((\d+)/(\d+)\)"),
    re.compile(r"\[(\d+)/(\d+)\]"),
    re.compile(r"часть\s+(\d+)(?:\s+из\s+(\d+))?", re.IGNORECASE),
    re.compile(r"(?:^|\s)(\d+)/(\d+)(?:\s|$)"),
    re.compile(r"#часть(\d+)"),
]


def detect_series_marker(first_line_or_title: str) -> tuple[int, int | None] | None:
    """Return (part, total) or None."""
    for rx in _MARKER_RES:
        m = rx.search(first_line_or_title)
        if m:
            part = int(m.group(1))
            total = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else None
            return (part, total)
    return None


class SeriesGroup(TypedDict):
    parts: list[dict]
    total: int


def group_series(messages: list[dict]) -> list[SeriesGroup]:
    """Group messages with sequential (N/total) markers. Only complete series returned."""
    groups: list[SeriesGroup] = []
    buf: list[dict] = []
    current_total: int | None = None
    expected_next = 1

    def flush():
        nonlocal buf, current_total, expected_next
        if len(buf) >= 2 and all(m["marker"] for m in buf):
            groups.append({"parts": buf, "total": current_total or len(buf)})
        buf = []
        current_total = None
        expected_next = 1

    for m in messages:
        mk = m.get("marker")
        if mk is None:
            flush()
            continue
        part, total = mk
        if not buf:
            if part != 1:
                continue  # doesn't start a series
            buf = [m]
            current_total = total
            expected_next = 2
            continue
        if part == expected_next and (total is None or total == current_total):
            buf.append(m)
            expected_next += 1
            if current_total and expected_next > current_total:
                flush()
        else:
            flush()
            if part == 1:
                buf = [m]
                current_total = total
                expected_next = 2
    flush()
    return groups
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/series.py import/tests/test_series.py
git commit -m "import: series detection + grouping of consecutive parts"
```

---

## Task 12: Dedup with existing 15 Jekyll posts

**Files:**
- Create: `import/lib/dedup.py`
- Create: `import/tests/test_dedup.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests/test_dedup.py`:

```python
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lib.dedup import match_existing_posts, Candidate


def test_match_by_date_and_first_line(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-03-12-ingress.md").write_text(
        "---\nlayout: post\ntitle: 'Про Ingress как кусок моего детства'\n---\n\n"
        "В 2016-2019 я играл в Ingress...",
        encoding="utf-8",
    )
    tg_msgs = [
        {"id": 86, "date": datetime(2022, 3, 12, 10, 0, tzinfo=timezone.utc),
         "title": "Про Ingress как кусок моего детства"},
        {"id": 100, "date": datetime(2022, 3, 13, 10, 0, tzinfo=timezone.utc),
         "title": "Что-то другое"},
    ]
    candidates = match_existing_posts(tg_msgs, posts_dir)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.telegram_id == 86
    assert c.post_file.name == "2022-03-12-ingress.md"
    assert c.permalink == "/blog/ingress/"
    assert c.score > 0.7

def test_no_match_when_date_differs_and_title_too(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-03-12-ingress.md").write_text(
        "---\ntitle: 'Про Ingress'\n---\n\ntext", encoding="utf-8"
    )
    tg_msgs = [{"id": 99, "date": datetime(2023, 7, 1, tzinfo=timezone.utc),
                "title": "Совсем другой"}]
    assert match_existing_posts(tg_msgs, posts_dir) == []
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement dedup**

Create `import/lib/dedup.py`:

```python
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
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/dedup.py import/tests/test_dedup.py
git commit -m "import: dedup — match existing posts to TG messages by date+title"
```

---

## Task 13: Post assembly — frontmatter writer

**Files:**
- Create: `import/lib/post.py`
- Modify: `import/tests/test_transform.py` (or create `test_post.py`)

- [ ] **Step 1: Write failing test**

Create `import/tests/test_post.py`:

```python
from datetime import datetime, timezone, timedelta
from lib.post import Post, render_post_file


def test_render_post_with_full_frontmatter():
    p = Post(
        telegram_id=14,
        telegram_url="https://t.me/pioblog/14",
        date=datetime(2020, 8, 18, 13, 0, 0, tzinfo=timezone(timedelta(hours=3))),
        title="Заголовок",
        slug="2020-08-18-zagolovok-14",
        tags=["whois", "intro"],
        body_md="Первая строка\n\nАбзац два.",
        thumbnail="/assets/img/posts/2020-08-18-zagolovok-14/photo_1.jpg",
    )
    out = render_post_file(p)
    assert out.startswith("---\n")
    assert 'title: "Заголовок"' in out
    assert "date: 2020-08-18 13:00:00 +0300" in out
    assert "tags: [whois, intro]" in out
    assert "telegram_id: 14" in out
    assert "telegram_url: https://t.me/pioblog/14" in out
    assert "thumbnail-img: /assets/img/posts/2020-08-18-zagolovok-14/photo_1.jpg" in out
    assert "Первая строка" in out


def test_render_post_without_optional_fields():
    p = Post(
        telegram_id=5,
        telegram_url="https://t.me/pioblog/5",
        date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        title="T",
        slug="2020-01-01-t-5",
        tags=[],
        body_md="body",
    )
    out = render_post_file(p)
    assert "thumbnail-img" not in out
    assert "tags:" not in out  # empty list → skipped
    assert "series_id" not in out


def test_render_post_series_fields():
    p = Post(
        telegram_id=17,
        telegram_url="https://t.me/pioblog/17",
        date=datetime(2020, 8, 21, tzinfo=timezone.utc),
        title="Часть 1",
        slug="2020-08-21-chast-1-17",
        tags=[],
        body_md="body",
        series_id="univer-story",
        series_part=1,
        series_total=3,
    )
    out = render_post_file(p)
    assert "series_id: univer-story" in out
    assert "series_part: 1" in out
    assert "series_total: 3" in out
```

- [ ] **Step 2: Run, verify fail**

- [ ] **Step 3: Implement Post + renderer**

Create `import/lib/post.py`:

```python
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
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add import/lib/post.py import/tests/test_post.py
git commit -m "import: Post dataclass + frontmatter renderer"
```

---

## Task 14: End-to-end parse.py orchestrator

**Files:**
- Create: `import/parse.py`

- [ ] **Step 1: Write e2e smoke test**

Append to `import/tests/test_html_parser.py`:

```python
import subprocess
import sys
from pathlib import Path

def test_parse_script_on_fixture_produces_staging(tmp_path, monkeypatch):
    # redirect config paths via env or module reload
    from importlib import reload
    import lib.config as cfg
    monkeypatch.setattr(cfg, "DUMP_DIR", Path(__file__).parent / "fixtures_dump")
    # build a minimal fake dump
    fdump = Path(__file__).parent / "fixtures_dump"
    if not fdump.exists():
        fdump.mkdir(parents=True)
        (fdump / "messages.html").write_text(
            (Path(__file__).parent / "fixtures" / "messages_sample.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fdump / "photos").mkdir()
        (fdump / "photos" / "photo_2@18-08-2020.jpg").write_bytes(b"x" * 100)
        (fdump / "video_files").mkdir()
        (fdump / "video_files" / "video_1.mp4").write_bytes(b"\0" * (5 * 1024 * 1024))
        (fdump / "video_files" / "video_big.mp4").write_bytes(b"\0" * (30 * 1024 * 1024))
    monkeypatch.setattr(cfg, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(cfg, "STAGING_POSTS", tmp_path / "staging" / "_posts")
    monkeypatch.setattr(cfg, "STAGING_ASSETS", tmp_path / "staging" / "assets")
    monkeypatch.setattr(cfg, "STAGING_SERIES", tmp_path / "staging" / "series")
    monkeypatch.setattr(cfg, "STAGING_DATA", tmp_path / "staging" / "_data")
    monkeypatch.setattr(cfg, "BACKUP_DIR", tmp_path / "backup")
    import parse
    reload(parse)
    parse.main(id_map={}, existing_posts_dir=None)
    assert (tmp_path / "staging" / "_posts").exists()
    posts = list((tmp_path / "staging" / "_posts").glob("*.md"))
    # fixtures have 8 non-skipped messages
    assert len(posts) == 8
```

- [ ] **Step 2: Implement parse.py**

Create `import/parse.py`:

```python
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

    # build link_map: all imported + id_map
    link_map: dict[int, str] = dict(id_map or {})

    # second pass: generate slugs, register in link_map
    posts: list[tuple[dict, Post]] = []
    for m in pre:
        slug = _build_slug(m["title"], m["date"].date(), m["id"])
        link_map[m["id"]] = f"/blog/{slug}/"
        m["slug"] = slug

    # third pass: transform + copy media + assemble Post
    for m in pre:
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
                    "permalink": f"/blog/{post.slug}/",
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
```

- [ ] **Step 3: Run tests**

```bash
cd import && make test
```

Expected: all tests pass including the e2e smoke.

- [ ] **Step 4: Run parse on fixture**

```bash
cd import
# make sure fixture dump exists (was created by test)
.venv/bin/python parse.py
ls staging/_posts/ | head
```

Expected: posts in staging/_posts/.

- [ ] **Step 5: Commit**

```bash
git add import/parse.py import/tests/test_html_parser.py
git commit -m "import: parse.py orchestrator produces staging output"
```

---

## Task 15: Validator

**Files:**
- Create: `import/validate.py`

- [ ] **Step 1: Implement validate.py**

Create `import/validate.py`:

```python
"""Validate staging/ before promote."""
from __future__ import annotations
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from lib import config as cfg

PIOBLOG_LEFTOVER = re.compile(r"https?://t\.me/pioblog/(\d+)")
IMG_REF = re.compile(r"!\[[^\]]*\]\((/assets/[^)]+)\)")
SRC_REF = re.compile(r'(?:src|href)="(/assets/[^"]+)"')
FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
TG_ID = re.compile(r"^telegram_id:\s*(\d+)$", re.MULTILINE)
TITLE_FIELD = re.compile(r"^title:\s*", re.MULTILINE)
DATE_FIELD = re.compile(r"^date:\s*", re.MULTILINE)


class Issue:
    def __init__(self, level: str, msg: str):
        self.level = level
        self.msg = msg
    def __repr__(self): return f"[{self.level}] {self.msg}"


def _collect_asset_refs(post_body: str, staging_dir: Path) -> list[Path]:
    refs: list[Path] = []
    for m in IMG_REF.finditer(post_body):
        refs.append(staging_dir / m.group(1).lstrip("/"))
    for m in SRC_REF.finditer(post_body):
        refs.append(staging_dir / m.group(1).lstrip("/"))
    return refs


def check_staging(link_map_ids: set[int]) -> list[Issue]:
    issues: list[Issue] = []
    posts = list(cfg.STAGING_POSTS.glob("*.md"))
    if not posts:
        issues.append(Issue("ERROR", "No posts in staging"))
        return issues

    telegram_ids_in_frontmatter: list[int] = []
    slugs: list[str] = []
    all_referenced_assets: set[Path] = set()

    for post in posts:
        content = post.read_text(encoding="utf-8")
        fm_m = FRONTMATTER.match(content)
        if not fm_m:
            issues.append(Issue("ERROR", f"{post.name}: no frontmatter"))
            continue
        fm = fm_m.group(1)
        body = content[fm_m.end():]
        if not TITLE_FIELD.search(fm):
            issues.append(Issue("ERROR", f"{post.name}: no title"))
        if not DATE_FIELD.search(fm):
            issues.append(Issue("ERROR", f"{post.name}: no date"))
        tid_m = TG_ID.search(fm)
        if not tid_m:
            issues.append(Issue("ERROR", f"{post.name}: no telegram_id"))
        else:
            telegram_ids_in_frontmatter.append(int(tid_m.group(1)))
        slugs.append(post.stem)
        for asset in _collect_asset_refs(body, cfg.STAGING_DIR):
            all_referenced_assets.add(asset)
            if not asset.exists():
                issues.append(Issue("ERROR", f"{post.name}: missing asset {asset.relative_to(cfg.STAGING_DIR)}"))
        for m in PIOBLOG_LEFTOVER.finditer(body):
            n = int(m.group(1))
            if n in link_map_ids:
                issues.append(Issue("ERROR", f"{post.name}: unrewritten pioblog/{n}"))

    # dupes
    for sid, count in Counter(telegram_ids_in_frontmatter).items():
        if count > 1:
            issues.append(Issue("ERROR", f"duplicate telegram_id {sid} in {count} posts"))
    for slug, count in Counter(slugs).items():
        if count > 1:
            issues.append(Issue("ERROR", f"slug collision {slug}"))

    # orphan assets
    for root in ["img/posts", "video/posts", "audio/posts", "files/posts"]:
        d = cfg.STAGING_ASSETS / root
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f not in all_referenced_assets:
                issues.append(Issue("WARN", f"orphan asset: {f.relative_to(cfg.STAGING_DIR)}"))

    # soft size warning
    size_mb = sum(f.stat().st_size for f in cfg.STAGING_ASSETS.rglob("*") if f.is_file()) / 1024 / 1024
    if size_mb > 500:
        issues.append(Issue("WARN", f"staging/assets is {size_mb:.0f} MB (soft limit 500)"))

    return issues


def main() -> int:
    # build link_map_ids from id_map + staging post ids
    import yaml
    id_map_path = Path(__file__).parent / "id_map.yml"
    raw = yaml.safe_load(id_map_path.read_text(encoding="utf-8")) if id_map_path.exists() else {}
    link_ids = set(int(k) for k in (raw or {}).keys())
    for post in cfg.STAGING_POSTS.glob("*.md"):
        m = TG_ID.search(post.read_text(encoding="utf-8"))
        if m:
            link_ids.add(int(m.group(1)))

    issues = check_staging(link_ids)
    errors = [i for i in issues if i.level == "ERROR"]
    warns = [i for i in issues if i.level == "WARN"]

    for i in issues:
        print(i)
    print(f"\n{len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run validator on fixture staging**

```bash
cd import && .venv/bin/python parse.py && .venv/bin/python validate.py
```

Expected: 0 errors (warnings are ok).

- [ ] **Step 3: Commit**

```bash
git add import/validate.py
git commit -m "import: validator — frontmatter, assets, pioblog links, dupes, orphans"
```

---

## Task 16: Promote command

**Files:**
- Create: `import/promote.py`

- [ ] **Step 1: Implement promote.py**

Create `import/promote.py`:

```python
"""Copy staging/ → real repo locations. Refuses if validator has errors."""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path
from lib import config as cfg


COPY_MAP = [
    ("_posts", "_posts"),
    ("assets/img/posts", "assets/img/posts"),
    ("assets/video/posts", "assets/video/posts"),
    ("assets/audio/posts", "assets/audio/posts"),
    ("assets/files/posts", "assets/files/posts"),
    ("_data", "_data"),
    ("series", "series"),
]


def main() -> int:
    # refuse if validator errors
    rc = subprocess.call([sys.executable, str(Path(__file__).parent / "validate.py")])
    if rc != 0:
        print("Validator failed. Aborting promote.")
        return 1

    for src_rel, dst_rel in COPY_MAP:
        src = cfg.STAGING_DIR / src_rel
        dst = cfg.REPO_ROOT / dst_rel
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_dir():
                continue
            rel = f.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            print(f"  → {target.relative_to(cfg.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add import/promote.py
git commit -m "import: promote — copy staging into real repo after validation"
```

---

## Task 17: Series layout + include + styles

**Files:**
- Create: `_layouts/series.html`
- Create: `_includes/series-nav.html`
- Modify: `_layouts/post.html`
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Create _layouts/series.html**

```html
---
layout: base
---

{% include header.html type="page" %}

<div class="container-md">
  <div class="row">
    <div class="col-xl-8 offset-xl-2 col-lg-10 offset-lg-1">
      <h1>{{ page.title }}</h1>
      {% assign series = site.data.series[page.series_id] %}
      <p class="series-meta">Серия из {{ series.total }} частей</p>
      <ol class="series-parts">
        {% for part in series.parts %}
          <li>
            <a href="{{ part.permalink | relative_url }}">{{ part.title }}</a>
            <time>{{ part.date | date: "%d.%m.%Y" }}</time>
          </li>
        {% endfor %}
      </ol>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Create _includes/series-nav.html**

```html
{% if page.series_id %}
  {% assign series = site.data.series[page.series_id] %}
  <nav class="series-nav">
    <div class="series-nav-title">
      <a href="{{ '/series/' | append: page.series_id | relative_url }}">{{ series.title }}</a>
      — часть {{ page.series_part }} из {{ page.series_total }}
    </div>
    <div class="series-nav-links">
      {% assign prev_part = page.series_part | minus: 1 %}
      {% assign next_part = page.series_part | plus: 1 %}
      {% for part in series.parts %}
        {% if part.part == prev_part %}
          <a href="{{ part.permalink | relative_url }}">← Часть {{ prev_part }}</a>
        {% endif %}
      {% endfor %}
      <a href="{{ '/series/' | append: page.series_id | relative_url }}">Оглавление</a>
      {% for part in series.parts %}
        {% if part.part == next_part %}
          <a href="{{ part.permalink | relative_url }}">Часть {{ next_part }} →</a>
        {% endif %}
      {% endfor %}
    </div>
  </nav>
{% endif %}
```

- [ ] **Step 3: Wire include into post.html**

Edit `_layouts/post.html` — insert just before the closing `</article>` of the content block. Find the line `{{ content }}` (should be around line 51) and replace the `</article>` block with:

```html
      <article role="main" class="blog-post">
        {{ content }}
        {% include series-nav.html %}
      </article>
```

- [ ] **Step 4: Add styles**

Append to `assets/css/overrides.css`:

```css
/* Series nav */
.series-nav {
  margin-top: 3rem;
  padding: 1rem;
  border: 1px solid #e1e1e1;
  border-radius: 6px;
  font-size: 0.9375rem;
}
.series-nav-title {
  font-weight: 600;
  margin-bottom: 0.5rem;
}
.series-nav-title a { color: inherit; }
.series-nav-links {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.series-nav-links a { white-space: nowrap; }

.series-parts { list-style: decimal inside; padding: 0; }
.series-parts li { margin: 0.5rem 0; }
.series-parts time { color: #666; margin-left: 0.5rem; font-size: 0.875rem; }
.series-meta { color: #666; }
```

- [ ] **Step 5: Local Jekyll dry-build to check nothing broke**

```bash
cd /Users/piofant/cursor/vedulix-blog
bundle exec jekyll build --destination /tmp/jekyll_check_series 2>&1 | tail -20
```

Expected: "done in Xs" without fatal errors (warnings about missing series.yml are OK — we haven't promoted yet).

- [ ] **Step 6: Commit**

```bash
git add _layouts/series.html _includes/series-nav.html _layouts/post.html assets/css/overrides.css
git commit -m "jekyll: series layout + post nav + styles"
```

---

## Task 18: Run parser on REAL dump, create id_map.yml

**Files:**
- Create: `import/id_map.yml`

- [ ] **Step 1: First parser run on real dump (no id_map yet)**

```bash
cd /Users/piofant/cursor/vedulix-blog/import
.venv/bin/python parse.py 2>&1 | tail -20
```

Expected: `Parsed ~370 posts → staging/_posts`, `Detected N series`.

- [ ] **Step 2: Generate id_map candidates via dedup**

Run this one-liner (or create a small script) that calls `match_existing_posts`:

```bash
cd /Users/piofant/cursor/vedulix-blog/import
.venv/bin/python - <<'PY'
from pathlib import Path
from lib import config as cfg
from lib.html_parser import parse_dump
from lib.transform import extract_title
from lib.dedup import match_existing_posts

raw = parse_dump(cfg.DUMP_DIR / "messages.html")
msgs = [{**r, "title": extract_title(r["text_html"], fallback_date=r["date"])} for r in raw]
posts_dir = cfg.REPO_ROOT / "_posts"
candidates = match_existing_posts(msgs, posts_dir)
for c in sorted(candidates, key=lambda x: x.post_file.name):
    print(f"{c.telegram_id:>4}: {c.permalink}    # {c.post_file.name} (score {c.score:.2f})")
PY
```

- [ ] **Step 3: Create id_map.yml from output**

Paste the output into `import/id_map.yml`, converting to YAML:

```yaml
# telegram_id: jekyll_permalink
# auto-generated, verify each entry by hand
86: /blog/ingress/
109: /blog/consuming-self-development-content/
# ... etc, one per existing post
```

Go through each candidate manually:
- If score < 0.7 or permalink looks wrong — open `_posts/<file>.md` and check against `https://t.me/pioblog/<id>` in a browser. Adjust `id_map.yml` to the correct id.
- If an existing post has no candidate — it may be something without a TG counterpart (e.g., migrated manually). Leave it out of map; validator will flag via check #11 (actually that check is about existing posts having telegram_id in frontmatter — we'll update those in the next task).

All 15 existing posts should end up in this file with correct TG ids.

- [ ] **Step 4: Re-parse with id_map**

```bash
cd import && make clean && .venv/bin/python parse.py
```

Now link_map includes mapping for the 15 existing posts, so any `t.me/pioblog/{86,109,...}` in newly-generated posts gets rewritten to `/blog/ingress/`, `/blog/consuming-self-development-content/`, etc.

- [ ] **Step 5: Commit id_map**

```bash
git add import/id_map.yml
git commit -m "import: id_map for 15 existing posts"
```

---

## Task 19: Update existing 15 posts with telegram_id/telegram_url frontmatter

**Files:**
- Create: `import/annotate_existing.py`
- Modify: all 15 files in `_posts/` (add two frontmatter keys)

- [ ] **Step 1: Write annotate_existing.py**

Create `import/annotate_existing.py`:

```python
"""Add telegram_id and telegram_url to frontmatter of existing 15 posts."""
from __future__ import annotations
import re
import sys
import yaml
from pathlib import Path
from lib import config as cfg


def main() -> int:
    id_map_path = Path(__file__).parent / "id_map.yml"
    raw = yaml.safe_load(id_map_path.read_text(encoding="utf-8")) or {}

    # invert: permalink → telegram_id
    by_permalink: dict[str, int] = {}
    for tid, permalink in raw.items():
        by_permalink[permalink.rstrip("/")] = int(tid)

    posts_dir = cfg.REPO_ROOT / "_posts"
    touched = 0
    for post in posts_dir.glob("*.md"):
        # permalink is /blog/<slug>/ where slug == filename minus date minus .md
        m = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)\.md$", post.name)
        if not m:
            continue
        slug = m.group(1)
        permalink = f"/blog/{slug}"
        tid = by_permalink.get(permalink)
        if tid is None:
            print(f"SKIP: {post.name} (not in id_map)")
            continue
        content = post.read_text(encoding="utf-8")
        if f"telegram_id: {tid}" in content:
            continue  # already annotated, idempotent
        # insert after 'layout: post' line in frontmatter
        lines = content.splitlines(keepends=True)
        out = []
        injected = False
        in_fm = False
        for i, ln in enumerate(lines):
            out.append(ln)
            if ln.strip() == "---" and not in_fm:
                in_fm = True
                continue
            if in_fm and not injected and ln.startswith("layout:"):
                out.append(f"telegram_id: {tid}\n")
                out.append(f"telegram_url: https://t.me/pioblog/{tid}\n")
                injected = True
        post.write_text("".join(out), encoding="utf-8")
        touched += 1
        print(f"OK:   {post.name}  ← pioblog/{tid}")
    print(f"\nAnnotated {touched} posts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd import && .venv/bin/python annotate_existing.py
```

Expected: "OK: 15 posts", no SKIPs (if SKIP — fix id_map.yml and rerun, it's idempotent).

- [ ] **Step 3: Verify with grep**

```bash
cd /Users/piofant/cursor/vedulix-blog
grep -L "telegram_id" _posts/*.md
```

Expected: empty output (all 15 posts now have it).

- [ ] **Step 4: Commit**

```bash
git add _posts/*.md import/annotate_existing.py
git commit -m "jekyll: add telegram_id to existing 15 posts for cross-link map"
```

---

## Task 20: Final parser run + validation

- [ ] **Step 1: Re-parse with complete id_map**

```bash
cd import && make clean && make parse
```

Expected: `Parsed ~355 posts → staging/_posts` (total messages minus ~15 that map to existing = the ones we newly import; actually parser still generates files for existing 15 as well — that's fine, promote.py will overwrite; you can decide to skip in parser but simpler to just overwrite).

Wait — check: does the parser import the 15 existing posts? It does, because it processes all non-service messages. After promote, they'd overwrite the hand-edited originals. We DON'T want that.

**Skip existing in parser:** modify `parse.py` main() to accept `id_map` and skip writing any post whose `telegram_id` is in the id_map keys.

Edit `parse.py` — in the third pass (body transform), wrap the `posts.append(...)` with:

```python
        if m["id"] in (id_map or {}):
            continue  # existing post, don't overwrite
```

Re-run.

```bash
cd import && make clean && make parse
```

Expected: `Parsed ~355 posts` (376 total messages minus skipped service/stickers minus 15 existing).

- [ ] **Step 2: Validate**

```bash
make validate
```

Expected: 0 errors. Warnings for orphan assets or size are OK.

Fix any errors by:
- Missing assets → check if dump has the file, maybe name collision
- Unrewritten pioblog link → check id_map completeness
- Slug collision → usually means two messages with identical first line on same day + same id_map issue

- [ ] **Step 3: Manual eyeball pass**

```bash
cd import
ls staging/_posts/ | head -30
ls staging/_posts/ | tail -30
echo "Total: $(ls staging/_posts/ | wc -l)"
```

Scan titles for garbage (empty, emoji-only, truncation mid-emoji).

Open 10 random posts:
```bash
ls staging/_posts/ | shuf -n 10 | while read f; do echo "=== $f ==="; head -20 "staging/_posts/$f"; done
```

Check for:
- Broken markdown (unclosed bold, escaped characters)
- Missing `thumbnail-img` where there should be one
- Wrong date format

If issues found — fix in `parse.py` or `transform.py`, repro via tests, re-run.

- [ ] **Step 4: Jekyll dry-build via validator already; also manual local build**

```bash
cd /Users/piofant/cursor/vedulix-blog
# temporary promote for local preview ONLY — not yet committed
cp -r import/staging/_posts/. _posts/
cp -r import/staging/assets/. assets/
cp -r import/staging/_data/. _data/ 2>/dev/null || true
cp -r import/staging/series/. series/ 2>/dev/null || true
bundle exec jekyll serve --watch
```

Open http://localhost:4000/blog/ in browser. Click through several posts: 2020 early, mid-2023, one of the series, latest 2026. Check images load, links work, series nav shows.

**This is a local preview only — no commit yet.**

If something broken — stop server, revert:
```bash
cd /Users/piofant/cursor/vedulix-blog
git checkout _posts/ assets/ _data/
rm -rf series/
# fix parser, re-run, re-preview
```

- [ ] **Step 5: Revert preview**

Once you're satisfied:
```bash
cd /Users/piofant/cursor/vedulix-blog
git checkout _posts/ assets/ _data/ 2>/dev/null || true
rm -rf series/
```

(The real promote happens in next task with proper git hygiene.)

---

## Task 21: Promote + commit in year batches + push

- [ ] **Step 1: Promote**

```bash
cd /Users/piofant/cursor/vedulix-blog/import
make promote
```

Validator runs first; if 0 errors, files copy into real repo locations.

- [ ] **Step 2: Verify git status**

```bash
cd /Users/piofant/cursor/vedulix-blog
git status --short | head -30
```

Expect:
- Hundreds of new files in `_posts/`, `assets/img/posts/`, `assets/video/posts/`, `_data/series.yml`, `series/*.md`
- No changes to the 15 existing `_posts/` (already committed in Task 19)

- [ ] **Step 3: Commit in year batches**

```bash
cd /Users/piofant/cursor/vedulix-blog

# 2020
git add _posts/2020-*.md assets/img/posts/2020-* assets/video/posts/2020-* assets/audio/posts/2020-* assets/files/posts/2020-* 2>/dev/null
git commit -m "import pioblog 2020 posts"

# 2021
git add _posts/2021-*.md assets/img/posts/2021-* assets/video/posts/2021-* assets/audio/posts/2021-* assets/files/posts/2021-* 2>/dev/null
git commit -m "import pioblog 2021 posts (new, existing 15 untouched)"

# 2022
git add _posts/2022-*.md assets/img/posts/2022-* assets/video/posts/2022-* assets/audio/posts/2022-* assets/files/posts/2022-* 2>/dev/null
git commit -m "import pioblog 2022 posts (new)"

# 2023
git add _posts/2023-*.md assets/img/posts/2023-* assets/video/posts/2023-* assets/audio/posts/2023-* assets/files/posts/2023-* 2>/dev/null
git commit -m "import pioblog 2023 posts"

# 2024
git add _posts/2024-*.md assets/img/posts/2024-* assets/video/posts/2024-* assets/audio/posts/2024-* assets/files/posts/2024-* 2>/dev/null
git commit -m "import pioblog 2024 posts"

# 2025 + 2026
git add _posts/2025-*.md _posts/2026-*.md assets/img/posts/2025-* assets/img/posts/2026-* assets/video/posts/2025-* assets/video/posts/2026-* assets/audio/posts/2025-* assets/audio/posts/2026-* assets/files/posts/2025-* assets/files/posts/2026-* 2>/dev/null
git commit -m "import pioblog 2025–2026 posts"

# series data + landing pages (must be a single atomic commit, before or after year batches is fine)
git add _data/series.yml series/
git commit -m "import pioblog: series data and landing pages"
```

- [ ] **Step 4: Push**

```bash
git push origin master
```

- [ ] **Step 5: Wait for Pages to build + verify live site**

```bash
until [ "$(gh api repos/piofant/blog/pages 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)" = "built" ]; do sleep 15; echo "building..."; done
echo "Pages built."
```

Open in browser:
- https://piofant.github.io/blog/ — feed shows newest posts (2026)
- https://piofant.github.io/blog/archive/ — shows all years 2020–2026 with counts
- https://piofant.github.io/blog/tags/ — shows all extracted hashtags
- https://piofant.github.io/blog/series/{sid}/ — pick one series from `_data/series.yml`, verify landing page renders + nav works inside a part
- 5 random posts from different years — verify images load, videos play (both self-hosted and TG embeds), internal `t.me/pioblog` links now navigate within the site

If anything broken — `git revert HEAD~1` etc, fix parser, re-run pipeline.

---

## Task 22: Finalize

- [ ] **Step 1: Update CHANGELOG.md**

Append to `CHANGELOG.md`:

```markdown
## 2026-04-24

- Imported ~355 posts from Telegram channel pioblog covering 2020–2026
- Added series navigation and landing pages for multi-part stories
- All internal pioblog links now route to the Jekyll permalinks
- Existing 15 hand-edited posts kept intact; enriched with telegram_id metadata for cross-linking
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for pioblog import"
git push
```

- [ ] **Step 3: Announce completion**

Plan is complete when:
- [x] All non-service, non-pure-sticker TG messages imported
- [x] 15 existing posts untouched but annotated with telegram_id
- [x] Series landing pages and per-post nav rendered correctly
- [x] All `t.me/pioblog/N` inside posts where N is in link_map resolve to internal permalinks
- [x] 29 videos self-hosted, 2 embedded via TG widget
- [x] Pages builds without errors
- [x] Live site smoke-tested across years and content types

---

## Appendix: Re-running later

If user exports pioblog again in 6 months:
1. Replace `ChatExport_*/` dir with new dump
2. `cd import && make clean && make parse && make validate && make promote`
3. Staging recreates from scratch, old posts get overwritten by newer versions (edits in TG persist to Jekyll)
4. Commit diff, push

The pipeline is idempotent by design.
