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

"""dora-rs node for the OpenArm follower arm.

Receives target joint positions (``target_left`` / ``target_right``) from the
leader node and tracks them with MIT-mode position PD control. Because the
devices are identical, the raw joint angles are copied 1:1 — no coordinate
mapping. On the first frame, each arm ramps from its current pose to the target
to avoid a sudden jump (alignment), then follows normally.

Control and target updates are decoupled: ``target_*`` events (slower, ~200 Hz
over the cross-machine link) only refresh a cached target, while ``control_tick``
(high rate, 500 Hz) runs the local PD loop on the latest cached target. This
keeps tracking smooth even if a network frame is delayed or dropped.

On ``sample_tick`` it also outputs each arm's full joint state
(qpos/qvel/qtorque) as ``state_left`` / ``state_right`` for recording.
"""

import argparse
import dataclasses
import os
import time

import dora
import numpy as np
import openarm_can as oa
import pyarrow as pa

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

# Default PD gains (per joint). From openarm_driver/config.yaml control_gains.
DEFAULT_KPS = np.array([70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0, 10.0], dtype=np.float32)
DEFAULT_KDS = np.array([2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2], dtype=np.float32)

# Maximum step (rad) taken per frame while aligning to the first target, and the
# threshold below which an arm is considered aligned and starts normal tracking.
ALIGN_STEP = 0.05
ALIGN_THRESHOLD = 0.1


@dataclasses.dataclass
class AlignState:
    """Per-arm alignment state: ramps from the initial pose to the target."""

    aligned: bool = False
    base: np.ndarray = None  # pose captured at the first received target


def make_arm(can_interface):
    """Create, configure and enable an OpenArm on the given CAN interface."""
    arm = oa.OpenArm(can_interface, enable_fd=True)
    arm.init_arm_motors(
        MOTOR_TYPES,
        SEND_CAN_IDS,
        RECV_CAN_IDS,
        [oa.ControlMode.MIT] * N_MOTORS,
    )
    arm.set_callback_mode_all(oa.CallbackMode.STATE)
    arm.enable_all()
    # 预热:发若干零力矩帧并 recv,确保收到全部电机的反馈帧。
    # 单次 recv_all 超时短,会漏掉后到的电机,使位置读到默认 -PMAX(=-12.5),
    # 导致 align 基准错乱、电机冲向极限。
    _warmup = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]
    for _ in range(30):
        arm.get_arm().mit_control_all(_warmup)
        arm.recv_all()
        time.sleep(0.005)  # 给电机反馈帧到达总线的时间
    return arm


def current_positions(arm):
    """Read the latest joint positions (rad) of an arm."""
    arm.recv_all()
    return np.array(
        [m.get_position() for m in arm.get_arm().get_motors()],
        dtype=np.float32,
    )


def current_states(arm):
    """Read the latest joint positions, velocities and torques of an arm."""
    arm.recv_all()
    motors = arm.get_arm().get_motors()
    return (
        np.array([m.get_position() for m in motors], dtype=np.float32),
        np.array([m.get_velocity() for m in motors], dtype=np.float32),
        np.array([m.get_torque() for m in motors], dtype=np.float32),
    )


def state_struct(arm):
    """Build a StructArray(qpos, qvel, qtorque) snapshot of an arm for recording."""
    qpos, qvel, qtorque = current_states(arm)
    return pa.StructArray.from_arrays(
        [
            pa.array(qpos, type=pa.float32()),
            pa.array(qvel, type=pa.float32()),
            pa.array(qtorque, type=pa.float32()),
        ],
        names=["qpos", "qvel", "qtorque"],
    )


def track(arm, target, kps, kds):
    """Send an MIT position-PD command toward ``target`` (rad)."""
    arm.get_arm().mit_control_all(
        [
            oa.MITParam(kp=float(kps[i]), kd=float(kds[i]), q=float(target[i]), dq=0.0, tau=0.0)
            for i in range(N_MOTORS)
        ]
    )


def align(arm, state, target, kps, kds):
    """Ramp from the initial pose toward ``target`` until aligned; return aligned."""
    if state.base is None:
        state.base = current_positions(arm)
    diff = target - state.base
    if np.all(np.abs(diff) < ALIGN_THRESHOLD):
        track(arm, target, kps, kds)
        state.aligned = True
        return True
    # Move one bounded step toward the target, then hold the reached pose.
    step = np.clip(diff, -ALIGN_STEP, ALIGN_STEP)
    state.base = state.base + step
    track(arm, state.base, kps, kds)
    return False


def to_array(value):
    """Convert an incoming dora event value into a float32 numpy array."""
    if hasattr(value, "to_numpy"):
        return value.to_numpy().astype(np.float32)
    return np.asarray([v.as_py() for v in value], dtype=np.float32)


def main():
    """Run the follower node: track leader targets with PD control."""
    parser = argparse.ArgumentParser(description="OpenArm follower arm node")
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
        "--align-threshold",
        default=float(os.getenv("ALIGN_THRESHOLD", ALIGN_THRESHOLD)),
        help="Alignment threshold [rad] (env: ALIGN_THRESHOLD)",
        type=float,
    )
    parser.add_argument(
        "--only",
        choices=["left", "right", "both"],
        default=os.getenv("ONLY", "both"),
        help="Which arms to enable (left arm not powered -> use 'right') (env: ONLY)",
    )
    args = parser.parse_args()

    arms = {}
    states = {}
    targets = {}
    if args.only in ("left", "both"):
        arms["left"] = make_arm(args.left_can_interface)
        states["left"] = AlignState()
        targets["left"] = None
    if args.only in ("right", "both"):
        arms["right"] = make_arm(args.right_can_interface)
        states["right"] = AlignState()
        targets["right"] = None

    node = dora.Node()
    try:
        for event in node:
            if event["type"] != "INPUT":
                continue

            event_id = event["id"]
            if event_id.startswith("target_"):
                side = event_id.removeprefix("target_")
                if side in targets:
                    targets[side] = to_array(event["value"])
            elif event_id == "control_tick":
                # High-rate (500 Hz) local PD loop on the latest cached targets.
                for side, arm in arms.items():
                    if targets[side] is None:
                        continue
                    if states[side].aligned:
                        track(arm, targets[side], DEFAULT_KPS, DEFAULT_KDS)
                    else:
                        align(arm, states[side], targets[side], DEFAULT_KPS, DEFAULT_KDS)
            elif event_id == "sample_tick":
                # Lower-rate (~200 Hz): stream full joint state (qpos/qvel/qtorque)
                # for recording as observation.
                for side, arm in arms.items():
                    node.send_output(f"state_{side}", state_struct(arm))
    finally:
        for arm in arms.values():
            try:
                arm.disable_all()
            except Exception:
                pass


if __name__ == "__main__":
    main()
