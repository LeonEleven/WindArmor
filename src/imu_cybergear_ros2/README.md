# imu_cybergear_ros2

`imu_cybergear_ros2` 提供 Hiwonder IMU 读取、CyberGear 多电机控制、结构化反馈与
安全状态，以及 MANUAL、LEGACY AUTO 和 Flight 控制归属接口。整机安装、正常启动、
风扇操作和 E-stop 恢复请从仓库根目录 [README](../../README.md) 开始；本文只描述
本包专属行为。

## 安全说明

本包可以访问真实串口和 CAN，并向电机发送控制指令。未经明确授权，不得运行本包
硬件节点或 launch，也不得把 fake/mock 测试表述为实机验证。不得修改当前固定的
`motor_ids`、`motor_signs`、`motor_limits_min` 或 `motor_limits_max`，除非用户针对
该变更明确授权。

全局 `/e_stop`、看门狗、软限位、反馈保护、失权和生命周期清理都属于安全边界，
不得绕过。当前机械映射与限制见
[硬件参考](../../docs/HARDWARE_REFERENCE.md)。

## 包组成

| 组件 | 作用 |
| --- | --- |
| `imu_driver_node` | 读取 Hiwonder IMU，发布 `/imu/data_raw` 与 `/imu/status` |
| `imu_motor_controller_node` | 生命周期电机控制、键盘、状态、安全和控制归属接口 |
| `imu_relative_observer_node` | 不控制硬件的相对姿态观察器 |
| `motor_feedback_observer_node` | 不控制硬件的结构化反馈观察器 |
| `CyberGearDriver` | USB-CAN / SocketCAN 后端与协议收发 |
| `MotorManager` | 目标推进、软限位、命令事务、控制归属与安全停止 |
| `StateManager` / `SafetyMonitor` | 状态转换、E-stop、watchdog 和反馈故障锁存 |

支持的控制后端为：

- `socketcan_hat`：Waveshare CAN HAT+，默认通道 `can10`；
- `usb_can_serial`：USB-CAN 串口后端。

后端、端口、波特率、运动参数和安全参数统一由
[`config/imu_cybergear_params.yaml`](config/imu_cybergear_params.yaml) 管理。

## 启动接口

以下 launch 都会访问真实硬件，只有在本次运行已获授权后才能执行：

```bash
# IMU + 电机控制器
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py

# 仅启动 IMU；仍会访问真实串口
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  start_controller:=false

# 单独启动电机控制器；会连接 CAN 并初始化电机
ros2 launch imu_cybergear_ros2 imu_motor_controller.launch.py
```

日常整机运行应使用根 README 中的 `windarmor_bringup` 统一入口，不要同时启动两个
争用相同 CAN 或电机控制接口的控制器。

## 电机键盘

| 按键 | 功能 |
| --- | --- |
| `w` / `s` | 左俯仰电机正向 / 反向 |
| `a` / `d` | 左升降电机反向 / 正向 |
| `i` / `k` | 右俯仰电机反向 / 正向 |
| `j` / `l` | 右升降电机反向 / 正向 |
| `1`…`4` | 按 CAN ID 选择电机 |
| `+`（或 `=`）/ `-`（或 `_`） | 提高 / 降低所选电机速度上限 |
| `[` / `]` | 所选电机快捷目标 `+90°` / `-90°` |
| `m` | 切换 MANUAL / LEGACY AUTO |
| `h` | HOME；AUTO 中会先回到 MANUAL |
| `z` | 设置 IMU 零点 |
| `x` | 将全部电机当前位置设为机械零点 |
| `p` | 打印状态摘要 |
| `空格` | 发布全局 E-stop |
| `r` | 显式恢复普通 E-stop，只回到 MANUAL |
| `q` | 安全停止并退出 |

前进/后退键可由 `motor_keys_forward` 和 `motor_keys_backward` 配置，但必须是全局
唯一的小写单字符，且不能与固定控制键或数字选择键冲突。

## 目标与初始化语义

控制器区分三类位置：

- `desired_targets`：MANUAL、绝对目标、AUTO 或 HOME 希望最终到达的位置；
- `current_targets`：固定控制周期内按速度限制推进后的当前软件目标；
- measured/commanded position：反馈测得位置与最近一次成功发送的位置。

MANUAL、AUTO 和 HOME 使用同一固定周期推进器和真实 `dt`，并共同受方向映射、
速度限制和软限位约束。IMU 回调只更新 AUTO 期望，不直接按消息频率发送电机命令。
新的 MANUAL 动作、模式切换、E-stop、生命周期停止或 Flight 控制权接管会取消未完成
的 HOME/旧目标。

冷启动在获得有效反馈后以测得位置建立保持目标，不把上次软件会话的零点继续当作
机械真值。电机断电或机械参考变化后，必须人工回到已知的正确机械参考姿态，
再显式调用：

```bash
ros2 service call /motors/set_zero std_srvs/srv/Trigger "{}"
```

服务成功后四轴 target 同步为 `0.0 rad`。在此之前，不应执行依赖准确机械坐标的
HOME、MANUAL、AUTO 或 Flight 动作。

IMU 零点通过键盘 `z` 或 `/imu/set_zero` 设置。成功后
`/imu/zero_generation` 递增，归零前相对姿态和风扇 AUTO 请求失效。

## 状态与恢复

公开电机状态为：`MANUAL`、`AUTO`、`EMERGENCY_STOP`、`DISABLED`、`ERROR`。
内部生命周期/运行状态遵循：

```text
UNINITIALIZED  -> INITIALIZING / ERROR / SHUTTING_DOWN
INITIALIZING   -> MANUAL_RUNNING / EMERGENCY_STOP / ERROR / SHUTTING_DOWN
MANUAL_RUNNING -> AUTO_RUNNING / EMERGENCY_STOP / ERROR / SHUTTING_DOWN
AUTO_RUNNING   -> MANUAL_RUNNING / EMERGENCY_STOP / ERROR / SHUTTING_DOWN
EMERGENCY_STOP -> MANUAL_RUNNING / ERROR / SHUTTING_DOWN
ERROR          -> SHUTTING_DOWN
SHUTTING_DOWN  -> 无其他状态
```

同状态请求是无副作用的 `NO_CHANGE`；非法转换为 `REJECTED`。普通 E-stop 排除原因后
可通过 `/enable_motor=true` 显式恢复，但固定回到 MANUAL，不恢复旧 AUTO、HOME 或
目标。`ERROR` 和 `SHUTTING_DOWN` 不能恢复到运行态。

以下任一严重事件都会锁存、丢弃未完成运动、逐台尽力停止并进入 `ERROR`：

- 电机命令或停止事务故障；
- 通信断线或受控重连耗尽；
- 有效反馈中的非零 CyberGear fault bit；
- 温度达到 critical 阈值；
- 连续无效反馈达到限制；
- 显式启用后的反馈超时。

`ERROR` 不会因后续正常反馈、温度回落、键盘 `r` 或 `/enable_motor=true` 自动清除。
必须排除原因后受控地重新 configure/activate 或重启节点。

## 反馈与保护边界

结构化 `MotorStatus` 包含原始位置、速度、力矩、温度及换算值、mode、fault flags
和时间戳。0x02 帧没有数值电流字段，因此：

- 固件过流 fault bit 可触发立即保护；
- `motor_current_limit_a` 是保留参数；
- 不使用 `torque_nm`、raw torque 或速度推导安培值。

只有 ID、数值范围、时间戳、mode 和 fault 位均合法的帧才会更新本地新鲜度。
`/motors/feedback` 按配置顺序发布完整快照；`has_feedback=false` 时 ROS 默认零值不能
解释成真实物理测量。`/motors/safety_state` 使用 reliable transient-local QoS，
只复制既有状态，不读取驱动或发送 CAN。

两个接收后端都依赖被动 0x02 反馈；代码不能证明电机空闲时持续周期反馈。因此强制
`motor_feedback_timeout_sec` 默认是 `0.0`。只有确认现场固件的空闲反馈行为后才应
显式启用正超时值；观测新鲜度与该保护参数是不同概念。

温度 warning 只告警、不自动降速；critical 单帧即锁存。重复或并发严重事件共享
一次主 stop batch，一台停止失败不会阻止其余电机尝试停止。

## 通信恢复与并发边界

运行期通信故障会原子锁存并立即停止控制推进。若配置允许，恢复工作线程
使用有限次数与退避重新连接；恢复成功也只回到安全、无旧目标的状态，不继续旧
MANUAL/AUTO/HOME。首次故障事实保留用于诊断。

后端资源、驱动 I/O 和恢复过程分别使用独立锁，避免等待读取线程、清理和重连形成反向等待。
deactivate、cleanup 和 shutdown 会幂等撤销定时器、回调、工作线程与驱动资源；异常退出仍
按尽力停止全部电机处理。

## 配置契约

`on_configure()` 先把参数解析为不可变的通道、通信、运动、安全、ROS 接口和键盘
配置。纯函数校验全部通过后，才创建驱动、ROS 资源、连接总线或发送命令。因此配置
错误以零硬件接触失败。

关键约束包括：

- 电机列表非空、长度一致，ID 为唯一的 1–127 整数；
- 电机名称唯一，方向严格为 `+1.0` 或 `-1.0`；
- 软限位有限、下限小于上限并位于协议 `[-4π,+4π]`；
- 后端只接受 `socketcan_hat` 或 `usb_can_serial`；
- 频率、新鲜度、误差阈值和告警限频为正有限值；
- critical 温度严格高于 warning，重连次数/退避参数合法；
- 旧标量 ID、方向和软限位参数只为迁移兼容，非默认值会明确失败。

当前固定映射以 YAML 和硬件参考为准，不应在普通开发任务中复制或覆盖。

## ROS 接口摘要

### 订阅/控制输入

| 接口 | 类型 | 用途 |
| --- | --- | --- |
| `/imu/data_raw` | `sensor_msgs/Imu` | 原始 IMU 姿态 |
| `/e_stop` | `std_msgs/Bool` | 全局急停 |
| `/motors/manual_targets` | `std_msgs/Float64MultiArray` | MANUAL 绝对目标 |
| Flight command | `windarmor_interfaces/MotorFlightCommand` | 已持有控制归属的 Flight 命令 |

### 发布/观察

| 接口 | 用途 |
| --- | --- |
| `/imu/relative_roll_pitch` | 相对 roll/pitch（rad） |
| `/imu/zero_generation` | IMU 零点 generation |
| `/motors/control_mode` | 稳定公开控制模式 |
| `/motors/feedback` | 结构化电机反馈快照 |
| `/motors/safety_state` | 电机安全状态与转换元数据 |
| `/motors/ownership_state` | 旧控制路径/Flight 控制归属状态 |

### 服务

| 接口 | 用途 |
| --- | --- |
| `/e_stop` | 触发电机急停 |
| `/enable_motor` | 显式停用或恢复普通 E-stop |
| `/imu/set_zero` | 设置当前 IMU 姿态为零点 |
| `/motors/set_zero` | 设置当前四电机位置为机械零点 |
| `/motors/flight_ownership/{prepare,commit,revoke}` | Flight 控制归属两阶段切换与撤销 |

Flight 消息字段、控制权 epoch、generation、命令时效租约和精确时序契约以
[Flight Control API](../../docs/FLIGHT_CONTROL_API.md) 为准，不在包 README 重复。

## 测试

本包测试使用纯函数、fake 驱动、fake 反馈和进程内生命周期测试隔离硬件 I/O。
仓库统一纯软件入口为：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

这些测试不会连接真实 CAN 或串口，也不构成硬件验证。新增测试必须在运行前重新审查
fixture、后端和插件没有访问真实硬件。

## 文档归属

- 整机安装、正常启动、基本操作和 E-stop 恢复：根目录
  [README](../../README.md)
- 电机/IMU 组件专属接口和实现约束：本文
- 固定硬件映射、方向、限位和接线：
  [硬件参考](../../docs/HARDWARE_REFERENCE.md)
- Flight 接口与算法接入：
  [Flight Control API](../../docs/FLIGHT_CONTROL_API.md) 和
  [算法开发者指南](../../docs/ALGORITHM_DEVELOPER_GUIDE.md)
- v0.4.0 最终实机结论：
  [硬件验证记录](../../docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)

`docs/` 下的三个早期包内指南仅为保留历史文件名和来源线索，不再承载当前命令、
硬件契约或发布证据。
