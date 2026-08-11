# NEXT_COMMAND

## Task

v0.4.0 Task 1.1 — Flight API Contract Polish

## Objective

在进入 v0.4.0 Task 2（Structured State Integration / DRY_RUN Runtime）之前，对 Task 1 已建立的 Flight API v1 做一次小范围契约收口。

本任务只处理：

1. `safe_stop` 不再要求携带可执行的旧 motor/fan target；
2. startup / 未观测状态必须能与明确的 `False` / 正常状态区分；
3. 同步 Flight API 文档、架构文档、example/fake helpers 与纯软件测试；
4. 清理工作流文档中的工具身份措辞，并规范 `LATEST_FEEDBACK.md` 的 Git 状态表述。

本任务不得进入真实 Flight Runtime、真实 ROS state aggregation 或真实 actuator path。

---

## Baseline

当前开发基线：

- 稳定发布：v0.3.2
- v0.3.2 annotated tag 指向：`398ea9b035929f745be79c4d75cfd99d73c77702`
- v0.4.0 Task 1 已完成并提交到当前开发分支；
- 已建立 `docs/FLIGHT_CONTROL_ARCHITECTURE.md`、`docs/FLIGHT_CONTROL_API.md`、`windarmor_interfaces`、`windarmor_flight_control`、pure Python `FlightState` / `FlightCommand` / `FlightController`、validation、fake state 和 unit tests；
- 尚未接入真实 Flight Runtime 或 actuator takeover。

执行前依次阅读并遵守：

1. `AGENTS.md`
2. `docs/FLIGHT_CONTROL_ARCHITECTURE.md`
3. `docs/FLIGHT_CONTROL_API.md`
4. `docs/LATEST_FEEDBACK.md`
5. 当前 `docs/NEXT_COMMAND.md`

如果实际仓库状态与以上描述冲突，以仓库当前内容和 `AGENTS.md` 为准，并在反馈中说明。

---

## Safety and Git Constraints

本任务默认：

- 不执行真实硬件操作；
- 不访问或控制真实 CyberGear、电调、涵道风扇、IMU、GPIO、SocketCAN 或 USB-CAN；
- 不运行需要真实设备存在的 ROS 2 launch；
- 不授权 commit / push / tag；
- 不创建、移动或重建任何稳定 tag；
- 不修改 v0.3.0 / v0.3.1 / v0.3.2 已有标签；
- 不改变 v0.3.2 motor / fan safety state machine；
- ERROR 不自动恢复；
- transport reconnect 只恢复通信；
- 不自动恢复 MANUAL / AUTO / HOME；
- 不重发旧目标；
- 不从 torque 推导 `current_a`；
- 不把 `motor_current_limit_a` 解释为实时安培阈值保护；
- 不直接控制真实 GPIO / PWM / CyberGear driver。

如果实现需要违反以上任意一项，停止扩大任务范围并更新 `docs/LATEST_FEEDBACK.md`。

---

## Deliverable 1 — Redesign `safe_stop`

### Problem

当前 safe-stop command 仍要求携带完整 actuator target frame。这会产生不必要歧义：safe stop 本身不应依赖旧目标，在 stale input、algorithm exception 或 state invalid 等场景下也不应诱导算法复制上一帧目标来构造停止请求。

### Required Contract

调整 API，使：

```python
FlightCommand.safe_stop()
```

可以在**不提供 motor target 和 fan target**的情况下表达：

> 当前算法主动放弃继续提供普通 actuator command。

优先采用简单表达，例如：

```python
@dataclass(frozen=True)
class FlightCommand:
    motor_positions_rad: Mapping[str, float] | None
    fan_commands: FanCommand | None
    request_safe_stop: bool = False
```

并提供无参数：

```python
@classmethod
def safe_stop(cls) -> "FlightCommand":
    ...
```

等价方案可以接受，但必须满足：

- `safe_stop()` 不要求 motor/fan targets；
- safe-stop payload 不会被后续 Runtime 当成真实 actuator target；
- 不缓存、不复制、不重发上一帧 command；
- 不通过默认 `0.0` 制造伪目标。

不要在本任务引入复杂 command hierarchy，除非现有实现确有必要。

---

## Deliverable 2 — Safe-stop Validation Semantics

更新 pure validation，明确区分：

### Normal command

当 `request_safe_stop == False`：

- `motor_positions_rad` 必须存在；
- motor logical key 集合必须完整；
- 不得有未知 motor key；
- motor target 必须为有限数；
- `fan_commands` 必须存在；
- fan normalized command 必须在 `[0.0, 1.0]`；
- NaN / Inf 必须拒绝。

### Safe-stop command

当 `request_safe_stop == True`：

- 不要求 motor target；
- 不要求 fan target；
- 不通过 normal actuator payload validation 阻止 safe-stop；
- target payload 不参与执行。

如果调用方人为构造 `request_safe_stop=True` 同时又携带 actuator payload，优先采用：

> **拒绝混合语义。**

将最终契约同步到文档和 tests。

---

## Deliverable 3 — Unknown / Unobserved State Semantics

### Problem

未来 Runtime 刚启动时，可能尚未收到：

- fan enabled state；
- fan control state；
- motor control mode；
- E-STOP 状态；
- 其他系统状态。

必须能区分：

- 明确观测到 `False` / disabled；
- 尚未收到状态 / unobserved。

不得用默认 `False`、空字符串或随意 magic string 冒充“未观测”。

### Required Model Review

优先使用显式 Optional，例如：

```python
@dataclass(frozen=True)
class FanSystemState:
    left: FanChannelState
    right: FanChannelState
    enabled: bool | None
    control_state: str | None
```

以及：

```python
@dataclass(frozen=True)
class SystemState:
    command_authority: CommandAuthority
    e_stop_active: bool | None
    motor_control_mode: str | None
    fan_control_state: str | None
    flight_control_active: bool
    actuation_allowed: bool
    required_inputs_fresh: bool
```

请特别审查 `e_stop_active`：

> 未收到安全关键状态时，不得把“未知”误表示为“明确安全”。

如果选择保持 `e_stop_active: bool`，必须在 `FLIGHT_CONTROL_API.md` 中明确说明由谁保证该值已知，以及 Task 2 Runtime 在什么条件下才允许构造可供算法使用的 `FlightState`。

---

## Deliverable 4 — Observed / Valid / Fresh / Healthy Semantics

检查当前：

- `ImuState`
- `MotorState`
- `FanChannelState`
- `FanSystemState`
- `SystemState`

确保语义一致：

- `None`：当前没有可用的真实观测值；
- `valid`：数据结构 / 数值 / 协议意义上有效；
- `fresh`：最近观测满足 Flight Runtime 的 freshness 要求；
- `healthy`：subsystem 状态允许被认为健康。

不要求所有模型机械增加全部字段，但必须避免：

- 用 `0.0` 表示未知真实物理量；
- 用 `False` 表示尚未观测；
- 用空字符串表示 unknown。

本任务只修 core model / documentation / tests，不实现真实 ROS freshness timer。

---

## Deliverable 5 — Preserve True Immutability

确认修改后以下类型仍保持 immutable：

- `FlightState`
- `MotorState`
- `ImuState`
- `FanChannelState`
- `FanSystemState`
- `SystemState`
- `FlightCommand`
- `FanCommand`

优先继续使用 `@dataclass(frozen=True)`。

同时检查 `Mapping` 字段是否可能通过外部 mutable dict 被间接修改。如果存在风险，应采用轻量防护或 immutable representation，并补测试。

目标：

> 算法收到的 snapshot 在一次 `update(state, dt)` 调用期间不能被外部代码静默修改。

不要引入重量级依赖。

---

## Deliverable 6 — Update `FLIGHT_CONTROL_API.md`

至少同步：

- `FlightCommand.safe_stop()` 新契约；
- normal command vs safe-stop command；
- unknown / unobserved 的 `None` 语义；
- `False` 与 `None` 的区别；
- 算法不得保存旧 target 来构造 safe-stop；
- safe-stop 不等于 hardware E-STOP；
- safe-stop 不清 ERROR；
- safe-stop 不恢复任何控制模式；
- safe-stop 只表示算法主动放弃继续控制。

提供简洁示例：

```python
if not state.system.required_inputs_fresh:
    return FlightCommand.safe_stop()
```

不要展示复用旧 target 的示例。

---

## Deliverable 7 — Update `FLIGHT_CONTROL_ARCHITECTURE.md`

只同步与本任务相关的架构契约：

1. safe-stop 不携带可执行 actuator target；
2. safe-stop 后续由 Runtime 解释为撤销 / inhibit Flight authority 的请求；
3. 未观测状态不能默认成安全值；
4. Runtime 必须等关键 system state 可判断后才允许真实 actuator arming；
5. Task 1.1 仍未实现真实 Runtime / arming。

不要提前实现或展开 Task 2 的 Runtime 细节。

---

## Deliverable 8 — Example Controller and Fake Helpers

更新 example controller，确保：

- 展示 normal command；
- 必要时可以直接 `FlightCommand.safe_stop()`；
- 不要求保留 previous target；
- 不依赖 ROS；
- 不访问 hardware；
- 不加入真实 PID 或姿态控制参数。

更新 fake state helper，使其可方便构造：

- fully observed healthy state；
- unobserved fan/system state；
- stale / invalid state；
- safe-stop 相关测试状态。

fake default 不得被解释为未来 Runtime 的真实安全默认值。

---

## Deliverable 9 — Tests

至少覆盖：

### Safe stop

- `FlightCommand.safe_stop()` 无参数可构造；
- 不要求 motor targets；
- 不要求 fan targets；
- safe-stop validation 通过；
- safe-stop 不调用任何 hardware；
- safe-stop 不依赖 previous command；
- 如果采用“拒绝混合 payload”，覆盖 rejection test。

### Normal command

- 完整 motor frame 通过；
- 缺 motor key 拒绝；
- 未知 motor key 拒绝；
- motor NaN / Inf 拒绝；
- fan `0.0` / `1.0` 通过；
- fan 越界拒绝。

### Unknown states

- `enabled=None` 与 `enabled=False` 可区分；
- `control_state=None` 与真实字符串状态可区分；
- system control mode 未观测可以表示；
- 不使用空字符串表达 unknown。

### Immutability

- frozen dataclass direct mutation；
- 如适用，mapping 底层 mutation 风险。

### Pure dependency boundary

继续确认 core / algorithms 不需要 ROS runtime。

---

## Deliverable 10 — Documentation Wording Cleanup

对本任务会修改到的工程文档使用工程化、工具无关措辞。

特别检查 `docs/NEXT_COMMAND.md`：不要在公开工程文档中列举具体生成工具、实现助手或模型名称作为反例。

统一表达为：

> 工程代码、注释、正式文档和测试说明应描述设计与行为，不记录生成工具或实现助手身份。

本任务不要扩大成全仓库文字清理；全面 cleanup 留给后续独立任务。

---

## Deliverable 11 — `LATEST_FEEDBACK.md` Git Status Semantics

完成后更新 `docs/LATEST_FEEDBACK.md`，只保留本任务最新反馈。

Git 状态描述必须使用不会与后续独立授权操作产生歧义的格式，例如：

```text
## Git 状态（反馈生成时）

- HEAD: <sha or working tree state>
- 本任务实现/验证阶段是否执行 commit: ...
- 本任务实现/验证阶段是否执行 push: ...
- 本任务实现/验证阶段是否执行 tag: ...
- 远端状态是否在本任务内核验: ...
```

重点：

- 描述“反馈生成时”和“本任务执行阶段”；
- 不声称后续不会获得新的 Git 授权；
- 不把后续用户独立执行的 Git 操作描述成任务执行阶段行为。

本任务本身仍然不授权 commit / push / tag。

---

## Compatibility Requirements

本任务不得改变：

- 现有 IMU runtime；
- 现有 motor runtime；
- 现有 fan runtime；
- 现有 ROS topic / service；
- legacy AUTO；
- MANUAL；
- HOME；
- ERROR；
- E-STOP；
- transport recovery；
- motor feedback health；
- motor temperature protection；
- fan safety；
- actuator command dispatch。

不得新增：

- real Flight Runtime node；
- `/motors/feedback` 真实 publisher；
- StateAggregator ROS subscription；
- `MotionSource.FLIGHT`；
- fan `FLIGHT_CONTROL` source；
- authority grant service；
- real command envelope dispatch；
- real actuator write。

---

## Versioning

本任务仍属于 v0.4.0 开发阶段。

保持新 package 版本为 `0.4.0`，除非当前仓库存在明确构建问题。

不要在本任务修改现有三个稳定 package 的版本。

---

## Validation

仅运行无硬件验证。

至少执行：

1. `windarmor_flight_control` pure unit tests；
2. `windarmor_interfaces` build / interface tests；
3. Task 1 已有 flight/interface tests；
4. 现有 motor/fan/IMU 无硬件回归测试；
5. workspace 适用的 `colcon build`；
6. workspace 适用的 `colcon test`；
7. `colcon test-result --verbose`。

如果某些 package 需要真实硬件，不要启动设备或修改测试去访问真实硬件；使用现有 mock / fake / CI 路径。

反馈记录：

- exact commands；
- pass/fail count；
- warnings；
- skipped tests；
- 环境相关限制。

---

## Expected Result

Task 1.1 完成后：

1. `FlightCommand.safe_stop()` 不需要 motor/fan targets；
2. safe-stop 不携带或不允许携带可执行 actuator payload；
3. normal `FlightCommand` 仍要求完整 motor frame；
4. startup unknown state 可以与明确 `False` / 正常状态区分；
5. Flight API 不使用伪造默认安全状态；
6. `FlightState` / `FlightCommand` 保持真正 immutable；
7. API / architecture docs 与代码一致；
8. example / fake state / tests 与新契约一致；
9. pure CI 全通过；
10. 真实 Runtime / actuator path 仍不存在；
11. v0.3.2 safety 行为完全不变。

完成后，Flight API v1 可作为进入 Task 2 前的冻结候选。

---

## Out of Scope

明确不做：

- Task 2 Structured State Integration；
- real Flight Runtime；
- real ROS StateAggregator；
- real `/motors/feedback` integration；
- command authority takeover；
- ARMING / ACTIVE / INHIBITED runtime；
- generation 实际 actuator validation；
- motor FLIGHT source；
- fan FLIGHT_CONTROL source；
- real PWM mapping；
- real motor dispatch；
- real hardware verification；
- IMU calibration；
- fan thrust/RPM calibration；
- current measurement research；
- repository full cleanup；
- 删除 `FIRST_COMMAND.md`；
- 删除 `MANUAL_VERIFICATION.md`；
- release；
- GitHub Release；
- commit / push / tag。

---

## Stop Conditions

遇到以下任意情况必须停止扩大任务并报告：

- 修 safe-stop 必须修改真实 motor/fan runtime；
- 必须接真实 actuator 才能完成测试；
- 必须改变 ERROR / E-STOP 语义；
- 必须自动恢复控制模式；
- 必须复用旧 target 才能实现 safe-stop；
- 必须用默认 `False` 冒充未知安全状态；
- 必须从 torque 推导 current；
- 必须修改稳定 tag；
- 必须删除现有 ROS public interface；
- 修改范围开始扩展到 Task 2 Runtime integration。

本任务应保持为一个小型 API contract polish。

---

## Final Report

完成后更新 `docs/LATEST_FEEDBACK.md`，至少包含：

- 修改文件列表；
- safe-stop 最终数据模型；
- safe-stop validation 契约；
- unknown / unobserved 最终表达方式；
- 是否调整 `e_stop_active` 类型及理由；
- immutable mapping 的处理方式；
- 与本任务建议设计相比的偏差及原因；
- 所有软件验证命令；
- 测试结果；
- warnings / skipped tests；
- 是否触碰现有 runtime；
- 是否发现 Task 2 阻塞项；
- Git 状态（反馈生成时）；
- 明确说明本任务未执行真实硬件操作。

反馈内容使用工程化、工具无关措辞。
