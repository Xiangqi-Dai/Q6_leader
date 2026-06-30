from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from local_dashboard.infra.state_store import VitalSnapshot


def _finite(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN
        return None
    return num


def build_heartbeat_points(history: Iterable[VitalSnapshot]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in history:
        d = row.vita_data
        points.append(
            {
                "t": row.collected_at * 1000.0,
                "latency": _finite(d.get("latency_ms")),
                "rssi": _finite(d.get("rssi_dbm")),
                "loss": _finite(d.get("packet_loss_rate")),
                "jitter": _finite(d.get("jitter_ms")),
            }
        )
    points.sort(key=lambda p: p["t"])
    return points


def build_air_pollutant_points(history: Iterable[VitalSnapshot]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in history:
        d = row.vita_data
        points.append(
            {
                "t": row.collected_at * 1000.0,
                "co2": _finite(d.get("co2")),
                "hcho": _finite(d.get("hcho")),
                "voc": _finite(d.get("voc")),
                "pm25": _finite(d.get("pm25")),
                "pm10": _finite(d.get("pm10")),
            }
        )
    points.sort(key=lambda p: p["t"])
    return points


def build_air_comfort_points(history: Iterable[VitalSnapshot]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in history:
        d = row.vita_data
        points.append(
            {
                "t": row.collected_at * 1000.0,
                "temperature": _finite(d.get("temperature")),
                "humidity": _finite(d.get("humidity")),
            }
        )
    points.sort(key=lambda p: p["t"])
    return points


def sort_radio_networks(networks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def pct(n: dict[str, Any]) -> float:
        try:
            return float(n.get("signal_percent", 0))
        except (TypeError, ValueError):
            return 0.0

    return sorted(networks, key=pct, reverse=True)
