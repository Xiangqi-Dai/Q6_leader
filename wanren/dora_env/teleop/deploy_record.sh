#!/usr/bin/env bash
# 部署录制所需组件到从臂(在主臂执行):
#   follower(含 state 输出)+ recorder + ui + opencv-video-capture(patch)+ 配置文件。
# 用法: ./deploy_record.sh   (代码/依赖变更后重跑,幂等)
set -euo pipefail
cd "$(dirname "$0")"
source ./cluster.env
REMOTE="$FOLLOWER_USER@$FOLLOWER_IP"
SSH_PORT="${FOLLOWER_SSH_PORT:-22}"
SSH="ssh -p $SSH_PORT $REMOTE"
ROOT=/ros2_ws/dora_env
NODES="$ROOT/dora-openarm-data-collection/nodes"

echo ">> [1] 同步节点包(follower/recorder/ui)+ teleop 脚本/metadata 到从臂..."
for pkg in dora-openarm-follower dora-openarm-dataset-recorder dora-openarm-data-collection-ui; do
  rsync -az -e "ssh -p $SSH_PORT" --delete "$NODES/$pkg/" "$REMOTE:$NODES/$pkg/"
done
rsync -az -e "ssh -p $SSH_PORT" \
  patch_capture_fourcc.sh metadata-record.yaml dataflow-record.yaml run_record.sh \
  "$REMOTE:$ROOT/teleop/"

echo ">> [2] 从臂装节点包 + opencv-video-capture..."
$SSH bash -se <<'EOF'
set -e
pip install -e /ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-follower -q
pip install -e /ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-dataset-recorder -q
pip install -e /ros2_ws/dora_env/dora-openarm-data-collection/nodes/dora-openarm-data-collection-ui -q
pip install opencv-video-capture -q
EOF
# 清 __pycache__,避免 editable 旧 .pyc 导致 recorder 跑旧代码(_load_existing_episodes bug)
$SSH "find /ros2_ws/dora_env/dora-openarm-data-collection/nodes -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"

echo ">> [3] 从臂 patch opencv-video-capture(加 CAPTURE_FOURCC,头顶 MJPG 需要)..."
$SSH "bash $ROOT/teleop/patch_capture_fourcc.sh"

echo ">> [4] 验证从臂导入..."
$SSH "python3 -c 'import dora_openarm_follower, dora_openarm_dataset_recorder, dora_openarm_data_collection_ui, opencv_video_capture; print(\"OK\")'"

echo ""
echo "✓ 从臂录制环境部署完成。运行: ./run_record.sh [datasets_root]"
