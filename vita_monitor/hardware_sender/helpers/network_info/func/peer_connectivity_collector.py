from __future__ import annotations

import ipaddress
import re
import time
from typing import Any

from .icmp_probe import PEER_FAILURE_LATENCY_MS, IcmpProbe

_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.\-]*[a-zA-Z0-9])?$")


class PeerConnectivityCollector:
    """对配置的对端 IP/主机名执行短 ICMP 探测。"""

    _round_robin_offset: int = 0
    _last_peer_results: dict[str, dict[str, Any]] = {}

    @classmethod
    def probe_all(
        cls,
        peers: list[dict[str, str]],
        *,
        ping_count: int = 2,
        ping_timeout_sec: float = 2.0,
        max_peers_per_cycle: int = 0,
    ) -> dict[str, Any]:
        probed_at = time.time()
        normalized = cls._normalize_peers(peers)
        if not normalized:
            return {
                "status": "error",
                "probed_at": probed_at,
                "peer_count": 0,
                "online_count": 0,
                "peers": [],
                "error": "peers is empty or all entries invalid",
            }

        targets, skipped_errors = cls._select_targets(normalized, max_peers_per_cycle=max_peers_per_cycle)

        for item in targets:
            peer_result = cls._probe_one(
                ip=item["ip"],
                name=item["name"],
                ping_count=ping_count,
                ping_timeout_sec=ping_timeout_sec,
            )
            cls._last_peer_results[item["ip"]] = peer_result

        ordered_peers: list[dict[str, Any]] = []
        for item in normalized:
            cached = cls._last_peer_results.get(item["ip"])
            if cached is not None:
                ordered_peers.append(dict(cached))
            else:
                ordered_peers.append(cls._unprobed_peer(ip=item["ip"], name=item["name"]))
        online_count = sum(1 for p in ordered_peers if p.get("connected"))
        global_error = "; ".join(skipped_errors) if skipped_errors else ""

        return {
            "status": "ok",
            "probed_at": probed_at,
            "peer_count": len(normalized),
            "online_count": online_count,
            "peers": ordered_peers,
            "error": global_error,
        }

    @staticmethod
    def _normalize_peers(peers: list[dict[str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in peers:
            if not isinstance(raw, dict):
                continue
            ip = str(raw.get("ip", "")).strip()
            if not ip or not PeerConnectivityCollector._is_valid_host(ip):
                continue
            if ip in seen:
                continue
            seen.add(ip)
            name = str(raw.get("name", "")).strip() or ip
            out.append({"ip": ip, "name": name})
        return out

    @staticmethod
    def _is_valid_host(host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return bool(_HOSTNAME_RE.match(host))

    @classmethod
    def _select_targets(
        cls,
        normalized: list[dict[str, str]],
        *,
        max_peers_per_cycle: int,
    ) -> tuple[list[dict[str, str]], list[str]]:
        if max_peers_per_cycle <= 0 or max_peers_per_cycle >= len(normalized):
            return list(normalized), []

        start = cls._round_robin_offset % len(normalized)
        end = start + max_peers_per_cycle
        if end <= len(normalized):
            batch = normalized[start:end]
        else:
            batch = normalized[start:] + normalized[: end - len(normalized)]
        cls._round_robin_offset = (start + max_peers_per_cycle) % len(normalized)
        return batch, []

    @staticmethod
    def _unprobed_peer(*, ip: str, name: str) -> dict[str, Any]:
        return {
            "ip": ip,
            "name": name,
            "connected": False,
            "latency_ms": PEER_FAILURE_LATENCY_MS,
            "packet_loss_rate": 1.0,
            "error": "not_probed_yet",
        }

    @staticmethod
    def _probe_one(
        *,
        ip: str,
        name: str,
        ping_count: int,
        ping_timeout_sec: float,
    ) -> dict[str, Any]:
        failure = {
            "ip": ip,
            "name": name,
            "connected": False,
            "latency_ms": PEER_FAILURE_LATENCY_MS,
            "packet_loss_rate": 1.0,
            "error": "timeout",
        }
        try:
            count = max(1, min(4, int(ping_count)))
            lat, loss, _jit, ok = IcmpProbe.measure(
                ip,
                ping_count=count,
                ping_timeout_sec=ping_timeout_sec,
            )
            connected = bool(ok and loss < 1.0)
            if not connected and not ok:
                return dict(failure)
            return {
                "ip": ip,
                "name": name,
                "connected": connected,
                "latency_ms": int(round(lat)) if connected else PEER_FAILURE_LATENCY_MS,
                "packet_loss_rate": float(max(0.0, min(1.0, loss))),
                "error": "" if connected else "unreachable",
            }
        except Exception as exc:
            out = dict(failure)
            out["error"] = str(exc)[:80] or "probe_failed"
            return out
