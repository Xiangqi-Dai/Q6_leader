# 05 硬件端内网自监控（Local Dashboard）

## 1. 模块定位

`hardware_sender/local_dashboard/` 是运行在**机器人本体**上的可选模块，在公网 MQTT 断联时，仍可通过**局域网 HTTP/WebSocket** 查看本机体征。

设计原则（已定稿）：

| 原则 | 说明 |
| --- | --- |
| **归属 hardware_sender** | 代码与配置均在 `hardware_sender` 内，不依赖 `frontend_dashboard` 或 `backend_receiver` |
| **纯 Python UI** | 页面由 Python（FastAPI + Jinja2）维护，**无独立前端工程**，无需 `npm` / `web/js/` |
| **与 main.py 同启** | `LocalDashboard` 在 `main.py` 中与 MQTT、插件一并启动与关闭 |
| **发送顺序** | 主发布循环：**先** `local_dashboard.ingest`，**再** `comm_infra.pub`（内网优先，公网其次） |
| **UI 内短历史** | 在 Local Dashboard 模块内按 plugin 维护环形历史（默认 20 条），供轻量 UI 展示；**不写 ClickHouse** |
| **与云端并行** | 不替代云端多设备监控；公网恢复后 MQTT 上报与内网监控同时工作 |

访问示例：

```text
http://<机器人局域网 IP>:8765
```

---

## 2. 系统拓扑

### 2.1 与云端链路的关系

```text
                    ┌── MQTT ──▶ Broker ──▶ backend_receiver ──▶ frontend_dashboard
                    │         （公网，可断联；内网 ingest 之后执行）
hardware_sender     │
  体征插件          │
    │               │
    ▼               │
 info_pool          │
    │               │
    ▼               │
 主发布循环 ─────────┘
    │
    │  ① local_dashboard.ingest()   ← 始终先执行（若 enabled）
    │  ② comm_infra.pub()           ← 其后执行；失败不回头影响 ①
    │
local_dashboard（main.py 同进程启动）
    ├── state_store   latest + ui_history（环形，按 plugin 配置条数）
    ├── REST          /api/health, /api/snapshot
    ├── WS            /ws/live
    └── ui/           Python 模板 + Panel 模块渲染页面
            │
            ▼
     局域网浏览器
```

### 2.2 数据流与发送顺序

```text
info_pool 任务
        │
        ▼
① local_dashboard.ingest(item)
        │
        ├── state_store.append(vita_type, snapshot)
        │     ├── latest 覆盖更新
        │     └── ui_history deque append（超出 ui_history_limit 则丢弃最旧）
        ├── ws_hub.broadcast(vital.updated)     # 含可选 history 摘要
        └── ui 层 Panel 可读 history 渲染曲线/列表
        │
        ▼
② comm_infra.pub(vita_data, vita_type)        # 公网 MQTT，可失败
        │
        └── 更新 mqtt_connected 状态供顶栏展示
```

**不做的事：**

- 不写入 ClickHouse / SQLite / 磁盘持久化历史
- 不提供与云端对齐的 `GET .../history` 长周期查询
- 不维护独立前端仓库或 Node 构建流程

**刷新浏览器后：** 短历史仍在服务端 `state_store.ui_history` 中（进程存活期间有效）；进程重启后清空。

---

## 3. 目录结构

```text
hardware_sender/local_dashboard/
├── __init__.py
├── README.md
│
├── infra/                         # 服务与状态
│   ├── __init__.py
│   ├── state_store.py             # latest + ui_history（deque）
│   ├── ws_hub.py                  # WebSocket 广播
│   └── server.py                  # FastAPI 应用工厂：REST + WS + 挂载 ui
│
└── ui/                            # 纯 Python 前端（Jinja2 + Panel 模块）
    ├── __init__.py
    ├── routes.py                  # 页面路由，注册 Panel
    ├── panels/
    │   ├── __init__.py
    │   ├── registry.py            # vita_type → Panel 类
    │   ├── base.py                # BasePanel：render_html(context)
    │   ├── heartbeat.py
    │   ├── air_sniffer.py
    │   ├── radio_sniffer.py
    │   ├── local_pose.py
    │   └── local_map.py
    ├── templates/
    │   ├── layout.html            # 顶栏、MQTT 状态、Panel 槽位
    │   └── partials/              # 各 Panel 对应的 Jinja 片段（可由 Panel 指定）
    └── static/                    # 仅 CSS / 少量内联 WS 客户端 JS（可选）
        └── main.css
```

与现有模块的边界：

| 目录 | 关系 |
| --- | --- |
| `plugins/` | 采集插件不变；不感知 local_dashboard |
| `comm_infra/` | MQTT 不变；`pub` 在 `ingest` 之后执行 |
| `main.py` | 创建并启动 `LocalDashboard`，编排启动/关闭顺序 |
| `frontend_dashboard/` | **无依赖** |

---

## 4. Infra 设计

### 4.1 `state_store.py`

```python
@dataclass(frozen=True)
class VitalSnapshot:
    device_id: str
    vita_type: str
    vita_data: dict[str, Any]
    collected_at: float

class LocalStateStore:
    latest: dict[str, VitalSnapshot]
    ui_history: dict[str, deque[VitalSnapshot]]   # 按 vita_type， maxlen 来自配置
    mqtt_connected: bool
    mqtt_last_error: str | None
```

- `append(item)`：更新 `latest`；向 `ui_history[vita_type]` 追加，长度超过该 plugin 的 `ui_history_limit` 时弹出最旧。
- `get_snapshot()`：返回 `{ vita_type: { latest, history: [...] } }`，供 REST 与首屏渲染。
- 大载荷（如 `local_map`）可通过 `push_to_ui: false` 跳过 UI 与 history。

### 4.2 REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务存活、`mqtt_connected`、`server_time` |
| `GET` | `/api/snapshot` | 各体征 `latest` + `history`（条数 ≤ 各 plugin `ui_history_limit`） |
| `GET` | `/api/meta` | `device_id`、已启用且 `push_to_ui` 的 plugin 列表 |
| `WS` | `/ws/live` | 推送 `vital.updated`（可带 `history` 或仅 latest，由实现定） |
| `GET` | `/` | Jinja 渲染监控主页（Python Panel 组装 HTML） |

不提供云端式长时间窗 history API。

### 4.3 WebSocket 事件示例

```json
{
  "event": "vital.updated",
  "device_id": "lijing_brain",
  "vita_type": "heartbeat",
  "collected_at": 1715302000.123,
  "vita_data": { "latency_ms": 36, "rssi_dbm": -45 },
  "history_count": 20
}
```

系统事件：

```json
{ "event": "mqtt.status", "connected": false, "message": "publish timeout" }
```

### 4.4 `main.py` 集成（启动与发送顺序）

**启动顺序：**

```text
main.py
  -> load_runtime_config()
  -> LocalDashboard.start()          # enabled 时：FastAPI/uvicorn 后台线程
  -> MqttSenderInfra.connect()
  -> create info_pool + launch plugins
  -> publish loop
```

**发布循环（严格顺序）：**

```python
item = info_pool.get(...)
if local_dashboard.enabled:
    local_dashboard.ingest(item)       # ① 内网优先
try:
    infra.pub(vita_data=..., vita_type=...)   # ② 公网其次
    local_dashboard.set_mqtt_connected(True)
except Exception:
    local_dashboard.set_mqtt_connected(False)
```

**关闭顺序：** 停止发布循环 → shutdown plugins → `LocalDashboard.stop()` → MQTT disconnect。

`LocalDashboard` 的构造与 `start()`/`stop()` 均在 `main.py`（或 `main` 调用的薄封装）中完成，**不**单独再起一个发送器进程。

---

## 5. 纯 Python UI 设计

### 5.1 技术选型

| 项 | 选择 |
| --- | --- |
| 服务端渲染 | **Jinja2** 模板 |
| Panel 逻辑 | Python 类 `BasePanel.render(context) -> str` 或指定 template |
| 实时刷新 | WebSocket 推送 + 极简客户端 JS（仅 WS 连接与 DOM 局部更新），或 HTMX |
| 样式 | `ui/static/main.css` |
| 图表 | 可选：服务端生成 SVG / 模板内简单表格；或嵌入轻量 chart 库静态文件 |

**不采用：** Vue/React 工程、`local_dashboard/web/js/panels/` 独立维护。

### 5.2 Panel 注册与扩展

新增体征内网展示：

1. `ui/panels/{vita_type}.py`：继承 `BasePanel`，实现 `render_latest` / `render_history`（若需小曲线）。
2. `registry.py` 注册。
3. `config.yaml` 的 `local_dashboard.vitals.{vita_type}` 配置 `ui_history_limit`（默认 20）。

Panel 直接消费硬件 `vita_data`（见 `docs/plugins/`）。

### 5.3 页面布局（首版）

```text
┌─────────────────────────────────────────┐
│  [device_id]  [MQTT: 已连接/断联]        │
├─────────────────────────────────────────┤
│  Heartbeat：当前值 + 最近 N 条简表/折线   │
├─────────────────────────────────────────┤
│  Air Sniffer：当前值 + 最近 N 条          │
├─────────────────────────────────────────┤
│  Radio Sniffer：当前扫描 + 最近 N 条摘要   │
└─────────────────────────────────────────┘
```

---

## 6. 配置规范

```yaml
local_dashboard:
  enabled: true
  host: "0.0.0.0"
  port: 8765
  show_mqtt_status: true

  # 全局默认；单个 plugin 可覆盖
  default_ui_history_limit: 20

  vitals:
    heartbeat:
      push_to_ui: true
      ui_history_limit: 20      # 省略则用 default_ui_history_limit
    air_sniffer:
      push_to_ui: true
      # ui_history_limit 省略 → 20
    radio_sniffer:
      push_to_ui: true
      ui_history_limit: 10
    local_map:
      push_to_ui: false         # 不 ingest 到 UI / history
      ui_history_limit: 0
    local_pose:
      push_to_ui: true
      ui_history_limit: 20

  auth:
    enabled: false
    token: ""
```

| 字段 | 说明 |
| --- | --- |
| `default_ui_history_limit` | 默认 **20**；各 plugin 未单独配置时使用 |
| `vitals.{name}.ui_history_limit` | 该体征在 Local Dashboard 内存中保留的条数；`0` 表示只保留 latest |
| `vitals.{name}.push_to_ui` | `false` 时不进入 ingest / UI / history |

---

## 7. 依赖

`hardware_sender/requirements.txt`（实现阶段）：

```text
fastapi>=0.115.0,<1
uvicorn[standard]>=0.32.0,<1
jinja2>=3.1.0,<4
```

---

## 8. 新增体征协作清单

| 步骤 | 位置 |
| --- | --- |
| 1 | `plugins/{vita}/` 硬件采集插件 |
| 2 | `config.yaml` `sender.plugins` + `local_dashboard.vitals.{vita}` |
| 3 | `local_dashboard/ui/panels/{vita}.py` + `registry.py` |
| 4 | 可选 `ui/templates/partials/{vita}.html` |
| 5 | `docs/plugins/` 补充字段说明 |

---

## 9. 实施阶段

### Phase 1 — MVP

- [ ] `state_store`（latest + ui_history deque）
- [ ] `server.py` + `ui/routes.py` + Jinja layout
- [ ] `main.py`：同启 LocalDashboard；发布循环 **先 ingest 后 pub**
- [ ] `heartbeat` Panel + 默认 20 条历史展示
- [ ] 验收：断网 LAN 可访问；ingest 先于 MQTT 日志顺序可验证

### Phase 2

- [ ] `air_sniffer`、`radio_sniffer` Panel
- [ ] `runtime_config` 解析 `local_dashboard` 与 per-plugin `ui_history_limit`
- [ ] WebSocket 实时刷新

### Phase 3（可选）

- [ ] `local_pose` / `local_map`（受 `push_to_ui` 控制）
- [ ] `auth.token`
- [ ] 插件进程存活指示

---

## 10. 验收标准

1. **发送顺序**：每条 info_pool 数据先出现在内网 snapshot/history，再尝试 MQTT。
2. **公网断联**：内网页持续更新；顶栏 MQTT 断联；ingest 不受影响。
3. **短历史**：各 plugin 历史条数不超过配置的 `ui_history_limit`（默认 20）。
4. **纯 Python UI**：仓库无 `local_dashboard/web/js` 工程；页面由 Jinja + Panel 模块输出。
5. **main.py 同启**：仅 `python main.py` 即可同时提供采集、MQTT、内网 UI。

---

## 11. 安全与运维

- 绑定 `0.0.0.0` 时 LAN 内均可访问；可配合防火墙或 `auth.token`。
- 内存上界 ≈ Σ(各 plugin `ui_history_limit` × 单条 `vita_data` 大小)；`local_map` 默认 `push_to_ui: false`。
- 内网页不暴露 MQTT 密码。

---

## 12. 延伸阅读

- `docs/01_Hardware_硬件发送器.md` §8
- `docs/00_Architecture_整体架构.md` §2.5、§4.1
- `docs/user_docs/01_通信路线_从智能体到前端.md` §6
- `docs/03_Frontend_前端展示.md` §7（与云端大屏关系）
