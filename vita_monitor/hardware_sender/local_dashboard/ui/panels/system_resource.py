from __future__ import annotations

from local_dashboard.infra.state_store import VitalSeries
from local_dashboard.ui.panels.base import BasePanel


class SystemResourcePanel(BasePanel):
    vita_type = "system_resource"
    title = "系统计算资源"

    @property
    def template_name(self) -> str:
        return "partials/system_resource.html"

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        latest_data = series.latest.vita_data if series.latest else {}
        gpu_devices: list[dict] = []
        if isinstance(latest_data, dict):
            gpu = latest_data.get("gpu")
            if isinstance(gpu, dict):
                devices = gpu.get("devices")
                if isinstance(devices, list):
                    gpu_devices = [d for d in devices if isinstance(d, dict)]
        return template.render(
            **self._render_context(
                series,
                gpu_devices=gpu_devices,
            )
        )
