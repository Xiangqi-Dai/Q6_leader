#!/usr/bin/env python3
"""
enable_openarm.py — OpenArm 双臂使能脚本 (只使能, 不运动)

复刻 openarm_ros2/openarm_hardware/src/openarm_simple_hardware.cpp 的 on_activate()
使能序列, 但**去掉 return_to_zero()**, 因此只发使能帧(0xFC), 不发任何 MIT 控制:
    set_callback_mode_all(STATE) → enable_all() → recv_all()
→ 电机抱住当前位置, 不回零位, 不运动.

电机型号 / CAN-ID 与 openarm_hardware 的 DEFAULT_* 完全一致
(见 openarm_simple_hardware.hpp 第 83-101 行).

用法:
    python3 enable_openarm.py enable              # 使能两臂(7关节+夹爪, 各8个)
    python3 enable_openarm.py enable left         # 只左臂
    python3 enable_openarm.py enable right        # 只右臂
    python3 enable_openarm.py disable             # 失能两臂(连发3次, 同 on_deactivate)
    python3 enable_openarm.py --no-can enable     # 跳过 CAN 口拉起(已配好时)
    python3 enable_openarm.py --help
"""
import sys
import time
import subprocess

from openarm_can import OpenArm, CallbackMode, MotorType

# ── 与 openarm_hardware DEFAULT_* 一致 (openarm_simple_hardware.hpp:83-101) ──
ARM_TYPES = [MotorType.DM8009, MotorType.DM8009, MotorType.DM4340,
             MotorType.DM4340, MotorType.DM4310, MotorType.DM4310, MotorType.DM4310]
ARM_SEND_IDS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]
ARM_RECV_IDS = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17]
GRIPPER_TYPE = MotorType.DM4310
GRIPPER_SEND_ID = 0x08
GRIPPER_RECV_ID = 0x18

# ── 现场配置: 左臂 ch0, 右臂 ch1 ────────────────────────────────
ARMS = {"left": "can_slot1_ch0", "right": "can_slot1_ch1"}
CAN_FD = True


def bringup_can(iface):
    """CAN-FD 1M/5M 拉起(CAN 配置不跨重启, 每次都要)."""
    subprocess.run(["sudo", "ip", "link", "set", iface, "down"],
                   stderr=subprocess.DEVNULL)
    r = subprocess.run(["sudo", "ip", "link", "set", iface, "up", "type", "can",
                        "bitrate", "1000000", "dbitrate", "5000000",
                        "fd", "on", "restart-ms", "1"])
    return r.returncode == 0


def make(iface):
    """构造 OpenArm 并初始化 7 关节 + 夹爪 (对应 on_init)."""
    oa = OpenArm(iface, CAN_FD)
    oa.init_arm_motors(ARM_TYPES, ARM_SEND_IDS, ARM_RECV_IDS)
    oa.init_gripper_motor(GRIPPER_TYPE, GRIPPER_SEND_ID, GRIPPER_RECV_ID)
    return oa


def enable_arm(name, iface):
    """复刻 on_activate 的使能部分, 不调 return_to_zero()."""
    oa = make(iface)
    oa.set_callback_mode_all(CallbackMode.STATE)   # ← on_activate 第 226 行
    oa.enable_all()                                 # ← 第 227 行: 使能(发0xFC)
    time.sleep(0.1)                                 # ← 第 228 行
    oa.recv_all()                                   # ← 第 229 行
    print(f"  [{name}] {iface}: 已使能 7关节+夹爪 (未发 MIT 控制 → 不运动)")


def disable_arm(name, iface):
    """复刻 on_deactivate: 连发 3 次 disable_all."""
    oa = make(iface)
    for _ in range(3):
        oa.disable_all()
        time.sleep(0.1)
        oa.recv_all()
    print(f"  [{name}] {iface}: 已失能")


def main():
    do_can = "--no-can" not in sys.argv
    args = [a for a in sys.argv[1:] if a != "--no-can"]
    cmd = args[0] if args else "enable"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return
    side = args[1] if len(args) > 1 else "both"
    if cmd not in ("enable", "disable"):
        print(f"未知命令: {cmd} (用 enable / disable)"); return
    if side == "both":
        targets = ARMS
    elif side in ARMS:
        targets = {side: ARMS[side]}
    else:
        print(f"未知臂: {side} (left / right / both)"); return

    if do_can:
        print("拉起 CAN 口...")
        for ifc in targets.values():
            print(f"  {ifc}: {'OK' if bringup_can(ifc) else '失败'}")

    print(f"=== {cmd} (复刻 on_activate, 无 return_to_zero) ===")
    fn = enable_arm if cmd == "enable" else disable_arm
    for n, ifc in targets.items():
        try:
            fn(n, ifc)
        except Exception as e:
            print(f"  [{n}] {ifc}: 出错 {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
