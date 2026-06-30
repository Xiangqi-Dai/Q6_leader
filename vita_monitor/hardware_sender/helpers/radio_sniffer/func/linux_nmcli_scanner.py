from __future__ import annotations

import re
import time
from typing import List, Optional

from helpers.network_info.func.command_runner import CommandRunner

from .linux_iw_scanner import ScannedNetwork
from ..channel_occupancy import band_for_channel

_NMCLI_LINE_RE = re.compile(
    r"^(?P<ssid>(?:\\.|[^:])*):"
    r"(?P<bssid>(?:[0-9a-fA-F]{2}\\?:){5}[0-9a-fA-F]{2}):"
    r"(?P<signal>[^:]+):"
    r"(?P<chan>\d+|--):"
    r"(?P<security>.+)$"
)


class LinuxNmcliScanner:
    """NetworkManager：`nmcli device wifi rescan` + `device wifi list`。"""

    def __init__(self, sudo_password: Optional[str] = None) -> None:
        self._sudo_password = sudo_password

    def list_wifi_devices(self) -> List[str]:
        out, code = CommandRunner.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            timeout=6.0,
            sudo_password=self._sudo_password,
        )
        if code != 0 or not out:
            return []
        devs: List[str] = []
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1].strip().lower() == "wifi":
                devs.append(parts[0].strip())
        return devs

    def scan(self, device: Optional[str] = None) -> tuple[List[ScannedNetwork], str]:
        wifi_devs = self.list_wifi_devices()
        iface = device or (wifi_devs[0] if wifi_devs else "")
        if iface:
            CommandRunner.run(
                ["nmcli", "device", "wifi", "rescan", "ifname", iface],
                timeout=12.0,
                sudo_password=self._sudo_password,
            )
        else:
            CommandRunner.run(
                ["nmcli", "device", "wifi", "rescan"],
                timeout=12.0,
                sudo_password=self._sudo_password,
            )
        time.sleep(3.0)

        out, code = CommandRunner.run(
            [
                "nmcli",
                "-t",
                "-f",
                "SSID,BSSID,SIGNAL,CHAN,SECURITY",
                "device",
                "wifi",
                "list",
            ],
            timeout=15.0,
            sudo_password=self._sudo_password,
        )
        if code != 0 or not out.strip():
            return [], iface

        return self._parse_list(out), iface

    @staticmethod
    def _rssi_to_percent(rssi_dbm: int) -> int:
        pct = int(round((rssi_dbm + 100) * 2))
        return max(0, min(100, pct))

    @staticmethod
    def _signal_to_rssi(signal_raw: str) -> int:
        s = signal_raw.strip()
        if not s or s == "--":
            return -95
        if s.endswith("%"):
            try:
                pct = int(s.replace("%", "").strip())
                return int(round(-100 + pct * 0.5))
            except ValueError:
                return -95
        try:
            return int(round(float(s)))
        except ValueError:
            return -95

    def _parse_list(self, text: str) -> List[ScannedNetwork]:
        networks: List[ScannedNetwork] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _NMCLI_LINE_RE.match(line)
            if not m:
                continue
            ssid = m.group("ssid").replace("\\:", ":").strip()
            bssid = m.group("bssid").replace("\\:", ":").strip().lower()
            signal_s = m.group("signal").strip()
            chan_s = m.group("chan").strip()
            security = m.group("security").strip()

            if not bssid or bssid == "--":
                continue
            try:
                channel = int(chan_s) if chan_s and chan_s != "--" else 1
            except ValueError:
                channel = 1
            rssi_dbm = self._signal_to_rssi(signal_s)
            auth, enc = self._split_security(security)
            if not ssid:
                ssid = "Hidden Network"
            networks.append(
                ScannedNetwork(
                    ssid=ssid,
                    bssid=bssid.lower(),
                    rssi_dbm=rssi_dbm,
                    signal_percent=self._rssi_to_percent(rssi_dbm),
                    channel=channel,
                    band=band_for_channel(channel),
                    authentication=auth,
                    encryption=enc,
                )
            )
        return networks

    @staticmethod
    def _split_security(security: str) -> tuple[str, str]:
        if not security or security == "--":
            return "Unknown", "Unknown"
        parts = [p.strip() for p in security.split() if p.strip()]
        auth = parts[0] if parts else "Unknown"
        enc = parts[-1] if len(parts) > 1 else "Unknown"
        return auth, enc
