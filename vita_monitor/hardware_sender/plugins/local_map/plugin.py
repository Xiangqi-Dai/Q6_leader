from __future__ import annotations

import logging
from typing import Any

from plugins.local_map.content_fingerprint import fingerprint_vita_data
from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)


class LocalMapVitalPlugin(BaseVitalPlugin):
    vita_type = "local_map"
    vita_data_schema: dict[str, Any] = {
        "map": {
            "frame_id": "str",
            "points": "list[[x,y]]",
            "point_count": "int",
            "width": "int",
            "height": "int",
            "map_name": "str (XOS 采集源携带；ROS 源可能缺失)",
        },
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        self._collector: Any = None
        self._kw = kwargs
        self._last_fingerprint: str | None = None

    def _resolve_source(self) -> str:
        """根据 kwargs.source 或已配置的采集参数推断 ros / xos。"""
        source = str(self._kw.get("source", "")).strip().lower()
        if source in ("ros", "xos"):
            return source
        if self._kw.get("xos_host"):
            return "xos"
        if self._kw.get("map_topic"):
            return "ros"
        return "xos"

    def _create_collector(self) -> Any:
        source = self._resolve_source()
        if source == "xos":
            from plugins.local_map.xos_map_collector import XosLocalMapCollector

            return XosLocalMapCollector(
                xos_host=str(self._kw.get("xos_host", "http://localhost:1888")),
            )

        from plugins.local_map.ros_map_collector import RosLocalMapCollector

        return RosLocalMapCollector(
            map_topic=str(self._kw.get("map_topic", "")),
            map_message_type=str(
                self._kw.get("map_message_type", "sensor_msgs/msg/PointCloud2")
            ),
            map_field_path=str(self._kw.get("map_field_path", ":")),
        )

    def collect_real_vita_data(self) -> dict[str, Any]:
        if self._collector is None:
            self._collector = self._create_collector()
            logger.info("local_map real collector: source=%s", self._resolve_source())
        try:
            return self._collector.snapshot()
        except Exception:
            logger.exception("local_map collect failed")
            return {"map": {}}

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.local_map.mock_generator import generate_local_map_mock

        return generate_local_map_mock(self.mock_config)

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
                fp = fingerprint_vita_data(vita_data)
                if fp != self._last_fingerprint:
                    self.put_data_to_pool(vita_data)
                    self._last_fingerprint = fp
                else:
                    logger.debug("local_map unchanged, skip publish")
            except Exception:
                logger.exception("plugin collect/push failed: vita_type=%s", self.vita_type)
            self._stop_event.wait(self.interval_sec)
        logger.info("plugin stopped: %s", self.vita_type)
