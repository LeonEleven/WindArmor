# IMU + CyberGear 系统详细使用手册

## 1. 目标与范围

本文档覆盖从开机、网络接口准备、节点启动、键盘调试到常见故障排查的完整流程，适用于当前项目实现版本。

本文中的 CAN、串口、launch 和电机操作会访问真实硬件。执行前必须获得明确
授权并满足 WindArmor 仓库根目录 `AGENTS.md` 的硬件安全门槛。

## 2. 系统组成

1. `imu_driver_node`
- 读取 WIT IMU 串口数据
- 解析 IMU 帧（0x51/0x52/0x53）
- 发布 `/imu/data_raw`

2. `imu_motor_controller_node`
- 订阅 IMU 姿态
- AUTO 模式执行姿态映射控制
- MANUAL 模式执行步进控制
- 支持选中电机后的调速与 ±90° 快捷动作

3. `cybergear_driver.py`
- `usb_can_serial` 后端
- `socketcan_hat` 后端

## 3. 开机后的标准流程（务必按顺序）

### 3.1 通用准备

1. 检查供电与接线
2. 进入工作区并加载 ROS 环境
3. 确认参数文件路径正确

### 3.2 使用 CAN HAT+ 时必须先做

每次系统重启后，先执行：

```bash
sudo ip link set can10 down
sudo ip link set can10 up type can bitrate 1000000
sudo ip link set can10 txqueuelen 1000
```

> **重要：`txqueuelen 1000` 必须加上！** 默认发送缓冲区只有 10 帧，
> 连续初始化多台电机会报 `No buffer space available [Error 105]`。

检查项：
- `state UP`
- 通道名与参数一致（如 `can10`）

### 3.3 编译（首次或代码变更后）

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 4. 启动方式

### 4.1 单终端一键启动

```bash
# USB-CAN
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  control_backend:=usb_can_serial

# SocketCAN HAT+
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  control_backend:=socketcan_hat can_channel:=can10
```

默认：`start_controller:=true`，IMU 和控制节点同时启动。

### 4.2 双终端分开启动（推荐）

终端 A（仅 IMU）：

```bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py start_controller:=false
```

终端 B（控制 + 键盘，自动生命周期转换）：

```bash
# USB-CAN
ros2 launch imu_cybergear_ros2 imu_motor_controller.launch.py \
  control_backend:=usb_can_serial

# SocketCAN HAT+
ros2 launch imu_cybergear_ros2 imu_motor_controller.launch.py \
  control_backend:=socketcan_hat can_channel:=can10
```

优点：
1. 键盘输入更稳
2. IMU/控制日志分离
3. 更易排障

## 5. 键盘控制说明

### 5.1 通用键

- `m`：切换 AUTO / MANUAL
- `z`：IMU 姿态归零
- `x`：设置全部电机当前位置为零点
- `h`：全部电机回目标零位
- `space`：急停全部电机
- `r`：仅从普通急停恢复到 MANUAL 并保持当前位置；不能恢复 ERROR
- `q`：退出节点

### 5.2 MANUAL 步进键

- `w/s`：ID3 正/反向步进
- `a/d`：ID4 负/正向步进
- `i/k`：ID2 反/正向步进
- `j/l`：ID1 反/正向步进

### 5.3 选中电机后动作键（新增功能）

步骤 1：按 CAN ID 选择电机（按 `1` 选中 CAN ID=1 的电机，以此类推）

步骤 2：执行动作
- `+`（或 `=`）：加速
- `-`（或 `_`）：减速
- `[`：设置 `+90°` 期望目标
- `]`：设置 `-90°` 期望目标

说明：
- `[`/`]` 更新期望目标，再由统一固定周期推进器渐进发送。
- 目标角度仍受模式速度、最大步长和软限位约束。

## 6. 日志说明

你会看到以下关键日志：

1. 选中日志
- `已选中电机 IDx`

2. 调速日志
- `调速: IDx old -> new rad/s (delta=...)`

3. 90 度动作日志
- `90度快捷位: IDx -> angle° (rad)`

## 7. 参数与调优建议

关键参数位于 `config/imu_cybergear_params.yaml`：

1. 控制平滑参数
- `deadband_rad`
- `max_position_step`
- `command_interval_sec`

2. 调速参数
- `manual_speed_min`
- `manual_speed_max`
- `manual_speed_step`

3. 方向参数
- `roll_axis_sign` / `pitch_axis_sign`
- `motor_signs` — 电机方向符号列表，按 `motor_ids` 索引对应

4. 位置软限位
- `motor_limits_min` / `motor_limits_max` — 电机限位列表，按 `motor_ids` 索引对应

## 8. 常见问题排查

### 8.1 “以前两条命令，现在一条命令就启动了”

不是功能变化，是 launch 默认同时起控制节点。
如需分开启动，用 `start_controller:=false`。

### 8.2 键盘无响应

1. 焦点不在控制终端
2. 键盘参数未启用
3. SSH 下输入通道冲突

### 8.3 CAN 侧无响应

1. 是否执行了 `ip link set can10 ...`（含 `txqueuelen 1000`）
2. `can_channel` 是否匹配
3. 接口状态是否 `UP`

### 8.4 90 度动作偏小

1. 被软限位约束
2. 电机方向符号配置不匹配

## 9. 推荐调试步骤

1. 上电后先做 CAN 接口准备
2. 双终端启动
3. 先测试 `1/2/3/4` 电机选择日志
4. 再测试 `+/-` 调速
5. 再测试 `[`/`]` 90度动作
6. 最后切 AUTO + `z` 归零联调

## 10. 资料来源说明

- `说明书/2-CH CAN HAT+扩展板.txt` 仅包含官方链接
- 本手册在该基础上补全了项目实操命令与完整流程
