from lib.slugify_ru import slugify_ru

def test_cyrillic_transliterated():
    assert slugify_ru("Про Ingress как кусок моего детства") == "pro-ingress-kak-kusok-moego-detstva"

def test_truncation_to_50_chars_at_word_boundary():
    long = "Очень длинный заголовок про многое интересное и немного про жизнь"
    slug = slugify_ru(long, max_length=50)
    assert len(slug) <= 50
    assert not slug.endswith("-")

def test_emoji_stripped():
    assert slugify_ru("📍 Популярные посты") == "populiarnye-posty"

def test_fallback_empty():
    # only emoji/punctuation → empty
    assert slugify_ru("📍🐳!") == ""
