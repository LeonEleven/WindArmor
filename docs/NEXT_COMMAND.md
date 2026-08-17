# NEXT_COMMAND

## Task

v0.4.0 Task 6.2.5 — Fan E-STOP State Preservation During Flight Rollback

## Objective

修复 B1 bounded Flight takeover 实机重试中发现的 fan safety 状态一致性问题。

真实 B1 测试观察到 Flight Runtime 持续打印：

```text
rejected fan safety observation:
fan e-stop latch conflicts with control state
```

同一轮测试中：

```text
/flight_control/authority/prepare
```

返回：

```text
success=True
message='authority preparation started: generation=1; takeover_enabled=True'
```

随后测试用：

```text
/e_stop=true
```

终止。

第二次重新启动 Flight Runtime 时又正确观察到：

```text
DRY_RUN controller inhibited;
explicit reset-inhibit is required:
global_estop_active
```

因此：

```text
B1 hardware PASS:
NOT ESTABLISHED

prepare accepted:
YES

confirmed ACTIVE:
NO EVIDENCE

confirmed bounded +0.05 rad movement:
NO EVIDENCE
```

本任务只修复：

> fan E-STOP 已锁存后，Flight rollback / ownership revoke / safe-stop 等路径不得把 fan control state 从 EMERGENCY_STOP 改成 SAFE_STOP 或其他非 E-STOP 状态。

---

# Baseline

当前 Git 基线：

```text
75eafcb
修复风扇启动首观测状态锁定
```

当前验证状态：

```text
Task 6.2.2 motor feedback:
SW + HW PASS

Task 6.2.3 cold-start hold:
SW + HW PASS

Task 6.2.4 fan passive startup:
SOFTWARE PASS
HARDWARE startup observation PASS

B1 bounded Flight takeover:
INCONCLUSIVE

prepare request:
ACCEPTED

confirmed FLIGHT_CONTROL ACTIVE:
NO EVIDENCE

confirmed bounded motor movement:
NO EVIDENCE
```

不要把本次 B1 标成 FAIL，因为未确认 ACTIVE 或 actuator command。

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

禁止：

- 真实 CAN；
- CyberGear 上电；
- ESC/fan 上电；
- GPIO/PWM 连接 ESC；
- hardware launch；
- Flight prepare；
- Flight takeover；
- E-STOP 实机测试；
- actuator command。

全部使用 pure core / fake manager / mock ROS / in-memory tests。

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

重点代码：

```text
src/windarmor_fan_controller/
  windarmor_fan_controller/fan_control.py
  ownership / manager / node related code
  tests

src/windarmor_flight_control/
  windarmor_flight_control/runtime/node.py
  windarmor_flight_control/runtime/safety_adapter.py
  windarmor_flight_control/core/preflight.py
  authority / rollback tests
```

---

# Confirm Root Cause Before Modification

不要直接根据任务描述修改代码。

首先建立 regression，确认当前真实根因。

重点审计以下路径：

```text
fan E-STOP handling
force_safe_stop(...)
accept_flight_safe_stop(...)
revoke_flight_ownership(...)
ownership timeout
Flight rollback
zero-generation / safety transitions
enabled / motor-mode updates
```

当前强推断是：

```text
1. /e_stop=true

2. fan core:
   e_stop_latched=true
   control_state=EMERGENCY_STOP

3. Flight detects E-STOP and performs fail-closed rollback

4. rollback/revoke reaches fan core

5. one path calls force_safe_stop()
   with default/non-E-STOP state

6. e_stop_latched remains true
   but control_state becomes SAFE_STOP

7. Flight safety adapter rejects:
   fan e-stop latch conflicts with control state
```

必须用 pure/fake regression 证明或推翻这个序列。

如果实际根因不同：

```text
STOP
report exact root cause
```

然后仍只做最小范围修复。

---

# Core Safety Invariant

建立一个明确 invariant：

```text
IF e_stop_latched == true

THEN control_state MUST remain EMERGENCY_STOP

UNTIL explicit reset_e_stop succeeds.
```

反向也保持当前 adapter contract：

```text
control_state == EMERGENCY_STOP
```

必须与当前项目定义的 E-STOP latch 语义一致。

不要放宽 Flight safety adapter。

---

# Required Behavior A — Flight Revoke During E-STOP

复现：

```text
fan Flight ownership:
reserved or committed

/e_stop=true
    ↓
e_stop_latched=true
control_state=EMERGENCY_STOP
STOP PWM

then:
revoke_flight_ownership(...)
```

最终必须仍然：

```text
e_stop_latched=true
control_state=EMERGENCY_STOP

left_pwm=STOP
right_pwm=STOP

Flight owner removed
authority/token cleared as current contract requires

passive_for_takeover=false
```

ownership 可以撤销。

**E-STOP state 不可以撤销。**

---

# Required Behavior B — Flight Safe-stop During E-STOP

复现：

```text
e_stop_latched=true
control_state=EMERGENCY_STOP

accept_flight_safe_stop(...)
```

或当前等价路径。

结果必须仍：

```text
EMERGENCY_STOP
STOP PWM
e_stop_latched=true
```

safe-stop payload 不能把 emergency state 降级成：

```text
SAFE_STOP
MANUAL_DISARMED
DISABLED
FLIGHT_WAITING
```

---

# Required Behavior C — Ownership Timeout During E-STOP

如果：

```text
Flight command lease expires
handoff lease expires
owner timeout occurs
```

同时：

```text
e_stop_latched=true
```

则 timeout cleanup 可以：

```text
revoke owner
clear token
clear generation/session state
STOP outputs
```

但最终状态仍必须：

```text
EMERGENCY_STOP
```

---

# Required Behavior D — Ordinary force_safe_stop

审计：

```text
force_safe_stop(...)
```

如果这是多个路径的统一底层函数，优先在最小、明确的位置维护 invariant。

允许实现类似：

```text
if self.e_stop_latched:
    final_state = EMERGENCY_STOP
else:
    final_state = requested_state
```

但不要机械照抄此伪代码。

必须根据现有 architecture 选择最干净的修法。

要求：

```text
ordinary safety stop
```

不能覆盖：

```text
latched emergency stop
```

---

# Required Behavior E — Explicit reset_e_stop Is the Only Exit

保持现有显式恢复契约。

只有：

```text
reset_e_stop(...)
```

满足当前全部恢复条件后，才允许：

```text
e_stop_latched=false
control_state leave EMERGENCY_STOP
```

继续要求当前已有条件，例如实际代码定义的：

```text
external E-STOP 已明确解除
fan enabled observation fresh/legal
motor mode legal
no conflicting unsafe state
```

不要增加自动 reset。

不要因为：

```text
enabled=true
motor mode MANUAL
Flight revoke
new owner generation
new zero generation
```

而自动离开 EMERGENCY_STOP。

---

# Required Behavior F — enabled Updates During E-STOP

测试：

```text
e_stop_latched=true
control_state=EMERGENCY_STOP

update_fan_enabled(true)
update_fan_enabled(false)
enabled timeout
```

无论这些 observation 怎样变化：

```text
E-STOP remains dominant
```

不得把 state 改成：

```text
SAFE_STOP
DISABLED
MANUAL_DISARMED
```

除非项目当前明确把某种更严重 terminal state 定义为高于 E-STOP；
如果存在，必须报告并保持现有优先级。

---

# Required Behavior G — Motor Mode Updates During E-STOP

测试：

```text
EMERGENCY_STOP latched
```

随后 motor mode/readback：

```text
MANUAL
AUTO
ERROR
DISABLED
EMERGENCY_STOP
```

普通 mode update 不能解除 fan E-STOP。

尤其不能出现：

```text
motor returns MANUAL
    ↓
fan becomes SAFE_STOP
```

---

# Required Behavior H — Zero-generation / Set-zero Observation

本次 B1 前出现过：

```text
safety_reason:
统一零点已变化；等待新姿态和重新授权
```

如果 E-STOP 已锁存后又发生：

```text
zero generation changed
姿态重新授权失效
```

可以更新 reason / revoke owner / clear authorization。

但不得：

```text
EMERGENCY_STOP -> SAFE_STOP
```

E-STOP 状态优先。

---

# Required Behavior I — Safety Snapshot Truthfulness

任何：

```text
e_stop_latched=true
```

的 published fan safety snapshot 必须满足：

```text
control_state=EMERGENCY_STOP
passive_for_takeover=false
manual_armed=false
legacy_auto_active=false
```

按当前 contract保留其他 truthful fields。

不得为了让 Flight adapter接受而伪造：

```text
e_stop_latched=false
```

---

# Required Behavior J — Flight Safety Adapter Must Stay Strict

不得修改 Flight safety adapter 来接受：

```text
e_stop_latched=true
control_state=SAFE_STOP
```

当前 rejection：

```text
fan e-stop latch conflicts with control state
```

是正确的。

修复后目标是：

```text
fan publisher/core 不再产生这种矛盾状态
```

而不是：

```text
Flight 接受矛盾状态
```

---

# Required Regression 1 — Exact Hardware Failure Shape

构建接近 B1 实际顺序的 fake test：

```text
fan normal startup
enabled=true
SAFE_STOP/passive

Flight reserve
Flight commit

then:
/e_stop=true

fan:
EMERGENCY_STOP
e_stop_latched=true

Flight/runtime rollback:
revoke ownership

final snapshot:
e_stop_latched=true
control_state=EMERGENCY_STOP
passive_for_takeover=false
STOP PWM
no Flight owner
```

然后通过当前 Flight safety adapter 解析该 snapshot。

必须：

```text
ACCEPTED
```

不能再得到：

```text
fan e-stop latch conflicts with control state
```

---

# Required Regression 2 — Revoke Without E-STOP Still Works

不要为了保持 EMERGENCY_STOP 破坏正常 revoke。

场景：

```text
Flight owner active
e_stop_latched=false
revoke_flight_ownership()
```

应继续按当前 contract：

```text
STOP
owner cleared
normal safe/passive non-E-STOP state
```

不要让所有 revoke 都变成 EMERGENCY_STOP。

---

# Required Regression 3 — Safe-stop Without E-STOP Still Works

正常 Flight safe-stop：

```text
e_stop_latched=false
```

保持当前行为。

不要把本修复变成：

```text
every safe_stop = emergency_stop
```

---

# Required Regression 4 — Timeout Without E-STOP

normal command/handoff timeout：

```text
e_stop_latched=false
```

保持当前 fail-closed state 与 owner cleanup contract。

本任务只增加：

```text
E-STOP already latched
```

时的 dominance。

---

# Required Regression 5 — Explicit Reset

完整序列：

```text
normal
→ Flight owner
→ E-STOP
→ rollback/revoke
→ remains EMERGENCY_STOP
→ external E-STOP false observed
→ explicit reset_e_stop
```

只有最后一步成功后：

```text
e_stop_latched=false
```

并进入当前正式定义的 safe post-reset state。

随后：

```text
passive_for_takeover
```

必须按正常状态重新计算，
不能自动恢复旧 Flight owner。

---

# Required Regression 6 — No Old Authority Replay

E-STOP 前假设：

```text
Flight epoch E
generation G
token T
last command C
```

E-STOP + rollback + reset 后：

不得恢复：

```text
E/G/T/C
```

不得重新发布旧 fan command。

必须重新走：

```text
new reserve
new commit
new generation
new Flight command
```

---

# Required Regression 7 — Flight Runtime Rollback Integration

使用 fake motor/fan ownership endpoints测试 Runtime：

```text
prepare
preflight ready
reserve
commit
ACTIVE or partially committed state
then global E-STOP
```

验证：

```text
Runtime fail closed
fan revoke executed
motor revoke executed as current contract requires
actuation_allowed=false
authority != FLIGHT_CONTROL
controller inhibited appropriately
```

并且 fan final safety readback仍是：

```text
e_stop_latched=true
EMERGENCY_STOP
```

不要通过重启 Runtime 来“解决”状态。

---

# Required Regression 8 — Restart Does Not Clear Lower-level E-STOP

明确锁定这次硬件测试观察到的行为：

```text
lower-level fan/motor E-STOP latched

Flight Runtime process exits
Flight Runtime process restarts
```

新的 Runtime必须仍看到：

```text
global_estop_active=true
```

并进入当前：

```text
controller inhibited
explicit reset required
```

的 fail-closed路径。

本 Task不得改变这一点。

---

# Logging

修复后不要产生高频重复 warning：

```text
rejected fan safety observation:
fan e-stop latch conflicts with control state
```

因为矛盾状态本身不应再生成。

但真正收到其他 malformed/inconsistent safety observation 时，
Flight adapter warning仍应保留。

不要简单 rate-limit 或删除 warning 来掩盖问题。

---

# B1 Test Recording Improvement

同时更新：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

把下一次 B1 的 observation 方法改掉。

不要再要求用户肉眼追：

```text
ros2 topic echo /flight_control/authority/status
ros2 topic echo /motors/feedback
```

高速刷屏。

下一次 B1 必须使用日志文件持续记录，例如：

```bash
ros2 topic echo /flight_control/authority/status \
  > /tmp/windarmor_b1_authority.log

ros2 topic echo /motors/feedback \
  > /tmp/windarmor_b1_feedback.log
```

必要时：

```text
stdbuf
timeout
ros2 bag
```

只能选择当前环境可靠、简单的方式。

目标：

```text
test结束后再分析 ACTIVE区间
```

而不是人工追屏。

---

# B1 E-STOP Timing Improvement

更新验证计划。

禁止再次使用：

```bash
sleep 3 && publish e_stop
```

在 `prepare` 前启动计时，
因为那不是：

```text
ACTIVE duration <= 3 sec
```

而只是：

```text
wall-clock from timer start
```

下一次 B1 应采用更清晰方式。

最低要求：

1. `prepare` 前急停终端就绪；
2. authority日志持续记录；
3. 进入 ACTIVE 后开始计算 bounded actuation window；
4. 最长 3 秒；
5. 用户可更早手动 E-STOP；
6. 如果未进入 ACTIVE，不得把 prepare 后 3 秒误当成 ACTIVE test。

如果纯 shell 自动化无法可靠以 ACTIVE transition作为 timer trigger，
不要增加复杂脚本。

允许采用：

```text
用户看到明确 ACTIVE event/log后
立即开始 3-second stop timer
```

但必须结合文件记录，避免状态证据丢失。

不要为此重构 Runtime。

---

# Documentation Status

更新硬件计划记录：

```text
B1 retry attempt #2:

prepare accepted:
YES

confirmed ACTIVE:
NO EVIDENCE

confirmed bounded motor motion:
NO EVIDENCE

E-STOP:
TRIGGERED

Flight Runtime restart:
correctly inhibited by global_estop_active

new blocker:
fan safety readback became internally inconsistent during E-STOP/rollback

observed warning:
fan e-stop latch conflicts with control state
```

修复后只写：

```text
Task 6.2.5:
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
Task 6.2.4 startup test
```

---

# Scope Freeze

不得修改：

- FlightState API；
- FlightCommand API；
- CommandAuthority；
- ControllerState；
- motor feedback acquisition；
- motor cold-start hold；
- motor ownership；
- fan startup first-observation fix；
- fan normalized command；
- bounded verification controller；
- atomic owner reserve/commit architecture；
- preflight safety rules。

不得增加：

```text
motor-only authority
fan bypass
test-only E-STOP bypass
automatic reset E-STOP
automatic legacy owner reclaim
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

# Required Test Matrix

至少覆盖：

1. Flight reserved -> E-STOP；
2. Flight committed -> E-STOP；
3. E-STOP -> Flight revoke；
4. E-STOP -> Flight safe-stop；
5. E-STOP -> handoff timeout；
6. E-STOP -> command timeout；
7. E-STOP -> enabled=true；
8. E-STOP -> enabled=false；
9. E-STOP -> enabled stale；
10. E-STOP -> motor MANUAL；
11. E-STOP -> motor AUTO；
12. E-STOP -> motor ERROR；
13. E-STOP -> zero-generation change；
14. snapshot always EMERGENCY_STOP while latched；
15. passive_for_takeover=false while latched；
16. Flight safety adapter accepts corrected snapshot；
17. normal revoke without E-STOP unchanged；
18. normal safe-stop without E-STOP unchanged；
19. normal timeout without E-STOP unchanged；
20. explicit reset required；
21. reset does not restore old owner；
22. old epoch/generation/token not replayed；
23. old fan command not replayed；
24. Runtime restart sees lower-level E-STOP；
25. global E-STOP inhibits Flight as before。

---

# Stop Conditions

停止并报告，如果发现必须：

- 放宽 Flight safety adapter；
- 自动清除 E-STOP；
- 让 ownership revoke优先于 E-STOP；
- 修改 authority架构；
- 增加新的 public state；
- 改 Flight API；
- 改 motor subsystem；
- 用日志 rate-limit掩盖 inconsistent state；
- 依赖真实硬件才能复现；
- 做架构级 redesign。

---

# Expected Result

目标序列：

```text
Flight owner active
    ↓
/e_stop=true
    ↓
fan:
e_stop_latched=true
control_state=EMERGENCY_STOP
STOP PWM
    ↓
Runtime rollback
    ↓
fan owner revoked
tokens/generation cleared
    ↓
fan STILL:
e_stop_latched=true
control_state=EMERGENCY_STOP
STOP PWM
passive_for_takeover=false
    ↓
Flight safety adapter accepts truthful readback
    ↓
explicit reset_e_stop required
```

绝对不能再次出现：

```text
e_stop_latched=true
control_state=SAFE_STOP
```

---

# Next Hardware Step

软件审核通过后：

```text
B1 bounded Flight takeover retry
```

参数保持：

```text
test_motor_name = left_pitch
motor_test_offset_rad = +0.05

other motors:
captured baseline hold

fan commands:
0.0 / 0.0

ESC power:
OFF

GPIO12/13 -> ESC:
DISCONNECTED
```

下一次使用文件记录：

```text
authority/status
motors/feedback
```

并修正 ACTIVE 3 秒计时流程。

任何真实 `prepare`：

```text
必须等待用户再次单独授权
```

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## Hardware Observation

- B1 prepare accepted；
- no confirmed ACTIVE；
- no confirmed bounded movement；
- E-STOP triggered；
- fan safety conflict warning；
- Runtime restart correctly inhibited by global E-STOP。

## Root Cause

必须说明：

- fake reproduction；
- exact path that changed state；
- whether initial inference was correct or not。

## Implementation

- E-STOP dominance invariant；
- affected fan cleanup paths；
- reset contract unchanged。

## Safety

- ownership revoke；
- safe-stop；
- lease timeout；
- enabled/motor/zero updates；
- no auto reset；
- no old command/authority replay。

## Tests

- exact commands；
- test counts；
- workspace result；
- CI result。

## Hardware Status

明确：

```text
B1 hardware:
NOT PASS
READY FOR RETRY ONLY
```

## Next Step

```text
B1 bounded Flight takeover retry
with file-based observation
```

等待新的硬件授权。

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