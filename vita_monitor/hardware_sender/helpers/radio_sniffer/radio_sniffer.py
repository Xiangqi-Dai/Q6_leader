from __future__ import annotations

import logging
import platform
import time
from typing import Any, Literal

from .channel_occupancy import RSSI_EMPTY_CHANNEL_DBM, build_channel_occupancy
from .func.linux_iw_scanner import LinuxIwScanner
from .func.linux_nmcli_scanner import LinuxNmcliScanner

ScanMethod = Literal["auto", "iw", "nmcli"]
logger = logging.getLogger(__name__)


class RadioSniffer:
    """Linux 无线嗅探：扫描周边 AP 并生成信道占用摘要。"""

    def __init__(
        self,
        *,
        interface: str | None = None,
        scan_method: ScanMethod = "auto",
        sudo_password: str | None = None,
    ) -> None:
        self.interface = (interface or "").strip() or None
        self.scan_method: ScanMethod = scan_method if scan_method in ("auto", "iw", "nmcli") else "auto"
        self._iw = LinuxIwScanner(sudo_password=sudo_password)
        self._nmcli = LinuxNmcliScanner(sudo_password=sudo_password)

    def collect(self) -> dict[str, Any]:
        if platform.system().lower() != "linux":
            return self._empty_payload(status="error", interface="", error="radio_sniffer 仅支持 Linux")

        networks, iface, err = self._scan_networks()
        if not networks:
            status = "empty" if not err else "error"
            payload = self._empty_payload(status=status, interface=iface, error=err)
            payload["scanned_at"] = time.time()
            return payload

        # 同一 BSSID 保留信号最强的一条
        best: dict[str, dict[str, Any]] = {}
        for n in networks:
            row = n.to_dict() if hasattr(n, "to_dict") else dict(n)
            bssid = str(row.get("bssid") or "").lower()
            if not bssid:
                continue
            prev = best.get(bssid)
            if prev is None or int(row.get("rssi_dbm", RSSI_EMPTY_CHANNEL_DBM)) > int(
                prev.get("rssi_dbm", RSSI_EMPTY_CHANNEL_DBM)
            ):
                best[bssid] = row

        merged = sorted(best.values(), key=lambda x: int(x.get("rssi_dbm", RSSI_EMPTY_CHANNEL_DBM)), reverse=True)
        return {
            "status": "ok",
            "interface": iface,
            "scanned_at": time.time(),
            "network_count": len(merged),
            "networks": merged,
            "channel_occupancy": build_channel_occupancy(merged),
            "error": "",
        }

    def _scan_networks(self) -> tuple[list[Any], str, str]:
        iface = ""
        err_parts: list[str] = []
        order: list[ScanMethod]
        if self.scan_method == "auto":
            order = ["iw", "nmcli"]
        else:
            order = [self.scan_method]

        for method in order:
            for attempt in range(2):
                try:
                    if method == "iw":
                        nets, iface = self._iw.scan(self.interface)
                    else:
                        nets, iface = self._nmcli.scan(self.interface)
                    if nets:
                        return nets, iface, ""
                    if attempt == 0:
                        logger.debug("%s scan returned empty, retrying in 1s", method)
                        time.sleep(1.0)
                        continue
                    err_parts.append(f"{method}: no networks")
                except Exception as exc:
                    err_parts.append(f"{method}: {exc}")
                    logger.warning("%s scan failed: %s", method, exc)
                    break
        err_msg = "; ".join(err_parts) if err_parts else "scan failed"
        logger.info("scan result: status=error, error=%s", err_msg)
        return [], iface, err_msg

    @staticmethod
    def _empty_payload(*, status: str, interface: str, error: str = "") -> dict[str, Any]:
        return {
            "status": status,
            "interface": interface,
            "scanned_at": time.time(),
            "network_count": 0,
            "networks": [],
            "channel_occupancy": build_channel_occupancy([]),
            "error": error,
        }
