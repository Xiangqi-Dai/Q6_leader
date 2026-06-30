from __future__ import annotations

import json
import logging
import math
import urllib.request
from typing import Any

from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)

_DEFAULT_XOS_POSE_PATH = "/robot/navigate/get_navigate_realtime_pose"


class LocalPoseVitalPlugin(BaseVitalPlugin):
    vita_type = "local_pose"
    vita_data_schema: dict[str, Any] = {
        "location": {
            "frame_id": "str",
            "position": "{x,y,z}",
            "orientation": "{x,y,z,w}",
        },
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        self._collector: Any = None
        self._mock_generator: Any = None
        self._kw = kwargs
        # simulated 模式：缓存上一次成功拉取的位姿，请求失败时降级使用
        self._last_simulated_pose: dict[str, Any] | None = None

    def _resolve_source(self) -> str:
        """根据 kwargs.source 或已配置的采集参数推断 ros / xos。"""
        source = str(self._kw.get("source", "")).strip().lower()
        if source in ("ros", "xos"):
            return source
        if self._kw.get("xos_url") or self._kw.get("xos_host"):
            return "xos"
        return "ros"

    def _create_collector(self) -> Any:
        source = self._resolve_source()
        if source == "xos":
            from plugins.local_pose.xos_pose_collector import XosLocalPoseCollector

            xos_url = str(self._kw.get("xos_url", "")).strip()
            if not xos_url:
                host = str(self._kw.get("xos_host", "http://localhost:1888")).rstrip("/")
                xos_url = f"{host}{_DEFAULT_XOS_POSE_PATH}"
            return XosLocalPoseCollector(
                xos_url=xos_url,
                frame_id=str(self._kw.get("frame_id", "map")),
                timeout_sec=float(self._kw.get("timeout_sec", 3.0)),
            )

        from plugins.local_pose.ros_pose_collector import RosLocalPoseCollector

        return RosLocalPoseCollector(
            pose_topic=str(self._kw.get("pose_topic", "")),
            pose_message_type=str(
                self._kw.get("pose_message_type", "geometry_msgs/msg/PoseStamped")
            ),
            pose_field_path=str(self._kw.get("pose_field_path", ":")),
        )

    def collect_real_vita_data(self) -> dict[str, Any]:
        if self._collector is None:
            self._collector = self._create_collector()
            logger.info("local_pose real collector: source=%s", self._resolve_source())
        try:
            return self._collector.snapshot()
        except Exception:
            logger.exception("local_pose collect failed")
            return {"location": {}}

    def collect_mock_vita_data(self) -> dict[str, Any]:
        if self._mock_generator is None:
            from plugins.local_pose.mock_generator import LocalPoseMockGenerator

            self._mock_generator = LocalPoseMockGenerator(self.mock_config)
        return self._mock_generator.snapshot()

    def collect_simulated_vita_data(self) -> dict[str, Any]:
        """从 robot_simulator HTTP 服务拉取当前位姿"""
        base_url = str(self._kw.get("simulator_url", "http://127.0.0.1:7001")).rstrip("/")
        api_path = str(self._kw.get("pose_api_path", "/api/pose"))
        if not api_path.startswith("/"):
            api_path = f"/{api_path}"
        url = f"{base_url}{api_path}"

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
        except Exception:
            logger.warning("local_pose simulated fetch failed: %s", url, exc_info=True)
            # 降级：返回上一次缓存的位姿，避免数据中断
            if self._last_simulated_pose is not None:
                return self._last_simulated_pose
            return {"location": {}}

        # 解析 robot_simulator 返回的位姿，转换为 local_pose 原有格式
        x = float(data.get("x", 0.0))
        y = float(data.get("y", 0.0))
        z = float(data.get("z", 0.0))
        yaw = float(data.get("yaw", 0.0))
        frame_id = str(data.get("frame_id", "map"))

        # yaw → 四元数（仅绕 Z 轴旋转）
        half_yaw = yaw / 2.0
        pose = {
            "location": {
                "frame_id": frame_id,
                "position": {
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "z": z,
                },
                "orientation": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": round(math.sin(half_yaw), 6),
                    "w": round(math.cos(half_yaw), 6),
                },
            }
        }
        self._last_simulated_pose = pose
        return pose
