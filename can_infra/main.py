#!/usr/bin/env python3
"""
main.py - Damiao电机 CAN通信 命令行测试工具

通过命令行参数快速测试 CAN 通信连接，无需修改代码。支持四种模式：
  enable    接口1: 电机使能
  disable   接口2: 电机失能
  set_zero  接口3: 电机标零
  action    接口4: 电机动作 (MIT 控制 / 状态读取)

用法示例:
  python3 main.py enable                       # 使能 (默认CAN口+默认电机)
  python3 main.py disable --motors 0x001       # 失能指定电机
  python3 main.py set_zero -y                  # 标零 (跳过确认)
  python3 main.py action --refresh             # 仅读取状态 (安全连通性测试)
  python3 main.py action --q 0.5 --kp 20       # MIT 控制 (自动使能→控制→失能)

更多示例见 README.md「命令行快速测试」一节。
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damiao_api import DamiaoAPI

# ─── 默认配置 (按实际硬件修改) ───────────────────────────────────────

CAN_IFACE = "can_slot1_ch1"     # 默认 CAN 口
CAN_BITRATE = 1000000           # 仲裁波特率
CAN_DBITRATE = 5000000          # 数据波特率

# 默认电机列表 (格式: can_id:master_id:type)
DEFAULT_MOTORS = [
    "0x001:0x11:DM8009",
    "0x002:0x12:DM8009",
    "0x003:0x13:DM4340P_48V",
]


# ─── 参数解析 ───────────────────────────────────────────────────────

def parse_motor_spec(spec):
    """
    解析电机描述字符串 → (can_id, master_id, motor_type)

    支持格式:
        "0x001:0x11:DM8009"   完整: can_id:master_id:type
        "0x001:0x11"          省略类型 (默认 DM8009)
        "0x001"               省略 master_id 与类型 (master_id = can_id + 0x10)

    can_id / master_id 可为十进制或 0x 十六进制。
    """
    parts = spec.split(":")
    if len(parts) == 3:
        can_id, master_id, mtype = parts
    elif len(parts) == 2:
        can_id, master_id = parts
        mtype = "DM8009"
    elif len(parts) == 1:
        can_id = parts[0]
        master_id = str(int(can_id, 0) + 0x10)
        mtype = "DM8009"
    else:
        raise argparse.ArgumentTypeError(
            f"电机格式错误: '{spec}'，应为 can_id:master_id:type")
    return int(can_id, 0), int(master_id, 0), mtype


def build_parser():
    # 公共参数 (父解析器)，各子命令共享
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--iface", default=CAN_IFACE,
                        help=f"CAN口名称 (默认: {CAN_IFACE})")
    common.add_argument("--motors", nargs="+", type=parse_motor_spec,
                        metavar="CAN_ID:MASTER_ID:TYPE",
                        help="电机列表，格式 can_id:master_id:type "
                             "(可省略 type / master_id)，可指定多个；"
                             f"默认: {' '.join(DEFAULT_MOTORS)}")
    common.add_argument("--bitrate", type=int, default=CAN_BITRATE,
                        help=f"仲裁波特率 (默认: {CAN_BITRATE})")
    common.add_argument("--dbitrate", type=int, default=CAN_DBITRATE,
                        help=f"数据波特率 (默认: {CAN_DBITRATE})")
    common.add_argument("--classic-can", action="store_true",
                        help="使用经典 CAN (默认 CAN-FD)")
    common.add_argument("--skip-init", action="store_true",
                        help="跳过 CAN 口 ip link 初始化 (CAN 口已配置好时使用)")

    parser = argparse.ArgumentParser(
        description="Damiao电机 CAN通信 命令行测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python3 main.py enable\n"
               "  python3 main.py action --q 0.5 --kp 20 --kd 1\n"
               "  python3 main.py action --refresh\n"
               "更多示例见 README.md")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{enable,disable,set_zero,action}")

    # enable
    sub.add_parser("enable", parents=[common],
                   help="接口1: 电机使能")

    # disable
    sub.add_parser("disable", parents=[common],
                   help="接口2: 电机失能")

    # set_zero
    p_zero = sub.add_parser("set_zero", parents=[common],
                            help="接口3: 电机标零 (将当前位置设为零位)")
    p_zero.add_argument("-y", "--yes", action="store_true",
                        help="跳过交互确认，直接标零")

    # action
    p_act = sub.add_parser("action", parents=[common],
                           help="接口4: 电机动作 (MIT 控制 / 状态读取)")
    p_act.add_argument("--kp", type=float, default=20.0,
                       help="位置刚度 (默认 20)")
    p_act.add_argument("--kd", type=float, default=1.0,
                       help="阻尼 (默认 1)")
    p_act.add_argument("--q", type=float, default=0.0,
                       help="目标位置 rad，绝对值 (默认 0)")
    p_act.add_argument("--dq", type=float, default=0.0,
                       help="目标速度 rad/s (默认 0)")
    p_act.add_argument("--tau", type=float, default=0.0,
                       help="前馈力矩 Nm (默认 0)")
    p_act.add_argument("--count", type=int, default=1,
                       help="连续发送 MIT 控制次数 (默认 1)")
    p_act.add_argument("--interval", type=float, default=0.5,
                       help="每次发送间隔秒 (默认 0.5)")
    p_act.add_argument("--refresh", action="store_true",
                       help="仅读取状态，不下发 MIT 控制")
    p_act.add_argument("--no-enable", action="store_true",
                       help="跳过自动使能 (电机已使能时使用)")
    p_act.add_argument("--no-disable", action="store_true",
                       help="结束后保持使能，不自动失能")

    return parser


# ─── CAN / 电机准备 ────────────────────────────────────────────────

def setup(args):
    """根据参数初始化 CAN 口并注册电机，返回 (api, motors)"""
    api = DamiaoAPI()

    if not args.skip_init:
        print(f"初始化CAN口: {args.iface} "
              f"({'CAN' if args.classic_can else 'CAN-FD'}, "
              f"{args.bitrate}/{args.dbitrate})")
        ok = api.init_can(args.iface, is_fd=not args.classic_can,
                          bitrate=args.bitrate, data_bitrate=args.dbitrate)
        if not ok:
            print(f"CAN口初始化失败: {args.iface}")
            sys.exit(1)
        print(f"  {args.iface}: OK")
    else:
        # 跳过 ip link (CAN 口已在外部配置好)，但仍需在 API 内登记接口元数据
        api._interfaces[args.iface] = {
            "type": "can" if args.classic_can else "can-fd",
            "bitrate": args.bitrate,
            "data_bitrate": args.dbitrate,
        }
        print(f"跳过CAN口初始化: {args.iface}")

    specs = args.motors if args.motors else [parse_motor_spec(s) for s in DEFAULT_MOTORS]
    motors = []
    for can_id, master_id, mtype in specs:
        m = api.add_motor(args.iface, can_id=can_id,
                          master_id=master_id, motor_type=mtype)
        motors.append(m)
        print(f"  注册电机: ID=0x{can_id:02X} master=0x{master_id:02X} {mtype}")
    print()
    return api, motors


# ─── 各模式实现 ────────────────────────────────────────────────────

def cmd_enable(api, motors, args):
    """接口1: 电机使能"""
    print("=== 接口1: 电机使能 ===")
    for m in motors:
        state = api.enable(m)
        print(f"  enable(ID=0x{m.can_id:02X}) → {state}")


def cmd_disable(api, motors, args):
    """接口2: 电机失能"""
    print("=== 接口2: 电机失能 ===")
    for m in motors:
        api.disable(m)
        print(f"  disable(ID=0x{m.can_id:02X}) OK")


def cmd_set_zero(api, motors, args):
    """接口3: 电机标零"""
    print("=== 接口3: 电机标零 ===")
    print("警告：将当前位置设为零位！")
    if not args.yes:
        ans = input("确认标零？[y/N]: ").strip().lower()
        if ans != "y":
            print("跳过。")
            return
    for m in motors:
        state = api.set_zero(m)
        print(f"  set_zero(ID=0x{m.can_id:02X}) → q={state.q:.4f}")


def cmd_action(api, motors, args):
    """接口4: 电机动作 (MIT 控制 / 状态读取)"""
    print("=== 接口4: 电机动作 ===")

    if args.refresh:
        # 仅状态读取：发送刷新帧并读取反馈，最安全的连通性测试
        for m in motors:
            state = api.motor_action(m)
            print(f"  read(ID=0x{m.can_id:02X}) → "
                  f"q={state.q:+.4f} dq={state.dq:+.4f} tau={state.tau:+.4f} "
                  f"tmos={state.tmos}°C")
        return

    # MIT 控制：默认 enable → control(×count) → disable
    if not args.no_enable:
        for m in motors:
            api.enable(m)
        time.sleep(0.3)
        print("  已使能。")

    print(f"  MIT控制: kp={args.kp} kd={args.kd} q={args.q} "
          f"dq={args.dq} tau={args.tau} (×{args.count})")
    for step in range(args.count):
        if args.count > 1:
            print(f"  --- 第{step + 1}次 ---")
        for m in motors:
            state = api.control_mit(m, kp=args.kp, kd=args.kd,
                                    q=args.q, dq=args.dq, tau=args.tau)
            print(f"    ID=0x{m.can_id:02X} → q={state.q:+.4f} "
                  f"dq={state.dq:+.4f} tau={state.tau:+.4f} "
                  f"tmos={state.tmos}°C")
        if step < args.count - 1:
            time.sleep(args.interval)

    if not args.no_disable:
        for m in motors:
            api.disable(m)
        print("  已失能。")


COMMANDS = {
    "enable": cmd_enable,
    "disable": cmd_disable,
    "set_zero": cmd_set_zero,
    "action": cmd_action,
}


# ─── main ──────────────────────────────────────────────────────────

def main():
    args = build_parser().parse_args()
    api, motors = setup(args)

    try:
        COMMANDS[args.command](api, motors, args)
    except KeyboardInterrupt:
        print("\n中断，紧急失能...")
        for m in motors:
            api.disable(m)
        print("已失能。")
        sys.exit(130)

    print("\n完成。")


if __name__ == "__main__":
    main()
