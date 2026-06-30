from __future__ import annotations

import logging
import struct
import urllib.request
import json
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:1888"
_TIMEOUT_SEC = 10


class XosLocalMapCollector:
    """通过 XOS HTTP 接口获取当前导航地图点云（完整点集，不抽稀）。"""

    def __init__(
        self,
        *,
        xos_host: str = _DEFAULT_HOST,
    ) -> None:
        self._host = xos_host.rstrip("/")
        self._cached_map: str | None = None
        self._cached_payload: dict[str, Any] = {}

    def _post(self, path: str) -> dict[str, Any]:
        url = self._host + path
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            return json.loads(resp.read())

    def _get_pcd(self, path: str) -> bytes:
        url = self._host + path
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:
            return resp.read()

    def snapshot(self) -> dict[str, Any]:
        # 1. 获取当前默认地图名
        try:
            result = self._post("/robot/navigate/get_default_map")
        except Exception:
            logger.exception("XOS get_default_map failed")
            return {"map": {}}

        if not result or result.get("code") != 200 or not result.get("data"):
            logger.warning("XOS get_default_map unexpected response: %s", result)
            return {"map": {}}

        map_name = result["data"]

        # 2. 如果地图没变，直接返回缓存
        if map_name == self._cached_map and self._cached_payload:
            return {"map": dict(self._cached_payload)}

        # 3. 下载 PCD
        import urllib.parse
        encoded_name = urllib.parse.quote(map_name, safe="")
        pcd_path = f"/robot/navigate/load_map/{encoded_name}/lidar_map.pcd"
        try:
            pcd_bytes = self._get_pcd(pcd_path)
        except Exception:
            logger.exception("XOS download PCD failed: %s", pcd_path)
            return {"map": {}}

        # 4. 解析 PCD 二进制
        payload = self._parse_pcd(pcd_bytes)
        if not payload:
            return {"map": {}}

        # 携带地图名，供前端按地图隔离对齐标定（每张点云图各自保存一份标定）
        payload["map_name"] = map_name

        self._cached_map = map_name
        self._cached_payload = payload
        return {"map": dict(payload)}

    def _parse_pcd(self, data: bytes) -> dict[str, Any]:
        # 分离 header 和 binary body
        sep = b"DATA binary\n"
        idx = data.find(sep)
        if idx < 0:
            logger.warning("PCD: 'DATA binary' marker not found")
            return {}
        body = data[idx + len(sep) :]

        # 从 header 解析 WIDTH
        header = data[:idx].decode("ascii", errors="ignore")
        width = 0
        height = 0
        for line in header.splitlines():
            if line.startswith("WIDTH"):
                width = int(line.split()[1])
            elif line.startswith("HEIGHT"):
                height = int(line.split()[1])
            elif line.startswith("POINTS"):
                pass  # derived from body size

        # FIELDS x y z intensity → 每点 4×float32 = 16 bytes
        point_size = 16
        total = len(body) // point_size

        pts: list[list[float]] = []
        for i in range(total):
            offset = i * point_size
            x, y = struct.unpack_from("ff", body, offset)
            pts.append([round(x, 4), round(y, 4)])

        return {
            "frame_id": "map",
            "points": pts,
            "point_count": len(pts),
            "width": width,
            "height": height,
        }
