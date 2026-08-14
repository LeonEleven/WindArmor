# 最新反馈：v0.4.0 Task 6.2.4 Fan Passive Startup Ordering Fix

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-14

## Root Cause

B1 bounded Flight takeover 第一次尝试在调用 prepare 前停止。motor safety 为 PASS，
Flight DRY_RUN 为 PASS；fan safety 的真实 readback 为：

```text
enabled_observed=true
enabled=true
control_state=DISABLED
passive_for_takeover=false
```

当时 Flight authority 为 NONE，没有发送 Flight motor command，也没有 fan actuation。

根因是 fan manager/core 与底层 controller 的启动顺序不匹配。`FanControlCore` 从
`SAFE_STOP`、`_fan_enabled=None` 启动，但旧 `control_tick()` 把“尚未收到第一条
enabled observation”与运行期 false/stale 合并处理，第一次 tick 立即进入
`DISABLED`。随后 `update_fan_enabled(True)` 只更新 observation；idle path 又按既有规则
保留 `DISABLED`，因此状态永久不能自然回到 passive。

底层 `DualFanController` 默认先输出 stop PWM 并等待 `arm_delay_sec=3.0`，待初始化返回后
才创建 `/fans/enabled` publisher/timer 并首次发布；manager 的
`fan_enabled_timeout_sec=1.0`。这不是 runtime timeout 配置错误，不能用放大 timeout、
提前伪造 `enabled=true` 或放宽 Flight preflight 解决。

修改生产代码前加入 pure-core reproduction：在 `t=0.1/0.5/1.1/2.0`、尚无任何
enabled observation 时 tick，再于 `t=3.0` 首次更新 true。旧代码按新要求断言后稳定
得到 1 failed，首个 tick 实际为 `DISABLED`，而预期是安全 `SAFE_STOP`。

## Implementation

修改文件：

- `src/windarmor_fan_controller/windarmor_fan_controller/fan_control.py`；
- `src/windarmor_fan_controller/test/test_fan_control.py`；
- `src/windarmor_flight_control/test/test_preflight.py`；
- `README.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`。

`FanControlCore` 只增加一个内部 first-observation latch，不新增公开
`FanControlState`、ROS interface 或 recovery service：

- 首条 `/fans/enabled` 尚未到达时，所有 tick 保持 stop PWM、`SAFE_STOP`、无
  MANUAL/AUTO/Flight owner，并如实报告 `enabled_observed=false`、`enabled=false`；
- 第一条合法 fresh `true` 结束 startup wait；在没有更高优先级 fault 或 owner 时仍为
  stop PWM、`SAFE_STOP`、owner NONE，readback 为 `enabled_observed=true`、
  `enabled=true`、`passive_for_takeover=true`；
- 第一条合法 `false` 立即进入 `DISABLED`；
- 任意无效 payload 或非有限时间同样结束 startup wait、清除观测并进入
  `DISABLED`，后续 true 不会把它当成正常首次观测；
- 已完成首观测后的 false 或 freshness timeout 保持原有 sticky `DISABLED`，后续 true
  不自动恢复。

生产代码未修改 Flight preflight、timeout、底层 `/fans/enabled` 真实性、PWM bounds、
GPIO mapping、motor code、bounded verification controller 或 combined reserve/commit
协议。

## Safety

- **E-STOP：** startup wait 中 `/e_stop=true` 仍立即锁存 `EMERGENCY_STOP` 和 stop PWM；
  后到的 enabled=true 不会清除锁存，仍要求既有显式 reset。
- **Explicit disable / runtime timeout：** 两者都进入 sticky `DISABLED`，释放不安全
  ownership、清除旧命令且不自动 recovery。
- **Motor safety：** invalid、ERROR 和 EMERGENCY_STOP 继续阻止 Flight prepare；startup
  wait 不覆盖 motor E-STOP 状态。
- **Ownership：** startup wait 强制 owner NONE，并清除 MANUAL/AUTO/Flight reserved 或
  committed 状态、epoch/generation 和旧 command sequence；已使用的 Flight token 不能
  replay。
- **Snapshot：** 未观测、合法 true、合法 false、invalid、E-STOP 和 runtime stale 均按
  core 真实状态发布；没有为 preflight 伪造 passive/readiness。
- **Flight：** 既有 enabled、passive、motor、freshness、owner 和 command/handoff lease
  检查全部保留；真正 `DISABLED` 仍被确定性拒绝。

## Tests

修改前 reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_control.py::test_delayed_first_enabled_observation_keeps_safe_passive_startup -q
```

旧代码结果：1 failed，实际首个输出状态为 `DISABLED`。修复后同一测试：1 passed。

专项安全回归：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/windarmor_fan_controller/test/test_fan_control.py \
  src/windarmor_fan_controller/test/test_fan_flight_ownership.py \
  src/windarmor_flight_control/test/test_preflight.py -q
```

结果：124 passed。覆盖首观测延迟并超过 timeout、first true/false、invalid payload/time、
runtime timeout、false→true sticky、startup E-STOP、motor invalid/ERROR/E-STOP、NONE 与旧
MANUAL/AUTO/Flight owner、旧 epoch/generation/command、全程 stop PWM、truthful passive、
healthy startup preflight READY、genuine DISABLED rejection，以及既有 Flight
handoff/command timeout。

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
- fan pytest：131 passed；
- Flight pytest：250 passed；
- manual colcon：848 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety、whitespace、compile、五包 build 全部通过；motor 431 passed、
  fan 131 passed、Flight + interfaces 258 passed；最终 848 tests、0 errors、0 failures、
  0 skipped。

全部验证只使用 pure/fake/mock/in-memory 路径，不是实机验证。

## Hardware Status

```text
Gate A0: PASS
Gate A1: PASS
Task 6.2.2: SOFTWARE + HARDWARE PASS
Gate B feedback baseline: PASS
Gate B Flight DRY_RUN: PASS
B0 cold-start hold-current: PASS

B1 bounded takeover attempt #1:
BLOCKED BEFORE PREPARE

motor safety: PASS
fan safety: enabled=true but stuck DISABLED
Flight authority: NONE
actuation: NONE

Fan passive startup fix:
SOFTWARE PASS

B1 bounded takeover:
READY FOR RETRY
NOT HARDWARE PASS

B1 retry:
NOT EXECUTED
```

本任务没有启动 hardware node/launch，没有访问 `/dev/*`、真实 serial、SocketCAN、
can10、CyberGear、GPIO12/13、PWM 或 ESC，也没有给 motor/fan 通电。

## Next Step

```text
B1 bounded Flight takeover retry
```

只需先确认 fan safety readback 为 fresh、真实 passive，再按新的单独授权重试既有 B1；
不重跑 Gate A、Task 6.2.2 或 B0。候选边界保持 `left_pitch`、`+0.05 rad`、其他 motor
hold captured baseline、fan `0.0/0.0`、ESC 断电且 GPIO12/13 信号断开。任何 Flight
prepare 仍必须等待用户另行明确授权并重新满足十项带电门槛。

## Git

- task-start HEAD：`601de7b4cff2d00a71415c96949aa6be09ba266c`；
- branch：`master...origin/master`，任务开始时无已知 ahead/behind；
- working tree：dirty，包含本 Task 的 source/tests/README/docs 修改，以及任务开始前用户
  已有的 `docs/NEXT_COMMAND.md` 修改；该用户文件保持未编辑；
- `git diff --check`：通过；
- commit/push/tag：未执行；
- 未 checkout/reset/clean；stable tags `v0.3.0/v0.3.1/v0.3.2` 未改变。
