# dora-openarm-leader

dora-rs node for the **leader** arm in a leader-follower teleoperation setup.

It keeps both the left and right OpenArm in **zero-torque mode** (MIT gains and
feed-forward torque all zero) so a human can freely drag the arm, and on every
incoming `tick` it publishes the latest joint positions:

- `position_left`  — float32[8] (7 joints + gripper), left arm
- `position_right` — float32[8] (7 joints + gripper), right arm

These outputs are consumed by `dora-openarm-follower` running on the follower
machine.

## Low-level driver

Uses the C++ `openarm_can` Python bindings directly (one `OpenArm` instance per
CAN interface), not the Python subprocess wrapper.

## Configuration

The CAN interface for each arm can be set via CLI args or environment variables:

| Argument                | Env       | Default          |
| ----------------------- | --------- | ---------------- |
| `--left-can-interface`  | `CAN_LEFT`  | `can_slot1_ch0`  |
| `--right-can-interface` | `CAN_RIGHT` | `can_slot1_ch1`  |

The 7-DoF + gripper topology (motor types, send/recv CAN IDs) mirrors
`openarm_driver/config.yaml`.
