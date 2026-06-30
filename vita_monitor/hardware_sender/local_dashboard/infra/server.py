from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from local_dashboard.service import LocalDashboard

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[1] / "ui" / "static"


def create_app(dashboard: LocalDashboard) -> FastAPI:
    app = FastAPI(title="Local Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    def _check_auth(request: Request) -> None:
        auth = dashboard.cfg.auth
        if not auth.enabled:
            return
        token = auth.token
        if not token:
            raise HTTPException(status_code=503, detail="auth enabled but token empty")
        supplied = request.query_params.get("token") or request.headers.get("x-local-token")
        if supplied != token:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        _check_auth(request)
        html = dashboard.render_index_page()
        return HTMLResponse(content=html)

    @app.get("/api/health")
    def health(request: Request) -> JSONResponse:
        _check_auth(request)
        return JSONResponse(
            {
                "ok": True,
                "server_time": time.time(),
                "device_id": dashboard.device_id,
                "mqtt_connected": dashboard.store.mqtt_connected,
                "websocket_clients": dashboard.ws_hub.client_count(),
            }
        )

    @app.get("/api/meta")
    def meta(request: Request) -> JSONResponse:
        _check_auth(request)
        return JSONResponse(
            {
                "device_id": dashboard.device_id,
                "panel_order": dashboard.panel_order(),
                "show_mqtt_status": dashboard.cfg.show_mqtt_status,
                "mock_vita_types": dashboard.mock_vita_types(),
            }
        )

    @app.get("/api/snapshot")
    def snapshot(request: Request) -> JSONResponse:
        _check_auth(request)
        return JSONResponse(dashboard.store.get_snapshot())

    @app.get("/api/panel/{vita_type}", response_class=HTMLResponse)
    def panel_fragment(vita_type: str, request: Request) -> HTMLResponse:
        _check_auth(request)
        html = dashboard.render_panel(vita_type)
        if html is None:
            raise HTTPException(status_code=404, detail=f"unknown panel: {vita_type}")
        return HTMLResponse(content=html)

    @app.websocket(dashboard.cfg.websocket_path)
    async def ws_live(websocket: WebSocket) -> None:
        if dashboard.cfg.auth.enabled:
            token = websocket.query_params.get("token") or websocket.headers.get("x-local-token")
            if token != dashboard.cfg.auth.token:
                await websocket.close(code=4401)
                return
        await dashboard.ws_hub.connect(websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and msg.get("action") == "ping":
                    await websocket.send_text(
                        json.dumps({"action": "pong", "server_time": time.time()})
                    )
        except WebSocketDisconnect:
            pass
        finally:
            await dashboard.ws_hub.disconnect(websocket)

    return app
