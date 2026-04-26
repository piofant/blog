"""Telethon wrapper: auth, fetch messages, group albums."""
from __future__ import annotations
import os
import asyncio
from collections import defaultdict
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.custom.message import Message

from pioblog_sync.config import CHANNEL, SESSION_FILE, TG_RATE_LIMIT_SEC


class TGClient:
    def __init__(self, api_id: int, api_hash: str, session_path: Path = SESSION_FILE):
        self.client = TelegramClient(str(session_path), api_id, api_hash)

    async def __aenter__(self):
        await self.client.start()  # prompts phone+code on first run
        return self

    async def __aexit__(self, *exc):
        await self.client.disconnect()

    async def fetch_all_ids(self, channel: str = CHANNEL) -> list[int]:
        """Return all message IDs in channel (ascending)."""
        ids = []
        async for m in self.client.iter_messages(channel, reverse=True):
            ids.append(m.id)
        return ids

    async def get_messages(self, channel: str, ids: list[int]) -> list[Message | None]:
        """Batch get_messages with rate limiting (chunks of 100)."""
        out: list[Message | None] = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            msgs = await self.client.get_messages(channel, ids=chunk)
            out.extend(msgs)
            if i + 100 < len(ids):
                await asyncio.sleep(TG_RATE_LIMIT_SEC)
        return out

    @staticmethod
    def group_albums(messages: list[Message]) -> dict[str, list[Message]]:
        """Bucket messages by grouped_id (str). Loners go in their own bucket."""
        groups: dict[str, list[Message]] = defaultdict(list)
        for m in messages:
            if m is None:
                continue
            key = str(m.grouped_id) if m.grouped_id else f"single_{m.id}"
            groups[key].append(m)
        for k in groups:
            groups[k].sort(key=lambda m: m.id)
        return dict(groups)


def get_credentials() -> tuple[int, str]:
    """Read TG_API_ID and TG_API_HASH from env. Raise ValueError if missing."""
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    if not api_id or not api_hash:
        raise ValueError(
            "Missing TG_API_ID / TG_API_HASH env vars. "
            "Get them from https://my.telegram.org/apps"
        )
    return int(api_id), api_hash
