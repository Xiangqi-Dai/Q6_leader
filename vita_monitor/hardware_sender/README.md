# 硬件发送器 (Hardware Sender)

本项目遵循“基础设施先行，按功能模块垂直且插件化迭代”的核心开发规范。
这里是运行在具身智能体（开发板）上的**硬件发送器**。

## 架构与代码存放规范

为了保证后续新增体征数据时可以“插件化热插拔”，发送器采用多进程解耦架构：

*   **`comm_infra/` (通信 Infra 骨架)**
    *   存放所有的核心通信基础设施代码。
    *   封装底层 MQTT 客户端的连接、鉴权、重连机制。
    *   **职责约束**：对外暴露极简的 API，例如 `pub(data: dict, name: str)`，供业务插件调用，禁止在此处编写任何具体的体征采集逻辑。
*   **`helpers/` (共享辅助模块)**
    *   与 `plugins`、`comm_infra` 同级，供多个插件复用。
    *   `helpers/ros_common/`：ROS 2 话题字段路径、PointCloud2 / PoseStamped JSON 序列化（`local_map`、`local_pose` 使用）。
    *   `helpers/network_info/`：网络类型、IP 路径、延迟/丢包/RSSI 等（`heartbeat` 使用）。
*   **`plugins/` (体征采集插件)**
    *   每个体征类型一个插件包（如 `heartbeat/`、`local_map/`）。
    *   插件实现 `collect_vita_data()`，由独立进程周期执行；可调用 `helpers` 中的能力。
*   **`local_dashboard/` (内网自监控，可选)**
    *   主循环 **先** `ingest` **后** MQTT；维护 latest + 按 plugin 可配置短历史（默认 20 条）。
    *   **纯 Python UI**（Jinja2 + Panel，`ui/`），由 **`main.py` 与 sender 同启**。
    *   详见 [`docs/05_Hardware_Local_Dashboard_内网自监控.md`](../docs/05_Hardware_Local_Dashboard_内网自监控.md)。
*   **`main.py` (主调度脚本)**
    *   主运行链路：`LocalDashboard.start（可选）→ MQTT connect → 插件采集 → info_pool → 顺序双写`。
    *   主循环：**①** `local_dashboard.ingest` → **②** `infra.pub`；MQTT 失败不影响 ingest。

## 配置说明

通信参数统一放在 `config.yaml`，由用户直接修改，不再从环境变量读取。默认配置指向公网 MQTT Broker。

关键配置项：

*   `sender.info_pool_maxsize`：主信息池容量（插件进程 -> 主发布循环）。
*   `sender.publish_idle_sleep_sec`：主发布循环取数超时时间。
*   `sender.plugins`：体征类型插件映射；支持直接在配置中新增或修改体征类型。
    *   `class`：插件类导入路径，格式 `module.path:ClassName`。
    *   `interval_sec`：采集周期（秒）。
    *   `qos`：MQTT QoS（0/1/2）。
    *   `enabled`：是否启用该插件。
    *   `kwargs`：透传给插件构造函数的参数。
*   `local_dashboard`：内网自监控（可选），含 `default_ui_history_limit`（默认 20）及 per-plugin `ui_history_limit`。

## 插件开发规范

1. 在 `plugins/` 新建插件包，例如 `plugins/heartbeat/plugin.py`。
2. 继承 `BaseVitalPlugin`，实现 `collect_vita_data()`。
3. 在 `config.yaml` 的 `sender.plugins` 新增映射（**键名 = `vita_type`**）。
4. 若启用 Local Dashboard，增加 `local_dashboard/ui/panels/{vita_type}.py` 并配置 `local_dashboard.vitals.{vita_type}`。
5. 重启 `main.py` 后生效，主调度代码无需改动。

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动发送器主服务（含内网 UI，若已 enabled）：

```bash
python main.py
```

运行公网 MQTT 发布 demo：

```bash
python demo_pub.py
```

### 内网自监控

启用 `local_dashboard.enabled: true` 后，与 `python main.py` 一并启动，局域网访问：

```text
http://<机器人局域网 IP>:8765
```

## 说明

*   `demo_pub.py` 会发送 `status` 与 `heartbeat`，用于验证“硬件 -> 公网 MQTT -> 后端”的发送链路。
*   `config.yaml` 中 `mqtt.host` 必须配置为公网可达 Broker，`localhost/127.0.0.1/::1` 会被拒绝（内网监控不走 MQTT，走 `local_dashboard` HTTP 服务）。
