import pytest
from unittest.mock import MagicMock
from pioblog_sync.classifier import classify, MsgType


def _msg(text=None, photo=None, video=None, voice=None, poll=None,
         document=None, forward=None, action=None, grouped_id=None):
    m = MagicMock()
    m.text = text or ""
    m.message = text or ""
    m.photo = photo
    m.video = video
    m.voice = voice
    m.poll = poll
    m.document = document
    m.forward = forward
    m.action = action  # service action (pin, photo change)
    m.grouped_id = grouped_id
    return m


def test_classify_none_is_deleted():
    assert classify(None) == MsgType.DELETED


def test_text_only():
    assert classify(_msg(text="hello world")) == MsgType.TEXT


def test_album_member():
    # photo with grouped_id -> album
    assert classify(_msg(text="caption", photo=True, grouped_id=12345)) == MsgType.ALBUM_MEMBER


def test_voice_only():
    assert classify(_msg(voice=True)) == MsgType.VOICE


def test_video_only():
    assert classify(_msg(video=True)) == MsgType.VIDEO


def test_poll():
    assert classify(_msg(poll=True)) == MsgType.POLL


def test_forward():
    fwd = MagicMock()
    assert classify(_msg(text="forwarded text", forward=fwd)) == MsgType.FORWARDED


def test_service_action():
    act = MagicMock()
    assert classify(_msg(action=act)) == MsgType.SERVICE


def test_text_with_photo_no_group():
    # single photo with caption -> just TEXT (single-photo post)
    assert classify(_msg(text="caption", photo=True)) == MsgType.TEXT
