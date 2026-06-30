from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any

if __package__ in (None, ""):
    _HARDWARE_SENDER_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if _HARDWARE_SENDER_ROOT not in sys.path:
        sys.path.insert(0, _HARDWARE_SENDER_ROOT)

from helpers.ros_common.field_path import navigate_fields, parse_field_path
from helpers.ros_common.ros_types import import_message_class
from helpers.ros_common.serialize import pointcloud2_to_map_payload

logger = logging.getLogger(__name__)


class RosLocalMapCollector:
    """采集进程内订阅点云话题，缓存完整 map 载荷。"""

    def __init__(
        self,
        *,
        map_topic: str,
        map_message_type: str,
        map_field_path: str,
    ) -> None:
        self._map_topic = map_topic.strip()
        self._map_message_type = map_message_type.strip()
        self._map_field_path = map_field_path

        self._lock = threading.Lock()
        self._map_payload: dict[str, Any] = {}
        self._node: Any = None
        self._spin_thread: threading.Thread | None = None
        self._started = False
        self._start_error: str | None = None

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            import rclpy
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.node import Node
            from sensor_msgs.msg import PointCloud2

            rclpy.init(args=None)
            self._node = Node("local_map_hw_sender")

            map_msg_cls = import_message_class(self._map_message_type)
            map_segments = parse_field_path(self._map_field_path)

            def on_map(msg: Any) -> None:
                try:
                    inner = navigate_fields(msg, map_segments) if map_segments else msg
                    if not isinstance(inner, PointCloud2):
                        logger.warning(
                            "map field is not PointCloud2 (got %s), skip",
                            type(inner).__name__,
                        )
                        return
                    payload = pointcloud2_to_map_payload(inner)
                    with self._lock:
                        self._map_payload = payload
                except Exception:
                    logger.exception("local_map callback failed")

            if self._map_topic:
                self._node.create_subscription(map_msg_cls, self._map_topic, on_map, 10)
            else:
                logger.warning("map_topic empty, no map subscription")

            executor = MultiThreadedExecutor()

            def _spin() -> None:
                try:
                    executor.add_node(self._node)
                    executor.spin()
                except Exception:
                    logger.exception("local_map executor.spin ended with error")

            self._spin_thread = threading.Thread(target=_spin, name="rclpy-local-map", daemon=True)
            self._spin_thread.start()
            logger.info("RosLocalMapCollector started topic=%s", self._map_topic or "(none)")
        except Exception as e:
            self._start_error = str(e)
            logger.exception("RosLocalMapCollector failed to start: %s", e)

    def snapshot(self) -> dict[str, Any]:
        self._ensure_started()
        if self._start_error:
            return {"map": {}, "error": self._start_error}
        with self._lock:
            return {"map": dict(self._map_payload) if self._map_payload else {}}


def _format_snapshot_for_print(data: dict[str, Any], *, max_points_preview: int = 5) -> str:
    display = dict(data)
    map_obj = display.get("map")
    if isinstance(map_obj, dict):
        m = dict(map_obj)
        pts = m.get("points")
        if isinstance(pts, list) and len(pts) > max_points_preview:
            m["points"] = pts[:max_points_preview]
            m["_points_preview"] = f"{max_points_preview} of {len(pts)}"
        display["map"] = m
    return json.dumps(display, ensure_ascii=False, indent=2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    collector = RosLocalMapCollector(
        map_topic="/glio_map",
        map_field_path=":",
        map_message_type="sensor_msgs/msg/PointCloud2",
    )

    duration_sec = 15.0
    interval_sec = 1.0
    deadline = time.monotonic() + duration_sec
    n = 0
    print(f"RosLocalMapCollector debug: topic={collector._map_topic!r} (Ctrl+C 可提前退出)\n")
    try:
        while time.monotonic() < deadline:
            n += 1
            snap = collector.snapshot()
            print(f"--- snapshot #{n} @ {time.strftime('%H:%M:%S')} ---")
            print(_format_snapshot_for_print(snap))
            print()
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n(interrupted)")


if __name__ == "__main__":
    main()
