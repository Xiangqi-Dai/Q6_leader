#!/usr/bin/env python3
"""
right_arm_slot2.py — 右臂电机控制脚本 (不依赖 ROS)

复刻 openarm_ros2/openarm_hardware/src/openarm_simple_hardware.cpp 的三个阶段,
对应这条 launch 指令背后的硬件接口行为:
    ros2 launch openarm_bringup openarm.bimanual.launch.py \
        arm_type:=v10 use_fake_hardware:=false \
        right_can_interface:=can_slot1_ch1 left_can_interface:=can_slot1_ch0

但完全不走 ROS / ros2_control, 直接用 openarm_can 的 Python 绑定驱动 CAN:

  enable  —— on_activate():  set_callback_mode_all(STATE) → enable_all → recv_all
  zero    —— return_to_zero(): 先读当前位置, 200 步线性插值到零位 (MIT PD 控制)
  disable —— on_deactivate():  连发 3 次 disable_all

CAN-ID / 电机型号 / kp / kd / ZERO_POSITION 全部与 openarm_simple_hardware.hpp 一致
(见 openarm_simple_hardware.hpp 第 83-146 行、return_to_zero 第 305-353 行).
slot2 右臂现场接口 = can_slot2_ch1 (slot1 右臂在 right_arm.py).

用法:
    python3 right_arm_slot2.py home                 # 完整: 使能 → 回零 → 失能 (默认)
    python3 right_arm_slot2.py enable               # 仅使能 (抱住当前位, 不运动)
    python3 right_arm_slot2.py zero                 # 仅回零 (需已使能)
    python3 right_arm_slot2.py disable              # 仅失能
    python3 right_arm_slot2.py setzero              # 标定零位: 把当前位姿写入电机为零点(先手掰到位!)
    python3 right_arm_slot2.py home --no-can        # 跳过 CAN 口拉起(已配好时)
    python3 right_arm_slot2.py home --iface can0    # 指定其它 CAN 口
    python3 right_arm_slot2.py home --no-gripper    # 不带夹爪(只有 7 关节)
    python3 right_arm_slot2.py --help
"""

import sys
import time
import subprocess

from openarm_can import OpenArm, CallbackMode, MotorType, MITParam

# ── 与 openarm_hardware DEFAULT_* 一致 (openarm_simple_hardware.hpp:83-101) ──
ARM_TYPES = [MotorType.DM8009, MotorType.DM8009, MotorType.DM4340,
             MotorType.DM4340, MotorType.DM4310, MotorType.DM4310, MotorType.DM4310]
ARM_SEND_IDS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]
ARM_RECV_IDS = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17]
GRIPPER_TYPE = MotorType.DM4310
GRIPPER_SEND_ID = 0x08
GRIPPER_RECV_ID = 0x18

# ── 与 on_activate / return_to_zero 的增益一致 (openarm_simple_hardware.hpp:104-112) ──
ARM_KP = [70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0]
ARM_KD = [2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5]
ZERO_POSITION = [0.0] * 7                       # 七关节零位全 0 (hpp:138-146)
GRIPPER_KP = 5.0
GRIPPER_KD = 0.1
GRIPPER_JOINT_0_POSITION = 0.044                # 回零时夹爪目标 (hpp:107, return_to_zero 直传)

ARM_DOF = 7
CAN_FD = True

# 现场配置: slot2 右臂 = can_slot2_ch1
DEFAULT_IFACE = "can_slot2_ch1"


def bringup_can(iface):
    """CAN-FD 1M/5M 拉起(CAN 配置不跨重启, 每次都要)."""
    subprocess.run(["sudo", "ip", "link", "set", iface, "down"],
                   stderr=subprocess.DEVNULL)
    r = subprocess.run(["sudo", "ip", "link", "set", iface, "up", "type", "can",
                        "bitrate", "1000000", "dbitrate", "5000000",
                        "fd", "on", "restart-ms", "1"])
    return r.returncode == 0


def make(iface, with_gripper=True):
    """构造 OpenArm 并初始化 7 关节 (可选夹爪), 对应 on_init."""
    oa = OpenArm(iface, CAN_FD)
    oa.init_arm_motors(ARM_TYPES, ARM_SEND_IDS, ARM_RECV_IDS)
    if with_gripper:
        oa.init_gripper_motor(GRIPPER_TYPE, GRIPPER_SEND_ID, GRIPPER_RECV_ID)
    return oa


# ── 阶段 1: 使能 (复刻 on_activate 第 223-236 行, 但去掉 return_to_zero) ──
def enable(oa):
    oa.set_callback_mode_all(CallbackMode.STATE)
    oa.enable_all()
    time.sleep(0.1)
    oa.recv_all()


# ── 阶段 2: 回零 (完整复刻 return_to_zero 第 305-353 行) ──
def return_to_zero(oa, with_gripper=True, steps=200, step_ms=10):
    """读当前位置 → 200 步线性插值到零位 (MIT PD), 与 C++ 逐行对应."""
    arm = oa.get_arm()
    gripper = oa.get_gripper() if with_gripper else None

    # 先刷新并下发一次零位目标, 取得实际起始位置 (return_to_zero:308-328)
    oa.refresh_all()
    arm.mit_control_all([MITParam(ARM_KP[i], ARM_KD[i], 0.0, 0.0, 0.0)
                         for i in range(ARM_DOF)])
    if gripper is not None:
        gripper.mit_control_all(
            [MITParam(GRIPPER_KP, GRIPPER_KD, GRIPPER_JOINT_0_POSITION, 0.0, 0.0)])
    time.sleep(0.001)
    oa.recv_all()

    motors = arm.get_motors()
    start_pos = [0.0] * ARM_DOF
    for i in range(min(ARM_DOF, len(motors))):
        start_pos[i] = motors[i].get_position()
    print(f"  起点 (rad): " + ", ".join(f"{p:+.3f}" for p in start_pos))

    # 200 步线性插值 start_pos → ZERO_POSITION (return_to_zero:333-350)
    for step in range(steps + 1):
        t = step / steps                       # 0.0 → 1.0
        arm.mit_control_all([
            MITParam(ARM_KP[i], ARM_KD[i],
                     start_pos[i] + t * (ZERO_POSITION[i] - start_pos[i]),
                     0.0, 0.0)
            for i in range(ARM_DOF)])
        if gripper is not None:
            gripper.mit_control_all(
                [MITParam(GRIPPER_KP, GRIPPER_KD,
                          GRIPPER_JOINT_0_POSITION, 0.0, 0.0)])
        oa.recv_all()
        time.sleep(step_ms / 1000.0)

    motors = arm.get_motors()
    cur = [motors[i].get_position() for i in range(min(ARM_DOF, len(motors)))]
    print("  到达零位 (rad): " + ", ".join(f"{p:+.3f}" for p in cur))


# ── 阶段 3: 失能 (复刻 on_deactivate 第 238-251 行: 连发 3 次 disable_all) ──
def disable(oa):
    for _ in range(3):
        oa.disable_all()
        time.sleep(0.1)
        oa.recv_all()


# ── 阶段 4: 标定零位 (把当前位姿写入电机为零点, 持久; 不使能, 臀可自由手掰到位) ──
def setzero(oa):
    """set_zero_all: 将各电机当前位置标定为零点 (写入电机, 跨重启持久).

    标定前需先手动把臂摆到想要的零位姿态 (电机失能/自由状态下手掰).
    注意: make() 不使能电机, 因此调用本函数时臂保持自由, 可直接手掰定位.
    """
    oa.set_zero_all()


def run(cmd, iface, with_gripper, do_can, steps, step_ms):
    if do_can:
        print(f"拉起 CAN 口 {iface}...")
        print(f"  {iface}: {'OK' if bringup_can(iface) else '失败'}")

    oa = make(iface, with_gripper)
    try:
        if cmd == "enable":
            enable(oa)
            print(f"  [{iface}] 已使能 (7 关节{'+夹爪' if with_gripper else ''}) — 未发 MIT 控制, 不运动")
        elif cmd == "zero":
            return_to_zero(oa, with_gripper, steps, step_ms)
            print(f"  [{iface}] 回零完成")
        elif cmd == "disable":
            disable(oa)
            print(f"  [{iface}] 已失能")
        elif cmd == "setzero":
            setzero(oa)
            print(f"  [{iface}] 已将当前位姿标定为零位 (7 关节{'+夹爪' if with_gripper else ''}, 持久写入电机)")
        elif cmd == "home":
            print(f"=== home: 使能 → 回零 → 失能 (复刻 on_activate + return_to_zero + on_deactivate) ===")
            enable(oa);            print(f"  [{iface}] 已使能")
            return_to_zero(oa, with_gripper, steps, step_ms)
            disable(oa);           print(f"  [{iface}] 已失能, 右臂回零完成")
    except KeyboardInterrupt:
        print("\n中断, 紧急失能...")
        try:
            disable(oa)
        finally:
            print("已失能。")
        sys.exit(130)


def main():
    do_can = "--no-can" not in sys.argv
    args = [a for a in sys.argv[1:] if a != "--no-can"]

    cmd = "home"
    iface = DEFAULT_IFACE
    with_gripper = True
    steps, step_ms = 200, 10

    i = 0
    pos_args = []
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help", "help"):
            print(__doc__); return
        elif a == "--iface" and i + 1 < len(args):
            iface = args[i + 1]; i += 2
        elif a == "--no-gripper":
            with_gripper = False; i += 1
        elif a == "--steps" and i + 1 < len(args):
            steps = int(args[i + 1]); i += 2
        elif a == "--step-ms" and i + 1 < len(args):
            step_ms = int(args[i + 1]); i += 2
        elif not a.startswith("--") and a in ("home", "enable", "zero", "disable", "setzero"):
            cmd = a; i += 1
        else:
            print(f"未知参数: {a} (用 --help 查看)"); return

    run(cmd, iface, with_gripper, do_can, steps, step_ms)


if __name__ == "__main__":
    main()


"""

cd /ros2_ws
python3 right_arm_slot2.py home              # 使能 → 回零 → 失能  (问题要的三步,默认动作)
python3 right_arm_slot2.py enable            # 仅使能(抱住当前位,不动)
python3 right_arm_slot2.py zero              # 仅回零(需已使能)
python3 right_arm_slot2.py disable           # 仅失能
python3 right_arm_slot2.py home --no-can     # CAN 口已配好时跳过 ip link
python3 right_arm_slot2.py home --iface can0 # 换 CAN 口
python3 right_arm_slot2.py home --no-gripper # 只有 7 关节,无夹爪

"""