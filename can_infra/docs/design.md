

## Part1: CAN口通信

### CAN口初始化：
- input：CAN口名称，是否CAN-FD，仲裁波特率，数据波特率
- output： 根据input对指定CAN口进行初始化，并反馈初始化结果

### CAN通信- 发CAN frame：
- input: CAN口，CAN-ID, CAN-data, 
- output: 完成CAN报文发送

### CAN通信- 收CAN frame：
- input：CAN口，CAN-ID
- output：反馈指定CAN-data

## Part2： Damiao电机通信
### 电机类，数据结构：
```cpp
struct Motor{
    CAN_interface: // CAN口
    CAN_ID：// （电机的can-id）
    Master_ID: // (电机的master-id)
}
```

### CAN信号 控制电机：
- input：Motor实例，CAN-data
- output：调用CAN通信(发)给CAN-ID发送frame，然后调用CAN通信(收)从master-id读电机反馈frame；反馈收发结果

### 特殊接口1：电机使能
- input：Motor实例
- output：CAN-data=使能帧，然后调用CAN信号控制电机函数

### 特殊接口2：电机失能
- input：Motor实例
- output：CAN-data=失能帧，然后调用CAN信号控制电机函数

### 特数接口3：电机标零（电机状态读取函数）
- input：Motor实例
- output：CAN-data=标零帧，然后调用CAN信号控制电机函数

### 特殊接口4：电机动作
- input：CAN口，CAN-ID

### 特殊接口5: 持续控制
为了保证 CAN信号控制效率，给持续控制接口。（本质是通过上述1~4的接口进行控制）

- input： 以以下数据格式给定 CAN信号控制序列：
    ```yaml
    control_frequency: 500 # 控制频率 Hz
    print_frequency: 5 # 日志反馈频率 Hz

    CAN口1: # 一个列表，表示该CAN口要执行的信号控制序列
    - CAN-ID:
      CAN-data:
      Master-ID:
    - CAN-ID:
      CAN-data:
      Master-ID:
    - ...
    CAN口2:
    - CAN-ID:
      CAN-data:
      Master-ID:
    - CAN-ID:
      CAN-data:
      Master-ID:
    - ...
    ```
- output: 调用CAN信号 控制电机函数，完成控制序列。



## Part3： 跨进程/跨语言 调用Damiao电机通信
为了保证CAN信号控制效率，提供的最终API为python库