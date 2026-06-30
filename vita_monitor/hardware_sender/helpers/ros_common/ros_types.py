from __future__ import annotations

import importlib


def import_message_class(ros_type: str) -> type:
    parts = ros_type.strip().split("/")
    if len(parts) != 3 or parts[1] != "msg":
        raise ValueError(f"ros message type must be pkg/msg/Name, got {ros_type!r}")
    pkg, _, name = parts
    mod = importlib.import_module(f"{pkg}.msg")
    cls = getattr(mod, name, None)
    if cls is None:
        raise ImportError(f"message class {name!r} not in {pkg}.msg")
    return cls
