from __future__ import annotations

from local_dashboard.ui.panels.base import BasePanel


class LocalPosePanel(BasePanel):
    vita_type = "local_pose"
    title = "本地位姿"

    @property
    def template_name(self) -> str:
        return "partials/local_pose.html"
