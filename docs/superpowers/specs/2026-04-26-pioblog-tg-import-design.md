# Pioblog Telegram → Jekyll Import — Design Spec

**Date:** 2026-04-26
**Repo:** `~/cursor/vedulix-blog/` → `https://github.com/piofant/blog` → `https://piofant.github.io/blog/`
**Source:** Telegram channel `@pioblog`

## Goal

Догрузить недостающие посты из TG-канала `pioblog` в Jekyll-сайт и провести аудит уже импортированных, ничего не теряя: правильные даты, фото в полном качестве, гиперссылки сохранены и переписаны на внутренние где возможно.

## Current state

- Уже импортировано: 160 постов в `_posts/` (telegram_id 4–424).
- 264 ID в диапазоне [1..424] отсутствуют — это альбомы / голос-видео-only / форварды / опросы / сервисные / возможно потерянные текстовые.
- На канале последний известный ID ≥ 430 (425, 426, 430 точно есть, не импортированы).
- Фото лежат в `assets/img/posts/<slug>/`.
- Внутренние ссылки на pioblog уже частично переписаны в формат `/blog/<slug>-<id>-YYYY-MM-DD/`.

## Scope

### In scope (v1)
- Импорт всех новых TG-постов с ID > 424.
- Аудит дыр: классификация всех 264 пропущенных ID, импорт «найденных» текстовых / голос-видео / опросов / форвардов.
- Аудит существующих 160 постов: проверка дат, фото в полном качестве, переписанных ссылок.
- Автофиксы безопасных вещей (фото, ссылки, дата, thumbnail) на существующих постах. Title/subtitle/тело **не трогаются**.
- LLM-проверка после импорта: ищет странности (поломанная разметка, обрезанный текст, потерянные подписи), блокирует push при критичных проблемах.
- Полный автомат: скрипт сам делает `git add / commit / push` и ждёт билда GitHub Pages.

### Out of scope (v2 / отдельной сессией)
- Теги / классификация постов по темам.
- Редактирование текста существующих постов.
- Импорт реакций, views, комментариев.

## Architecture

Один Python-скрипт `scripts/import_pioblog.py` с подкомандами:

```
python scripts/import_pioblog.py audit   # только аудит существующих 160
python scripts/import_pioblog.py sync    # только догрузка новых + классификация дыр
python scripts/import_pioblog.py full    # audit + sync (default для первого запуска)
```

### Зависимости
- `telethon` — TG client с авторизацией через user account (нужно для полного качества фото и `grouped_id` альбомов).
- `anthropic` SDK — Claude Haiku для генерации title/subtitle и финальной проверки.
- `python-slugify` — транслит для имён файлов.
- `python-frontmatter` — парсинг/запись YAML фронтматтера.
- `Pillow` — сравнение размеров фото при аудите.

### Состояние

`scripts/.pioblog_state.json` (в `.gitignore`):
```json
{
  "last_synced_id": 430,
  "processed_ids": {"4": "imported", "1": "skipped:nonexistent", "45": "skipped:voice"},
  "photo_hashes": {"path/to/photo.jpg": "sha256..."},
  "album_groups": {"<grouped_id>": [422, 423, 424]}
}
```

**Идемпотентность:** скрипт всегда фетчит полную историю канала (`iter_messages` без offset), но для каждого ID смотрит в `processed_ids` — если статус не изменился (`imported` остаётся `imported`), пост пропускается. Audit-проверки (фото-качество, ссылки) выполняются всегда — они дёшевы и сами идемпотентны.

**Auth первого запуска:** telethon попросит phone number и код подтверждения из TG один раз, дальше работает через session-файл.

### Auth

Telethon session-файл `scripts/.pioblog.session` (в `.gitignore`).
API credentials (`api_id`, `api_hash`) — переменные окружения `TG_API_ID`, `TG_API_HASH`. `ANTHROPIC_API_KEY` для LLM.

## Import rules

### Mapping: TG message → Jekyll file

**Имя файла:**
```
_posts/YYYY-MM-DD-<translit-первых-слов>-<telegram_id>.md
```

**Альбомы** (несколько `message_id` под одним `grouped_id`): склеиваются в один файл, имя — по самому раннему ID, фото идут в порядке отправки.

### Frontmatter

```yaml
---
layout: post
title: "<LLM-generated title, ≤80 chars>"
date: <YYYY-MM-DD HH:MM:SS +0300>
subtitle: "<LLM-generated subtitle, ≤140 chars>"
thumbnail-img: /blog/assets/img/posts/<slug>/<first_photo>
telegram_id: <int>
telegram_url: https://t.me/pioblog/<id>
---
```

Для альбомов `telegram_id` = самый ранний ID, `telegram_url` — на него же.

### Body conversion

| TG entity | Markdown |
|---|---|
| **bold** / *italic* / `code` / strikethrough | соответствующий markdown |
| inline link | `[text](url)` |
| `@mention` (canonical channel) | `[@channel](https://t.me/channel)` |
| custom emoji | unicode fallback или картинка-инлайн |
| spoiler | обернуть в `<span class="spoiler">...</span>` |

### Link rewriting

Ссылки `t.me/pioblog/<N>` в теле:
- если N импортирован → `[текст](/blog/<slug>/)`,
- если N — голос/видео/опрос/форвард (импортирован, но не как «текст») → `/blog/<slug>/`,
- если N — служебка / удалённое / не существует → оставить `https://t.me/pioblog/N`.

Внизу каждого поста:
```markdown
[Оригинал в Telegram →](https://t.me/pioblog/<id>)
```

### Media

**Фото:**
- Скачиваются в `assets/img/posts/<slug>/photo_<seq>.jpg` через `client.download_media(message, ...)` с самым большим `PhotoSize`.
- Первая → `thumbnail-img` фронтматтера.
- Все → встраиваются в тело: `![](/blog/assets/img/posts/<slug>/photo_<seq>.jpg)` с подписью если была.

**Видео:** `assets/img/posts/<slug>/video_<seq>.mp4`, встраивается через `<video controls src="..."></video>`.

**Голосовые:** `assets/img/posts/<slug>/voice_<seq>.ogg`, встраивается через `<audio controls src="..."></audio>`.

**Стикеры:** скачиваются как webp/webm → встраиваются как `<img>` или `<video>`.

**Опросы:** статичный снимок результатов в виде markdown-списка с процентами:
```markdown
**Опрос:** Какой питон лучше?
- Python 3.12 — 67% (123 голоса)
- Python 3.11 — 23% (42 голоса)
- Python 2.7 — 10% (19 голосов)
```

### Date / timezone

`message.date` (UTC из Telethon) → конвертируется в `+0300` (Europe/Moscow).
Формат: `YYYY-MM-DD HH:MM:SS +0300`.

### Title / subtitle generation

LLM (`claude-haiku-4-5`) получает body поста, возвращает:
- `title` — ≤80 символов, в стиле автора (lowercase, без точки в конце, может содержать эмодзи в начале),
- `subtitle` — ≤140 символов, краткий тизер.

Если body ≤ 30 символов или это медиа-only пост — title = первые слова, subtitle = пустая.

## Audit logic

### Для существующих 160 постов

Для каждого:
1. **Дата:** сравнить `frontmatter.date` с `message.date`. Если расхождение > 1 дня — переименовать файл (`YYYY-MM-DD` префикс) и обновить `date:` в frontmatter.
2. **Фото:** для каждой фотки в TG-сообщении проверить, что соответствующий файл есть в `assets/img/posts/<slug>/`. Если нет — скачать.
3. **Качество фото:** через Pillow сравнить площадь пикселей в репо vs `PhotoSize` оригинала. Если в репо меньше — пере-скачать и заменить.
4. **Thumbnail:** проверить, что `thumbnail-img` ведёт на существующий файл. Если нет — поставить первую фотку.
5. **Внутренние ссылки:** для каждой `t.me/pioblog/<N>` в теле — если N импортирован, переписать на `/blog/<slug>/`.

Title / subtitle / тело поста **не модифицируются**.

### Для 264 «дырявых» ID

Для каждого ID:
1. Запросить `client.get_messages('pioblog', ids=[N])`.
2. Классифицировать:
   - Существует и `grouped_id` совпадает с импортированным постом → **album member** → добавить медиа к тому посту.
   - Голос/видео без текста → **voice/video** → импортировать как новый пост.
   - Опрос → **poll** → импортировать как новый пост.
   - Форвард (есть `forward_from`) → **forwarded** → импортировать с пометкой «↻ переслано из @канал».
   - Текст без специфики → **text** → импортировать как новый.
   - Служебка → **service** → пропустить, залогировать.
   - `None` (удалено) → **deleted** → пропустить, залогировать.

## LLM verification

После импорта Claude Haiku получает diff (новые + изменённые файлы) и проверяет:
- разметка не поломана (нет одиночных `*`, незакрытых тегов),
- текст не обрезан на середине предложения,
- все `![](...)` ссылаются на существующие файлы,
- нет дубликатов абзацев,
- нет очевидной рассинхронизации title vs body.

**Severity levels:**
- **critical** — текст обрезан, разметка сломана так что Jekyll-билд упадёт, ссылка ведёт на несуществующий файл `assets/img/posts/...`. → скрипт **не пушит**, печатает список проблем в консоль, exit code 1.
- **warning** — потенциально странная вещь, не блокирует (например, заголовок повторяет первую строку body, или title слишком короткий). → пушит, печатает предупреждения.

## Workflow

```
$ python scripts/import_pioblog.py full
[1/6] auth: ok (vova_lutsenko)
[2/6] fetching channel history... 430 messages
[3/6] audit existing 160 posts:
  - 3 photos re-downloaded in higher quality
  - 12 internal links rewritten
  - 1 thumbnail fixed
[4/6] sync: 6 new posts, 8 album members merged, 4 voice imported, 2 polls imported
[5/6] LLM verification: ok, no critical issues, 2 warnings
[6/6] git push... done. waiting for Pages build... built (45s).
done.
  + 12 new posts
  + 16 audit fixes
  live: https://piofant.github.io/blog/
```

## Safety

- Скрипт **никогда** не удаляет существующие файлы — только дозаливает / обновляет.
- Перед `git commit` — sanity-check: `len(_posts/*.md) >= 160`. Если меньше — abort.
- Title/subtitle/тело существующих постов не модифицируются никогда (только дата/фото/ссылки).
- Telethon session-файл и `.pioblog_state.json` в `.gitignore`.
- Между запусками TG API — лимит 1 req/sec для bulk download (избежать flood-wait).

## Files affected

**Новые:**
- `scripts/import_pioblog.py`
- `scripts/.gitignore` (внутри: `.pioblog_state.json`, `.pioblog.session`)

**Возможно изменённые (audit):**
- `_posts/*.md` — даты, thumbnail, внутренние ссылки.
- `assets/img/posts/<slug>/*` — дозалитые фото в полном качестве.

**Новые (sync):**
- `_posts/YYYY-MM-DD-<slug>-<id>.md` — новые посты.
- `assets/img/posts/<slug>/*` — медиа новых постов.

**Корневой `.gitignore`** — дополнить.
