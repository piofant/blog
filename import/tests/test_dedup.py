from datetime import datetime, timezone, timedelta
from pathlib import Path
from lib.dedup import match_existing_posts, Candidate


def test_match_by_date_and_first_line(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-03-12-ingress.md").write_text(
        "---\nlayout: post\ntitle: 'Про Ingress как кусок моего детства'\n---\n\n"
        "В 2016-2019 я играл в Ingress...",
        encoding="utf-8",
    )
    tg_msgs = [
        {"id": 86, "date": datetime(2022, 3, 12, 10, 0, tzinfo=timezone.utc),
         "title": "Про Ingress как кусок моего детства"},
        {"id": 100, "date": datetime(2022, 3, 13, 10, 0, tzinfo=timezone.utc),
         "title": "Что-то другое"},
    ]
    candidates = match_existing_posts(tg_msgs, posts_dir)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.telegram_id == 86
    assert c.post_file.name == "2022-03-12-ingress.md"
    assert c.permalink == "/blog/ingress/"
    assert c.score > 0.7

def test_no_match_when_date_differs_and_title_too(tmp_path):
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    (posts_dir / "2022-03-12-ingress.md").write_text(
        "---\ntitle: 'Про Ingress'\n---\n\ntext", encoding="utf-8"
    )
    tg_msgs = [{"id": 99, "date": datetime(2023, 7, 1, tzinfo=timezone.utc),
                "title": "Совсем другой"}]
    assert match_existing_posts(tg_msgs, posts_dir) == []
