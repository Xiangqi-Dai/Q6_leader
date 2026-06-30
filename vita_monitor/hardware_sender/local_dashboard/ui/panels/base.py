from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from local_dashboard.infra.state_store import VitalSeries
from local_dashboard.ui import formatters

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


def create_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["fmt_time"] = formatters.fmt_time
    env.filters["fmt_float"] = formatters.fmt_float
    env.filters["fmt_percent_rate"] = formatters.fmt_percent_rate
    env.filters["heartbeat_traffic"] = formatters.heartbeat_traffic_class
    env.filters["ip_peer_traffic"] = formatters.ip_peer_traffic_class
    env.filters["ip_peer_summary"] = formatters.ip_peer_summary_class
    env.filters["risk_level_class"] = formatters.risk_level_class
    env.filters["sysres_percent"] = formatters.system_resource_percent_class
    env.filters["sysres_temp"] = formatters.system_resource_temp_class
    env.tests["mock_data_mode"] = formatters.is_mock_data_mode
    return env


class BasePanel(ABC):
    vita_type: str = ""
    title: str = ""

    def __init__(self, env: Environment) -> None:
        self._env = env

    @property
    @abstractmethod
    def template_name(self) -> str:
        raise NotImplementedError

    def _render_context(self, series: VitalSeries, **extra: Any) -> dict[str, Any]:
        data_mode = series.latest.data_mode if series.latest else None
        is_mock_mode = formatters.is_mock_data_mode(data_mode)
        ctx: dict[str, Any] = {
            "title": self.title,
            "vita_type": self.vita_type,
            "data_mode": data_mode,
            "is_mock_mode": is_mock_mode,
            "latest": series.latest,
            "history": list(series.history),
        }
        ctx.update(extra)
        return ctx

    def render(self, series: VitalSeries) -> str:
        template = self._env.get_template(self.template_name)
        return template.render(**self._render_context(series))
