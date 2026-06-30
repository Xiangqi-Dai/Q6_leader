from __future__ import annotations

import platform
import re
from typing import List, Optional, Tuple

from .command_runner import CommandRunner
from .icmp_probe import (
    ICMP_COMPLETE_FAILURE_JITTER_MS,
    ICMP_COMPLETE_FAILURE_LATENCY_MS,
    IcmpProbe,
)

# 与 docs/plugins/1. heartbeat.md 约定一致：无读数时的断联哨兵
RSSI_NO_READING_DBM = -95

__all__ = [
    "RSSI_NO_READING_DBM",
    "ICMP_COMPLETE_FAILURE_LATENCY_MS",
    "ICMP_COMPLETE_FAILURE_JITTER_MS",
    "ConnectionQualityCollector",
]


class ConnectionQualityCollector:
    """公网 ICMP 与无线接口信息估计延迟、抖动、丢包与 RSSI。"""

    _PING_TARGETS = ("8.8.8.8", "1.1.1.1")

    @staticmethod
    def measure(sudo_password: Optional[str] = None) -> Tuple[float, int, float, float]:
        latency_ms, loss, jitter_ms = ConnectionQualityCollector._measure_icmp()
        rssi = ConnectionQualityCollector._measure_rssi_dbm(sudo_password=sudo_password)
        return latency_ms, rssi, loss, jitter_ms

    @staticmethod
    def _measure_icmp() -> Tuple[float, float, float]:
        for host in ConnectionQualityCollector._PING_TARGETS:
            lat, loss, jit, ok = IcmpProbe.measure(host, ping_count=3, ping_timeout_sec=2.0)
            if ok or loss > 0.0:
                return float(round(lat or 0.0)), float(loss), float(round(jit or 0.0))
        return ICMP_COMPLETE_FAILURE_LATENCY_MS, 1.0, ICMP_COMPLETE_FAILURE_JITTER_MS

    @staticmethod
    def _measure_rssi_dbm(sudo_password: Optional[str] = None) -> int:
        system = platform.system().lower()
        if system == "windows":
            v = ConnectionQualityCollector._rssi_windows_netsh()
            if v is not None:
                return v
        if system == "linux":
            v2 = ConnectionQualityCollector._rssi_linux_iw(sudo_password=sudo_password)
            if v2 is not None:
                return v2
            v3 = ConnectionQualityCollector._rssi_linux_nmcli()
            if v3 is not None:
                return v3
        v4 = ConnectionQualityCollector._rssi_mmcli()
        if v4 is not None:
            return v4
        return RSSI_NO_READING_DBM

    @staticmethod
    def _rssi_windows_netsh() -> Optional[int]:
        out, code = CommandRunner.run(["netsh", "wlan", "show", "interfaces"])
        if code != 0 or not out:
            return None
        m_dbm = re.search(r"RSSI\s*[:：]\s*(-?\d+)\s*dBm", out, flags=re.IGNORECASE)
        if m_dbm:
            return int(m_dbm.group(1))
        m_sig = re.search(
            r"(?:Signal|信号|Señal|Senal|Signál|Signale|Qualité|Qualit[eé])\s*[:：]\s*(\d+)\s*%",
            out,
            flags=re.IGNORECASE,
        )
        if m_sig:
            pct = int(m_sig.group(1))
            return int(round(-100.0 + (pct / 100.0) * 50.0))
        return None

    @staticmethod
    def _rssi_linux_iw(sudo_password: Optional[str] = None) -> Optional[int]:
        out, code = CommandRunner.run(["iw", "dev"], sudo_password=sudo_password)
        if code != 0 or not out:
            return None
        ifaces: List[str] = []
        for line in out.splitlines():
            m = re.match(r"\s*Interface\s+(\S+)", line, flags=re.IGNORECASE)
            if m:
                ifaces.append(m.group(1))
        not_connected = (
            "not connected",
            "no station",
            "未连接",
            "未連接",
            "no client",
        )
        for ifn in ifaces:
            link, c = CommandRunner.run(["iw", "dev", ifn, "link"], sudo_password=sudo_password)
            if c != 0 or not link:
                continue
            low = link.lower()
            if any(x in low for x in not_connected):
                continue
            m = re.search(r"signal:\s*(-?\d+)\s*dBm", link, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _rssi_linux_nmcli() -> Optional[int]:
        out, code = CommandRunner.run(["nmcli", "-t", "-f", "ACTIVE,DEV,TYPE", "device", "status"])
        if code != 0 or not out:
            return None
        wifi_dev: Optional[str] = None
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "yes" and "wifi" in parts[2].lower():
                wifi_dev = parts[1]
                break
        if not wifi_dev:
            return None
        out2, code2 = CommandRunner.run(["nmcli", "-f", "WIFI.SIGNAL", "device", "show", wifi_dev])
        if code2 != 0 or not out2:
            return None
        m = re.search(r"WIFI\.SIGNAL\s+(\d+)", out2)
        if not m:
            return None
        pct = int(m.group(1))
        return int(round(-100.0 + (pct / 100.0) * 50.0))

    @staticmethod
    def _rssi_mmcli() -> Optional[int]:
        out, code = CommandRunner.run(["mmcli", "-m", "0"], timeout=6.0)
        if code != 0 or not out:
            return None
        m = re.search(r"signal\s+quality:\s*(\d+)\s*%", out, flags=re.IGNORECASE)
        if m:
            pct = int(m.group(1))
            return int(round(-100.0 + (pct / 100.0) * 50.0))
        return None
