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

当前驱动的软件协议路径可以在只打开 transport 和 reader 后解析 CyberGear 0x02
反馈：SocketCAN `connect()` 本身不发送 CAN frame；USB-CAN `connect()` 会向 USB-CAN
适配器写入 AT transport setup，但不会向 CyberGear 发送 run-mode、target、enable、
stop 或 set-zero command。仓库没有独立的 GET/status query，也不假设一个伪造的
电机 measurement。

软件层具备 passive-RX observation path，不等于已证明真实电机在没有任何 host
control TX 时会主动发送 0x02。该物理行为仍是未来单独授权 Stage 1 要记录的
`PASS / FAIL / NOT VERIFIED` 项；没有 frame 时必须保持 `has_feedback=false`。

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
