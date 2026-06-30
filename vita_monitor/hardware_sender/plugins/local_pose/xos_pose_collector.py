from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:1888/robot/navigate/get_navigate_realtime_pose"
_DEFAULT_FRAME_ID = "map"
_DEFAULT_TIMEOUT_SEC = 3.0


class XosLocalPoseCollector:
    """通过 XOS HTTP POST 接口获取当前导航位姿。"""

    def __init__(
        self,
        *,
        xos_url: str = _DEFAULT_URL,
        frame_id: str = _DEFAULT_FRAME_ID,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self._url = (xos_url or "").strip() or _DEFAULT_URL
        self._frame_id = frame_id or _DEFAULT_FRAME_ID
        self._timeout_sec = max(0.5, float(timeout_sec))

    def _post(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
            return json.loads(resp.read())

    def snapshot(self) -> dict[str, Any]:
        try:
            resp = self._post(self._url)
        except Exception:
            logger.exception("XOS get_navigate_realtime_pose failed: %s", self._url)
            return {"location": {}}

        if not resp or resp.get("code") != 200 or not resp.get("data"):
            logger.warning("XOS navigate_realtime_pose unexpected response: %s", resp)
            return {"location": {}}

        d = resp["data"]
        try:
            location = {
                "frame_id": self._frame_id,
                "position": {
                    "x": float(d["x"]),
                    "y": float(d["y"]),
                    "z": float(d["z"]),
                },
                "orientation": {
                    "x": float(d["qx"]),
                    "y": float(d["qy"]),
                    "z": float(d["qz"]),
                    "w": float(d["qw"]),
                },
            }
        except (KeyError, TypeError, ValueError):
            logger.exception("XOS navigate_realtime_pose data shape invalid: %s", d)
            return {"location": {}}

        return {"location": location}


def main() -> None:
    """手工调试入口：与 config.yaml → sender.plugins.local_pose.kwargs 一致。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    collector = XosLocalPoseCollector(
        xos_url=_DEFAULT_URL,
        frame_id="map",
        timeout_sec=3.0,
    )
    snap = collector.snapshot()
    print(json.dumps(snap, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
