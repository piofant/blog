"""Detect and group multi-part series in consecutive messages."""
from __future__ import annotations
import re
from typing import TypedDict


_MARKER_RES = [
    re.compile(r"\((\d+)/(\d+)\)"),
    re.compile(r"\[(\d+)/(\d+)\]"),
    re.compile(r"часть\s+(\d+)(?:\s+из\s+(\d+))?", re.IGNORECASE),
    re.compile(r"(?:^|\s)(\d+)/(\d+)(?:\s|$)"),
    re.compile(r"#часть(\d+)"),
]


def detect_series_marker(first_line_or_title: str) -> tuple[int, int | None] | None:
    """Return (part, total) or None."""
    for rx in _MARKER_RES:
        m = rx.search(first_line_or_title)
        if m:
            part = int(m.group(1))
            total = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else None
            return (part, total)
    return None


class SeriesGroup(TypedDict):
    parts: list[dict]
    total: int


def group_series(messages: list[dict]) -> list[SeriesGroup]:
    """Group messages with sequential (N/total) markers. Only complete series returned."""
    groups: list[SeriesGroup] = []
    buf: list[dict] = []
    current_total: int | None = None
    expected_next = 1

    def flush():
        nonlocal buf, current_total, expected_next
        if len(buf) >= 2 and all(m["marker"] for m in buf):
            groups.append({"parts": buf, "total": current_total or len(buf)})
        buf = []
        current_total = None
        expected_next = 1

    for m in messages:
        mk = m.get("marker")
        if mk is None:
            flush()
            continue
        part, total = mk
        if not buf:
            if part != 1:
                continue  # doesn't start a series
            buf = [m]
            current_total = total
            expected_next = 2
            continue
        if part == expected_next and (total is None or total == current_total):
            buf.append(m)
            expected_next += 1
            if current_total and expected_next > current_total:
                flush()
        else:
            flush()
            if part == 1:
                buf = [m]
                current_total = total
                expected_next = 2
    flush()
    return groups
