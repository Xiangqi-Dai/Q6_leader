"""Generator node (runs on the leader host): emit an incrementing counter on each tick."""
import dora
import pyarrow as pa


def main():
    node = dora.Node()
    i = 0
    for event in node:
        if event["type"] != "INPUT":
            continue
        if event["id"] == "tick":
            i += 1
            node.send_output("counter", pa.array([i], type=pa.int32()))
