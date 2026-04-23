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
