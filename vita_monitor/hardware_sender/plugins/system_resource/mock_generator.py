"""system_resource Mock 数据生成器。"""

from __future__ import annotations

import time
from typing import Any

from plugins.mock_utils import pick_float, rng_from_config


def generate_system_resource_mock(mock_config: dict[str, Any]) -> dict[str, Any]:
    rng = rng_from_config(mock_config)

    # CPU
    core_count = int(mock_config.get("core_count", 4))
    cpu_percent = pick_float(rng, mock_config.get("cpu_percent_range"), (10.0, 80.0))
    per_core = [round(pick_float(rng, None, (max(0, cpu_percent - 20), min(100, cpu_percent + 20))), 1) for _ in range(core_count)]
    cpu_temp_enabled = mock_config.get("cpu_temperature_enabled", True)
    if cpu_temp_enabled:
        cpu_temp = round(pick_float(rng, mock_config.get("cpu_temp_range"), (35.0, 72.0)), 1)
        cpu_temp_fields = {"temperature": cpu_temp, "temperature_available": True}
    else:
        cpu_temp_fields = {"temperature": -1.0, "temperature_available": False}

    # 内存
    total_mb = float(mock_config.get("memory_total_mb", 8192.0))
    mem_percent = pick_float(rng, mock_config.get("memory_percent_range"), (20.0, 70.0))
    used_mb = round(total_mb * mem_percent / 100.0, 1)
    available_mb = round(total_mb - used_mb, 1)

    # GPU
    gpu_enabled = mock_config.get("gpu_enabled", True)
    if gpu_enabled:
        gpu_name = mock_config.get("gpu_name", "NVIDIA Mock GPU")
        gpu_mem_total = float(mock_config.get("gpu_memory_total_mb", 8192.0))
        gpu_util = pick_float(rng, mock_config.get("gpu_util_range"), (10.0, 90.0))
        gpu_mem_used = round(gpu_mem_total * pick_float(rng, mock_config.get("gpu_mem_percent_range"), (20.0, 80.0)) / 100.0, 1)
        gpu_mem_percent = round(gpu_mem_used / gpu_mem_total * 100.0, 1) if gpu_mem_total > 0 else 0.0
        gpu_temp = pick_float(rng, mock_config.get("gpu_temp_range"), (35.0, 75.0))
        gpu: dict[str, Any] = {
            "available": True,
            "devices": [
                {
                    "index": 0,
                    "name": gpu_name,
                    "utilization_percent": round(gpu_util, 1),
                    "memory_total_mb": round(gpu_mem_total, 1),
                    "memory_used_mb": gpu_mem_used,
                    "memory_percent": gpu_mem_percent,
                    "temperature": round(gpu_temp, 1),
                }
            ],
        }
    else:
        gpu = {"available": False, "devices": []}

    return {
        "status": "ok",
        "collected_at": time.time(),
        "cpu": {
            "percent": round(cpu_percent, 1),
            "per_core": per_core,
            "core_count": core_count,
            **cpu_temp_fields,
        },
        "memory": {
            "total_mb": round(total_mb, 1),
            "used_mb": used_mb,
            "available_mb": available_mb,
            "percent": round(mem_percent, 1),
        },
        "gpu": gpu,
        "error": "",
    }
