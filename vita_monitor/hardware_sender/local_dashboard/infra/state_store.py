from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VitalSnapshot:
    device_id: str
    vita_type: str
    data_mode: str
    vita_data: dict[str, Any]
    collected_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "vita_type": self.vita_type,
            "data_mode": self.data_mode,
            "vita_data": dict(self.vita_data),
            "collected_at": self.collected_at,
        }


@dataclass
class VitalSeries:
    latest: VitalSnapshot | None = None
    latest_valid_value: VitalSnapshot | None = None
    history: deque[VitalSnapshot] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = deque()


def radio_sniffer_is_valid(vita_data: dict[str, Any]) -> bool:
    """radio_sniffer 采集成功：status 为 ok 或 empty（empty 表示扫描成功但未发现 AP）。"""
    return isinstance(vita_data, dict) and vita_data.get("status") != "error"


class LocalStateStore:
    def __init__(self, *, device_id: str) -> None:
        self._device_id = device_id
        self._lock = threading.RLock()
        self._latest: dict[str, VitalSnapshot] = {}
        self._latest_valid_value: dict[str, VitalSnapshot] = {}
        self._history: dict[str, deque[VitalSnapshot]] = {}
        self._history_limits: dict[str, int] = {}
        self.mqtt_connected: bool = False
        self.mqtt_last_error: str | None = None

    def configure_vital(self, vita_type: str, *, ui_history_limit: int) -> None:
        with self._lock:
            self._history_limits[vita_type] = max(0, int(ui_history_limit))
            if vita_type not in self._history:
                maxlen = self._history_limits[vita_type] or None
                self._history[vita_type] = deque(maxlen=maxlen if maxlen else None)

    def append(
        self,
        *,
        vita_type: str,
        vita_data: dict[str, Any],
        collected_at: float,
        data_mode: str = "real",
    ) -> VitalSnapshot:
        snap = VitalSnapshot(
            device_id=self._device_id,
            vita_type=vita_type,
            data_mode=str(data_mode or "real"),
            vita_data=dict(vita_data),
            collected_at=float(collected_at),
        )
        with self._lock:
            self._latest[vita_type] = snap
            if vita_type == "radio_sniffer" and radio_sniffer_is_valid(vita_data):
                self._latest_valid_value[vita_type] = snap
            limit = self._history_limits.get(vita_type, 20)
            if limit > 0:
                hist = self._history.setdefault(vita_type, deque(maxlen=limit))
                if hist.maxlen != limit:
                    self._history[vita_type] = deque(list(hist)[-limit:], maxlen=limit)
                    hist = self._history[vita_type]
                hist.append(snap)
        return snap

    def set_mqtt_status(self, *, connected: bool, error: str | None = None) -> None:
        with self._lock:
            self.mqtt_connected = connected
            self.mqtt_last_error = error

    def get_series(self, vita_type: str) -> VitalSeries:
        with self._lock:
            return VitalSeries(
                latest=self._latest.get(vita_type),
                latest_valid_value=self._latest_valid_value.get(vita_type),
                history=deque(self._history.get(vita_type, deque())),
            )

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            vitals: dict[str, Any] = {}
            for vita_type in sorted(set(self._latest) | set(self._history)):
                series = VitalSeries(
                    latest=self._latest.get(vita_type),
                    latest_valid_value=self._latest_valid_value.get(vita_type),
                    history=deque(self._history.get(vita_type, deque())),
                )
                vitals[vita_type] = {
                    "latest": series.latest.to_dict() if series.latest else None,
                    "latest_valid_value": (
                        series.latest_valid_value.to_dict()
                        if series.latest_valid_value
                        else None
                    ),
                    "history": [s.to_dict() for s in series.history],
                }
            return {
                "device_id": self._device_id,
                "server_time": time.time(),
                "mqtt_connected": self.mqtt_connected,
                "mqtt_last_error": self.mqtt_last_error,
                "vitals": vitals,
            }

    def list_ui_vita_types(self) -> list[str]:
        with self._lock:
            return sorted(set(self._latest) | set(self._history_limits))

    def build_vital_event(self, snap: VitalSnapshot) -> dict[str, Any]:
        with self._lock:
            history_count = len(self._history.get(snap.vita_type, ()))
        return {
            "event": "vital.updated",
            "device_id": snap.device_id,
            "vita_type": snap.vita_type,
            "data_mode": snap.data_mode,
            "collected_at": snap.collected_at,
            "vita_data": dict(snap.vita_data),
            "history_count": history_count,
        }

    def build_mqtt_status_event(self) -> dict[str, Any]:
        with self._lock:
            return {
                "event": "mqtt.status",
                "connected": self.mqtt_connected,
                "message": self.mqtt_last_error or "",
                "server_time": time.time(),
            }
