# dora-openarm-follower

dora-rs node for the **follower** arm in a leader-follower teleoperation setup.

Receives target joint positions from `dora-openarm-leader`:

- `target_left`  — float32[8] (7 joints + gripper), left arm
- `target_right` — float32[8] (7 joints + gripper), right arm

and tracks them with **MIT-mode position PD control**. Because both devices are
identical, the raw joint angles are copied 1:1 — no coordinate mapping.

## Alignment (first frame)

On the first received target each arm **ramps** from its current pose toward the
target (bounded step per frame) until the gap is below `--align-threshold`. This
prevents a sudden jump when teleoperation starts. After alignment it tracks the
leader 1:1.

## Low-level driver

Uses the C++ `openarm_can` Python bindings directly.

## Configuration

| Argument                | Env              | Default          |
| ----------------------- | ---------------- | ---------------- |
| `--left-can-interface`  | `CAN_LEFT`       | `can_slot1_ch0`  |
| `--right-can-interface` | `CAN_RIGHT`      | `can_slot1_ch1`  |
| `--align-threshold`     | `ALIGN_THRESHOLD`| `0.1` (rad)      |

PD gains default to `openarm_driver/config.yaml` `control_gains`.
