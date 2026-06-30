# 01 硬件发送器开发架构与规范

## 1. 模块定位

`hardware_sender` 运行在远程硬件或具身智能体本体上，负责完成“体征数据采集 -> 数据入池 -> 数据发送”的完整链路。

它不负责后端存储、告警、云端大屏展示。硬件端稳定职责是：按照统一协议持续产出体征数据，并通过通信 Infra 上报给后端；**可选**通过 `local_dashboard/` 在局域网提供本机实时监控页。

硬件发送器整体链路为：

```text
config.yaml
    |
    v
main.py 启动服务并加载插件
    |
    v
各体征 plugin 独立进程并发采集
    |
    v
数据池 info_pool
    |
    v
主发布循环（顺序双写：内网 → 公网）
    ├── ① local_dashboard.ingest()   # 内网自监控（可选，见 §8）
    └── ② comm_infra.pub(vita_data, vita_type)
            |
            v
    MQTT Broker -> backend_receiver
```

公网断联时，MQTT 发布可失败；若已启用 `local_dashboard`，局域网内仍可监控本机体征。详见 `docs/05_Hardware_Local_Dashboard_内网自监控.md`。

---

## 2. 目录职责划分

### 2.1 `comm_infra/`：通信 Infra

状态：已实现。

职责：

- 封装 MQTT 连接、鉴权、TLS、KeepAlive、Last Will、断线重连等通信细节。
- 封装硬件到后端的通用 Envelope。
- 根据 `device_id` 与 `vita_type` 自动映射 MQTT Topic。
- 对插件和主调度脚本暴露稳定 API：

```python
pub(vita_data: dict, vita_type: str)
```

约束：

- `comm_infra` 只处理通信，不允许出现任何具体体征采集逻辑。
- 业务层不允许手写 MQTT Topic。
- 业务层只传入体征业务数据 `vita_data` 与体征类型 `vita_type`。
- `vita_data` 的内部字段由对应体征 plugin 类自行定义，`comm_infra` 不理解也不校验其业务含义。

### 2.2 `utils/`：运行骨架工具

职责：

- 解析与校验 `config.yaml`。
- 管理插件加载。
- 管理并发进程生命周期。
- 管理数据池与队列。
- 提供通用 worker、scheduler、process manager 等能力。

设计原则：

- `main.py` 只保留最精炼的业务编排逻辑。
- 并发、数据池、插件扫描、配置校验等可复用能力都应下沉到 `utils/`。
- `utils/` 不写具体体征采集逻辑。

建议拆分：

```text
hardware_sender/utils/
├── runtime_config.py      # config.yaml 解析与结构化配置
├── plugin_loader.py       # 插件发现、导入、实例化
├── process_manager.py     # 插件进程 launch / shutdown 管理
├── data_pool.py           # 数据池结构、入池、取数、限流策略
└── scheduler.py           # 采集频率、循环调度、异常隔离
```

### 2.3 `helpers/`：共享辅助模块

与 `plugins`、`comm_infra` 同级，**不**作为 MQTT 体征插件注册，仅供插件或其它运行时代码复用。

```text
hardware_sender/helpers/
├── ros_common/          # ROS 2：字段路径、消息导入、PointCloud2/Pose 最小 JSON
├── network_info/        # 网络连通性探测（公网 + IP 对端），见下表
└── radio_sniffer/       # Linux WiFi 嗅探：iw/nmcli 扫描 + 信道占用聚合
```

`network_info/` 内部结构：

```text
network_info/
├── network_info.py              # 门面 NetworkInfo
└── func/
    ├── command_runner.py        # 子进程执行 ping 等
    ├── icmp_probe.py            # 共用 ICMP 命令构造与输出解析
    ├── connection_quality_collector.py  # 公网目标（8.8.8.8 / 1.1.1.1）
    ├── peer_connectivity_collector.py     # 配置的对端 IP 短测
    ├── network_type_collector.py
    └── ip_collector.py
```

| API | 用途 | 消费插件 |
| --- | --- | --- |
| `get_network_type()` / `get_my_ip()` / `get_connection_info()` | 公网链路与出网质量 | `heartbeat` |
| `probe_peers(peers, ...)` | 机器人 ↔ 配置 IP 设备连通性 | `ip_peer_monitor` |

详见 `docs/plugins/1. heartbeat.md`、`docs/plugins/5. ip_peer_monitor.md`。

约束：

- `helpers` 内不写 MQTT 发布、不写 `vita_type` 注册。
- 新增可复用能力时优先放入 `helpers/`，避免堆在单个 `plugins/<vita>/` 目录下。

### 2.4 `plugins/`：体征采集插件

职责：

- 每个插件只负责一种体征数据。
- 插件实现该体征的数据结构声明、采集逻辑、入池逻辑和生命周期管理。
- 新增体征时，优先新增插件文件，不修改 `comm_infra` 和主调度框架。

示例：

```text
hardware_sender/plugins/
├── heartbeat.py   # 生命体征 / 心跳数据
├── temperature.py # 温度体征
├── battery.py     # 电池体征
└── energy.py      # 能量 / 电量体征
```

### 2.5 `local_dashboard/`：内网自监控（可选）

状态：规划中（见 `docs/05_Hardware_Local_Dashboard_内网自监控.md`）。

职责：

- 从主发布循环 **优先** ingest `info_pool` 任务（先于 MQTT），不经过公网 Broker。
- 维护各 `vita_type` 的 `latest` 与 **ui_history 环形缓冲**（条数由 `ui_history_limit` 配置，默认 20）。
- 提供 REST + WebSocket + **纯 Python UI**（Jinja2 + Panel，`ui/`）。
- 由 **`main.py` 与发送器同进程启动**，无独立前端工程。

约束：

- 体征插件不直接调用 `local_dashboard`。
- `local_dashboard` 不写 MQTT、不替代 `backend_receiver`、不写 ClickHouse。
- 新增体征时，若需内网展示，须实现 `ui/panels/{vita_type}.py` 并配置 `local_dashboard.vitals.{vita_type}.ui_history_limit`。

### 2.6 `main.py`：主调度脚本

职责：

- 读取 `config.yaml`。
- 初始化通信 Infra 与（可选）Local Dashboard Infra，**在 `main.py` 中一并 `start()`**。
- 根据配置判断启用哪些插件。
- 启动插件进程。
- 从数据池中实时取出体征数据。
- **顺序双写**：**①** `local_dashboard.ingest` → **②** `comm_infra.pub(vita_data, vita_type)`。
- 处理退出信号，完成插件、Local Dashboard 和 MQTT 连接的优雅关闭。

约束：

- `main.py` 不写具体体征采集逻辑。
- `main.py` 不直接实现复杂并发细节。
- `main.py` 不关心插件内部如何采集数据，只关心插件是否把数据放入数据池。

---

## 3. 数据流与并发架构

### 3.1 基本原则

硬件发送器采用“插件独立采集 + 数据池统一发送”的架构。

原因：

- 不同体征采集频率不同，不能互相阻塞。
- 某个体征采集失败，不应影响其他体征。
- MQTT 发布链路应集中管理，避免多个插件各自创建连接。
- 数据进入统一数据池后，便于做限流、丢弃策略、优先级、日志与调试。

### 3.2 推荐进程模型

```text
主进程 main.py
├── LocalDashboard.start()（local_dashboard.enabled 时，与发送器同启）
├── 初始化 MqttSenderInfra.connect()
├── 创建 info_pool 数据池
├── 启动 plugin_heartbeat 进程
├── 启动 plugin_xxx 进程
└── 主循环：从 info_pool pick 数据
         ├── ① local_dashboard.ingest(item)
         └── ② infra.pub(vita_data, vita_type)
```

每个插件在自己的独立进程中循环执行：

```text
collect_vita_data()
    |
    v
put_data_to_pool()
    |
    v
sleep(interval_sec)
```

### 3.3 数据池内部数据结构

插件放入数据池的数据不等同于最终 MQTT Envelope。数据池里存放的是发送任务对象，由主调度脚本和通信 Infra 再包装成最终 Envelope。

建议结构：

```json
{
  "vita_type": "heartbeat",
  "data_mode": "real",
  "vita_data": {
    "status": "online",
    "rssi": -45,
    "network_type": "wifi",
    "latency_ms": 36,
    "IP_address": ["10.0.0.12", "203.0.113.8"]
  },
  "collected_at": 1715302000.123,
  "qos": 0
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `vita_type` | `string` | 是 | 体征类型，对应最终 Envelope 中的 `vita_type` |
| `data_mode` | `string` | 是 | `real` \| `mock`；由 `BaseVitalPlugin.put_data_to_pool` 根据配置注入 |
| `vita_data` | `object` | 是 | 体征业务数据，对应最终 Envelope 中的 `vita_data`（不含 `data_mode`） |
| `collected_at` | `number` | 是 | 插件采集到数据的时间 |
| `qos` | `number` | 否 | MQTT QoS，默认 `0` |

注意：上面的 `heartbeat` 只是示例。`vita_data` 内部业务字段由对应 plugin 类的 `vita_data_schema` 定义；`data_mode` 为传输层固定字段，见 `docs/user_docs/05_插件采集模式_真实与模拟.md` §5。

主调度脚本从数据池取出后执行映射：

```text
comm_infra.pub(vita_data=vita_data, vita_type=vita_type, data_mode=data_mode)
```

---

## 4. `config.yaml` 规范

`config.yaml` 是硬件发送器启动和插件启停的唯一配置入口。

建议结构：

```yaml
device:
  id: robot_demo_name

mqtt:
  host: broker.hivemq.com
  port: 1883
  use_tls: false
  username: null
  password: null
  keepalive: 60
  client_id: null

sender:
  default_data_mode: real          # 可选；插件未写 data_mode 时使用
  info_pool_maxsize: 1000
  publish_idle_sleep_sec: 0.2
  plugins:
    heartbeat:
      enabled: true
      data_mode: real              # real | mock
      class: plugins.heartbeat:HeartbeatVitalPlugin
      interval_sec: 1.0
      qos: 0
      kwargs: {}
      mock: {}                     # data_mode: mock 时生效，结构见各插件文档
    temperature:
      enabled: true
      data_mode: mock
      class: plugins.temperature:TemperatureVitalPlugin
      interval_sec: 5.0
      qos: 0
      kwargs:
        sensor_bus: 1
      mock:
        seed: 0
        celsius_range: [20.0, 28.0]
```

`local_dashboard` 段（可选，完整说明见 `docs/05_Hardware_Local_Dashboard_内网自监控.md` §6）：

```yaml
local_dashboard:
  enabled: true
  host: "0.0.0.0"
  port: 8765
  show_mqtt_status: true
  default_ui_history_limit: 20
  vitals:
    heartbeat:
      push_to_ui: true
      ui_history_limit: 20
    local_map:
      push_to_ui: false
      ui_history_limit: 0
  auth:
    enabled: false
    token: ""
```

配置约束：

- `sender.plugins` 的 key 必须等于插件的 `vita_type`。
- `enabled: false` 的插件不启动。
- `class` 使用 `module.path:ClassName` 形式。
- `interval_sec` 必须大于 `0`。
- `data_mode` 为 `real` 或 `mock`；缺省时继承 `sender.default_data_mode`，再缺省为 `real`。
- `kwargs` 只用于**真实采集**的初始化或采集参数，不允许放通信参数。
- `mock` 只用于**模拟数据**参数，不得与 `kwargs` 混用。
- 双模式完整约定见 `docs/user_docs/05_插件采集模式_真实与模拟.md`。

---

## 5. 插件基类规范

后续所有硬件端插件都必须基于统一基类扩展。该基类用于保证业务流一致：声明体征类型、声明数据结构、启动独立进程、采集数据、放入数据池、关闭进程。

### 5.1 插件必须具备的属性

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `vita_type` | `str` | 体征唯一标识，对应通信 Envelope 中的 `vita_type` |
| `vita_data_schema` | `dict` 或类型声明 | 该体征 `vita_data` 的数据结构定义，由该 plugin 类自行维护 |
| `process` | `multiprocessing.Process | None` | 插件自己的独立采集进程 |
| `interval_sec` | `float` | 采集周期 |
| `qos` | `int` | MQTT QoS |

### 5.2 插件必须具备的方法

| 方法 | 说明 |
| --- | --- |
| `collect_real_vita_data()` | 真实采集一次，返回 `vita_data: dict` |
| `collect_mock_vita_data()` | 模拟采集一次，返回与真实模式同形的 `vita_data: dict` |
| `collect_vita_data()` | **基类实现**：按 `data_mode` 分发到上述二者，子类不得覆盖 |
| `put_data_to_pool(vita_data)` | 把采集结果封装为数据池任务对象，并放入 `info_pool` |
| `launch()` | 启动插件独立进程，在进程中循环执行采集与入池 |
| `shutdown()` | 停止插件独立进程，并释放资源 |

### 5.3 插件基类伪代码

```python
class BaseVitalPlugin:
    vita_type: str
    vita_data_schema: dict

    def __init__(
        self, *, info_pool, interval_sec: float, qos: int = 0,
        data_mode: str = "real", mock_config: dict | None = None, **kwargs
    ):
        self.info_pool = info_pool
        self.interval_sec = interval_sec
        self.qos = qos
        self.data_mode = data_mode  # "real" | "mock"
        self.mock_config = mock_config or {}
        self.kwargs = kwargs
        self.process = None

    def collect_vita_data(self) -> dict:
        if self.data_mode == "mock":
            return self.collect_mock_vita_data()
        return self.collect_real_vita_data()

    def collect_real_vita_data(self) -> dict:
        raise NotImplementedError

    def collect_mock_vita_data(self) -> dict:
        raise NotImplementedError

    def put_data_to_pool(self, vita_data: dict) -> None:
        item = {
            "vita_type": self.vita_type,
            "data_mode": self.data_mode,
            "vita_data": vita_data,
            "collected_at": time.time(),
            "qos": self.qos,
        }
        self.info_pool.put(item)

    def launch(self) -> None:
        # 启动独立进程，循环执行 collect_vita_data -> put_data_to_pool
        ...

    def shutdown(self) -> None:
        # 通知进程退出，必要时 terminate
        ...
```

### 5.4 插件开发流程

新增一个体征插件时，必须按以下步骤执行：

1. 在该 plugin 类中定义该体征的 `vita_type` 和 `vita_data_schema`，必要时同步补充到文档。
2. 在 `plugins/` 下创建对应插件模块（建议含 `mock_generator.py`）。
3. 继承 `BaseVitalPlugin`。
4. 实现 `collect_real_vita_data()` 与 `collect_mock_vita_data()`。
5. 确保 `put_data_to_pool()` 放入的数据满足数据池结构。
6. 在 `config.yaml` 的 `sender.plugins` 中添加该插件（含 `data_mode` 与 `mock` 示例）。
7. 分别以 `data_mode: mock` 与 `real` 启动 `main.py`，验证数据能进入后端对应 `sub(vita_type)`。

---

## 6. 生命周期与异常处理

### 6.1 启动流程

```text
main.py
  -> 读取 config.yaml
  -> LocalDashboard.start()（若 enabled）
  -> 初始化 MqttSenderInfra
  -> 创建 info_pool
  -> 加载 enabled 插件
  -> 调用每个插件的 launch()
  -> 进入顺序双写发布循环（先 ingest 后 pub）
```

### 6.2 关闭流程

```text
收到 SIGINT / SIGTERM
  -> main.py 停止发布循环
  -> 调用每个插件 shutdown()
  -> 清理进程和数据池
  -> 停止 LocalDashboardInfra
  -> 断开 MQTT 连接
  -> 退出
```

### 6.3 异常隔离原则

- 单个插件采集失败，只记录该插件错误，不影响其他插件。
- 插件连续失败时，应进入降频或熔断策略，避免刷日志和占满 CPU。
- 数据池满时，默认允许丢弃低优先级体征数据，并记录 warning。
- `heartbeat` 体征优先级最高，后续数据池策略应保证心跳数据优先发送。
- MQTT `pub` 失败时不得影响已完成的 `local_dashboard.ingest`；内网监控优先于公网上报。

---

## 8. 内网自监控（Local Dashboard）

硬件端可在公网 MQTT 之外，向局域网浏览器提供本机监控能力。设计细节、API 子集、前端嵌入与验收标准见：

**`docs/05_Hardware_Local_Dashboard_内网自监控.md`**

现场访问示例：`http://<机器人局域网 IP>:8765`

---

## 9. 生命体征相关 TODO

生命体征是第一个必须打通的体征插件。其基础含义是：表明智能体在线状态、存活状态，以及与服务器之间的通信状态。

TODO：调研并设计“主系统关机或死机后仍可发送心跳/关机状态”的硬件方案。

初步方向：

- 引入独立低功耗 MCU 或硬件看门狗模块。
- MCU 拥有独立供电或备用电源。
- 主系统正常运行时定期向 MCU 喂狗或同步状态。
- 主系统关机、死机或掉电后，由 MCU 发送“主系统不可用”的低频状态数据。