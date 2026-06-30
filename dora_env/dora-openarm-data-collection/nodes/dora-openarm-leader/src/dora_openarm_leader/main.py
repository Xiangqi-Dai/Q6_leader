# Copyright 2026 Enactic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""dora-rs node for the OpenArm leader arm.

The leader runs in zero-torque mode so a human can freely drag the arm. On every
tick it keeps both arms at zero torque, reads back the current joint positions
and publishes them as ``position_left`` / ``position_right`` so a remote follower
can track them.
"""

import argparse
import os

import dora
import numpy as np
import openarm_can as oa
import pyarrow as pa
import time

# 7-DoF arm + gripper (DM3507). Mirrors openarm_driver/config.yaml.
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

# Zero-torque command: MIT mode with all gains and feed-forward torque at zero.
ZERO_MIT = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]


def make_arm(can_interface):
    """Create, configure and enable an OpenArm on the given CAN interface."""
    arm = oa.OpenArm(can_interface, enable_fd=True)
    arm.init_arm_motors(
        MOTOR_TYPES,
        SEND_CAN_IDS,
        RECV_CAN_IDS,
        [oa.ControlMode.MIT] * N_MOTORS,
    )
    # STATE callback lets recv_all() automatically populate motor state fields.
    arm.set_callback_mode_all(oa.CallbackMode.STATE)
    arm.enable_all()
    # 预热:发若干零力矩帧并 recv,确保收到全部电机的反馈帧。
    # 单次 recv_all 超时短,会漏掉后到的电机,使位置读到默认 -PMAX(=-12.5)。
    _warmup = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]
    for _ in range(30):
        arm.get_arm().mit_control_all(_warmup)
        arm.recv_all()
        time.sleep(0.005)  # 给电机反馈帧到达总线的时间
    return arm


def read_positions(arm):
    """Read the latest joint positions (rad) of an arm into a float32 array."""
    arm.recv_all()
    return np.array(
        [m.get_position() for m in arm.get_arm().get_motors()],
        dtype=np.float32,
    )


def main():
    """Run the leader node: hold zero torque (500 Hz) and stream positions (200 Hz).

    Control and sampling are decoupled: ``control_tick`` (high rate) keeps both
    arms in zero-torque mode — DAMIAO needs continuous MIT frames to hold the
    enabled behaviour — while ``sample_tick`` (lower rate) reads back joint
    positions and streams them to the follower, keeping the cross-machine load
    low.
    """
    parser = argparse.ArgumentParser(description="OpenArm leader arm node")
    parser.add_argument(
        "--left-can-interface",
        default=os.getenv("CAN_LEFT", "can_slot1_ch0"),
        help="CAN interface for the left arm (env: CAN_LEFT)",
    )
    parser.add_argument(
        "--right-can-interface",
        default=os.getenv("CAN_RIGHT", "can_slot1_ch1"),
        help="CAN interface for the right arm (env: CAN_RIGHT)",
    )
    parser.add_argument(
        "--only",
        choices=["left", "right", "both"],
        default=os.getenv("ONLY", "both"),
        help="Which arms to enable (left arm not powered -> use 'right') (env: ONLY)",
    )
    args = parser.parse_args()

    # Only open the requested arm(s); the un-powered arm's CAN bus is left alone.
    arms = {}
    if args.only in ("left", "both"):
        arms["left"] = make_arm(args.left_can_interface)
    if args.only in ("right", "both"):
        arms["right"] = make_arm(args.right_can_interface)

    node = dora.Node()
    try:
        for event in node:
            if event["type"] != "INPUT":
                continue

            event_id = event["id"]
            if event_id == "control_tick":
                # High rate (500 Hz): hold enabled arms in zero-torque mode.
                for arm in arms.values():
                    arm.get_arm().mit_control_all(ZERO_MIT)
            elif event_id == "sample_tick":
                # Lower rate (200 Hz): stream joint positions of enabled arms.
                for side, arm in arms.items():
                    node.send_output(
                        f"position_{side}",
                        pa.array(read_positions(arm), type=pa.float32()),
                    )
    finally:
        # Safely disable enabled arms on exit (Ctrl-C, quitter stop, ...).
        for arm in arms.values():
            try:
                arm.disable_all()
            except Exception:
                pass


if __name__ == "__main__":
    main()
