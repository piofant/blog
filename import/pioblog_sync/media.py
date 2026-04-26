"""Download photos/videos/voices in full quality, idempotent by filename."""
from __future__ import annotations
from pathlib import Path
from PIL import Image

from pioblog_sync.config import ASSETS_DIR


async def download_media_for_post(client, messages, slug: str) -> dict[str, list[str]]:
    """Download all media for a post (single message or album).

    Returns dict with keys 'photos', 'videos', 'voices' (each list of /blog/... URLs).
    """
    out_dir = ASSETS_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    photos: list[str] = []
    videos: list[str] = []
    voices: list[str] = []

    photo_seq = video_seq = voice_seq = 0
    for m in messages:
        if m.photo is not None:
            photo_seq += 1
            fname = f"photo_{photo_seq}.jpg"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            photos.append(f"/blog/assets/img/posts/{slug}/{fname}")
        elif m.video is not None:
            video_seq += 1
            fname = f"video_{video_seq}.mp4"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            videos.append(f"/blog/assets/img/posts/{slug}/{fname}")
        elif m.voice is not None:
            voice_seq += 1
            fname = f"voice_{voice_seq}.ogg"
            target = out_dir / fname
            if not target.exists():
                await client.download_media(m, file=str(target))
            voices.append(f"/blog/assets/img/posts/{slug}/{fname}")

    return {"photos": photos, "videos": videos, "voices": voices}


def photo_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image."""
    with Image.open(path) as img:
        return img.size


def is_higher_quality(existing: Path, new_size_bytes: int) -> bool:
    """Crude heuristic: new is higher quality if its file is significantly larger."""
    if not existing.exists():
        return True
    return new_size_bytes > existing.stat().st_size * 1.2
