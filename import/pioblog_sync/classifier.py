"""Classify a Telegram message into one of N categories."""
from __future__ import annotations
from enum import Enum


class MsgType(str, Enum):
    TEXT = "text"
    ALBUM_MEMBER = "album_member"
    VOICE = "voice"
    VIDEO = "video"
    POLL = "poll"
    FORWARDED = "forwarded"
    SERVICE = "service"
    DELETED = "deleted"


def classify(message) -> MsgType:
    """Return classification of a Telethon Message (or None for deleted)."""
    if message is None:
        return MsgType.DELETED
    if message.action is not None:
        return MsgType.SERVICE
    if message.poll is not None:
        return MsgType.POLL
    if message.forward is not None:
        return MsgType.FORWARDED
    if message.grouped_id is not None:
        return MsgType.ALBUM_MEMBER
    if message.voice is not None:
        return MsgType.VOICE
    if message.video is not None and not (message.text or "").strip():
        return MsgType.VIDEO
    return MsgType.TEXT
