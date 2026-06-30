# heartbeat 体征数据

数据结构：[heartbeat.md](../../../docs/plugins/1.%20heartbeat.md)

网络采集位于 **`hardware_sender/helpers/network_info/`**（与 `plugins` 同级），插件通过 `helpers.network_info.NetworkInfo` 调用。

### 网络连接类型识别
- 对应字段: `network_type`
- 目标：识别 当前和公网通信 用的是 4G/5G 还是 WIFI
- 代码实现：[network_info.py](network_info.py)
```py
from network_info.py import NetworkInfo
network_type = NetworkInfo.get_network_type()
```

### IP信息
- 对应字段 `IP_adress`
- 目标：硬件访问公网走的ip路线
- 代码实现：[network_info.py](network_info.py)
```py
from network_info.py import NetworkInfo
ip_address = NetworkInfo.get_my_ip()
```

# 连接稳定性信息
- 对应字段: `latency_ms` 延迟， `rssi_dbm` 信号强度， `packet_loss_rate` 丢包率， `jitter_ms` 网络抖动
- 目标：识别 当前和公网通信网络连接的稳定性情况
- 代码实现：[network_info.py](network_info.py)
```py
from network_info.py import NetworkInfo
latency_ms, rssi_dbm, packet_loss_rate, jitter_ms = NetworkInfo.get_connection_info()
```
