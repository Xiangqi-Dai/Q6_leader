from __future__ import annotations

import time
from typing import Any

from plugins.mock_utils import pick_float, pick_int, rng_from_config


def generate_heartbeat_mock(mock_config: dict[str, Any]) -> dict[str, Any]:
    rng = rng_from_config(mock_config)
    network_type = str(mock_config.get("network_type", "wifi"))
    return {
        "status": "online",
        "network_type": network_type,
        "latency_ms": pick_int(rng, mock_config.get("latency_ms_range"), (25, 80)),
        "rssi_dbm": pick_int(rng, mock_config.get("rssi_dbm_range"), (-68, -42)),
        "packet_loss_rate": round(pick_float(rng, mock_config.get("packet_loss_rate_range"), (0.0, 0.05)), 3),
        "jitter_ms": pick_int(rng, mock_config.get("jitter_ms_range"), (4, 18)),
        "IP_address": list(mock_config.get("ip_addresses") or ["192.168.1.100", "10.0.0.12"]),
    }
