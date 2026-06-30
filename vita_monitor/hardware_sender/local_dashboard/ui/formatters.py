from __future__ import annotations

import datetime
import math
from typing import Any


def fmt_time(ts: float | None) -> str:
    if ts is None or ts <= 0:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def fmt_float(value: Any, digits: int = 1, default: str = "—") -> str:
    """Jinja2 过滤器：{{ value | fmt_float(2) }} 会传入 positional digits。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(num) or math.isinf(num):
        return default
    if digits == 0:
        return str(int(round(num)))
    return f"{num:.{digits}f}"


def fmt_percent_rate(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{num * 100:.1f}%"


def heartbeat_traffic_class(value: Any, field: str = "") -> str:
    if field in ("network_type", "IP_address", "status"):
        return "neutral"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "bad"
    if field == "rssi_dbm":
        if num >= -55:
            return "good"
        if num >= -70:
            return "warn"
        return "bad"
    if field == "latency_ms":
        if num <= 40:
            return "good"
        if num <= 120:
            return "warn"
        return "bad"
    if field == "packet_loss_rate":
        if num < 0.01:
            return "good"
        if num < 0.05:
            return "warn"
        return "bad"
    if field == "jitter_ms":
        if num <= 12:
            return "good"
        if num <= 35:
            return "warn"
        return "bad"
    return "neutral"


def ip_peer_summary_class(online_count: Any, peer_count: Any) -> str:
    try:
        on = int(online_count)
        total = int(peer_count)
    except (TypeError, ValueError):
        return "neutral"
    if total <= 0:
        return "neutral"
    if on >= total:
        return "good"
    if on == 0:
        return "bad"
    return "warn"


def ip_peer_traffic_class(value: Any, field: str = "") -> str:
    if field == "connected":
        if value is True:
            return "good"
        if value is False:
            return "bad"
        return "neutral"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "bad"
    if field == "latency_ms":
        if num <= 10:
            return "good"
        if num <= 50:
            return "warn"
        return "bad"
    if field == "packet_loss_rate":
        if num < 0.01:
            return "good"
        if num < 0.05:
            return "warn"
        return "bad"
    return "neutral"


def risk_level_class(level: str) -> str:
    if level == "danger":
        return "risk-danger"
    if level == "warning":
        return "risk-warn"
    return "risk-normal"


def system_resource_percent_class(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "bad"
    if num < 0:
        return "bad"
    if num <= 60:
        return "good"
    if num <= 85:
        return "warn"
    return "bad"


def system_resource_temp_class(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if num <= 65:
        return "good"
    if num <= 80:
        return "warn"
    return "bad"


def is_mock_data_mode(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() == "mock"
