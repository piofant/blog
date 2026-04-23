# Notion → Jekyll Sync

Автосинк 3 Notion-страниц в `pages/*.md` (+ `pages/cases/*.md` для sub-pages) через GitHub Actions cron (каждые 15 мин). Картинки — в `assets/images/notion/<slug>/`.

## Локальный запуск

DRY_RUN (без API, создаёт fixture-файлы):

```
cd scripts && npm install && npm run sync:dry
```

С реальным API:

```
cd scripts && NOTION_TOKEN=secret_xxx npm run sync
```

## Настройка GitHub Secrets

Необходимые (основные):
- `NOTION_TOKEN` — Internal Integration Secret из https://www.notion.so/my-integrations

Опциональные:
- `HEALTHCHECK_URL` — https://hc-ping.com/&lt;uuid&gt; для мониторинга cron
- `TG_BOT_TOKEN`, `TG_CHAT_ID` — уведомления в Telegram при падении

## Добавление новой страницы

1. В Notion: `···` → Add connections → выбрать интеграцию (иначе API → 404)
2. Отредактировать `scripts/notion-pages.json` — добавить запись с `page_id`, `target`, `slug`, `title`, `permalink`
3. Запушить — cron подхватит в ближайшие 15 минут
