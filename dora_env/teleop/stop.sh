#!/usr/bin/env bash
# 停止遥操 dataflow + 拆除两机 daemon / coordinator(dora 0.5.0)。
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env 2>/dev/null || true
REMOTE="${FOLLOWER_USER:-root}@${FOLLOWER_IP:-}"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"

# 流名可被环境变量覆盖(默认双臂的 teleop)。停右臂单臂:
#   FLOW_NAME=teleop-right ./stop.sh
FLOW_NAME="${FLOW_NAME:-teleop}"

echo ">> 停止 dataflow '$FLOW_NAME' (若在运行)..."
dora stop "$FLOW_NAME" 2>/dev/null || true

echo ">> 终止主臂 daemon / coordinator..."
pkill -f 'dora daemon' 2>/dev/null || true
pkill -f 'dora coordinator' 2>/dev/null || true

if [ -n "${FOLLOWER_IP:-}" ]; then
  echo ">> 终止从臂 daemon..."
  ssh -p "$SSH_PORT" "$REMOTE" "pkill -f 'dora daemon'" 2>/dev/null || true
fi
echo "✓ 已停止"
