# Pioblog → Jekyll Import — Design Spec

**Date:** 2026-04-24
**Status:** Design approved, ready for implementation plan
**Source channel:** `https://t.me/pioblog`
**Target site:** `https://piofant.github.io/blog/`
**Jekyll repo:** `~/cursor/vedulix-blog/` (remote `piofant/blog`)

---

## 1. Goal

Импортировать всю историю Telegram-канала `pioblog` (376 сообщений, 2020–2026) как посты в существующий Jekyll-блог с сохранением:
- текстов в точности
- полных оригинальных фото и (где возможно) видео
- дат и хронологии
- всех гиперссылок
- хэштегов (как Jekyll-теги)
- серий из нескольких сообщений (с навигацией между частями)

Существующие 15 постов в `_posts/` остаются нетронутыми, только получают метаданные TG id для корректной перелинковки.

## 2. Scope

### In scope
- HTML-парсер фиксированной выгрузки `ChatExport_2026-04-24 pioblog/messages.html`
- Генерация markdown-файлов в `_posts/` с YAML-frontmatter, корректными title/slug/date/tags
- Копирование медиа (фото, видео <25MB, голосовые, кружочки, аттачи) в `/assets/…/posts/{slug}/`
- Для видео ≥25MB — embed-виджет Telegram + локальный бэкап в `~/piofant-media/`
- Переписывание внутренних ссылок `t.me/pioblog/{N}` → локальные permalink-и
- Детекция и навигация серий («(N/M)», «часть N из M» итп)
- Landing-страницы серий в `/series/{id}/`
- Ручная карта `id_map.yml` для дедупа с 15 существующими постами
- Валидатор (ссылки, картинки, коллизии, dry-build)
- Staging-папка для безопасных повторных прогонов

### Out of scope (вторая итерация)
- Ретаггинг существующих 15 постов
- Перевод тегов в кириллический UX
- Оптимизация весов медиа (resize, LFS, внешнее хранилище)
- Автосклейка серий без явных маркеров

## 3. Architecture

```
ChatExport_2026-04-24 pioblog/           ← сырой TG-дамп (в .gitignore)
├── messages.html
├── photos/           (37 MB, все в оригинале)
├── video_files/      (458 MB, 31 штука)
├── round_video_messages/  (25 MB)
├── voice_messages/   (252 KB)
└── files/            (67 MB, аттачи)
              │
              ▼
      import/parse.py         ← основная логика, идемпотентна
              │
              ▼
import/staging/                         ← изолированная зона, .gitignored
├── _posts/*.md
├── assets/img/posts/{slug}/*.jpg
├── assets/video/posts/{slug}/*.mp4     (только <25 MB)
├── assets/audio/posts/{slug}/*.ogg
├── assets/files/posts/{slug}/*
└── _data/series.yml
              │
   ┌──────────┤
   │          │
   ▼          ▼
import/validate.py      ~/piofant-media/{slug}/...  ← offline-бэкап всех видео, вне репо
   │
   ▼ OK
make promote      ← copy staging/* → реальный репо
   │
   ▼
git commit (батчами по годам) + push
```

**Языки/инструменты:** Python 3.11+, BeautifulSoup4, markdownify, python-slugify, pyyaml. Makefile для команд (`make parse`, `make validate`, `make promote`, `make clean`).

## 4. Parsing a Telegram message

Для каждого `<div class="message default clearfix" id="messageN">` в `messages.html`:

### 4.1 Skip rules

- `type="service"` (по классу `service` в div) — события типа «Channel created», «Channel photo changed»
- Сообщение состоит только из стикера (`<div class="media_wrap"><a class="sticker_wrap">`) без текста

Всё остальное — пост.

### 4.2 Fields

| Поле | Источник |
|---|---|
| `telegram_id` | число из `id="messageN"` |
| `telegram_url` | `https://t.me/pioblog/{N}` |
| `date` | из `<div class="pull_right date" title="DD.MM.YYYY HH:MM:SS UTC±ZZ:ZZ">` → ISO 8601 с таймзоной |
| `title` | первая строка `<div class="text">...</div>` до первого `<br>`/`\n`. Strip markup, ≤ 80 симв. (режем по слову). Fallback: `«Запись от {DD MMMM YYYY}»` по-русски (locale `ru_RU`) |
| `slug` | `{YYYY-MM-DD}-{slugify(title)}-{telegram_id}`. Транслит через `python-slugify` (lowercase, дефисы, без кириллицы) |
| `body` | HTML→Markdown через `markdownify` с кастомными хуками (п. 4.3) |
| `tags` | список из `<a onclick="return ShowHashtag(&quot;X&quot;)">` → `[X1, X2]`. Саму плашку `#X` в теле НЕ убираем |
| `media` | см. п. 5 |

### 4.3 Body transforms

- **Внутренние ссылки `https?://t\.me/pioblog/(\d+)`** → если N в `link_map` (все импортируемые + 15 старых через `id_map.yml`) — заменяем на локальный permalink `/blog/{slug}/`. Если N не в map (удалённое сообщение) — оставляем как есть.
- **Остальные ссылки** — без изменений, включая `t.me/*` на другие каналы и пользователей.
- **Emoji, UTF-8** — без изменений.
- **Формат**: `<strong>`→`**`, `<em>`→`*`, `<code>`→`` ` ``, blockquote→`>`, `<br>`→перевод строки, `<a>`→`[text](url)`.
- **Изображения** размещаются в теле на месте их появления в HTML через `![{alt}](/assets/img/posts/{slug}/photo_N.jpg)` (п. 5.1).

### 4.4 Forwarded messages

Если есть `<div class="forwarded body">`, в начало тела добавляем:
```md
> Переслано из **{source_name}**{если есть source_url: ([оригинал](url))}
```
Саму суть форварда разбираем теми же правилами как обычное сообщение.

### 4.5 Polls

`<div class="media_poll">` → конвертируем в:
```md
**Опрос:** {question}
- {option 1}
- {option 2}
- ...
```
Без цифр голосов.

### 4.6 Reactions, views

Игнорируем полностью (шум).

## 5. Media handling

### 5.1 Photos

- Все референсы `<a class="photo_wrap" href="photos/photo_N@DATE.jpg">` → копия в `staging/assets/img/posts/{slug}/photo_{N}.jpg`
- Игнорируем `_thumb.jpg` (копируем только full-quality)
- В теле поста в месте появления — `![](/assets/img/posts/{slug}/photo_{N}.jpg)` на отдельной строке
- Для первой фотки в посте — дополнительно проставляем `thumbnail-img: /assets/img/posts/{slug}/photo_{N}.jpg` в frontmatter (для feed/archive cards)

### 5.2 Videos (self-hosted, <25 MB)

- `<a class="video_file_wrap" href="video_files/X.mp4">` или аналог → копия в `staging/assets/video/posts/{slug}/video_{index}.mp4`
- В теле:
```html
<video controls preload="metadata" style="width:100%;max-width:620px">
  <source src="/assets/video/posts/{slug}/video_{i}.mp4" type="video/mp4">
</video>
<p><a href="https://t.me/pioblog/{N}">Оригинал в Telegram →</a></p>
```

### 5.3 Videos (embed, ≥25 MB)

- Файл НЕ копируется в staging. Только локальный бэкап в `~/piofant-media/{slug}/`.
- В теле:
```html
<script async src="https://telegram.org/js/telegram-widget.js?22"
        data-telegram-post="pioblog/{N}" data-width="100%"></script>
<p><a href="https://t.me/pioblog/{N}">Оригинал в Telegram →</a></p>
```

Порог 25 MB — константа в конфиге парсера, меняется одним числом.

### 5.4 Round video messages (кружочки)

Всегда self-host. Такой же `<video>`-блок как в 5.2, но `style="width:240px;border-radius:50%"`.

### 5.5 Voice messages

`<a class="voice_message">`. Self-host в `staging/assets/audio/posts/{slug}/voice_{i}.ogg`:
```html
<audio controls src="/assets/audio/posts/{slug}/voice_{i}.ogg"></audio>
```

### 5.6 Attached files (`files/`)

Self-host (<25 MB) в `staging/assets/files/posts/{slug}/{orig_filename}`:
```md
📎 [{orig_filename}](/assets/files/posts/{slug}/{orig_filename}) ({size})
```
Для файлов ≥25 MB — только ссылка на `t.me/pioblog/{N}` и бэкап в `~/piofant-media/`.

### 5.7 Stickers inside a post

Если пост содержит и текст, и стикеры — стикеры копируем как фото через `<img>`, привязываем к `{slug}/sticker_{i}.webp`. Без описания в alt.

## 6. Frontmatter schema

```yaml
---
layout: post
title: "Про ИИ-саммари в контент-машине — сколько $ принесло"
date: 2026-01-13 21:43:00 +0300
tags: [контент, эксперименты, аналитика]
telegram_id: 373
telegram_url: https://t.me/pioblog/373
thumbnail-img: /assets/img/posts/2026-01-13-pro-ii-sammari-373/photo_1.jpg  # если есть
# опционально, только для серий:
series_id: yandex-internship
series_part: 3
series_total: 5
---
```

## 7. Dedup with existing 15 posts

### 7.1 Problem

Существующие 15 постов в `_posts/` — редактированы руками. Их нельзя перегенерить. Но их TG id-шники нужны в `link_map` чтобы новые посты правильно перелинковывались.

### 7.2 Solution

**Файл `import/id_map.yml`** — source of truth, редактируется вручную:

```yaml
# Карта: telegram_id → существующий jekyll permalink
# Генерится первым проходом парсера (по совпадению даты + первой строки),
# затем проверяется руками.

86:  /blog/ingress/                             # 2022-03-12-ingress.md
109: /blog/consuming-self-development-content/  # 2022-07-17-...
# ... etc
```

Парсер:
1. Читает `_posts/*.md`, извлекает `date` из имени файла, строит индекс.
2. Для каждого из 376 TG-сообщений пробует сматчить по (дата + первые 40 символов). Кандидаты заносит в `id_map.yml`.
3. Пользователь вручную правит `id_map.yml`, подтверждая/исправляя матчи.
4. Второй проход парсера использует утверждённую карту.

**TG id-шники существующих 15 постов** после утверждения карты дописываются в их frontmatter как `telegram_id` и `telegram_url`. Это единственное изменение в существующих файлах — минимально инвазивное.

### 7.3 Conflict resolution

Если парсер сгенерил слог, который конфликтует с существующим файлом в `_posts/` — в staging создаётся с суффиксом `-{telegram_id}`, валидатор такой случай ловит и требует ручного разрешения (либо юзер обновляет `id_map.yml`, либо переименовывает).

## 8. Series detection

### 8.1 Явные маркеры (регэкс по первой строке тела)

- `\((\d+)/(\d+)\)` — `(1/5)`, `(2/5)`
- `\[(\d+)/(\d+)\]` — `[1/5]`
- `^часть\s+(\d+)(?:\s+из\s+(\d+))?` — «часть 1», «часть 1 из 5»
- `^(\d+)/(\d+)` — `1/5 в начале строки`
- `#часть(\d+)` — `#часть1`

Если найден маркер `part/total`, и предыдущее сообщение того же дня не является частью серии, создаём новую серию. Все последующие подряд идущие с совпадающим `total` и инкрементом `part` → в ту же серию.

### 8.2 ID серии

`series_id = slugify(title первого поста)`, пример `yandex-internship-road`. Хранится в `_data/series.yml`:

```yaml
yandex-internship-road:
  title: "Как я стажировался в Яндексе"
  total: 5
  parts:
    - { part: 1, telegram_id: 130, permalink: /blog/... }
    - { part: 2, telegram_id: 132, permalink: /blog/... }
    # ...
```

### 8.3 Рендеринг

**Landing `/series/{id}/`** — новая страница-коллекция. Генерим `staging/series/{id}.md` с layout `series`, Jekyll сам превратит в `/series/{id}/`. На странице: заголовок серии, список частей с датами и заголовками постов.

**В посте** — include в конце `_layouts/post.html`:

```html
{% if page.series_id %}
  {% include series-nav.html %}
{% endif %}
```

`_includes/series-nav.html` рендерит:
```
━━━━━━━━━━━━
{Заголовок серии} · Часть 2 из 5
← Часть 1  ·  [Оглавление]  ·  Часть 3 →
```

## 9. Pipeline commands

```Makefile
# import/Makefile
parse:       ## Парсит ChatExport_*/messages.html → staging/
validate:    ## Проверяет staging — ссылки, картинки, slug-коллизии, Jekyll dry-build
promote:     ## Копирует staging/ → реальный репо (_posts/, assets/, _data/, series/, _includes/)
clean:       ## Удаляет staging/
all:         parse validate   ## Прогон без промоута
```

## 10. Validation (`validate.py`)

Список проверок, все должны пройти перед `promote`:

| # | Проверка |
|---|---|
| 1 | Все `![...](/assets/.../...)` в staging/_posts указывают на реально существующие файлы в staging/assets |
| 2 | Все `<video>`, `<audio>` с `src="/assets/..."` указывают на реально существующие файлы |
| 3 | Все `<script data-telegram-post="pioblog/N">` имеют N, существующий в исходном HTML |
| 4 | Нет оставшихся `https?://t\.me/pioblog/\d+` в текстах постов, у которых N присутствует в `link_map` |
| 5 | Slug-коллизии в staging/_posts — нет |
| 6 | Дубли `telegram_id` в frontmatter-ах — нет |
| 7 | Каждый пост имеет `title`, `date`, `layout: post`, `telegram_id`, `telegram_url` |
| 8 | Нет orphan-файлов в staging/assets (не привязаны ни к одному посту) |
| 9 | `bundle exec jekyll build --destination /tmp/jekyll_check` — проходит без errors |
| 10 | Сумма размеров staging/assets ≤ 500 MB (soft warning, не блокирует) |
| 11 | Спец-проверка: все 15 существующих постов в `_posts/` имеют валидный `telegram_id` (значит `id_map.yml` полный) |

Вывод — табличный отчёт, по секциям. Exit code 1 если любая проверка #1–9 фейлится.

## 11. Manual validation pass

После `validate.py` ОК — валидатор печатает отчёт для глаз:

- **Список всех сгенерированных заголовков по годам** — скроллим, находим кривые
- **10 случайных полных постов** (title + первые 200 симв. + список медиа) — смотрим, ничего ли не съелось
- **Список серий** (id, title, total parts) — глазами проверяем что склеилось правильно
- **Все 2 видео ≥25 MB** — кликаем по embed-ам, убеждаемся что TG-виджет рендерит корректно

Что не нравится — правим в staging (руками в markdown или поправив `parse.py` и перепрогнав). Повторяем до счастья. Потом — `make promote`.

## 12. Commit strategy

После promote — 6 git-коммитов, по годам:

1. `import pioblog 2020 posts (N posts)`
2. `import pioblog 2021 posts (N posts, excluding N pre-existing)`
3. `import pioblog 2022 posts (N posts, excluding N pre-existing)`
4. `import pioblog 2023 posts (N posts)`
5. `import pioblog 2024 posts (N posts)`
6. `import pioblog 2025-2026 posts (N posts)`

Отдельным коммитом **до** года-батчей — servicing:
- `.gitignore`: exclude ChatExport + staging
- `_layouts/post.html`: series-nav include
- `_includes/series-nav.html`
- `_data/series.yml`
- `series/{id}.md` (landing pages)
- `import/` (parse.py, validate.py, Makefile, id_map.yml)
- `assets/img/posts/`, `assets/video/posts/`, `assets/audio/posts/`, `assets/files/posts/` — фикстуры

Потом — push в `origin/master`, Pages собирает.

## 13. Rollback

Если на Pages что-то рассыпалось — `git revert {hash}` последнего батча, pages пересобирает. Батчи по годам → гранулярный откат без потери остального.

## 14. Edge cases

| Кейс | Поведение |
|---|---|
| Сообщение отредактировано в TG после первого экспорта | Импортим последнюю версию из дампа. Нет нужды отслеживать правки. |
| Пустой пост (ни текста, ни медиа после фильтрации стикеров) | Скип с логом WARNING |
| Сообщение с только одним кружочком, без текста | Title = `Видеосообщение от DATE` |
| Видео или фото без расширения в `href` | Пробуем угадать по mime из HTML, fallback `.mp4`/`.jpg` |
| Файл ≥100 MB в `files/` | Не копируем. Рендерим только ссылку на TG. Backup в `~/piofant-media/` |
| Слоган с emoji в title («📍 Популярные посты») | Emoji как есть, в slug попадут только латинские символы |
| Один `telegram_id` маппится на несколько постов в `id_map.yml` | Ошибка валидации (#6) |
| Пост-кросспост в другой TG-канал | Оставляем ссылку `t.me/other_channel/N` как есть |

## 15. Risks and mitigations

| Риск | Mitigation |
|---|---|
| 458 MB видео случайно попадают в git | `.gitignore ChatExport_*/` уже добавлен. Staging тоже игнорится |
| Неверное совпадение TG-id ↔ существующий пост в `id_map.yml` | Первый проход парсера печатает топ-5 кандидатов с match score; юзер проверяет руками; валидатор #11 ловит незамапленные |
| Ломает стиль оформления (overrides.css из прошлого рефреша) | Используем тот же layout `post`, переменные темы. Добавляем только `series-nav.html`, стили туда же в `overrides.css` небольшим блоком |
| GitHub Pages отказывается собирать сайт > 1 GB | Мониторим через `du -sh .` после promote; 300 MB — в запасе |
| Кривой title у постов без текста | Fallback на дату по-русски — приемлемо; валидатор печатает их список для ручной правки |
| Серия разбита между двумя годами (в коммит-батчах) | Landing-страница генерится по `_data/series.yml`, коммитится в servicing-коммите до batch-ей |

## 16. Acceptance criteria

- [ ] `make all` проходит без ошибок на свежем дампе
- [ ] Все 376 - (service + pure-sticker) сообщений стали постами
- [ ] 15 существующих постов не изменились (кроме добавления `telegram_id`/`telegram_url` в frontmatter)
- [ ] 29 видео self-hosted, 2 — через TG embed
- [ ] Все `t.me/pioblog/N` внутри текстов, у которых N в `link_map`, переписаны на локальные permalink-и
- [ ] Все серии (если найдены) имеют landing `/series/{id}/` и навигацию в постах
- [ ] `jekyll build` без ошибок и warnings
- [ ] `piofant.github.io/blog/` после push показывает посты корректно, картинки грузятся, видео воспроизводятся
- [ ] Архив (`/archive/`) автоматически заполнился всеми годами 2020–2026

---

**Next step:** после approve спеца — `writing-plans` → `docs/superpowers/plans/2026-04-24-pioblog-import.md`.
