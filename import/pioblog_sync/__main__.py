"""CLI: python -m pioblog_sync [audit|sync|full] [--dry-run] [--limit N] [--no-push]"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

# Ensure import/ is on sys.path so `from lib.*` works
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pioblog_sync.config import POSTS_DIR, STATE_FILE
from pioblog_sync.state import State
from pioblog_sync.existing import build_index
from pioblog_sync.tg_client import TGClient, get_credentials
from pioblog_sync.classifier import classify, MsgType
from pioblog_sync.sync_new import import_message_group
from pioblog_sync.audit import audit_post
from pioblog_sync.llm import verify_post_file
from pioblog_sync.git_ops import (
    commit_and_push, wait_for_pages_build, url_ok, has_changes,
)


async def cmd_audit(tg: TGClient, existing: dict, state: State, dry_run: bool) -> int:
    print(f"[2/6] audit existing {len(existing)} posts...")
    ids = sorted(existing.keys())
    messages = await tg.get_messages("pioblog", ids)
    fixes = 0
    for tg_id, msg in zip(ids, messages):
        if msg is None:
            continue
        post = existing[tg_id]
        post_fixes = await audit_post(tg.client, msg, post, existing)
        for f in post_fixes:
            print(f"  - {post.path.name}: {f.kind} — {f.description}")
            fixes += 1
    print(f"  audit: {fixes} fixes applied")
    return fixes


async def cmd_sync(tg: TGClient, existing: dict, state: State,
                   limit: int | None, dry_run: bool) -> int:
    print(f"[3/6] discovering messages on channel...")
    all_ids = await tg.fetch_all_ids("pioblog")
    print(f"  channel has {len(all_ids)} message ids (max={max(all_ids)})")

    todo = [i for i in all_ids if i not in existing and state.get_status(i) is None]
    if limit:
        todo = todo[-limit:]
    print(f"  to process: {len(todo)} ids")

    if not todo:
        return 0

    messages = await tg.get_messages("pioblog", todo)
    # Group by grouped_id (album); align Nones to their requested ids
    groups: dict[str, list] = {}
    for requested_id, m in zip(todo, messages):
        if m is None:
            state.set_status(requested_id, "skipped:deleted")
            continue
        key = str(m.grouped_id) if m.grouped_id else f"single_{m.id}"
        groups.setdefault(key, []).append(m)
    for k in groups:
        groups[k].sort(key=lambda x: x.id)

    created = 0
    for key, msgs in groups.items():
        primary = msgs[0]
        msg_type = classify(primary)

        if msg_type == MsgType.SERVICE:
            for m in msgs:
                state.set_status(m.id, "skipped:service")
            continue
        if msg_type == MsgType.DELETED:
            for m in msgs:
                state.set_status(m.id, "skipped:deleted")
            continue

        try:
            if dry_run:
                print(f"  [DRY] would import {key} ({msg_type.value}): primary id={primary.id}")
            else:
                path = await import_message_group(
                    tg.client, msgs, msg_type, existing, state
                )
                if path:
                    print(f"  + {path.name} ({msg_type.value})")
                    created += 1
        except Exception as e:
            print(f"  ! failed {key}: {e}")
            for m in msgs:
                state.set_status(m.id, f"error:{type(e).__name__}")

    return created


def cmd_verify(diff_files: list[Path]) -> tuple[int, int]:
    """LLM verification of changed files. Returns (critical_count, warning_count)."""
    print(f"[5/6] LLM verification of {len(diff_files)} files...")
    critical = warnings = 0
    for f in diff_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        issues = verify_post_file(str(f), content)
        for i in issues:
            print(f"  [{i.severity}] {f.name}: {i.message}")
            if i.severity == "critical":
                critical += 1
            else:
                warnings += 1
    return critical, warnings


def changed_post_files() -> list[Path]:
    """git diff names_only on _posts/ since last commit."""
    import subprocess
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "_posts/"],
        capture_output=True, text=True, cwd=str(POSTS_DIR.parent),
    ).stdout.strip().splitlines()
    return [POSTS_DIR.parent / p for p in out if p]


async def main_async(args):
    api_id, api_hash = get_credentials()
    state = State(STATE_FILE)
    existing = build_index(POSTS_DIR)
    print(f"[1/6] auth + index: {len(existing)} existing posts")

    async with TGClient(api_id, api_hash) as tg:
        fixes = created = 0
        if args.command in ("audit", "full"):
            fixes = await cmd_audit(tg, existing, state, args.dry_run)
        if args.command in ("sync", "full"):
            # Re-build index in case audit moved files
            if fixes:
                existing = build_index(POSTS_DIR)
            created = await cmd_sync(tg, existing, state, args.limit, args.dry_run)

    state.save()

    if args.dry_run:
        print(f"[done] DRY RUN: would have done {fixes} fixes + {created} new posts")
        return 0

    diff_files = changed_post_files()
    critical, warnings = cmd_verify(diff_files) if diff_files else (0, 0)

    if critical > 0:
        print(f"[ABORT] {critical} critical issues — not pushing. Review and re-run.")
        return 1

    if not has_changes():
        print("[done] no changes to push")
        return 0

    if args.no_push:
        print(f"[done] {fixes} fixes, {created} new posts staged. --no-push: not pushing.")
        return 0

    print(f"[6/6] git push...")
    sha = commit_and_push(f"sync pioblog: +{created} new posts, {fixes} audit fixes")
    print(f"  pushed {sha[:7]}, waiting for Pages build...")
    if wait_for_pages_build():
        print(f"  built. checking live URL...")
        if url_ok("https://piofant.github.io/blog/"):
            print(f"[done] live: https://piofant.github.io/blog/")
        else:
            print(f"[warn] live URL not 200 yet — may take another minute")
    else:
        print(f"[warn] Pages build did not complete in time — check https://github.com/piofant/blog/actions")

    return 0


def main():
    parser = argparse.ArgumentParser("pioblog_sync")
    parser.add_argument("command", choices=["audit", "sync", "full"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
