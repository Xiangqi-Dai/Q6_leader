from __future__ import annotations

from typing import Any

# 与 reference/嗅探/visualizer.py 常用信道列表一致
CHANNELS_2_4_GHZ = list(range(1, 15))
CHANNELS_5_GHZ = [
    36,
    40,
    44,
    48,
    52,
    56,
    60,
    64,
    100,
    104,
    108,
    112,
    116,
    120,
    124,
    128,
    132,
    136,
    140,
    144,
    149,
    153,
    157,
    161,
    165,
]

RSSI_EMPTY_CHANNEL_DBM = -95


def band_for_channel(channel: int) -> str:
    if channel in CHANNELS_2_4_GHZ:
        return "2_4_ghz"
    if channel in CHANNELS_5_GHZ or channel >= 36:
        return "5_ghz"
    return "unknown"


def build_channel_occupancy(networks: list[dict[str, Any]]) -> dict[str, Any]:
    """按频段汇总各信道的 AP 数量与最强 RSSI（dBm）。"""
    buckets: dict[str, dict[int, list[int]]] = {
        "2_4_ghz": {ch: [] for ch in CHANNELS_2_4_GHZ},
        "5_ghz": {ch: [] for ch in CHANNELS_5_GHZ},
    }
    for net in networks:
        ch = int(net.get("channel") or 0)
        rssi = int(net.get("rssi_dbm") or RSSI_EMPTY_CHANNEL_DBM)
        band = str(net.get("band") or band_for_channel(ch))
        if band not in buckets or ch not in buckets[band]:
            continue
        buckets[band][ch].append(rssi)

    out: dict[str, Any] = {}
    for band, ch_map in buckets.items():
        channels = sorted(ch_map.keys())
        ap_counts: list[int] = []
        peak_rssi_dbm: list[int] = []
        for ch in channels:
            rssis = ch_map[ch]
            ap_counts.append(len(rssis))
            peak_rssi_dbm.append(max(rssis) if rssis else RSSI_EMPTY_CHANNEL_DBM)
        out[band] = {
            "channels": channels,
            "ap_counts": ap_counts,
            "peak_rssi_dbm": peak_rssi_dbm,
        }
    return out
