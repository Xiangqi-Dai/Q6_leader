from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from comm_infra.envelope import normalize_data_mode

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int = 1883
    use_tls: bool = False
    username: str | None = None
    password: str | None = None
    keepalive: int = 60
    client_id: str | None = None


@dataclass(frozen=True)
class PluginConfig:
    vita_type: str
    class_path: str
    interval_sec: float
    qos: int = 0
    enabled: bool = True
    data_mode: str = "real"
    mock: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SenderConfig:
    default_data_mode: str = "real"
    info_pool_maxsize: int = 1000
    publish_idle_sleep_sec: float = 0.2
    plugins: dict[str, PluginConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class VitalUiConfig:
    push_to_ui: bool = True
    ui_history_limit: int = 20


@dataclass(frozen=True)
class LocalDashboardAuthConfig:
    enabled: bool = False
    token: str = ""


DEFAULT_UI_PANEL_ORDER: tuple[str, ...] = ("heartbeat", "radio_sniffer", "air_sniffer")


@dataclass(frozen=True)
class LocalDashboardConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8765
    show_mqtt_status: bool = True
    default_ui_history_limit: int = 20
    websocket_path: str = "/ws/live"
    panel_order: tuple[str, ...] = DEFAULT_UI_PANEL_ORDER
    vitals: dict[str, VitalUiConfig] = field(default_factory=dict)
    auth: LocalDashboardAuthConfig = field(default_factory=LocalDashboardAuthConfig)

    def ui_config_for(self, vita_type: str, *, sender_enabled: bool) -> VitalUiConfig | None:
        """Return UI config if this vital should be shown; None means skip ingest/UI."""
        if vita_type in self.vitals:
            cfg = self.vitals[vita_type]
            if not cfg.push_to_ui:
                return None
            return cfg
        if not sender_enabled:
            return None
        return VitalUiConfig(
            push_to_ui=True,
            ui_history_limit=self.default_ui_history_limit,
        )


@dataclass(frozen=True)
class RuntimeConfig:
    config_path: Path
    device_id: str
    mqtt: MqttConfig
    sender: SenderConfig
    local_dashboard: LocalDashboardConfig
    sudo_password: str | None = None


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be object: {path}")
    return raw


def _to_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def load_runtime_config(config_path: str | Path | None = None) -> RuntimeConfig:
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    raw = _read_yaml(path)

    device_cfg = raw.get("device") or {}
    if not isinstance(device_cfg, dict):
        raise ValueError("config.yaml: device must be an object")
    device_id = str(device_cfg.get("id", "")).strip()
    if not device_id:
        raise ValueError("config.yaml: device.id is required")

    mqtt_cfg_raw = raw.get("mqtt") or {}
    if not isinstance(mqtt_cfg_raw, dict):
        raise ValueError("config.yaml: mqtt must be an object")
    mqtt_host = str(mqtt_cfg_raw.get("host", "")).strip()
    if not mqtt_host:
        raise ValueError("config.yaml: mqtt.host is required")
    mqtt_cfg = MqttConfig(
        host=mqtt_host,
        port=int(mqtt_cfg_raw.get("port", 1883)),
        use_tls=_to_bool(mqtt_cfg_raw.get("use_tls"), default=False),
        username=mqtt_cfg_raw.get("username"),
        password=mqtt_cfg_raw.get("password"),
        keepalive=int(mqtt_cfg_raw.get("keepalive", 60)),
        client_id=mqtt_cfg_raw.get("client_id"),
    )

    sender_raw = raw.get("sender") or {}
    if not isinstance(sender_raw, dict):
        raise ValueError("config.yaml: sender must be an object")

    plugins_raw = sender_raw.get("plugins") or {}
    if not isinstance(plugins_raw, dict):
        raise ValueError("config.yaml: sender.plugins must be an object")

    default_data_mode = normalize_data_mode(sender_raw.get("default_data_mode"), default="real")

    plugins: dict[str, PluginConfig] = {}
    for vita_type, cfg in plugins_raw.items():
        if not isinstance(vita_type, str) or not vita_type.strip():
            raise ValueError("config.yaml: sender.plugins key must be non-empty string")
        if not isinstance(cfg, dict):
            raise ValueError(f"config.yaml: sender.plugins.{vita_type} must be an object")
        class_path = str(cfg.get("class", "")).strip()
        if not class_path:
            raise ValueError(f"config.yaml: sender.plugins.{vita_type}.class is required")
        interval_sec = float(cfg.get("interval_sec", 0))
        if interval_sec <= 0:
            raise ValueError(f"config.yaml: sender.plugins.{vita_type}.interval_sec must be > 0")
        qos = int(cfg.get("qos", 0))
        if qos not in (0, 1, 2):
            raise ValueError(f"config.yaml: sender.plugins.{vita_type}.qos must be 0/1/2")
        kwargs = cfg.get("kwargs") or {}
        if not isinstance(kwargs, dict):
            raise ValueError(f"config.yaml: sender.plugins.{vita_type}.kwargs must be an object")
        mock = cfg.get("mock") or {}
        if not isinstance(mock, dict):
            raise ValueError(f"config.yaml: sender.plugins.{vita_type}.mock must be an object")
        plugin_data_mode = normalize_data_mode(cfg.get("data_mode"), default=default_data_mode)
        plugins[vita_type] = PluginConfig(
            vita_type=vita_type,
            class_path=class_path,
            interval_sec=interval_sec,
            qos=qos,
            enabled=_to_bool(cfg.get("enabled"), default=True),
            data_mode=plugin_data_mode,
            mock=mock,
            kwargs=kwargs,
        )

    sender_cfg = SenderConfig(
        default_data_mode=default_data_mode,
        info_pool_maxsize=int(sender_raw.get("info_pool_maxsize", 1000)),
        publish_idle_sleep_sec=float(sender_raw.get("publish_idle_sleep_sec", 0.2)),
        plugins=plugins,
    )
    if sender_cfg.info_pool_maxsize <= 0:
        raise ValueError("config.yaml: sender.info_pool_maxsize must be > 0")
    if sender_cfg.publish_idle_sleep_sec <= 0:
        raise ValueError("config.yaml: sender.publish_idle_sleep_sec must be > 0")

    # sudo 密码（可选），用于 iw 等需要 root 权限的命令
    sudo_password = device_cfg.get("sudo_password") or None

    local_dashboard_cfg = _parse_local_dashboard_config(
        raw.get("local_dashboard") or {},
        sender_plugins=plugins,
    )

    return RuntimeConfig(
        config_path=path,
        device_id=device_id,
        mqtt=mqtt_cfg,
        sender=sender_cfg,
        local_dashboard=local_dashboard_cfg,
        sudo_password=sudo_password,
    )


def _parse_local_dashboard_config(
    raw: Any,
    *,
    sender_plugins: dict[str, PluginConfig],
) -> LocalDashboardConfig:
    if not isinstance(raw, dict):
        raise ValueError("config.yaml: local_dashboard must be an object")

    default_limit = int(raw.get("default_ui_history_limit", 20))
    if default_limit < 0:
        raise ValueError("config.yaml: local_dashboard.default_ui_history_limit must be >= 0")

    auth_raw = raw.get("auth") or {}
    if not isinstance(auth_raw, dict):
        raise ValueError("config.yaml: local_dashboard.auth must be an object")
    auth_cfg = LocalDashboardAuthConfig(
        enabled=_to_bool(auth_raw.get("enabled"), default=False),
        token=str(auth_raw.get("token") or "").strip(),
    )

    vitals_raw = raw.get("vitals") or {}
    if not isinstance(vitals_raw, dict):
        raise ValueError("config.yaml: local_dashboard.vitals must be an object")

    vitals: dict[str, VitalUiConfig] = {}
    for vita_type, cfg in vitals_raw.items():
        if not isinstance(vita_type, str) or not vita_type.strip():
            raise ValueError("config.yaml: local_dashboard.vitals key must be non-empty string")
        if not isinstance(cfg, dict):
            raise ValueError(f"config.yaml: local_dashboard.vitals.{vita_type} must be an object")
        limit = int(cfg.get("ui_history_limit", default_limit))
        if limit < 0:
            raise ValueError(
                f"config.yaml: local_dashboard.vitals.{vita_type}.ui_history_limit must be >= 0"
            )
        vitals[vita_type] = VitalUiConfig(
            push_to_ui=_to_bool(cfg.get("push_to_ui"), default=True),
            ui_history_limit=limit,
        )

    port = int(raw.get("port", 8765))
    if port <= 0 or port > 65535:
        raise ValueError("config.yaml: local_dashboard.port must be in 1..65535")

    ws_path = str(raw.get("websocket_path", "/ws/live")).strip() or "/ws/live"
    if not ws_path.startswith("/"):
        ws_path = f"/{ws_path}"

    panel_order_raw = raw.get("panel_order")
    if panel_order_raw is None:
        panel_order: tuple[str, ...] = DEFAULT_UI_PANEL_ORDER
    else:
        if not isinstance(panel_order_raw, list) or not panel_order_raw:
            raise ValueError("config.yaml: local_dashboard.panel_order must be a non-empty list")
        panel_order = tuple(str(v).strip() for v in panel_order_raw if str(v).strip())
        if not panel_order:
            raise ValueError("config.yaml: local_dashboard.panel_order must contain vita_type names")

    return LocalDashboardConfig(
        enabled=_to_bool(raw.get("enabled"), default=False),
        host=str(raw.get("host", "0.0.0.0")).strip() or "0.0.0.0",
        port=port,
        show_mqtt_status=_to_bool(raw.get("show_mqtt_status"), default=True),
        default_ui_history_limit=default_limit,
        websocket_path=ws_path,
        panel_order=panel_order,
        vitals=vitals,
        auth=auth_cfg,
    )
