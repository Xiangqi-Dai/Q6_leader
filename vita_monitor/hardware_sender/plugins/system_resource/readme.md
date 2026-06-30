# system_resource 发送端插件

采集机器人本机 **CPU / 内存 / GPU** 占用与 **CPU / GPU 温度** 指标，经 MQTT 上报。

- 类：`SystemResourceVitalPlugin`
- `vita_type`：`system_resource`
- 依赖：`psutil`（必须）；`nvidia-smi`（可选，无 GPU 时自动跳过）
- CPU 温度：`psutil.sensors_temperatures()` 优先，Linux `/sys/class/thermal` 兜底（见 `cpu_temperature.py`）
- 文档：`docs/plugins/6. system_resource.md`
