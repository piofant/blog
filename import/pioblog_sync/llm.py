"""Claude Haiku for title/subtitle generation and post-import verification."""
from __future__ import annotations
import json
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


def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        # ```json\n...\n```
        parts = raw.split("```", 2)
        if len(parts) >= 2:
            inner = parts[1]
            # Remove leading 'json' marker if present
            if inner.lstrip().lower().startswith("json"):
                inner = inner.lstrip()[4:]
            raw = inner.strip()
            # If trailing fence remains
            if raw.endswith("```"):
                raw = raw[:-3].strip()
    return raw


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
    try:
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_code_fences(resp.content[0].text)
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
    try:
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_code_fences(resp.content[0].text)
        arr = json.loads(raw)
        return [
            VerificationIssue(
                severity=i["severity"], file=filepath, message=i["message"]
            )
            for i in arr
        ]
    except Exception:
        return []
