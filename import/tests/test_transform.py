from datetime import datetime, timezone
from lib.transform import extract_title

def test_first_line_no_markup():
    assert extract_title("<p>Простой текст<br>вторая строка</p>") == "Простой текст"

def test_strips_bold_italic_but_keeps_text():
    assert extract_title("<strong>Жирный</strong> заголовок<br>остальное") == "Жирный заголовок"

def test_truncates_at_word_boundary():
    long_line = "Очень длинный заголовок с кучей слов который точно не влезет в восемьдесят символов никак"
    title = extract_title(long_line + "<br>more")
    assert len(title) <= 80
    assert not title.endswith(" ")

def test_empty_text_fallback_to_russian_date():
    dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
    assert extract_title("", fallback_date=dt) == "Запись от 15 июня 2024"

def test_only_emoji_fallback():
    dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
    assert extract_title("🐳 👀", fallback_date=dt) == "Запись от 15 июня 2024"
