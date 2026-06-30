from __future__ import annotations

from typing import Any

from helpers.network_info import NetworkInfo
from plugins.plugin_base import BaseVitalPlugin


class IpPeerMonitorVitalPlugin(BaseVitalPlugin):
    vita_type = "ip_peer_monitor"
    vita_data_schema: dict[str, Any] = {
        "status": "str",
        "probed_at": "float",
        "peer_count": "int",
        "online_count": "int",
        "peers": "list[object]",
        "error": "str",
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        self._net_info = NetworkInfo()
        self._peers = self._parse_peers(kwargs.get("peers"))
        self._ping_count = max(1, min(4, int(kwargs.get("ping_count", 2))))
        self._ping_timeout_sec = float(kwargs.get("ping_timeout_sec", 2.0))
        self._max_peers_per_cycle = int(kwargs.get("max_peers_per_cycle", 0))
        self._last_payload: dict[str, Any] = self._empty_payload("no data yet")

    @staticmethod
    def _parse_peers(raw: Any) -> list[dict[str, str]]:
        if not isinstance(raw, list):
            return []
        out: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip", "")).strip()
            if not ip:
                continue
            name = str(item.get("name", "")).strip() or ip
            out.append({"ip": ip, "name": name})
        return out

    @staticmethod
    def _empty_payload(error: str) -> dict[str, Any]:
        return {
            "status": "error",
            "probed_at": 0.0,
            "peer_count": 0,
            "online_count": 0,
            "peers": [],
            "error": error,
        }

    def collect_real_vita_data(self) -> dict[str, Any]:
        if not self._peers:
            out = self._empty_payload("peers is empty")
            self._last_payload = out
            return dict(out)
        try:
            result = self._net_info.probe_peers(
                self._peers,
                ping_count=self._ping_count,
                ping_timeout_sec=self._ping_timeout_sec,
                max_peers_per_cycle=self._max_peers_per_cycle,
            )
            out = {
                "status": str(result.get("status", "error")),
                "probed_at": float(result.get("probed_at", 0.0)),
                "peer_count": int(result.get("peer_count", 0)),
                "online_count": int(result.get("online_count", 0)),
                "peers": list(result.get("peers", [])),
                "error": str(result.get("error", "")),
            }
            self._last_payload = out
            return dict(out)
        except Exception as exc:
            out = dict(self._last_payload)
            out["status"] = "error"
            out["error"] = str(exc)[:120]
            return out

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.ip_peer_monitor.mock_generator import generate_ip_peer_monitor_mock

        out = generate_ip_peer_monitor_mock(self.mock_config, peers=self._peers)
        self._last_payload = out
        return dict(out)
