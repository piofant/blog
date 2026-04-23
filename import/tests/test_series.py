from lib.series import detect_series_marker, group_series


def test_marker_parens():
    r = detect_series_marker("Заголовок (1/5)\nтекст")
    assert r == (1, 5)

def test_marker_brackets():
    assert detect_series_marker("Серия [2/3]") == (2, 3)

def test_marker_russian_chast():
    assert detect_series_marker("часть 3 из 5\nтекст") == (3, 5)

def test_marker_russian_chast_no_total():
    assert detect_series_marker("часть 2") == (2, None)

def test_no_marker():
    assert detect_series_marker("Обычный пост без маркера") is None

def test_group_series_consecutive_parts():
    msgs = [
        {"id": 100, "title": "Часть (1/3)", "marker": (1, 3)},
        {"id": 101, "title": "Часть (2/3)", "marker": (2, 3)},
        {"id": 102, "title": "Часть (3/3)", "marker": (3, 3)},
        {"id": 103, "title": "Независимый", "marker": None},
    ]
    groups = group_series(msgs)
    assert len(groups) == 1
    assert [m["id"] for m in groups[0]["parts"]] == [100, 101, 102]
    assert groups[0]["total"] == 3

def test_group_series_ignores_broken_sequence():
    msgs = [
        {"id": 100, "title": "A (1/3)", "marker": (1, 3)},
        {"id": 101, "title": "Other (1/5)", "marker": (1, 5)},  # different total
        {"id": 102, "title": "B (2/3)", "marker": (2, 3)},
    ]
    groups = group_series(msgs)
    # only the (1/5) is its own dangling single-part group? No — we require ≥2 parts to form a series
    ids = [[m["id"] for m in g["parts"]] for g in groups]
    assert ids == []  # no complete group
