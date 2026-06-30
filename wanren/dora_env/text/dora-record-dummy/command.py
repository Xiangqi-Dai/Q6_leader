"""Dummy command: auto-drive the recorder — send start at 2s, success at 8s."""
import dora
import time
import pyarrow as pa


def main():
    node = dora.Node()
    t0 = time.time()
    started = False
    for event in node:
        if event["type"] != "INPUT":
            continue
        if event["id"] != "tick":
            continue
        elapsed = time.time() - t0
        if not started and elapsed > 2:
            node.send_output(
                "command",
                pa.array(["start"]),
                {"episode_number": 0, "task_index": 0},
            )
            started = True
            print("[dummy-command] sent start", flush=True)
        elif started and elapsed > 8:
            node.send_output("command", pa.array(["success"]))
            print("[dummy-command] sent success", flush=True)
            break


if __name__ == "__main__":
    main()
