# NEXT_COMMAND

## Task

v0.4.0 Task 6.2.6 — Flight Fan Safety State Contract Alignment

## Objective

修复 B1 bounded Flight takeover 第三次实机重试中发现的跨包 fan safety state contract 不一致。

真实硬件日志已经确认：

```text
DRY_RUN
  ↓
ARMING
  ↓
READY_TO_TAKEOVER
preflight_ready=true
  ↓
ownership handoff starts
  ↓
fan safety observation:
control_state = FLIGHT_WAITING
  ↓
Flight Runtime rejects:
unknown fan control state
  ↓
INHIBITED
last_inhibit_reason = invalid fan safety observation
```

本次没有确认：

```text
authority_state = ACTIVE
command_authority = FLIGHT_CONTROL
actuation_allowed = true
```

也没有确认：

```text
left_pitch ≈ +0.05 rad
```

因此 B1 attempt #3 状态：

```text
prepare accepted: YES
preflight READY: YES
ownership handoff started: YES

ACTIVE: NO
bounded motor movement: NO EVIDENCE

failure:
Flight SafetyReadbackAdapter does not recognize
legitimate fan FLIGHT_WAITING state.
```

本任务只修复：

> fan controller 已正式定义的 FLIGHT_WAITING / FLIGHT_ACTIVE 状态，与 Flight Runtime safety adapter 的允许状态集合不一致。

---

# Baseline

当前 Git 基线：

```text
5fa3810513dab65ff885954bf5af749b756bf0f8
修复风扇急停回滚状态保持
```

当前验证状态：

```text
Task 6.2.2 motor feedback:
SW + HW PASS

Task 6.2.3 cold-start hold:
SW + HW PASS

Task 6.2.4 fan startup ordering:
SW PASS + real startup observation PASS

Task 6.2.5 fan E-STOP preservation:
SOFTWARE PASS

B1 attempt #3:
PREPARE ACCEPTED
PREFLIGHT READY
HANDOFF STARTED
NO ACTIVE
NO CONFIRMED ACTUATION

Blocker:
fan FLIGHT_WAITING rejected as unknown state
```

---

# Hardware Boundary

本任务 SOFTWARE-ONLY。

必须保持：

```text
CyberGear motor bus: OFF

left ESC power: OFF
right ESC power: OFF

GPIO12 -> left ESC:
DISCONNECTED

GPIO13 -> right ESC:
DISCONNECTED
```

不得：

- 打开真实 CAN；
- 给 CyberGear 上电；
- 给 ESC/fan 上电；
- 连接 GPIO/PWM 到 ESC；
- 启动 hardware launch；
- 调用真实 Flight prepare；
- 执行 Flight takeover；
- 执行 actuator command。

全部测试必须使用 pure/fake/mock/in-memory。

---

# Required Reading

执行前必须阅读：

```text
AGENTS.md
README.md

docs/HARDWARE_REFERENCE.md
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
docs/LATEST_FEEDBACK.md
docs/NEXT_COMMAND.md
```

重点检查：

```text
src/windarmor_fan_controller/
  windarmor_fan_controller/fan_control.py
  ownership related code
  tests

src/windarmor_flight_control/
  windarmor_flight_control/runtime/safety_adapter.py
  windarmor_flight_control/runtime/node.py
  windarmor_flight_control/core/preflight.py
  runtime / ownership integration tests

src/windarmor_interfaces/
  fan / ownership / safety messages
```

---

# Hardware Evidence To Preserve

B1 attempt #3 已观察到：

```text
authority_state:
DRY_RUN
→ ARMING
→ READY_TO_TAKEOVER
→ INHIBITED
```

其中：

```text
preflight_ready=true
```

后 Runtime 打印：

```text
rejected fan safety observation:
unknown fan control state
```

随后：

```text
DRY_RUN controller inhibited;
explicit reset-inhibit is required:
invalid fan safety observation
```

因此本任务不要重新怀疑：

```text
motor feedback
motor cold-start
fan startup ordering
preflight
global e-stop observation
```

除非 regression 证明真实根因另有其因。

---

# Confirm Root Cause Before Modification

先增加最小 regression。

审计当前：

```text
FanControlState
```

确认正式存在：

```text
FLIGHT_WAITING
FLIGHT_ACTIVE
```

然后审计：

```text
SafetyReadbackAdapter.update_fan(...)
```

确认当前合法状态集合遗漏这两个状态。

必须先构造：

```text
FanSafetyState:
  e_stop_latched=false
  control_state=FLIGHT_WAITING
  enabled_observed=true
  enabled=true
  manual_armed=false
  legacy_auto_requested=false
  legacy_auto_active=false
  passive_for_takeover=false
```

当前 baseline 应得到：

```text
REJECT
reason = unknown fan control state
```

再构造：

```text
control_state=FLIGHT_ACTIVE
```

当前 baseline 也应被错误拒绝。

先证明，再修改。

如果 regression 不能复现：

```text
STOP
```

报告真实根因，不要照任务描述盲改。

---

# Formal Fan State Contract

明确检查 fan controller 当前正式 public states。

至少应包括当前实现已有的：

```text
SAFE_STOP
MANUAL_DISARMED
MANUAL_WAITING_FOR_NEUTRAL
MANUAL_WAITING
MANUAL_ACTIVE
AUTO_WAITING
AUTO_ACTIVE
FLIGHT_WAITING
FLIGHT_ACTIVE
DISABLED
EMERGENCY_STOP
```

不要新增状态。

不要改名。

不要建立第二套 fan state enum。

---

# Required Fix

Flight safety adapter 必须正式接受：

```text
FLIGHT_WAITING
FLIGHT_ACTIVE
```

作为已知合法 fan control state。

但：

```text
known state
```

不等于：

```text
always safe
```

现有所有 cross-field invariant 检查继续执行。

不得只写：

```text
if state.startswith("FLIGHT_"):
    accept
```

使用明确、封闭的合法集合。

未知字符串仍必须拒绝。

---

# FLIGHT_WAITING Contract

合法：

```text
control_state = FLIGHT_WAITING
e_stop_latched = false
passive_for_takeover = false
```

该状态表示 fan ownership/handoff 已进入 Flight session，
但 executable Flight command 尚未建立。

不得把：

```text
FLIGHT_WAITING
```

解释为：

```text
passive_for_takeover=true
```

因为 reserve 之后已经不再是 legacy passive owner-ready 状态。

同时必须保持：

```text
manual_armed=false
legacy_auto_active=false
```

以及当前 fan core 的真实 ownership contract。

---

# FLIGHT_ACTIVE Contract

合法：

```text
control_state = FLIGHT_ACTIVE
e_stop_latched = false
passive_for_takeover = false
```

它表示 fan 已进入 committed/executable Flight control path。

Safety adapter 可以识别该状态，
但仍需验证：

```text
E-STOP consistency
manual/AUTO consistency
enabled truth
snapshot/readback consistency
```

不要因为 state=FLIGHT_ACTIVE 就跳过其他 safety validation。

---

# E-STOP Invariant

Task 6.2.5 的 invariant 保持：

```text
IF e_stop_latched=true
THEN control_state MUST be EMERGENCY_STOP
```

因此以下仍必须拒绝：

```text
e_stop_latched=true
control_state=FLIGHT_WAITING
```

以及：

```text
e_stop_latched=true
control_state=FLIGHT_ACTIVE
```

不能因为本任务加入两个合法 state 就放宽 E-STOP 一致性。

---

# Passive-for-takeover Invariant

保持当前规则：

只有正式 legacy-safe passive states 才允许：

```text
passive_for_takeover=true
```

例如当前 contract允许的：

```text
SAFE_STOP
MANUAL_DISARMED
```

不要把：

```text
FLIGHT_WAITING
FLIGHT_ACTIVE
```

加入 passive state 集合。

以下必须拒绝：

```text
FLIGHT_WAITING + passive_for_takeover=true
FLIGHT_ACTIVE  + passive_for_takeover=true
```

---

# Manual / AUTO Conflict

构造 regression 确认：

```text
FLIGHT_WAITING
manual_armed=true
```

按当前 contract 必须被拒绝或被当前既有一致性规则拦截。

同理：

```text
FLIGHT_ACTIVE
legacy_auto_active=true
```

不得因为新增 known-state support 而被接受。

不要新造规则；
优先复用当前 adapter 的 cross-field consistency。

---

# Enabled Contract

保持当前 truthful enabled contract。

例如：

```text
FLIGHT_ACTIVE
enabled_observed=true
enabled=true
```

可以继续评估。

但：

```text
FLIGHT_ACTIVE
enabled_observed=false
```

或当前定义下不可信的 enabled 状态，
不得被本任务绕过。

不要伪造：

```text
enabled=true
```

---

# Unknown State Must Still Fail Closed

增加明确 regression：

```text
control_state = "FLIGHT_SUPER_MODE"
```

或者其他不存在字符串。

必须：

```text
REJECT
reason = unknown fan control state
```

不要使用宽松 prefix / suffix 匹配。

---

# Required Regression — Exact B1 Failure Shape

建立 fake integration sequence：

```text
1. fan starts SAFE_STOP/passive

2. Flight prepare

3. preflight READY

4. fan reserve succeeds

5. fan core transitions:
   SAFE_STOP -> FLIGHT_WAITING

6. fan safety snapshot publishes:
   control_state=FLIGHT_WAITING
   e_stop_latched=false
   passive_for_takeover=false

7. Flight safety adapter consumes snapshot
```

修改前：

```text
REJECT unknown fan control state
```

修改后：

```text
ACCEPT
```

然后 Runtime handoff不得因为这一 snapshot进入：

```text
INHIBITED invalid fan safety observation
```

---

# Required Regression — FLIGHT_ACTIVE

继续 fake sequence：

```text
reserve
→ commit
→ first valid Flight command
→ fan state = FLIGHT_ACTIVE
```

Safety adapter必须接受合法：

```text
FLIGHT_ACTIVE
```

snapshot。

不要实际执行硬件。

---

# Required Runtime Integration Regression

使用 fake motor/fan ownership endpoints模拟：

```text
DRY_RUN
→ prepare
→ ARMING
→ READY_TO_TAKEOVER
→ motor reserve
→ fan reserve
→ fan safety FLIGHT_WAITING
→ motor commit
→ fan commit
→ owner readback valid
→ atomic ACTIVE
```

必须证明：

```text
FLIGHT_WAITING safety observation
```

不再导致：

```text
invalid fan safety observation
INHIBITED
```

最终 fake runtime可以进入：

```text
authority_state=ACTIVE
command_authority=FLIGHT_CONTROL
actuation_allowed=true
```

按当前架构完成。

---

# Do Not Fake ACTIVE

Runtime regression 必须走真实现有：

```text
reserve
commit
readback
cutoff
atomic commit
```

路径。

不要直接测试中赋值：

```text
runtime.state = ACTIVE
```

来绕过 ownership handoff。

---

# Atomic Ownership Must Stay Frozen

不得修改：

```text
motor reserve
fan reserve
motor commit
fan commit
owner token matching
authority generation
atomic cutoff
command lease
handoff lease
```

本任务只修 safety state vocabulary contract。

如果 handoff在修复 state allowlist后暴露另一个真实问题，
先报告，不顺带 redesign。

---

# Search For Duplicated State Allowlists

全仓搜索：

```text
SAFE_STOP
MANUAL_DISARMED
AUTO_ACTIVE
EMERGENCY_STOP
```

以及：

```text
known fan states
allowed fan states
control_state
```

确认是否还有其他 consumer 复制了一份旧 fan-state allowlist。

如果存在：

- 只修正式 contract 对齐；
- 不创建新的 architecture；
- 不扩大语义。

如果某处明确只允许 legacy states是有意设计，
不要强行加入 Flight states；
必须解释其职责差异。

---

# Preferred Contract Source

如果仓库已有单一正式的：

```text
FanControlState
```

enum/constants，

优先考虑让 safety adapter复用或从正式定义导出合法 state名称，
避免以后再次出现两份手工 allowlist漂移。

但：

```text
不要为了 DRY
```

做大规模 package dependency重构。

如果直接小范围补上：

```text
FLIGHT_WAITING
FLIGHT_ACTIVE
```

是更稳定、依赖更少的方案，
可以采用。

目标是：

```text
minimal fix
```

不是新建 shared-state framework。

---

# Preflight Must Stay Unchanged

不得为了修这个问题修改 Flight preflight。

B1 attempt #3 已经证明：

```text
preflight_ready=true
```

所以当前 preflight不是 blocker。

不要删除：

```text
fan.enabled
fan.passive_for_takeover
manual/AUTO checks
fan state consistency
```

---

# Fan Core Must Stay Unchanged Unless Regression Proves Otherwise

当前 fan core 正常进入：

```text
FLIGHT_WAITING
```

本身是正确行为。

不要为了让旧 adapter通过而把它伪装回：

```text
SAFE_STOP
```

也不要让 reserve 后继续发布：

```text
passive_for_takeover=true
```

正确修复方向是 consumer理解正式 producer state，
不是 producer伪装 legacy state。

---

# Bounded Verification Controller Freeze

不得修改：

```text
test_motor_name=left_pitch
motor_test_offset_rad=+0.05
```

controller逻辑。

本次失败发生在 executable command前，
没有证据表明 bounded controller有问题。

---

# Motor Subsystem Freeze

不得修改：

```text
motor feedback acquisition
cold-start hold
set-zero
motor ownership
motor safety
motor command envelope
```

B1 attempt #3 的 motor feedback仍然正常 zero baseline，
且没有 +0.05 动作证据。

不要动 motor。

---

# Fan E-STOP Fix Freeze

Task 6.2.5 的修复不得回退。

继续测试：

```text
FLIGHT_WAITING
→ E-STOP
→ EMERGENCY_STOP
→ rollback
```

最终仍必须：

```text
e_stop_latched=true
control_state=EMERGENCY_STOP
```

不能因为加入 FLIGHT state支持重新出现：

```text
fan e-stop latch conflicts with control state
```

---

# Required Test Matrix

至少覆盖：

1. FLIGHT_WAITING legitimate snapshot accepted；
2. FLIGHT_ACTIVE legitimate snapshot accepted；
3. FLIGHT_WAITING + e_stop=true rejected；
4. FLIGHT_ACTIVE + e_stop=true rejected；
5. FLIGHT_WAITING + passive=true rejected；
6. FLIGHT_ACTIVE + passive=true rejected；
7. FLIGHT_WAITING + manual conflict；
8. FLIGHT_ACTIVE + AUTO conflict；
9. unknown state rejected；
10. existing SAFE_STOP accepted；
11. existing MANUAL states unchanged；
12. existing AUTO states unchanged；
13. DISABLED semantics unchanged；
14. EMERGENCY_STOP semantics unchanged；
15. Task 6.2.5 E-STOP dominance unchanged；
16. exact B1 reserve -> FLIGHT_WAITING adapter regression；
17. commit -> FLIGHT_ACTIVE adapter regression；
18. Runtime handoff progresses past FLIGHT_WAITING；
19. fake atomic ACTIVE reachable；
20. no old epoch/generation replay；
21. command lease semantics unchanged；
22. handoff lease semantics unchanged；
23. malformed fan snapshot still rejected；
24. Flight preflight unchanged；
25. bounded controller unchanged。

---

# Logging

真实 B1 曾出现：

```text
rejected fan safety observation:
unknown fan control state
```

修复后合法：

```text
FLIGHT_WAITING
FLIGHT_ACTIVE
```

不应再产生该 warning。

真正 arbitrary/unknown state仍应产生明确 reject warning。

不要删除 warning。

不要仅做 rate-limit。

---

# Documentation

更新：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
docs/LATEST_FEEDBACK.md
```

记录 B1 attempt #3：

```text
prepare accepted: YES
preflight READY: YES
handoff started: YES

fan entered:
FLIGHT_WAITING

Flight adapter:
REJECTED legitimate FLIGHT_WAITING as unknown

Runtime:
INHIBITED

ACTIVE:
NO

bounded motor movement:
NO EVIDENCE
```

Task完成后只写：

```text
Task 6.2.6:
SOFTWARE PASS

B1:
READY FOR RETRY
NOT HARDWARE PASS
```

不重跑：

```text
Gate A
Task 6.2.2 hardware
B0
Task 6.2.4 startup
Task 6.2.5 hardware scenario
```

---

# Next B1 Recording

保留最新已经验证可用的文件记录方式：

```bash
stdbuf -oL ros2 topic echo \
  /flight_control/authority/status \
  windarmor_interfaces/msg/FlightAuthorityStatus \
  > /tmp/windarmor_b1_authority.log

stdbuf -oL ros2 topic echo \
  /motors/feedback \
  windarmor_interfaces/msg/MotorFeedbackArray \
  > /tmp/windarmor_b1_feedback.log
```

下一次继续从：

```text
prepare 前
```

开始记录。

---

# Next ACTIVE Timing

继续保持：

```text
ACTIVE max = 3 sec
```

但是：

```text
只有明确检测到 authority_state=ACTIVE
```

后才开始 3 秒窗口。

如果 10 秒内没有 ACTIVE：

```text
E-STOP
NO ACTIVE
```

不得自动重复 prepare。

---

# Hardware Parameters Remain Frozen

下一次 B1仍然：

```text
test_motor_name = left_pitch

motor_test_offset_rad = +0.05

other motors =
captured baseline hold

fan_left_test_command = 0.0
fan_right_test_command = 0.0

ESC power = OFF

GPIO12 -> ESC = DISCONNECTED
GPIO13 -> ESC = DISCONNECTED
```

本 Task不得改变这些参数。

---

# Scope Freeze

不得修改：

- FlightState API；
- FlightCommand API；
- CommandAuthority；
- ControllerState；
- Flight preflight；
- Flight atomic handoff architecture；
- motor subsystem；
- fan startup fix；
- fan E-STOP fix；
- fan PWM normalization；
- bounded verification controller；
- soft limits。

不得增加：

```text
motor-only Flight authority
fan bypass
test bypass
fake fan safety state
```

---

# Software Verification

至少执行：

```bash
source /opt/ros/jazzy/setup.bash

colcon build --symlink-install

source install/setup.bash

python3 -m pytest \
  src/windarmor_fan_controller/test \
  -q

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

全部 software-only。

---

# Stop Conditions

如果发现必须：

- 修改 fan core 正确的 FLIGHT_WAITING 语义；
- 把 FLIGHT state伪装为 SAFE_STOP；
- 放宽 E-STOP invariant；
- 放宽 passive_for_takeover；
- 删除 unknown-state rejection；
- 修改 preflight；
- 修改 motor subsystem；
- 修改 authority architecture；
- 增加 test bypass；
- 使用真实硬件才能完成；

则停止并报告。

---

# Expected Result

修复后 fake B1：

```text
SAFE_STOP
    ↓
prepare
    ↓
ARMING
    ↓
preflight READY
    ↓
fan reserve
    ↓
FLIGHT_WAITING
    ↓
SafetyReadbackAdapter ACCEPT
    ↓
commit
    ↓
owner readback valid
    ↓
atomic ACTIVE
    ↓
FLIGHT_ACTIVE safety state
    ↓
SafetyReadbackAdapter ACCEPT
```

而：

```text
unknown arbitrary state
```

仍然：

```text
REJECT
```

并且：

```text
E-STOP
```

仍保持最高优先级：

```text
EMERGENCY_STOP
```

---

# Hardware Status After Task

只允许更新为：

```text
Task 6.2.6:
SOFTWARE PASS

B1 attempt #3:
INCONCLUSIVE / FAIL-CLOSED BEFORE ACTIVE

B1 next:
READY FOR RETRY
NOT HARDWARE PASS
```

不得声称：

```text
Flight bounded actuation hardware PASS
```

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## Hardware Observation

- ARMING reached；
- preflight READY reached；
- FLIGHT_WAITING produced；
- adapter rejected it as unknown；
- Runtime INHIBITED；
- no ACTIVE；
- no confirmed +0.05 rad actuation。

## Root Cause

- producer formal states；
- consumer stale allowlist；
- exact regression reproduction。

## Implementation

- FLIGHT_WAITING handling；
- FLIGHT_ACTIVE handling；
- unknown-state rejection retained；
- cross-field checks retained。

## Safety

- E-STOP invariant；
- passive invariant；
- manual/AUTO conflict；
- enabled truth；
- no authority bypass。

## Tests

- exact commands；
- regression counts；
- package counts；
- workspace counts；
- CI result。

## Hardware Status

明确：

```text
B1 hardware:
NOT PASS
```

## Next Step

```text
B1 bounded Flight takeover retry
```

等待用户新的单独硬件授权。

## Git

默认：

```text
no commit
no push
no tag
```

stable tags：

```text
v0.3.0
v0.3.1
v0.3.2
```

不得移动。