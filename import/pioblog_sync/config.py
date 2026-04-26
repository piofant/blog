"""Constants for pioblog sync."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POSTS_DIR = REPO_ROOT / "_posts"
ASSETS_DIR = REPO_ROOT / "assets" / "img" / "posts"
SYNC_DIR = REPO_ROOT / "import" / "pioblog_sync"
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
