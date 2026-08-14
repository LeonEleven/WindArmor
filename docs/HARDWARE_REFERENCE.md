# WindArmor Hardware Reference

本文档记录 WindArmor 的长期硬件布局、机械映射、安装坐标和接线边界。运行命令、
带电授权和测试流程以根目录 `AGENTS.md` 为准；Flight 算法数据语义以
`FLIGHT_CONTROL_API.md` 为准。

## Platform

- Raspberry Pi 5；
- Ubuntu 24.04；
- ROS 2 Jazzy；
- Waveshare 2-CH CAN HAT+；
- 当前 SocketCAN 接口 `can10`；
- 4 个 CyberGear 微电机；
- Hiwonder IMU；
- 2 个涵道风扇。

Ubuntu patch 版本不属于长期硬件契约。

## Motor physical mapping

机械位置与当前配置中的逻辑名称对应如下：

| CAN ID | 机械位置/轴 | 当前逻辑名称 |
|---:|---|---|
| 1 | 机器人右臂左右/侧向肩部轴 | `right_lift` |
| 2 | 机器人右臂前后肩部轴 | `right_pitch` |
| 3 | 机器人左臂前后肩部轴 | `left_pitch` |
| 4 | 机器人左臂左右/侧向肩部轴 | `left_lift` |

当前受保护配置按列表索引一一对应，而不是按 CAN ID 数值升序排列：

```yaml
motor_names: ["left_lift", "left_pitch", "right_pitch", "right_lift"]
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
```

- 机械映射描述 CAN ID 对应的实际关节位置；
- `motor_ids` 定义配置列表顺序；
- `motor_signs` 是各索引的软件方向修正；
- `motor_limits_min/max` 是各索引的软件位置软限位，单位为 rad。

Flight API 使用稳定逻辑名称作为 motor key。算法不得解析、生成或依赖 CAN ID，
也不得把 CAN ID 当作公开算法逻辑 key。

### CyberGear observation transport boundary

CyberGear CAN 总线使用 1 Mbps。当前驱动的软件协议路径可以在只打开 transport 和
reader 后解析 CyberGear 通信类型 2（0x02）
反馈：SocketCAN `connect()` 本身不发送 CAN frame；USB-CAN `connect()` 会向 USB-CAN
适配器写入 AT transport setup，但不会向 CyberGear 发送 run-mode、target、enable、
stop 或 set-zero command，也不假设一个伪造的电机 measurement。

既有实机 passive observation 已确认：transport connected 时，四台电机在零 host
command TX 下均持续 `has_feedback=false`，没有观测到 spontaneous 0x02。零 TX 完整
motor feedback 因而标为 `NOT SUPPORTED BY OBSERVED HARDWARE BEHAVIOR`，不是 v0.4.0
release requirement；passive observer 没有 frame 时继续如实保持 unknown/invalid。

CyberGear 手册 4.1.9 规定通信类型 18 单参数写入应答为通信类型 2；位置模式的
`0x7016 loc_ref` 是当前既有正常控制路径。normal controller active 时以默认 10 Hz
重发每台电机当前 owner、当前会话中最近成功提交的同值 hold target，以取得包含位置、
速度、力矩、温度、device mode 和 fault bits 的完整 0x02。软件 fake regression 已证明
该 probe 不修改 target、不切换模式、不 enable/recover/set-zero，也不会在 revoked
Flight generation、E-STOP、ERROR、transport fault 或 inactive lifecycle 下发送；真实
Gate B feedback baseline 已确认四台电机持续反馈均为 valid、fresh、healthy 且
`fault_flags=0`。

手册 4.1.8 另定义通信类型 17 单参数读取，4.1.12 列出 `0x7019 mechPos`、
`0x701A iqf`、`0x701B mechVel`、`0x701C VBUS`，但注明 `0x7019–0x7020` 只在
1.2.1.5 固件可读。本任务未查询真实固件，且 type-17 单独不能提供完整 temperature、
fault flags、device mode 和 torque contract，因此不作为 Flight 完整反馈来源。

### CyberGear zero reference and cold power cycle

CyberGear 手册明确说明通信类型 6 设置的机械零位“掉电丢失”。这里的掉电是
CyberGear motor power loss；不能把 Raspberry Pi 单独掉电描述成电机零位必然丢失。
软件也无法只根据当前位置合法就判断机器人正处于项目机械零位，因此 cold startup
绝不自动 set-zero。

normal controller 每次 configure 都为每台电机重新取得本次初始化期间的新鲜、合法
type-2 实测位置，并把第一次 `loc_ref` 设置为同一 CyberGear 原生坐标值。反馈和目标
使用同一个 driver coordinate，`motor_signs` 不在这条保持路径中再次应用。没有可信
位置、ID 不匹配、位置非有限、设备状态非法、fault bit、临界温度或 transport 故障
都会使 configure 失败并执行既有 rollback；不得使用零、软限位中点或旧会话 target
作为 fallback。

CyberGear motor power cycle 后的操作顺序是：

1. cold startup 只保持上电时当前位置；
2. operator 确认机器人处于正确物理 reference posture；
3. operator 显式执行 `/motors/set_zero`；
4. 确认四轴 feedback 接近零后，才进行依赖准确机械坐标的 MANUAL、AUTO、HOME 或
   Flight 测试。

同一进程 cleanup/reconfigure 也必须重新采集本次 measured baseline，不能复用前一
lifecycle、Flight generation 或磁盘中的 target。

## IMU mounting and frame

Hiwonder IMU 水平安装在机器人上躯干中央，安装轴向为：

```text
X+ -> 机器人正面
Y+ -> 机器人左侧/左臂方向
Z+ -> 垂直向上
```

这是硬件安装与坐标契约。当前 ROS `frame_id` 配置为 `imu_link`；字符串本身不
替代上述物理安装定义，也不新增坐标变换。统一归零后的 `relative_roll_rad` /
`relative_pitch_rad` 算法语义继续以 `FLIGHT_CONTROL_API.md` 为准。当前没有经过
验证的 relative yaw reference，本文件不定义或推断 yaw 零点。

## Fan wiring

仓库当前使用 BCM GPIO 编号：

| 通道 | BCM GPIO | Raspberry Pi 物理引脚 |
|---|---:|---:|
| 左风扇 PWM | GPIO12 | 32 |
| 右风扇 PWM | GPIO13 | 33 |
| GND | — | 34 或其他 GND |

GPIO12 来自原单风扇项目已经验证的连接。GPIO13 是当前第二路风扇默认配置；首次
带电前仍必须物理确认它实际连接到右风扇电调信号线，不能把仓库默认值视为该接线
已经完成实机确认。任何 GPIO/PWM/ESC 操作仍需遵守 `AGENTS.md` 的硬件授权门槛。

## Measurement limitations

- CyberGear 0x02 feedback 没有经过验证的数值 `current_a`；
- 不得从 torque 或原始 torque 数值推导电流；
- 风扇没有真实 RPM readback；
- Flight 的 normalized fan command 是 `[0.0, 1.0]` 无量纲控制意图，不是
  thrust fraction；
- `flight_takeover_enabled=false` 是当前默认值；
- v0.4.0 Task 4/4.1 的 Flight takeover 只完成 pure/fake/in-memory 软件验证，
  尚未完成真实硬件验证。

本文档不把软件测试、默认配置或历史正常功能回归扩展解释为新的物理量、性能
标定或 Flight takeover 实机结论。
