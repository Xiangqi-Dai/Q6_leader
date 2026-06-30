from __future__ import annotations

import time
from typing import Any

from plugins.mock_utils import pick_int, rng_from_config


def generate_radio_sniffer_mock(mock_config: dict[str, Any]) -> dict[str, Any]:
    rng = rng_from_config(mock_config)
    iface = str(mock_config.get("interface", "wlan0"))
    networks = [
        {
            "ssid": "Lab-WiFi",
            "bssid": "aa:bb:cc:dd:ee:01",
            "channel": 6,
            "frequency_mhz": 2437,
            "rssi_dbm": pick_int(rng, None, (-58, -42)),
            "security": "WPA2",
        },
        {
            "ssid": "Guest-Net",
            "bssid": "aa:bb:cc:dd:ee:02",
            "channel": 11,
            "frequency_mhz": 2462,
            "rssi_dbm": pick_int(rng, None, (-72, -55)),
            "security": "WPA2",
        },
        {
            "ssid": "IoT-Bridge",
            "bssid": "aa:bb:cc:dd:ee:03",
            "channel": 1,
            "frequency_mhz": 2412,
            "rssi_dbm": pick_int(rng, None, (-80, -62)),
            "security": "OPEN",
        },
    ]
    channel_occupancy: dict[str, int] = {}
    for net in networks:
        ch = str(net["channel"])
        channel_occupancy[ch] = channel_occupancy.get(ch, 0) + 1
    return {
        "status": "ok",
        "interface": iface,
        "scanned_at": time.time(),
        "network_count": len(networks),
        "networks": networks,
        "channel_occupancy": channel_occupancy,
        "error": "",
    }
