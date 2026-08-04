# imu_cybergear_ros2 — IMU 驱动多电机联动控制系统

本项目支持两种连接方式：

1. CAN-USB（`usb_can_serial`）
2. 微雪扩展板 CAN HAT+（`socketcan_hat`）

## ✨ 主要功能

| 功能 | 说明 |
|------|------|
| **LifecycleNode** | 两个节点均采用 ROS2 生命周期管理（configure/activate/deactivate/cleanup） |
| **可配置电机数量** | 通过列表参数支持任意数量电机，无需修改代码 |
| **通信看门狗** | IMU 数据超时自动切换手动模式，保持当前位置 |
| **急停接口** | 三重通道：键盘[空格]、话题 `/e_stop`、服务 `/e_stop` |
| **远程启停** | `/enable_motor` 服务（std_srvs/SetBool） |
| **电机反馈** | 实时读取电机位置/速度/力矩/温度/模式/故障 |
| **故障保护** | 电机 CAN 故障标志位（过流/过温/欠压等）自动触发保护 |
| **断线重连** | IMU 串口 / CAN 总线断开后自动指数退避重连 |
| **低 CPU** | 空闲时不空转，CPU 占用率接近 0% |
| **状态机** | 统一生命周期管理（7 状态：AUTO/MANUAL/急停/错误等） |
| **统一相对姿态** | `/imu/relative_roll_pitch` 发布归一化、轴向修正和统一归零后的 roll/pitch（rad） |
| **公开控制模式** | `/motors/control_mode` 可靠、transient-local 发布稳定状态并发送心跳 |
| **统一目标推进** | MANUAL、AUTO、HOME 共用固定周期和真实 dt 的位置目标推进器 |

## 系统架构

```
┌──────────────────┐  /imu/data_raw   ┌─────────────────────────┐
│ imu_driver_node   │ ───────────────>│ imu_motor_controller_node│
│ (LifecycleNode)   │  sensor_msgs/Imu│ (LifecycleNode)          │
│ • WIT IMU 串口读取 │                 │ • 看门狗 / 状态机         │
│ • 断线自动重连      │                 │ • 电机反馈 / 温度保护     │
│ • /imu/status     │                 │ • 三重急停通道           │
└──────────────────┘                 │ • 键盘 / /e_stop 话题/服务│
                                      │ • 支持任意数量电机       │
                                      └──────────┬───────────────┘
                                                  │
                    ┌──────────────────────────────┼──────────────┐
                    │                              │              │
             CyberGearDriver                键盘交互          状态发布
                    │                      (raw终端)    /motor/status
          ┌─────────┴─────────┐
          │                   │
  UsbCanSerialBackend  SocketCanHatBackend
  (USB-CAN AT协议)     (python-can/SocketCAN)
          │                   │
     串口/CAN总线 ──────> CyberGear 电机（数量可配置）
            ←────── 反馈帧(位置/速度/力矩/温度)
```

## 0. CAN HAT+ 开机一次性初始化（每次开机只执行一次）

如果你使用微雪 CAN HAT+（`socketcan_hat`），请在系统每次开机后先执行一次：

```bash
sudo ip link set can10 down
sudo ip link set can10 up type can bitrate 1000000
sudo ip link set can10 txqueuelen 1000
```

> **重要：第三条 `txqueuelen 1000` 必须加上！** 默认发送缓冲区只有 10 帧，
> 连续初始化多台电机会报 `No buffer space available [Error 105]`，导致电机不动。
> `txqueuelen` 是通用网卡参数，不属于 `type can`，所以必须单独一行设置。

说明：
- 这三条命令是"开机一次性初始化"。
- 同一次开机周期内，不需要在每个终端重复执行。

## 1. CAN-USB 启动命令

### 1.1 单终端启动

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  control_backend:=usb_can_serial
```

### 1.2 双终端启动（键盘不稳定时推荐）

终端 A（仅 IMU）：

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py start_controller:=false
```

终端 B（仅控制器，自动生命周期转换）：

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_motor_controller.launch.py \
  control_backend:=usb_can_serial
```

## 2. 微雪 CAN HAT+ 启动命令（can10 示例）

### 2.1 单终端启动

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  control_backend:=socketcan_hat \
  can_channel:=can10
```

### 2.2 双终端启动（can10）

终端 A（仅 IMU）：

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py start_controller:=false
```

终端 B（仅控制器，自动生命周期转换）：

```bash
cd <你的工作空间>
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_motor_controller.launch.py \
  control_backend:=socketcan_hat \
  can_channel:=can10
```

## 3. 键盘控制

### 3.1 模式切换与全局操作

| 按键 | 功能 |
|------|------|
| `m` | 切换 AUTO / MANUAL 模式 |
| `z` | IMU 姿态归零（当前姿态设为零点） |
| `x` | 设置全部电机当前位置为零点 |
| `h` | 自动归零；AUTO 中会先切到 MANUAL，再按 HOME 速度回零 |
| `p` | 发布当前状态汇总（含各电机位置/力矩/温度/故障） |
| `空格` | **急停全部电机**（进入 EMERGENCY_STOP 状态） |
| `r` | 从急停恢复（保持当前位置） |
| `q` | 停止全部电机并退出；通过整套系统 launch 启动时，同时关闭 IMU 和风扇节点 |

### 3.2 MANUAL 模式步进控制

以下为默认键位，可通过 YAML 中 `motor_keys_forward` / `motor_keys_backward` 自定义：

| 按键 | 功能 |
|------|------|
| `w` / `s` | 左俯仰电机 (ID3) 步进 +/- |
| `a` / `d` | 左抬升电机 (ID4) 步进 -/+ |
| `i` / `k` | 右俯仰电机 (ID2) 步进 -/+ |
| `j` / `l` | 右抬升电机 (ID1) 步进 -/+ |

### 3.3 电机选择与调速

| 按键 | 功能 |
|------|------|
| `1` ~ `N` | 按 CAN ID 选中电机（按 `1` 选中 CAN ID=1 的电机） |
| `+` / `=` | 提高当前选中电机的 CyberGear 速度上限 |
| `-` / `_` | 降低当前选中电机的 CyberGear 速度上限 |
| `[` | 设置当前选中电机的 +90° 期望目标（MANUAL） |
| `]` | 设置当前选中电机的 -90° 期望目标（MANUAL） |

### 3.4 MANUAL、AUTO 与 HOME 的速度语义

控制器维护两组位置：

- `desired_targets`：键盘、绝对目标话题、IMU 或 HOME 希望最终到达的位置；
- `current_targets`：最近一次实际发送给 CyberGear 的软件位置命令。

正常运动输入只更新 `desired_targets`。节点激活后的唯一固定周期推进器使用
真实单调时间差推进：

```text
allowed_step = min(
    max_position_step,
    min(mode_speed, motor_speed_limit) × min(real_dt, motion_dt_max_sec)
)
```

默认速度参数：

```yaml
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0
auto_roll_gain: 1.0
auto_pitch_gain: 1.0
```

这些值是软件目标位置变化率，不等于负载下实测机械角速度，当前
`4.0 rad/s` 只是尚未实机验证的候选值。`default_speed: 10.0` 是启动时写给
CyberGear 的位置模式速度上限初值。`+/-` 调整选中电机的这个上限；低于模式
速度时会限制该电机，高于模式速度后继续增加也不会突破模式速度参数。

轻按一次 `w/s/a/d/i/k/j/l` 使用 `manual_step_deg` 增加有限期望目标。连续
重复字符按实际接收间隔换算增量，稳定重复阶段尽量接近 MANUAL 模式速度；
单个字符不会被当成永久按住。`[`、`]` 和 `/motors/manual_targets` 同样只
设置期望目标，不会一次性跳写完整角度。

AUTO 的 IMU 回调只计算和更新最新期望目标，固定推进器可以在两帧新鲜 IMU
消息之间继续追赶，因此每秒最大推进量不再直接取决于 IMU 回调频率。IMU
超时退出 AUTO 时会立即丢弃未完成的旧姿态目标并保持最近命令位置。

`auto_roll_gain` 和 `auto_pitch_gain` 在既有姿态死区之后放大或缩小对应轴的
电机 AUTO 目标幅度，默认 `1.0` 保持原比例，`0.0` 可关闭对应轴。增益后的
目标仍受正负 90° AUTO 范围、既有方向映射、电机软限位、统一推进器和 AUTO
速度限制约束。增益控制目标角度幅度；`auto_motion_speed_rad_s` 控制追赶目标
的最大软件速度。增益不应用于 `/imu/relative_roll_pitch`，因而不会改变风扇
姿态输入，也不用于 MANUAL、HOME、绝对目标、快捷目标或机械零点流程。

`h` 使用同一个推进器和 `home_motion_speed_rad_s`，不再创建独立快速定时器。
在 AUTO 中按 `h` 会先显式切回 MANUAL；任意有效 MANUAL 运动、绝对目标、
`[`/`]`、切换 AUTO、急停或生命周期停止都会取消 HOME。

本次速度统一改进位于 `v0.3.0` 标签之后，只完成纯软件验证；后续需要固定
机器人并从低速逐电机复验，未经明确授权不得启动硬件验证。

## 4. 远程控制接口

### 4.1 急停（三种方式）

```bash
# 方式一：话题
ros2 topic pub /e_stop std_msgs/msg/Bool "data: true" -1

# 方式二：服务
ros2 service call /e_stop std_srvs/srv/Trigger

# 方式三：键盘按空格
```

### 4.2 远程启停

```bash
# 启用电机关闭
ros2 service call /enable_motor std_srvs/srv/SetBool "data: false"

# 恢复运控模式；成功后固定进入 MANUAL，不直接恢复 AUTO
ros2 service call /enable_motor std_srvs/srv/SetBool "data: true"
```

键盘 `z` 与 `/imu/set_zero` 使用同一归零方法和相同的新鲜度检查。归零成功
会递增 `/imu/zero_generation`，让风扇管理器丢弃归零前姿态并清除已有 AUTO
请求。无效、零范数、NaN/Inf 或过旧的姿态不会刷新有效 IMU 时间。

### 4.3 动态修改参数

两个节点均为 LifecycleNode，需在 active 状态下才能修改参数：

```bash
# 查看节点生命周期状态
ros2 lifecycle nodes

# 修改看门狗超时
ros2 param set /imu_motor_controller_node watchdog_timeout_ms 500

# 修改温度保护阈值
ros2 param set /imu_motor_controller_node motor_temp_limit_degC 70.0
```

### 4.4 查看电机状态

```bash
# 订阅电机反馈话题
ros2 topic echo /motor/status

# 输出格式: motor_id,pos_rad,speed_rad_s,torque_nm,temp_C,mode,fault_hex
# 示例: "1,0.5234,-0.1000,1.200,35.0,运行,0x00"
# 含义: 电机ID,位置(rad),速度(rad/s),力矩(Nm),温度(°C),模式,故障码(hex)
```

控制协调接口：

```text
/imu/relative_roll_pitch  geometry_msgs/msg/Vector3Stamped
/imu/zero_generation      std_msgs/msg/UInt64
/motors/control_mode      std_msgs/msg/String
```

相对姿态的 `vector.x/y` 为 roll/pitch（rad），`vector.z=0`，并保留原始
IMU header；即使电机处于 MANUAL，也会继续发布有效姿态。公开模式只使用
`MANUAL`、`AUTO`、`EMERGENCY_STOP`、`DISABLED`、`ERROR`。

这些协调接口属于 `v0.3.0`，其整机功能已由用户按根 README 验证。本次统一
速度改进位于标签之后，只完成纯软件验证，未因本次任务访问真实 IMU、CAN
或电机。

## 5. 文档导航

- `docs/项目总览与功能清单.md`
- `docs/环境搭建到调试运行手册.md`
- `docs/IMU_CyberGear_Guide.md`
- `../项目分析报告.md` — 详细分析与改进建议
