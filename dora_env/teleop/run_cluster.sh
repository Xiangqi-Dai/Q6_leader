#!/usr/bin/env bash
# dora 0.5.0 分布式启动:主臂 coordinator + 本地 daemon(machine=leader),
# SSH 到从臂起 daemon(machine=follower,连主臂 coordinator),然后 build + start。
#
# 前提:
#   1. cluster.env 已填(从臂 IP/用户/端口)。
#   2. 主臂→从臂免密 SSH 通。
#   3. 两机都已 deploy_follower.sh 部署过(从臂装好 follower + 依赖)。
#   4. 两机 CAN 口都已 up(can_slot1_ch0 / can_slot1_ch1)。
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env

REMOTE="$FOLLOWER_USER@$FOLLOWER_IP"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"

# 数据流文件 / 流名可被环境变量覆盖(默认双臂)。跑右臂单臂:
#   DATAFLOW=dataflow-teleop-right.yaml FLOW_NAME=teleop-right ./run_cluster.sh
DATAFLOW="${DATAFLOW:-dataflow-teleop.yaml}"
FLOW_NAME="${FLOW_NAME:-teleop}"

cleanup() {
  echo ""
  echo ">> 停止 dataflow + daemons + coordinator..."
  dora stop "$FLOW_NAME" 2>/dev/null || true
  kill "${LEADER_D_PID:-}" "${COORD_PID:-}" 2>/dev/null || true
  ssh -p "$SSH_PORT" "$REMOTE" "pkill -f 'dora daemon --machine-id follower'" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ">> 主臂:启动 coordinator (监听 0.0.0.0:$COORD_PORT)..."
dora coordinator --quiet &
COORD_PID=$!
sleep 2

echo ">> 主臂:启动本地 daemon (machine=leader)..."
dora daemon --machine-id leader \
  --coordinator-addr 127.0.0.1 --coordinator-port "$COORD_PORT" --quiet &
LEADER_D_PID=$!

echo ">> 从臂:SSH 启动 daemon (machine=follower, 连 $LEADER_IP:$COORD_PORT)..."
ssh -p "$SSH_PORT" "$REMOTE" "dora daemon --machine-id follower \
  --coordinator-addr $LEADER_IP --coordinator-port $COORD_PORT --quiet" &
sleep 3

echo ">> Build 节点(幂等;依赖已由 deploy_follower.sh 装好)..."
dora build "$DATAFLOW" || true

echo ""
echo ">> 启动遥操数据流 ($DATAFLOW, name=$FLOW_NAME;拖动主臂 → 从臂跟随;Ctrl-C 停止)..."
dora start "$DATAFLOW" --name "$FLOW_NAME" --attach
