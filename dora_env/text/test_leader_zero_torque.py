#!/usr/bin/env python3
# Copyright 2026 Enactic, Inc.
#
# 独立硬件测试脚本 — 只验证主臂(leader)零力矩模式 + 实时打印关节角。
# 不依赖 dora,直接调用 openarm_can C++ 绑定。
#
# 用途:
#   1. 验证 CAN 通信 / 电机使能 / 编码器读数是否正常(拖动时角度随动)。
#   2. 验证零力矩是否生效(拖动时电机不抵抗,tau ≈ 0)。
#
# 运行(确保 CAN 口已 up):
#   sudo ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on
#   sudo ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on
#   python3 test_leader_zero_torque.py
#
# 选项:
#   --only left|right|both   只测单臂(隔离定位硬件问题,默认 both)
#   --left-can NAME          左臂 CAN 口(默认 can_slot1_ch0)
#   --right-can NAME         右臂 CAN 口(默认 can_slot1_ch1)
#   --control-hz N           发零力矩帧的频率(默认 100)
#   --print-hz N             屏幕刷新频率(默认 20)

import argparse
import sys
import time

import numpy as np
import openarm_can as oa

# 7-DoF 臂 + 夹爪(DM3507),与 openarm_driver/config.yaml 一致。
MOTOR_TYPES = [
    oa.MotorType.DM8009,
    oa.MotorType.DM8009,
    oa.MotorType.DM4340,
    oa.MotorType.DM4340,
    oa.MotorType.DM4310,
    oa.MotorType.DM4310,
    oa.MotorType.DM4310,
    oa.MotorType.DM3507,
]
SEND_CAN_IDS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
RECV_CAN_IDS = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18]
N_MOTORS = len(MOTOR_TYPES)
JOINT_LABELS = ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "GR"]
ZERO_MIT = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]


class ArmHandle:
    """单臂封装:对象 + 初始位置基准(用于算 delta)。"""

    def __init__(self, name, can_interface):
        self.name = name
        self.can_interface = can_interface
        print(f"  [{name}] 打开 CAN 口 {can_interface} (CAN-FD) ...")
        self.arm = oa.OpenArm(can_interface, enable_fd=True)
        print(f"  [{name}] 初始化 {N_MOTORS} 个电机 ...")
        self.arm.init_arm_motors(
            MOTOR_TYPES,
            SEND_CAN_IDS,
            RECV_CAN_IDS,
            [oa.ControlMode.MIT] * N_MOTORS,
        )
        self.arm.set_callback_mode_all(oa.CallbackMode.STATE)
        print(f"  [{name}] 使能电机 ...")
        self.arm.enable_all()
        self.arm.recv_all()
        self.motors = self.arm.get_arm().get_motors()
        self.initial = self.read_positions()

    def read_positions(self):
        return np.array([m.get_position() for m in self.motors], dtype=np.float64)

    def read_torques(self):
        return np.array([m.get_torque() for m in self.motors], dtype=np.float64)

    def step(self):
        """发一帧零力矩 + 读最新状态。"""
        self.arm.get_arm().mit_control_all(ZERO_MIT)
        self.arm.recv_all()

    def disable(self):
        try:
            self.arm.disable_all()
            print(f"  [{self.name}] 已失能")
        except Exception as e:  # noqa: BLE001
            print(f"  [{self.name}] 失能失败: {e}", file=sys.stderr)


def render(arms, elapsed):
    """清屏重绘当前状态表。"""
    sys.stdout.write("\033[2J\033[H")
    print("=" * 64)
    print(f" OpenArm 主臂零力矩硬件测试   运行 {elapsed:6.1f}s   Ctrl-C 退出")
    print("=" * 64)
    for h in arms:
        pos = h.read_positions()
        tau = h.read_torques()
        delta = pos - h.initial
        enabled = all(m.is_enabled() for m in h.motors)
        print(
            f" {h.name:5s}  {h.can_interface}  "
            f"使能:{'是' if enabled else '否'}"
        )
        print(f"   {'关节':>4s}  {'角度(rad)':>10s}  {'变化Δ(rad)':>11s}  {'力矩(Nm)':>9s}")
        for i in range(N_MOTORS):
            print(
                f"   {JOINT_LABELS[i]:>4s}  {pos[i]:10.4f}  "
                f"{delta[i]:+11.4f}  {tau[i]:9.3f}"
            )
        print("-" * 64)
    print(" 提示: 手拖主臂 → 角度/变化应随之变动,力矩应保持 ≈ 0(零力矩生效)")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="主臂零力矩硬件测试")
    parser.add_argument(
        "--only",
        choices=["left", "right", "both"],
        default="both",
        help="只测某一侧臂(默认 both)",
    )
    parser.add_argument("--left-can", default="can_slot1_ch0", help="左臂 CAN 口")
    parser.add_argument("--right-can", default="can_slot1_ch1", help="右臂 CAN 口")
    parser.add_argument("--control-hz", type=int, default=100, help="发帧频率 Hz")
    parser.add_argument("--print-hz", type=int, default=20, help="刷新频率 Hz")
    args = parser.parse_args()

    print(">>> 初始化主臂(零力矩 MIT 模式)...")
    arms = []
    try:
        if args.only in ("left", "both"):
            arms.append(ArmHandle("左臂", args.left_can))
        if args.only in ("right", "both"):
            arms.append(ArmHandle("右臂", args.right_can))
    except Exception as e:  # noqa: BLE001
        print(f"\n[错误] 硬件初始化失败: {e}", file=sys.stderr)
        print(
            "排查: 1) CAN 口是否已 up 且为 fd 模式 "
            "(sudo ip link set <iface> up type can bitrate 1000000 dbitrate 5000000 fd on)\n"
            "      2) CAN 口名是否正确  3) 电机供电/接线  4) 是否需要 sudo",
            file=sys.stderr,
        )
        for h in arms:
            h.disable()
        sys.exit(1)

    control_period = 1.0 / args.control_hz
    print_every = max(1, round(args.control_hz / args.print_hz))
    print(f">>> 进入零力矩循环(控制 {args.control_hz}Hz / 刷新 "
          f"{args.control_hz // print_every}Hz),拖动主臂观察,Ctrl-C 退出。")

    count = 0
    start = time.time()
    try:
        while True:
            for h in arms:
                h.step()  # 持续发零力矩帧 + 读位(每帧)
            count += 1
            if count % print_every == 0:
                render(arms, time.time() - start)
            time.sleep(control_period)
    except KeyboardInterrupt:
        print("\n>>> 收到 Ctrl-C,正在停止 ...")
    finally:
        for h in arms:
            h.disable()
        print(">>> 已退出。")


if __name__ == "__main__":
    main()
