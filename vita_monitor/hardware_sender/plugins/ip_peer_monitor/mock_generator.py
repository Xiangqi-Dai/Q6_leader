from __future__ import annotations

import time
from typing import Any

from plugins.mock_utils import pick_int, rng_from_config


def generate_ip_peer_monitor_mock(
    mock_config: dict[str, Any],
    *,
    peers: list[dict[str, str]],
) -> dict[str, Any]:
    rng = rng_from_config(mock_config)
    offline_ips = {
        str(ip).strip()
        for ip in (mock_config.get("offline_ips") or [])
        if str(ip).strip()
    }
    peer_rows: list[dict[str, Any]] = []
    online_count = 0
    for peer in peers:
        ip = peer["ip"]
        online = ip not in offline_ips
        if online:
            online_count += 1
        latency = pick_int(rng, mock_config.get("latency_ms_range"), (1, 12)) if online else 0
        peer_rows.append(
            {
                "ip": ip,
                "name": peer.get("name", ip),
                "connected": online,
                "latency_ms": latency,
                "packet_loss_rate": 0.0 if online else 1.0,
                "error": "" if online else "unreachable",
            }
        )
    return {
        "status": "ok" if peer_rows else "error",
        "probed_at": time.time(),
        "peer_count": len(peer_rows),
        "online_count": online_count,
        "peers": peer_rows,
        "error": "" if peer_rows else "peers is empty",
    }
