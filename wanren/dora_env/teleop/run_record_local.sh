#!/usr/bin/env bash
# 【单机】启动录制 dataflow: 本机 .56 上 slot1 主臂 → slot2 从臂遥操 + 3 相机 + 数据采集。
#
# 数据集: {DATASETS_ROOT}/{NAME时间戳}/episodes/N/{obs,action,cameras}/...
#   格式与 dataset/test/smoke_test/episodes 一致(recorder 节点原生输出)。
#   - DATASETS_ROOT 可指定(参数1 或 env, 默认 /ros2_ws/wanren/dora_env/datasets)。
#   - NAME 每次运行用时间戳 → 独立目录, 绝不覆盖。
#   - 同一次运行内, 多个 episode(浏览器 Start/Success 反复录)累积在同一 NAME 目录。
#
# 用法: ./run_record_local.sh [datasets_root]
set -euo pipefail
cd "$(dirname "$0")"

DATASETS_ROOT="${1:-${DATASETS_ROOT:-/ros2_ws_dxq/wanren/dora_env/datasets}}"
mkdir -p "$DATASETS_ROOT"
# 命名规则: data01, data02, ... 递增(扫描已有 dataNN 取最大序号 +1, 2位补零; 绝不覆盖)
max=0
for d in "$DATASETS_ROOT"/data*/ ; do
  [ -d "$d" ] || continue
  n=$(basename "$d" | sed -n 's/^data\([0-9][0-9]*\)$/\1/p')
  if [ -n "$n" ] && [ "$((10#$n))" -gt "$max" ]; then max=$((10#$n)); fi
done
NAME=$(printf "data%02d" $((max + 1)))
echo ">> 本次数据集目录: $DATASETS_ROOT/$NAME  (独立, 不覆盖)"

echo ">> [0] 拉起 4 个 CAN 口(slot1 主臂 + slot2 从臂)..."
for ifc in can_slot1_ch0 can_slot1_ch1 can_slot2_ch0 can_slot2_ch1; do
  sudo ip link set "$ifc" down 2>/dev/null || true
  if sudo ip link set "$ifc" up type can bitrate 1000000 dbitrate 5000000 fd on restart-ms 1 2>/dev/null; then
    echo "   $ifc: OK"
  else
    echo "   $ifc: 失败(可能未上电/不存在)"
  fi
done

cleanup() {
  echo ""
  echo ">> 清理所有节点进程(防 ui/相机变孤儿残留)..."
  # 按具体命令行匹配, 不会误杀本脚本自身(cmdline 只是 bash run_record_local.sh)
  pkill -f '/usr/local/bin/dora run' 2>/dev/null || true
  pkill -f '/usr/local/bin/opencv-video-capture' 2>/dev/null || true
  pkill -f 'dora-openarm-leader' 2>/dev/null || true
  pkill -f 'dora-openarm-follower' 2>/dev/null || true
  pkill -f 'dora-openarm-dataset-recorder' 2>/dev/null || true
  pkill -f 'dora-openarm-data-collection-ui' 2>/dev/null || true
  echo ">> 已停止。"
}
trap cleanup EXIT INT TERM

echo ">> [1] patch opencv-video-capture FOURCC(本机)..."
bash ./patch_capture_fourcc.sh || true

echo ">> [2] 生成本次 yaml(NAME=$NAME, ROOT=$DATASETS_ROOT; 去掉 _unstable_deploy, dora run 用不上)..."
sed -e "s|__DATASET_NAME__|$NAME|g" -e "s|__DATASETS_ROOT__|$DATASETS_ROOT|g" -e '/_unstable_deploy:/d' \
  dataflow-record.yaml > /tmp/dataflow-record-local.yaml

echo ">> [3] dora run(本地运行, 自动 build + 跑; 无需 coordinator/daemon。Ctrl-C 停止)"
echo ""
echo "=========================================================="
echo " 录制已启动。浏览器打开(本机 web UI):"
echo "   http://192.168.0.56:8000"
echo " 点 [Start] 开始本 episode → 拖主臂(slot1)操作 → [Success]/[Fail] 结束"
echo " 可反复 Start 录多个 episode(同目录累积)。Ctrl-C 彻底停止。"
echo " 数据集: $DATASETS_ROOT/$NAME"
echo "=========================================================="
dora run /tmp/dataflow-record-local.yaml
