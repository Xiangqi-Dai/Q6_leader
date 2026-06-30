from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import signal
import threading
import time
from queue import Empty
from typing import Any

from comm_infra.envelope import normalize_data_mode
from comm_infra.mqtt_infra import MqttSenderInfra
from local_dashboard import LocalDashboard
from plugins.plugin_base import BaseVitalPlugin
from utils.data_pool import create_info_pool
from utils.plugin_loader import build_enabled_plugins
from utils.process_manager import launch_plugins, shutdown_plugins
from utils.runtime_config import RuntimeConfig, load_runtime_config


logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hardware sender main process")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml (default: hardware_sender/config.yaml)",
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=None,
        help="Optional runtime for smoke test; omitted means run forever",
    )
    return parser


def _publish_from_pool(
    *,
    infra: MqttSenderInfra,
    local_dashboard: LocalDashboard,
    cfg: RuntimeConfig,
    stop_event: threading.Event,
    run_seconds: float | None = None,
) -> None:
    started_at = time.monotonic()
    info_pool = create_info_pool(maxsize=cfg.sender.info_pool_maxsize)
    plugins: list[BaseVitalPlugin] = build_enabled_plugins(config=cfg, info_pool=info_pool)
    if not plugins:
        logger.warning("no enabled plugins configured, publish loop will idle")

    launch_plugins(plugins)
    try:
        while not stop_event.is_set():
            if run_seconds is not None and time.monotonic() - started_at >= run_seconds:
                logger.info("run-seconds reached: %.2f, stopping", run_seconds)
                break
            try:
                item: dict[str, Any] = info_pool.get(timeout=cfg.sender.publish_idle_sleep_sec)
            except Empty:
                continue
            except (KeyboardInterrupt, InterruptedError):
                logger.info("publish loop interrupted, stopping gracefully")
                stop_event.set()
                break

            if not isinstance(item, dict):
                logger.warning("drop invalid pool item, expected dict: %r", item)
                continue

            vita_type = item.get("vita_type")
            vita_data = item.get("vita_data")
            qos = int(item.get("qos", 0))
            if not isinstance(vita_type, str) or not isinstance(vita_data, dict):
                logger.warning("drop invalid pool item schema: %r", item)
                continue
            try:
                data_mode = normalize_data_mode(item.get("data_mode"))
            except ValueError:
                logger.warning("drop invalid pool item data_mode: %r", item)
                continue

            # ① 内网优先
            try:
                local_dashboard.ingest(item)
            except Exception:
                logger.exception("local_dashboard ingest failed: type=%s", vita_type)

            # ② 公网 MQTT
            try:
                infra.pub(
                    vita_data=vita_data,
                    vita_type=vita_type,
                    qos=qos,
                    data_mode=data_mode,
                )
                local_dashboard.set_mqtt_connected(True)
                logger.info("published vital: type=%s data_mode=%s qos=%s", vita_type, data_mode, qos)
            except Exception as exc:
                local_dashboard.set_mqtt_connected(False, error=str(exc)[:120])
                logger.exception("publish failed: type=%s", vita_type)
    finally:
        shutdown_plugins(plugins)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    cfg = load_runtime_config(args.config)
    local_dashboard = LocalDashboard(cfg)
    stop_event = threading.Event()

    def _request_stop(signum: int, frame: object) -> None:
        if stop_event.is_set():
            return
        logger.info("received signal=%s, stopping...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    local_dashboard.start()

    infra = MqttSenderInfra(config_path=cfg.config_path)
    infra.set_last_will({"online": False, "status": "offline", "reason": "network_lost"})
    infra.connect()
    infra.announce_online()
    logger.info("hardware sender started: device_id=%s", cfg.device_id)

    try:
        try:
            _publish_from_pool(
                infra=infra,
                local_dashboard=local_dashboard,
                cfg=cfg,
                stop_event=stop_event,
                run_seconds=args.run_seconds,
            )
        except (KeyboardInterrupt, InterruptedError):
            logger.info("main loop interrupted, shutting down")
            stop_event.set()
    finally:
        try:
            infra.announce_offline()
        except Exception:
            logger.exception("announce_offline failed")
        finally:
            infra.disconnect()
        local_dashboard.stop()
    logger.info("hardware sender exited")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
