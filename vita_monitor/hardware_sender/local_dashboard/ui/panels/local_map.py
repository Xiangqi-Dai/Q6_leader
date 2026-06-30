from __future__ import annotations

from local_dashboard.ui.panels.base import BasePanel


class LocalMapPanel(BasePanel):
    vita_type = "local_map"
    title = "本地地图"

    @property
    def template_name(self) -> str:
        return "partials/local_map.html"
