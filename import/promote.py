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
