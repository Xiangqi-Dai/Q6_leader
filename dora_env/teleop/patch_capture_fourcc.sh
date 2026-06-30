#!/usr/bin/env bash
# patch opencv-video-capture(幂等):
#   ① CAPTURE_FOURCC:头顶奥比中光要 MJPG 采集(640x480 MJPG @30)
#   ② 分辨率双 set:先设非标准值再设目标,触发 V4L2 重协商
#      (opencv 对部分 RealSense color 流直接 set 目标会静默回退,如 video11)
# 主臂/从臂各跑一次;每次 pip 重装 opencv-video-capture 后也要重跑。
set -euo pipefail
TARGET=$(python3 -c "import opencv_video_capture,os;print(os.path.join(os.path.dirname(opencv_video_capture.__file__),'main.py'))")
if grep -q "openarm patch] 先设非标准值" "$TARGET" 2>/dev/null; then
  echo "已全部 patch: $TARGET"; exit 0
fi
python3 - "$TARGET" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(); orig = s

# Patch ① CAPTURE_FOURCC
if "CAPTURE_FOURCC" not in s:
    n1 = '    image_width = os.getenv("IMAGE_WIDTH", args.image_width)\n\n    if image_width is not None:\n'
    assert n1 in s, "patch①锚点未找到"
    s = s.replace(n1, (
        '    # [openarm patch] Optional capture FOURCC (MJPG). Set before WIDTH/HEIGHT\n'
        '    # so V4L2 picks the resolution under this format (Orbbec Gemini 335 needs MJPG).\n'
        '    capture_fourcc = os.getenv("CAPTURE_FOURCC", "")\n'
        '    if capture_fourcc:\n'
        '        video_capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*capture_fourcc[:4].upper()))\n\n'
    ) + n1, 1)

# Patch ② 分辨率双 set(+2 触发 V4L2 重协商)
if "先设非标准值" not in s:
    n2w = '        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, image_width)\n'
    assert n2w in s, "patch②WIDTH锚点未找到"
    s = s.replace(n2w, (
        '        # [openarm patch] 先设非标准值再设目标,触发 V4L2 重协商\n'
        '        # (部分 RealSense color 直接 set 目标会静默回退,如 video11)\n'
        '        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, image_width + 2)\n'
        '        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, image_width)\n'
    ), 1)
    n2h = '        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, image_height)\n'
    assert n2h in s, "patch②HEIGHT锚点未找到"
    s = s.replace(n2h, (
        '        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, image_height + 2)\n'
        '        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, image_height)\n'
    ), 1)

if s != orig:
    p.write_text(s); print("patched:", p)
else:
    print("无需改动:", p)
PY
python3 -c "import opencv_video_capture; print('import OK')"
