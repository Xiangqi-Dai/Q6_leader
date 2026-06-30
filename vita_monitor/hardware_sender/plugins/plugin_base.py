from __future__ import annotations

import logging
import multiprocessing as mp
import time
from abc import ABC, abstractmethod
from queue import Full
from typing import Any

from comm_infra.envelope import normalize_data_mode, sanitize_vita_data

logger = logging.getLogger(__name__)


class BaseVitalPlugin(ABC):
    """
    Base contract for hardware sender plugins.

    Subclasses must define:
    - class attr `vita_type`
    - class attr `vita_data_schema`
    - method `collect_real_vita_data()`
    - method `collect_mock_vita_data()`
    """

    vita_type: str = ""
    vita_data_schema: dict[str, Any] = {}

    def __init__(
        self,
        *,
        info_pool: Any,
        interval_sec: float,
        qos: int = 0,
        data_mode: str = "real",
        mock_config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._validate_plugin_contract()
        self.info_pool = info_pool
        self.interval_sec = float(interval_sec)
        self.qos = int(qos)
        self.data_mode = normalize_data_mode(data_mode)
        self.mock_config = dict(mock_config or {})
        self.kwargs = kwargs
        self.process: mp.Process | None = None
        self._stop_event: mp.Event = mp.Event()

        if self.interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        if self.qos not in (0, 1, 2):
            raise ValueError("qos must be one of (0, 1, 2)")

    def _validate_plugin_contract(self) -> None:
        if not isinstance(self.vita_type, str) or not self.vita_type.strip():
            raise ValueError(f"{self.__class__.__name__}.vita_type must be a non-empty string")
        if not isinstance(self.vita_data_schema, dict):
            raise ValueError(f"{self.__class__.__name__}.vita_data_schema must be a dict")

    def collect_vita_data(self) -> dict[str, Any]:
        """Dispatch by configured data_mode. Subclasses must not override."""
        if self.data_mode == "mock":
            return self.collect_mock_vita_data()
        if self.data_mode == "simulated":
            return self.collect_simulated_vita_data()
        return self.collect_real_vita_data()

    @abstractmethod
    def collect_real_vita_data(self) -> dict[str, Any]:
        """Collect one snapshot from real hardware / APIs."""
        raise NotImplementedError

    @abstractmethod
    def collect_mock_vita_data(self) -> dict[str, Any]:
        """Collect one synthetic snapshot matching vita_data_schema."""
        raise NotImplementedError

    def collect_simulated_vita_data(self) -> dict[str, Any]:
        """从外部模拟服务（如 robot_simulator）读取数据。插件按需覆写。"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support simulated mode"
        )

    def put_data_to_pool(self, vita_data: dict[str, Any]) -> None:
        """
        Push a publish task into info_pool.

        Item structure follows project docs:
        {
          "vita_type": str,
          "data_mode": str,
          "vita_data": dict,
          "collected_at": float,
          "qos": int
        }
        """
        item = {
            "vita_type": self.vita_type,
            "data_mode": self.data_mode,
            "vita_data": sanitize_vita_data(vita_data),
            "collected_at": time.time(),
            "qos": self.qos,
        }
        try:
            self.info_pool.put(item, block=False)
        except Full:
            logger.warning("info_pool full, dropping vital data: vita_type=%s", self.vita_type)

    def _run_loop(self) -> None:
        if self.data_mode in ("mock", "simulated"):
            logger.warning("plugin running in %s mode: %s", self.data_mode.upper(), self.vita_type)
        else:
            logger.info("plugin started: %s data_mode=%s", self.vita_type, self.data_mode)
        while not self._stop_event.is_set():
            try:
                vita_data = self.collect_vita_data()
                if not isinstance(vita_data, dict):
                    raise TypeError(
                        f"{self.__class__.__name__}.collect_vita_data() must return dict, "
                        f"got {type(vita_data).__name__}"
                    )
                self.put_data_to_pool(vita_data)
            except Exception:
                logger.exception("plugin collect/push failed: vita_type=%s", self.vita_type)
            self._stop_event.wait(self.interval_sec)
        logger.info("plugin stopped: %s", self.vita_type)

    def launch(self) -> None:
        """Start plugin process: collect -> put_data_to_pool in a loop."""
        if self.process is not None and self.process.is_alive():
            return
        self._stop_event.clear()
        self.process = mp.Process(target=self._run_loop, name=f"plugin-{self.vita_type}", daemon=True)
        self.process.start()

    def shutdown(self, *, timeout_sec: float = 5.0) -> None:
        """Stop plugin process gracefully, then force terminate if needed."""
        if self.process is None:
            return
        self._stop_event.set()
        self.process.join(timeout=timeout_sec)
        if self.process.is_alive():
            logger.warning("plugin shutdown timeout, terminating: %s", self.vita_type)
            self.process.terminate()
            self.process.join(timeout=1.0)
        self.process = None
