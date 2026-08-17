# 最新反馈：v0.4.0 Task 6.2.7 Fan Shutdown + Gate C E-STOP Watchdog

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-17

## B1 Final Functional Result

```text
B1 bounded Flight functional hardware verification:
HARDWARE PASS
```

既有 closure run 已确认 prepare、ARMING、READY_TO_TAKEOVER、atomic ACTIVE、
`command_authority=FLIGHT_CONTROL`、motor/fan committed、owner token 匹配、atomic cutoff
存在及 `actuation_allowed=true`。`left_pitch` 达到 baseline `+0.05 rad`，其他三轴保持
baseline；相关 feedback 均为 valid/fresh/healthy、`fault_flags=0`。E-STOP 到达 lower-level
后，motor 从 `AUTO_RUNNING` 进入 `EMERGENCY_STOP`，motor/fan latch 均为 true，fan
control state 为 `EMERGENCY_STOP`，Flight 进入 INHIBITED/NONE、actuation disabled，最终
motor/fan owner 均为 NONE；未观察到 shake 或异常声音。

上述是用户提供的既有实机证据。本 Task 6.2.7 没有重跑 B1。

## Timing Deviation

```text
B1 functional result: PASS
procedural ACTIVE <= 3.0 sec: NOT MET in closure run
```

旧临时 watchdog 在检测到 ACTIVE 后先 sleep 2.5 秒，随后才启动新的
`ros2 topic pub --once`。ROS process startup 和 DDS discovery 增加了显著延迟，导致实际
`/e_stop` publication 晚于 3 秒；lower-level 真正收到 E-STOP 后的 motor stop、fan stop
和状态转换很快，因此不能写成 Flight E-STOP failure。严格 `<3 sec` 证据将在 Gate C
E-STOP 子场景使用预热 publisher 顺便闭合，不为此重跑 B1 functional test。

## Fan Shutdown Root Cause

修改生产实现前增加了真实 rclpy context regression：构造 `FanCommandManager` 后先执行
`rclpy.shutdown()`，再调用 `destroy_node()`。旧实现稳定复现：

```text
destroy_node
-> force_safe_stop
-> _finish_observation
-> _publish_command
-> Publisher.publish
-> RCLError: publisher's context is invalid
```

因此根因是 shutdown ordering：SIGINT/launch teardown 已先使 node context invalid，manager
的 finally cleanup 仍无条件发布；不是 fan state machine 或普通 command path 错误。旧实现
专项结果为 1 failed，异常与实机 stack 一致。

另一个 `Cannot shutdown a ROS adapter that is not running` 字符串只存在于 Jazzy
`launch_ros.ros_adapters.ROSAdapter.shutdown()` 的重复 shutdown guard，不来自本仓库 fan
manager。现有证据不能证明它与 invalid publisher 是同一缺陷，因此本任务记录但不扩展
修改 launch framework。

## Implementation

`fan_command_manager.destroy_node()` 现在具有窄范围 lifecycle guard：

- cleanup 只启动一次，重复 destroy 不重新发布或恢复旧 command；
- 始终在内存 core 中执行 safe-stop，清 owner、token 和旧命令；
- context 有效时仍发布既有最终 STOP 和只读状态；
- context 已无效时跳过全部 ROS publish，再销毁资源；
- `finally` 保证 ROS 资源销毁；有效 context 下的其他 publish error 仍向上暴露，不做
  arbitrary exception swallowing。

新增 `scripts/flight_estop_watchdog.py`，publisher、authority subscription 和 timer 在启动
时一次创建。它确认 `/e_stop` 至少有一个 matched subscriber 后才报告 READY；只在首次
同时观察到 ACTIVE、FLIGHT_CONTROL、`actuation_allowed=true` 后启动 monotonic 计时，
默认 2.0 秒后由同一 publisher 发布一次 E-STOP。10 秒内没有 ACTIVE 时也 fail-closed
发布一次并报告 `NO ACTIVE WITHIN TIMEOUT`。`--delay-sec` 仅允许 `0 < value < 3.0`。

watchdog 可选等待 Flight 回报 `global_e_stop_active=true` 且 actuation disabled，并输出
ACTIVE-to-publish、publish-to-inhibit monotonic 时间。它不调用 prepare/reset，不 reserve/
commit/revoke owner，也不发送 motor/fan command；未加入任何正常 launch。

修改文件：

- `src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py`；
- `src/windarmor_fan_controller/test/test_fan_shutdown.py`；
- `scripts/flight_estop_watchdog.py`；
- `src/windarmor_flight_control/test/test_flight_estop_watchdog.py`；
- `scripts/ci_software.sh`；
- `README.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`；
- 任务开始前用户已有的 `docs/NEXT_COMMAND.md` 内容由实现过程保留。

## Gate C Watchdog

在未来单独获授权的 Gate C E-STOP 子场景中，必须在 prepare 前运行：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 scripts/flight_estop_watchdog.py
```

只有看到 `WATCHDOG READY` 后才可由另一终端执行单独授权的 prepare。watchdog 不适用于
C1 stale-input、C2 command-timeout 或 C3 Runtime-shutdown 子场景，因为自动 E-STOP 会
干扰这些独立 fail-closed 原因。不得退回临时启动 `ros2 topic pub --once` 来测量严格
timing，也不得自动 retry prepare。

## Safety

- production Flight API、authority、preflight、takeover、reserve/commit/cutoff、lease、
  bounded controller 和 Runtime timing 均未修改；
- motor controller、feedback、cold-start、set-zero 和 command envelope 未修改；
- fan state machine、E-STOP dominance、normalized PWM 和 startup semantics 未修改；
- context 有效时的最终 STOP publication 没有删除；无效 context 只禁止必然失败的 ROS
  publish，内存 cleanup 仍执行；
- watchdog 只有 observe authority 和 publish `/e_stop=true` 两项权限，不 reset safety、
  不取得 authority、不产生 actuator command，也不成为 production interlock。

## Tests

修复前 reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_shutdown.py::test_destroy_after_context_shutdown_does_not_publish_or_raise -q
```

旧实现结果：1 failed，准确复现 invalid-context RCLError。

专项验证：

```bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_shutdown.py \
  src/windarmor_flight_control/test/test_flight_estop_watchdog.py -q
```

结果：22 passed，其中 shutdown 5 项、watchdog 17 项。

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
- fan pytest：158 passed；
- Flight pytest：292 passed；
- manual colcon：917 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety、whitespace、compile、五包 build 全部通过；motor 431 passed、
  fan 158 passed、Flight + interfaces 300 passed；最终 917 tests、0 errors、0 failures、
  0 skipped。

全部新增测试使用 pure logic、invalid in-process context 或 capture publisher；没有连接
真实 CAN、串口、GPIO/PWM 或 actuator。

## Hardware

```text
No hardware used in Task 6.2.7

Task 6.2.7:
SOFTWARE PASS

Gate C:
READY FOR HARDWARE VERIFICATION
NOT AUTHORIZED
```

本任务没有启动 hardware node/launch、Flight prepare 或 takeover，没有访问 `/dev/*`、
SocketCAN、can10、GPIO12/13、PWM 或 ESC，没有给 motor/fan 通电，也没有发送真实
actuator command。

## Next

```text
Gate C fail-closed hardware verification
```

按 C1–C4 子场景分别等待新的单独硬件授权和完整十项带电门槛。预热 watchdog 只准备了
工具，不构成任何真实 prepare、E-STOP timing test 或其他 Gate C 执行授权。

## Git

- task-start HEAD：`3e94b5bc3bf2aa20368031c65a25165ac6d9a602`；
- branch：`master...origin/master`，任务开始时无已知 ahead/behind；
- 用户本次明确授权将本任务用中文 commit 并 push 到 GitHub；
- 不创建或移动 tag；stable tags `v0.3.0/v0.3.1/v0.3.2` 保持不变；
- 未执行 checkout/reset/clean。
