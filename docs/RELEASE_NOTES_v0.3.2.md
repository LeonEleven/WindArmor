# WindArmor v0.3.2

## 版本定位

`v0.3.2` 是安全性、确定性与运行可靠性版本。当前 `master` 是发布候选；
Git tag `v0.3.2` 尚未创建，最新稳定标签仍为 `v0.3.1`。

## 相比 v0.3.1 的主要变化

### 风扇控制安全

- 普通 callback 只更新经校验的缓存；定时器是唯一正常 PWM slew 推进路径。
- 急停不再依靠 enabled、电机模式或姿态心跳自动恢复，必须显式调用
  `/fans/reset_e_stop`。
- MANUAL 必须先通过 `/fans/manual_enable` 授权，再提交本次授权后的双路
  停止基线，才会接受非停止 PWM。
- 未知、空白或不支持的电机模式使旧缓存失效并立即安全停止。
- 既有死区、滞回、`smoothstep` 响应曲线、PWM 上下限与上升/下降步长未改变。

### 电机命令一致性

- `desired_targets` 表示期望目标；`current_targets` 表示最近成功发送给
  驱动的目标，不是待发送值或真实位置反馈。
- 位置或速度写入失败时，软件状态不会提前提交。
- 批量位置写入在失败前已成功的前缀保留成功提交；失败电机及后续普通
  命令停止推进。
- 命令写失败会尽力停止全部电机并进入 `ERROR`，不自动恢复。

### 生命周期可靠性

- 部分初始化失败会反向回滚已触及电机，best-effort stop、关闭驱动、
  清除 callback 并释放已创建的 ROS 资源。
- configure 失败、cleanup 与 shutdown 共用幂等资源释放流程；单项清理
  失败不阻止后续清理。
- 再次 configure 创建全新 driver、callback、安全健康与 recovery session，不继承
  旧资源或锁存。

### 配置契约

- 在创建驱动、ROS 运行资源或访问通信后端前，集中校验电机列表长度、
  ID 唯一性、sign、软限位、控制轴、键盘冲突、通信后端和安全参数。
- 旧标量电机参数保持默认值时兼容；非默认值会明确拒绝并指向列表参数。
- USB-CAN 新参数优先；仅当新参数为空/零时启用带废弃告警的旧参数 fallback。

### 状态转换契约

- 状态请求返回 `CHANGED`、`NO_CHANGE` 或 `REJECTED`，并保留 reason、source 和最近
  真实变化的不可变快照。
- 转换依据显式合法表；`ERROR` 只能进入 `SHUTTING_DOWN`，`SHUTTING_DOWN`
  不能离开。
- 同状态请求幂等，非法请求不运行 callback；状态 callback 在释放状态锁后执行。

### 电机反馈健康

- 反馈先按配置 ID、有限数、协议量程、模式、已支持 fault bit 与 timestamp
  合法性检查。
- 无效反馈不覆盖最近合法反馈；未配置 motor ID 不污染健康状态。
- 任一严重 firmware fault bit 会停止全部电机、进入 `ERROR` 并在本次 lifecycle
  session 锁存。

### 温度与故障位保护

- 温度 `>= 80.0 °C` 且 `< 90.0 °C` 时仅限频告警，不自动降速。
- 温度 `>= 90.0 °C` 时停止全部电机、进入 `ERROR` 并锁存。
- `motor_current_limit_a: 5.0` 仍是保留参数。0x02 feedback 没有经验证的
  数值 `current_a`，因此软件尚不执行 5 A 数值比较。实际过流保护依赖
  CyberGear firmware fault bit，不从 torque 推导 current。

### CyberGear 状态帧端序修正

- 0x02 feedback 数据区的 position、speed、torque 和 temperature 四个 `uint16`
  均按大端序解析。
- 实机观察的温度字节 `0x0167/0x0161/0x015A` 对应 `35.9/35.3/34.6 °C`；
  该修正已在正常机械零点与手动控制路径复测。

### GitHub Actions CI

- 新增 GitHub hosted Ubuntu 24.04 / ROS 2 Jazzy 纯软件 CI，统一入口为
  `scripts/ci_software.sh`。
- workflow 只有 `contents: read`，不使用 self-hosted runner、secret、真实 `/dev`、
  CAN/GPIO/PWM、硬件节点或 launch。
- CI 安全检查器约束 workflow 和统一入口；Actions 使用完整 commit SHA 固定，
  测试日志 artifact 缺失时不会静默成功。

### 运行期通信断线与受控重连

- transport fault 与 motor health fault 分离，覆盖 USB-CAN 与 SocketCAN 的明确断线/
  读写异常。
- connection generation 屏蔽旧 reader 晚到事件；运行期重连使用有界重试和
  可取消退避，cleanup/shutdown 可取消并 join worker。
- 通信重连成功不等于恢复机器人运动。成功后状态为 `RECONNECTED_LOCKED`，
  ControllerState 与公开模式仍为 `ERROR`；不重新初始化电机、不
  `enter_control_mode`、不恢复 MANUAL/AUTO/HOME 或旧目标。
- 排除故障后必须重新 lifecycle cleanup/configure 或重启节点。

## 兼容性

- 三个 ROS 2 package 版本统一为 `0.3.2`：`imu_cybergear_ros2`、
  `windarmor_fan_controller` 和 `windarmor_bringup`。
- v0.3.1 已有 topic/service 的名称、消息类型与状态 QoS 未删除或重命名。
- 风扇有意新增 `/fans/manual_enable` (`std_srvs/srv/SetBool`) 和
  `/fans/reset_e_stop` (`std_srvs/srv/Trigger`)，以及公开状态
  `MANUAL_DISARMED` 和 `MANUAL_WAITING_FOR_NEUTRAL`。
- `/motor/status` 继续使用 `std_msgs/msg/String`；transport 诊断没有引入新自定义
  ROS message 或自动恢复服务。

## 公共 ROS 接口

主要 topic：

- `/imu/data_raw` (`sensor_msgs/msg/Imu`)、`/imu/status` (`std_msgs/msg/String`)；
- `/imu/relative_roll_pitch` (`geometry_msgs/msg/Vector3Stamped`)、
  `/imu/zero_generation` (`std_msgs/msg/UInt64`)；
- `/motors/control_mode` (`std_msgs/msg/String`)、
  `/motors/manual_targets` (`std_msgs/msg/Float64MultiArray`)、
  `/motor/status` (`std_msgs/msg/String`)；
- `/e_stop` (`std_msgs/msg/Bool`)；
- `/fans/pwm` (`std_msgs/msg/Int32MultiArray`)、`/fans/left/pwm` 与 `/fans/right/pwm`
  (`std_msgs/msg/Int32`)；
- `/fans/status_pwm` 与 `/fans/auto_target_pwm` (`std_msgs/msg/Int32MultiArray`)；
- `/fans/enabled`、`/fans/auto_enabled`、`/fans/auto_active` (`std_msgs/msg/Bool`)；
- `/fans/control_state` (`std_msgs/msg/String`)。

主要 service：

- `/e_stop`、`/imu/set_zero`、`/motors/set_zero` (`std_srvs/srv/Trigger`)；
- `/enable_motor` (`std_srvs/srv/SetBool`)；
- `/fans/enable`、`/fans/auto_enable`、`/fans/manual_enable` (`std_srvs/srv/SetBool`)；
- `/fans/stop`、`/fans/reset_e_stop` (`std_srvs/srv/Trigger`)。

`/imu/zero_generation`、`/motors/control_mode`、`/fans/enabled`、
`/fans/auto_enabled`、`/fans/auto_active`、`/fans/auto_target_pwm` 和
`/fans/control_state` 使用 reliable、transient-local 状态 QoS。公开电机模式值仍为
`MANUAL`、`AUTO`、`EMERGENCY_STOP`、`DISABLED` 和 `ERROR`。

## 默认参数

发布冻结的主要电机默认值：

```yaml
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
command_interval_sec: 0.02
max_position_step: 0.4
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0
motion_dt_max_sec: 0.05
target_reached_tolerance_rad: 0.001
manual_step_deg: 3.0
manual_repeat_gap_sec: 0.8
manual_repeat_dt_max_sec: 0.08
default_speed: 10.0
auto_roll_gain: 1.0
auto_pitch_gain: 1.0
motor_temp_limit_degC: 80.0
motor_temp_critical_degC: 90.0
motor_current_limit_a: 5.0
motor_feedback_timeout_sec: 0.0
```

`motor_feedback_timeout_sec: 0.0` 默认关闭强制反馈超时，因为当前尚不能证明
电机空闲时一定持续周期返回状态帧。

发布冻结的主要风扇默认值：

```yaml
fan_deadband_on_deg: 5.0
fan_deadband_off_deg: 3.0
fan_full_scale_deg: 45.0
fan_stop_pwm_us: 800
fan_start_pwm_us: 1200
fan_auto_max_pwm_us: 1400
control_rate_hz: 20.0
rise_step_pwm_us: 10
fall_step_pwm_us: 20
fan_response_curve: smoothstep
```

`4.0 rad/s`、`fan_full_scale_deg: 45.0`、`1200 μs` 和 `1400 μs` 是当前冻结值，
不代表已完成精确机械速度、推力或恢复能力标定。

## 重要安全语义

- 命令 fault、严重 motor feedback fault、临界温度或 transport fault 会停止普通
  运动推进并进入 `ERROR`；没有自动运动恢复。
- 通信重连成功只恢复 transport/reader，不恢复电机控制或旧目标。
- 风扇急停、MANUAL 和 AUTO 都需要当前会话的显式恢复/授权，旧心跳或旧
  PWM 不会隐式恢复输出。
- `/e_stop`、看门狗、软限位、停用和安全退出机制保持。

## 已完成验证

- 用户此前完成统一 launch、MANUAL、AUTO、机械零点和风扇正常功能验证；
  0x02 大端序修正后已重复正常实机路径。
- 大量 pure logic、fake driver、fake feedback、fake clock 和 fake transport 故障注入
  覆盖命令失败、回滚、清理、状态转换、feedback health 与受控重连。
- 当前 RC 本地 `./scripts/ci_software.sh` 完整通过：电机包 `359 passed`、风扇关键
  回归 `98 passed`、三包完整 `480 tests, 0 errors, 0 failures, 0 skipped`；更完整的
  分项结果记录在 `docs/LATEST_FEEDBACK.md`。
- RC 工作区尚未 push，因此尚未触发包含本地 RC 修改的新 GitHub Hosted CI。

## 尚未完成的真实硬件故障注入

以下项目没有作为 v0.3.2 发布门槛的普通实机测试：

- 真实欠压、过流、90 °C 过温或编码器 fault 注入；
- USB-CAN 拔线、CAN 断线、串口破坏或自动重连实机认证；
- `stop_motor` 失败、feedback timeout 或真实 cleanup 故障注入。

现有 fake/mock 覆盖只是纯软件故障注入，不是真实硬件认证。

## 已知限制

- 0x02 feedback 没有已验证的数值安培电流；无软件 5 A 闭环保护。
- 反馈强制超时默认关闭；需要先验证真实空闲反馈周期。
- 风扇 PWM/推力、`fan_full_scale_deg` 和三模式实际机械速度尚未完成最终
  物理标定。
- 本版本不包含动态平衡控制、PID 优化、高级姿态控制或结构化
  `DiagnosticArray`。

## 升级注意事项

1. 风扇 MANUAL 调用方必须接入 `/fans/manual_enable` 和授权后双路停止基线。
2. 急停恢复必须先明确观察 `/e_stop=false`，恢复底层和电机模式安全状态，
   再调用 `/fans/reset_e_stop`；复位后仍需重新选择 MANUAL 或 AUTO。
3. 电机 command、health 或 transport `ERROR` 不能用普通急停恢复流程清除；
   排除原因后重新 lifecycle 配置或重启。
4. 不要因 transport 显示已重连就假定电机已初始化或可运动。
5. 创建 `v0.3.2` annotated tag 之前，必须等待本 RC 提交/push、Hosted CI
   green 和用户最终整机正常功能回归。
