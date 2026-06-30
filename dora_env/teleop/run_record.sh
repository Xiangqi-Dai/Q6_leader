#!/usr/bin/env bash
# 启动录制 dataflow:主从遥操 + 数据采集(双臂16电机 + 3相机,无升降)。
#
# 数据集存放在 {DATASETS_ROOT}/{NAME时间戳}/episodes/N/。
#   - DATASETS_ROOT 可指定(参数1 或 env,默认 /ros2_ws/dora_env/datasets)。
#   - NAME 每次运行用时间戳 → 独立目录,绝不覆盖。
#   - 同一次运行内,多个 episode(浏览器点 Start/Success 反复录)累积在同一 NAME 目录下。
#
# 用法: ./run_record.sh [datasets_root]
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env
REMOTE="$FOLLOWER_USER@$FOLLOWER_IP"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"

DATASETS_ROOT="${1:-${DATASETS_ROOT:-/ros2_ws/dora_env/datasets}}"
NAME="teleop_$(date +%Y%m%d_%H%M%S)"
echo ">> 本次数据集目录: $DATASETS_ROOT/$NAME  (独立,不覆盖)"

cleanup() {
  echo ""
  echo ">> 停止 dataflow + daemons + coordinator..."
  dora stop record 2>/dev/null || true
  kill "${LD:-}" "${COORD:-}" 2>/dev/null || true
  pkill -f 'dora coordinator' 2>/dev/null || true
  pkill -f 'dora daemon --machine-id leader' 2>/dev/null || true
  ssh -p "$SSH_PORT" "$REMOTE" "pkill -f 'dora daemon'" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ">> [1] 确保 opencv-video-capture 已 patch FOURCC(主臂 + 从臂)..."
./patch_capture_fourcc.sh || true
ssh -p "$SSH_PORT" "$REMOTE" "bash /ros2_ws/dora_env/teleop/patch_capture_fourcc.sh" || true
# 确保从臂数据集目录存在
ssh -p "$SSH_PORT" "$REMOTE" "mkdir -p '$DATASETS_ROOT'"

echo ">> [2] 生成本次运行 yaml(NAME=$NAME, ROOT=$DATASETS_ROOT)..."
sed -e "s|__DATASET_NAME__|$NAME|g" -e "s|__DATASETS_ROOT__|$DATASETS_ROOT|g" \
  dataflow-record.yaml > /tmp/dataflow-record-run.yaml

echo ">> [3] 起 coordinator + 两 daemon..."
pkill -f 'dora coordinator' 2>/dev/null || true
pkill -f 'dora daemon --machine-id leader' 2>/dev/null || true
ssh -p "$SSH_PORT" "$REMOTE" "pkill -f 'dora daemon'" 2>/dev/null || true
sleep 1
dora coordinator --quiet & COORD=$!; sleep 2
dora daemon --machine-id leader --coordinator-addr 127.0.0.1 --coordinator-port "$COORD_PORT" --quiet & LD=$!; sleep 2
ssh -p "$SSH_PORT" "$REMOTE" "nohup dora daemon --machine-id follower --coordinator-addr $LEADER_IP --coordinator-port $COORD_PORT --quiet >/tmp/fd.log 2>&1 &"
sleep 3

echo ">> [4] build 节点(幂等)..."
dora build /tmp/dataflow-record-run.yaml || true

echo ""
echo "=========================================================="
echo " 录制已启动。浏览器打开(从臂 web UI):"
echo "   http://$FOLLOWER_IP:8000"
echo " 点 [Start] 开始本 episode → 拖主臂操作 → [Success]/[Fail] 结束"
echo " 可反复 Start 录多个 episode(同目录累积)。Ctrl-C 彻底停止。"
echo " 数据集: $DATASETS_ROOT/$NAME"
echo "=========================================================="
dora start /tmp/dataflow-record-run.yaml --name record --attach
