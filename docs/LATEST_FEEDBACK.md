# 最新反馈：v0.4.0 Task 6.2.6 Flight Fan Safety State Contract Alignment

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-17

## Hardware Observation

B1 bounded Flight takeover retry attempt #3 的既有实机观察结果为：

```text
prepare accepted: YES
ARMING reached: YES
preflight READY: YES
ownership handoff started: YES
fan control_state: FLIGHT_WAITING
Flight Runtime: unknown fan control state -> INHIBITED
confirmed FLIGHT_CONTROL ACTIVE: NO
confirmed bounded +0.05 rad movement: NO EVIDENCE
```

fan producer 已按正式 contract 发布 `FLIGHT_WAITING`，但 Flight consumer 拒绝了该状态，
随后按既有 fail-closed 路径进入 INHIBITED。该轮没有确认
`authority_state=ACTIVE`、`command_authority=FLIGHT_CONTROL`、
`actuation_allowed=true` 或 `left_pitch +0.05 rad` 运动，因此 B1 attempt #3 是
`INCONCLUSIVE / FAIL-CLOSED BEFORE ACTIVE`，不是 hardware PASS。

## Root Cause

fan producer 的 `FanControlState` 正式定义 11 个状态：

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

Flight `SafetyReadbackAdapter` 使用独立的封闭 allowlist，却遗漏了正式的
`FLIGHT_WAITING` 和 `FLIGHT_ACTIVE`。修改生产代码前加入实际 fan core snapshot 回归，
两个状态均稳定复现 `ValueError: unknown fan control state`，结果为 2 failed。问题位于
consumer contract，不是 fan core、preflight、authority、motor 或 bounded controller。

## Implementation

修改文件：

- `src/windarmor_flight_control/windarmor_flight_control/runtime/safety_adapter.py`；
- `src/windarmor_flight_control/test/test_fan_estop_rollback_integration.py`；
- `README.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`；
- 任务开始前用户已有的 `docs/NEXT_COMMAND.md` 保持其任务内容不被实现过程改写。

adapter 现在显式维护与 producer 一致的 11-state closed vocabulary，并把两个 Flight 状态
纳入已知集合。识别状态不等于无条件接受：`FLIGHT_WAITING` 和 `FLIGHT_ACTIVE` 必须满足
enabled 已观测且为 true、非 E-STOP、非 passive，且没有 legacy MANUAL/AUTO owner 冲突。
未知字符串和 cross-field 冲突仍抛出错误并由 Runtime fail-closed 处理。

集成测试使用实际 `FanControlCore` snapshot、严格 safety adapter、既有 Runtime prepare/
preflight/ownership state machine 与 fake owner endpoints，走通 reserve、commit、readback、
cutoff 和 atomic ACTIVE；随后 Runtime 产生的真实 envelope 被 fan core 接受并进入
`FLIGHT_ACTIVE`。测试没有直接篡改 Runtime authority state，也没有新增 production 跨包依赖。

## Safety

新增和既有回归共同确认：

- 11 个 producer 正式状态逐一被 consumer 按原值识别；
- 两个 Flight 状态都不能与 E-STOP latch 或 passive predicate 并存；
- Flight 状态要求 `enabled_observed=true` 且 `enabled=true`；
- Flight 状态不能与 legacy MANUAL armed 或 AUTO requested/active 并存；
- 未知状态仍被拒绝；malformed bool 仍被拒绝；
- E-STOP dominance、被动接管、epoch/generation、cutoff、lease、旧 command/restart rejection
  和 explicit-reset-required inhibit 规则均未删除或放宽；
- fan core、preflight、authority、motor、bounded controller、GPIO/PWM 路径均未修改。

本次只对 legitimate Flight ownership readback 补齐 consumer contract，不绕过 authority，
也不把软件模拟结果表述为实机验证。

## Tests

修改前 reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_fan_estop_rollback_integration.py::test_flight_waiting_snapshot_is_a_known_safety_state \
  src/windarmor_flight_control/test/test_fan_estop_rollback_integration.py::test_flight_active_snapshot_is_a_known_safety_state -q
```

旧实现结果：2 failed，均为 `unknown fan control state`。修复并补齐状态矩阵、冲突矩阵和
Runtime handoff integration 后，同一集成文件结果为 25 passed。

规定的完整验证：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/windarmor_fan_controller/test -q
python3 -m pytest src/windarmor_flight_control/test -q
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
./scripts/ci_software.sh
```

结果：

- manual build：5 packages finished；
- fan pytest：153 passed；
- Flight pytest：275 passed；
- manual colcon：895 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety、whitespace、compile、五包 build 全部通过；motor 431 passed、
  fan 153 passed、Flight + interfaces 283 passed；最终 895 tests、0 errors、0 failures、
  0 skipped。

全部验证只使用 pure/fake/mock/in-memory 路径，不是实机验证。

## Hardware Status

```text
Task 6.2.6:
SOFTWARE PASS

B1 attempt #3:
INCONCLUSIVE / FAIL-CLOSED BEFORE ACTIVE

B1 next:
READY FOR RETRY ONLY
NOT HARDWARE PASS

B1 hardware:
NOT PASS
```

本任务没有启动 hardware node/launch、Flight prepare 或 takeover，没有访问 `/dev/*`、真实
serial、SocketCAN、can10、CyberGear、GPIO12/13、PWM 或 ESC，没有给 motor/fan 通电，也
没有发送 actuator command。

## Next Step

下一步仍是：

```text
B1 bounded Flight takeover retry
with file-based observation
```

从 prepare 前持续记录 `/tmp/windarmor_b1_authority.log` 和
`/tmp/windarmor_b1_feedback.log`。只有明确观察到 ACTIVE event 后才启动最长 3 秒 actuation
window；如果 prepare 后 10 秒内仍没有 ACTIVE，立即 E-STOP、记录 `NO ACTIVE`，且不得自动
重复 prepare。候选边界仍为 `left_pitch`、`+0.05 rad`、其他 motor captured baseline hold、
fan `0.0/0.0`、ESC 断电、GPIO12/13 与 ESC 信号断开。

任何真实 prepare 都必须等待新的单独硬件授权并重新满足十项带电门槛；本次 SOFTWARE PASS
不构成执行授权，也不要求重跑 Gate A、Task 6.2.2、B0、Task 6.2.4 startup test。

## Git

- task-start HEAD：`5fa3810513dab65ff885954bf5af749b756bf0f8`；
- branch：`master...origin/master`，任务开始时无已知 ahead/behind；
- 用户本次明确授权将本任务用中文 commit 并 push 到 GitHub；
- 不创建或移动 tag；stable tags `v0.3.0/v0.3.1/v0.3.2` 保持不变；
- 未执行 checkout/reset/clean。
