from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._clients.add(ws)
        logger.info("local dashboard ws client connected, total=%s", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)
        logger.info("local dashboard ws client disconnected, total=%s", len(self._clients))

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    async def _broadcast_async(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast(self, payload: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._broadcast_async(payload), loop)
