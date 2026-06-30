#!/usr/bin/env bash
# Bring up the dora cluster, build the dataflow, then run it attached.
#
# Prerequisites:
#   1. cluster.yml filled in (follower host IP + SSH users, passwordless SSH).
#   2. CAN interfaces up on BOTH hosts, e.g. on each host:
#        sudo ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on
#        sudo ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on
#   3. dora (0.5.0) + openarm_can installed on both hosts; both node packages
#      pip-installed on the leader host (follower gets them via `distribute: scp`).
set -euo pipefail

cd "$(dirname "$0")"

echo ">> Starting cluster (coordinator + daemons)..."
dora cluster up cluster.yml

echo ">> Building dataflow..."
dora build dataflow-teleop.yaml

echo ">> Starting teleoperation dataflow (Ctrl-C to stop)..."
dora start dataflow-teleop.yaml --name teleop --attach
