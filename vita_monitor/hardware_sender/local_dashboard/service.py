from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import uvicorn

from local_dashboard.infra.server import create_app
from local_dashboard.infra.state_store import LocalStateStore
from local_dashboard.infra.ws_hub import WebSocketHub
from local_dashboard.ui.panels.base import create_jinja_env
from comm_infra.envelope import normalize_data_mode
from local_dashboard.ui.panels.registry import PanelRegistry, build_panel_registry
from utils.runtime_config import LocalDashboardConfig, RuntimeConfig, VitalUiConfig

logger = logging.getLogger(__name__)


class LocalDashboard:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self._runtime_cfg = cfg
        self.cfg = cfg.local_dashboard
        self.device_id = cfg.device_id
        self.enabled = self.cfg.enabled

        self.store = LocalStateStore(device_id=cfg.device_id)
        self.ws_hub = WebSocketHub()
        self._env = create_jinja_env()
        self._panels = build_panel_registry(self._env)
        self._ui_vita_types: list[str] = []
        self._configure_ui_vitals(cfg)

        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def panels(self) -> PanelRegistry:
        return self._panels

    def _configure_ui_vitals(self, cfg: RuntimeConfig) -> None:
        order: list[str] = []
        seen: set[str] = set()

        def try_add(vita_type: str, ui_cfg: VitalUiConfig | None) -> None:
            if ui_cfg is None or vita_type in seen:
                return
            panel = self._panels.get(vita_type)
            if panel is None:
                logger.warning("local_dashboard: no panel for vita_type=%s, skip UI", vita_type)
                return
            self.store.configure_vital(vita_type, ui_history_limit=ui_cfg.ui_history_limit)
            order.append(vita_type)
            seen.add(vita_type)

        for vita_type, ui_cfg in self.cfg.vitals.items():
            if ui_cfg.push_to_ui:
                try_add(vita_type, ui_cfg)

        for vita_type, plugin_cfg in cfg.sender.plugins.items():
            try_add(vita_type, self.cfg.ui_config_for(vita_type, sender_enabled=plugin_cfg.enabled))

        self._ui_vita_types = self._sort_panel_order(order)
        logger.info("local_dashboard ui vitals: %s", self._ui_vita_types)

    def _sort_panel_order(self, order: list[str]) -> list[str]:
        preferred = self.cfg.panel_order
        rank = {vita_type: idx for idx, vita_type in enumerate(preferred)}
        return sorted(order, key=lambda vita_type: (rank.get(vita_type, len(preferred)), order.index(vita_type)))

    def panel_order(self) -> list[str]:
        return list(self._ui_vita_types)

    def start(self) -> None:
        if not self.enabled:
            logger.info("local_dashboard disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return

        app = create_app(self)
        config = uvicorn.Config(
            app,
            host=self.cfg.host,
            port=self.cfg.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self.ws_hub.bind_loop(loop)
            loop.run_until_complete(self._server.serve())

        self._thread = threading.Thread(target=_run, name="local-dashboard", daemon=True)
        self._thread.start()
        logger.info(
            "local_dashboard started: http://%s:%s",
            self.cfg.host,
            self.cfg.port,
        )

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=8.0)
            self._thread = None
        self._server = None
        self._loop = None
        logger.info("local_dashboard stopped")

    def ingest(self, item: dict[str, Any]) -> None:
        if not self.enabled:
            return
        vita_type = item.get("vita_type")
        vita_data = item.get("vita_data")
        if not isinstance(vita_type, str) or vita_type not in self._ui_vita_types:
            return
        if not isinstance(vita_data, dict):
            return
        collected_at = item.get("collected_at")
        if not isinstance(collected_at, (int, float)):
            collected_at = time.time()
        try:
            data_mode = normalize_data_mode(item.get("data_mode"))
        except ValueError:
            data_mode = "real"
        snap = self.store.append(
            vita_type=vita_type,
            vita_data=vita_data,
            collected_at=float(collected_at),
            data_mode=data_mode,
        )
        self.ws_hub.broadcast(self.store.build_vital_event(snap))

    def set_mqtt_connected(self, connected: bool, *, error: str | None = None) -> None:
        if not self.enabled:
            return
        prev = self.store.mqtt_connected
        self.store.set_mqtt_status(connected=connected, error=error)
        if prev != connected:
            self.ws_hub.broadcast(self.store.build_mqtt_status_event())

    def render_panel(self, vita_type: str) -> str | None:
        panel = self._panels.get(vita_type)
        if panel is None or vita_type not in self._ui_vita_types:
            return None
        series = self.store.get_series(vita_type)
        try:
            return panel.render(series)
        except Exception:
            logger.exception("local_dashboard panel render failed: %s", vita_type)
            return (
                f'<article class="panel"><header class="panel-header"><h2>{vita_type}</h2></header>'
                f'<p class="empty err-tag">Panel 渲染失败，请查看服务日志。</p></article>'
            )

    def mock_vita_types(self) -> list[str]:
        out: list[str] = []
        for vita_type in self._ui_vita_types:
            latest = self.store.get_series(vita_type).latest
            if latest is not None and latest.data_mode == "mock":
                out.append(vita_type)
        return out

    def render_index_page(self) -> str:
        panel_html: dict[str, str] = {}
        for vita_type in self._ui_vita_types:
            html = self.render_panel(vita_type)
            panel_html[vita_type] = html or ""
        template = self._env.get_template("layout.html")
        return template.render(
            device_id=self.device_id,
            show_mqtt_status=self.cfg.show_mqtt_status,
            mqtt_connected=self.store.mqtt_connected,
            panel_order=self._ui_vita_types,
            panel_html=panel_html,
            websocket_path=self.cfg.websocket_path,
            mock_vita_types=self.mock_vita_types(),
        )
