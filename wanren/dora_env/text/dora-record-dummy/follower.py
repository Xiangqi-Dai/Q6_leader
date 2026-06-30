"""Dummy follower: emit fake joint state (= observation) for the recording smoke test."""
import dora
import numpy as np
import pyarrow as pa

Z = np.zeros(8, dtype=np.float32)


def state():
    return pa.StructArray.from_arrays(
        [pa.array(Z, type=pa.float32()) for _ in range(3)],
        names=["qpos", "qvel", "qtorque"],
    )


def main():
    node = dora.Node()
    for event in node:
        if event["type"] != "INPUT":
            continue
        if event["id"] == "tick":
            node.send_output("state_left", state())
            node.send_output("state_right", state())


if __name__ == "__main__":
    main()
