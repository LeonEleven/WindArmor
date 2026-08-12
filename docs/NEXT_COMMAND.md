# NEXT_COMMAND

## Task

v0.4.0 Task 6 — Hardware Verification Planning Only

## Objective

在 v0.4.0 软件主线、仓库清理和算法成员交接已经完成的基础上，设计一份**分阶段、可独立授权、可中途停止**的真实硬件验证方案。

本任务只负责：

1. 设计 v0.4.0 的真实硬件验证 protocol；
2. 明确每个阶段的前置条件、允许动作、禁止动作、预期状态、观测项、停止条件和回滚方式；
3. 明确哪些阶段需要用户单独授权；
4. 明确 owner handoff、Flight command、timeout、Runtime crash、E-STOP/ERROR 等真实验证顺序；
5. 设计最终 RC 前 legacy regression；
6. 不执行任何真实硬件操作；
7. 不修改控制逻辑；
8. 不进入 v0.4.0 RC / release。

本任务的核心产物是一份长期可执行的验证计划，而不是一次性聊天或临时命令记录。

---

## Baseline

当前开发基线：

```text
413dbc1
整理仓库文档并完善飞控算法交接
```

当前状态：

- v0.3.2 仍为正式稳定发布基线；
- 当前开发目标为 v0.4.0；
- Flight API / Structured State / DRY_RUN / authoritative safety readback / authority / owner handoff / actuator adapter / rollback & lease hardening / repository cleanup / algorithm handoff 均已完成软件阶段；
- `flight_takeover_enabled=false` 仍为默认；
- `motor_feedback_timeout_sec=0.0` 仍为默认；
- 尚未执行 v0.4.0 Flight takeover 的真实硬件验证。

执行前必须阅读：

1. `AGENTS.md`
2. `README.md`
3. `docs/HARDWARE_REFERENCE.md`
4. `docs/FLIGHT_CONTROL_ARCHITECTURE.md`
5. `docs/FLIGHT_CONTROL_API.md`
6. `docs/LATEST_FEEDBACK.md`
7. `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md`
8. 当前 `docs/NEXT_COMMAND.md`

还必须检查当前 motor/fan/Flight config、launch、ROS topics/services、owner handoff services、authority status、Flight command envelope topic 与 E-STOP/ERROR recovery path。

如果仓库状态与以上描述冲突：不覆盖用户修改，不 reset/checkout/clean，先报告差异，以 `AGENTS.md` 为最高安全与 Git 规则。

---

## Safety and Git Constraints

本任务**绝对不授权任何真实硬件动作**。

禁止：

- 给 CyberGear 执行动作验证；
- 启动真实 motor control；
- 启动真实 fan PWM；
- 实际发 Flight takeover；
- 实际 reserve/commit owner；
- 实际发送可执行 FlightCommandEnvelope；
- 实际触发 motor/fan motion；
- 实际做 Runtime crash 后硬件停止测试；
- 实际触发 E-STOP/fault；
- 实际调用 reset E-STOP / ERROR；
- set-zero / enable；
- 配置 SocketCAN；
- 访问 `/dev/*`；
- `sudo` 硬件操作；
- commit / push / tag；
- 创建、移动、删除或重建稳定 tag。

允许：

- 只读代码/文档/config；
- 仓库搜索；
- fake/mock/software 验证；
- 编写 checklist/protocol；
- 无硬件核对 ROS CLI/interface 名称。

---

# Deliverable 1 — Create `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`

新增长期文档：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

文档开头必须明确：

```text
Status: PLANNED / NOT YET EXECUTED
```

并注明：

- 当前 stable release 仍是 v0.3.2；
- v0.4.0 Flight takeover 尚未经过真实硬件验证；
- 每个带电阶段必须得到用户单独授权；
- 某阶段通过不自动授权下一阶段；
- 任一阶段失败后默认停止，不自动继续。

---

# Deliverable 2 — Verification Philosophy

明确：

```text
physical confirmation
-> read-only observation
-> ownership reservation without motion
-> single-subsystem takeover
-> bounded actuator command
-> combined takeover
-> timeout/fault injection
-> legacy regression
```

每个阶段都必须有：

- prerequisites；
- allowed operations；
- forbidden operations；
- expected ROS state；
- expected physical behavior；
- observations；
- abort conditions；
- rollback；
- pass/fail；
- next-stage gate。

Stage N 通过 != 自动允许 Stage N+1。

---

# Deliverable 3 — Stage 0: Physical Preflight

只做断电/不上电状态的物理核对。

至少确认：

- Raspberry Pi 5 / CAN HAT；
- CAN bus wiring；
- motor CAN ID ↔ physical joint；
- motor mechanical direction；
- IMU X+/Y+/Z+；
- left fan GPIO12 / pin32；
- right fan GPIO13 / pin33；
- GND；
- fan physical left/right；
- ESC power wiring；
- 可物理断电方式；
- 急停方式；
- 机械活动范围；
- current motor soft limits 是否与机构范围一致。

GPIO13 仍按“需首次真实确认”处理，不得写成已验证。

记录表必须支持：

```text
PASS / FAIL / NOT VERIFIED
```

---

# Deliverable 4 — Stage 1: Read-only State Verification

`flight_takeover_enabled=false`，不允许 actuator command。

验证：

```text
hardware
-> existing subsystem feedback
-> structured ROS state
-> FlightState
-> DRY_RUN preview
```

至少包括：

### IMU
- `/imu/data_raw`
- relative roll/pitch
- zero_generation
- connected status
- physical axis match
- stale/invalid behavior

### Motor
- `/motors/feedback`
- 4 logical motors
- logical name ↔ CAN ID
- position/velocity/torque/temp
- no fake `current_a`
- health/fault/temp
- safety readback

### Fan
- `/fans/status_pwm`
- `/fans/enabled`
- `/fans/control_state`
- `/fans/safety_state`
- no RPM/thrust assumption

### Flight Runtime
- DRY_RUN
- authority NONE
- actuation_allowed false
- preview only
- no executable actuator path

---

# Deliverable 5 — Stage 2: Ownership Reserve / Revoke Without Motion

只验证：

```text
READY_TO_TAKEOVER
-> reserve
-> revoke
```

不进入可执行 normal Flight command。

要求：

- `flight_takeover_enabled=true` 仅在该阶段获得单独授权后开启；
- 使用明确 safe/test controller；
- reserve 后 motor/fan 进入 safe hold/stop；
- legacy MANUAL/AUTO 被 block；
- 不产生新 motor target；
- 不产生新 active fan PWM；
- revoke 后 owner -> NONE；
- 不自动恢复 legacy owner；
- operator 显式 reclaim。

验证 token、authority_epoch/generation、owner readback、partial reserve rollback、handoff lease timeout、revoke unavailable 的 fail-closed。

---

# Deliverable 6 — Stage 3: Motor-only Flight Takeover

这是第一次可能允许真实 motor movement，必须单独显式授权。

目标：

- fan 保持 safe stop；
- 只验证 motor ownership + bounded Flight position command；
- 先单 motor / 单轴；
- 再按需要扩展完整 4-motor frame。

前置：

- Stage 0–2 通过；
- motor temperature normal；
- no fault；
- global E-STOP clear；
- soft limits confirmed；
- mechanical clearance；
- physical kill available；
- explicit motor-motion authorization。

命令幅度必须非常小且靠近 current/last successful position。

**不要凭空发明最大偏移数值。**

如果仓库没有可安全引用的阈值，计划写：

```text
TO BE SET BEFORE EXECUTION
```

不得为测试修改 soft limit、speed limit 或 `motor_feedback_timeout_sec`。

---

# Deliverable 7 — Stage 4: Fan-only Flight Takeover

motor 保持不动，只验证 fan ownership + normalized command mapping。

要求：

- 从 stop / very-low normalized command 开始；
- 不直接跳 1.0；
- 不超过 current `flight_fan_max_pwm_us`；
- 不把 normalized value 当 thrust；
- 验证 left/right mapping、起转、ramp、timeout、safe-stop、revoke、E-STOP override、Runtime loss safe-stop。

不发明 RPM/thrust 判定标准。

---

# Deliverable 8 — Stage 5: Combined Ownership, Minimal Command

目标验证：

```text
motor reserve/commit
fan reserve/commit
atomic Runtime commit
post-grant new-state barrier
first valid envelope
```

只使用：

- motor 最小安全幅度；
- fan 最低实际可验证 command；
- 简单非飞行、非激烈闭环 test controller。

重点是 distributed ownership + atomic commit，不是飞控算法性能。

必须记录：

- authority_epoch；
- generation；
- cutoff state_sequence；
- first command state_sequence；
- owner tokens；
- first accepted command sequence。


---

# Deliverable 9 — Stage 6: Safe-stop / Timeout / Runtime Loss

至少设计：

## Algorithm safe-stop

ACTIVE 时：

```text
FlightCommand.safe_stop()
```

预期：

- motor halt；
- fan stop；
- Runtime INHIBITED；
- owner NONE；
- no automatic legacy recovery。

## Command heartbeat timeout

验证 motor/fan Flight command timeout、owner release、Runtime inhibit。

## Handoff lease timeout

reserve/commit 后第一条 command 前故意延迟，确认 owner fail-closed。

## Runtime process stop/crash

预期：

- no new command；
- owner local lease timeout；
- motor halt；
- fan stop；
- new Runtime 不恢复 old authority；
- old epoch message reject。

## Owner process loss

任一 owner 丢失：

- Runtime inhibit；
- remaining owner best-effort revoke；
- no auto fallback。

所有 crash/kill 操作在未来执行时都必须单独授权。

---

# Deliverable 10 — Stage 7: E-STOP / ERROR Interaction

这是高风险阶段，必须单独授权。

至少规划：

## E-STOP during Flight

预期：

- lower-level E-STOP 优先；
- Flight authority失效；
- motor/fan safe state；
- Runtime INHIBITED；
- E-STOP clear 不自动恢复 Flight；
- existing explicit recovery + new prepare。

## Motor ERROR during Flight

优先使用安全、已有、可控的软件模拟/受控 fault。

若必须真实 hardware fault 才能验证，标记：

```text
OPTIONAL / HIGH RISK / NOT REQUIRED FOR NORMAL RC
```

不得规划：

- 故意 critical overtemperature；
- 故意堵转；
- 人为危险过流；
- 带电拔插高功率线；
- destructive fault。

预期：

- ERROR latch；
- Flight 不能 clear ERROR；
- reconnect 不恢复 Flight；
- old target 不重发。

---

# Deliverable 11 — Stage 8: Legacy Regression After Flight

验证：

- motor MANUAL；
- motor legacy AUTO；
- HOME；
- fan MANUAL；
- fan legacy AUTO；
- E-STOP；
- reset flow；
- normal shutdown；
- transport reconnect；
- v0.3.2 normal behavior。

特别确认：

- Flight release 后不会自动 legacy；
- operator 显式 reclaim 后 legacy 才恢复；
- old Flight epoch/generation command 不再有效。

---

# Deliverable 12 — Stage 9: Final v0.4.0 RC Regression

最终候选验证摘要，不在 Task 6 执行。

至少包含：

- boot；
- IMU；
- motor feedback；
- fan status；
- DRY_RUN；
- explicit Flight takeover；
- minimal normal command；
- safe-stop；
- explicit legacy reclaim；
- E-STOP；
- shutdown；
- restart；
- no stale authority replay；
- no old target replay。

避免与 Stage 0–8 逐项重复，作为最终整机正常功能 + 核心安全契约摘要。

---

# Deliverable 13 — Per-stage Template

每个 Stage 统一使用：

```text
Stage name
Risk level
Hardware scope
Prerequisites
Required explicit user authorization
Allowed operations
Forbidden operations
Exact launch / ROS commands
Expected ROS state
Expected physical behavior
Observations to record
Abort / stop conditions
Rollback / safe-state procedure
Pass criteria
Fail criteria
Next-stage gate
```

如果某项仍需执行前确认：

```text
TO BE CONFIRMED BEFORE EXECUTION
```

不要编造不存在的 topic/service/launch 名称。

所有命令必须从当前仓库真实接口核对。

---

# Deliverable 14 — Authorization Matrix

增加表格，至少区分：

```text
Stage 0 physical-only
Stage 1 powered read-only
Stage 2 owner handoff, no motion
Stage 3 motor motion
Stage 4 fan spin
Stage 5 combined actuator
Stage 6 timeout/crash
Stage 7 E-STOP/fault
Stage 8 legacy regression
Stage 9 final RC
```

每阶段写：

- 是否需要真实硬件；
- 是否带电；
- 是否可能运动；
- 是否需要用户单独授权；
- 是否可 software-only 替代。

所有会导致真实 actuator movement、owner takeover、E-STOP/fault injection 的阶段必须单独授权。

---

# Deliverable 15 — Hardware Scope Matrix

按域拆分：

```text
IMU
Motor/CAN
Fan/GPIO/PWM
Flight Runtime
Ownership protocol
E-STOP
Power/mechanical environment
```

标明每个 Stage 涉及哪些域。

---

# Deliverable 16 — Evidence Template

设计统一记录：

```text
Date/time
Git HEAD
Config snapshot
Stage
Hardware powered?
Takeover enabled?
Authority epoch
Generation
Owner states
ControllerState
Global E-STOP
Motor health
Fan state
Command sequence
Expected
Observed
Pass/Fail
Operator notes
Stop reason
```

未来实际执行时填写，不把聊天记录当正式验证证据。

---

# Deliverable 17 — Config Snapshot Requirements

硬件执行前必须记录关键 config。

### Motor
- `motor_ids`
- `motor_names`
- `motor_signs`
- soft limits
- manual/auto/flight motion speeds
- `motor_feedback_timeout_sec`
- handoff/command timeout

### Fan
- pins
- stop/start/max
- flight max
- ramp rates
- handoff/command timeout

### Flight
- control rate
- freshness
- `flight_takeover_enabled`
- handoff timeout
- controller factory

Task 6 不修改这些值。

---

# Deliverable 18 — Pre-execution Safety Checklist

任何带电 Stage 前统一确认：

- correct Git HEAD；
- working tree status；
- correct config；
- expected launch；
- physical clearance；
- no person in motion envelope；
- kill power available；
- E-STOP reachable；
- fan guarded / clear；
- motor load mechanically safe；
- terminal/log capture；
- no stale ROS graph/process；
- previous Flight authority cleared；
- no old Runtime process；
- user explicitly authorized this Stage。

---

# Deliverable 19 — Global Stop Conditions

至少：

- unexpected motor direction；
- unexpected fan side/direction；
- command target mismatch；
- motor fault bit；
- worsening temperature warning；
- critical temperature；
- CAN/transport instability；
- IMU axis mismatch；
- unknown/incorrect owner state；
- E-STOP unknown when clear required；
- unexpected authority token；
- command sequence anomaly；
- unexpected ACTIVE；
- stale readback；
- lease timeout；
- unexpected actuator movement；
- mechanical interference；
- unusual sound/vibration/smell/heat；
- user requests stop。

发生任意条件：

```text
STOP current stage
do not auto-continue
record evidence
return to safe state
```

---

# Deliverable 20 — Recovery Rules

继续遵守：

- ERROR 不自动恢复；
- E-STOP clear 不恢复 Flight；
- transport reconnect 不恢复 Flight；
- Runtime restart 不恢复 authority；
- old epoch/generation 不恢复；
- owner timeout 后不自动 legacy；
- Flight safe-stop 后不自动 legacy；
- next attempt 需要 explicit prepare/handoff；
- legacy reclaim 需要显式 operator action。

不要设计自动恢复以方便测试。

---

# Deliverable 21 — No Destructive Testing

常规 v0.4.0 验证禁止：

- 故意堵转 motor；
- 故意超过 soft limit；
- 故意升温到 critical；
- 故意过流；
- 故意破坏 CAN bus；
- 带电拔插 high-current line；
- 触碰旋转 fan；
- 超出 current fan Flight max；
- 修改 safety threshold 制造故障；
- 绕过 E-STOP/watchdog；
- 直接写 CyberGear SDO 代替正式 path。

---

# Deliverable 22 — Software Gate Before Hardware Session

硬件 session 前执行：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

并记录当前 Git HEAD。

如果 hardware session 使用的 commit 与最近 green CI commit 不同，必须重新判断是否重跑。

---

# Deliverable 23 — Plan Interface Audit

本任务完成前以只读/无硬件方式核对计划中的：

- topic names；
- service names；
- launch names；
- package names；
- parameter names；
- status enums；
- owner states；
- authority states。

可使用：

```text
rg
git grep
ROS interface introspection from built workspace
```

但不启动真实硬件 node。

所有命令示例必须与当前代码一致。

---

# Deliverable 24 — README / AGENTS Minimal Update Only If Needed

原则上本任务只新增 hardware verification plan。

README 可增加一个简洁入口链接。

AGENTS 仅在确有必要时补充：

> 所有带电 Stage 均需逐阶段独立授权。

不要复制完整 checklist 到 README/AGENTS。

---

# Deliverable 25 — Do Not Modify Control Logic

禁止修改：

- motor control；
- motor ownership；
- fan control；
- fan ownership；
- Flight Runtime；
- authority；
- envelope；
- safety monitor；
- timeout implementation；
- launch default behavior；
- config values。

若制定 plan 时发现新的 software blocker：

- 不在 Task 6 修；
- 写入 `LATEST_FEEDBACK.md`；
- 建议新的 Task 6.x；
- 停止进入 hardware execution。

---

# Deliverable 26 — Software Verification

至少运行：

```bash
git diff --check
```

以及：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

不得访问真实硬件。

---

# Expected Result

Task 6 完成后：

1. 存在 `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
2. 文档状态明确为未执行；
3. 验证被拆成 Stage 0–9；
4. 每个 Stage 有独立授权门槛；
5. 所有会产生 motion/takeover/fault 的阶段默认禁止；
6. Stage 0 先确认机械/接线/IMU frame；
7. Stage 1 先只读状态链；
8. Stage 2 先 owner reserve/revoke；
9. motor/fan takeover 分开验证；
10. combined handoff 在单 subsystem 之后；
11. timeout/crash/E-STOP 在基础 motion 成功后；
12. legacy regression 在 Flight 测试后；
13. final RC regression 单独定义；
14. 无 destructive testing；
15. plan 中 interface 与当前仓库一致；
16. 未执行任何真实硬件操作；
17. 未改变 control/safety/config semantics；
18. 下一步只能由用户逐阶段选择并授权 Stage 0/1 或后续阶段。

---

# Out of Scope

明确不做：

- Stage 0–9 的真实执行；
- CyberGear motion；
- fan spin；
- owner takeover；
- E-STOP/fault injection；
- hardware timing measurement；
- config tuning；
- Flight algorithm tuning；
- IMU calibration；
- thrust/RPM characterization；
- current measurement；
- package version bump；
- v0.4.0 RC tag；
- release；
- GitHub Release；
- commit；
- push；
- tag。

---

# Stop Conditions

若出现：

- 无法从当前仓库确认 interface 名称；
- hardware mapping 与 `HARDWARE_REFERENCE.md` 冲突；
- 发现新的 software safety blocker；
- 某 Stage 必须绕过 existing safety path；
- 必须改 config default 才能制定计划；
- 必须做真实硬件动作才能确认计划；
- 计划开始包含 destructive testing；
- 一次授权被解释为后续阶段授权；

必须停止并报告。

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## Scope
- 新增/修改 docs；
- 是否修改 README/AGENTS；
- source/config/control logic 是否未修改。

## Verification Plan
- Stage 0–9 摘要；
- authorization matrix；
- hardware scope matrix；
- global stop conditions；
- evidence template；
- config snapshot；
- recovery rules。

## Interface Audit
- 核对的 topic/service/parameter/launch；
- 是否存在计划与实现不一致；
- 是否存在需要 Task 6.x 修复的软件 blocker。

## Safety Boundary
明确：
- 未执行真实硬件；
- 未开启 takeover；
- 未运行 motor/fan；
- 未调用 E-STOP/ERROR recovery；
- 未修改 config；
- `flight_takeover_enabled=false` 不变；
- `motor_feedback_timeout_sec=0.0` 不变；
- stable tags 不变。

## Tests
- `git diff --check`；
- `./scripts/ci_software.sh`；
- pass/fail；
- warnings/skipped；
- 是否有进入 Stage 0/1 前 blocker。

## Git 状态（反馈生成时）
- HEAD；
- branch；
- working tree；
- implementation/verification 阶段是否 commit；
- push/tag；
- remote 是否核验；
- v0.3.0 / v0.3.1 / v0.3.2 stable tags 是否保持。

本任务默认不授权 commit / push / tag。

工程文档继续使用工具无关措辞。
