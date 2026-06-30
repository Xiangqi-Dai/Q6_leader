"""CPU 温度采集 —— psutil.sensors_temperatures 优先，/sys/class/thermal 兜底。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CPU_ZONE_RE = re.compile(
    r"coretemp|k10temp|cpu|acpitz|pch|package|soc-thermal",
    re.IGNORECASE,
)


def _valid_celsius(value: float) -> bool:
    return 0 < value <= 150


def _read_sysfs_zone_temp(zone_dir: Path) -> float | None:
    temp_path = zone_dir / "temp"
    if not temp_path.is_file():
        return None
    try:
        raw = temp_path.read_text(encoding="ascii").strip()
        value = int(raw) / 1000.0
    except (OSError, ValueError):
        return None
    return value if _valid_celsius(value) else None


def _read_sysfs_zone_type(zone_dir: Path) -> str:
    type_path = zone_dir / "type"
    if not type_path.is_file():
        return ""
    try:
        return type_path.read_text(encoding="ascii").strip().lower()
    except OSError:
        return ""


def _from_psutil() -> float | None:
    try:
        import psutil

        temps = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, ImportError, OSError, NotImplementedError):
        return None

    if not temps:
        return None

    matched: list[float] = []
    fallback: list[float] = []
    for name, entries in temps.items():
        for entry in entries or []:
            current = getattr(entry, "current", None)
            if current is None:
                continue
            try:
                value = float(current)
            except (TypeError, ValueError):
                continue
            if not _valid_celsius(value):
                continue
            if _CPU_ZONE_RE.search(name) or _CPU_ZONE_RE.search(getattr(entry, "label", "") or ""):
                matched.append(value)
            else:
                fallback.append(value)

    if matched:
        return max(matched)
    if fallback:
        return max(fallback)
    return None


def _from_sysfs() -> float | None:
    base = Path("/sys/class/thermal")
    if not base.is_dir():
        return None

    matched: list[float] = []
    fallback: list[float] = []
    for zone in sorted(base.glob("thermal_zone*")):
        value = _read_sysfs_zone_temp(zone)
        if value is None:
            continue
        zone_type = _read_sysfs_zone_type(zone)
        if zone_type and "gpu" in zone_type and "cpu" not in zone_type:
            continue
        if zone_type and _CPU_ZONE_RE.search(zone_type):
            matched.append(value)
        else:
            fallback.append(value)

    if matched:
        return max(matched)
    if fallback:
        return max(fallback)
    return None


def collect_cpu_temperature() -> dict[str, Any]:
    """返回 cpu.temperature / cpu.temperature_available 字段片段。"""
    temp = _from_psutil()
    if temp is None:
        temp = _from_sysfs()

    if temp is None:
        return {"temperature": -1.0, "temperature_available": False}

    return {"temperature": round(temp, 1), "temperature_available": True}
