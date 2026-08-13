# NEXT_COMMAND

## Task

v0.4.0 Task 6.2 — Bounded Hardware Verification Controller & Final Test Readiness

## Objective

在当前 `918270e` 基线上，为即将开始的 v0.4.0 实机验证准备一个专用、保守、可预测的 hardware verification controller，并完成最终测试前的软件准备。

本任务的目标是：

> 准备真实硬件验证所必需的最小测试工具，然后停止继续扩展软件架构，转入真实系统验证。

本任务不再继续增加新的 authority / ownership / verification framework。

完成本任务后，如果软件验证全部通过，下一步应直接进入逐阶段 hardware verification，而不是继续预先设计 Task 6.3、6.4、6.5。

---

# Baseline

当前开发基线：

```text
918270e
实现只读硬件观测路径
```

当前已经完成：

- FlightState / FlightCommand API；
- 独立算法开发模块；
- Structured State；
- DRY_RUN；
- authoritative motor / fan safety readback；
- authority epoch / generation；
- owner reserve / commit / revoke；
- atomic authority commit；
- post-grant new-state barrier；
- MotorManager Flight adapter；
- FanCommandManager Flight adapter；
- Flight command timeout；
- rollback fail-closed；
- handoff lease / active command lease；
- observation-only hardware path；
- repository cleanup；
- algorithm developer handoff；
- v0.4.0 hardware verification plan。

除非本任务发现明确的软件缺陷，上述架构均视为冻结基线。

不要继续为了测试便利重新设计：

- AuthorityStateMachine；
- ownership protocol；
- authority epoch；
- generation；
- FlightCommandEnvelope；
- command leases；
- MotorManager；
- FanCommandManager。

---

# Required Reading

执行前必须阅读：

1. `AGENTS.md`
2. `README.md`
3. `docs/HARDWARE_REFERENCE.md`
4. `docs/FLIGHT_CONTROL_ARCHITECTURE.md`
5. `docs/FLIGHT_CONTROL_API.md`
6. `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`
7. `docs/LATEST_FEEDBACK.md`
8. 当前 `docs/NEXT_COMMAND.md`

还必须检查：

- `windarmor_flight_control/algorithms/`
- current controller loader
- `FlightState`
- `FlightCommand`
- Flight Runtime command validation
- motor ownership / Flight target path
- fan ownership / Flight normalized command path
- Flight config
- motor/fan config
- current software tests

如果仓库 HEAD、分支或用户已有修改与本任务描述不同：

- 不覆盖用户修改；
- 不 reset；
- 不 checkout；
- 不 clean；
- 先报告差异；
- 以 `AGENTS.md` 为最高安全和 Git 规则。

---

# Hardware Authorization Boundary

默认硬件状态必须按以下前提处理：

```text
CyberGear motors: NOT POWERED
ducted fans / ESCs: NOT POWERED
```

本任务：

- 不要求用户给 CyberGear 通电；
- 不要求用户给 fan / ESC 通电；
- 不执行真实 motor movement；
- 不执行真实 fan PWM；
- 不执行真实 Flight takeover；
- 不执行 powered hardware verification；
- 不打开真实 SocketCAN；
- 不打开真实 IMU serial；
- 不访问 `/dev/*`；
- 不初始化 GPIO/PWM。

如果实现或验证过程中发现必须进行真实硬件测试：

```text
STOP
```

先在 `docs/LATEST_FEEDBACK.md` 中说明：

1. 为什么必须进行硬件测试；
2. 需要给哪些硬件通电；
3. 是否会产生运动；
4. 风险范围；
5. 用户需要执行的完整命令和步骤；
6. 预期结果；
7. 停止条件。

未经用户新的明确授权不得继续。

---

# Git Constraints

本任务默认：

- 不授权 commit；
- 不授权 push；
- 不授权 tag；
- 不创建 GitHub Release；
- 不创建、移动、删除或重建稳定 tag。

必须保持：

- v0.3.0 tag 不变；
- v0.3.1 tag 不变；
- v0.3.2 tag 不变。

---

# Safety Baseline

不得改变：

- ERROR 不自动恢复；
- E-STOP clear 不自动恢复 Flight；
- transport reconnect 不自动恢复运行状态；
- MANUAL / LEGACY_AUTO / HOME 不自动恢复；
- old target 不重发；
- old authority epoch 不恢复；
- old generation 不恢复；
- Flight release 不自动恢复 legacy owner；
- motor ownership semantics；
- fan ownership semantics；
- command timeout；
- handoff lease；
- active command lease；
- `motor_feedback_timeout_sec=0.0`；
- `flight_takeover_enabled=false` 默认；
- torque 不得推导 `current_a`；
- fan normalized command 不是 thrust fraction。

---

# Deliverable 1 — Dedicated Hardware Verification Controller

在：

```text
src/windarmor_flight_control/windarmor_flight_control/algorithms/
```

新增明确命名的 verification controller，例如：

```text
bounded_verification_controller.py
```

具体文件名可以按当前项目命名风格调整。

它仍然必须严格实现现有算法接口：

```python
reset()

update(
    state: FlightState,
    dt: float,
) -> FlightCommand
```

不得修改 Flight API。

不得 import：

- `rclpy`
- ROS message
- CAN
- CyberGear driver
- serial
- GPIO
- PWM

---

# Deliverable 2 — Feedback-relative Motor Baseline

verification controller 不得把：

```text
0.0 rad
```

当作真实机器人机械中位。

真实 motor verification command 必须基于：

```text
fresh
valid
healthy
MotorState.position_rad
```

建立 feedback-relative baseline。

基本逻辑：

```text
selected test motor
    = captured baseline position + configured bounded offset

all other motors
    = captured baseline position
```

必须使用 Flight API logical motor name。

不得让算法依赖 CAN ID。

如果任意 required motor：

- missing；
- stale；
- invalid；
- unhealthy；
- position unknown；

则必须返回：

```python
FlightCommand.safe_stop()
```

---

# Deliverable 3 — Complete Motor Frame

normal verification command 必须继续满足 Flight API 完整 frame 契约。

例如 required motors 为：

```text
left_lift
left_pitch
right_pitch
right_lift
```

则每一条 normal command 必须同时包含全部 motor target。

不得通过：

```text
missing key
```

表达：

```text
hold previous target
```

不得复用旧目标。

非测试 motor 必须明确使用 captured feedback-relative hold position。

---

# Deliverable 4 — No Invented Real Hardware Offset

本任务不得凭空决定真实测试偏移，例如：

```text
0.05 rad
5 deg
10 deg
```

除非当前仓库已经存在明确、经过真实机械验证、适合作为 Flight hardware verification 的依据。

如果不存在：

真实 hardware config 中必须保持：

```text
motor test offset disabled
```

或使用等价明确 fail-closed 配置。

软件 unit test 可以注入 fake offset，例如任意有限测试值，以验证数学和 command contract。

但是：

> fake unit-test value 不能自动成为未来实机默认值。

在真实执行前，motor test offset 必须由用户明确确认。

---

# Deliverable 5 — Explicit Test Motor

controller 必须使用显式配置：

```text
test_motor_name
```

并验证该名称属于当前 required logical motor names。

不得：

- 自动轮询 4 个 motor；
- 自动依次运动；
- 根据 CAN ID 选择；
- 随机选择；
- 启动后自动切换测试轴。

未来实机验证必须一次只测试一个明确 motor axis。

---

# Deliverable 6 — Baseline Capture

verification controller 必须有明确 baseline capture 语义。

建议：

```text
RESET
    ↓
WAIT_VALID_ACTIVE_STATE
    ↓
CAPTURE_BASELINE
    ↓
COMMAND
```

baseline 至少包含每个 required motor 的：

```text
position_rad
```

要求：

- baseline 只从 fresh + valid + healthy FlightState 获取；
- baseline capture 后不能逐 tick 重新累加 offset；
- authority session 变化后旧 baseline 不得继续使用；
- `reset()` 后旧 baseline 清除；
- controller重新进入新的 authority session 时必须重新 capture。

---

# Deliverable 7 — No Cumulative Drift

禁止实现：

```python
target += offset
```

或：

```text
previous target + offset
```

这种逐周期累积行为。

必须始终是：

```text
captured baseline + configured offset
```

例如：

```text
baseline = 1.00 rad
offset   = 0.02 rad

every update:
target = 1.02 rad
```

不能变成：

```text
1.02
1.04
1.06
...
```

必须有 unit test 覆盖。

---

# Deliverable 8 — Authority Session Isolation

verification baseline 不得跨 authority session 复用。

至少需要根据当前 existing FlightState / Runtime 可用 metadata 检查：

- authority active；
- generation；
- 如 FlightState 已提供 authority epoch，则同时检查 epoch。

如果 authority generation / epoch 改变：

```text
clear baseline
return safe-stop until new valid baseline captured
```

不要让上一次 Flight takeover 的测试 target进入新 takeover。

---

# Deliverable 9 — Default Fan Command Is STOP

verification controller 默认：

```text
fan left  = 0.0
fan right = 0.0
```

这必须是默认且 fail-closed 的行为。

因此未来 motor hardware verification 时：

```text
motor = bounded feedback-relative command
fan   = explicit STOP
```

不得因为 normal FlightCommand 要求 fan payload 就自动给 fan非零输出。

---

# Deliverable 10 — Optional Bounded Fan Verification

controller 可以支持显式配置：

```text
fan_left_test_command
fan_right_test_command
```

用于未来 fan physical test。

要求：

```text
0.0 <= command <= 1.0
```

默认仍必须：

```text
0.0
0.0
```

本任务不决定真实 fan test command 值。

未来真实值必须由用户明确确认。

不得默认：

```text
1.0
```

不得把 normalized command解释成 thrust percentage。

仍由 existing fan mapping / ramp / `flight_fan_max_pwm_us`限制真实输出。

---

# Deliverable 11 — Combined Ownership, Single-domain Actuation

不要新增：

```text
motor-only Flight authority
fan-only Flight authority
```

保持现有：

```text
motor + fan atomic ownership
```

未来 motor physical verification 定义为：

```text
motor:
    bounded feedback-relative command

fan:
    explicit STOP
```

未来 fan physical verification定义为：

```text
motor:
    feedback-relative HOLD

fan:
    explicitly configured bounded command
```

即：

```text
combined ownership
+
single-domain non-stop actuation
```

不要为了测试方便重写 authority architecture。

---

# Deliverable 12 — Normal Command Preconditions

verification controller 返回 normal `FlightCommand` 前至少要求：

```text
SystemState.command_authority == FLIGHT_CONTROL
flight_control_active == True
actuation_allowed == True
required_inputs_fresh == True
```

并要求：

```text
IMU valid/fresh
all required motors valid/fresh/healthy
```

否则：

```python
FlightCommand.safe_stop()
```

controller 不负责：

- prepare；
- reserve；
- owner commit；
- authority grant；
- E-STOP reset；
- ERROR recovery；
- enable motor；
- enable fan；
- zero。

---

# Deliverable 13 — Verification Controller Enable Gate

增加明确 verification enable 配置，例如：

```text
verification_controller_enabled
```

默认：

```text
false
```

即使 controller factory 被错误选中，只要 verification enable=false：

```text
return FlightCommand.safe_stop()
```

不得自动产生 hardware test command。

---

# Deliverable 14 — Hardware Test Config

增加独立 verification config，或在现有 Flight config 中增加清晰的 verification section。

至少表达：

```text
verification_controller_enabled
test_motor_name
motor_test_offset_rad
fan_left_test_command
fan_right_test_command
```

默认必须达到：

```text
verification_controller_enabled = false
motor movement = disabled
fan left = 0.0
fan right = 0.0
```

如果 motor offset 未明确配置成可执行值：

```text
motor normal verification command must not be generated
```

不要使用一个看似安全但未经验证的默认非零 offset。

---

# Deliverable 15 — Configuration Validation

必须 reject：

- NaN；
- Inf；
- invalid logical motor name；
- fan command < 0；
- fan command > 1；
- 非法 motor offset；
- verification enabled 但必要参数未提供。

配置错误：

```text
fail closed
```

不要 silent clamp hardware test parameters。

---

# Deliverable 16 — Simple Controller State Only

不要为了 hardware verification controller 增加复杂状态机。

最多保持类似：

```text
WAITING
BASELINE_CAPTURED
```

或等价最小内部状态。

不要新增：

- verification authority state；
- verification ownership state；
-自动 test sequence；
- timing-based multi-step motor test；
- automatic return trajectory；
- automatic motor cycling。

真实测试步骤由用户逐条执行和观察，不由 controller自动编排。

---

# Deliverable 17 — Software Unit Tests

使用 fake FlightState。

至少覆盖：

- reset；
- verification disabled -> safe-stop；
- no authority -> safe-stop；
- actuation not allowed -> safe-stop；
- required inputs stale -> safe-stop；
- IMU stale/invalid -> safe-stop；
- motor stale -> safe-stop；
- motor unhealthy -> safe-stop；
- incomplete motor set -> safe-stop；
- invalid test motor -> fail-closed；
- missing motor offset -> safe-stop；
- baseline capture；
- selected motor = baseline + fake offset；
- other motors = baseline hold；
- complete motor frame；
- fan default stop；
- fake configured fan command；
- invalid fan command reject；
- no cumulative motor drift；
- reset clears baseline；
- authority generation change clears baseline；
- old baseline never reused；
- output remains immutable valid FlightCommand。

---

# Deliverable 18 — Pure Algorithm Import Guard

增加或扩展 tests，确保 verification controller 不 import：

```text
rclpy
sensor_msgs
std_msgs
windarmor_interfaces
socket
serial
gpiozero
lgpio
CyberGearDriver
MotorManager
FanControlCore
```

它必须继续是纯算法模块。

---

# Deliverable 19 — No Hardware Execution in Tests

所有 Task 6.2 tests：

- pure Python；
- fake FlightState；
- fake motor states；
- no hardware node；
- no SocketCAN；
- no serial；
- no GPIO；
- no PWM；
- no `/dev/*`。

不得为了验证 controller 命令而启动真实 actuator adapter。

---

# Deliverable 20 — Update Hardware Verification Plan

更新：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

不要再继续围绕“staged reserve pause”设计新的 production feature。

将后续真实验证收敛成四个 Gate：

```text
Gate A
Physical + Powered Read-only

Gate B
Bounded Actuator Verification

Gate C
Fail-closed Verification

Gate D
Legacy + Final RC Regression
```

原 Stage 0–9 内容如仍有价值可以保留为详细 checklist，
但执行入口应以 Gate A–D 为主，减少过度拆分。

---

# Deliverable 21 — Gate A Plan

定义：

```text
Gate A — Physical + Powered Read-only
```

只规划，不执行。

至少分：

## A0 — Power-off physical inspection

检查：

- CAN wiring；
- motor mapping；
- mechanical clearance；
- IMU direction；
- GPIO12 / GPIO13；
- fan left/right；
- physical emergency power cut。

## A1 — Sensor / IMU observation

根据实际硬件供电关系，
只开启必要系统。

## A2 — Motor passive observation

必须明确告诉用户：

```text
这一子阶段需要给 CyberGear motor bus 通电
```

但 fan/ESC 默认仍保持断电。

使用：

```text
windarmor_observation_only.launch.py
```

确认：

- no actuator initialization；
- no motor movement；
- passive 0x02 feedback 是否真实存在。

如果没有 passive feedback：

```text
STOP
record protocol limitation
```

不得临时改用 normal motor initialization继续。

## A3 — Fan

第一次 read-only Gate 中：

```text
fan/ESC remain unpowered
```

因为当前没有真实 fan hardware feedback。

---

# Deliverable 22 — Gate B Plan

定义：

```text
Gate B — Bounded Actuator Verification
```

只规划，不执行。

执行顺序建议：

### B1 — Motor bounded verification

明确通知用户：

```text
CyberGear motors need power
fan/ESC should remain unpowered if electrical architecture permits
```

如果 Flight ownership要求 fan controller真实存在而必须给 fan controller供电，
必须在执行前明确说明，不能假设。

使用 verification controller：

```text
fan command = STOP
selected motor = baseline + user-approved offset
other motors = baseline hold
```

### B2 — Fan bounded verification

需要单独授权：

```text
fan/ESC power ON
```

motor：

```text
feedback-relative hold
```

fan：

```text
user-approved bounded normalized command
```

不要默认沿用 B1 的授权。

---

# Deliverable 23 — Gate C Plan

定义：

```text
Gate C — Fail-closed Verification
```

只规划。

包含：

- `FlightCommand.safe_stop()`；
- command timeout；
- Runtime stop/restart；
- stale authority rejection；
- owner loss；
- E-STOP interaction。

不要为每个测试提前创建新的软件 Task。

如果真实测试暴露 bug：

```text
STOP hardware validation
create targeted fix task
```

---

# Deliverable 24 — Gate D Plan

定义：

```text
Gate D — Legacy + Final RC Regression
```

包含：

- motor MANUAL；
- motor LEGACY_AUTO；
- HOME；
- fan MANUAL；
- fan LEGACY_AUTO；
- E-STOP；
- shutdown；
- restart；
- explicit legacy reclaim；
- final normal regression。

Gate D通过后才进入 v0.4.0 RC / release收口。

---

# Deliverable 25 — Detailed User Manual Test Steps

这是后续 hardware execution 的强制要求。

`V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 中，每个真实 Gate 必须明确：

1. 哪些设备需要通电；
2. 哪些设备必须保持断电；
3. 上电前检查；
4. Terminal 1 执行什么；
5. Terminal 2 执行什么；
6. Terminal 3 执行什么（如需要）；
7. 每条命令完整内容；
8. 每条命令执行后的预期 ROS 输出；
9. 预期物理行为；
10. 明确不应该出现的物理行为；
11. PASS 判据；
12. FAIL 判据；
13. 立即停止条件；
14. 安全退出命令；
15. 安全断电顺序。

不能只写：

```text
启动节点并观察
```

---

# Deliverable 26 — Commands Must Match Repository

计划中的：

```text
ros2 launch
ros2 topic echo
ros2 topic hz
ros2 service call
ros2 param
```

必须根据当前真实：

- executable；
- launch；
- topic；
- service；
- interface type；
- parameter name；

逐一核对。

不得凭记忆编造命令。

如果某个真实 test value 尚未由用户决定：

```text
TO BE SET BEFORE EXECUTION
```

但 command结构本身应尽量写完整。

---

# Deliverable 27 — Explicit Power Notices

未来所有人工 hardware step 必须在对应步骤最前面写：

```text
【本阶段需要通电】
...
```

以及：

```text
【本阶段必须保持断电】
...
```

如果 motor和fan需要不同供电阶段，必须明确区分。

默认前提仍是：

```text
motors OFF
fans/ESC OFF
```

不能因为之前某个 Gate曾上电，就假设后续仍然通电。

---

# Deliverable 28 — User-facing Manual Test Format

后续实际需要用户操作时必须采用类似格式：

```text
【本阶段硬件状态】

需要通电：
- ...

保持断电：
- ...

【上电前检查】

1. ...
2. ...

【Terminal 1】

执行：

<exact command>

预期：

...

【Terminal 2】

执行：

<exact command>

预期：

...

【物理预期】

应该发生：
- ...

绝对不应该发生：
- ...

【立即停止条件】

- ...
- ...

【PASS】

...

【FAIL】

...

【安全退出】

1. ...
2. ...
3. ...
```

不要让用户自行从长篇 architecture文档推导操作步骤。

---

# Deliverable 29 — README / API

`FLIGHT_CONTROL_API.md` 原则上不需要修改算法 contract。

可以增加一句：

> `bounded_verification_controller` 仅用于项目硬件验证，不是实际飞控算法模板。

README只需在 hardware verification section 保持链接清晰。

不要继续扩大主 README。

---

# Deliverable 30 — Preserve Architecture

本任务禁止重新设计：

- AuthorityStateMachine；
- ownership protocol；
- authority epoch；
- generation；
- FlightCommandEnvelope；
- MotorManager；
- fan ownership；
- command lease；
- rollback；
- observation-only architecture。

只有发现明确软件 bug 才停止并报告。

不要因为“理论上可以更安全”继续增加新机制。

---

# Deliverable 31 — Software Verification

仅运行无硬件验证。

至少：

```bash
source /opt/ros/jazzy/setup.bash

colcon build --symlink-install

source install/setup.bash

python3 -m pytest \
  src/windarmor_flight_control/test \
  -q

colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_interfaces \
  windarmor_flight_control \
  windarmor_bringup

colcon test-result --verbose

./scripts/ci_software.sh
```

如果仓库当前推荐命令有变化，以当前统一 CI script 为准。

不得访问真实：

```text
/dev/*
CAN
CyberGear
IMU serial
GPIO
PWM
ESC
fan
```

---

# Expected Result

Task 6.2 完成后：

1. 有专用 bounded hardware verification controller；
2. controller 使用 feedback-relative motor baseline；
3. 不把 0 rad 当真实机械中位；
4. motor offset不累积；
5. 未测试 motor明确 hold baseline；
6. fan默认 STOP；
7. verification默认 disabled；
8. 未指定真实 motor offset时 fail-closed；
9. 不新增 motor-only/fan-only authority；
10. 不新增 staged ownership mode；
11. 不新增 reservation keepalive；
12. Flight safety architecture冻结；
13. hardware plan收敛为 Gate A–D；
14. future人工测试有完整命令/预期结果/停止条件；
15. 所有真实 actuator动作仍需用户逐项授权；
16. 本任务未执行任何真实硬件；
17. software CI全部通过；
18. 下一步不再创建预防性软件任务；
19. 默认进入 Gate A hardware verification准备；
20. 只有真实硬件验证暴露缺陷时再创建针对性 fix Task。

---

# Out of Scope

明确不做：

- 旧版 Task 6.2 staged ownership；
- reservation keepalive；
- verification authority states；
- real hardware test；
- motor power-on；
- fan/ESC power-on；
- motor movement；
- fan spin；
- actual Flight takeover；
- hardware parameter tuning；
- PID / flight algorithm；
- package version bump；
- v0.4.0 RC；
- release；
- GitHub Release；
- commit；
- push；
- tag。

---

# Stop Conditions

出现以下任一情况必须停止并报告：

- 必须修改 authority architecture才能做 bounded test；
- 必须真实给 hardware通电才能完成 controller；
- 必须编造 motor safe offset；
- 必须绕过 MotorManager；
- 必须绕过 FanCommandManager；
- 必须关闭 safety timeout；
- 必须伪造 feedback；
- 必须自动恢复 legacy owner；
- 任务范围再次扩展成新的 verification framework；
- 发现当前软件存在会阻止 Gate A/B 的明确 safety bug。

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## Scope

- 修改文件；
- verification controller；
- config；
- hardware plan；
- tests。

## Verification Controller

说明：

- controller 文件/factory；
- baseline capture；
- selected motor；
- target生成规则；
- non-test motor hold规则；
- fan默认值；
- verification enable gate；
- safe-stop conditions；
- authority session变化行为；
- 是否存在 cumulative drift（预期：否）。

## Hardware Readiness

明确：

```text
Gate A
Gate B
Gate C
Gate D
```

分别处于什么状态。

说明：

- 哪些 Gate需要 motor通电；
- 哪些需要 fan/ESC通电；
- 哪些参数仍需用户执行前决定；
- hardware commands是否已经与当前 repo核对。

## Safety Boundary

明确：

- 本任务未给 CyberGear通电；
- 本任务未给 fan/ESC通电；
- 未执行真实 motor/fan；
- 未执行 owner takeover；
- authority/ownership architecture未改；
- `flight_takeover_enabled=false`默认未改；
- `motor_feedback_timeout_sec=0.0`未改；
- ERROR/E-STOP/reconnect semantics未改。

## Tests

- exact commands；
- verification controller tests；
- pytest count；
- colcon result；
- CI result；
- warnings/skipped。

## Next Step

如果没有 software blocker：

```text
NEXT:
Gate A — Physical + Powered Read-only
```

但：

```text
NOT AUTHORIZED / NOT EXECUTED
```

在真正执行 Gate A 前，必须先向用户提供：

- 哪些设备需要通电；
- 哪些设备保持断电；
- 完整逐步命令；
- 每步预期结果；
- PASS/FAIL；
- 立即停止条件；
- 安全退出步骤。

然后等待用户明确授权。

## Git 状态（反馈生成时）

记录：

- HEAD；
- branch；
- working tree；
- implementation/verification 阶段是否 commit；
- push/tag；
- remote是否核验；
- v0.3.0 / v0.3.1 / v0.3.2 stable tags是否保持。

本任务默认不授权 commit / push / tag。

工程文档继续使用工具无关措辞。