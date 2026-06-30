#!/usr/bin/env python3
"""测试节点:订阅主臂左右关节角,实时打印到终端。

仅供 leader 本地测试用,验证 leader 节点在 dora 下能正常输出角度。
"""

import sys
import time

import dora
import numpy as np

JOINT_LABELS = ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "GR"]
REFRESH_HZ = 20.0


def to_numpy(value):
    """把 dora 事件值转成 numpy float32 数组。"""
    if hasattr(value, "to_numpy"):
        return value.to_numpy().astype(np.float32)
    return np.array([v.as_py() for v in value], dtype=np.float32)


def render(left, right, n):
    """清屏重绘左右臂关节角。"""
    print("\033[2J\033[H", end="")
    print("=" * 56)
    print(" leader 节点实时关节角 (via dora)   帧数:%5d   Ctrl-C 退出" % n)
    print("=" * 56)
    for name, arr in (("左臂", left), ("右臂", right)):
        if arr is None:
            print(f" {name}: 等待数据...")
            continue
        cells = "  ".join(f"{JOINT_LABELS[i]}={arr[i]:+.3f}" for i in range(len(arr)))
        print(f" {name}: {cells}")
    print("-" * 56)
    sys.stdout.flush()


def main():
    """订阅 position_left/right 并以 ~20Hz 刷新打印。"""
    node = dora.Node()
    left = None
    right = None
    last_print = 0.0
    count = 0
    for event in node:
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        if eid == "position_left":
            left = to_numpy(event["value"])
        elif eid == "position_right":
            right = to_numpy(event["value"])
        else:
            continue

        count += 1
        now = time.time()
        if now - last_print < 1.0 / REFRESH_HZ:
            continue
        last_print = now
        render(left, right, count)


if __name__ == "__main__":
    main()
