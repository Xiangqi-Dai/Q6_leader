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
from helpers.ros_common.serialize import pose_stamped_to_minimal

logger = logging.getLogger(__name__)


class RosLocalPoseCollector:
    """采集进程内订阅位姿话题，缓存最小 location 载荷。"""

    def __init__(
        self,
        *,
        pose_topic: str,
        pose_message_type: str,
        pose_field_path: str,
    ) -> None:
        self._pose_topic = pose_topic.strip()
        self._pose_message_type = pose_message_type.strip()
        self._pose_field_path = pose_field_path

        self._lock = threading.Lock()
        self._location_payload: dict[str, Any] = {}
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
            from geometry_msgs.msg import PoseStamped
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.node import Node

            rclpy.init(args=None)
            self._node = Node("local_pose_hw_sender")

            pose_msg_cls = import_message_class(self._pose_message_type)
            pose_segments = parse_field_path(self._pose_field_path)

            def on_pose(msg: Any) -> None:
                try:
                    inner = navigate_fields(msg, pose_segments) if pose_segments else msg
                    if not isinstance(inner, PoseStamped):
                        logger.warning(
                            "pose field is not PoseStamped (got %s), skip",
                            type(inner).__name__,
                        )
                        return
                    payload = pose_stamped_to_minimal(inner)
                    with self._lock:
                        self._location_payload = payload
                except Exception:
                    logger.exception("local_pose callback failed")

            if self._pose_topic:
                self._node.create_subscription(pose_msg_cls, self._pose_topic, on_pose, 10)
            else:
                logger.warning("pose_topic empty, no pose subscription")

            executor = MultiThreadedExecutor()

            def _spin() -> None:
                try:
                    executor.add_node(self._node)
                    executor.spin()
                except Exception:
                    logger.exception("local_pose executor.spin ended with error")

            self._spin_thread = threading.Thread(target=_spin, name="rclpy-local-pose", daemon=True)
            self._spin_thread.start()
            logger.info("RosLocalPoseCollector started topic=%s", self._pose_topic or "(none)")
        except Exception as e:
            self._start_error = str(e)
            logger.exception("RosLocalPoseCollector failed to start: %s", e)

    def snapshot(self) -> dict[str, Any]:
        self._ensure_started()
        if self._start_error:
            return {"location": {}, "error": self._start_error}
        with self._lock:
            return {"location": dict(self._location_payload) if self._location_payload else {}}


def main() -> None:
    # 与 config_q5.yaml → sender.plugins.local_pose.kwargs + interval_sec 一致
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    collector = RosLocalPoseCollector(
        pose_topic="/get_pose",
        pose_field_path=":head_pose:",
        pose_message_type="geometry_msgs/msg/PoseStamped",
    )

    duration_sec = 15.0
    interval_sec = 0.5
    deadline = time.monotonic() + duration_sec
    n = 0
    print(f"RosLocalPoseCollector debug: topic={collector._pose_topic!r} (Ctrl+C 可提前退出)\n")
    try:
        while time.monotonic() < deadline:
            n += 1
            snap = collector.snapshot()
            print(f"--- snapshot #{n} @ {time.strftime('%H:%M:%S')} ---")
            print(json.dumps(snap, ensure_ascii=False, indent=2))
            print()
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n(interrupted)")


if __name__ == "__main__":
    main()
