# NEXT_COMMAND

## Task

v0.4.0 Task 1 — Flight Control Core & Interface Foundation

## Objective

为 WindArmor 建立稳定、低耦合的飞控算法开发边界，使后续算法开发成员可以：

- 不依赖 ROS 2、CAN、GPIO、串口或底层硬件驱动编写飞控算法；
- 通过稳定的 `FlightState` 获取 IMU、电机、风扇和系统状态；
- 通过稳定的 `FlightCommand` 返回电机位置目标、风扇归一化目标和安全停止请求；
- 使用 fake state / unit tests 在无 Raspberry Pi、无真实硬件条件下开发和验证算法；
- 不具备绕过现有安全状态机、直接访问硬件、清除 ERROR / E-STOP、重新使能硬件或设置零点的能力。

本任务只建立 v0.4.0 的核心架构与纯软件 API 基础，不接入真实 actuator command path。

---

## Safety and Git Constraints

必须遵守仓库根目录 `AGENTS.md`。

本任务默认：

- 不执行任何真实硬件操作；
- 不访问或控制真实 CyberGear、电调、涵道风扇、IMU、GPIO、SocketCAN 或 USB-CAN；
- 不执行需要真实设备存在的 ROS 2 launch；
- 不授权 commit；
- 不授权 push；
- 不授权 tag；
- 不创建或移动任何已有 tag；
- 不修改 v0.3.0 / v0.3.1 / v0.3.2 已有稳定标签；
- 不改变 v0.3.2 的既有安全语义；
- 不自动恢复 ERROR；
- transport 恢复不得自动恢复 MANUAL / AUTO / HOME；
- 不重发旧目标；
- 不从 torque 推导未经验证的 `current_a`；
- 不把 `motor_current_limit_a` 重新解释为实时安培保护；
- 不绕过现有 motor / fan safety state machine；
- 不新增直接控制真实 GPIO、PWM 或 CyberGear driver 的飞控路径。

如果实现需要违反以上任意一条，立即停止并在 `docs/LATEST_FEEDBACK.md` 中说明原因，不继续扩大修改范围。

---

## Architecture Baseline

本阶段正式采用以下核心边界：

```text
ROS / Hardware World
        |
        v
Flight Runtime / Adapters
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

算法层必须与 ROS 2 和硬件 I/O 解耦。

以下目录中的纯算法代码不得依赖：

- `rclpy`
- `sensor_msgs`
- `std_msgs`
- `geometry_msgs`
- `can`
- `serial`
- GPIO / PWM backend
- CyberGear driver
- SocketCAN
- ROS topic / service 名称

---

## Deliverable 1 — Architecture Document

新增：

`docs/FLIGHT_CONTROL_ARCHITECTURE.md`

该文档作为飞控架构的长期 source of truth，初始基线为 v0.4.0。

至少包含：

### 1. Goals

说明目标：

- 飞控算法与硬件实现解耦；
- 飞控算法与 ROS transport 解耦；
- 现有 safety layer 保持最终裁决权；
- 一个新算法成员只需要理解 Flight API，不需要理解 CyberGear、GPIO、PWM、CAN transport recovery 等实现细节。

### 2. Package Boundaries

记录计划中的 package：

```text
imu_cybergear_ros2
windarmor_fan_controller
windarmor_interfaces
windarmor_flight_control
windarmor_bringup
```

说明：

- `windarmor_interfaces`：ROS package 间的结构化消息契约；
- `windarmor_flight_control`：Flight Core、算法接口与后续 Runtime；
- `imu_cybergear_ros2` / `windarmor_fan_controller`：继续拥有实际硬件与现有 safety；
- `windarmor_bringup`：后续负责选择是否启动 Flight Runtime；
- 本任务不实现真实 actuator takeover。

### 3. Flight API Boundary

记录：

```python
class FlightController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

要求：

- `reset()` 只重置算法内部状态；
- 不得重置硬件；
- 不得清 ERROR；
- 不得清 E-STOP；
- 不得 set motor zero；
- 不得 enable hardware。

### 4. Command Authority Contract

记录已经确认的设计：

```text
NONE
MANUAL
LEGACY_AUTO
FLIGHT_CONTROL
```

并明确：

- 同一时刻只能有一个普通 command owner；
- `CommandAuthority` 与既有 `ControllerState` 正交；
- 不新增 `FLIGHT_RUNNING` 到现有 ControllerState；
- `FLIGHT_CONTROL` 后续复用 `AUTO_RUNNING` 的硬件安全语义，但由 authority 区分命令来源；
- authority grant 必须带 generation；
- 旧 generation command 永远拒绝；
- Flight failure 后不得自动赋予 MANUAL authority；
- `INHIBITED` 不得自动恢复 `ACTIVE`；
- E-STOP / ERROR 永远高于 command authority。

本任务只文档化该契约，不要求接入现有 actuator。

### 5. Non-negotiable Safety Contracts

必须明确记录：

- ERROR 不自动恢复；
- transport 重连只恢复通信，不恢复运行状态；
- 不自动恢复 MANUAL / AUTO / HOME；
- 不重发旧目标；
- Flight Runtime 不得清除 ERROR / E-STOP；
- Flight Runtime 不得直接访问 CyberGear driver；
- Flight Runtime 不得直接写 GPIO / PWM；
- Flight motor command 后续必须经过现有 MotorManager 安全路径；
- Flight fan command 后续必须经过现有 fan command manager；
- 不创建虚假的 `current_a`、RPM 或 thrust；
- 没有真实反馈时不得用 `0.0` 冒充真实物理状态。

### 6. Version Note

注明该架构：

> Initial architecture baseline introduced for v0.4.0.

不要把文档写成一次性任务说明。

---

## Deliverable 2 — Flight Control API Document

新增：

`docs/FLIGHT_CONTROL_API.md`

这是以后提供给飞控算法开发成员的主要文档。

本任务先建立 v1 初版，至少说明：

- 算法入口；
- `FlightState`；
- `FlightCommand`；
- 单位；
- `None / valid / fresh / healthy` 语义；
- 禁止调用的能力；
- fake state 示例；
- unit test 示例；
- 当前不授权真实 actuator；
- 当前 API 为 v0.4.0 foundation，后续 runtime 接入时保持兼容优先。

文档内容必须描述工程接口，不出现生成工具、助手或 AI 相关措辞。

---

## Deliverable 3 — New `windarmor_interfaces` Package Skeleton

新增 ROS 2 interface package：

`src/windarmor_interfaces`

采用适合 ROS custom interfaces 的标准结构。

本任务只建立最小、可构建骨架，以及后续结构化 motor feedback 所需要的消息定义。

至少新增：

### `MotorFeedback.msg`

字段应表达真实可验证的数据，不得加入虚构字段。

建议语义至少覆盖：

- logical motor name
- CAN ID
- position rad
- velocity rad/s
- torque Nm
- temperature C
- device mode
- fault flags
- feedback age
- has feedback
- healthy

如果 ROS message 无法原生表达 Python `None`，必须通过明确的 validity / presence 字段表达“没有反馈”，并在文档中说明。

禁止新增：

- `current_a`

除非仓库内已经存在经过验证的真实 current feedback 来源；本任务不得通过 torque 推导。

### `MotorFeedbackArray.msg`

用于发布完整电机 feedback snapshot。

本任务可以只定义接口与构建测试，不要求修改现有电机节点去发布该 topic；真实 integration 留给后续 Task 2。

如果实现中认为 message 字段需要调整，优先保证：

- 明确单位；
- 明确 presence；
- 不伪造物理量；
- 后续 FlightState adapter 易于消费。

---

## Deliverable 4 — New `windarmor_flight_control` Package

新增：

`src/windarmor_flight_control`

采用 `ament_python`。

建议结构：

```text
windarmor_flight_control/
├── windarmor_flight_control/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── controller.py
│   │   ├── validation.py
│   │   └── authority.py
│   └── algorithms/
│       ├── __init__.py
│       ├── base.py
│       └── example_controller.py
├── test/
├── package.xml
└── setup.py
```

本任务不要新增真实 ROS runtime node，不要订阅真实 topic，不要发布 actuator command。

---

## Deliverable 5 — Pure Python Data Models

在 `windarmor_flight_control/core/models.py` 中建立 immutable data models。

优先使用：

- `@dataclass(frozen=True)`
- 明确类型
- 明确 SI 单位
- `None` 表示从未获得或当前未知的真实物理值

建议定义以下模型。

### Vector / Quaternion

可以建立轻量纯 Python 类型：

```python
Vector3
Quaternion
```

不得依赖 ROS message class。

### `ImuState`

建议包含：

- orientation quaternion
- roll_rad
- pitch_rad
- yaw_rad
- relative_roll_rad
- relative_pitch_rad
- angular_velocity_rad_s
- linear_acceleration_m_s2
- sample_age_sec
- valid
- fresh
- connected
- zero_generation

本任务不要添加没有当前契约依据的 `relative_yaw_rad`。

### `MotorState`

建议包含：

- name
- position_rad: float | None
- velocity_rad_s: float | None
- torque_nm: float | None
- temperature_c: float | None
- device_mode
- fault_flags
- feedback_age_sec
- has_feedback
- valid
- fresh
- healthy

禁止加入未经验证的 `current_a`。

### `FanChannelState`

建议包含：

- applied_command: float | None
- output_known: bool

算法层 fan command 使用无量纲 `[0.0, 1.0]`，不得直接暴露 PWM microseconds 作为主要算法 API。

不要虚构：

- RPM
- thrust

### `FanSystemState`

建议包含：

- left
- right
- enabled
- control_state

### `SystemState`

至少表达：

- command_authority
- e_stop_active
- motor_control_mode
- fan_control_state
- flight_control_active
- actuation_allowed
- required_inputs_fresh

### `FlightState`

建议：

```python
@dataclass(frozen=True)
class FlightState:
    timestamp_sec: float
    sequence: int
    imu: ImuState
    motors: Mapping[str, MotorState]
    fans: FanSystemState
    system: SystemState
```

要求：

- snapshot immutable；
- logical motor name 不直接等同于 CAN ID；
- 不假设尚未正式确认的机械命名；
- 不以 `0.0` 表示未知真实反馈。

---

## Deliverable 6 — Pure Python Command Models

定义：

### `FanCommand`

建议：

```python
@dataclass(frozen=True)
class FanCommand:
    left: float
    right: float
```

约束：

```text
0.0 <= command <= 1.0
```

`0.0` 表示停止请求，`1.0` 表示 Flight API 所允许的最大归一化请求。

具体 PWM 映射不属于算法层。

### `FlightCommand`

建议：

```python
@dataclass(frozen=True)
class FlightCommand:
    motor_positions_rad: Mapping[str, float]
    fan_commands: FanCommand
    request_safe_stop: bool = False
```

要求：

- 正常 control tick 返回完整目标 frame；
- 不允许通过“省略某个 motor”隐式保留旧目标；
- 后续 runtime 必须验证 motor key 集合；
- 本任务只实现模型与 validation，不下发真实硬件。

可提供：

```python
FlightCommand.safe_stop(...)
```

但其语义只代表：

> 算法主动放弃继续控制。

不得等同于硬件 E-STOP，也不得调用 ERROR recovery。

---

## Deliverable 7 — `FlightController` Contract

在纯 Python core 中定义稳定 controller protocol / ABC。

建议公开：

```python
class FlightController(Protocol):
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

或者等价的 ABC，选择更简单、可测试、依赖更少的方案。

要求：

- 不依赖 ROS；
- `reset()` 不接受硬件对象；
- `update()` 不接受 ROS node；
- `update()` 不进行 hardware I/O；
- 算法可以在普通 Python unit test 中直接运行。

---

## Deliverable 8 — Command Authority Pure Model

在 `core/authority.py` 中建立纯 Python：

```text
NONE
MANUAL
LEGACY_AUTO
FLIGHT_CONTROL
```

以及必要的基础数据结构。

可以预留：

- generation
- sequence

但本任务不要求把它接入现有 motor / fan 节点。

不要在本任务修改现有 `ControllerState` 去新增 `FLIGHT_RUNNING`。

---

## Deliverable 9 — Pure Validation

在 `core/validation.py` 实现纯函数 validation。

至少覆盖：

### State validation

- 非有限数值；
- negative age；
- inconsistent feedback presence；
- required motor logical names；
- fan command representation；
- 必要字段缺失。

### FlightCommand validation

至少拒绝：

- NaN；
- Inf；
- fan command < 0；
- fan command > 1；
- motor target 非有限数值；
- motor key 集合不完整；
- 未知 motor key。

validation 不得做真实硬件 clamp。

安全原则：

> 对算法 API 的非法 command 应明确拒绝，不应通过静默修正掩盖算法错误。

实际硬件软限位和推进限制仍属于后续 actuator adapter / 现有 safety layer。

---

## Deliverable 10 — Example Controller

新增一个非常简单的：

`algorithms/example_controller.py`

目的只是演示 API，不实现真实飞控。

建议行为：

- 读取 `FlightState`；
- 不做 ROS import；
- 返回中性 / 安全的示例 `FlightCommand`；
- 明确注释“仅用于 API 示例与测试，不代表真实飞控算法”。

不要加入未经验证的 PID 参数或机器人姿态控制逻辑。

---

## Deliverable 11 — Fake State Helpers and Unit Tests

必须提供足够的无硬件测试，使其他成员可以在普通开发环境理解和使用 API。

至少测试：

### Imports

确认 pure core / algorithms 不会 import：

- `rclpy`
- hardware libraries

### Immutability

确认 `FlightState` / 子状态 / `FlightCommand` 不可被算法意外修改。

### Unknown feedback

确认：

- 没有反馈时使用 `None` / presence flag；
- 不会把 `0.0` 当作默认真实位置。

### Fan validation

确认：

- `0.0` 和 `1.0` 有效；
- 越界拒绝；
- NaN / Inf 拒绝。

### Motor command completeness

使用测试定义的逻辑 motor names 验证：

- 完整目标通过；
- 少一个 motor 拒绝；
- 多一个未知 motor 拒绝。

### Safe stop

确认 `request_safe_stop` 是 Flight API 状态，不触发任何硬件操作。

### Example controller

使用 fake `FlightState` 调用：

```python
controller.reset()
controller.update(state, dt)
```

不需要 ROS graph 或真实硬件。

---

## Deliverable 12 — Package Versioning

本任务属于 v0.4.0 开发阶段。

如果新 package 需要初始版本：

```text
0.4.0
```

不要在本任务提前修改三个现有稳定 package 的版本，除非构建系统有严格必要性。

如确有必要修改现有 package version，必须在 `docs/LATEST_FEEDBACK.md` 明确说明原因。

---

## Repository Documentation Rules

本任务新增或修改的：

- 源代码注释；
- README；
- architecture docs；
- API docs；
- tests；
- package metadata；

应使用工程化、工具无关措辞。

不要写：

- AI generated
- generated by ...
- ChatGPT
- Codex
- assistant suggested
- model generated

描述“设计是什么、为什么、如何验证”，不要描述由哪个工具产生。

本任务不要顺手大规模清理旧仓库内容。

仓库冗余、旧文档和 stale wording 的集中清理保留给后续独立任务，避免 Task 1 diff 过大。

---

## Existing Files That Must Not Be Removed in This Task

本任务不要删除：

- `docs/FIRST_COMMAND.md`
- `docs/MANUAL_VERIFICATION.md`
- 任何 v0.3.2 release / RC verification 文档
- 现有 ROS topics / services
- 现有 legacy AUTO 实现
- 现有 safety logic

这些内容将在后续 repository cleanup task 中单独审计。

---

## Compatibility Requirements

本任务必须保持：

- v0.3.2 现有包可以继续构建；
- 现有 motor / fan / IMU runtime 行为不改变；
- 现有 ROS 接口不被破坏；
- 不改变任何真实 actuator 默认行为；
- 不改变启动时 MANUAL / AUTO / HOME / ERROR 语义；
- 不改变 e-stop；
- 不改变 transport reconnect；
- 不改变 motor feedback timeout 默认值；
- 不改变 fan command manager 的现有安全行为。

---

## Validation Commands

仅运行无硬件验证。

优先执行仓库现有 Hosted CI 等价的软件测试命令。

至少需要验证：

1. 新 `windarmor_interfaces` package 能完成接口生成 / build；
2. 新 `windarmor_flight_control` package 能 build；
3. pure Python unit tests 通过；
4. existing repository tests 不回归；
5. core / algorithms 不依赖 ROS runtime；
6. 不需要 Raspberry Pi 或任何真实设备即可完成验证。

如果仓库使用：

```bash
colcon build
colcon test
colcon test-result --verbose
```

可以在无硬件条件下运行适用的 package / workspace 范围。

禁止为了让测试通过而访问真实：

- `/dev/*`
- CAN interface
- GPIO
- USB serial
- physical ESC
- CyberGear
- fan

---

## Expected Result

Task 1 完成后，应达到：

1. 仓库存在正式的 `docs/FLIGHT_CONTROL_ARCHITECTURE.md`；
2. 仓库存在初版 `docs/FLIGHT_CONTROL_API.md`；
3. 存在 `windarmor_interfaces`；
4. 存在 `windarmor_flight_control`；
5. `FlightState` / `FlightCommand` / `FlightController` 可在纯 Python 中使用；
6. 存在 example controller；
7. 存在 fake state / unit tests；
8. 一个新的算法开发成员可以不理解底层 ROS / CAN / GPIO 代码就开始实现算法；
9. Flight API 还不能控制真实 hardware；
10. v0.3.2 所有稳定 safety 语义保持不变。

---

## Out of Scope

以下内容明确不属于本任务：

- 真实 Flight Runtime ROS node；
- 真实 `/motors/feedback` 发布接入；
- `StateAggregator` 订阅真实硬件 topic；
- `MotionSource.FLIGHT`；
- fan `FLIGHT_CONTROL` source；
- actuator takeover；
- authority grant service；
- ARMING / ACTIVE / INHIBITED runtime state machine；
- generation 在真实 actuator path 中的校验；
- real fan PWM mapping；
- real motor target dispatch；
- 修改 legacy AUTO 行为；
- 删除 legacy AUTO；
- 删除旧 docs；
- 仓库全面 cleanup；
- IMU 实机标定；
- 风扇 thrust/RPM 标定；
- CyberGear current 研究；
- 任何实机测试；
- release；
- GitHub Release；
- commit / push / tag。

---

## Final Report

完成后更新：

`docs/LATEST_FEEDBACK.md`

只保留本任务最新反馈。

反馈至少包含：

- 修改文件列表；
- 新增 package / interface 列表；
- Flight API 最终字段；
- 与本任务原设计相比的必要偏差及原因；
- 所有运行的软件验证命令；
- 测试结果；
- 是否存在 warning；
- 是否触碰现有 runtime 行为；
- 是否发现需要留到 Task 2 的阻塞项；
- 明确说明未执行真实硬件操作；
- 明确说明未执行 commit / push / tag。

不要在反馈中使用 AI / 助手身份相关措辞。

---

## Stop Conditions

遇到以下情况必须停止扩大任务范围并报告：

- 需要改变 v0.3.2 安全语义；
- 需要操作真实 hardware；
- 需要移动或重建稳定 tag；
- 需要删除现有 ROS interface 才能实现；
- 需要直接让 Flight API 控制 CyberGear / GPIO / PWM；
- 需要从 torque 推导 `current_a`；
- 需要让 Flight Runtime 自动恢复 ERROR；
- 需要实现真实 actuator takeover 才能完成 Task 1；
- 现有 workspace 无法在不改安全逻辑的情况下加入新 package。

本任务以“建立稳定、纯软件、无硬件副作用的 Flight API foundation”为唯一目标。