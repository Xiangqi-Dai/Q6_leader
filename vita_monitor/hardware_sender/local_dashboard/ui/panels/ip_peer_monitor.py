from __future__ import annotations

from local_dashboard.infra.state_store import VitalSeries
from local_dashboard.ui.panels.base import BasePanel


class IpPeerMonitorPanel(BasePanel):
    vita_type = "ip_peer_monitor"
    title = "IP 对端连通性"

    @property
    def template_name(self) -> str:
        return "partials/ip_peer_monitor.html"

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        history = list(series.history)
        latest_data = series.latest.vita_data if series.latest else {}
        peers = latest_data.get("peers") if isinstance(latest_data, dict) else []
        if not isinstance(peers, list):
            peers = []
        return template.render(
            **self._render_context(
                series,
                peers=peers,
            )
        )
