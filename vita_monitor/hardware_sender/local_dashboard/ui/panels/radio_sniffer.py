from __future__ import annotations

from local_dashboard.infra.state_store import VitalSeries, VitalSnapshot, radio_sniffer_is_valid
from local_dashboard.ui.chart_payload import sort_radio_networks
from local_dashboard.ui.panels.base import BasePanel


class RadioSnifferPanel(BasePanel):
    vita_type = "radio_sniffer"
    title = "WiFi 嗅探"

    @property
    def template_name(self) -> str:
        return "partials/radio_sniffer.html"

    def _display_snapshot(self, series: VitalSeries) -> tuple[VitalSnapshot | None, bool]:
        """返回用于展示的 snapshot，以及是否因最新采集失败而回退到 latest_valid_value。"""
        latest = series.latest
        latest_valid = series.latest_valid_value
        if latest is not None and not radio_sniffer_is_valid(latest.vita_data):
            if latest_valid is not None:
                return latest_valid, True
            return None, False
        return latest or latest_valid, False

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        display, using_stale = self._display_snapshot(series)
        display_data = display.vita_data if display else {}
        networks = display_data.get("networks") if isinstance(display_data, dict) else []
        if not isinstance(networks, list):
            networks = []
        latest = series.latest
        latest_failed = (
            latest is not None
            and not radio_sniffer_is_valid(latest.vita_data)
        )
        return template.render(
            **self._render_context(
                series,
                display=display,
                using_stale=using_stale,
                latest_failed=latest_failed,
                sorted_networks=sort_radio_networks(networks),
                radio_data=display_data if isinstance(display_data, dict) else {},
            )
        )
