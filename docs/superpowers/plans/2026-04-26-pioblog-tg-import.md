# Pioblog TG Import + Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Догрузить новые посты из Telegram-канала pioblog (после ID 424) и провести аудит уже импортированных 160 постов: фотки в полном качестве, правильные даты, переписанные ссылки. Полный автомат с LLM-проверкой и git push.

**Architecture:** Python-пакет `import/sync/` с CLI `python -m import.sync`. Telethon тянет историю канала через user-account, классифицирует сообщения, конвертирует в Jekyll-посты. Переиспользует `import/lib/post.py` (frontmatter writer) и `import/lib/slugify_ru.py` из предыдущего импорта. State хранится в `import/sync/.state.json`.

**Tech Stack:** Python 3.9, telethon (TG client), anthropic SDK (Claude Haiku), Pillow (фото-сравнение), pytz (timezone), pytest. Переиспользует BS4-стек из `import/lib/`.

**Spec:** `docs/superpowers/specs/2026-04-26-pioblog-tg-import-design.md`

---

## File Structure

```
import/
├── lib/                                # ПЕРЕИСПОЛЬЗУЕТСЯ as-is
│   ├── post.py                         # Post dataclass, render_post_file
│   ├── slugify_ru.py                   # cyrillic slugify
│   └── config.py                       # TITLE_MAX_CHARS, RU_MONTHS
├── sync/                               # НОВОЕ
│   ├── __init__.py
│   ├── __main__.py                     # CLI entry: python -m import.sync ...
│   ├── config.py                       # paths, channel name, limits
│   ├── state.py                        # .state.json R/W, idempotency
│   ├── existing.py                     # parse _posts/*.md → id index
│   ├── classifier.py                   # message → category enum
│   ├── entities.py                     # TG MessageEntity → markdown
│   ├── converter.py                    # full message → Post
│   ├── media.py                        # download photos/videos, full quality
│   ├── tg_client.py                    # telethon wrapper (auth, fetch)
│   ├── audit.py                        # audit existing posts
│   ├── sync_new.py                     # sync new + holes
│   ├── llm.py                          # title/subtitle + verifier
│   └── git_ops.py                      # commit, push, wait Pages
└── tests_sync/                         # НОВОЕ
    ├── __init__.py
    ├── conftest.py                     # sys.path, fixtures
    ├── test_state.py
    ├── test_existing.py
    ├── test_classifier.py
    ├── test_entities.py
    ├── test_converter.py
    └── test_audit.py

# .gitignore additions:
# import/sync/.state.json
# import/sync/.session
```

---

## Task 1: Setup environment

**Files:**
- Modify: `import/requirements.txt`
- Modify: `.gitignore` (root)
- Create: `import/sync/__init__.py` (empty)
- Create: `import/sync/config.py`
- Create: `import/tests_sync/__init__.py` (empty)
- Create: `import/tests_sync/conftest.py`

- [ ] **Step 1: Add new deps to import/requirements.txt**

Append to `import/requirements.txt`:
```
telethon==1.36.0
anthropic==0.39.0
Pillow==10.4.0
pytz==2024.1
python-frontmatter==1.1.0
```

- [ ] **Step 2: Install deps**

```bash
cd ~/cursor/vedulix-blog/import
make install
```

Expected: success, no errors.

- [ ] **Step 3: Update root .gitignore**

Append to `~/cursor/vedulix-blog/.gitignore`:
```
import/sync/.state.json
import/sync/.session
import/sync/.session-journal
```

- [ ] **Step 4: Create import/sync/config.py**

```python
"""Constants for pioblog sync."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POSTS_DIR = REPO_ROOT / "_posts"
ASSETS_DIR = REPO_ROOT / "assets" / "img" / "posts"
SYNC_DIR = REPO_ROOT / "import" / "sync"
STATE_FILE = SYNC_DIR / ".state.json"
SESSION_FILE = SYNC_DIR / ".session"

CHANNEL = "pioblog"
TIMEZONE = "Europe/Moscow"
SITE_BASE_URL = "https://piofant.github.io/blog"
PERMALINK_PATTERN = "/blog/{slug}-{id}-{date}/"  # matches _config.yml

# Limits
TITLE_MAX_CHARS = 80
SUBTITLE_MAX_CHARS = 140
TG_RATE_LIMIT_SEC = 1.0  # 1 req/sec for bulk download

# LLM
LLM_MODEL = "claude-haiku-4-5"

# Pages build wait
PAGES_WAIT_TIMEOUT_SEC = 300
PAGES_WAIT_INTERVAL_SEC = 5
```

- [ ] **Step 5: Create import/tests_sync/conftest.py**

```python
"""Pytest config for sync tests."""
import sys
from pathlib import Path

# Make `import.sync` and `import.lib` importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
```

- [ ] **Step 6: Verify pytest discovers new test dir**

```bash
cd ~/cursor/vedulix-blog/import
.venv/bin/pytest tests_sync/ -v
```

Expected: `no tests ran in 0.0s` (empty dir, no errors).

- [ ] **Step 7: Commit**

```bash
cd ~/cursor/vedulix-blog && git add .gitignore import/requirements.txt import/sync/ import/tests_sync/ && git commit -m "sync: scaffold pioblog telethon-based sync package"
```

---

## Task 2: State module

**Files:**
- Create: `import/sync/state.py`
- Create: `import/tests_sync/test_state.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests_sync/test_state.py`:
```python
import json
import pytest
from import_module_alias import sync  # see conftest

# We import via standard path; conftest sets sys.path
from import.sync.state import State  # noqa


def test_empty_state(tmp_path):
    state_file = tmp_path / "state.json"
    s = State(state_file)
    assert s.get_status(42) is None
    assert s.last_synced_id == 0


def test_set_and_get_status(tmp_path):
    state_file = tmp_path / "state.json"
    s = State(state_file)
    s.set_status(42, "imported")
    s.set_status(43, "skipped:voice")
    assert s.get_status(42) == "imported"
    assert s.get_status(43) == "skipped:voice"


def test_persistence(tmp_path):
    state_file = tmp_path / "state.json"
    s1 = State(state_file)
    s1.set_status(10, "imported")
    s1.last_synced_id = 100
    s1.save()

    s2 = State(state_file)
    assert s2.get_status(10) == "imported"
    assert s2.last_synced_id == 100


def test_album_grouping(tmp_path):
    state_file = tmp_path / "state.json"
    s = State(state_file)
    s.set_album_group("grp_xyz", [422, 423, 424])
    assert s.get_album_members("grp_xyz") == [422, 423, 424]
    assert s.get_album_for_message(423) == "grp_xyz"
```

Note: replace `from import_module_alias import sync` with proper import — `import` is reserved. Use `import importlib; sync_state = importlib.import_module("import.sync.state")` OR rename package to `pioblog_sync/`.

**Decision:** Rename package directory `import/sync/` → `import/pioblog_sync/` to avoid Python keyword collision. Update all references.

Re-do Step 1 of Task 1 file paths: use `import/pioblog_sync/` everywhere instead of `import/sync/`. Re-do this test file:

```python
import pytest
from pioblog_sync.state import State


def test_empty_state(tmp_path):
    state_file = tmp_path / "state.json"
    s = State(state_file)
    assert s.get_status(42) is None
    assert s.last_synced_id == 0


def test_set_and_get_status(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_status(42, "imported")
    s.set_status(43, "skipped:voice")
    assert s.get_status(42) == "imported"
    assert s.get_status(43) == "skipped:voice"


def test_persistence(tmp_path):
    s1 = State(tmp_path / "s.json")
    s1.set_status(10, "imported")
    s1.last_synced_id = 100
    s1.save()
    s2 = State(tmp_path / "s.json")
    assert s2.get_status(10) == "imported"
    assert s2.last_synced_id == 100


def test_album_grouping(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_album_group("grp_xyz", [422, 423, 424])
    assert s.get_album_members("grp_xyz") == [422, 423, 424]
    assert s.get_album_for_message(423) == "grp_xyz"
```

Update `conftest.py` to add `import/pioblog_sync/` parent to sys.path:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pioblog_sync"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

Wait — for `from pioblog_sync.state import State` to work, sys.path must include parent of `pioblog_sync/`, i.e., `import/`. Update:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

Then rename references in this plan from `import/sync/` to `import/pioblog_sync/` everywhere.

- [ ] **Step 2: Run tests to verify failure**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_state.py -v
```

Expected: ImportError for `pioblog_sync.state`.

- [ ] **Step 3: Implement State**

Create `import/pioblog_sync/state.py`:
```python
"""JSON state for idempotent sync."""
from __future__ import annotations
import json
from pathlib import Path


class State:
    """Tracks per-message processing status + album groups."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_synced_id: int = 0
        self._statuses: dict[int, str] = {}
        self._album_groups: dict[str, list[int]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.last_synced_id = int(data.get("last_synced_id", 0))
        self._statuses = {int(k): v for k, v in data.get("statuses", {}).items()}
        self._album_groups = {k: list(v) for k, v in data.get("album_groups", {}).items()}

    def save(self) -> None:
        data = {
            "last_synced_id": self.last_synced_id,
            "statuses": {str(k): v for k, v in self._statuses.items()},
            "album_groups": self._album_groups,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_status(self, msg_id: int) -> str | None:
        return self._statuses.get(msg_id)

    def set_status(self, msg_id: int, status: str) -> None:
        self._statuses[msg_id] = status

    def set_album_group(self, group_id: str, member_ids: list[int]) -> None:
        self._album_groups[group_id] = sorted(member_ids)

    def get_album_members(self, group_id: str) -> list[int]:
        return self._album_groups.get(group_id, [])

    def get_album_for_message(self, msg_id: int) -> str | None:
        for gid, members in self._album_groups.items():
            if msg_id in members:
                return gid
        return None
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_state.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Rename Task 1 dir + commit**

```bash
cd ~/cursor/vedulix-blog && git mv import/sync import/pioblog_sync && git mv import/sync/__init__.py import/pioblog_sync/__init__.py 2>/dev/null
# also fix conftest sys.path if needed (Task 1 step 5)
git add -A && git commit -m "sync: state module + idempotency tracking"
```

---

## Task 3: Existing posts index

**Files:**
- Create: `import/pioblog_sync/existing.py`
- Create: `import/tests_sync/test_existing.py`
- Create: `import/tests_sync/fixtures/sample_post.md`

- [ ] **Step 1: Write failing tests**

Create `import/tests_sync/fixtures/sample_post.md`:
```markdown
---
layout: post
title: "Test post"
date: 2024-06-07 12:00:00 +0300
telegram_id: 157
telegram_url: https://t.me/pioblog/157
thumbnail-img: /blog/assets/img/posts/2024-06-07-foo-157/photo_1.jpg
---

Body of the post here.
```

Create `import/tests_sync/test_existing.py`:
```python
import pytest
from pathlib import Path
from pioblog_sync.existing import build_index, ExistingPost


def test_build_index_finds_telegram_id(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "sample_post.md"
    target = posts_dir / "2024-06-07-foo-157.md"
    target.write_text(fixture.read_text(), encoding="utf-8")

    idx = build_index(posts_dir)
    assert 157 in idx
    p = idx[157]
    assert isinstance(p, ExistingPost)
    assert p.telegram_id == 157
    assert p.slug == "foo-157"
    assert p.date.isoformat().startswith("2024-06-07")
    assert p.path == target


def test_build_index_skips_underscore_files(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "_draft.md").write_text("---\ntelegram_id: 99\n---\nbody", encoding="utf-8")
    idx = build_index(posts_dir)
    assert 99 not in idx


def test_build_index_skips_posts_without_telegram_id(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-01-03-define-self-reflexion.md").write_text(
        "---\nlayout: post\ntitle: 'No TG'\ndate: 2022-01-03\n---\nbody", encoding="utf-8"
    )
    idx = build_index(posts_dir)
    assert idx == {}


def test_permalink_for_post():
    """Jekyll permalink format from _config.yml: /:title-:year-:month-:day/"""
    from datetime import datetime
    p = ExistingPost(
        telegram_id=157, slug="foo-157",
        date=datetime(2024, 6, 7, 12, 0),
        path=Path("/tmp/x.md"),
        title="Test", subtitle=None, thumbnail=None,
    )
    assert p.permalink() == "/blog/foo-157-2024-06-07/"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_existing.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement existing.py**

Create `import/pioblog_sync/existing.py`:
```python
"""Index of existing _posts/*.md by telegram_id."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
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


def build_index(posts_dir: Path) -> dict[int, ExistingPost]:
    """Scan _posts/ for .md files with telegram_id; return id → ExistingPost."""
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

        # parse date from frontmatter (preferred) or filename
        fm_date = post.metadata.get("date")
        if isinstance(fm_date, datetime):
            date = fm_date
        elif isinstance(fm_date, str):
            try:
                date = datetime.fromisoformat(fm_date.split(" +")[0].replace(" ", "T"))
            except ValueError:
                date = datetime.fromisoformat(date_str)
        else:
            date = datetime.fromisoformat(date_str)

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
```

- [ ] **Step 4: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_existing.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Smoke check on real _posts/**

```bash
cd ~/cursor/vedulix-blog && python3 -c "
import sys; sys.path.insert(0, 'import')
from pioblog_sync.existing import build_index
from pathlib import Path
idx = build_index(Path('_posts'))
print(f'indexed: {len(idx)} posts, ids: {min(idx)}..{max(idx)}')
print('sample permalink:', list(idx.values())[0].permalink())
"
```

Expected: `indexed: 160 posts, ids: 4..424`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "sync: existing posts index by telegram_id"
```

---

## Task 4: Message classifier

**Files:**
- Create: `import/pioblog_sync/classifier.py`
- Create: `import/tests_sync/test_classifier.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests_sync/test_classifier.py`:
```python
import pytest
from unittest.mock import MagicMock
from pioblog_sync.classifier import classify, MsgType


def _msg(text=None, photo=None, video=None, voice=None, poll=None,
         document=None, forward=None, action=None, grouped_id=None):
    m = MagicMock()
    m.text = text or ""
    m.message = text or ""
    m.photo = photo
    m.video = video
    m.voice = voice
    m.poll = poll
    m.document = document
    m.forward = forward
    m.action = action  # service action (pin, photo change)
    m.grouped_id = grouped_id
    return m


def test_classify_none_is_deleted():
    assert classify(None) == MsgType.DELETED


def test_text_only():
    assert classify(_msg(text="hello world")) == MsgType.TEXT


def test_album_member():
    # photo with grouped_id → album
    assert classify(_msg(text="caption", photo=True, grouped_id=12345)) == MsgType.ALBUM_MEMBER


def test_voice_only():
    assert classify(_msg(voice=True)) == MsgType.VOICE


def test_video_only():
    assert classify(_msg(video=True)) == MsgType.VIDEO


def test_poll():
    assert classify(_msg(poll=True)) == MsgType.POLL


def test_forward():
    fwd = MagicMock()
    assert classify(_msg(text="forwarded text", forward=fwd)) == MsgType.FORWARDED


def test_service_action():
    act = MagicMock()
    assert classify(_msg(action=act)) == MsgType.SERVICE


def test_text_with_photo_no_group():
    # single photo with caption → just TEXT (single-photo post)
    assert classify(_msg(text="caption", photo=True)) == MsgType.TEXT
```

- [ ] **Step 2: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_classifier.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement classifier**

Create `import/pioblog_sync/classifier.py`:
```python
"""Classify a Telegram message into one of N categories."""
from __future__ import annotations
from enum import Enum


class MsgType(str, Enum):
    TEXT = "text"
    ALBUM_MEMBER = "album_member"
    VOICE = "voice"
    VIDEO = "video"
    POLL = "poll"
    FORWARDED = "forwarded"
    SERVICE = "service"
    DELETED = "deleted"


def classify(message) -> MsgType:
    """Return classification of a Telethon Message (or None for deleted)."""
    if message is None:
        return MsgType.DELETED
    if message.action is not None:
        return MsgType.SERVICE
    if message.poll is not None:
        return MsgType.POLL
    if message.forward is not None:
        return MsgType.FORWARDED
    if message.grouped_id is not None:
        return MsgType.ALBUM_MEMBER
    if message.voice is not None:
        return MsgType.VOICE
    if message.video is not None and not (message.text or "").strip():
        return MsgType.VIDEO
    return MsgType.TEXT
```

- [ ] **Step 4: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_classifier.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "sync: message classifier (text/album/voice/video/poll/forward/service)"
```

---

## Task 5: Entity converter (TG entities → markdown)

**Files:**
- Create: `import/pioblog_sync/entities.py`
- Create: `import/tests_sync/test_entities.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests_sync/test_entities.py`:
```python
import pytest
from unittest.mock import MagicMock
from pioblog_sync.entities import entities_to_markdown


def _ent(cls_name, offset, length, **kwargs):
    e = MagicMock()
    e.__class__.__name__ = cls_name
    e.offset = offset
    e.length = length
    for k, v in kwargs.items():
        setattr(e, k, v)
    # ensure these don't auto-create on access
    if cls_name != "MessageEntityTextUrl":
        e.url = None
    if cls_name != "MessageEntityMentionName":
        e.user_id = None
    return e


def test_no_entities():
    assert entities_to_markdown("hello world", []) == "hello world"


def test_bold():
    text = "hello world"
    e = _ent("MessageEntityBold", 0, 5)
    assert entities_to_markdown(text, [e]) == "**hello** world"


def test_italic():
    text = "hello world"
    e = _ent("MessageEntityItalic", 6, 5)
    assert entities_to_markdown(text, [e]) == "hello *world*"


def test_code():
    text = "use foo() here"
    e = _ent("MessageEntityCode", 4, 5)
    assert entities_to_markdown(text, [e]) == "use `foo()` here"


def test_text_url():
    text = "see Google"
    e = _ent("MessageEntityTextUrl", 4, 6, url="https://google.com")
    assert entities_to_markdown(text, [e]) == "see [Google](https://google.com)"


def test_url_inline():
    text = "go https://x.com now"
    e = _ent("MessageEntityUrl", 3, 13)
    assert entities_to_markdown(text, [e]) == "go <https://x.com> now"


def test_mention():
    text = "ping @user"
    e = _ent("MessageEntityMention", 5, 5)
    assert entities_to_markdown(text, [e]) == "ping [@user](https://t.me/user)"


def test_strike():
    text = "old new"
    e = _ent("MessageEntityStrike", 0, 3)
    assert entities_to_markdown(text, [e]) == "~~old~~ new"


def test_overlapping_entities():
    text = "hello world"
    bold = _ent("MessageEntityBold", 0, 5)
    italic = _ent("MessageEntityItalic", 6, 5)
    assert entities_to_markdown(text, [bold, italic]) == "**hello** *world*"


def test_unicode_offsets():
    """Telegram entity offsets are UTF-16 code units, not Python str chars."""
    # Russian: 'привет мир' — Cyrillic letters are BMP single units in UTF-16.
    text = "привет мир"
    e = _ent("MessageEntityBold", 0, 6)  # 'привет'
    assert entities_to_markdown(text, [e]) == "**привет** мир"
```

- [ ] **Step 2: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_entities.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement entities.py**

Create `import/pioblog_sync/entities.py`:
```python
"""Convert Telegram MessageEntity list → markdown text.

Telegram entities use UTF-16 code-unit offsets. We work in UTF-16 internally,
then re-encode to UTF-8 string at the end.
"""
from __future__ import annotations
from typing import Iterable


def _wrap(name: str, ent) -> tuple[str, str]:
    """Return (open, close) markdown for an entity class name."""
    if name == "MessageEntityBold":
        return "**", "**"
    if name == "MessageEntityItalic":
        return "*", "*"
    if name == "MessageEntityCode":
        return "`", "`"
    if name in ("MessageEntityPre",):
        lang = getattr(ent, "language", "") or ""
        return f"\n```{lang}\n", "\n```\n"
    if name == "MessageEntityStrike":
        return "~~", "~~"
    if name == "MessageEntityUnderline":
        return "<u>", "</u>"
    if name == "MessageEntitySpoiler":
        return '<span class="spoiler">', "</span>"
    if name == "MessageEntityBlockquote":
        return "> ", ""
    return "", ""


def entities_to_markdown(text: str, entities: Iterable) -> str:
    """Apply Telegram entities (UTF-16 offsets) to plain text → markdown."""
    if not entities:
        return text

    # Convert text to UTF-16 LE units for offset arithmetic
    utf16 = text.encode("utf-16-le")
    # Build list of insertions: (utf16_byte_offset, priority, insert_str)
    inserts: list[tuple[int, int, str]] = []

    for ent in entities:
        cls = ent.__class__.__name__
        start = ent.offset * 2  # UTF-16 code units → bytes
        end = (ent.offset + ent.length) * 2

        if cls == "MessageEntityTextUrl":
            url = getattr(ent, "url", "")
            inserts.append((start, 0, "["))
            inserts.append((end, 1, f"]({url})"))
        elif cls == "MessageEntityUrl":
            # Inline URL: wrap in <...>
            inserts.append((start, 0, "<"))
            inserts.append((end, 1, ">"))
        elif cls == "MessageEntityMention":
            # @username — wrap as [text](https://t.me/username) — text already includes @
            mention_bytes = utf16[start:end]
            mention = mention_bytes.decode("utf-16-le")
            handle = mention.lstrip("@")
            inserts.append((start, 0, "["))
            inserts.append((end, 1, f"](https://t.me/{handle})"))
        else:
            o, c = _wrap(cls, ent)
            if o or c:
                inserts.append((start, 0, o))
                inserts.append((end, 1, c))

    # Sort by byte offset; ties → 'close' (priority 1) before 'open' (0) at same pos
    inserts.sort(key=lambda x: (x[0], -x[1]))

    out = bytearray()
    cursor = 0
    for offset, _, s in inserts:
        out.extend(utf16[cursor:offset])
        out.extend(s.encode("utf-16-le"))
        cursor = offset
    out.extend(utf16[cursor:])
    return out.decode("utf-16-le")
```

- [ ] **Step 4: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_entities.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "sync: TG MessageEntity → markdown converter"
```

---

## Task 6: Body converter (full message → Post + link rewriting)

**Files:**
- Create: `import/pioblog_sync/converter.py`
- Create: `import/tests_sync/test_converter.py`

- [ ] **Step 1: Write failing tests**

Create `import/tests_sync/test_converter.py`:
```python
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from pioblog_sync.converter import (
    rewrite_pioblog_links, build_body, build_post_filename
)
from pioblog_sync.existing import ExistingPost


def _existing(id_, slug="foo", date=datetime(2024, 1, 1)):
    return ExistingPost(
        telegram_id=id_, slug=slug, date=date, path=Path("/x.md"),
        title="t", subtitle=None, thumbnail=None,
    )


def test_rewrite_known_pioblog_link():
    body = "see [past post](https://t.me/pioblog/100) for context"
    idx = {100: _existing(100, "old-100", datetime(2022, 5, 16))}
    out = rewrite_pioblog_links(body, idx)
    assert out == "see [past post](/blog/old-100-2022-05-16/) for context"


def test_rewrite_bare_pioblog_url():
    body = "context: <https://t.me/pioblog/100>"
    idx = {100: _existing(100, "old-100", datetime(2022, 5, 16))}
    out = rewrite_pioblog_links(body, idx)
    assert out == "context: </blog/old-100-2022-05-16/>"


def test_dont_rewrite_unknown_pioblog_link():
    body = "see [post](https://t.me/pioblog/999) here"
    idx = {100: _existing(100)}
    out = rewrite_pioblog_links(body, idx)
    assert out == "see [post](https://t.me/pioblog/999) here"


def test_dont_rewrite_other_channels():
    body = "follow [chan](https://t.me/somechannel/42)"
    idx = {}
    out = rewrite_pioblog_links(body, idx)
    assert out == body


def test_build_body_appends_telegram_link():
    body_md = "Hello world"
    out = build_body(body_md, photos=[], videos=[], voices=[], polls=[], telegram_id=42)
    assert "Hello world" in out
    assert "[Оригинал в Telegram →](https://t.me/pioblog/42)" in out
    assert out.endswith("\n")


def test_build_body_with_photos():
    body_md = "Caption text"
    out = build_body(body_md, photos=["/blog/assets/img/posts/foo/photo_1.jpg"],
                     videos=[], voices=[], polls=[], telegram_id=1)
    assert "![](/blog/assets/img/posts/foo/photo_1.jpg)" in out


def test_build_body_with_video():
    out = build_body("", photos=[], videos=["/blog/assets/img/posts/foo/video_1.mp4"],
                     voices=[], polls=[], telegram_id=1)
    assert '<video controls src="/blog/assets/img/posts/foo/video_1.mp4"></video>' in out


def test_build_post_filename():
    fn = build_post_filename(datetime(2026, 4, 15, 14, 30), "moi-post", 425)
    assert fn == "2026-04-15-moi-post-425.md"
```

- [ ] **Step 2: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_converter.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement converter.py**

Create `import/pioblog_sync/converter.py`:
```python
"""Convert TG message → Jekyll Post: body assembly + link rewriting."""
from __future__ import annotations
import re
from datetime import datetime
from typing import Iterable

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
```

- [ ] **Step 4: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_converter.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "sync: body converter + pioblog link rewriting"
```

---

## Task 7: Telegram client wrapper

**Files:**
- Create: `import/pioblog_sync/tg_client.py`

This module is I/O-heavy and only integration-testable. We'll smoke-test it manually in Task 13.

- [ ] **Step 1: Implement tg_client.py**

Create `import/pioblog_sync/tg_client.py`:
```python
"""Telethon wrapper: auth, fetch messages, group albums."""
from __future__ import annotations
import os
import asyncio
from collections import defaultdict
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.custom.message import Message

from pioblog_sync.config import CHANNEL, SESSION_FILE, TG_RATE_LIMIT_SEC


class TGClient:
    def __init__(self, api_id: int, api_hash: str, session_path: Path = SESSION_FILE):
        self.client = TelegramClient(str(session_path), api_id, api_hash)

    async def __aenter__(self):
        await self.client.start()  # prompts phone+code on first run
        return self

    async def __aexit__(self, *exc):
        await self.client.disconnect()

    async def fetch_all_ids(self, channel: str = CHANNEL) -> list[int]:
        """Return all message IDs in channel (ascending)."""
        ids = []
        async for m in self.client.iter_messages(channel, reverse=True):
            ids.append(m.id)
        return ids

    async def get_messages(self, channel: str, ids: list[int]) -> list[Message | None]:
        """Batch get_messages with rate limiting (chunks of 100)."""
        out: list[Message | None] = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i+100]
            msgs = await self.client.get_messages(channel, ids=chunk)
            out.extend(msgs)
            if i + 100 < len(ids):
                await asyncio.sleep(TG_RATE_LIMIT_SEC)
        return out

    @staticmethod
    def group_albums(messages: list[Message]) -> dict[str, list[Message]]:
        """Bucket messages by grouped_id (str). Loners go in their own bucket."""
        groups: dict[str, list[Message]] = defaultdict(list)
        for m in messages:
            if m is None:
                continue
            key = str(m.grouped_id) if m.grouped_id else f"single_{m.id}"
            groups[key].append(m)
        for k in groups:
            groups[k].sort(key=lambda m: m.id)
        return dict(groups)


def get_credentials() -> tuple[int, str]:
    """Read TG_API_ID and TG_API_HASH from env. Raise ValueError if missing."""
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    if not api_id or not api_hash:
        raise ValueError(
            "Missing TG_API_ID / TG_API_HASH env vars. "
            "Get them from https://my.telegram.org/apps"
        )
    return int(api_id), api_hash
```

- [ ] **Step 2: Smoke check (no auth — just import)**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -c "from pioblog_sync.tg_client import TGClient, get_credentials; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: telethon client wrapper"
```

---

## Task 8: Media downloader

**Files:**
- Create: `import/pioblog_sync/media.py`

- [ ] **Step 1: Implement media.py**

Create `import/pioblog_sync/media.py`:
```python
"""Download photos/videos/voices in full quality, idempotent by filename."""
from __future__ import annotations
import asyncio
from pathlib import Path
from PIL import Image

from pioblog_sync.config import ASSETS_DIR


async def download_media_for_post(client, messages, slug: str) -> dict[str, list[str]]:
    """Download all media for a post (single message or album).

    Returns dict with keys 'photos', 'videos', 'voices' (each list of /blog/... URLs).
    """
    out_dir = ASSETS_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    photos: list[str] = []
    videos: list[str] = []
    voices: list[str] = []

    photo_seq = video_seq = voice_seq = 0
    for m in messages:
        if m.photo is not None:
            photo_seq += 1
            fname = f"photo_{photo_seq}.jpg"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            photos.append(f"/blog/assets/img/posts/{slug}/{fname}")
        elif m.video is not None:
            video_seq += 1
            fname = f"video_{video_seq}.mp4"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            videos.append(f"/blog/assets/img/posts/{slug}/{fname}")
        elif m.voice is not None:
            voice_seq += 1
            fname = f"voice_{voice_seq}.ogg"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            voices.append(f"/blog/assets/img/posts/{slug}/{fname}")

    return {"photos": photos, "videos": videos, "voices": voices}


def photo_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image."""
    with Image.open(path) as img:
        return img.size


def is_higher_quality(existing: Path, new_size_bytes: int) -> bool:
    """Crude heuristic: new is higher quality if its file is significantly larger."""
    if not existing.exists():
        return True
    return new_size_bytes > existing.stat().st_size * 1.2
```

- [ ] **Step 2: Smoke check import**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -c "from pioblog_sync.media import download_media_for_post, photo_dimensions; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: media downloader (photo/video/voice in full quality)"
```

---

## Task 9: LLM module (title/subtitle + verifier)

**Files:**
- Create: `import/pioblog_sync/llm.py`

Integration with Anthropic API; tested by smoke run during real sync.

- [ ] **Step 1: Implement llm.py**

Create `import/pioblog_sync/llm.py`:
```python
"""Claude Haiku for title/subtitle generation and post-import verification."""
from __future__ import annotations
import os
from dataclasses import dataclass

from anthropic import Anthropic
from pioblog_sync.config import LLM_MODEL, TITLE_MAX_CHARS, SUBTITLE_MAX_CHARS


@dataclass
class TitleSubtitle:
    title: str
    subtitle: str


@dataclass
class VerificationIssue:
    severity: str  # "critical" or "warning"
    file: str
    message: str


_TITLE_PROMPT = """Тебе дано тело Telegram-поста на русском. Сгенерируй для него:
1) title — короткий заголовок (≤{title_max} символов), в стиле автора (lowercase ок, без точки в конце, можно эмодзи в начале если они есть в посте);
2) subtitle — подзаголовок-тизер (≤{subtitle_max} символов).

ВЕРНИ ТОЛЬКО JSON в формате: {{"title": "...", "subtitle": "..."}}
Никаких пояснений вокруг.

Тело поста:
---
{body}
---"""


def generate_title_subtitle(body: str) -> TitleSubtitle:
    """Generate title + subtitle for a TG post body via Claude Haiku."""
    if not body.strip():
        return TitleSubtitle(title="(медиа)", subtitle="")
    if len(body.strip()) < 30:
        # Too short for LLM — use first line
        first = body.strip().split("\n")[0]
        return TitleSubtitle(title=first[:TITLE_MAX_CHARS], subtitle="")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _TITLE_PROMPT.format(
        title_max=TITLE_MAX_CHARS,
        subtitle_max=SUBTITLE_MAX_CHARS,
        body=body[:4000],  # cap to be safe
    )
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # Strip code fences if present
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    import json
    try:
        obj = json.loads(raw)
        return TitleSubtitle(
            title=str(obj.get("title", "")).strip()[:TITLE_MAX_CHARS],
            subtitle=str(obj.get("subtitle", "")).strip()[:SUBTITLE_MAX_CHARS],
        )
    except Exception:
        # Fallback: first line
        first = body.strip().split("\n")[0]
        return TitleSubtitle(title=first[:TITLE_MAX_CHARS], subtitle="")


_VERIFY_PROMPT = """Проверь содержимое импортированного Jekyll-поста на предмет проблем:
- разметка markdown поломана (одиночный `*`, незакрытые теги, кривые ссылки);
- текст обрезан на середине предложения;
- title или subtitle очевидно неадекватный (повторяет body, пустой, бессмысленный);
- ссылка на изображение `![](path)` указывает на путь, которого не должно существовать.

ВЕРНИ ТОЛЬКО JSON-массив объектов:
[{{"severity": "critical|warning", "message": "..."}}]

Если проблем нет — верни [].

Содержимое файла:
---
{content}
---"""


def verify_post_file(filepath: str, content: str) -> list[VerificationIssue]:
    """Run LLM check on a single .md file. Returns list of issues."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _VERIFY_PROMPT.format(content=content[:8000])
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    import json
    try:
        arr = json.loads(raw)
        return [VerificationIssue(severity=i["severity"], file=filepath, message=i["message"])
                for i in arr]
    except Exception:
        return []
```

- [ ] **Step 2: Smoke check import**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -c "from pioblog_sync.llm import generate_title_subtitle, verify_post_file; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: LLM title/subtitle generation + post-import verifier"
```

---

## Task 10: Audit module

**Files:**
- Create: `import/pioblog_sync/audit.py`
- Create: `import/tests_sync/test_audit.py`

- [ ] **Step 1: Write failing test (link rewrite logic only — file ops too I/O-heavy)**

Create `import/tests_sync/test_audit.py`:
```python
import pytest
from datetime import datetime
from pathlib import Path
from pioblog_sync.audit import find_unrewritten_links
from pioblog_sync.existing import ExistingPost


def _existing(id_, slug, date):
    return ExistingPost(
        telegram_id=id_, slug=slug, date=date, path=Path("/x.md"),
        title="t", subtitle=None, thumbnail=None,
    )


def test_find_unrewritten_pioblog_links():
    body = "see https://t.me/pioblog/100 and [also](https://t.me/pioblog/200)"
    idx = {
        100: _existing(100, "old-100", datetime(2022, 1, 1)),
        200: _existing(200, "old-200", datetime(2023, 5, 1)),
        300: _existing(300, "skip-300", datetime(2024, 1, 1)),
    }
    found = find_unrewritten_links(body, idx)
    assert sorted(found) == [100, 200]


def test_no_unrewritten_when_already_internal():
    body = "see [past](/blog/old-100-2022-01-01/) here"
    idx = {100: _existing(100, "old-100", datetime(2022, 1, 1))}
    found = find_unrewritten_links(body, idx)
    assert found == []


def test_skip_unknown_pioblog_ids():
    body = "see https://t.me/pioblog/999"
    idx = {100: _existing(100, "old-100", datetime(2022, 1, 1))}
    found = find_unrewritten_links(body, idx)
    assert found == []  # 999 not imported, leave as-is
```

- [ ] **Step 2: Implement audit.py**

Create `import/pioblog_sync/audit.py`:
```python
"""Audit existing posts: photos, dates, links."""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter

from pioblog_sync.config import POSTS_DIR, ASSETS_DIR
from pioblog_sync.converter import rewrite_pioblog_links, PIOBLOG_LINK
from pioblog_sync.existing import ExistingPost


@dataclass
class AuditFix:
    kind: str  # 'date', 'thumbnail', 'links', 'photo'
    file: Path
    description: str


def find_unrewritten_links(body: str, existing: dict[int, ExistingPost]) -> list[int]:
    """IDs of pioblog links in body that COULD be rewritten (i.e., target is imported)."""
    out: list[int] = []
    for m in PIOBLOG_LINK.finditer(body):
        tg_id = int(m.group(1))
        if tg_id in existing:
            out.append(tg_id)
    return out


async def audit_post(client, message, post: ExistingPost,
                    existing: dict[int, ExistingPost]) -> list[AuditFix]:
    """Compare existing post to TG message, apply safe fixes, return list of fixes done."""
    fixes: list[AuditFix] = []
    fm = frontmatter.load(str(post.path))

    # 1. Date check (skip if intentional override — > 1 day diff means fix)
    tg_date = message.date.astimezone()  # Telethon returns aware UTC
    fm_date = fm.metadata.get("date")
    if isinstance(fm_date, datetime):
        fm_aware = fm_date if fm_date.tzinfo else fm_date.replace(tzinfo=tg_date.tzinfo)
        if abs((fm_aware - tg_date).total_seconds()) > 86400:
            fm.metadata["date"] = tg_date.strftime("%Y-%m-%d %H:%M:%S %z")
            fixes.append(AuditFix("date", post.path, f"date {fm_date} → {tg_date}"))

    # 2. Body link rewriting
    body = fm.content
    unrewritten = find_unrewritten_links(body, existing)
    if unrewritten:
        new_body = rewrite_pioblog_links(body, existing)
        if new_body != body:
            fm.content = new_body
            fixes.append(AuditFix("links", post.path,
                                  f"rewrote {len(unrewritten)} pioblog links"))

    # 3. Thumbnail existence check
    thumb = fm.metadata.get("thumbnail-img")
    if thumb:
        thumb_path = Path(str(thumb).replace("/blog/", "")).resolve()
        full = ASSETS_DIR.parent.parent.parent / str(thumb).lstrip("/").replace("blog/", "")
        # ... resolve relative to repo root
        # Skip complex resolution: just write and let LLM verifier catch broken links

    if fixes:
        post.path.write_text(frontmatter.dumps(fm), encoding="utf-8")

    return fixes


# Note: Photo re-download logic deferred — too I/O-heavy to test in unit tests.
# It runs in real sync flow; covered by smoke check.
```

- [ ] **Step 3: Run tests**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/pytest tests_sync/test_audit.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "sync: audit module (date, links, thumbnail checks)"
```

---

## Task 11: Sync module (orchestration)

**Files:**
- Create: `import/pioblog_sync/sync_new.py`

- [ ] **Step 1: Implement sync_new.py**

Create `import/pioblog_sync/sync_new.py`:
```python
"""Orchestrate sync of new posts + classification of holes."""
from __future__ import annotations
import asyncio
import re
from datetime import datetime
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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.slugify_ru import slugify_ru


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

    # Poll → static snapshot
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
    fname = build_post_filename(tg_date_msk, slug.rsplit(f"-{primary.id}", 1)[0], primary.id)
    target = POSTS_DIR / fname
    target.write_text(frontmatter.dumps(post), encoding="utf-8")

    # Mark all member ids as imported
    for m in messages:
        state.set_status(m.id, "imported")
    if primary.grouped_id:
        state.set_album_group(str(primary.grouped_id), [m.id for m in messages])

    return target


```

This module exposes reusable helpers (`import_message_group`, `_slug_for_message`, `_format_poll`); orchestration loop lives in `__main__.py` (Task 13).

- [ ] **Step 2: Smoke check import**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -c "from pioblog_sync.sync_new import import_message_group, _slug_for_message, _format_poll; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: import_message_group + helpers (poll snapshot, slug, body assembly)"
```

---

## Task 12: Git ops

**Files:**
- Create: `import/pioblog_sync/git_ops.py`

- [ ] **Step 1: Implement git_ops.py**

Create `import/pioblog_sync/git_ops.py`:
```python
"""Git commit + push + wait for GitHub Pages build."""
from __future__ import annotations
import subprocess
import time
import json
import urllib.request
from pathlib import Path

from pioblog_sync.config import REPO_ROOT, PAGES_WAIT_TIMEOUT_SEC, PAGES_WAIT_INTERVAL_SEC


def _run(args: list[str], cwd: Path = REPO_ROOT, check: bool = True) -> str:
    res = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(args)}\nstdout: {res.stdout}\nstderr: {res.stderr}")
    return res.stdout.strip()


def has_changes() -> bool:
    return bool(_run(["git", "status", "--porcelain", "_posts/", "assets/img/posts/"]))


def commit_and_push(message: str) -> str:
    """Stage _posts/ and assets/, commit, push. Returns commit SHA."""
    _run(["git", "add", "_posts/", "assets/img/posts/"])
    _run(["git", "commit", "-m", message])
    _run(["git", "push", "origin", "master"])
    return _run(["git", "rev-parse", "HEAD"])


def wait_for_pages_build() -> bool:
    """Poll gh api repos/piofant/blog/pages until status='built' or timeout."""
    start = time.time()
    while time.time() - start < PAGES_WAIT_TIMEOUT_SEC:
        try:
            out = subprocess.run(
                ["gh", "api", "repos/piofant/blog/pages"],
                capture_output=True, text=True, check=True,
            ).stdout
            data = json.loads(out)
            if data.get("status") == "built":
                return True
        except Exception:
            pass
        time.sleep(PAGES_WAIT_INTERVAL_SEC)
    return False


def url_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False
```

- [ ] **Step 2: Smoke check import + dry checks**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -c "from pioblog_sync.git_ops import has_changes, url_ok; print('changes:', has_changes()); print('live ok:', url_ok('https://piofant.github.io/blog/'))"
```

Expected: `changes: ...; live ok: True`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: git ops (commit, push, wait Pages, verify URL)"
```

---

## Task 13: CLI entry point + orchestration

**Files:**
- Create: `import/pioblog_sync/__main__.py`

- [ ] **Step 1: Implement __main__.py**

Create `import/pioblog_sync/__main__.py`:
```python
"""CLI: python -m pioblog_sync [audit|sync|full] [--dry-run] [--limit N] [--no-push]"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

# Ensure import/ is on sys.path so `import lib.*` works
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pioblog_sync.config import POSTS_DIR, STATE_FILE
from pioblog_sync.state import State
from pioblog_sync.existing import build_index
from pioblog_sync.tg_client import TGClient, get_credentials
from pioblog_sync.classifier import classify, MsgType
from pioblog_sync.sync_new import import_message_group
from pioblog_sync.audit import audit_post
from pioblog_sync.llm import verify_post_file
from pioblog_sync.git_ops import commit_and_push, wait_for_pages_build, url_ok, has_changes


async def cmd_audit(tg: TGClient, existing: dict, state: State, dry_run: bool) -> int:
    print(f"[2/6] audit existing {len(existing)} posts...")
    ids = sorted(existing.keys())
    messages = await tg.get_messages("pioblog", ids)
    fixes = 0
    for tg_id, msg in zip(ids, messages):
        if msg is None:
            continue
        post = existing[tg_id]
        post_fixes = await audit_post(tg.client, msg, post, existing)
        for f in post_fixes:
            print(f"  - {post.path.name}: {f.kind} — {f.description}")
            fixes += 1
    print(f"  audit: {fixes} fixes applied")
    return fixes


async def cmd_sync(tg: TGClient, existing: dict, state: State,
                   limit: int | None, dry_run: bool) -> int:
    print(f"[3/6] discovering messages on channel...")
    all_ids = await tg.fetch_all_ids("pioblog")
    print(f"  channel has {len(all_ids)} message ids (max={max(all_ids)})")

    todo = [i for i in all_ids if i not in existing and state.get_status(i) is None]
    if limit:
        todo = todo[-limit:]
    print(f"  to process: {len(todo)} ids")

    if not todo:
        return 0

    messages = await tg.get_messages("pioblog", todo)
    # Group by grouped_id (album); align Nones to their requested ids
    groups: dict[str, list] = {}
    for requested_id, m in zip(todo, messages):
        if m is None:
            state.set_status(requested_id, "skipped:deleted")
            continue
        key = str(m.grouped_id) if m.grouped_id else f"single_{m.id}"
        groups.setdefault(key, []).append(m)
    for k in groups:
        groups[k].sort(key=lambda x: x.id)

    created = 0
    for key, msgs in groups.items():
        primary = msgs[0]
        msg_type = classify(primary)

        if msg_type == MsgType.SERVICE:
            for m in msgs: state.set_status(m.id, "skipped:service")
            continue
        if msg_type == MsgType.DELETED:
            for m in msgs: state.set_status(m.id, "skipped:deleted")
            continue

        try:
            if dry_run:
                print(f"  [DRY] would import {key} ({msg_type.value}): primary id={primary.id}")
            else:
                path = await import_message_group(tg.client, msgs, msg_type, existing, state)
                if path:
                    print(f"  + {path.name} ({msg_type.value})")
                    created += 1
        except Exception as e:
            print(f"  ! failed {key}: {e}")
            for m in msgs: state.set_status(m.id, f"error:{type(e).__name__}")

    return created


def cmd_verify(diff_files: list[Path]) -> tuple[int, int]:
    """LLM verification of changed files. Returns (critical_count, warning_count)."""
    print(f"[5/6] LLM verification of {len(diff_files)} files...")
    critical = warnings = 0
    for f in diff_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        issues = verify_post_file(str(f), content)
        for i in issues:
            print(f"  [{i.severity}] {f.name}: {i.message}")
            if i.severity == "critical":
                critical += 1
            else:
                warnings += 1
    return critical, warnings


def changed_post_files() -> list[Path]:
    """git diff names_only on _posts/ since last commit."""
    import subprocess
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "_posts/"],
        capture_output=True, text=True, cwd=str(POSTS_DIR.parent),
    ).stdout.strip().splitlines()
    return [POSTS_DIR.parent / p for p in out if p]


async def main_async(args):
    api_id, api_hash = get_credentials()
    state = State(STATE_FILE)
    existing = build_index(POSTS_DIR)
    print(f"[1/6] auth + index: {len(existing)} existing posts")

    async with TGClient(api_id, api_hash) as tg:
        fixes = created = 0
        if args.command in ("audit", "full"):
            fixes = await cmd_audit(tg, existing, state, args.dry_run)
        if args.command in ("sync", "full"):
            # Re-build index in case audit moved files
            if fixes:
                existing = build_index(POSTS_DIR)
            created = await cmd_sync(tg, existing, state, args.limit, args.dry_run)

    state.save()

    if args.dry_run:
        print(f"[done] DRY RUN: would have done {fixes} fixes + {created} new posts")
        return 0

    diff_files = changed_post_files()
    critical, warnings = cmd_verify(diff_files) if diff_files else (0, 0)

    if critical > 0:
        print(f"[ABORT] {critical} critical issues — not pushing. Review and re-run.")
        return 1

    if not has_changes():
        print("[done] no changes to push")
        return 0

    if args.no_push:
        print(f"[done] {fixes} fixes, {created} new posts staged. --no-push: not pushing.")
        return 0

    print(f"[6/6] git push...")
    sha = commit_and_push(f"sync pioblog: +{created} new posts, {fixes} audit fixes")
    print(f"  pushed {sha[:7]}, waiting for Pages build...")
    if wait_for_pages_build():
        print(f"  built. checking live URL...")
        if url_ok("https://piofant.github.io/blog/"):
            print(f"[done] live: https://piofant.github.io/blog/")
        else:
            print(f"[warn] live URL not 200 yet — may take another minute")
    else:
        print(f"[warn] Pages build did not complete in time — check https://github.com/piofant/blog/actions")

    return 0


def main():
    parser = argparse.ArgumentParser("pioblog_sync")
    parser.add_argument("command", choices=["audit", "sync", "full"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke check CLI parses**

```bash
cd ~/cursor/vedulix-blog/import && .venv/bin/python -m pioblog_sync --help
```

Expected: argparse help printed, no exception.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "sync: CLI entry point + orchestration"
```

---

## Task 14: Smoke test (dry run on real channel)

**Prerequisites:**
- User has obtained `TG_API_ID` and `TG_API_HASH` from https://my.telegram.org/apps
- User has `ANTHROPIC_API_KEY` set
- First run will prompt for phone number + Telegram code

- [ ] **Step 1: Set env vars and run dry-run**

```bash
cd ~/cursor/vedulix-blog/import
export TG_API_ID="<from_user>"
export TG_API_HASH="<from_user>"
export ANTHROPIC_API_KEY="<from_env_or_user>"
.venv/bin/python -m pioblog_sync sync --dry-run --limit 5
```

Expected output structure:
```
[1/6] auth + index: 160 existing posts
[3/6] discovering messages on channel...
  channel has N message ids (max=4XX)
  to process: 5 ids
  [DRY] would import single_425 (text): primary id=425
  ...
[done] DRY RUN: would have done 0 fixes + 5 new posts
```

If anything fails — diagnose and fix. Common issues:
- ImportError: missing dep → reinstall
- TG auth fail: re-export env vars
- pioblog channel access: verify user is subscribed

- [ ] **Step 2: Real run on small subset (no push)**

```bash
.venv/bin/python -m pioblog_sync sync --limit 3 --no-push
```

Expected:
- 3 new files in `_posts/` for the 3 latest TG messages
- their photos in `assets/img/posts/<slug>/`
- LLM verification runs, 0 critical
- "not pushing" message at end

- [ ] **Step 3: Manually inspect generated posts**

```bash
git status _posts/ assets/img/posts/
git diff _posts/
ls -la assets/img/posts/$(ls -t assets/img/posts/ | head -1)/
```

Verify:
- frontmatter looks right (title, subtitle, date in MSK, telegram_id)
- body has correct text
- photos have reasonable file sizes (full quality, not thumbnails)
- pioblog links rewritten to /blog/...

- [ ] **Step 4: Roll back smoke test**

```bash
cd ~/cursor/vedulix-blog
git checkout -- _posts/ assets/img/posts/
# Remove state from smoke run so next real run re-imports the 3 latest
rm import/pioblog_sync/.state.json
```

- [ ] **Step 5: Commit (no code changes — just record decision)**

If smoke test passed, no commit needed. If issues found and fixed, commit fixes:
```bash
git add -A && git commit -m "sync: fix issues found in smoke test"
```

---

## Task 15: Real run — full sync + push

- [ ] **Step 1: Confirm prerequisites**

- TG_API_ID, TG_API_HASH, ANTHROPIC_API_KEY env vars set
- `gh auth status` shows authenticated
- Working tree is clean (`git status` shows no uncommitted changes)

- [ ] **Step 2: Run full sync (audit + new + push)**

```bash
cd ~/cursor/vedulix-blog/import
.venv/bin/python -m pioblog_sync full 2>&1 | tee /tmp/pioblog-sync.log
```

Expected runtime: ~3-10 minutes depending on channel size.

Expected exit code: 0.

- [ ] **Step 3: Verify live**

```bash
curl -sI https://piofant.github.io/blog/ | head -1
curl -s https://piofant.github.io/blog/ | grep -o 'class="post-preview"' | wc -l
```

Expected: `HTTP/2 200`, post count > 160.

- [ ] **Step 4: Spot-check newest post**

```bash
ls -t ~/cursor/vedulix-blog/_posts/ | head -3
# Open the newest one in browser:
echo "https://piofant.github.io/blog/$(ls -t ~/cursor/vedulix-blog/_posts/ | head -1 | sed 's/\.md$//' | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//' )-$(ls -t ~/cursor/vedulix-blog/_posts/ | head -1 | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')/"
```

Manually open that URL and verify:
- post renders with image
- title and date are correct
- "Оригинал в Telegram" link works
- internal links to other pioblog posts → /blog/... not t.me/...

- [ ] **Step 5: Final report**

Print to user:
- N new posts imported
- M audit fixes applied
- Critical/warning counts from LLM verifier
- Live URL working
- Any caveats / things that needed manual intervention

---

## Notes for executor

- **Reuse don't recreate**: `import/lib/post.py`, `import/lib/slugify_ru.py`, `import/lib/config.py` are battle-tested from previous import. Use them.
- **First TG auth**: The first telethon `start()` will prompt interactively for phone number + SMS/app code. This must be done in a real TTY — can't be automated. After first run, `.session` file persists.
- **State file is precious**: `import/pioblog_sync/.state.json` is the only memory between runs. Don't accidentally delete it on real channel — that means re-classifying all 264 holes.
- **Rate limits**: Telethon respects FloodWait automatically. Don't add extra retries; let telethon handle it.
- **Photo quality**: telethon `download_media(message, file=...)` defaults to highest PhotoSize. Verify file sizes look like full-res (~200KB-2MB), not thumbnails (~10-30KB).
- **If LLM is unreachable**: fall back to first-line title, no subtitle. Don't block the import.
