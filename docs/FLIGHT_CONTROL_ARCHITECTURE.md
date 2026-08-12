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
  ROS-dependent runtime/adapters 位于该 package 的 `runtime/`，不反向污染 core；
- `windarmor_bringup` 后续负责选择是否启动 Flight Runtime，不把选择逻辑放进
  算法层。

v0.4.0 Task 1 只建立接口和纯算法基础，不实现 runtime node、真实状态订阅或
actuator takeover。现有三个 v0.3.2 package 的运行路径不依赖新 package，默认
行为不变。

v0.4.0 Task 2 建立只读 ROS state adapters、monotonic `StateAggregator` 和只能
DRY_RUN 的 Flight Runtime。sensor callback 只转换并更新 observation cache；固定
control timer 每 tick 构造一次不可变 snapshot，再调用算法与校验 command。Runtime
只发布带 `dry_run`/`preview` 语义的结构化观察消息，不拥有 authority，没有
actuator publisher、service client 或 dispatch。现有 bringup 默认路径不启动它。

v0.4.0 Task 3/3.1 增加并加固 observer-only `/motors/safety_state` 与
`/fans/safety_state`，并在 pure core 中建立 authority/preflight/envelope 契约。
production Runtime 允许 `DRY_RUN -> ARMING -> READY_TO_TAKEOVER`，但 hard-code
`takeover_supported=false`，没有 owner acknowledgement path，所以不可能进入
`ACTIVE`、声明 `FLIGHT_CONTROL` 或 dispatch actuator。真正的 atomic owner handoff
与 actuator adapter 属于 Task 4。

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

safe-stop command 与 normal command 是互斥语义。`FlightCommand.safe_stop()`
不携带 motor 或 fan target，只表示算法主动撤销继续控制的意图；runtime 不得
把它解释为可执行 actuator frame，不得复制、缓存或重发上一帧目标。Task 2
DRY_RUN 只观察该意图；后续 authority runtime 才能将其解释为撤销或 inhibit
Flight authority 的请求，再通过既有安全层进入安全状态。safe-stop 不是 hardware
E-STOP，也不能清除 ERROR 或恢复控制模式。

外部观测状态在 startup 可能尚未收到。adapter 必须用 `None` 显式表达 unknown，
不能用 `False`、空字符串或数值零伪装已知安全状态。runtime 只有在 E-STOP、
motor mode、fan enabled/control state 等关键状态均已观测且明确满足安全条件后，
才可声明 actuation allowed 或进入真实 actuator arming。Task 2 已实现 startup
unknown 观测，但因为只允许 DRY_RUN，始终如实保持 authority `NONE`、generation
`0`、`flight_control_active=False` 和 `actuation_allowed=False`；arming 与 actuator
path 仍不存在。

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

Flight failure 后不得自动把 authority 赋予 MANUAL。后续 authority runtime 的
`INHIBITED` 不得因输入重新新鲜或 transport 恢复而自动回到 `ACTIVE`；重新进入
控制必须经过明确的新授权流程。E-STOP 和 ERROR 的裁决优先级永远高于任何
command authority。

Task 3 authority state machine 为：

```text
DISABLED -> DRY_RUN -> ARMING -> READY_TO_TAKEOVER
                         |              |
                         +-----> INHIBITED <----+
```

`prepare` 在进入 ARMING 时分配唯一正 generation；`0` 永远保留给 no-authority。
cancel/inhibit 立即使 attempt generation 失效，reset-inhibit 只返回 DRY_RUN，之后
必须重新 prepare。Task 3.1 的 pure contract 将 motor/fan owner ack 限定为诊断
记录：ack 只保存 owner、当前正 generation 和 owner 观察到的 state sequence；两路
ack 完成仍保持 READY，不能决定 cutoff 或产生 grant。旧 generation、缺少 ack、
duplicate ack、cancel/inhibit 后的 ack 都被拒绝。

未来 grant 必须通过单独的 atomic commit：仅在 READY、当前 generation、两路 ack
齐全且 Runtime 当前 `FlightState.sequence` 不早于 ready barrier 时提交一次。提交
瞬间的 Runtime sequence 才成为不可变 `arming_cutoff_state_sequence`；成功结果只
产生一次 controller reset 与丢弃 pre-commit preview 的要求，pure authority core
不导入具体算法。之后必须等待 `FlightState.sequence > cutoff` 才生成该 generation
第一条 `FlightCommandEnvelope`。ARMING/READY preview 不缓存、不复用。envelope
还要求当前非零 generation、严格递增 command sequence、有限 monotonic timestamp
和合法完整 `FlightCommand`。

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
- `request_safe_stop` 只表示算法主动放弃继续控制，且不得携带 actuator payload。
  Task 2 只观察它；后续 authority runtime 必须将其导向既有安全停止路径。它不
  等同于硬件 E-STOP，也不是 ERROR recovery；
- 不从 torque 推导 `current_a`，不创建未经验证的 RPM 或 thrust；
- 没有真实反馈时必须使用 presence/validity 与 `None` 表示 unknown，不能用
  `0.0` 冒充位置、速度、力矩、温度或风扇实际输出。

## 接口演进

新增状态字段必须有可验证的数据来源、明确单位与 unknown 语义。删除字段、改变
单位、改变 presence 语义或放宽命令校验属于破坏性变更，应提供迁移说明。
runtime 接入阶段优先保持 v0.4.0 Flight API 兼容；adapter 可以演进，但不能把
ROS 或硬件类型泄漏进 core。

## Task 2 状态观测边界

`/motors/feedback` 是从现有已验证 feedback cache 和本地 monotonic 接收时间周期
生成的完整只读 snapshot。它不会触发 CAN read；publisher observer freshness 与
底层 `motor_feedback_timeout_sec` 是独立策略。Runtime 再以
`publisher_reported_age + local_elapsed_since_receipt` 独立判定 Flight freshness。

IMU raw 与 relative roll/pitch 只按相同 source stamp 配对；control timestamp、
`dt` 和所有 freshness 都使用 runtime 本地 monotonic 时间。fan PWM 只作为实际
应用输出观察并归一化，不代表 RPM 或 thrust。fan 与 motor mode 过期后回到
`None`/unknown。现有 `/e_stop` 是触发通道而非权威解除回读；Task 2 因而只锁存
`True`。Task 3 仍不接受 `False` 或 silence 作为解除证据，而改由下述两路权威
readback 聚合完成解除判断。

## Task 3 权威安全观测

motor readback 的 E-STOP/ERROR 分别来自既有 `ControllerState` 和 feedback safety
fault latch；fan readback 的 E-STOP 直接来自唯一的
`FanControlCore.e_stop_latched`。两者都使用 reliable transient-local QoS，publisher
只读取内存快照，不参与 recovery、owner arbitration 或 hardware output。

Task 3.1 为两种 readback 增加 `source_epoch`。publisher 在进程节点实例构造时从
system monotonic clock 生成一次正 uint64 epoch，lifecycle configure/deactivate/
activate 不得改变它；同一实例的 observation sequence 从 `1` 起严格递增且不得因
reconfigure 回退。Runtime 以 `(source_epoch, observation_sequence)` 判序：新 epoch
可从低 sequence 重新开始，旧 epoch 永久拒绝，同 epoch 只接受严格递增值，epoch
或 sequence 为 `0` 一律非法。ROS/wall time 不参与这个顺序契约；Runtime 自身重启
则重建 observation baseline。

Runtime 的全局 E-STOP 聚合规则是：任一权威 latch true 为 `True`；两路都已观测、
新鲜且 false 才为 `False`；其余为 `None`。`/e_stop=True` 作为即时风险证据，必须
等两路在 trigger 之后给出新鲜 false 才能解除；`/e_stop=False` 永远不能单独清除。
readback freshness 使用 Runtime 本地 monotonic receive time，且不改变 motor
watchdog、feedback safety、fan timeout 或 `motor_feedback_timeout_sec`。

preflight 要求 IMU 与全部 required motor 合法、新鲜、健康；全局 E-STOP 明确
false；motor node active、无 ERROR/feedback latch 且公开模式为 MANUAL；fan enabled
明确为 true、无 E-STOP、legacy AUTO 未 requested/active、MANUAL 未 armed 且处于
既有 passive safe-stop state。稳定 reason code 会发布到 authority status。

ARMING 初期可以等待尚未出现的 observation；明确危险、已观测 safety readback
过期或已经满足过的 required inputs 再次失效会锁存 INHIBITED。READY 丢失任一
preflight 条件必定进入 INHIBITED，不自动恢复。

Task 3.1 production 仍固定 `takeover_supported=false`，没有 owner ack/atomic commit
service、topic 或 callback；因此 `MotionSource.FLIGHT`、fan FLIGHT source、ACTIVE 和
actuator dispatch 仍不存在。Runtime 在全部现有状态继续发布 authority `NONE`、
generation `0`、`flight_control_active=false`、`actuation_allowed=false`。

> Initial architecture baseline introduced for v0.4.0.
