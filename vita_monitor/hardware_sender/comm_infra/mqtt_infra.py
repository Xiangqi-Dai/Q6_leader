"""硬件端 MQTT 通信 Infra：连接公网 Broker，提供 pub(vita_data, vita_type)。"""

from __future__ import annotations

import logging
import ipaddress
import ssl
import socket
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import yaml
from paho.mqtt.enums import CallbackAPIVersion

from .envelope import build_envelope, topic_for_vital

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_CONNECT_TIMEOUT_SEC = 30
_PUBLISH_TIMEOUT_SEC = 10
_RECONNECT_INTERVAL_SEC = 3


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


def _load_connection_params(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    从 config.yaml 读取连接参数（不再从环境变量读取）。
    默认使用公网 Broker，禁止 localhost，确保 demo 和联调走公网。
    """
    cfg_path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    cfg = _read_yaml(cfg_path)

    mqtt_cfg = cfg.get("mqtt") or {}
    if not isinstance(mqtt_cfg, dict):
        raise ValueError("config.yaml: mqtt must be an object")

    device_cfg = cfg.get("device") or {}
    if not isinstance(device_cfg, dict):
        raise ValueError("config.yaml: device must be an object")

    host = str(mqtt_cfg.get("host", "")).strip()
    if not host:
        raise ValueError("config.yaml: mqtt.host is required")
    if host.lower() in _LOCAL_HOSTS:
        raise ValueError("config.yaml: mqtt.host cannot be localhost/127.0.0.1/::1")
    _ensure_public_host(host)

    device_id = str(device_cfg.get("id", "")).strip()
    if not device_id:
        raise ValueError("config.yaml: device.id is required")

    return {
        "config_path": str(cfg_path),
        "host": host,
        "port": int(mqtt_cfg.get("port", 1883)),
        "use_tls": _to_bool(mqtt_cfg.get("use_tls"), default=False),
        "username": mqtt_cfg.get("username"),
        "password": mqtt_cfg.get("password"),
        "device_id": device_id,
        "keepalive": int(mqtt_cfg.get("keepalive", 60)),
        "client_id": mqtt_cfg.get("client_id"),
    }


def _ensure_public_host(host: str) -> None:
    """
    约束 MQTT 必须走公网：
    - 禁止 localhost / 私网 IP / 链路本地地址
    - 域名场景放行（交由 DNS 与网络环境决定）
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 域名无法在本地静态判断是否公网，允许继续连接。
        return

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        logger.warning(
            "mqtt.host is not a public endpoint (%r); continuing by request, "
            "but public broker is recommended for remote deployment",
            host,
        )


class MqttSenderInfra:
    """
    硬件发送器通信骨架：仅负责 MQTT 连接与发布，不含任何体征采集逻辑。
    """

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        host: str | None = None,
        port: int | None = None,
        use_tls: bool | None = None,
        username: str | None = None,
        password: str | None = None,
        device_id: str | None = None,
        keepalive: int | None = None,
        client_id: str | None = None,
    ) -> None:
        p = _load_connection_params(config_path)
        self._config_path = p["config_path"]
        self._host = host if host is not None else p["host"]
        self._port = port if port is not None else p["port"]
        self._use_tls = use_tls if use_tls is not None else p["use_tls"]
        self._username = username if username is not None else p["username"]
        self._password = password if password is not None else p["password"]
        self._device_id = device_id if device_id is not None else p["device_id"]
        self._keepalive = keepalive if keepalive is not None else p["keepalive"]

        cid = client_id or p["client_id"] or f"hw-{self._device_id}"
        self._client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid)
        if self._username is not None:
            self._client.username_pw_set(self._username, self._password)

        self._client.on_connect = self._on_connect

        if self._use_tls:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

        self._connected = threading.Event()
        self._connect_abort = threading.Event()
        self._lock = threading.Lock()
        self._loop_started = False
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_disconnect = self._on_disconnect

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def config_path(self) -> str:
        return self._config_path

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        failed = getattr(reason_code, "is_failure", None)
        if failed is True:
            logger.error("MQTT connect failed: %s", reason_code)
            return
        if failed is None:
            try:
                if int(reason_code) != 0:
                    logger.error("MQTT connect failed: %s", reason_code)
                    return
            except (TypeError, ValueError):
                pass
        logger.info("MQTT connected to %s:%s (TLS=%s)", self._host, self._port, self._use_tls)
        self._connected.set()
        # 每次连接/重连都覆盖 broker 上可能残留的 LWT 离线 retain 消息。
        # 注意：不能在 on_connect 回调中调用 wait_for_publish，因为 PUBACK 需要
        # 同一个网络循环线程来处理，会造成死锁。此处使用非阻塞 fire-and-forget。
        try:
            topic = f"robot/{self._device_id}/status"
            payload = build_envelope(
                device_id=self._device_id,
                vita_type="status",
                vita_data={"online": True, "status": "online", "reason": "reconnect", "reported_at": time.time()},
            )
            self._client.publish(topic, payload, qos=1, retain=True)
            logger.info("announced online (fire-and-forget) on connect")
        except Exception:
            logger.exception("announce_online on connect failed")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        self._connected.clear()
        if getattr(reason_code, "is_failure", False):
            logger.warning("MQTT disconnected unexpectedly: %s", reason_code)
        else:
            logger.info("MQTT disconnected: %s", reason_code)

    def _cleanup_connect_attempt(self) -> None:
        """单次连接失败后清理半连接状态，便于下一次重试。"""
        with self._lock:
            if self._loop_started:
                try:
                    self._client.loop_stop()
                except Exception:
                    logger.debug("loop_stop during connect cleanup failed", exc_info=True)
                self._loop_started = False
            self._connected.clear()
            try:
                self._client.disconnect()
            except Exception:
                logger.debug("disconnect during connect cleanup failed", exc_info=True)

    def _connect_once(self) -> None:
        """尝试建立一次 MQTT 连接；失败时抛出 ConnectionError 或 TimeoutError。"""
        with self._lock:
            if self._connected.is_set():
                return
            self._connected.clear()

            # 先做 DNS 解析，尽早暴露公网地址配置错误。
            try:
                socket.getaddrinfo(self._host, self._port, proto=socket.IPPROTO_TCP)
            except socket.gaierror as e:
                raise ConnectionError(
                    f"MQTT host resolve failed: {self._host}:{self._port}"
                ) from e

            try:
                self._client.connect(self._host, self._port, keepalive=self._keepalive)
            except OSError as e:
                raise ConnectionError(
                    f"MQTT TCP connect failed: {self._host}:{self._port}"
                ) from e

            if not self._loop_started:
                self._client.loop_start()
                self._loop_started = True

        if not self._connected.wait(timeout=_CONNECT_TIMEOUT_SEC):
            self._cleanup_connect_attempt()
            raise TimeoutError(f"MQTT connect timeout: {self._host}:{self._port}")

    def connect(self) -> None:
        """
        阻塞直到 MQTT 连接成功。
        开机阶段网络未就绪时可能触发 OSError / DNS 失败 / 握手超时，将每 3 秒重试一次。
        """
        with self._lock:
            if self._connected.is_set():
                return
            self._connect_abort.clear()

        while not self._connect_abort.is_set():
            try:
                self._connect_once()
                return
            except (ConnectionError, TimeoutError, OSError) as exc:
                if self._connect_abort.is_set():
                    return
                logger.warning(
                    "MQTT connect failed (%s), retrying in %ss...",
                    exc,
                    _RECONNECT_INTERVAL_SEC,
                )
                self._cleanup_connect_attempt()
                if self._connect_abort.wait(_RECONNECT_INTERVAL_SEC):
                    return

    def disconnect(self) -> None:
        self._connect_abort.set()
        with self._lock:
            if self._loop_started:
                self._client.loop_stop()
                self._loop_started = False
            try:
                self._client.disconnect()
            except Exception:
                logger.debug("disconnect failed", exc_info=True)
            self._connected.clear()

    def pub(
        self,
        vita_data: dict[str, Any],
        vita_type: str,
        *,
        qos: int = 0,
        data_mode: str = "real",
    ) -> None:
        """
        发布一条体征数据。vita_data 为业务字段；vita_type 为体征标识（与后端 sub(vita_type) 对应）。
        """
        if not isinstance(vita_type, str) or not vita_type.strip():
            raise ValueError("vita_type must be a non-empty string")
        if not isinstance(vita_data, Mapping):
            raise ValueError("vita_data must be a mapping object")

        if not self._connected.is_set():
            self.connect()
        topic = topic_for_vital(self._device_id, vita_type)
        payload = build_envelope(
            device_id=self._device_id,
            vita_type=vita_type,
            vita_data=dict(vita_data),
            data_mode=data_mode,
        )
        info = self._client.publish(topic, payload, qos=qos)
        info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_SEC)
        if not info.is_published():
            raise TimeoutError(f"MQTT publish timeout: topic={topic!r}")

    def set_last_will(
        self,
        offline_payload: dict[str, Any] | None = None,
        *,
        qos: int = 1,
        retain: bool = True,
    ) -> None:
        """设置遗嘱（必须在首次 connect 之前调用）。发布至 robot/{id}/status。"""
        topic = f"robot/{self._device_id}/status"
        body = offline_payload or {"online": False, "reason": "lwt"}
        will = build_envelope(
            device_id=self._device_id,
            vita_type="status",
            vita_data=body,
        )
        self._client.will_set(topic, will, qos=qos, retain=retain)

    def publish_status(self, status_data: Mapping[str, Any], *, qos: int = 1, retain: bool = True) -> None:
        """主动发布设备状态，默认发送到 robot/{device_id}/status。"""
        if not self._connected.is_set():
            self.connect()
        topic = f"robot/{self._device_id}/status"
        payload = build_envelope(
            device_id=self._device_id,
            vita_type="status",
            vita_data=dict(status_data),
        )
        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        info.wait_for_publish(timeout=_PUBLISH_TIMEOUT_SEC)
        if not info.is_published():
            raise TimeoutError(f"MQTT publish timeout: topic={topic!r}")

    def announce_online(self) -> None:
        """发送上线状态，便于后端与前端快速更新设备在线态。"""
        self.publish_status(
            {"online": True, "status": "online", "reason": "boot", "reported_at": time.time()}
        )

    def announce_offline(self) -> None:
        """主动发送离线状态（优雅退出时调用）。"""
        self.publish_status(
            {"online": False, "status": "offline", "reason": "shutdown", "reported_at": time.time()}
        )
