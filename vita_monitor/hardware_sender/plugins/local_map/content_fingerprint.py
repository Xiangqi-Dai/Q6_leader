from __future__ import annotations

import hashlib
import json
from typing import Any

_TRANSIENT_VITA_KEYS = frozenset({"error"})


def fingerprint_vita_data(vita_data: dict[str, Any]) -> str:
    """
    计算 local_map vita_data 的内容指纹，用于判断点云是否变化。

    剔除瞬时字段（如采集失败时的 error），不参与比对。
    map 内不含采集时间戳，points / frame_id / width / height 等均为有效内容。
    """
    comparable: dict[str, Any] = {}
    for key, value in vita_data.items():
        if key in _TRANSIENT_VITA_KEYS:
            continue
        comparable[key] = value
    payload = json.dumps(comparable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
