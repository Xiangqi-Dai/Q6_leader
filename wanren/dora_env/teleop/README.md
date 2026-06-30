# Bimanual Leader-Follower Teleoperation

Distributed dora dataflow for teleoperating one OpenArm setup (leader) from
another (follower). Both setups are identical RK3588 boards; the leader arms are
held in zero-torque mode and dragged by hand, and the follower tracks the
leader's joint angles 1:1 over the network.

```
leader host (192.168.0.56)                follower host (192.168.0.?)
┌──────────────────────────┐              ┌──────────────────────────┐
│ leader-tick  100Hz       │              │                          │
│ leader       L/R zero-tq │ position_L/R │ follower    L/R MIT PD   │
│              read joints ─┼──────────────▶              track 1:1  │
└──────────────────────────┘   (Zenoh)    └──────────────────────────┘
   coordinator + daemon                         daemon
```

## Files

| File                  | Purpose                                                     |
| --------------------- | ----------------------------------------------------------- |
| `dataflow-teleop.yaml`| The distributed dataflow graph (node placement + wiring).   |
| `cluster.yml`         | Cluster topology: coordinator addr + the two machines.      |
| `run_cluster.sh`      | `cluster up` → `build` → `start --attach`.                  |
| `stop.sh`             | `stop` + `cluster down`.                                    |

The two node packages live in
`../dora-openarm-data-collection/nodes/dora-openarm-leader` and
`.../dora-openarm-follower`.

> **dora 0.5.0 has no `distribute` field** (verified — `_unstable_deploy` only
> accepts `machine`/`working_dir`), so node source is **not** auto-pushed.
> Each host must have its node package installed locally (see step 2).

## Setup

1. **Fill in `cluster.yml`**: follower host IP, SSH users on both hosts. Ensure
   passwordless SSH from the leader host to both hosts.
2. **Software on both hosts**: `dora==0.5.0` and `openarm_can` installed
   everywhere. Then install the node packages — on the leader host:
   ```bash
   pip install -e ../dora-openarm-data-collection/nodes/dora-openarm-leader
   pip install -e ../dora-openarm-data-collection/nodes/dora-openarm-follower
   ```
   and sync the follower package to the follower host and install it there too,
   e.g. via rsync or git clone:
   ```bash
   rsync -az ../dora-openarm-data-collection/nodes/dora-openarm-follower \
       <follower-user>@<follower-host>:/ros2_ws/dora_env/dora-openarm-data-collection/nodes/
   ssh <follower-user>@<follower-host> \
       'cd /ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-follower && pip install -e .'
   ```
3. **Bring CAN up on both hosts** (interface names must match the node `args`
   in `dataflow-teleop.yaml`, default `can_slot1_ch0` / `can_slot1_ch1`):
   ```bash
   sudo ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on
   sudo ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on
   ```

## Run

```bash
./run_cluster.sh        # start cluster, build, run attached
# ... drag the leader arms; the follower tracks ...
# Ctrl-C stops the dataflow
./stop.sh               # stop + tear down
```

## Checks

```bash
dora cluster status     # both daemons connected?
dora logs teleop --node leader --follow
dora graph dataflow-teleop.yaml --open
```

## Local smoke test (no cluster)

Replace the `leader` node with `dora-openarm-dummy` and run locally with
`dora run dataflow-teleop.yaml` to validate the wiring without hardware or a
second machine. (`_unstable_deploy` fields are ignored by `dora run`.)
