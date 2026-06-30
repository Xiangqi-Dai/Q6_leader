from __future__ import annotations

from local_dashboard.infra.state_store import VitalSeries
from local_dashboard.ui.chart_payload import build_heartbeat_points
from local_dashboard.ui.panels.base import BasePanel


class HeartbeatPanel(BasePanel):
    vita_type = "heartbeat"
    title = "心跳 / 公网连接"

    @property
    def template_name(self) -> str:
        return "partials/heartbeat.html"

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        history = list(series.history)
        return template.render(
            **self._render_context(
                series,
                heartbeat_points=build_heartbeat_points(history),
            )
        )
