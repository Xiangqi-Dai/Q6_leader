#!/usr/bin/env python3
"""
teleop_collect.py — OpenArm 单机双臂主从遥操 + 数据采集 (不依赖 Dora/ROS, 无网络)

拓扑 (全部在同一台机器上, 4 个 CAN 口):
    主动臂 leader  = slot1:  左臂 can_slot1_ch0, 右臂 can_slot1_ch1
    从动臂 follower = slot2:  左臂 can_slot2_ch0, 右臂 can_slot2_ch1

    人手拖动 slot1 主动臂 (零力矩, 自由) → 读其关节角 → slot2 从动臂 MIT PD 跟随 (左→左, 右→右, 1:1).
    无 TCP / 无 SSH / 无第二台机, 全在本地一个进程里完成.

复刻 dora_env/dora-openarm-data-collection 里 dora-openarm-leader/follower 的已验证逻辑:
  · leader:  控制环 ~500Hz 给每个主动臂发零力矩 (DAMIAO 需持续 MIT 帧才保持使能/自由),
             每帧读其 8 关节角作为 follower 的 target.
  · follower: 每侧各自收第一个 target 后, 先读当前位姿, 按 0.05rad/帧 缓动对齐 (避免跳变),
             对齐后用 DEFAULT_KPS/KDS 做 MIT PD 跟随.
  · 录制:    ~170Hz 记 action(leader 关节角) + obs(follower qpos/qvel/qtorque) + 时间戳,
             Ctrl-C 退出时存 npz.

每臂 8 电机 (7 关节 + DM4310 夹爪), send 0x01-0x08, recv 0x11-0x18 (与 motor_config.txt 一致).

用法:
    python3 teleop_collect.py                 # 双臂遥操 + 采集 (默认)
    python3 teleop_collect.py --arms right    # 只右臂 (左→左 或 右→右)
    python3 teleop_collect.py --arms left     # 只左臂
    python3 teleop_collect.py disable         # 紧急/手动失能全部 4 个臂
    python3 teleop_collect.py --no-can        # 跳过 CAN 口拉起 (已配好时)
    python3 teleop_collect.py --out x.npz     # 指定 npz 输出路径
"""

import argparse
import os
import subprocess
import time

import numpy as np
import openarm_can as oa

# ── 电机配置 (每臂 7 关节 + DM4310 夹爪 = 8, 与 motor_config.txt 一致) ──
MOTOR_TYPES = [
    oa.MotorType.DM8009,
    oa.MotorType.DM8009,
    oa.MotorType.DM4340,
    oa.MotorType.DM4340,
    oa.MotorType.DM4310,
    oa.MotorType.DM4310,
    oa.MotorType.DM4310,
    oa.MotorType.DM4310,  # 夹爪
]
SEND_CAN_IDS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
RECV_CAN_IDS = [0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18]
N_MOTORS = len(MOTOR_TYPES)

# follower PD 增益 (与 dora follower DEFAULT_KPS/KDS 一致; 末位=夹爪)
DEFAULT_KPS = np.array([70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0, 10.0], dtype=np.float32)
DEFAULT_KDS = np.array([2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2], dtype=np.float32)

# 零力矩帧 (leader 用): MIT kp=kd=tau=0 -> 电机自由, 人手可拖动
ZERO_MIT = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]

# follower 首帧对齐缓动 (与 dora follower 一致)
ALIGN_STEP = 0.05       # 每帧最大移动量 [rad]
ALIGN_THRESHOLD = 0.1   # 距 target 小于此值即对齐, 切正常跟踪

# 现场拓扑: leader=slot1, follower=slot2 (本机 4 个 CAN 口)
LEADER_CANS = {"left": "can_slot1_ch0", "right": "can_slot1_ch1"}
FOLLOWER_CANS = {"left": "can_slot2_ch0", "right": "can_slot2_ch1"}
SIDES = ("left", "right")


# ════════════════════════════════════════════════════════════════════════════
# CAN / OpenArm
# ════════════════════════════════════════════════════════════════════════════
def bringup_can(iface):
    """CAN-FD 1M/5M 拉起 (CAN 配置不跨重启, 每次都要)."""
    subprocess.run(["sudo", "ip", "link", "set", iface, "down"], stderr=subprocess.DEVNULL)
    r = subprocess.run(
        ["sudo", "ip", "link", "set", iface, "up", "type", "can",
         "bitrate", "1000000", "dbitrate", "5000000", "fd", "on", "restart-ms", "1"]
    )
    return r.returncode == 0


def make_arm(can_interface, label=""):
    """建 OpenArm, init 8 电机, STATE 回调, 使能, 预热; 无反馈则告警."""
    arm = oa.OpenArm(can_interface, enable_fd=True)
    arm.init_arm_motors(MOTOR_TYPES, SEND_CAN_IDS, RECV_CAN_IDS, [oa.ControlMode.MIT] * N_MOTORS)
    arm.set_callback_mode_all(oa.CallbackMode.STATE)
    arm.enable_all()
    for _ in range(30):  # 预热: 连发零力矩帧并 recv, 确保收到全部反馈
        arm.get_arm().mit_control_all(ZERO_MIT)
        arm.recv_all()
        time.sleep(0.005)
    pos = read_positions(arm)
    if float(np.std(pos)) < 1e-6:
        print(f"  [警告] {label}{can_interface}: 8 电机位置无变异 ({pos[0]:+.3f}),"
              f" 可能未上电/未接线 (is_enabled 读数不可信, 以能否拖动/跟踪为准).")
    return arm


def read_positions(arm):
    arm.recv_all()
    return np.array([m.get_position() for m in arm.get_arm().get_motors()], dtype=np.float32)


def track(arm, target):
    """向 target 发一帧 MIT 位置 PD 指令."""
    arm.get_arm().mit_control_all(
        [oa.MITParam(kp=float(DEFAULT_KPS[i]), kd=float(DEFAULT_KDS[i]),
                     q=float(target[i]), dq=0.0, tau=0.0) for i in range(N_MOTORS)]
    )


def disable_arm(arm):
    for _ in range(3):
        try:
            arm.disable_all()
        except Exception:
            pass
        time.sleep(0.05)


# ════════════════════════════════════════════════════════════════════════════
# 遥操主循环
# ════════════════════════════════════════════════════════════════════════════
def run_teleop(args):
    active = list(SIDES) if args.arms == "both" else [args.arms]
    print(f"=== 单机双臂主从遥操: leader=slot1 {active}  →  follower=slot2 {active} ===")
    if args.bringup:
        cans = []
        for s in active:
            cans.append(LEADER_CANS[s])
            cans.append(FOLLOWER_CANS[s])
        for c in dict.fromkeys(cans):  # 去重保序
            print(f"  拉起 CAN {c}: {'OK' if bringup_can(c) else '失败'}")

    leader = {s: make_arm(LEADER_CANS[s], f"[leader {s}] ") for s in active}
    follower = {s: make_arm(FOLLOWER_CANS[s], f"[follower {s}] ") for s in active}
    align = {s: {"aligned": False, "base": None} for s in active}

    rec = {s: {"action": [], "qpos": [], "qvel": [], "qtor": []} for s in active}
    rec_ts = []
    last_sample = 0.0

    print(f"开始遥操: 拖动 slot1 主动臂({active}), slot2 从动臂跟随. Ctrl-C 结束并保存.")
    try:
        while True:
            lpos = {}
            for s in active:
                # 主动臂: 零力矩(自由可拖) + 读关节角
                leader[s].get_arm().mit_control_all(ZERO_MIT)
                leader[s].recv_all()
                lpos[s] = np.array(
                    [m.get_position() for m in leader[s].get_arm().get_motors()], dtype=np.float32)

                # 从动臂: 对齐缓动 / PD 跟随
                st = align[s]
                if not st["aligned"]:
                    if st["base"] is None:
                        st["base"] = np.array(
                            [m.get_position() for m in follower[s].get_arm().get_motors()],
                            dtype=np.float32)
                    diff = lpos[s] - st["base"]
                    if np.all(np.abs(diff) < ALIGN_THRESHOLD):
                        track(follower[s], lpos[s])
                        st["aligned"] = True
                        print(f"  [{s}] 从动臂对齐完成, 进入 PD 跟随")
                    else:
                        st["base"] = st["base"] + np.clip(diff, -ALIGN_STEP, ALIGN_STEP)
                        track(follower[s], st["base"])
                else:
                    track(follower[s], lpos[s])
                follower[s].recv_all()

            # 录制 ~170Hz
            now = time.time()
            if now - last_sample >= 0.006:
                for s in active:
                    rec[s]["action"].append(lpos[s])
                    ms = follower[s].get_arm().get_motors()
                    rec[s]["qpos"].append(np.array([m.get_position() for m in ms], dtype=np.float32))
                    rec[s]["qvel"].append(np.array([m.get_velocity() for m in ms], dtype=np.float32))
                    rec[s]["qtor"].append(np.array([m.get_torque() for m in ms], dtype=np.float32))
                rec_ts.append(now)
                last_sample = now
            time.sleep(0.002)  # ~500Hz 控制环
    except KeyboardInterrupt:
        pass
    finally:
        print("\n失能全部 4 个臂...")
        for s in active:
            disable_arm(leader[s])
            disable_arm(follower[s])
        _save_dataset(args, active, rec, rec_ts)


def _save_dataset(args, active, rec, rec_ts):
    if not rec_ts or not any(rec[s]["action"] for s in active):
        print("无有效数据可保存"); return
    n = min(len(rec[s]["action"]) for s in active) if len(active) > 1 else len(rec[active[0]]["action"])
    out = args.out or "/ros2_ws/datasets/teleop_%s.npz" % time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    save = {"timestamp": np.asarray(rec_ts[:n], dtype=np.float64)}
    for s in active:
        save[f"action_{s}"] = np.asarray(rec[s]["action"][:n], dtype=np.float32)
        save[f"obs_qpos_{s}"] = np.asarray(rec[s]["qpos"][:n], dtype=np.float32)
        save[f"obs_qvel_{s}"] = np.asarray(rec[s]["qvel"][:n], dtype=np.float32)
        save[f"obs_qtorque_{s}"] = np.asarray(rec[s]["qtor"][:n], dtype=np.float32)
    duration = rec_ts[n - 1] - rec_ts[0] if n > 1 else 0.0
    save["fps"] = np.float32(n / duration if duration > 0 else 0.0)
    save["motor_types"] = np.array([m.name for m in MOTOR_TYPES])
    save["arms"] = np.array(active)
    np.savez(out, **save)
    print(f"已保存 {n} 帧 -> {out}  ({duration:.1f}s, arms={active})")


# ════════════════════════════════════════════════════════════════════════════
# 紧急/手动失能全部 4 臂
# ════════════════════════════════════════════════════════════════════════════
def run_disable(args):
    active = list(SIDES)
    print(f"=== 失能全部 4 臂: slot1/slot2 各左右 ===")
    if args.bringup:
        for c in [LEADER_CANS[s] for s in active] + [FOLLOWER_CANS[s] for s in active]:
            bringup_can(c)
    arms = {}
    for s in active:
        arms[("leader", s)] = make_arm(LEADER_CANS[s], f"[leader {s}] ")
        arms[("follower", s)] = make_arm(FOLLOWER_CANS[s], f"[follower {s}] ")
    for (role, s), a in arms.items():
        print(f"  失能 {role} {s}")
        disable_arm(a)
    print("完成.")


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(
        description="OpenArm 单机双臂(slot1→slot2)主从遥操 + 数据采集",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    p.add_argument("cmd", nargs="?", default="teleop", choices=["teleop", "disable"],
                   help="teleop=遥操采集(默认); disable=失能全部 4 臂")
    p.add_argument("--arms", choices=["both", "left", "right"], default="both", help="激活哪侧(默认 both)")
    p.add_argument("--no-can", action="store_true", help="跳过 CAN 口拉起 (已配好时)")
    p.add_argument("--out", default="", help="npz 输出路径 (默认带时间戳)")
    args = p.parse_args()
    args.bringup = not args.no_can
    if args.cmd == "disable":
        run_disable(args)
    else:
        run_teleop(args)


if __name__ == "__main__":
    main()
