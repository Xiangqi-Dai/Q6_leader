#!/usr/bin/env bash
# 探测所有相机的 color 节点 + by-id + 分辨率。换 USB 口 / 重启后跑,确认 CAPTURE_PATH。
# 在从臂跑(从主臂):
#   ssh -p 20000 root@192.168.0.238 'bash /ros2_ws/dora_env/teleop/probe_cameras.sh'
echo "=== color 节点(按 by-id,换口不变)==="
for d in /dev/v4l/by-id/*; do
  fmt=$(v4l2-ctl -d "$d" --list-formats-ext 2>/dev/null) || continue
  echo "$fmt" | grep -qiE "YUYV|MJPG" || continue
  echo "--- $(basename "$d") -> $(basename "$(readlink -f "$d")") ---"
  echo "$fmt" | grep -iE "\[.*YUYV|\[.*MJPG|1920x1080|1280x720|640x480" | head -4
done
echo ""
echo "=== 支持 1920x1080 的 videoN(确认腕右 color 节点号,无 by-id 的相机用这个)==="
for n in /dev/video[0-9]*; do
  [ -c "$n" ] || continue
  v4l2-ctl -d "$n" --list-formats-ext 2>/dev/null | grep -q "1920x1080" && echo "  $n 支持 1920x1080"
done
