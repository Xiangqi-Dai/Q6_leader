from __future__ import annotations

import json
import platform
import re
import socket
import urllib.error
import urllib.request
from typing import List, Optional

from .command_runner import CommandRunner


class IpCollector:
    """公网 → 默认网关 → 本机 IPv4 路径采集（Windows / Linux）。"""

    _PUBLIC_IP_URLS = (
        "https://api.ipify.org?format=json",
        "https://api64.ipify.org?format=json",
    )
    _PUBLIC_FETCH_TIMEOUT_S = 4.0

    @staticmethod
    def collect_route() -> List[str]:
        ordered: List[str] = []
        pub = IpCollector._get_public_ip()
        if pub:
            ordered.append(pub)
        gw = IpCollector._get_default_gateway()
        if gw and gw not in ordered:
            ordered.append(gw)
        for lip in IpCollector._get_local_ipv4s():
            if lip not in ordered:
                ordered.append(lip)
        return ordered

    @staticmethod
    def _get_public_ip() -> Optional[str]:
        for url in IpCollector._PUBLIC_IP_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ip_collector/1.0"})
                with urllib.request.urlopen(req, timeout=IpCollector._PUBLIC_FETCH_TIMEOUT_S) as resp:
                    raw = resp.read().decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                if raw.startswith("{"):
                    data = json.loads(raw)
                    ip = data.get("ip")
                    if isinstance(ip, str) and IpCollector._is_ipv4(ip):
                        return ip
                elif IpCollector._is_ipv4(raw):
                    return raw
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
                continue
        return None

    @staticmethod
    def _get_default_gateway() -> Optional[str]:
        system = platform.system().lower()
        if system == "windows":
            return IpCollector._gateway_windows()
        if system == "linux":
            return IpCollector._gateway_linux()
        return None

    @staticmethod
    def _gateway_linux() -> Optional[str]:
        out, code = CommandRunner.run(["ip", "-4", "route", "show", "default"])
        if code == 0 and out:
            m = re.search(r"\bdefault\b.*\bvia\s+(\d{1,3}(?:\.\d{1,3}){3})\b", out)
            if m:
                ip = m.group(1)
                if IpCollector._is_ipv4(ip):
                    return ip
        out2, code2 = CommandRunner.run(["route", "-n"])
        if code2 == 0 and out2:
            for line in out2.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "0.0.0.0" and parts[1] != "0.0.0.0":
                    if IpCollector._is_ipv4(parts[1]):
                        return parts[1]
        return None

    @staticmethod
    def _windows_colon_value(line: str) -> Optional[str]:
        for sep in (":", "："):
            idx = line.rfind(sep)
            if idx != -1:
                return line[idx + 1 :].strip()
        return None

    @staticmethod
    def _is_default_gateway_line(low: str, raw: str) -> bool:
        if raw.strip().startswith("默认网关"):
            return True
        prefixes = (
            "default gateway",
            "default gateways",
            "standardgateway",
            "standardgateways",
            "passerelle par défaut",
            "passerelle par defaut",
            "puerta de enlace predeterminada",
            "gateway di default",
            "gateway predefinito",
            "predvolená brána",
        )
        return any(low.startswith(p) for p in prefixes)

    @staticmethod
    def _is_ipv4_address_line(low: str, raw: str) -> bool:
        if raw.strip().startswith("IPv4 地址"):
            return True
        prefixes = (
            "ipv4 address",
            "ipv4-adresse",
            "adresse ipv4",
            "indirizzo ipv4",
            "dirección ipv4",
            "direccion ipv4",
            "endereço ipv4",
            "endereco ipv4",
        )
        return any(low.startswith(p) for p in prefixes)

    @staticmethod
    def _gateway_windows() -> Optional[str]:
        out, code = CommandRunner.run(["ipconfig"])
        if code == 0 and out:
            last: Optional[str] = None
            for raw_line in out.splitlines():
                line = raw_line.strip()
                low = line.lower()
                if not IpCollector._is_default_gateway_line(low, raw_line):
                    continue
                val = IpCollector._windows_colon_value(line)
                if not val:
                    continue
                if not val:
                    continue
                for token in re.split(r"[;\s,]+", val):
                    token = token.strip()
                    if IpCollector._is_ipv4(token):
                        last = token
            if last:
                return last
        out2, code2 = CommandRunner.run(["route", "print", "0.0.0.0"])
        if code2 != 0 or not out2:
            return None
        for raw in out2.splitlines():
            line = raw.strip()
            if not line or line.startswith("====") or line.startswith("Active") or line.startswith("接口") or line.startswith("If "):
                continue
            if line.lower().startswith("network destination"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            if parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                gw = parts[2]
                if gw != "On-link" and IpCollector._is_ipv4(gw):
                    return gw
        return None

    @staticmethod
    def _get_local_ipv4s() -> List[str]:
        system = platform.system().lower()
        ips: List[str] = []
        if system == "windows":
            ips.extend(IpCollector._local_ipv4s_windows())
        elif system == "linux":
            ips.extend(IpCollector._local_ipv4s_linux())
        else:
            ips.extend(IpCollector._local_ipv4s_socket_probe())
        dedup: List[str] = []
        for ip in ips:
            if ip not in dedup:
                dedup.append(ip)
        return dedup

    @staticmethod
    def _local_ipv4s_linux() -> List[str]:
        out, code = CommandRunner.run(["hostname", "-I"])
        if code == 0 and out:
            found: List[str] = []
            for tok in out.split():
                if IpCollector._is_ipv4(tok) and not IpCollector._is_loopback(tok):
                    found.append(tok)
            if found:
                return found
        out2, code2 = CommandRunner.run(["ip", "-4", "-o", "addr", "show", "scope", "global"])
        if code2 == 0 and out2:
            found2: List[str] = []
            for line in out2.splitlines():
                for m in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})/\d+\b", line):
                    ip = m.group(1)
                    if IpCollector._is_ipv4(ip) and not IpCollector._is_loopback(ip):
                        found2.append(ip)
            if found2:
                return found2
        return IpCollector._local_ipv4s_socket_probe()

    @staticmethod
    def _local_ipv4s_windows() -> List[str]:
        out, code = CommandRunner.run(["ipconfig"])
        if code != 0 or not out:
            return IpCollector._local_ipv4s_socket_probe()
        found: List[str] = []
        for line in out.splitlines():
            s = line.strip()
            low = s.lower()
            if not IpCollector._is_ipv4_address_line(low, line):
                continue
            val = IpCollector._windows_colon_value(s)
            if not val:
                continue
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", val)
            if not m:
                continue
            ip = m.group(1)
            if IpCollector._is_ipv4(ip) and not IpCollector._is_loopback(ip):
                found.append(ip)
        return found if found else IpCollector._local_ipv4s_socket_probe()

    @staticmethod
    def _local_ipv4s_socket_probe() -> List[str]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
        except OSError:
            return []
        if IpCollector._is_ipv4(ip) and not IpCollector._is_loopback(ip):
            return [ip]
        return []

    @staticmethod
    def _is_ipv4(s: str) -> bool:
        parts = s.split(".")
        if len(parts) != 4:
            return False
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return False
        return all(0 <= n <= 255 for n in nums)

    @staticmethod
    def _is_loopback(ip: str) -> bool:
        return ip.startswith("127.")
