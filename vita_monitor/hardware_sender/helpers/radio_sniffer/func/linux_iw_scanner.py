from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from helpers.network_info.func.command_runner import CommandRunner

from ..channel_occupancy import band_for_channel


@dataclass
class ScannedNetwork:
    ssid: str
    bssid: str
    rssi_dbm: int
    signal_percent: int
    channel: int
    band: str
    authentication: str
    encryption: str

    def to_dict(self) -> dict:
        return {
            "ssid": self.ssid,
            "bssid": self.bssid,
            "rssi_dbm": self.rssi_dbm,
            "signal_percent": self.signal_percent,
            "channel": self.channel,
            "band": self.band,
            "authentication": self.authentication,
            "encryption": self.encryption,
        }


class LinuxIwScanner:
    """Linux `iw` 扫描：优先 `iw dev <iface> scan`，回退 `scan dump`。"""

    _BSS_RE = re.compile(r"^BSS ([0-9a-fA-F:]+)", re.MULTILINE)

    def __init__(self, sudo_password: Optional[str] = None) -> None:
        self._sudo_password = sudo_password

    def list_interfaces(self) -> List[str]:
        out, code = CommandRunner.run(["iw", "dev"], timeout=6.0, sudo_password=self._sudo_password)
        if code != 0 or not out:
            return []
        names: List[str] = []
        for line in out.splitlines():
            m = re.match(r"^\s*Interface\s+(\S+)", line)
            if m:
                names.append(m.group(1))
        return names

    def scan(self, interface: Optional[str] = None) -> tuple[List[ScannedNetwork], str]:
        if not interface:
            ifaces = self.list_interfaces()
            iface = ifaces[0] if ifaces else ""
        else:
            iface = interface
        if not iface:
            return [], ""

        out, code = CommandRunner.run(["iw", "dev", iface, "scan"], timeout=25.0, sudo_password=self._sudo_password)
        if code != 0 or not out.strip():
            out, code = CommandRunner.run(["iw", "dev", iface, "scan", "dump"], timeout=12.0, sudo_password=self._sudo_password)
        if code != 0 or not out.strip():
            return [], iface

        networks = self._parse_scan_output(out)
        return networks, iface

    @staticmethod
    def _rssi_to_percent(rssi_dbm: int) -> int:
        # 与 reference/嗅探/scanner.py 互逆：rssi ≈ -100 + signal% * 0.5
        pct = int(round((rssi_dbm + 100) * 2))
        return max(0, min(100, pct))

    @staticmethod
    def _channel_from_freq_mhz(freq_mhz: float) -> int:
        f = int(round(freq_mhz))
        if 2400 <= f <= 2500:
            return max(1, min(14, int(round((f - 2407) / 5))))
        if 5000 <= f <= 6000:
            # 5 GHz 常用中心频率 → 信道（容差匹配）
            table = {
                5180: 36,
                5200: 40,
                5220: 44,
                5240: 48,
                5260: 52,
                5280: 56,
                5300: 60,
                5320: 64,
                5500: 100,
                5520: 104,
                5540: 108,
                5560: 112,
                5580: 116,
                5600: 120,
                5620: 124,
                5640: 128,
                5660: 132,
                5680: 136,
                5700: 140,
                5720: 144,
                5745: 149,
                5765: 153,
                5785: 157,
                5805: 161,
                5825: 165,
            }
            best_ch, best_diff = 36, 10_000
            for center, ch in table.items():
                diff = abs(center - f)
                if diff < best_diff:
                    best_diff = diff
                    best_ch = ch
            if best_diff <= 15:
                return best_ch
        return 1

    def _parse_scan_output(self, text: str) -> List[ScannedNetwork]:
        networks: List[ScannedNetwork] = []
        parts = self._BSS_RE.split(text)
        if len(parts) < 2:
            return networks

        # split 后奇数位为 BSSID，偶数位为块内容
        i = 1
        while i + 1 < len(parts):
            bssid = parts[i].split("(", 1)[0].strip().lower()
            block = parts[i + 1]
            i += 2
            net = self._parse_bss_block(bssid, block)
            if net is not None:
                networks.append(net)
        return networks

    def _parse_bss_block(self, bssid: str, block: str) -> Optional[ScannedNetwork]:
        ssid = ""
        m_ssid = re.search(r"\n\s*SSID:\s*(.*)", block)
        if m_ssid:
            ssid = m_ssid.group(1).strip()
        if not ssid:
            ssid = "Hidden Network"

        rssi_dbm = -95
        m_sig = re.search(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", block, re.IGNORECASE)
        if m_sig:
            rssi_dbm = int(round(float(m_sig.group(1))))

        channel = 0
        m_ds = re.search(r"DS Parameter set:\s*channel\s*(\d+)", block, re.IGNORECASE)
        if m_ds:
            channel = int(m_ds.group(1))
        if channel <= 0:
            m_freq = re.search(r"freq:\s*(\d+(?:\.\d+)?)", block, re.IGNORECASE)
            if m_freq:
                channel = self._channel_from_freq_mhz(float(m_freq.group(1)))
        if channel <= 0:
            channel = 1

        auth, enc = self._parse_security_ies(block)
        band = band_for_channel(channel)
        return ScannedNetwork(
            ssid=ssid,
            bssid=bssid,
            rssi_dbm=rssi_dbm,
            signal_percent=self._rssi_to_percent(rssi_dbm),
            channel=channel,
            band=band,
            authentication=auth,
            encryption=enc,
        )

    @staticmethod
    def _parse_security_ies(block: str) -> tuple[str, str]:
        auth = "Unknown"
        enc = "Unknown"
        if re.search(r"RSN:", block) or re.search(r"WPA:", block):
            auth = "WPA2"
            enc = "CCMP"
        elif re.search(r"WEP:", block, re.IGNORECASE):
            auth = "WEP"
            enc = "WEP"
        elif re.search(r"capability:.*Privacy", block):
            auth = "Open"
            enc = "None"
        return auth, enc
