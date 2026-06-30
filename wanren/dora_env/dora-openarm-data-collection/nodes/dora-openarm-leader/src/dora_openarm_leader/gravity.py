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

"""Gravity-compensation helper for the OpenArm leader.

Loads the bimanual OpenArm URDF into MuJoCo and, given the current motor
positions of one arm, returns the per-joint gravity torque ``G(q)`` (the
generalized gravity force). At zero velocity MuJoCo's ``qfrc_bias`` is exactly
``G(q)``, so feeding ``tau = G(q)`` back to the MIT-mode motors makes the arm
hold its own weight against gravity (pure feed-forward, no stiffness/damping).

This mirrors the validated C++ KDL reference
(``openarm_teleop/control/gravity_compasation.cpp``): same URDF, same sign and
magnitude convention, same ``MITParam{0,0,0,0,tau}`` output.

The URDF ships with ``package://openarm_description/`` mesh URIs which MuJoCo
cannot resolve, so we rewrite them to absolute paths at load time.
"""

import os

import numpy as np

# Bimanual URDF produced by openarm_description (root link openarm_body_link0,
# arms openarm_{left,right}_joint1..7 + finger joints).
DEFAULT_URDF = os.environ.get(
    "OPENARM_BIMANUAL_URDF",
    "/ros2_ws/openarm_ros2/openarm_description/output.urdf",
)
# ROS package URI -> absolute path rewrite so MuJoCo can find the STL meshes.
_PKG_PREFIX = "package://openarm_description/"
_PKG_ROOT = "/ros2_ws/openarm_ros2/openarm_description/"

# The motor encoder zero (set via `left_arm.py setzero`) does NOT coincide with
# the URDF joint zero. openarm_driver maps motor->URDF as
# ``urdf_q = motor_q - joint_offset`` (driver.py:140). Gravity is a function of
# the *absolute* URDF joint angle, so we MUST subtract these offsets before
# evaluating G(q); otherwise the gravity torque is wrong (the elbow offset is
# -1.745 rad ~ -100 deg, far from negligible). Torque needs no conversion back:
# it is conjugate to the joint coordinate, and a pure offset leaves it invariant.
_DRIVER_CONFIG_CANDIDATES = [
    os.environ.get("OPENARM_DRIVER_CONFIG", ""),
    "/usr/local/lib/python3.10/dist-packages/openarm_driver/config.yaml",
]
_FALLBACK_JOINT_OFFSETS = {
    # Fallback copy of openarm_driver/config.yaml `joint_offsets` (8 entries:
    # J1..J7 + gripper). Only the first 7 are used for gravity.
    "right_arm": [0.0, -0.506145, 1.570796, -1.745329, 0.0, 0.331612, -1.570796, 0.0],
    "left_arm": [0.0, 0.506145, -1.570796, -1.745329, 0.0, -0.331612, 1.570796, 0.0],
}


def _load_joint_offsets() -> dict:
    """Load motor->URDF joint offsets per arm from openarm_driver config.yaml.

    Keys returned are ``left_arm`` / ``right_arm`` (8-vectors). Falls back to the
    hardcoded copy if the config file or PyYAML is unavailable.
    """
    for path in _DRIVER_CONFIG_CANDIDATES:
        if not path or not os.path.isfile(path):
            continue
        try:
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            jo = cfg.get("joint_offsets")
            if jo and "left_arm" in jo and "right_arm" in jo:
                return {k: np.array(v, dtype=np.float64) for k, v in jo.items()}
        except Exception:
            continue
    return {k: np.array(v, dtype=np.float64) for k, v in _FALLBACK_JOINT_OFFSETS.items()}

# Motor index -> OpenArm joint. Mirrors MOTOR_TYPES in main.py:
#   0:J1(base yaw) 1:J2(shoulder pitch) 2:J3 3:J4(elbow) 4:J5 5:J6 6:J7 7:gripper
ARM_MOTOR_INDEXES = list(range(7))  # J1..J7 (gripper at index 7 has no gravity)


class GravityCompensator:
    """Per-joint gravity torque ``G(q)`` from the bimanual URDF via MuJoCo."""

    def __init__(self, urdf_path: str = DEFAULT_URDF):
        # Imported lazily so the zero-torque leader path stays dependency-light.
        import mujoco

        self._mj = mujoco
        with open(urdf_path, "r", encoding="utf-8") as f:
            xml = f.read()
        if _PKG_PREFIX in xml and not os.path.isdir(_PKG_ROOT):
            raise FileNotFoundError(
                f"OpenArm meshes not found at {_PKG_ROOT}; set OPENARM_BIMANUAL_URDF"
            )
        xml = xml.replace(_PKG_PREFIX, _PKG_ROOT)

        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)

        # Cache qpos/dof addresses of openarm_{side}_joint1..7 per arm.
        self._qposadr: dict[str, list[int]] = {}
        self._dofadr: dict[str, list[int]] = {}
        for side in ("left", "right"):
            qa, da = [], []
            for k in range(1, 8):
                jid = mujoco.mj_name2id(
                    self.model, mujoco.mjtObj.mjOBJ_JOINT, f"openarm_{side}_joint{k}"
                )
                if jid < 0:
                    raise RuntimeError(
                        f"joint openarm_{side}_joint{k} not found in {urdf_path}"
                    )
                qa.append(int(self.model.jnt_qposadr[jid]))
                da.append(int(self.model.jnt_dofadr[jid]))
            self._qposadr[side] = qa
            self._dofadr[side] = da

        # motor->URDF joint offsets (left_arm/right_arm keys -> left/right).
        offsets = _load_joint_offsets()
        self._offset = {
            "left": offsets["left_arm"],
            "right": offsets["right_arm"],
        }

    def gravity(self, side: str, positions: np.ndarray) -> np.ndarray:
        """Return the 8-vector gravity torque (motor order, Nm).

        ``positions`` is the 8-vector [J1..J7, gripper] in radians (**motor**
        order, as returned by ``motor.get_position()``). The motor->URDF joint
        offset is applied internally before evaluating G(q). The returned vector
        is laid out the same motor way; index 7 (gripper) is always 0. The whole
        other arm is held at q=0 — the two arms are independent chains from the
        body, so it does not affect this arm's gravity.
        """
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        m, d = self.model, self.data
        qa = self._qposadr[side]
        da = self._dofadr[side]
        offset = self._offset[side]

        d.qpos[:] = 0.0
        d.qvel[:] = 0.0
        for i in ARM_MOTOR_INDEXES:
            d.qpos[qa[i]] = float(positions[i]) - float(offset[i])
        self._mj.mj_forward(m, d)

        tau = np.zeros(8, dtype=np.float64)
        for i in ARM_MOTOR_INDEXES:
            tau[i] = float(d.qfrc_bias[da[i]])
        return tau
