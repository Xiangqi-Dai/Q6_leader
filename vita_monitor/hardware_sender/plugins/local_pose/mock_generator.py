from __future__ import annotations

import math
import time
from typing import Any


class LocalPoseMockGenerator:
    def __init__(self, mock_config: dict[str, Any]) -> None:
        self._cfg = mock_config
        self._started_at = time.monotonic()

        self._trajectory = str(mock_config.get("trajectory", "circle")).strip().lower()

        # circle 参数
        self._radius = float(mock_config.get("radius", 3.0))

        # 通用参数
        self._speed = float(mock_config.get("speed", 0.3))
        self._frame_id = str(mock_config.get("frame_id", "map"))
        self._z = float(mock_config.get("z", 0.0))

        # line_pingpong 参数：从左到右、再从右到左
        self._start_x = float(mock_config.get("start_x", -3.0))
        self._start_y = float(mock_config.get("start_y", 0.0))
        self._end_x = float(mock_config.get("end_x", 3.0))
        self._end_y = float(mock_config.get("end_y", 0.0))

    def snapshot(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._started_at

        if self._trajectory == "static":
            x = float(self._cfg.get("x", 0.0))
            y = float(self._cfg.get("y", 0.0))
            yaw = float(self._cfg.get("yaw", 0.0))

        elif self._trajectory == "line":
            heading = float(self._cfg.get("heading", 0.0))
            distance = elapsed * self._speed

            x = math.cos(heading) * distance
            y = math.sin(heading) * distance
            yaw = heading

        elif self._trajectory in ("line_pingpong", "pingpong", "back_and_forth"):
            x, y, yaw = self._line_pingpong(elapsed)

        else:
            # 默认画圆
            t = elapsed * self._speed

            x = self._radius * math.cos(t)
            y = self._radius * math.sin(t)
            yaw = t + math.pi / 2

        half_yaw = yaw / 2.0

        return {
            "location": {
                "frame_id": self._frame_id,
                "position": {
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "z": self._z,
                },
                "orientation": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": round(math.sin(half_yaw), 6),
                    "w": round(math.cos(half_yaw), 6),
                },
            }
        }

    def _line_pingpong(self, elapsed: float) -> tuple[float, float, float]:
        """
        沿 start 点和 end 点之间往返运动：
        start -> end -> start -> end ...
        """

        dx = self._end_x - self._start_x
        dy = self._end_y - self._start_y
        length = math.hypot(dx, dy)

        # 避免起点终点重合导致除零
        if length <= 1e-9:
            return self._start_x, self._start_y, 0.0

        # 机器人沿线运动的距离
        distance = elapsed * self._speed

        # 一个完整往返周期长度：去程 length + 回程 length
        cycle_length = 2.0 * length

        # 当前在周期内走了多少
        phase = distance % cycle_length

        if phase <= length:
            # 去程：start -> end
            progress = phase / length
            yaw = math.atan2(dy, dx)
        else:
            # 回程：end -> start
            progress = 1.0 - (phase - length) / length
            yaw = math.atan2(-dy, -dx)

        x = self._start_x + progress * dx
        y = self._start_y + progress * dy

        return x, y, yaw