"""system_resource 插件 —— 采集 CPU / 内存 / GPU 等计算资源占用指标。"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any

from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)


class SystemResourceVitalPlugin(BaseVitalPlugin):
    vita_type = "system_resource"
    vita_data_schema: dict[str, Any] = {
        "status": "str",
        "collected_at": "float",
        "cpu": "object",
        "memory": "object",
        "gpu": "object",
        "error": "str",
    }

    def __init__(
        self,
        *,
        info_pool: Any,
        interval_sec: float,
        qos: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs
        )
        self._cpu_sample_interval = max(
            0.1, min(float(kwargs.get("cpu_sample_interval", 1.0)), interval_sec * 0.5)
        )
        self._gpu_enabled = bool(kwargs.get("gpu_enabled", True))
        self._cpu_temperature_enabled = bool(kwargs.get("cpu_temperature_enabled", True))
        self._gpu_available: bool | None = None  # 延迟检测
        self._last_payload: dict[str, Any] = self._empty_payload("no data yet")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_payload(error: str) -> dict[str, Any]:
        return {
            "status": "error",
            "collected_at": 0.0,
            "cpu": {
                "percent": -1.0,
                "per_core": [],
                "core_count": 0,
                "temperature": -1.0,
                "temperature_available": False,
            },
            "memory": {
                "total_mb": 0.0,
                "used_mb": 0.0,
                "available_mb": 0.0,
                "percent": -1.0,
            },
            "gpu": {"available": False, "devices": []},
            "error": error,
        }

    def _check_gpu_available(self) -> bool:
        """检测 nvidia-smi 是否可用（仅检测一次，结果缓存）。"""
        if self._gpu_available is not None:
            return self._gpu_available
        if not self._gpu_enabled:
            self._gpu_available = False
            return False
        self._gpu_available = shutil.which("nvidia-smi") is not None
        if not self._gpu_available:
            logger.info("nvidia-smi not found, GPU metrics disabled")
        return self._gpu_available

    # ------------------------------------------------------------------
    # CPU 采集
    # ------------------------------------------------------------------

    def _collect_cpu(self) -> dict[str, Any]:
        try:
            import psutil

            percent = psutil.cpu_percent(interval=self._cpu_sample_interval)
            per_core = psutil.cpu_percent(interval=0, percpu=True)
            core_count = psutil.cpu_count(logical=True) or 0
            out: dict[str, Any] = {
                "percent": round(percent, 1),
                "per_core": [round(v, 1) for v in per_core],
                "core_count": core_count,
                "temperature": -1.0,
                "temperature_available": False,
            }
        except Exception as exc:
            logger.warning("CPU 采集失败: %s", exc)
            return {
                "percent": -1.0,
                "per_core": [],
                "core_count": 0,
                "temperature": -1.0,
                "temperature_available": False,
            }

        if self._cpu_temperature_enabled:
            try:
                from plugins.system_resource.cpu_temperature import collect_cpu_temperature

                out.update(collect_cpu_temperature())
            except Exception as exc:
                logger.warning("CPU 温度采集失败: %s", exc)

        return out

    # ------------------------------------------------------------------
    # 内存采集
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_memory() -> dict[str, Any]:
        try:
            import psutil

            mem = psutil.virtual_memory()
            return {
                "total_mb": round(mem.total / (1024 * 1024), 1),
                "used_mb": round(mem.used / (1024 * 1024), 1),
                "available_mb": round(mem.available / (1024 * 1024), 1),
                "percent": round(mem.percent, 1),
            }
        except Exception as exc:
            logger.warning("内存采集失败: %s", exc)
            return {
                "total_mb": 0.0,
                "used_mb": 0.0,
                "available_mb": 0.0,
                "percent": -1.0,
            }

    # ------------------------------------------------------------------
    # GPU 采集（nvidia-smi）
    # ------------------------------------------------------------------

    def _collect_gpu(self) -> dict[str, Any]:
        if not self._check_gpu_available():
            return {"available": False, "devices": []}

        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,memory.total,memory.used,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=5.0,
                text=True,
            )
            devices: list[dict[str, Any]] = []
            for line in output.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 6:
                    continue
                idx = int(parts[0])
                name = parts[1]
                util = float(parts[2])
                mem_total = float(parts[3])
                mem_used = float(parts[4])
                temp = float(parts[5])
                mem_percent = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0.0
                devices.append(
                    {
                        "index": idx,
                        "name": name,
                        "utilization_percent": round(util, 1),
                        "memory_total_mb": round(mem_total, 1),
                        "memory_used_mb": round(mem_used, 1),
                        "memory_percent": mem_percent,
                        "temperature": round(temp, 1),
                    }
                )
            return {"available": True, "devices": devices}
        except Exception as exc:
            logger.warning("GPU 采集失败: %s", exc)
            # 保留上一轮的 GPU 数据（如有），异常原因写入顶层 error
            prev_devices = self._last_payload.get("gpu", {}).get("devices", [])
            return {"available": True, "devices": prev_devices, "_gpu_error": str(exc)[:120]}

    # ------------------------------------------------------------------
    # 插件接口
    # ------------------------------------------------------------------

    def collect_real_vita_data(self) -> dict[str, Any]:
        error_parts: list[str] = []
        has_error = False

        cpu = self._collect_cpu()
        if cpu["percent"] < 0:
            error_parts.append("cpu failed")
            has_error = True

        memory = self._collect_memory()
        if memory["percent"] < 0:
            error_parts.append("memory failed")
            has_error = True

        gpu = self._collect_gpu()
        gpu_error = gpu.pop("_gpu_error", None)
        if gpu_error:
            error_parts.append(str(gpu_error))

        out: dict[str, Any] = {
            "status": "error" if has_error else "ok",
            "collected_at": time.time(),
            "cpu": cpu,
            "memory": memory,
            "gpu": gpu,
            "error": "; ".join(error_parts),
        }
        self._last_payload = out
        return dict(out)

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.system_resource.mock_generator import generate_system_resource_mock

        out = generate_system_resource_mock(self.mock_config)
        self._last_payload = out
        return dict(out)
