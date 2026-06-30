"""Camera FPS probe: counts frames received per camera each second.

Subscribes to camera_* image streams and a 1Hz tick; on each tick it reports
each camera's measured frame rate over the elapsed interval.
"""

import dora
import time


def main():
    node = dora.Node()
    counts = {}
    last_report = time.time()
    for event in node:
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        if eid.startswith("camera_"):
            counts[eid] = counts.get(eid, 0) + 1
        elif eid == "tick":
            now = time.time()
            dt = now - last_report
            if dt >= 1.0:
                line = " | ".join(
                    f"{k.replace('camera_', '')}={v / dt:.1f}fps"
                    for k, v in sorted(counts.items())
                )
                print(f"[fps] {line}", flush=True)
                counts.clear()
                last_report = now


if __name__ == "__main__":
    main()
