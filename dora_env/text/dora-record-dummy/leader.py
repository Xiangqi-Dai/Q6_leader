"""Dummy leader: emit fake joint positions (= action) for the recording smoke test."""
import dora
import numpy as np
import pyarrow as pa

POS = np.zeros(8, dtype=np.float32)  # 8 关节假角度


def main():
    node = dora.Node()
    for event in node:
        if event["type"] != "INPUT":
            continue
        if event["id"] == "tick":
            node.send_output("position_left", pa.array(POS, type=pa.float32()))
            node.send_output("position_right", pa.array(POS, type=pa.float32()))


if __name__ == "__main__":
    main()
