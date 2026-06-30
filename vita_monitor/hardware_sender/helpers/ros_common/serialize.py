from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def pointcloud2_to_map_payload(cloud: Any) -> dict[str, Any]:
    """sensor_msgs/msg/PointCloud2 → 完整 2D 点云 JSON（不抽稀、不截断）。"""
    try:
        from sensor_msgs_py import point_cloud2
    except ImportError:
        logger.warning("sensor_msgs_py unavailable, map payload will be empty")
        return {}

    pts: list[list[float]] = []
    try:
        it = point_cloud2.read_points(cloud, field_names=("x", "y"), skip_nans=True)
        for p in it:
            pts.append([float(p[0]), float(p[1])])
    except Exception:
        logger.exception("pointcloud2_to_map_payload: read_points failed")
        return {}

    try:
        w = int(cloud.width)
        h = int(cloud.height)
    except Exception:
        w, h = 0, 0

    return {
        "frame_id": str(cloud.header.frame_id),
        "points": pts,
        "point_count": len(pts),
        "width": w,
        "height": h,
    }


def pointcloud2_to_minimal(cloud: Any, *, max_points: int, stride: int) -> dict[str, Any]:
    """已废弃：请使用 pointcloud2_to_map_payload。保留以兼容旧调用方。"""
    payload = pointcloud2_to_map_payload(cloud)
    if not payload:
        return {}
    stride = max(1, int(stride))
    max_points = max(1, int(max_points))
    pts = payload["points"][::stride][:max_points]
    return {
        "frame_id": payload["frame_id"],
        "points": pts,
        "sampled_count": len(pts),
        "stride": stride,
        "width": payload["width"],
        "height": payload["height"],
    }


def pose_stamped_to_minimal(pose_msg: Any) -> dict[str, Any]:
    """geometry_msgs/msg/PoseStamped → 轻量 JSON。"""
    try:
        pos = pose_msg.pose.position
        ori = pose_msg.pose.orientation
        return {
            "frame_id": str(pose_msg.header.frame_id),
            "position": {
                "x": float(pos.x),
                "y": float(pos.y),
                "z": float(pos.z),
            },
            "orientation": {
                "x": float(ori.x),
                "y": float(ori.y),
                "z": float(ori.z),
                "w": float(ori.w),
            },
        }
    except Exception:
        logger.exception("pose_stamped_to_minimal failed")
        return {}
