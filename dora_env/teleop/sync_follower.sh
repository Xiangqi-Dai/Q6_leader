#!/usr/bin/env bash
# 轻量同步 follower 代码到从臂(开发快速迭代用)。
# 只 rsync 源码,不装依赖 —— editable 安装 + 节点 spawn 时加载代码,
# 故纯代码改动 rsync 后重启 dataflow 即生效。
# 用法: ./sync_follower.sh           # 轻量同步 + 停当前 dataflow
#       ./sync_follower.sh --install # 等价 deploy_follower.sh(完整部署)
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env

if [ "${1:-}" = "--install" ]; then
  exec ./deploy_follower.sh
fi

REMOTE="$FOLLOWER_USER@$FOLLOWER_IP"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"
PKG_DIR="/ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-follower"

echo ">> 轻量同步 follower 代码到从臂 (rsync only)..."
rsync -az -e "ssh -p $SSH_PORT" --delete "$PKG_DIR/" "$REMOTE:$PKG_DIR/"

echo ">> 停止当前 dataflow 'teleop' (若在跑, daemon 保持)..."
dora stop teleop 2>/dev/null || true

cat <<EOF

✓ 代码已同步到从臂。重新启动 dataflow 即加载新代码:
  - daemon 仍在跑(后台/常驻): dora start dataflow-teleop.yaml --name teleop --attach
  - daemon 已停(之前 Ctrl-C 过 run_cluster.sh): ./run_cluster.sh
EOF
