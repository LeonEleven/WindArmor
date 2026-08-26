# WindArmor 飞控架构

## 阅读对象与文档状态

本文是 Runtime、安全机制、控制权（authority）和集成维护者的长期架构依据。算法新人应
先读[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)，字段参考见
[飞控 API](FLIGHT_CONTROL_API.md)。

v0.4.0 飞控栈已完成该版本对应的硬件与功能验证，Gate B/C/D 均为 COMPLETE。最终判定、
特定版本证据和限制保存在
[v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)，完整
执行过程保存在[历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)。本文不复制会话标识
或时间戳，也不把该结果扩展为任意新算法、性能标定或新硬件场景已获验证。
`flight_takeover_enabled=false` 继续作为生产默认值。

## 架构目标

- 算法不依赖 ROS 传输、消息、话题、服务或生命周期；
- 算法不理解 CyberGear、CAN、串口、GPIO、PWM 或 ESC；
- 既有电机/风扇管理器和安全层始终保留最终裁决权；
- 未知、有效、新鲜、健康与控制权就绪条件显式区分；
- 控制权交接、命令流、关闭、超时和重启全部执行失效后安全闭锁（fail-close）；
- 通信恢复不自动恢复控制状态、控制归属或旧目标。

## 组件与依赖边界

```text
ROS / 硬件观测来源
                 |
                 v
       Runtime 适配器 + 状态聚合器
                 |
                 v
             FlightState
                 |
            纯算法边界
                 |
                 v
       FlightController.update()
                 |
                 v
            FlightCommand
                 |
        pure algorithm boundary
                 |
                 v
 Runtime 校验 / 控制权 / 命令包络
                 |
                 v
 MotorManager / FanCommandManager / 安全机制
                 |
                 v
              hardware
```

包职责：

- `imu_cybergear_ros2`：IMU/CyberGear I/O、电机生命周期/状态机、软限位、看门狗、
  故障与通信恢复；
- `windarmor_fan_controller`：GPIO/PWM I/O、风扇命令仲裁、斜率限制、看门狗和停止；
- `windarmor_interfaces`：ROS 包之间的结构化传输契约；
- `windarmor_flight_control/core`：纯模型、校验、控制权、预检和命令包络；
- `windarmor_flight_control/algorithms`：纯控制器实现；
- `windarmor_flight_control/runtime`：ROS 适配器、状态聚合、控制器加载器、控制权编排和
  执行器命令包络传输；
- `windarmor_bringup`：选择是否启动 Runtime；不把选择逻辑放入算法。

`core/` 与 `algorithms/` 禁止依赖 `rclpy`、ROS 消息、CAN/串口库、GPIO/PWM 后端、
CyberGear 驱动或其他硬件包。ROS ↔ 纯模型转换只属于 Runtime 适配器。

## Runtime 状态观测链路

传感器回调只校验、转换并更新观测缓存；固定控制定时器每周期使用同一个本地单调时钟时间
构造一次不可变 `FlightState`，先校验状态，再调用控制器，最后校验命令。

### IMU 配对与时间

原始 IMU 与相对滚转/俯仰观测只按相同来源时间戳配对。状态快照时间戳、`dt` 和新鲜度都
使用 Runtime 内部单调时钟；不使用墙上时钟推断新鲜度。零点代次变化会丢弃旧配对，避免
跨参考零点复用。

### 电机观测

`/motors/feedback` 是全部配置逻辑电机的完整状态快照。发布者只复制当前反馈缓存和本地
接收年龄；普通控制器中受生命周期/控制归属约束的采集定时器可重发相同的权威 `loc_ref`
以获取 type-2 反馈，但观测发布者本身不执行驱动 I/O。未知物理量使用存在性标志/`None`，
不能用 ROS 数值默认零冒充。

### 风扇观测

风扇实际输出由已观测 PWM 归一化而来，只表达实际输出已知或未知，不是 RPM 或推力。
`enabled/control_state` 过期后回到 `None`。算法归一化命令与已观测实际输出是两个方向的
数据，不能混为一谈。

### `required_inputs_fresh`

StateAggregator 当前定义为：

```text
paired IMU is fresh
AND
every configured MotorState is fresh
```

它不包含风扇输出/状态、电机/风扇权威安全回读、E-STOP 是否解除、控制归属回读或控制权
就绪条件。预检和 `actuation_allowed` 会分别检查这些条件，因此不得把
`required_inputs_fresh=True` 当作整个系统已经就绪。

## 未知状态与权威安全回读

启动后尚未收到外部观测时必须使用 `None`，不能用 false、空字符串或零伪造安全
状态。`/e_stop` 是 trigger channel，不是 authoritative clear readback；`/e_stop=False` 不能
单独证明急停已解除。

motor/fan safety readback 使用 reliable transient-local QoS，并携带：

- 正的 `source_epoch`：底层进程实例标识；
- 同一 epoch 内为正且严格递增的 `observation_sequence`；
- 生命周期/管理器状态、E-STOP/ERROR 锁存和控制归属相关安全事实。

Runtime 判序规则：同 epoch 只接受更大 sequence；更大 epoch 建立新 baseline；更小 epoch
永久拒绝；epoch/sequence 为零非法。Runtime 自身 restart 时重建 observation baseline。

全局 E-STOP 聚合规则：

1. 任一路 authoritative latch true → `True`；
2. 两路都已观测、新鲜且 false → `False`；
3. 其他情况 → `None`；
4. trigger true 后，必须看到两路在 trigger 之后的新鲜 false 才能解除其风险证据。

## 控制权状态机

普通命令的控制归属独立建模为：

```text
NONE
MANUAL
LEGACY_AUTO
FLIGHT_CONTROL
```

同一时刻只允许一个普通命令 owner。Flight 控制权状态为：

```text
DISABLED -> DRY_RUN -> ARMING -> READY_TO_TAKEOVER
                                      |
                                      v
                                   ACTIVE
                         |              |
                         +-----> INHIBITED <----+
```

`reset_inhibit` 只回到 DRY_RUN；之后必须重新 prepare。输入/通信恢复不能自动从
INHIBITED 回到 ACTIVE，也不能自动恢复 MANUAL、LEGACY_AUTO 或旧目标。E-STOP/ERROR 的
裁决永远高于 authority。

### 身份标识与重启隔离

正式身份标识是 `(authority_epoch, generation)`：

- `authority_epoch` 是 Runtime 进程会话的正 uint64，重启会产生新值；
- generation 在该 epoch 的 prepare 尝试中分配正值；
- `0` 保留表示无控制权；
- cancel/inhibit 立即使本次尝试的 token 永久失效；
- owner 拒绝旧 epoch/generation，新 epoch 也不能抢占仍为 active 的旧 Flight owner；
- 命令序号在同一 token 内严格递增，用于拒绝重复或乱序帧。

## 预检与就绪条件

prepare 进入 ARMING。预检（preflight）至少要求：

- IMU valid/fresh；
- 每个必要电机均有效、新鲜且健康；
- 全局 E-STOP 明确为 false；
- 电机安全状态已观测且新鲜，节点 active，无 ERROR/反馈锁存，并处于允许的被动模式；
- 风扇安全状态已观测且新鲜，处于 enabled、无 E-STOP、无旧 active owner，并处于允许的
  被动 safe-stop 状态；
- 控制归属回读、进程 epoch/sequence 和跨字段状态一致。

ARMING 初期可以等待尚未出现的观测。明确危险、已观测安全回读过期，或已经满足过的必要
输入再次失效会锁存 INHIBITED。READY 丢失任一预检条件也会
INHIBITED，不自动恢复。

`actuation_allowed=True` 比 `required_inputs_fresh=True` 更严格：必须 ACTIVE、current authority
token committed、两 owner readback 匹配、E-STOP 明确 false、fan enabled、motor/fan mode 已
观测，并满足所有 Runtime safety gate。默认 takeover 关闭时永远 false。

## 两阶段控制归属交接

motor owner states 包含 `MANUAL/LEGACY_AUTO/NONE/FLIGHT_RESERVED/FLIGHT_CONTROL`；fan 包含
`LEGACY_MANUAL/LEGACY_AUTO/NONE/FLIGHT_RESERVED/FLIGHT_CONTROL`。

交接顺序：

1. Runtime 在 READY 后向电机/风扇请求 reserve；
2. 底层校验当前 token 与本地安全状态，清除旧目标/命令并阻止旧控制输入；
3. 两边 reserve 成功后分别 commit；
4. commit 响应只作为 owner 确认；
5. Runtime 还必须观察两路控制归属回读均为同一 token 的 `FLIGHT_CONTROL`；
6. 满足全部条件后执行单独的原子控制权提交。

两路确认的顺序不重要；重复响应、旧 token、cancel/inhibit 之后、READY 之前或格式错误的
响应都会被拒绝。任何一边失败都先在本地使 Runtime token/下发通道失效，再尽力撤销；绝不
回退到旧 owner。

## 原子截止点与命令包络

原子提交使用提交瞬间的最新 `FlightState.sequence` 形成不可变的
`arming_cutoff_state_sequence`，且不能早于 READY barrier。成功后：

- 控制器只重置一次；
- 提交前预览全部丢弃；
- 第一条可执行命令必须来自 `state_sequence > cutoff` 的新状态快照；
- 交接前命令不缓存、不复用；
- 命令包络携带当前 epoch/generation、严格递增的命令序号、状态序号、有限的生成时间
  （单调时钟）和完整且校验通过的 `FlightCommand`。

唯一的 Runtime → 执行器传输通道是 `/flight_control/command`。电机/风扇消费者各自重新
校验 token、sequence 和本域载荷；任一域的拒绝结果不会被另一域覆盖。

## 命令时效租约与心跳

Runtime 事务、底层交接和 ACTIVE 命令使用独立的本地单调时钟截止时间：

- Runtime handoff transaction 默认 `1.0 s`；
- motor/fan handoff lease 默认 `1.5 s`；
- motor/fan ACTIVE command lease 默认 `0.25 s`；
- best-effort revoke diagnostic deadline 默认 `0.25 s`。

reserve 启动交接租约，commit 不重置。只有第一条 token、sequence、截止点后状态和载荷都
合法的普通命令包络，才会结束交接租约并启动 ACTIVE 心跳租约。之后只有合法普通帧会刷新；
重复帧、错误 token、非法载荷和 safe-stop 都不会刷新。

这些值是当前生产默认值。v0.4.0 受限/失效后安全闭锁验证已覆盖相关版本场景，但本文不把
单次观测扩展为通用时序 SLA、控制性能标定或任意负载下的保证。

## 命令与 safe-stop 语义

普通 `FlightCommand` 包含完整电机帧和左右归一化风扇载荷。Runtime 严格校验不会静默填充
或限幅；电机软限位、运动步长/速率和风扇 PWM/斜率限制保留在底层管理器。

`FlightCommand.safe_stop()` 是不含载荷的控制意图：

- DRY_RUN 只发布预览；
- ACTIVE Runtime 先关闭可执行命令下发，使 token/sequence 失效并进入闭锁/回滚；
- 不复制上一帧，不将 `None` 替换为零；
- 不等于硬件 E-STOP，不清除 ERROR，不恢复旧 owner。

## 执行器适配器与最终否决权

电机适配器复用 `MotorManager` 的 `MotionSource.FLIGHT` 和唯一运动定时器，不新增
`FLIGHT_RUNNING` controller state；它在 `AUTO_RUNNING + owner=FLIGHT_CONTROL` 下继续应用
soft limit、maximum step、mode/motor speed limit、feedback/transport fault 和 write-failure
ERROR 路径。

风扇适配器不创建第二个 GPIO 控制器。`FanCommandManager` 继续是唯一普通 PWM 发布者；
`0` 映射为停止值，`(0,1]` 映射到配置的起始/最大区间并应用既有上升/下降斜率限制。
归一化命令不是推力比例。

Runtime、适配器或算法都不能绕过底层 E-STOP、ERROR、看门狗、租约、停用/生命周期状态、
软限位或关闭清理。

## 故障、回滚与关闭

以下任一条件都会关闭可执行命令门槛、使 token/sequence 失效，并使 Runtime 进入失效后
安全闭锁：

- 必要状态过期或无效；
- 权威安全状态未知、过期或冲突；
- E-STOP/ERROR；
- 控制归属回读丢失或进程 epoch 变化；
- 交接/命令租约超时；
- safe-stop 请求；
- 控制器加载、重置、更新或校验异常；
- Runtime 关闭/重启隔离失败；
- 命令包络、token、sequence 或载荷违规。

回滚顺序：

1. 在本地使控制权/token 失效；
2. 关闭可执行命令下发；
3. 清除待处理的交接/确认/命令跟踪；
4. 锁存 INHIBITED；
5. 对电机/风扇各执行一次非阻塞、尽力而为的撤销。

清理诊断区分未尝试、成功、服务不可用、超时、异常、拒绝和响应格式错误。清理失败不得
递归触发回滚，也不得重新打开下发通道；底层租约是 Runtime 崩溃或无响应时独立的失效后
安全闭锁后备机制。撤销不会自动恢复旧 owner。

Runtime executable 禁用 rclpy default SIGINT/SIGTERM handler，由 Python signal handler 保持
ROS context 在 `destroy_node()`/rollback 期间有效，node destruction 后才 shutdown context。
普通 executor/Runtime 错误不会伪装成正常信号退出。重启必须获得新的进程 PID、控制权
epoch 和完整的新交接；不得恢复旧 token、目标或命令序号。

## 不可妥协的安全不变量

- ERROR 和 INHIBITED 不因输入/通信恢复自动清除；
- 不自动恢复 MANUAL/AUTO/HOME、owner、控制权或旧目标；
- Runtime 不清除 ERROR/E-STOP，不启用硬件，不设置零点；
- 算法/Runtime 不直接访问 CAN/串口/GPIO/PWM/CyberGear 后端；
- 每条可执行普通命令都使用当前 token、截止点后状态和严格递增序号；
- safe-stop 永不携带执行器载荷；
- 未知状态使用 `None`/存在性标志，不用 false/zero/empty string 伪装；
- 不从力矩推导电流，不创建未经验证的 RPM/推力；
- motor/fan manager、watchdog、lease、soft limit、E-STOP 和 physical operator boundary 保持最终
  裁决权；
- 软件 CI/fake/mock/DRY_RUN 不表述为真实硬件验证。

新增字段或传输契约必须有可验证来源，并说明单位、坐标系/符号、存在性/`None`、有效性、
新鲜度和兼容性。删除字段、改变单位/存在性或放宽校验属于破坏性变更，需要独立迁移审查。
