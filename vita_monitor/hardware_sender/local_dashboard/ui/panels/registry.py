from __future__ import annotations

from jinja2 import Environment

from local_dashboard.ui.panels.air_sniffer import AirSnifferPanel
from local_dashboard.ui.panels.base import BasePanel
from local_dashboard.ui.panels.heartbeat import HeartbeatPanel
from local_dashboard.ui.panels.ip_peer_monitor import IpPeerMonitorPanel
from local_dashboard.ui.panels.local_map import LocalMapPanel
from local_dashboard.ui.panels.local_pose import LocalPosePanel
from local_dashboard.ui.panels.radio_sniffer import RadioSnifferPanel
from local_dashboard.ui.panels.system_resource import SystemResourcePanel


class PanelRegistry:
    def __init__(self, panels: dict[str, BasePanel]) -> None:
        self._panels = panels

    def get(self, vita_type: str) -> BasePanel | None:
        return self._panels.get(vita_type)

    def ordered_types(self, preferred: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for vita_type in preferred:
            if vita_type in self._panels and vita_type not in seen:
                out.append(vita_type)
                seen.add(vita_type)
        for vita_type in sorted(self._panels):
            if vita_type not in seen:
                out.append(vita_type)
                seen.add(vita_type)
        return out


def build_panel_registry(env: Environment) -> PanelRegistry:
    panels: list[BasePanel] = [
        HeartbeatPanel(env),
        IpPeerMonitorPanel(env),
        SystemResourcePanel(env),
        AirSnifferPanel(env),
        RadioSnifferPanel(env),
        LocalPosePanel(env),
        LocalMapPanel(env),
    ]
    return PanelRegistry({p.vita_type: p for p in panels if p.vita_type})
