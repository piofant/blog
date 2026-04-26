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
        raise RuntimeError(
            f"cmd failed: {' '.join(args)}\n"
            f"stdout: {res.stdout}\nstderr: {res.stderr}"
        )
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
