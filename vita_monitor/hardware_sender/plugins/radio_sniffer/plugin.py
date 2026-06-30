from __future__ import annotations

import logging
from typing import Any

from helpers.radio_sniffer import RadioSniffer
from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)


class RadioSnifferVitalPlugin(BaseVitalPlugin):
    """周边 WiFi 扫描与频段信道占用嗅探（Linux）。"""

    vita_type = "radio_sniffer"
    vita_data_schema: dict[str, Any] = {
        "status": "str",  # ok | empty | error
        "interface": "str",
        "scanned_at": "float",
        "network_count": "int",
        "networks": "list[object]",
        "channel_occupancy": "object",
        "error": "str",
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        scan_method = str(kwargs.get("scan_method", "auto")).strip().lower()
        if scan_method not in ("auto", "iw", "nmcli"):
            scan_method = "auto"
        self._sniffer = RadioSniffer(
            interface=str(kwargs.get("interface", "")).strip() or None,
            scan_method=scan_method,  # type: ignore[arg-type]
            sudo_password=kwargs.get("sudo_password"),
        )
        self._last_payload: dict[str, Any] = {
            "status": "empty",
            "interface": "",
            "scanned_at": 0.0,
            "network_count": 0,
            "networks": [],
            "channel_occupancy": {},
            "error": "",
        }

    def collect_real_vita_data(self) -> dict[str, Any]:
        """单次嗅探：失败时仍上报空快照，不中断插件循环。"""
        try:
            out = self._sniffer.collect()
        except Exception:
            logger.exception("radio_sniffer collect failed")
            out = dict(self._last_payload)
            out["status"] = "error"
            out["error"] = "collect exception"
        self._last_payload = out
        return dict(out)

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.radio_sniffer.mock_generator import generate_radio_sniffer_mock

        out = generate_radio_sniffer_mock(self.mock_config)
        self._last_payload = out
        return dict(out)
