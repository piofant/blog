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
