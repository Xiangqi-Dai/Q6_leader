# Copyright 2026 Enactic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""dora-rs node that captures RGB frames from a real camera.

Supports Intel RealSense D435i and Orbbec Gemini 335Lg over V4L2 (UVC YUYV).
Only the color stream is used; depth / IR / metadata video nodes are skipped.
The camera is identified by USB port path (stable across reboots, unlike the
volatile /dev/videoN number, and works even when a RealSense has no USB serial).
"""

import argparse
import os
import subprocess
import time

import cv2
import dora
import numpy as np
import pyarrow as pa

YUYV = cv2.VideoWriter_fourcc("Y", "U", "Y", "V")


def find_color_node(device_path):
    """Locate the color (YUYV) video node on the given USB port path.

    Returns the /dev/videoN device string, or None if not found.
    """
    for n in range(32):
        dev = f"/dev/video{n}"
        info = subprocess.run(
            ["v4l2-ctl", "-d", dev, "--info", "--list-formats-ext"],
            capture_output=True,
            text=True,
        ).stdout
        if "YUYV" in info and device_path in info:
            return dev
    return None


def set_ctrl(dev, key, value):
    """Set a V4L2 control on the device."""
    subprocess.run(
        ["v4l2-ctl", "-d", dev, f"--set-ctrl={key}={value}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def match_bgr(frame, tb, tg, tr, iters=1):
    """Per-channel gain pulling the frame's mean B/G/R toward (tb, tg, tr).

    1 iteration is ~4x faster than 5 (47ms -> 12ms) to keep 30fps; the mean
    settles within a few units (highlight clipping blocks exact convergence).
    """
    f = frame.astype(np.float32)
    for _ in range(iters):
        b, g, r = f.reshape(-1, 3).mean(0)
        f[:, :, 0] *= tb / b
        f[:, :, 1] *= tg / g
        f[:, :, 2] *= tr / r
    return np.clip(f, 0, 255).astype(np.uint8)


def main():
    """Run the real camera dora node."""
    parser = argparse.ArgumentParser(description="Real camera node for OpenArm data collection")
    parser.add_argument(
        "--device-path",
        default=os.getenv("DEVICE_PATH", ""),
        help="USB port path, e.g. usb-xhci-hcd.10.auto-1.2",
        type=str,
    )
    parser.add_argument(
        "--camera-type",
        default=os.getenv("CAMERA_TYPE", "realsense"),
        choices=["realsense", "orbbec"],
        help="Camera type.",
        type=str,
    )
    parser.add_argument(
        "--image-width",
        default=int(os.getenv("IMAGE_WIDTH", 1280)),
        help="The width of the image output. Default is 1280.",
        type=int,
    )
    parser.add_argument(
        "--image-height",
        default=int(os.getenv("IMAGE_HEIGHT", 720)),
        help="The height of the image output. Default is 720.",
        type=int,
    )
    parser.add_argument(
        "--encoding",
        default=os.getenv("ENCODING", "jpeg"),
        help="The encoding.",
        type=str,
    )
    parser.add_argument(
        "--jpeg-quality",
        default=int(os.getenv("JPEG_QUALITY", 90)),
        help="The JPEG quality. (0-100) Default is 90.",
        type=int,
    )
    parser.add_argument(
        "--wb-kelvin",
        default=int(os.getenv("WB_KELVIN", 5400)),
        help="RealSense manual white-balance color temperature. Default is 5400.",
        type=int,
    )
    parser.add_argument(
        "--target-bgr",
        default=os.getenv("TARGET_BGR", ""),
        help="Optional 'B,G,R' (e.g. '108,108,105') for per-channel gain alignment.",
        type=str,
    )
    parser.add_argument(
        "--exposure",
        default=int(os.getenv("EXPOSURE", "0")),
        help="RealSense manual exposure in 100us units (e.g. 300=30ms). 0 = auto.",
        type=int,
    )
    args = parser.parse_args()

    dev = find_color_node(args.device_path)
    if not dev:
        raise SystemExit(
            f"[FAIL] no color (YUYV) node found on USB port {args.device_path!r}"
        )
    print(f"[camera] {args.camera_type} @ {args.device_path} -> {dev}")

    # RealSense: set V4L2 controls BEFORE opening cap. cap holds an exclusive
    # V4L2 capture handle, so v4l2-ctl --set-ctrl called after cap open fails
    # silently (device busy) and EXPOSURE / WB never take effect.
    if args.camera_type == "realsense":
        if args.exposure > 0:
            set_ctrl(dev, "auto_exposure", 1)             # manual mode
            set_ctrl(dev, "exposure_dynamic_framerate", 0)
            set_ctrl(dev, "exposure_time_absolute", args.exposure)
        else:
            set_ctrl(dev, "auto_exposure", 3)             # auto mode
        if args.wb_kelvin > 0:
            set_ctrl(dev, "white_balance_automatic", 0)
            set_ctrl(dev, "white_balance_temperature", args.wb_kelvin)
        else:
            set_ctrl(dev, "white_balance_automatic", 1)   # auto white balance

    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit(f"[FAIL] cannot open {dev}")
    cap.set(cv2.CAP_PROP_FOURCC, YUYV)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.image_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.image_height)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    # Warm up: let auto exposure / white balance settle and drain the buffer.
    t0 = time.time()
    while time.time() - t0 < 1.5:
        cap.read()

    # Background grab thread: continuously read to keep the latest frame.
    # The main loop reads `latest` non-blockingly on each tick, so a blocking
    # cap.read() can't stall the 30Hz tick (otherwise drops to ~20fps).
    import threading
    latest = {"frame": None}

    def _grab_loop():
        while True:
            ret, f = cap.read()
            if ret:
                latest["frame"] = f

    threading.Thread(target=_grab_loop, daemon=True).start()
    time.sleep(0.5)  # let the first frame arrive

    target = None
    if args.target_bgr:
        target = tuple(int(x) for x in args.target_bgr.split(","))

    node = dora.Node()
    for event in node:
        if event["type"] != "INPUT":
            continue

        frame = latest["frame"]
        if frame is None:
            continue
        if target is not None:
            frame = match_bgr(frame, *target)

        metadata = event["metadata"]
        metadata["encoding"] = args.encoding
        metadata["width"] = args.image_width
        metadata["height"] = args.image_height

        if args.encoding == "rgb8":
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            payload = pa.array(image.ravel())
        elif args.encoding == "yuv420":
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            payload = pa.array(image.ravel())
        else:
            enc = "jpeg" if args.encoding in ("jpeg", "jpg", "jpe") else args.encoding
            params = (
                [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality]
                if enc in ("jpeg", "jpg", "jpe")
                else []
            )
            success, image = cv2.imencode("." + enc, frame, params)
            if not success:
                print("Failed to encode image")
                continue
            payload = pa.array(image.ravel())

        node.send_output("image", payload, metadata)

    cap.release()


if __name__ == "__main__":
    main()
