import pytest
from pioblog_sync.state import State


def test_empty_state(tmp_path):
    state_file = tmp_path / "state.json"
    s = State(state_file)
    assert s.get_status(42) is None
    assert s.last_synced_id == 0


def test_set_and_get_status(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_status(42, "imported")
    s.set_status(43, "skipped:voice")
    assert s.get_status(42) == "imported"
    assert s.get_status(43) == "skipped:voice"


def test_persistence(tmp_path):
    s1 = State(tmp_path / "s.json")
    s1.set_status(10, "imported")
    s1.last_synced_id = 100
    s1.save()
    s2 = State(tmp_path / "s.json")
    assert s2.get_status(10) == "imported"
    assert s2.last_synced_id == 100


def test_album_grouping(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_album_group("grp_xyz", [422, 423, 424])
    assert s.get_album_members("grp_xyz") == [422, 423, 424]
    assert s.get_album_for_message(423) == "grp_xyz"
