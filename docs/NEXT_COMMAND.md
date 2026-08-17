# NEXT_COMMAND

## Task

v0.4.0 Task 6.2.7 — Fan Shutdown Cleanup + Gate C E-STOP Harness Hardening

## Objective

完成两个非常小的 RC 前软件收尾项：

1. 修复 `fan_command_manager` 在 ROS shutdown / Ctrl+C 时，
   `destroy_node()` 仍尝试 publish，导致：

```text
rclpy._rclpy_pybind11.RCLError:
Failed to publish:
publisher's context is invalid
```

2. 为 Gate C 硬件验证提供一个简单、预热的 E-STOP watchdog，
   避免每次临时启动：

```bash
ros2 topic pub --once /e_stop ...
```

产生 ROS process startup / DDS discovery 延迟。

本任务不得修改 Flight 控制架构、motor 控制、fan 控制语义或 authority 逻辑。

---

# Baseline

当前基线：

```text
3e94b5bc3bf2aa20368031c65a25165ac6d9a602
对齐飞控风扇安全状态契约
```

当前 B1 结果：

```text
B1 Flight functional hardware verification:
PASS

atomic combined takeover:
PASS

command_authority=FLIGHT_CONTROL:
PASS

left_pitch +0.05 rad:
PASS

other 3 motors hold:
PASS

motor E-STOP:
PASS

fan E-STOP:
PASS

ownership release:
PASS

actuation_allowed=false after E-STOP:
PASS

no shake / abnormal noise:
PASS
```

但：

```text
procedural ACTIVE <= 3.0 sec:
NOT MET
```

原因已定位为测试工具：

```text
watchdog detects ACTIVE
→ sleep 2.5 sec
→ starts a new `ros2 topic pub --once`
→ ROS process/discovery adds substantial delay
→ actual /e_stop delivery occurs later
```

不是 Flight Runtime 或 lower-level E-STOP 响应慢。

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

- 打开真实 motor power；
- 给 ESC 上电；
- 连接 PWM 到 ESC；
- 执行 Flight prepare；
- 执行 real takeover；
- 调用真实 actuator command；
- 做任何 hardware verification。

---

# Required Reading

先阅读：

```text
AGENTS.md
README.md

docs/LATEST_FEEDBACK.md
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md

src/windarmor_fan_controller/
src/windarmor_flight_control/
scripts/
```

重点检查：

```text
windarmor_fan_controller/fan_command_manager.py

main()
destroy_node()
_finish_observation()
_publish_command()
```

以及当前节点 shutdown 顺序。

---

# Part A — Confirm Fan Shutdown Root Cause

先构造 regression，不要先修改实现。

当前实机 stack：

```text
main
→ node.destroy_node()
→ _finish_observation(force=True)
→ _publish_command(...)
→ Publisher.publish(...)
→ RCLError:
  publisher's context is invalid
```

必须确认实际根因属于哪一种：

```text
A. rclpy.shutdown() 已先发生，
   然后 destroy_node() 尝试 publish

B. launch SIGINT 已使 context invalid，
   destroy_node() 仍无条件 publish

C. 其他实际 shutdown ordering race
```

必须用 software-only regression 重现。

如果实际根因与上述不同：

```text
报告真实根因
做最小修复
```

不要照描述盲改。

---

# Shutdown Invariant

正常运行时的 fail-safe 行为不能被削弱。

如果 ROS context 仍有效：

```text
shutdown
→ manager should finish current observation
→ request STOP / safe command as existing design requires
→ destroy resources
```

但是：

```text
IF ROS context already invalid
THEN destroy cleanup MUST NOT attempt a ROS publish
```

shutdown cleanup 必须：

```text
idempotent
exception-safe
```

重复调用：

```text
cleanup()
destroy_node()
```

不能抛异常，也不能恢复旧 command。

---

# Preferred Fix Direction

优先修正生命周期顺序。

理想顺序类似：

```text
try:
    rclpy.spin(node)
finally:
    if ROS context is still valid:
        perform final safe observation / STOP publication

    destroy node

    shutdown ROS if still required
```

具体按当前代码结构实现。

不要仅仅：

```python
try:
    publish(...)
except Exception:
    pass
```

吞掉所有错误。

可以做窄范围 defensive guard，例如：

```text
if context invalid:
    skip ROS publish during destruction
```

但正常运行期间真正的 publish error 仍应暴露。

---

# Required Shutdown Tests

至少覆盖：

1. normal shutdown while context valid；
2. final safe/STOP publication occurs while context valid；
3. context already invalid before destroy；
4. destroy does not publish into invalid context；
5. no RCLError；
6. repeated cleanup is idempotent；
7. repeated destroy does not restore command；
8. Flight ownership cleanup unchanged；
9. E-STOP cleanup semantics unchanged；
10. normal fan command path unchanged。

---

# Part B — Prewarmed Gate C E-STOP Watchdog

新增一个非常小的测试辅助工具。

推荐位置：

```text
scripts/
```

例如：

```text
scripts/flight_estop_watchdog.py
```

名字可以合理调整。

这不是 production control architecture。

它只用于 hardware verification。

---

# Required Watchdog Behavior

启动后必须先：

```text
create ROS node
create /e_stop publisher
create /flight_control/authority/status subscription
```

然后等待 publisher / DDS graph 已建立。

**不能在检测到 ACTIVE 后再启动新 ROS process。**

---

# Trigger

watchdog 监听：

```text
/flight_control/authority/status
```

只有首次观察到：

```text
authority_state == ACTIVE
command_authority == FLIGHT_CONTROL
actuation_allowed == true
```

才启动计时。

不要仅凭 grep 一个字符串触发。

---

# Timer

使用 monotonic clock：

```python
time.monotonic()
```

或等价 monotonic source。

默认测试参数：

```text
delay_sec = 2.0
```

不要再默认 2.5 秒。

这样给：

```text
ROS scheduling
publication
lower-level callback
safety propagation
```

留下足够 `<3 sec` margin。

允许 CLI 覆盖：

```text
--delay-sec
```

但必须限制：

```text
0 < delay_sec < 3.0
```

硬件计划默认仍使用：

```text
2.0 sec
```

---

# ACTIVE Timeout

如果指定时间内没有进入 ACTIVE，例如：

```text
10 sec
```

watchdog 必须 fail closed：

```text
publish /e_stop=true
report:
NO ACTIVE WITHIN TIMEOUT
```

不得自动 retry prepare。

---

# E-STOP Publication

使用**已经创建并预热的 publisher**：

```text
std_msgs/msg/Bool
data=true
```

不要 shell out：

```text
ros2 topic pub
```

不要启动第二个 Python process。

---

# Publisher Readiness

在进入 armed/waiting 状态前，
至少确认 `/e_stop` publisher 已有 subscriber。

如果当前 ROS API 可可靠取得：

```python
publisher.get_subscription_count()
```

则等待：

```text
subscription_count >= 1
```

带合理 timeout。

如果 timeout：

```text
do not claim watchdog armed
exit non-zero
```

不要在没有 E-STOP subscriber 的情况下开始真实测试。

---

# Watchdog Output

保持简单明确。

至少打印：

```text
WATCHDOG READY
ACTIVE DETECTED
E-STOP TIMER START
E-STOP PUBLISHED
```

并打印 monotonic 时间。

例如：

```text
ACTIVE_DETECTED_MONOTONIC=...
ESTOP_PUBLISHED_MONOTONIC=...
ACTIVE_TO_PUBLISH_SEC=...
```

这样后续不需要靠人手计算。

---

# Optional E-STOP Observation

如果实现很小，可以继续监听：

```text
/flight_control/authority/status
```

直到：

```text
global_e_stop_active=true
actuation_allowed=false
```

然后打印：

```text
ESTOP OBSERVED BY FLIGHT
PUBLISH_TO_INHIBIT_SEC=...
```

这是推荐项。

但不要因此扩展成大型 recorder framework。

现有：

```text
ros2 topic echo > /tmp/*.log
```

仍保留用于完整证据。

---

# Watchdog Must Not Control Authority

该工具不得：

- 调用 `/flight_control/authority/prepare`；
- reset E-STOP；
- reset inhibit；
- reserve owner；
- commit owner；
- revoke owner；
-发送 motor command；
-发送 fan command。

它只允许：

```text
observe authority
publish /e_stop=true
```

prepare 仍由用户单独执行。

---

# Pure Software Testability

把 trigger/timer 判断尽量保持成小的可测试逻辑。

测试至少覆盖：

```text
DRY_RUN:
no timer

ARMING:
no timer

READY_TO_TAKEOVER:
no timer

ACTIVE but wrong command_authority:
no timer

ACTIVE + FLIGHT_CONTROL + actuation_allowed=true:
start timer exactly once

ACTIVE repeated:
must not restart timer

timeout without ACTIVE:
publish E-STOP exactly once

delay expiration:
publish E-STOP exactly once

invalid delay >= 3:
reject

invalid delay <= 0:
reject
```

不得使用真实 hardware。

---

# Do Not Turn It Into Production Safety

这个 watchdog 是验证工具。

不得：

- 把它加入正常 launch 默认启动；
- 把 2 秒 E-STOP 写进 Flight production Runtime；
- 创建新的 controller state；
- 创建新的 CommandAuthority；
- 让 test watchdog成为 production interlock。

Production safety architecture保持冻结。

---

# Documentation — B1 Status

更新：

```text
docs/LATEST_FEEDBACK.md
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

正式记录：

```text
B1 bounded Flight functional hardware verification:
PASS
```

证据包括：

```text
prepare accepted
ARMING
READY_TO_TAKEOVER
atomic ACTIVE

command_authority=FLIGHT_CONTROL

motor_committed=true
fan_committed=true
owner_tokens_match=true
atomic_cutoff_present=true
actuation_allowed=true

left_pitch ≈ baseline + 0.05 rad

other three motors remain at baseline

all relevant feedback:
valid=true
fresh=true
healthy=true
fault_flags=0

/e_stop received by motor controller

AUTO_RUNNING
→ EMERGENCY_STOP

motor:
e_stop_latched=true

fan:
e_stop_latched=true
control_state=EMERGENCY_STOP

Flight:
INHIBITED
command_authority=NONE
actuation_allowed=false

motor ownership:
NONE

fan ownership:
NONE
```

---

# B1 Timing Deviation

同时明确记录：

```text
B1 functional result:
PASS

procedural ACTIVE <= 3.0 sec:
NOT MET in closure run
```

原因：

```text
temporary `ros2 topic pub --once`
startup / DDS discovery delay
```

不得说：

```text
Flight failed E-STOP
```

因为 lower-level 实际收到 `/e_stop` 后，
motor stop 和 EMERGENCY_STOP transition 很快完成。

---

# No More B1 Functional Retest

计划中明确：

```text
Do NOT rerun B1 merely to reconfirm:
- atomic ACTIVE
- left_pitch +0.05
- other motors hold
- motor E-STOP
- fan E-STOP
- owner release
```

这些已经得到 hardware evidence。

下一阶段 Gate C 使用预热 watchdog，
顺便获得严格 `<3 sec` 时间证据即可。

---

# Gate C Preparation

本任务只准备工具和文档。

不要执行 hardware Gate C。

下一步只记录：

```text
Gate C:
READY FOR HARDWARE VERIFICATION
```

Gate C 的真实 hardware test 必须等待新的单独授权。

---

# Existing Shutdown Observation

记录当前 RC blocker：

```text
fan_command_manager Ctrl+C shutdown

destroy_node
→ _finish_observation
→ publish
→ publisher context invalid
→ exit code 1
```

修复后这个已知 stack trace 不应再出现。

同时当前另外观察到：

```text
Cannot shutdown a ROS adapter that is not running
```

必须审计它是否与同一 shutdown ordering 有直接关系。

如果同一窄范围修复自然解决：

```text
include regression
```

如果属于独立原因：

```text
记录
不要顺手大改
```

---

# Scope Freeze

不得修改：

- FlightState API；
- FlightCommand API；
- FlightController API；
- CommandAuthority；
- ControllerState；
- Flight preflight；
- Flight takeover；
- atomic reserve/commit；
- cutoff semantics；
- lease semantics；
- bounded controller；
- motor feedback；
- motor cold-start；
- set-zero；
- fan control states；
- fan E-STOP semantics；
- fan normalized PWM semantics。

不得增加：

```text
motor-only Flight authority
fan-only Flight authority
auto E-STOP reset
auto inhibit reset
hardware bypass
test bypass
```

---

# Software Verification

至少运行：

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

如果 watchdog 有单独 test：

```bash
python3 -m pytest <watchdog tests> -q
```

全部 software-only。

---

# Stop Conditions

如果发现修复必须：

- 修改 production authority architecture；
- 修改 Flight Runtime timing；
- 修改 motor controller；
- 修改 fan state machine；
- 放松 E-STOP；
- swallow arbitrary publish errors；
- 增加 production watchdog；
- 使用真实硬件才能证明；

则停止并报告。

---

# Expected Result

最终：

```text
fan shutdown:
clean
no publish after invalid context
no RCLError
no exit code 1 from known cleanup path

Gate C watchdog:
publisher pre-created
publisher ready before test
waits for real ACTIVE
monotonic timer
default 2.0 sec
publishes E-STOP from same live node
no new ROS process at trigger time
no repeated trigger
10 sec no-ACTIVE fail closed
```

---

# Hardware Status After Task

只允许更新为：

```text
B1 functional hardware verification:
PASS

B1 <=3 sec procedural constraint:
to be closed incidentally during Gate C
with prewarmed watchdog

Task 6.2.7:
SOFTWARE PASS

Gate C:
READY FOR HARDWARE VERIFICATION
```

不要再把 B1 标为：

```text
NOT HARDWARE PASS
```

但也不要声称：

```text
<=3 sec already verified
```

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## B1 Final Functional Result

```text
HARDWARE PASS
```

## Timing Deviation

解释 CLI publisher startup/discovery latency。

## Fan Shutdown Root Cause

说明真实 shutdown ordering root cause。

## Implementation

说明最小 cleanup fix。

## Gate C Watchdog

说明：

```text
prewarmed publisher
ACTIVE trigger
2.0 sec default
10 sec no-ACTIVE fail closed
monotonic timing
```

## Safety

确认 production safety没有变化。

## Tests

给出：

```text
commands
counts
workspace result
ci_software.sh result
```

## Hardware

明确：

```text
No hardware used in Task 6.2.7
```

## Next

```text
Gate C fail-closed hardware verification
```

等待新的单独硬件授权。

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