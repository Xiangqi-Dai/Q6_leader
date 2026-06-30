from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


Point = list[float]


def _dedupe_points(points: list[Point]) -> list[Point]:
    seen: set[tuple[float, float]] = set()
    out: list[Point] = []
    for x, y in points:
        key = (round(x, 4), round(y, 4))
        if key not in seen:
            seen.add(key)
            out.append([key[0], key[1]])
    return out


def _sample_rect_fill(
    points: list[Point],
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    step: float,
) -> None:
    """
    生成实心矩形点云，用于模拟有厚度的墙体。
    """
    x = x_min
    while x <= x_max:
        y = y_min
        while y <= y_max:
            points.append([round(x, 4), round(y, 4)])
            y += step
        x += step


def _sample_h_wall(
    points: list[Point],
    *,
    x1: float,
    x2: float,
    y: float,
    thickness: float,
    step: float,
) -> None:
    _sample_rect_fill(
        points,
        x_min=min(x1, x2),
        x_max=max(x1, x2),
        y_min=y - thickness / 2,
        y_max=y + thickness / 2,
        step=step,
    )


def _sample_v_wall(
    points: list[Point],
    *,
    x: float,
    y1: float,
    y2: float,
    thickness: float,
    step: float,
) -> None:
    _sample_rect_fill(
        points,
        x_min=x - thickness / 2,
        x_max=x + thickness / 2,
        y_min=min(y1, y2),
        y_max=max(y1, y2),
        step=step,
    )


def _generate_latest_layout_wall_points(
    *,
    step: float = 0.05,
    wall_thickness: float = 0.08,
) -> list[Point]:
    """
    根据你最新这张图生成点云：
    - 只生成褐色墙体点云
    - 其余区域保持空白
    - 墙体为横平竖直
    """

    pts: list[Point] = []
    t = wall_thickness

    # ==========================================================
    # 1. 上方大房间（A3 对应区域）
    # ==========================================================
    _sample_h_wall(pts, x1=-9.2, x2=1.4, y=7.0, thickness=t, step=step)
    _sample_h_wall(pts, x1=-9.2, x2=1.4, y=5.1, thickness=t, step=step)
    _sample_v_wall(pts, x=-9.2, y1=5.1, y2=7.0, thickness=t, step=step)
    _sample_v_wall(pts, x=1.4, y1=5.1, y2=7.0, thickness=t, step=step)

    # ==========================================================
    # 2. 左侧房间（A2 对应区域）
    # ==========================================================
    _sample_h_wall(pts, x1=-9.2, x2=-5.4, y=5.1, thickness=t, step=step)
    _sample_h_wall(pts, x1=-9.2, x2=-5.4, y=1.2, thickness=t, step=step)
    _sample_v_wall(pts, x=-9.2, y1=1.2, y2=5.1, thickness=t, step=step)

    # 右边留门洞：上段 + 下段
    _sample_v_wall(pts, x=-5.4, y1=2.2, y2=5.1, thickness=t, step=step)
    _sample_v_wall(pts, x=-5.4, y1=1.2, y2=1.5, thickness=t, step=step)

    # ==========================================================
    # 3. 主横向大走廊 / 外轮廓
    # ==========================================================

    # 顶边：分段（中间与 A3 相接，左侧留一点空隙）
    _sample_h_wall(pts, x1=-2.0, x2=8.8, y=5.0, thickness=t, step=step)

    # 底边：中间给下行通道留开口
    _sample_h_wall(pts, x1=-5.4, x2=-1.0, y=1.2, thickness=t, step=step)
    _sample_h_wall(pts, x1=0.1, x2=8.8, y=1.2, thickness=t, step=step)

    # 右侧竖边
    _sample_v_wall(pts, x=8.8, y1=1.2, y2=5.0, thickness=t, step=step)

    # ==========================================================
    # 4. 中间左侧内部矩形
    # 顶边留一个小缺口（和图一致）
    # ==========================================================
    _sample_h_wall(pts, x1=-3.3, x2=-1.1, y=4.0, thickness=t, step=step)
    # 顶边右侧不封死，留小口
    _sample_h_wall(pts, x1=-3.3, x2=-0.4, y=2.9, thickness=t, step=step)
    _sample_v_wall(pts, x=-3.3, y1=2.9, y2=4.0, thickness=t, step=step)
    _sample_v_wall(pts, x=-0.4, y1=2.9, y2=4.0, thickness=t, step=step)

    # 修正：底边
    _sample_h_wall(pts, x1=-3.3, x2=-0.4, y=2.9, thickness=t, step=step)

    # 由于上面画法略重复，为了符合图中矩形：
    _sample_h_wall(pts, x1=-3.3, x2=-1.3, y=4.0, thickness=t, step=step)

    # 更完整一些：右边向下闭合
    _sample_v_wall(pts, x=-0.4, y1=2.9, y2=4.0, thickness=t, step=step)

    # ==========================================================
    # 5. 中间右侧内部矩形
    # 顶边留一个小缺口
    # ==========================================================
    _sample_h_wall(pts, x1=0.9, x2=3.7, y=4.0, thickness=t, step=step)
    _sample_h_wall(pts, x1=4.2, x2=6.8, y=4.0, thickness=t, step=step)
    _sample_h_wall(pts, x1=0.9, x2=6.8, y=2.9, thickness=t, step=step)
    _sample_v_wall(pts, x=0.9, y1=2.9, y2=4.0, thickness=t, step=step)
    _sample_v_wall(pts, x=6.8, y1=2.9, y2=4.0, thickness=t, step=step)

    # ==========================================================
    # 6. 中央向下走廊
    # ==========================================================
    _sample_v_wall(pts, x=-1.0, y1=-4.8, y2=1.2, thickness=t, step=step)
    _sample_v_wall(pts, x=0.1, y1=-4.8, y2=1.2, thickness=t, step=step)
    _sample_h_wall(pts, x1=-1.0, x2=0.1, y=-4.8, thickness=t, step=step)

    # ==========================================================
    # 7. 去重（生成阶段重叠墙体可能产生重复坐标）
    # ==========================================================
    pts = _dedupe_points(pts)

    return pts


def generate_local_map_mock(mock_config: dict[str, Any]) -> dict[str, Any]:
    """
    生成和你最新图片对应的 local_map mock 数据。
    褐色墙体 -> points 点云
    其余区域 -> 空白
    """
    fixture = str(mock_config.get("fixture_file", "")).strip()

    if fixture:
        path = Path(fixture)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / fixture
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "map" in raw:
                return {"map": dict(raw["map"])}
            if isinstance(raw, dict):
                return {"map": raw}

    points = _generate_latest_layout_wall_points(
        step=float(mock_config.get("step", 0.05)),
        wall_thickness=float(mock_config.get("wall_thickness", 0.08)),
    )

    return {
        "map": {
            "frame_id": str(mock_config.get("frame_id", "map")),
            "points": points,
            "point_count": len(points),
            "width": int(mock_config.get("width", 400)),
            "height": int(mock_config.get("height", 400)),
            "bounds": {
                "x_min": -10.0,
                "x_max": 10.0,
                "y_min": -5.2,
                "y_max": 7.5,
            },
        }
    }


def save_map_preview(
    local_map: dict[str, Any],
    output_path: str = "latest_layout_pointcloud_preview.png",
) -> None:
    """
    将 points 可视化：
    - 褐色点云 = 墙体
    - 其他区域 = 空白
    """
    points = local_map["map"]["points"]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    bounds = local_map["map"].get(
        "bounds",
        {
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
        },
    )

    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.scatter(
        xs,
        ys,
        s=4,
        c="#6f2c2c",   # 褐色
        marker="s",
        linewidths=0,
        alpha=0.95,
    )

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(bounds["x_min"], bounds["x_max"])
    ax.set_ylim(bounds["y_min"], bounds["y_max"])
    ax.axis("off")

    plt.tight_layout(pad=0)
    plt.savefig(output_path, dpi=200, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


if __name__ == "__main__":
    data = generate_local_map_mock(
        {
            "step": 0.05,
            "wall_thickness": 0.08,
            "width": 400,
            "height": 400,
        }
    )

    Path("latest_layout_local_map.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    save_map_preview(data, "latest_layout_pointcloud_preview.png")

    print(f"points: {data['map']['point_count']}")
    print("saved: latest_layout_local_map.json")
    print("saved: latest_layout_pointcloud_preview.png")