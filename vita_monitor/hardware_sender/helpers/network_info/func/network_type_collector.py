from __future__ import annotations

import platform
import re
from typing import Optional

from .command_runner import CommandRunner


class NetworkTypeCollector:
    """根据默认出网接口判断与公网通信的大致链路类型（Wi‑Fi / 蜂窝 / 有线）。"""

    @staticmethod
    def detect() -> str:
        system = platform.system().lower()
        if system == "windows":
            alias = NetworkTypeCollector._windows_default_interface_alias()
            t = NetworkTypeCollector._classify_from_alias(alias)
            if t != "unknown":
                return t
        if system in ("linux", "darwin"):
            iface = NetworkTypeCollector._unix_egress_iface()
            t = NetworkTypeCollector._classify_from_iface_name(iface)
            if t != "unknown":
                return t
        if system == "windows":
            iface2 = NetworkTypeCollector._windows_egress_iface_from_route_print()
            return NetworkTypeCollector._classify_from_iface_name(iface2)
        return "unknown"

    @staticmethod
    def _windows_default_interface_alias() -> Optional[str]:
        ps = (
            "Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1 -ExpandProperty InterfaceAlias"
        )
        out, code = CommandRunner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            timeout=12.0,
        )
        if code != 0 or not out:
            return None
        line = out.strip().splitlines()[-1].strip()
        return line or None

    @staticmethod
    def _windows_egress_iface_from_route_print() -> Optional[str]:
        out, code = CommandRunner.run(["route", "print", "-4"])
        if code != 0 or not out:
            return None
        in_ipv4 = False
        for raw in out.splitlines():
            line = raw.strip()
            if any(
                m in line
                for m in (
                    "IPv4 Route Table",
                    "IPv4 路由表",
                    "IPv4-Routentabelle",
                    "Tabela de Rotas IPv4",
                    "Table de routage IPv4",
                    "Tabla de rutas IPv4",
                )
            ):
                in_ipv4 = True
                continue
            if in_ipv4 and ("====" in line or line.startswith("Active")):
                continue
            if in_ipv4 and (
                line.lower().startswith("network destination")
                or line.startswith("Netzwerkziel")
                or line.startswith("Destino de red")
                or line.startswith("Destinazione rete")
            ):
                continue
            if not in_ipv4:
                continue
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                return parts[3]
        return None

    @staticmethod
    def _unix_egress_iface() -> Optional[str]:
        out, code = CommandRunner.run(["ip", "route", "get", "8.8.8.8"])
        if code == 0 and out:
            m = re.search(r"\bdev\s+(\S+)", out)
            if m:
                return m.group(1).strip()
        if platform.system().lower() == "darwin":
            out2, code2 = CommandRunner.run(["route", "-n", "get", "8.8.8.8"])
            if code2 == 0 and out2:
                m2 = re.search(r"interface:\s*(\S+)", out2, flags=re.IGNORECASE)
                if m2:
                    return m2.group(1).strip()
        return None

    @staticmethod
    def _classify_from_alias(alias: Optional[str]) -> str:
        if not alias:
            return "unknown"
        low = alias.lower()
        if any(k in low for k in ("wi-fi", "wifi", "wlan", "wireless", "802.11")):
            return "wifi"
        if any(k in low for k in ("cellular", "mobile broadband", "lte", "5g", "wwan")):
            return "cellular"
        if "ethernet" in low or low.startswith("eth") or "以太网" in alias:
            return "ethernet"
        if "vpn" in low or "tap" in low or "tun" in low:
            return "unknown"
        return "unknown"

    @staticmethod
    def _classify_from_iface_name(iface: Optional[str]) -> str:
        if not iface:
            return "unknown"
        low = iface.lower()
        if low.startswith(("wlan", "wl", "wifi")):
            return "wifi"
        if any(low.startswith(p) for p in ("wwan", "rmnet", "ppp", "usb", "cdc", "ww")):
            return "cellular"
        if low.startswith(("eth", "en", "eno", "ens", "enp", "enx", "bridge", "br")):
            return "ethernet"
        if "vpn" in low or low.startswith(("tun", "tap")):
            return "unknown"
        return "unknown"
