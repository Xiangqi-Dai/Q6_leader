# Local Dashboard（内网自监控）

`hardware_sender` 可选模块：公网 MQTT 断联时，通过局域网浏览器查看本机体征。

- **纯 Python UI**：Jinja2 模板 + `ui/panels/` Panel 模块
- **main.py 同启**：`LocalDashboard.start()` 与 MQTT、插件采集同一进程
- **发送顺序**：主循环 **先** `ingest` **再** MQTT `pub`
- **短历史**：`state_store` 内按 plugin 环形缓冲，默认 20 条（`ui_history_limit`）

## 访问

```text
http://<机器人局域网 IP>:8765
```

`config.yaml` → `local_dashboard.enabled: true`

## 目录

```text
local_dashboard/
├── service.py       # LocalDashboard 入口（ingest / start / stop）
├── infra/           # state_store、WebSocket、FastAPI
├── templates/       # Jinja2 页面与 partials
└── ui/
    ├── panels/      # 各 vita_type 的 Python Panel
    └── static/      # CSS + 极简 WS 客户端
```

完整设计见 [`docs/05_Hardware_Local_Dashboard_内网自监控.md`](../../docs/05_Hardware_Local_Dashboard_内网自监控.md)。
