from __future__ import annotations
import os, sys
from typing import Any, List, Tuple

if __package__ in (None, ""):
    _HARDWARE_SENDER_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if _HARDWARE_SENDER_ROOT not in sys.path:
        sys.path.insert(0, _HARDWARE_SENDER_ROOT)
    from helpers.network_info.func.connection_quality_collector import (
        ConnectionQualityCollector,
    )
    from helpers.network_info.func.ip_collector import IpCollector
    from helpers.network_info.func.network_type_collector import NetworkTypeCollector
    from helpers.network_info.func.peer_connectivity_collector import PeerConnectivityCollector
else:
    from .func.connection_quality_collector import ConnectionQualityCollector
    from .func.ip_collector import IpCollector
    from .func.network_type_collector import NetworkTypeCollector
    from .func.peer_connectivity_collector import PeerConnectivityCollector


class NetworkInfo:
    network_type: str = ""
    my_ip: List[str] = []
    latency_ms: float = 0.0
    rssi_dbm: int = 0
    packet_loss_rate: float = 0.0
    jitter_ms: float = 0.0
    """对外统一入口：公网连接质量、对端 IP 连通性（实现细节见 ``func/``）。"""

    def __init__(self, sudo_password: str | None = None) -> None:
        self._sudo_password = sudo_password

    def get_network_type(self) -> str:
        """与公网通信的大致链路类型，如 ``wifi`` / ``cellular`` / ``ethernet`` / ``unknown``。"""
        self.network_type = NetworkTypeCollector.detect()
        return self.network_type

    def get_my_ip(self) -> List[str]:
        """硬件访问公网所经 IPv4 路径：公网出口 → 默认网关 → 本机地址（去重保序）。"""
        self.my_ip = IpCollector.collect_route()
        return self.my_ip

    def get_connection_info(self) -> Tuple[int, int, float, int]:
        """
        ``(latency_ms, rssi_dbm, packet_loss_rate, jitter_ms)``；
        RSSI 无读数时为 ``RSSI_NO_READING_DBM``（-95)
        """
        self.latency_ms, self.rssi_dbm, self.packet_loss_rate, self.jitter_ms = ConnectionQualityCollector.measure(
            sudo_password=self._sudo_password
        )
        if self.network_type == "ethernet":
            self.rssi_dbm = 0
        return self.latency_ms, self.rssi_dbm, self.packet_loss_rate, self.jitter_ms

    def probe_peers(
        self,
        peers: list[dict[str, str]],
        *,
        ping_count: int = 2,
        ping_timeout_sec: float = 2.0,
        max_peers_per_cycle: int = 0,
    ) -> dict[str, Any]:
        """探测机器人与配置对端 IP 设备之间的连通性（短 ICMP）。"""
        return PeerConnectivityCollector.probe_all(
            peers,
            ping_count=ping_count,
            ping_timeout_sec=ping_timeout_sec,
            max_peers_per_cycle=max_peers_per_cycle,
        )


def main() -> None:
    network_info = NetworkInfo()    
    print("get_network_type:", network_info.get_network_type())
    print("get_my_ip:", network_info.get_my_ip())
    latency_ms, rssi_dbm, packet_loss_rate, jitter_ms = network_info.get_connection_info()
    print(
        "get_connection_info:",
        {
            "latency_ms": latency_ms,
            "rssi_dbm": rssi_dbm,
            "packet_loss_rate": packet_loss_rate,
            "jitter_ms": jitter_ms,
        },
    )


if __name__ == "__main__":
    main()
