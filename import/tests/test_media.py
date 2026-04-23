from pathlib import Path
from bs4 import BeautifulSoup
from lib.media import extract_media, MediaItem, MediaKind

FIXTURE = Path(__file__).parent / "fixtures" / "messages_sample.html"

def _msg(mid: int):
    soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")
    return soup.find("div", id=f"message{mid}")

def test_photo_extracted_fullquality_not_thumb():
    items = extract_media(_msg(14))
    assert len(items) == 1
    assert items[0].kind == MediaKind.PHOTO
    assert items[0].rel_path == "photos/photo_2@18-08-2020.jpg"
    assert "_thumb" not in items[0].rel_path

def test_video_small_declared_size_parsed():
    items = extract_media(_msg(15))
    assert len(items) == 1
    v = items[0]
    assert v.kind == MediaKind.VIDEO
    assert v.rel_path == "video_files/video_1.mp4"
    # parser extracts declared size for routing hint (real size checked on copy)
    assert v.declared_mb == 5.0

def test_video_large_declared_50mb():
    v = extract_media(_msg(16))[0]
    assert v.declared_mb == 50.0

def test_no_media_in_text_only():
    assert extract_media(_msg(10)) == []

def test_no_media_in_photo_only_no_text():
    # message 13 has only photo → still returns it as media
    items = extract_media(_msg(13))
    assert len(items) == 1
    assert items[0].kind == MediaKind.PHOTO

import tempfile
from lib.media import copy_media, MediaCopyResult

def test_copy_small_video_goes_to_staging_and_backup(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    (dump / "video_files").mkdir(parents=True)
    f = dump / "video_files" / "v.mp4"
    f.write_bytes(b"\0" * (5 * 1024 * 1024))  # 5 MB
    item = MediaItem(MediaKind.VIDEO, "video_files/v.mp4", declared_mb=5.0)
    r = copy_media(item, dump, staging, backup, slug="my-post", tg_id=42)
    assert r.in_staging is True
    assert r.embed is False
    assert (staging / "assets" / "video" / "posts" / "my-post").exists()
    assert (backup / "my-post").exists()

def test_copy_large_video_only_backup_and_embed(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    (dump / "video_files").mkdir(parents=True)
    f = dump / "video_files" / "big.mp4"
    f.write_bytes(b"\0" * (30 * 1024 * 1024))  # 30 MB
    item = MediaItem(MediaKind.VIDEO, "video_files/big.mp4", declared_mb=30.0)
    r = copy_media(item, dump, staging, backup, slug="lecture", tg_id=100)
    assert r.in_staging is False
    assert r.embed is True
    assert not (staging / "assets" / "video" / "posts" / "lecture").exists()
    assert (backup / "lecture" / "big.mp4").exists()

def test_photo_always_copied(tmp_path):
    dump = tmp_path / "dump"
    staging = tmp_path / "staging"
    (dump / "photos").mkdir(parents=True)
    (dump / "photos" / "p.jpg").write_bytes(b"x" * 1000)
    item = MediaItem(MediaKind.PHOTO, "photos/p.jpg")
    r = copy_media(item, dump, staging, tmp_path / "backup", slug="post", tg_id=1)
    assert r.in_staging is True
    assert (staging / "assets" / "img" / "posts" / "post" / "p.jpg").exists()

from lib.media import render_media_markdown

def test_render_photo():
    item = MediaItem(MediaKind.PHOTO, "photos/p.jpg")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/img/posts/post/p.jpg"), None)
    md = render_media_markdown(r, slug="post", tg_id=1)
    assert md == "![](/assets/img/posts/post/p.jpg)"

def test_render_video_selfhosted():
    item = MediaItem(MediaKind.VIDEO, "video_files/v.mp4", declared_mb=5.0)
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/video/posts/post/v.mp4"), None)
    md = render_media_markdown(r, slug="post", tg_id=10)
    assert '<video controls' in md
    assert 'src="/assets/video/posts/post/v.mp4"' in md
    assert 'https://t.me/pioblog/10' in md  # "Оригинал"

def test_render_video_embed_for_large():
    item = MediaItem(MediaKind.VIDEO, "video_files/big.mp4", declared_mb=50.0)
    r = MediaCopyResult(item, False, True, None, Path("/backup/big.mp4"))
    md = render_media_markdown(r, slug="lecture", tg_id=100)
    assert 'data-telegram-post="pioblog/100"' in md
    assert 'telegram-widget.js' in md

def test_render_voice():
    item = MediaItem(MediaKind.VOICE, "voice_messages/v.ogg")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/audio/posts/post/v.ogg"), None)
    assert '<audio controls' in render_media_markdown(r, slug="post", tg_id=1)

def test_render_file_attachment():
    item = MediaItem(MediaKind.FILE, "files/doc.pdf", orig_filename="doc.pdf")
    r = MediaCopyResult(item, True, False,
                        Path("/stub/assets/files/posts/post/doc.pdf"), None)
    md = render_media_markdown(r, slug="post", tg_id=1)
    assert "📎" in md
    assert "(/assets/files/posts/post/doc.pdf)" in md
