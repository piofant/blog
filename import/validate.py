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
        # get this post's own telegram_id to exclude intentional self-references
        own_tid = int(tid_m.group(1)) if tid_m else None
        for m in PIOBLOG_LEFTOVER.finditer(body):
            n = int(m.group(1))
            if n == own_tid:
                continue  # intentional self-reference (e.g. video "Оригинал" link)
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
