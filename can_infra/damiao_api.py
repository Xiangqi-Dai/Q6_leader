#!/usr/bin/env python3
"""
damiao_api.py - Damiao电机 CAN通信 Python API

将 design.md 中定义的每个API封装为Python函数。
Python类负责：通过API传参生成配置文件，调用编译后的C++二进制文件执行CAN通信。

使用方式:
    api = DamiaoAPI()
    api.init_can("can_slot1_ch0", is_fd=True, bitrate=1000000, data_bitrate=5000000)
    motor = api.add_motor("can_slot1_ch0", can_id=0x001, master_id=0x11, motor_type="DM8009")
    api.enable(motor)
    api.control_mit(motor, kp=20, kd=1, q=1.0, dq=0, tau=0)
    api.disable(motor)
"""

import subprocess
import os
import sys
import tempfile
import struct


# ─── 电机型号限位参数 [PMAX, VMAX, TMAX] ────────────────────────────
MOTOR_LIMITS = {
    "DM4310":      (12.5,  30.0,  10.0),
    "DM4310_48V":  (12.5,  50.0,  10.0),
    "DM4340":      (12.5,   8.0,  28.0),
    "DM4340_48V":  (12.5,  10.0,  28.0),
    "DM4340P_48V": (12.5,   8.0,  28.0),
    "DM6006":      (12.5,  45.0,  20.0),
    "DM8006":      (12.5,  45.0,  40.0),
    "DM8009":      (12.5,  45.0,  54.0),
    "DM10010L":    (12.5,  25.0, 200.0),
    "DM10010":     (12.5,  20.0, 200.0),
    "DMH3510":     (12.5, 280.0,   1.0),
    "DMG62150":    (12.5,  45.0,  10.0),
    "DMH6220":     (12.5,  45.0,  10.0),
}


def _float_to_uint(x, x_min, x_max, bits):
    """Float → uint 编码（Damiao协议）"""
    x = max(x_min, min(x, x_max))
    span = x_max - x_min
    data_norm = (x - x_min) / span
    return int(data_norm * ((1 << bits) - 1)) & 0xFFFF


class MotorState:
    """电机反馈状态"""
    __slots__ = ("q", "dq", "tau", "tmos", "trotor")

    def __init__(self):
        self.q = 0.0       # position (rad)
        self.dq = 0.0      # velocity (rad/s)
        self.tau = 0.0      # torque (Nm)
        self.tmos = 0       # MOS temperature
        self.trotor = 0     # rotor temperature

    def __repr__(self):
        return (f"MotorState(q={self.q:.4f}, dq={self.dq:.4f}, "
                f"tau={self.tau:.4f}, tmos={self.tmos}, trotor={self.trotor})")


class Motor:
    """电机引用对象，由 DamiaoAPI.add_motor() 创建"""
    __slots__ = ("interface", "can_id", "master_id", "motor_type", "limits", "state")

    def __init__(self, interface, can_id, master_id, motor_type, limits):
        self.interface = interface
        self.can_id = can_id
        self.master_id = master_id
        self.motor_type = motor_type
        self.limits = limits  # (PMAX, VMAX, TMAX)
        self.state = MotorState()

    def __repr__(self):
        return (f"Motor(iface={self.interface}, id=0x{self.can_id:X}, "
                f"master=0x{self.master_id:X}, type={self.motor_type})")


class DamiaoAPI:
    """
    Damiao电机 CAN通信 API

    封装 design.md 中定义的所有接口:
      - Part1: CAN口初始化
      - Part2: 接口1~4 + 接口5(持续控制, 通过接口1~4组合实现)
    """

    def __init__(self, binary_path=None):
        if binary_path is None:
            binary_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "main")
        self._binary = binary_path
        self._interfaces = {}   # name -> {type, bitrate, data_bitrate}
        self._motors = []       # [Motor, ...]

    # ─── Part1: CAN口通信 ───────────────────────────────────────────

    def init_can(self, name, is_fd=True, bitrate=1000000, data_bitrate=5000000):
        """
        Part1: CAN口初始化

        input: CAN口名称, 是否CAN-FD, 仲裁波特率, 数据波特率
        output: 根据input对指定CAN口进行初始化，并反馈初始化结果

        Returns:
            bool: 初始化是否成功
        """
        self._interfaces[name] = {
            "type": "can-fd" if is_fd else "can",
            "bitrate": bitrate,
            "data_bitrate": data_bitrate,
        }
        subprocess.run(
            ["sudo", "ip", "link", "set", name, "down"],
            stderr=subprocess.DEVNULL)
        if is_fd:
            r = subprocess.run([
                "sudo", "ip", "link", "set", name, "up",
                "type", "can", "bitrate", str(bitrate),
                "dbitrate", str(data_bitrate), "fd", "on", "restart-ms", "1",
            ])
        else:
            r = subprocess.run([
                "sudo", "ip", "link", "set", name, "up",
                "type", "can", "bitrate", str(bitrate),
            ])
        return r.returncode == 0

    # ─── 配置 ──────────────────────────────────────────────────────

    def add_motor(self, interface, can_id, master_id=None, motor_type="DM4310"):
        """
        添加电机到指定CAN口

        Args:
            interface:  CAN口名称
            can_id:     电机 CAN-ID (slave_id)
            master_id:  电机 Master-ID (default: can_id + 0x10)
            motor_type: 电机型号字符串

        Returns:
            Motor: 电机引用对象
        """
        if interface not in self._interfaces:
            raise ValueError(f"CAN interface '{interface}' not initialized. "
                             f"Call init_can() first.")
        if master_id is None:
            master_id = can_id + 0x10
        limits = MOTOR_LIMITS.get(motor_type, (12.5, 30.0, 10.0))
        motor = Motor(interface, can_id, master_id, motor_type, limits)
        self._motors.append(motor)
        return motor

    # ─── Part2: 接口1~4 ───────────────────────────────────────────

    def control_motor(self, motor, can_data):
        """
        CAN信号控制电机: 发送CAN-data，接收Master-ID反馈
        """
        data = list(can_data)
        config = self._build_config([motor], {"send_data": data})
        stdout, rc = self._run_binary("send_recv", config)
        if rc == 0:
            self._parse_and_update(stdout, [motor])
        return motor.state

    def enable(self, motor):
        """接口1: 电机使能 (CAN-data=使能帧0xFC)"""
        config = self._build_config([motor])
        stdout, rc = self._run_binary("enable", config)
        if rc == 0:
            self._parse_and_update(stdout, [motor])
        return motor.state

    def disable(self, motor):
        """接口2: 电机失能 (CAN-data=失能帧0xFD)"""
        config = self._build_config([motor])
        self._run_binary("disable", config)

    def set_zero(self, motor):
        """接口3: 电机标零 (CAN-data=标零帧0xFE)"""
        config = self._build_config([motor])
        stdout, rc = self._run_binary("set_zero", config)
        if rc == 0:
            self._parse_and_update(stdout, [motor])
        return motor.state

    def motor_action(self, motor):
        """接口4: 电机动作（状态读取/刷新）"""
        refresh_data = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        return self.control_motor(motor, refresh_data)

    def control_mit(self, motor, kp, kd, q, dq, tau):
        """MIT模式控制（单次，通过control_motor实现）"""
        can_data = self.pack_mit_data(motor, kp, kd, q, dq, tau)
        return self.control_motor(motor, can_data)

    # ─── Part2: 接口5 持续控制（通过接口1~4组合实现） ──────────────

    def continuous_control(self, motors=None, kp=20.0, kd=1.0, tau=0.0, q=0.0, dq=0.0,
                           control_frequency=500, print_frequency=5,
                           duration=60.0, set_zero_first=False,
                           commands=None):
        """
        接口5: 持续控制 — 通过接口1~4组合实现

        控制序列包含: enable → [set_zero] → control循环 → disable

        input:
            motors:             电机列表 (None=全部已注册电机)
            kp, kd, q, dq, tau: MIT控制参数 (用于自动生成CONTROL命令)
            control_frequency:  控制频率 Hz
            print_frequency:    日志反馈频率 Hz
            duration:           持续时间 (秒)
            set_zero_first:     是否在使能后先标零
            commands:           自定义命令序列 dict (覆盖自动生成):
                {
                    "CAN口1": [
                        {"type": "enable",   "can_id": 0x001, "master_id": 0x11},
                        {"type": "control",  "can_id": 0x001, "can_data": [...], "master_id": 0x11},
                        {"type": "disable",  "can_id": 0x001, "master_id": 0x11},
                    ],
                    "CAN口2": [...]
                }

        output: 调用接口1~4完成控制序列
        """
        if motors is None:
            motors = self._motors

        if commands is None:
            commands = self._build_full_sequence(
                motors, kp, kd, q, dq, tau, set_zero_first)

        config = self._build_config(
            motors,
            {
                "seq_control_freq": control_frequency,
                "seq_print_freq": print_frequency,
                "seq_duration": duration,
                "_commands": commands,
            }
        )
        try:
            subprocess.run(
                [self._binary, "continuous", config],
                cwd=os.path.dirname(self._binary) or ".")
        except KeyboardInterrupt:
            print("\n[API] Continuous control interrupted")
        finally:
            if os.path.exists(config):
                os.unlink(config)

    # ─── MIT正弦控制 ───────────────────────────────────────────────

    def run_mit_sine(self, motors=None, kp=20.0, kd=1.0, tau_ff=0.1,
                     amplitude=1.0, sine_freq=0.1, duration=60.0,
                     control_freq=500, print_freq=5):
        """MIT正弦波控制循环"""
        if motors is None:
            motors = self._motors
        config = self._build_config(motors, {
            "kp": kp, "kd": kd, "tau_ff": tau_ff,
            "amplitude": amplitude, "sine_freq": sine_freq,
            "duration": duration,
            "control_freq": control_freq, "print_freq": print_freq,
        })
        try:
            subprocess.run(
                [self._binary, "mit_sine", config],
                cwd=os.path.dirname(self._binary) or ".")
        except KeyboardInterrupt:
            print("\n[API] MIT sine control interrupted")
        finally:
            if os.path.exists(config):
                os.unlink(config)

    # ─── 工具函数 ──────────────────────────────────────────────────

    @staticmethod
    def pack_mit_data(motor, kp, kd, q, dq, tau):
        """将MIT控制参数编码为8字节CAN数据"""
        PMAX, VMAX, TMAX = motor.limits
        q_uint = _float_to_uint(q, -PMAX, PMAX, 16)
        dq_uint = _float_to_uint(dq, -VMAX, VMAX, 12)
        kp_uint = _float_to_uint(kp, 0, 500, 12)
        kd_uint = _float_to_uint(kd, 0, 5, 12)
        tau_uint = _float_to_uint(tau, -TMAX, TMAX, 12)

        data = [0] * 8
        data[0] = (q_uint >> 8) & 0xFF
        data[1] = q_uint & 0xFF
        data[2] = dq_uint >> 4
        data[3] = ((dq_uint & 0xF) << 4) | ((kp_uint >> 8) & 0xF)
        data[4] = kp_uint & 0xFF
        data[5] = kd_uint >> 4
        data[6] = ((kd_uint & 0xF) << 4) | ((tau_uint >> 8) & 0xF)
        data[7] = tau_uint & 0xFF
        return data

    # ─── 内部方法 ──────────────────────────────────────────────────

    def _build_full_sequence(self, motors, kp, kd, q, dq, tau, set_zero_first):
        """
        为所有电机生成完整控制序列:
        enable → [set_zero] → control(MIT) → disable
        """
        commands = {}
        for m in motors:
            iface = m.interface
            entries = commands.setdefault(iface, [])

            # 接口1: 使能
            entries.append({
                "type": "enable",
                "can_id": m.can_id,
                "master_id": m.master_id,
            })

            # 接口3: 标零 (可选)
            if set_zero_first:
                entries.append({
                    "type": "set_zero",
                    "can_id": m.can_id,
                    "master_id": m.master_id,
                })

            # 接口4: MIT控制
            can_data = self.pack_mit_data(m, kp, kd, q, dq, tau)
            entries.append({
                "type": "control",
                "can_id": m.can_id,
                "can_data": can_data,
                "master_id": m.master_id,
            })

            # 接口2: 失能
            entries.append({
                "type": "disable",
                "can_id": m.can_id,
                "master_id": m.master_id,
            })

        return commands

    def _build_config(self, motors, params=None):
        """生成临时配置文件，返回文件路径"""
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="damiao_")
        with os.fdopen(fd, 'w') as f:
            # interfaces
            written = set()
            for m in motors:
                if m.interface not in written:
                    cfg = self._interfaces[m.interface]
                    f.write(f"interface {m.interface} {cfg['type']}\n")
                    written.add(m.interface)
            # motors
            for m in motors:
                f.write(f"motor {m.can_id} {m.motor_type} {m.master_id}\n")
            # params
            if params:
                for k, v in params.items():
                    if k.startswith("_"):
                        continue
                    if k == "send_data":
                        f.write("send_data " + " ".join(f"{b:02X}" for b in v) + "\n")
                    else:
                        f.write(f"{k} {v}\n")
                # command sequence
                cmds = params.get("_commands")
                if cmds:
                    for iface, cmd_list in cmds.items():
                        for entry in cmd_list:
                            t = entry["type"]
                            if t == "control":
                                hex_data = " ".join(f"{b:02X}" for b in entry["can_data"])
                                f.write(f"cmd {iface} control {entry['can_id']:X} "
                                        f"{hex_data} {entry['master_id']:X}\n")
                            else:
                                f.write(f"cmd {iface} {t} {entry['can_id']:X} "
                                        f"{entry['master_id']:X}\n")
        return path

    def _run_binary(self, mode, config_path):
        """执行C++二进制文件，返回 (stdout, returncode)"""
        try:
            result = subprocess.run(
                [self._binary, mode, config_path],
                capture_output=True, text=True, timeout=30,
                cwd=os.path.dirname(self._binary) or ".")
            return result.stdout, result.returncode
        except subprocess.TimeoutExpired:
            return "", 1
        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)

    @staticmethod
    def _parse_and_update(stdout, motors):
        """解析C++二进制输出的电机状态，更新Motor对象"""
        for line in stdout.strip().split('\n'):
            if line.strip() in ("OK", "ERR") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 6:
                can_id = int(parts[0])
                for m in motors:
                    if m.can_id == can_id or m.master_id == can_id:
                        m.state.q = float(parts[1])
                        m.state.dq = float(parts[2])
                        m.state.tau = float(parts[3])
                        m.state.tmos = int(parts[4])
                        m.state.trotor = int(parts[5])
                        break
