# 最新反馈：v0.4.0 Task 6.2.5 Fan E-STOP State Preservation

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-17

## Hardware Observation

B1 bounded Flight takeover retry attempt #2 的实机观察结果为：

```text
prepare accepted: YES
confirmed FLIGHT_CONTROL ACTIVE: NO EVIDENCE
confirmed bounded +0.05 rad movement: NO EVIDENCE
E-STOP: TRIGGERED
```

该轮 Runtime 重复报告：

```text
rejected fan safety observation:
fan e-stop latch conflicts with control state
```

Flight Runtime 重启后正确观察到 `global_estop_active` 并保持 controller inhibited，要求
显式 reset-inhibit。由于没有保存到 ACTIVE 或 actuator command/movement 证据，B1 不是
FAIL，也不是 PASS，仍为 inconclusive。

## Root Cause

修改生产代码前新增 pure-core regression，并复现了以下确定序列：

1. fan 已完成 Flight reserve/commit；
2. `/e_stop=true` 使 `e_stop_latched=true`、state=`EMERGENCY_STOP`、PWM 立即回 stop；
3. E-STOP 后迟到的普通 Flight command 被 core 以 `flight_command_not_allowed` 拒绝；
4. manager 的 fail-closed fallback 调用默认 `force_safe_stop(...)`；
5. 旧实现保留 latch，却把 state 无条件写成默认 `SAFE_STOP`；
6. 当前严格 Flight safety adapter 因 latch/state 矛盾而正确拒绝 readback。

旧实现上的专项结果为 2 failed、4 passed；失败分别锁定迟到 Flight command fallback 和
E-STOP 后 Flight safe-stop 对 state 的降级。

任务中的初始推断只部分成立：缺陷确实是 E-STOP 后再次调用默认/non-E-STOP
`force_safe_stop()`，但同步 pure-core 顺序下 `emergency_stop()` 已主动释放 Flight owner，
随后 revoke 返回 `already_revoked`，不会直接再次调用 `force_safe_stop()`。因此不能把
“revoke service 本身”写成唯一根因；准确根因是统一 cleanup primitive 没有维护 latch
dominance，迟到 command fallback、safe-stop、timeout、zero-generation 等任何调用者都
可能制造矛盾状态。硬件日志没有保存到足以区分当时具体 caller 的证据，本报告不虚构。

## Implementation

修改文件：

- `src/windarmor_fan_controller/windarmor_fan_controller/fan_control.py`；
- `src/windarmor_fan_controller/test/test_fan_estop_dominance.py`；
- `src/windarmor_flight_control/test/test_fan_estop_rollback_integration.py`；
- `src/windarmor_flight_control/package.xml`；
- `README.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`；
- 任务开始前用户已有的 `docs/NEXT_COMMAND.md` 保持内容不被实现过程改写。

`FanControlCore.force_safe_stop()` 现在集中维护一个明确 invariant：

```text
e_stop_latched == true
    => final control state == EMERGENCY_STOP
```

cleanup 仍会立即输出 stop PWM、清除 MANUAL/AUTO、Flight target、owner、epoch、generation、
command sequence 和 lease；只是不再允许普通 requested state 覆盖已锁存 emergency state。
现有 `reset_e_stop()` 仍先检查 external E-STOP 已明确为 false、fan enabled 新鲜合法、motor
mode 新鲜合法，再清 latch 并进入既有 `MANUAL_DISARMED`。没有新增 public state、service、
自动 reset 或 legacy reclaim，也没有修改 Flight safety adapter、Flight API、authority、
motor subsystem、fan first-observation 或 preflight rules。

Flight package只增加 `windarmor_fan_controller` 的 test dependency，用于实际 fan core 与
fake Runtime owner endpoint 的进程内集成；不形成 production 运行依赖。

## Safety

新增回归覆盖：

- Flight reserved / committed 后 E-STOP；
- E-STOP 后 revoke、safe-stop、handoff timeout、command timeout；
- E-STOP 后 enabled=true、enabled=false、enabled stale；
- E-STOP 后 motor MANUAL、AUTO、ERROR、DISABLED、EMERGENCY_STOP；
- E-STOP 后 zero-generation 初次或再次变化；
- 所有普通 `force_safe_stop()` requested state 均不能降级 E-STOP；
- latch 期间 snapshot 始终为 `EMERGENCY_STOP`、stop PWM、非 passive、非 manual、非 legacy
  AUTO；
- 修正后的 snapshot 被严格 Flight adapter 接受，矛盾 snapshot 仍被拒绝；
- 无 E-STOP 时 revoke、safe-stop、handoff timeout 保持原有 `SAFE_STOP` contract；
- 只有显式 reset 可离开 E-STOP，且 reset 不恢复旧 owner、epoch、generation、token、command
  sequence 或 fan target；旧 command 不能 replay，必须新 reserve/commit/generation/command；
- ACTIVE Runtime 收到 global E-STOP 后 inhibit，motor/fan fake revoke 均执行，command dispatch
  关闭，fan final readback 保持锁存；
- 新 Runtime 仍从 lower-level motor/fan E-STOP readback 聚合
  `global_estop_active=true`，prepare 后进入既有 explicit-reset-required inhibit 路径。

Flight adapter 的 warning 没有删除、放宽或 rate-limit；修复目标是 core 不再发布该类矛盾
状态，其他 malformed/inconsistent observation 仍严格拒绝。

## Tests

修改前 reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_estop_dominance.py -q
```

旧实现结果：2 failed、4 passed。单点修复后同一组为 6 passed；补齐矩阵后的 fan + Runtime
专项为：

```bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_estop_dominance.py \
  src/windarmor_flight_control/test/test_fan_estop_rollback_integration.py -q
```

结果：26 passed。

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
- Flight pytest：254 passed；
- manual colcon：874 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety、whitespace、compile、五包 build 全部通过；motor 431 passed、
  fan 153 passed、Flight + interfaces 262 passed；最终 874 tests、0 errors、0 failures、
  0 skipped。

全部验证只使用 pure/fake/mock/in-memory 路径，不是实机验证。

## Hardware Status

```text
Task 6.2.5:
SOFTWARE PASS

B1 hardware:
NOT PASS
READY FOR RETRY ONLY
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

验证计划已改为从 prepare 前持续记录：

```text
/tmp/windarmor_b1_authority.log
/tmp/windarmor_b1_feedback.log
```

只有明确观察到 ACTIVE event 后才启动最长 3 秒 actuation window；如果没有 ACTIVE，不得
把 prepare 后的 wall-clock 计时当作 ACTIVE test。候选边界仍为 `left_pitch`、`+0.05 rad`、
其他 motor captured baseline hold、fan `0.0/0.0`、ESC 断电、GPIO12/13 与 ESC 信号断开。
任何真实 prepare 必须等待新的单独硬件授权和十项带电门槛，不重跑 Gate A、Task 6.2.2、
B0 或 Task 6.2.4 startup test。

## Git

- task-start HEAD：`75eafcb48c23af22ffeb9fb29a1b48876d7bdbfe`；
- branch：`master...origin/master`，任务开始时无已知 ahead/behind；
- 用户本次明确授权将本任务用中文 commit 并 push 到 GitHub；
- 不创建或移动 tag；stable tags `v0.3.0/v0.3.1/v0.3.2` 保持不变；
- 未执行 checkout/reset/clean。
