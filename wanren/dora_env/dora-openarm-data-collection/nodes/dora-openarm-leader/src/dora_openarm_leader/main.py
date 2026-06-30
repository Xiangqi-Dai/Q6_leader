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

Two drive modes (``--mode``):

* ``zero_torque`` (default): keeps both arms at ``tau=0`` so a human can freely
  drag the arm. Safe opt-out default.
* ``gravity_comp``: instead of ``tau=0``, feeds a *low-torque* gravity
  compensation ``tau = gain * G(q)`` to the shoulder (J2) and elbow (J4) joints
  only, computed from the bimanual URDF via MuJoCo (see ``gravity.py``). This
  cancels the arm's own weight so the master feels weightless instead of heavy,
  while staying pure feed-forward (``kp=kd=0``, no stiffness/damping added).

On every tick it drives both arms (high rate), reads back the current joint
positions and publishes them as ``position_left`` / ``position_right`` so a
remote follower can track them.
"""

import argparse
import os

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

# Zero-torque command: MIT mode with all gains and feed-forward torque at zero.
ZERO_MIT = [oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=0.0) for _ in range(N_MOTORS)]

# Gravity-bearing joints (the two big ones in the OpenArm URDF): J2 = shoulder
# pitch (motor idx 1) and J4 = elbow (motor idx 3). Wrist/base carry <0.3 Nm and
# are intentionally left uncompensated to keep the compensation focused + safe.
DEFAULT_GRAVITY_JOINTS = "2,4"  # 1-based joint numbers passed via --gravity-joints


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
    arm.recv_all()
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
        "--mode",
        choices=["zero_torque", "gravity_comp"],
        default=os.getenv("LEADER_MODE", "zero_torque"),
        help="Drive mode: zero_torque (default, tau=0) or gravity_comp "
        "(low-torque gravity feed-forward on shoulder/elbow) (env: LEADER_MODE)",
    )
    parser.add_argument(
        "--gravity-gain",
        type=float,
        default=float(os.getenv("LEADER_GRAVITY_GAIN", "0.7")),
        help="Gain on the gravity torque in gravity_comp mode (env: "
        "LEADER_GRAVITY_GAIN). <1.0 = partial/low-torque (stable).",
    )
    parser.add_argument(
        "--gravity-joints",
        default=os.getenv("LEADER_GRAVITY_JOINTS", DEFAULT_GRAVITY_JOINTS),
        help="Comma-separated 1-based joint numbers to compensate "
        "(default '2,4' = shoulder+elbow) (env: LEADER_GRAVITY_JOINTS)",
    )
    args = parser.parse_args()

    left = make_arm(args.left_can_interface)
    right = make_arm(args.right_can_interface)

    # Build the per-tick MIT-command factory. Zero-torque mode never imports
    # MuJoCo; gravity_comp loads the URDF model once at startup.
    gravity_mask = set()
    compensator = None
    if args.mode == "gravity_comp":
        from .gravity import GravityCompensator

        gravity_mask = {int(j) - 1 for j in args.gravity_joints.split(",") if j.strip()}
        compensator = GravityCompensator()
        print(
            f">> gravity_comp mode: joints={sorted(j + 1 for j in gravity_mask)} "
            f"gain={args.gravity_gain}"
        )

    def mit_for(side, arm):
        """Return the MIT command list for one arm on this control tick."""
        if compensator is None:
            return ZERO_MIT
        arm.recv_all()
        positions = np.array(
            [m.get_position() for m in arm.get_arm().get_motors()], dtype=np.float64
        )
        gravity = compensator.gravity(side, positions)
        tau = np.zeros(N_MOTORS, dtype=np.float64)
        for i in gravity_mask:
            tau[i] = args.gravity_gain * gravity[i]
        return [
            oa.MITParam(kp=0.0, kd=0.0, q=0.0, dq=0.0, tau=float(tau[i]))
            for i in range(N_MOTORS)
        ]

    node = dora.Node()
    try:
        for event in node:
            if event["type"] != "INPUT":
                continue

            event_id = event["id"]
            if event_id == "control_tick":
                # High rate (500 Hz): drive both arms. In zero_torque this holds
                # tau=0; in gravity_comp it feeds gain*G(q) to the shoulder/elbow.
                # DAMIAO needs continuous MIT frames, so this runs faster than
                # the position streaming below.
                left.get_arm().mit_control_all(mit_for("left", left))
                right.get_arm().mit_control_all(mit_for("right", right))
            elif event_id == "sample_tick":
                # Lower rate (200 Hz): read back joint positions and stream them
                # to the follower over the (slower) cross-machine link.
                node.send_output(
                    "position_left",
                    pa.array(read_positions(left), type=pa.float32()),
                )
                node.send_output(
                    "position_right",
                    pa.array(read_positions(right), type=pa.float32()),
                )
    finally:
        # Safely disable both arms on exit (Ctrl-C, quitter stop, ...).
        for arm in (left, right):
            try:
                arm.disable_all()
            except Exception:
                pass


if __name__ == "__main__":
    main()
