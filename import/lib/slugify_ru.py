"""Cyrillic-aware slugifier."""
from slugify import slugify


def slugify_ru(text: str, max_length: int = 60) -> str:
    """Transliterate Russian → latin, lowercase, dash-separated."""
    return slugify(text, max_length=max_length, word_boundary=True, save_order=True)
