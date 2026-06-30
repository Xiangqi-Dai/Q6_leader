from __future__ import annotations

from local_dashboard.infra.state_store import VitalSeries
from local_dashboard.ui.panels.base import BasePanel
from local_dashboard.ui.chart_payload import (
    build_air_comfort_points,
    build_air_pollutant_points,
)


class AirSnifferPanel(BasePanel):
    vita_type = "air_sniffer"
    title = "空气传感器"

    @property
    def template_name(self) -> str:
        return "partials/air_sniffer.html"

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        history = list(series.history)
        return template.render(
            **self._render_context(
                series,
                pollutant_points=build_air_pollutant_points(history),
                comfort_points=build_air_comfort_points(history),
            )
        )
