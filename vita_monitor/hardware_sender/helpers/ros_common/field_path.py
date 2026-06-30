from __future__ import annotations

from typing import Any


def parse_field_path(path: str | None) -> list[str]:
    """以 ':' 分隔路径段，首尾 ':' 忽略；仅 ':' 或空表示根（整条消息）。"""
    if path is None:
        return []
    raw = str(path).strip()
    if not raw or raw == ":":
        return []
    return [p for p in raw.split(":") if p]


def navigate_fields(obj: Any, segments: list[str]) -> Any:
    cur = obj
    for seg in segments:
        cur = getattr(cur, seg)
    return cur
