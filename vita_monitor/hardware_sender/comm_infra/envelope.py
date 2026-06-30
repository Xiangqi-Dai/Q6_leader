"""
通信外层数据格式（与 Roadmap / 架构文档一致）。
所有经 MQTT 传输的业务载荷均为 UTF-8 JSON 字符串，结构如下：
{
  "device_id": str,
  "timestamp": float|int,  # Unix 秒或毫秒，由发送端约定；此处使用秒（time.time()）
  "vita_type": str,        # 体征唯一标识，如 heartbeat / temperature / demo_vital
  "data_mode": str,        # real | mock；采集模式，由 Infra 根据 config 注入（见 docs/user_docs/05）
  "vita_data": object      # 业务 dict；不含 data_mode
}
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

VALID_DATA_MODES = frozenset({"real", "mock", "simulated"})
_SCHEMA_KEYS = frozenset({"device_id", "timestamp", "vita_type", "data_mode", "vita_data"})


def normalize_data_mode(value: Any, *, default: str = "real") -> str:
    if value is None:
        return default
    mode = str(value).strip().lower()
    if mode not in VALID_DATA_MODES:
        raise ValueError(f"data_mode must be one of {sorted(VALID_DATA_MODES)}, got {value!r}")
    return mode


def sanitize_vita_data(vita_data: dict[str, Any]) -> dict[str, Any]:
    """Strip infra field if a plugin mistakenly included it in business payload."""
    out = dict(vita_data)
    if "data_mode" in out:
        logger.debug("stripped data_mode from vita_data before envelope build")
        out.pop("data_mode", None)
    return out


def build_envelope(
    *,
    device_id: str,
    vita_type: str,
    vita_data: dict[str, Any],
    data_mode: str = "real",
) -> str:
    payload = {
        "device_id": device_id,
        "timestamp": time.time(),
        "vita_type": vita_type,
        "data_mode": normalize_data_mode(data_mode),
        "vita_data": sanitize_vita_data(vita_data),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_envelope(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("envelope must be a JSON object")

    missing = _SCHEMA_KEYS - obj.keys()
    if missing:
        # 兼容旧发送端：缺 data_mode 时视为 real
        if missing == {"data_mode"}:
            obj["data_mode"] = "real"
            logger.debug("envelope missing data_mode, defaulting to real")
        else:
            raise ValueError(f"envelope missing keys: {sorted(missing)}")

    obj["data_mode"] = normalize_data_mode(obj.get("data_mode"), default="real")
    vita_data = obj.get("vita_data")
    if isinstance(vita_data, dict):
        obj["vita_data"] = sanitize_vita_data(vita_data)
    return obj


def topic_for_vital(device_id: str, vita_type: str) -> str:
    """
    Topic 规则（见 docs/00_Architecture_整体架构.md）：
    - life -> robot/{id}/vitals/life
    - state -> robot/{id}/vitals/state
    - 其余（含扩展体征、demo_vital）-> robot/{id}/vitals/{vita_type}
    """
    return f"robot/{device_id}/vitals/{vita_type}"
