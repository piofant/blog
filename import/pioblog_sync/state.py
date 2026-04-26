"""JSON state for idempotent sync."""
from __future__ import annotations
import json
from pathlib import Path


class State:
    """Tracks per-message processing status + album groups."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_synced_id: int = 0
        self._statuses: dict[int, str] = {}
        self._album_groups: dict[str, list[int]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.last_synced_id = int(data.get("last_synced_id", 0))
        self._statuses = {int(k): v for k, v in data.get("statuses", {}).items()}
        self._album_groups = {
            k: list(v) for k, v in data.get("album_groups", {}).items()
        }

    def save(self) -> None:
        data = {
            "last_synced_id": self.last_synced_id,
            "statuses": {str(k): v for k, v in self._statuses.items()},
            "album_groups": self._album_groups,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_status(self, msg_id: int) -> str | None:
        return self._statuses.get(msg_id)

    def set_status(self, msg_id: int, status: str) -> None:
        self._statuses[msg_id] = status

    def set_album_group(self, group_id: str, member_ids: list[int]) -> None:
        self._album_groups[group_id] = sorted(member_ids)

    def get_album_members(self, group_id: str) -> list[int]:
        return self._album_groups.get(group_id, [])

    def get_album_for_message(self, msg_id: int) -> str | None:
        for gid, members in self._album_groups.items():
            if msg_id in members:
                return gid
        return None
