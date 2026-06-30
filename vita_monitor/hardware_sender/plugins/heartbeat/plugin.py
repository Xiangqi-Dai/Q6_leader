from __future__ import annotations

from typing import Any

from plugins.plugin_base import BaseVitalPlugin

from helpers.network_info import NetworkInfo
from helpers.network_info.func.connection_quality_collector import (
    ICMP_COMPLETE_FAILURE_JITTER_MS,
    ICMP_COMPLETE_FAILURE_LATENCY_MS,
    RSSI_NO_READING_DBM,
)


class HeartbeatVitalPlugin(BaseVitalPlugin):
    vita_type = "heartbeat"
    vita_data_schema: dict[str, Any] = {
        "status": "str",
        "network_type": "str",
        "latency_ms": "int",
        "rssi_dbm": "int",
        "packet_loss_rate": "float",
        "jitter_ms": "int",
        "IP_address": "list[str]",
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        sudo_password = kwargs.get("sudo_password")
        self.net_info: NetworkInfo = NetworkInfo(sudo_password=sudo_password)
        self._last_payload: dict[str, Any] = {
            "status": "online",
            "network_type": "unknown",
            "latency_ms": ICMP_COMPLETE_FAILURE_LATENCY_MS,
            "rssi_dbm": RSSI_NO_READING_DBM,
            "packet_loss_rate": 1.0,
            "jitter_ms": ICMP_COMPLETE_FAILURE_JITTER_MS,
            "IP_address": [],
        }

    def collect_real_vita_data(self) -> dict[str, Any]:
        """各字段独立采集：失败字段写入断联哨兵，仍每次上报，不整包吞掉。"""
        out: dict[str, Any] = {
            "status": "online",
            "network_type": "unknown",
            "latency_ms": ICMP_COMPLETE_FAILURE_LATENCY_MS,
            "rssi_dbm": RSSI_NO_READING_DBM,
            "packet_loss_rate": 1.0,
            "jitter_ms": ICMP_COMPLETE_FAILURE_JITTER_MS,
            "IP_address": [],
        }
        try:
            out["network_type"] = self.net_info.get_network_type()
        except Exception:
            pass
        try:
            out["IP_address"] = list(self.net_info.get_my_ip())
        except Exception:
            pass
        try:
            latency_ms, rssi_dbm, packet_loss_rate, jitter_ms = self.net_info.get_connection_info()
            out["latency_ms"] = int(latency_ms)
            out["rssi_dbm"] = int(rssi_dbm)
            out["packet_loss_rate"] = float(packet_loss_rate)
            out["jitter_ms"] = int(jitter_ms)
        except Exception:
            pass
        self._last_payload = out
        return dict(out)

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.heartbeat.mock_generator import generate_heartbeat_mock

        out = generate_heartbeat_mock(self.mock_config)
        self._last_payload = out
        return dict(out)
