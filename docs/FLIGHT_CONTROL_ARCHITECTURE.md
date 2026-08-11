# WindArmor Flight Control Architecture

本文档是 WindArmor 飞控集成架构的长期依据。初始架构基线在 v0.4.0 引入；
后续 runtime、adapter 和算法实现应保持这里定义的纯算法边界与安全裁决关系。

## 目标

- 飞控算法不依赖硬件实现，也不理解 CyberGear、CAN transport、GPIO、PWM 或
  电调细节；
- 飞控算法不依赖 ROS transport、消息类型、topic、service 或 node lifecycle；
- 现有电机与风扇安全层始终保留最终裁决权；
- 算法开发成员只需使用 `FlightState`、`FlightCommand` 和
  `FlightController`，即可用普通 Python 与 fake state 开发和测试算法。

架构中的数据流为：

```text
ROS / hardware world
        |
        v
Flight runtime / adapters
        |
        v
FlightState
        |
======== pure algorithm boundary ========
        |
        v
FlightController.update(state, dt)
        |
        v
FlightCommand
        |
======== pure algorithm boundary ========
        |
        v
Runtime validation / authority / adapters
        |
        v
Existing WindArmor safety layers
        |
        v
Hardware
```

## Package 边界

- `imu_cybergear_ros2` 继续拥有 IMU/CyberGear 的实际 I/O、电机状态机、软限位、
  看门狗、故障处理和 transport recovery；
- `windarmor_fan_controller` 继续拥有 PWM/GPIO 的实际 I/O、风扇命令仲裁、
  看门狗和安全停止；
- `windarmor_interfaces` 保存 ROS package 之间的结构化消息契约；
- `windarmor_flight_control` 保存纯 Python Flight Core、算法接口和算法实现，
  后续可以在该 package 的非 core 区域加入 runtime/adapters；
- `windarmor_bringup` 后续负责选择是否启动 Flight Runtime，不把选择逻辑放进
  算法层。

v0.4.0 Task 1 只建立接口和纯算法基础，不实现 runtime node、真实状态订阅或
actuator takeover。现有三个 v0.3.2 package 的运行路径不依赖新 package，默认
行为不变。

`windarmor_flight_control/core` 与 `algorithms` 禁止依赖 `rclpy`、ROS message
class、CAN/serial library、GPIO/PWM backend、CyberGear driver、SocketCAN，
也禁止包含 ROS topic 或 service 名称。ROS message 与纯模型之间的转换属于
未来 adapter，不属于算法。

## Flight API 边界

稳定的算法入口为：

```python
class FlightController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

`FlightState` 是单个 tick 的不可变快照。adapter 负责把不同来源的状态在明确
时间点聚合，并显式表示 unknown、valid、fresh 和 healthy；算法不得直接回读
硬件来补齐状态。

`FlightCommand` 是算法意图，不是硬件命令。正常 tick 必须给出配置中全部逻辑
电机的完整目标 frame，以及两个风扇的 `[0.0, 1.0]` 无量纲目标。runtime 必须
严格校验完整性与有限值，不能静默补齐或限幅来掩盖算法错误；真正的软限位、
推进限制和 PWM 映射仍由 actuator adapter 与既有安全层处理。

`reset()` 只重置算法内部状态。它没有硬件对象，因此不能重置硬件、清除 ERROR、
清除 E-STOP、设置电机零点或重新使能设备。

## Command Authority 契约

普通命令所有权独立建模为：

```text
NONE
MANUAL
LEGACY_AUTO
FLIGHT_CONTROL
```

同一时刻只能有一个普通 command owner。`CommandAuthority` 与既有
`ControllerState` 正交：不得给现有状态机新增 `FLIGHT_RUNNING`；未来
`FLIGHT_CONTROL` 可以复用 `AUTO_RUNNING` 的硬件安全语义，但必须由 authority
明确区分命令来源。

每次 authority grant 必须带单调 generation。runtime 只能接受当前 generation
的命令，旧 generation 命令永久拒绝；sequence 用于同 generation 内识别旧帧或
乱序帧。Task 1 只定义纯数据模型，不把 generation 接入真实执行路径。

Flight failure 后不得自动把 authority 赋予 MANUAL。未来 runtime 的
`INHIBITED` 不得因输入重新新鲜或 transport 恢复而自动回到 `ACTIVE`；重新进入
控制必须经过明确的新授权流程。E-STOP 和 ERROR 的裁决优先级永远高于任何
command authority。

## 不可妥协的安全契约

- ERROR 不自动恢复；
- transport 重连只恢复通信，不恢复运行状态；
- 不自动恢复 MANUAL、AUTO 或 HOME，也不重发旧目标；
- Flight Runtime 不得清除 ERROR 或 E-STOP，不得 enable hardware 或 set zero；
- Flight Runtime 和算法不得直接访问 CyberGear driver、CAN、GPIO 或 PWM；
- 未来 flight motor command 必须进入现有 `MotorManager` 安全路径；
- 未来 flight fan command 必须进入现有 fan command manager；
- runtime 校验与 authority 不能绕过电机/风扇状态机、看门狗、软限位、停用或
  安全退出；
- `request_safe_stop` 只表示算法主动放弃继续控制。runtime 必须将其导向既有
  安全停止路径；它不等同于硬件 E-STOP，也不是 ERROR recovery；
- 不从 torque 推导 `current_a`，不创建未经验证的 RPM 或 thrust；
- 没有真实反馈时必须使用 presence/validity 与 `None` 表示 unknown，不能用
  `0.0` 冒充位置、速度、力矩、温度或风扇实际输出。

## 接口演进

新增状态字段必须有可验证的数据来源、明确单位与 unknown 语义。删除字段、改变
单位、改变 presence 语义或放宽命令校验属于破坏性变更，应提供迁移说明。
runtime 接入阶段优先保持 v0.4.0 Flight API 兼容；adapter 可以演进，但不能把
ROS 或硬件类型泄漏进 core。

> Initial architecture baseline introduced for v0.4.0.
