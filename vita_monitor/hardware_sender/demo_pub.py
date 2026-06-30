"""
验收用 demo：向公网 MQTT Broker 发布 heartbeat/status 体征数据。
运行前：pip install -r requirements.txt
配置文件：hardware_sender/config.yaml（host 必须为公网可达地址）
"""

from __future__ import annotations

import logging
import time

logging.basicConfig(level=logging.INFO)

from comm_infra.mqtt_infra import MqttSenderInfra  # noqa: E402


def main() -> int:
    infra = MqttSenderInfra()
    infra.set_last_will({"online": False, "status": "offline", "reason": "network_lost"})
    infra.connect()
    print(
        f"已连接公网 MQTT: {infra.host}:{infra.port}, device={infra.device_id}, "
        f"config={infra.config_path}"
    )
    try:
        infra.announce_online()
        for i in range(10):
            heartbeat = {
                "status": "online",
                "network_type": "wifi",
                "latency_ms": 30 + i,
                "rssi": -45,
                "IP_address": ["192.168.1.88", "203.0.113.8"],
            }
            infra.pub(heartbeat, "heartbeat", qos=0, data_mode="mock")
            print(f"已发布 heartbeat 至公网 MQTT: {heartbeat}")
            time.sleep(1.0)
    finally:
        try:
            infra.announce_offline()
        finally:
            infra.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
