#!/usr/bin/env python3
# Copyright 2026 Enactic, Inc.
#
# 独立硬件测试脚本 — 验证主臂(leader)低力矩重力补偿模式。
# 不依赖 dora, 直接调用 openarm_can + MuJoCo URDF 重力模型。
#
# 用途(进数据采集 dataflow 前先在这里确认方向, 安全!):
#   1. 重力补偿是否方向正确: 松手后手臂应"悬浮"在原位(不上扬、不快速下坠)。
#      若手臂快速下坠/加速甩出 → 方向反了, 立刻 Ctrl-C 并把 gain 取负或检查。
#   2. 对比"指令力矩 gain*G"与"实测力矩": 两者应相近且符号一致。
#
# 安全建议:
#   - 第一次务必 --gain 0.3 起步, 手扶住手臂, 确认方向后再调到 0.7。
#   - 脚本只补偿肩(J2)+肘(J4), 其余关节 tau=0。
#
# 运行(确保 CAN 口已 up):
#   sudo ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on
#   sudo ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on
#   python3 test_leader_gravity_comp.py --gain 0.3
#
# 选项:
#   --only left|right|both   只测单臂(默认 both)
#   --gain G                 重力补偿增益(默认 0.5; 首测建议 0.3)
#   --joints 2,4             被补偿关节(1-based; 默认 2,4 = 肩+肘)
#   --left-can / --right-can  CAN 口(默认 can_slot1_ch0 / can_slot1_ch1)
#   --control-hz N           发帧频率(默认 100)   --print-hz N  刷新频率(默认 20)

import argparse
import sys
import time

import numpy as np
import openarm_can as oa

# 显式用 wanren 副本(与 dataflow build 一致), 避免误用其它已安装副本。
sys.path.insert(
    0,
    "/ros2_ws/wanren/dora_env/dora-openarm-data-collection/nodes/dora-openarm-leader/src",
)
from dora_openarm_leader.gravity import GravityCompensator  # noqa: E402

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
SHOULDER_ELBOW = {1, 3}  # 0-based motor idx: J2(肩), J4(肘)



class ArmHandle:
    """单臂封装: 对象 + 重力补偿器 + 最近一帧的指令力矩。"""

    def __init__(self, name, can_interface, compensator, gain, mask):
        self.name = name
        self.can_interface = can_interface
        self.compensator = compensator
        self.gain = gain
        self.mask = mask
        self.commanded_tau = np.zeros(N_MOTORS)
        print(f"  [{name}] 打开 CAN 口 {can_interface} (CAN-FD) ...")
        self.arm = oa.OpenArm(can_interface, enable_fd=True)
        self.arm.init_arm_motors(
            MOTOR_TYPES,
            SEND_CAN_IDS,
            RECV_CAN_IDS,
            [oa.ControlMode.MIT] * N_MOTORS,
        )
        self.arm.set_callback_mode_all(oa.CallbackMode.STATE)
        self.arm.enable_all()
        self.arm.recv_all()
        self.motors = self.arm.get_arm().get_motors()
        self.initial = self.read_positions()

    def read_positions(self):
        return np.array([m.get_position() for m in self.motors], dtype=np.float64)

    def read_torques(self):
        return np.array([m.get_torque() for m in self.motors], dtype=np.float64)

    def step(self):
        """读位姿 → 算重力 → 只对 mask 关节下发 gain*G, 其余 tau=0。"""
        self.arm.recv_all()
        positions = np.array(
            [m.get_position() for m in self.motors], dtype=np.float64
        )
        gravity = self.compensator.gravity(self.side, positions)
        tau = np.zeros(N_MOTORS, dtype=np.float64)
        for i in self.mask:
            tau[i] = self.gain * gravity[i]
        self.commanded_tau = tau
        self.arm.get_arm().mit_control_all(
            [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=float(tau[i])) for i in range(N_MOTORS)]
        )

    def disable(self):
        try:
            self.arm.disable_all()
            print(f"  [{self.name}] 已失能")
        except Exception as e:  # noqa: BLE001
            print(f"  [{self.name}] 失能失败: {e}", file=sys.stderr)



def render(arms, gain, mask, elapsed):
    sys.stdout.write("\033[2J\033[H")
    print("=" * 70)
    print(f" OpenArm 主臂重力补偿测试  gain={gain}  joints={sorted(i+1 for i in mask)}  "
          f"运行 {elapsed:6.1f}s  Ctrl-C 退出")
    print("=" * 70)
    for h in arms:
        pos = h.read_positions()
        tau = h.read_torques()
        enabled = all(m.is_enabled() for m in h.motors)
        print(f" {h.name:5s}  {h.can_interface}  使能:{'是' if enabled else '否'}")
        print(f"   {'关节':>4s}  {'角度rad':>9s}  {'指令τ':>8s}  {'实测τ':>8s}  {'重力G':>8s}")
        G = h.compensator.gravity(h.side, pos)
        for i in range(N_MOTORS):
            tag = " ←补" if i in mask else ""
            print(
                f"   {JOINT_LABELS[i]:>4s}  {pos[i]:9.3f}  "
                f"{h.commanded_tau[i]:+8.3f}  {tau[i]:+8.3f}  {G[i]:+8.3f}{tag}"
            )
        print("-" * 70)
    print(" 验证: 松手→手臂应悬浮(不下坠/不甩)。指令τ与实测τ应相近同号。")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="主臂重力补偿硬件测试")
    parser.add_argument("--only", choices=["left", "right", "both"], default="both")
    parser.add_argument("--gain", type=float, default=0.5, help="重力补偿增益(首测建议 0.3)")
    parser.add_argument("--joints", default="2,4", help="被补偿关节 1-based(默认 2,4)")
    parser.add_argument("--left-can", default="can_slot1_ch0")
    parser.add_argument("--right-can", default="can_slot1_ch1")
    parser.add_argument("--control-hz", type=int, default=100)
    parser.add_argument("--print-hz", type=int, default=20)
    args = parser.parse_args()

    mask = {int(j) - 1 for j in args.joints.split(",") if j.strip()}
    print(f">> 加载 MuJoCo 双臂 URDF 重力模型 ...")
    comp = GravityCompensator()
    print(f">> 初始化主臂(MIT 模式, 重力补偿: 关节={sorted(i+1 for i in mask)} gain={args.gain}) ...")

    arms = []
    try:
        if args.only in ("left", "both"):
            h = ArmHandle("左臂", args.left_can, comp, args.gain, mask)
            h.side = "left"
            arms.append(h)
        if args.only in ("right", "both"):
            h = ArmHandle("右臂", args.right_can, comp, args.gain, mask)
            h.side = "right"
            arms.append(h)
    except Exception as e:  # noqa: BLE001
        print(f"\n[错误] 硬件初始化失败: {e}", file=sys.stderr)
        print(
            "排查: 1) CAN 口是否 up+fd "
            "(sudo ip link set <iface> up type can bitrate 1000000 dbitrate 5000000 fd on)\n"
            "      2) CAN 口名  3) 电机供电/接线  4) 是否需要 sudo",
            file=sys.stderr,
        )
        for h in arms:
            h.disable()
        sys.exit(1)


    period = 1.0 / args.control_hz
    print_every = max(1, round(args.control_hz / args.print_hz))
    print(f">>> 进入重力补偿循环(控制 {args.control_hz}Hz)。手扶手臂! Ctrl-C 退出。")

    count = 0
    start = time.time()
    try:
        while True:
            for h in arms:
                h.step()
            count += 1
            if count % print_every == 0:
                render(arms, args.gain, mask, time.time() - start)
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n>>> 收到 Ctrl-C, 正在停止 ...")
    finally:
        for h in arms:
            h.disable()
        print(">>> 已退出。")


if __name__ == "__main__":
    main()
