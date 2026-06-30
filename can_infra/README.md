# Damiao电机 CAN通信 infra

本目录提供与Damiao电机CAN通信的基础设施（infra）。

后续OpenArm相关项目，应通过本项目提供的通信API实现通信。

项目架构设计详见：[design.md](docs/design.md)

## 项目结构

```
can_infra/
├── include/                    # C++ 头文件
│   ├── can_bus.hpp             # Part1: CAN口通信层
│   ├── damiao_motor.hpp        # Part2: Damiao电机通信层
│   └── motor_controller.hpp   # Part2: 控制器 + 持续控制
├── src/
│   └── main.cpp                # C++ 二进制入口（支持多模式）
├── config/
│   └── motor.yaml              # 电机拓扑配置
├── damiao_api.py               # Python API 类（主要使用入口）
├── config_manager.py           # YAML配置 → 文本配置 + CAN初始化
├── build.sh                    # 编译脚本（部署时使用）
├── Makefile
└── docs/
    └── design.md
```

## 构建

```bash
./build.sh
```

## 命令行快速测试 (`main.py`)

`main.py` 提供命令行接口，可一行指令快速测试 CAN 通信连接，无需改代码。
支持四种模式：

| 命令 | 对应接口 | 说明 |
|------|---------|------|
| `enable`   | 接口1 | 电机使能 |
| `disable`  | 接口2 | 电机失能 |
| `set_zero` | 接口3 | 电机标零（当前位置设为零位） |
| `action`   | 接口4 | 电机动作：MIT 控制 / 状态读取 |

> 注意：`--motors` 等选项需写在子命令**之后**，例如 `python3 main.py enable --motors ...`。

### 通用参数（所有子命令共享）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--iface NAME` | CAN 口名称 | `can_slot1_ch1` |
| `--motors SPEC [SPEC ...]` | 电机列表，格式 `can_id:master_id:type` | 内置 3 个测试电机 |
| `--bitrate N` | 仲裁波特率 | `1000000` |
| `--dbitrate N` | 数据波特率 | `5000000` |
| `--classic-can` | 使用经典 CAN（默认 CAN-FD） | 关闭 |
| `--skip-init` | 跳过 `ip link` 初始化（CAN 口已配置好时使用） | 关闭 |

电机描述 `SPEC` 三种写法（`can_id`/`master_id` 可写十进制或 `0x` 十六进制）：

- `0x001:0x11:DM8009` — 完整
- `0x001:0x11` — 省略型号，默认 `DM8009`
- `0x001` — 省略 master_id（自动取 `can_id + 0x10`）与型号

### 1. 使能 `enable`

```bash
# 使用默认 CAN 口与默认电机
python3 main.py enable

# 指定 CAN 口与电机（可多个）
python3 main.py enable --iface can_slot1_ch0 --motors 0x001:0x11:DM8009 0x002:0x12:DM8009
```

### 2. 失能 `disable`

```bash
python3 main.py disable

# 失能单个电机
python3 main.py disable --motors 0x001
```

### 3. 标零 `set_zero`

```bash
# 交互确认（默认会提示 y/N）
python3 main.py set_zero

# 直接标零，跳过确认（脚本友好）
python3 main.py set_zero -y
```

### 4. 动作 `action`

```bash
# 纯状态读取：最安全的连通性测试，不驱动电机
python3 main.py action --refresh

# MIT 控制：目标位置 0.5 rad（自动 enable → control → disable）
python3 main.py action --q 0.5 --kp 20 --kd 1

# 纯力矩前馈，连续发送 5 次
python3 main.py action --q 0 --kp 0 --kd 0 --tau 0.5 --count 5 --interval 0.2

# 电机已使能时，跳过自动使能/失能
python3 main.py action --q 0.5 --kp 20 --no-enable --no-disable
```

`action` 专用参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--kp` | 位置刚度 | `20` |
| `--kd` | 阻尼 | `1` |
| `--q` | 目标位置 (rad，绝对值) | `0` |
| `--dq` | 目标速度 (rad/s) | `0` |
| `--tau` | 前馈力矩 (Nm) | `0` |
| `--count N` | MIT 控制发送次数 | `1` |
| `--interval S` | 多次发送时的间隔（秒） | `0.5` |
| `--refresh` | 仅读取状态，不下发控制 | 关闭 |
| `--no-enable` | 跳过自动使能 | 关闭 |
| `--no-disable` | 结束后保持使能 | 关闭 |

### 典型连通性测试流程

```bash
python3 main.py enable                  # 1. 使能，确认收到反馈帧
python3 main.py action --refresh        # 2. 读取状态，确认 q/dq/tau 合理
python3 main.py action --q 0.5 --kp 20  # 3. 轻微转动，确认电机响应
python3 main.py disable                 # 4. 失能
```

### 查看帮助

```bash
python3 main.py -h            # 顶层帮助
python3 main.py action -h     # action 子命令帮助
```

## Python API (`damiao_api.py`)

### 导入

```python
from damiao_api import DamiaoAPI, Motor, MotorState
```

### Part1: CAN口通信

#### `init_can(name, is_fd=True, bitrate=1000000, data_bitrate=5000000)`

CAN口初始化。

- **input**: CAN口名称，是否CAN-FD，仲裁波特率，数据波特率
- **output**: 根据input对指定CAN口进行初始化，返回是否成功

```python
api = DamiaoAPI()
api.init_can("can_slot1_ch0", is_fd=True, bitrate=1000000, data_bitrate=5000000)
```

### Part2: Damiao电机通信

#### `add_motor(interface, can_id, master_id=None, motor_type="DM4310")`

添加电机到指定CAN口，返回 `Motor` 对象。

```python
motor = api.add_motor("can_slot1_ch0", can_id=0x001, master_id=0x11, motor_type="DM8009")
```

#### `control_motor(motor, can_data)` — CAN信号控制电机

- **input**: Motor实例，CAN-data (bytes/list, 长度8)
- **output**: 调用CAN通信(发)给CAN-ID发送frame，然后调用CAN通信(收)从master-id读电机反馈frame；返回MotorState

```python
state = api.control_motor(motor, [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFC])
print(f"pos={state.q}, vel={state.dq}, tau={state.tau}")
```

#### `enable(motor)` — 特殊接口1: 电机使能

- **input**: Motor实例
- **output**: CAN-data=使能帧(0xFC)，然后调用CAN信号控制电机函数；返回MotorState

```python
state = api.enable(motor)
```

#### `disable(motor)` — 特殊接口2: 电机失能

- **input**: Motor实例
- **output**: CAN-data=失能帧(0xFD)，然后调用CAN信号控制电机函数

```python
api.disable(motor)
```

#### `set_zero(motor)` — 特殊接口3: 电机标零

- **input**: Motor实例
- **output**: CAN-data=标零帧(0xFE)，然后调用CAN信号控制电机函数；返回MotorState

```python
state = api.set_zero(motor)
```

#### `motor_action(motor)` — 特殊接口4: 电机动作（状态读取）

- **input**: Motor实例 (CAN口, CAN-ID)
- **output**: 刷新并返回电机当前状态

```python
state = api.motor_action(motor)
print(f"pos={state.q}")
```

#### `control_mit(motor, kp, kd, q, dq, tau)` — MIT模式控制

```python
state = api.control_mit(motor, kp=20.0, kd=1.0, q=1.0, dq=0.0, tau=0.1)
```

#### `continuous_control(...)` — 持续控制

保证CAN信号控制效率，按指定频率持续执行控制序列。

```python
api.continuous_control(
    control_frequency=500,  # Hz
    print_frequency=5,      # Hz
    duration=60.0,          # seconds
    commands={
        "can_slot1_ch0": [
            {"can_id": 0x001, "can_data": [0,0,0,0,0,0,0,0], "master_id": 0x11},
            {"can_id": 0x002, "can_data": [0,0,0,0,0,0,0,0], "master_id": 0x12},
        ],
        "can_slot1_ch1": [
            {"can_id": 0x001, "can_data": [0,0,0,0,0,0,0,0], "master_id": 0x11},
        ],
    }
)
```

#### `run_mit_sine(...)` — MIT正弦控制

```python
api.run_mit_sine(
    motors=[motor1, motor2],
    kp=20.0, kd=1.0, tau_ff=0.1,
    amplitude=1.0, sine_freq=0.1,
    duration=60.0, control_freq=500, print_freq=5
)
```

#### `pack_mit_data(motor, kp, kd, q, dq, tau)` — 编码MIT数据

将MIT控制参数编码为8字节CAN数据（静态方法）。

```python
data = DamiaoAPI.pack_mit_data(motor, kp=20, kd=1, q=1.0, dq=0, tau=0)
```

### 完整示例

```python
from damiao_api import DamiaoAPI

api = DamiaoAPI()

# 1. 初始化CAN口
api.init_can("can_slot1_ch0", is_fd=True, bitrate=1000000, data_bitrate=5000000)

# 2. 添加电机
motor = api.add_motor("can_slot1_ch0", can_id=0x001, master_id=0x11, motor_type="DM8009")

# 3. 使能
state = api.enable(motor)
print(f"Enabled: {state}")

# 4. MIT控制
state = api.control_mit(motor, kp=20, kd=1, q=0.5, dq=0, tau=0)
print(f"Pos={state.q:.4f}, Vel={state.dq:.4f}")

# 5. 失能
api.disable(motor)
```

## 支持的电机型号

DM4310, DM4310_48V, DM4340, DM4340_48V, DM4340P_48V, DM6006, DM8006, DM8009, DM10010L, DM10010, DMH3510, DMG62150, DMH6220

## C++ 二进制模式

`./main <mode> <config_file>`

| 模式 | 说明 |
|------|------|
| `enable` | 使能所有配置的电机 |
| `disable` | 失能所有电机 |
| `set_zero` | 标零所有电机 |
| `send_recv` | 发送指定CAN数据并接收反馈 |
| `mit_sine` | MIT正弦波控制循环 |
| `continuous` | 持续控制（自定义CAN命令序列） |
