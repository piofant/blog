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

from lib.transform import html_to_markdown

def test_bold_italic_link():
    assert html_to_markdown("<strong>жирный</strong>") == "**жирный**"
    assert html_to_markdown("<em>курсив</em>") == "*курсив*"
    assert html_to_markdown('<a href="https://x.com">link</a>') == "[link](https://x.com)"

def test_br_becomes_newline():
    assert html_to_markdown("line1<br>line2") == "line1\nline2"

def test_code_and_blockquote():
    assert html_to_markdown("<code>x</code>") == "`x`"
    assert html_to_markdown("<blockquote>quoted</blockquote>").strip().startswith(">")

def test_hashtag_link_becomes_plain_tag():
    html = '<a href="" onclick="return ShowHashtag(&quot;рефлексия&quot;)">#рефлексия</a>'
    assert html_to_markdown(html).strip() == "#рефлексия"

def test_emoji_preserved():
    assert html_to_markdown("текст 🐳 текст") == "текст 🐳 текст"

def test_preserves_external_link_with_bold_inside():
    html = '<a href="https://x.com"><strong>link</strong></a>'
    md = html_to_markdown(html)
    assert "[**link**](https://x.com)" in md or "**[link](https://x.com)**" in md

from lib.transform import rewrite_pioblog_links

def test_rewrite_known_link():
    link_map = {10: "/blog/first-post/", 14: "/blog/later-post/"}
    md = "Смотри [прошлый](https://t.me/pioblog/10) и [ещё](https://t.me/pioblog/14)."
    out = rewrite_pioblog_links(md, link_map)
    assert "(/blog/first-post/)" in out
    assert "(/blog/later-post/)" in out
    assert "t.me/pioblog" not in out

def test_unknown_id_preserved():
    link_map = {10: "/blog/x/"}
    md = "[удалённый](https://t.me/pioblog/999)"
    assert "https://t.me/pioblog/999" in rewrite_pioblog_links(md, link_map)

def test_preserves_other_tg_channels():
    link_map = {}
    md = "[отсюда](https://t.me/not_tldr/5)"
    assert rewrite_pioblog_links(md, link_map) == md

def test_also_rewrites_in_html_anchor_forms():
    link_map = {10: "/blog/x/"}
    md = 'Ссылка: <a href="https://t.me/pioblog/10">link</a>'
    assert "/blog/x/" in rewrite_pioblog_links(md, link_map)
