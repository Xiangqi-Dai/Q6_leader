#!/usr/bin/env bash
# 从主臂机一键部署 follower 节点到从臂机:
#   1) rsync follower 节点包
#   2) 在从臂装依赖(dora-rs / openarm_can / numpy / pyarrow)+ follower 包
#   3) 验证导入
# 用法: ./deploy_follower.sh
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env

REMOTE="$FOLLOWER_USER@$FOLLOWER_IP"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"
ROOT=/ros2_ws/dora_env
PKG_DIR="$ROOT/dora-openarm-data-collection/nodes/dora-openarm-follower"

echo ">> [1/3] 同步 follower 节点包到从臂 ($REMOTE:$SSH_PORT)..."
rsync -az -e "ssh -p $SSH_PORT" --delete \
  "$PKG_DIR/" "$REMOTE:$PKG_DIR/"

echo ">> [2/3] 在从臂装依赖 + follower 包..."
ssh -p "$SSH_PORT" "$REMOTE" bash -se <<'EOF'
set -e
pip install --quiet dora-rs==0.5.0 'openarm_can==1.2.9' numpy pyarrow
pip install -e /ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-follower
EOF

echo ">> [3/3] 验证从臂依赖..."
ssh -p "$SSH_PORT" "$REMOTE" "python3 -c 'import dora, openarm_can, dora_openarm_follower; print(\"OK\")'"

cat <<EOF

✓ 从臂部署完成。接下来:
  1. 从臂 up CAN 口(已是 root,免 sudo):
       ssh -p $SSH_PORT $REMOTE 'ip link set can_slot1_ch0 up type can bitrate 1000000 dbitrate 5000000 fd on; ip link set can_slot1_ch1 up type can bitrate 1000000 dbitrate 5000000 fd on'
  2. 回主臂跑 ./run_cluster.sh。
EOF
