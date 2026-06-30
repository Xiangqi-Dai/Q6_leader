"""Sink node (runs on the follower host): receive the cross-machine counter and log it.

Also writes each received value to /tmp/sink_received.txt so we can confirm
delivery even if `dora logs` formatting differs.
"""
import dora


def main():
    node = dora.Node()
    with open("/tmp/sink_received.txt", "w") as f:
        f.write("started\n")
        f.flush()
        for event in node:
            if event["type"] != "INPUT":
                continue
            if event["id"] == "counter":
                val = event["value"][0].as_py()
                line = f"received counter={val}\n"
                print(f"[从臂收到跨机数据] {line}", flush=True)
                f.write(line)
                f.flush()
