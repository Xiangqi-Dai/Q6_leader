# Bimanual Leader-Follower Teleoperation

Distributed dora dataflow for teleoperating one OpenArm setup (follower) from
another (leader). Both setups are identical RK3588 boards; the leader arms are
held in zero-torque mode and dragged by hand, the follower tracks the leader's
joint angles 1:1 over the network.

**Frequencies are decoupled** — the leader holds zero-torque at 500 Hz and
streams joint angles at 200 Hz; the follower runs a local 500 Hz PD loop on the
latest cached target, so tracking stays smooth even if a network frame drops.

```
leader host (192.168.0.56)                 follower host (FOLLOWER_IP)
┌────────────────────────────┐             ┌────────────────────────────┐
│ leader-tick  500Hz         │             │                            │
│ leader       L/R zero-tq   │  pos L/R    │ follower   L/R MIT PD      │
│   control_tick 500Hz       │ ──200Hz────▶│   control_tick 500Hz       │
│   sample_tick  200Hz read  │   (Zenoh)   │   track cached target 1:1  │
└────────────────────────────┘             └────────────────────────────┘
   coordinator + daemon (machine=leader)      daemon (machine=follower)
```

> **dora 0.5.0 has no `dora cluster` command** — distributed runs use
> `dora coordinator` + `dora daemon` instead (see `run_cluster.sh`).
> The node source is **not** auto-pushed; `deploy_follower.sh` handles that.

## Files

| File                  | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `dataflow-teleop.yaml`| Distributed dataflow graph (node placement via `_unstable_deploy.machine` + wiring). |
| `cluster.env`         | Shell variables: both hosts' IP / SSH user / coordinator port.   |
| `deploy_follower.sh`  | One-shot: rsync the follower package to the follower host + install deps. |
| `run_cluster.sh`      | Start coordinator + both daemons, build, `dora start --attach`.  |
| `stop.sh`             | Stop the dataflow + kill both daemons/coordinator.               |

The two node packages live in
`../dora-openarm-data-collection/nodes/dora-openarm-leader` and
`.../dora-openarm-follower`.

## Setup (do once)

1. **Fill in `cluster.env`**: follower host IP + SSH users on both hosts. Ensure
   passwordless SSH from the leader host to the follower host.

2. **Install on the leader host** (this machine):
   ```bash
   pip install dora-rs==0.5.0 'openarm_can==1.2.9' numpy pyarrow
   pip install -e ../dora-openarm-data-collection/nodes/dora-openarm-leader
   pip install -e ../dora-openarm-data-collection/nodes/dora-openarm-follower
   ```

3. **Deploy the follower package + deps to the follower host** (run from the
   leader host; repeats safely on every code change):
   ```bash
   ./deploy_follower.sh
   ```

4. **Bring CAN up on BOTH hosts** (interface names must match the node args,
   default `can_slot1_ch0` / `can_slot1_ch1`):
   ```bash
   sudo ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on
   sudo ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on
   ```

> The leader host runs in a Docker container with **host networking**
> (`wlP2p33s0` = `192.168.0.56`), so the coordinator's `0.0.0.0:53290` is
> reachable from the follower host directly — no port mapping needed.

## Run

```bash
./run_cluster.sh        # start coordinator + daemons, build, run attached
# ... drag the leader arms; the follower tracks ...
# Ctrl-C stops the dataflow (daemons/coordinator are cleaned up)
./stop.sh               # belt-and-suspenders full teardown
```

## Checks

```bash
dora logs teleop --node leader --follow      # leader stream
dora logs teleop --node follower --follow    # follower stream
dora graph dataflow-teleop.yaml --open       # visualize the graph
```

## Local smoke test (no second machine)

Validate the leader node alone on this host with
`../text/dataflow-leader-test.yaml` (`dora run`, no coordinator/daemon needed).
For a hardware-only check, use the standalone script
`../text/test_leader_zero_torque.py` (no dora at all).
