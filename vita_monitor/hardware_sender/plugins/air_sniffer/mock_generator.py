from __future__ import annotations

import time
from typing import Any
import random

from plugins.mock_utils import rng_from_config

# 插件在独立进程中首次采集时记录起点，用于「浅→深」渐变
_RAMP_START_MONO: float | None = None

# 低浓度端（热力图偏蓝/绿）与深浓度端（热力图偏黄/红）
_LOW_METRICS: dict[str, float] = {
    "co2": 430.0,
    "hcho": 18.0,
    "voc": 55.0,
    "pm25": 6.0,
    "pm10": 12.0,
    "temperature": 23.5,
    "humidity": 52.0,
    "o2": 20.9,
    "h2s": 0.0,
    "co": 0.0,
    "so2": 0.05,
    "no2": 0.05,
    "ch4": 0.0,
    "nh3": 1.0,
    "ph3": 0.005,
    "eto": 0.05,
}

_HIGH_METRICS: dict[str, float] = {
    "co2": 1750.0,
    "hcho": 96.0,
    "voc": 820.0,
    "pm25": 88.0,
    "pm10": 165.0,
    "temperature": 31.5,
    "humidity": 68.0,
    "o2": 20.2,
    "h2s": 13.0,
    "co": 24.0,
    "so2": 4.2,
    "no2": 4.5,
    "ch4": 18.0,
    "nh3": 38.0,
    "ph3": 0.22,
    "eto": 1.8,
}

_INT_KEYS = frozenset({"co2", "hcho", "voc", "pm25", "pm10", "h2s", "co", "ch4", "nh3"})


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ramp_progress(mock_config: dict[str, Any]) -> float:
    """0=浅/低浓度，1=深/高浓度（前端热力图偏红）。"""
    global _RAMP_START_MONO
    if _RAMP_START_MONO is None:
        _RAMP_START_MONO = time.monotonic()

    duration = max(5.0, float(mock_config.get("ramp_duration_sec", 90.0)))
    hold = max(0.0, float(mock_config.get("ramp_hold_sec", 8.0)))
    cycle = bool(mock_config.get("ramp_cycle", True))
    elapsed = time.monotonic() - _RAMP_START_MONO

    if cycle:
        period = duration + hold
        phase = elapsed % period
        if phase >= duration:
            return 1.0
        return _smoothstep(phase / duration)

    return _smoothstep(min(1.0, elapsed / duration))


def _lerp_metric(
    rng: random.Random,
    key: str,
    low: float,
    high: float,
    t: float,
    *,
    jitter_ratio: float,
) -> float:
    base = low + (high - low) * t
    if jitter_ratio <= 0:
        return base
    span = high - low
    spread = span * jitter_ratio * (0.35 + 0.65 * t)
    return base + rng.uniform(-spread, spread)


def _finalize_metric(key: str, value: float) -> int | float:
    if key in _INT_KEYS:
        return int(round(value))
    if key in ("so2", "no2", "ph3", "eto"):
        decimals = 3 if key == "ph3" else 2
        return round(value, decimals)
    return round(value, 1)


def generate_air_sniffer_mock(mock_config: dict[str, Any], *, sensor_url: str) -> dict[str, Any]:
    from plugins.air_sniffer.plugin import _assess_risk

    rng = rng_from_config(mock_config)
    t = _ramp_progress(mock_config)
    jitter = float(mock_config.get("ramp_jitter", 0.04))

    metrics: dict[str, float] = {}
    for key in _LOW_METRICS:
        low = float(mock_config.get(f"{key}_low", _LOW_METRICS[key]))
        high = float(mock_config.get(f"{key}_high", _HIGH_METRICS[key]))
        if low > high:
            low, high = high, low
        raw = _lerp_metric(rng, key, low, high, t, jitter_ratio=jitter)
        metrics[key] = float(_finalize_metric(key, raw))

    risk_level, risk_score, main_factor, summary = _assess_risk(metrics)
    return {
        "status": "ok",
        "sensor_url": sensor_url,
        "sampled_at": time.time(),
        "co2": int(metrics["co2"]),
        "hcho": int(metrics["hcho"]),
        "voc": int(metrics["voc"]),
        "pm25": int(metrics["pm25"]),
        "pm10": int(metrics["pm10"]),
        "temperature": metrics["temperature"],
        "humidity": metrics["humidity"],
        "o2": metrics["o2"],
        "h2s": int(metrics["h2s"]),
        "co": int(metrics["co"]),
        "so2": metrics["so2"],
        "no2": metrics["no2"],
        "ch4": int(metrics["ch4"]),
        "nh3": int(metrics["nh3"]),
        "ph3": metrics["ph3"],
        "eto": metrics["eto"],
        "risk_level": risk_level,
        "risk_score": risk_score,
        "main_factor": main_factor,
        "summary": summary,
        "error": "",
    }
