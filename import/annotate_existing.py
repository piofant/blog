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
            print(f"SKIP: {post.name} (already annotated)")
            continue
        # insert after 'layout: post' line in frontmatter
        lines = content.splitlines(keepends=True)
        out = []
        injected = False
        in_fm = False
        for ln in lines:
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
