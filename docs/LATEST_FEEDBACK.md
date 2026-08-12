# 最新反馈：v0.4.0 Command Authority & Arming Foundation（No Takeover）

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-12

## 执行结论

v0.4.0 Task 3 已完成。motor 与 fan 现在分别发布 authoritative、read-only、
transient-local safety snapshot；Flight Runtime 使用本地 monotonic receive time
聚合全局 E-STOP `True / False / None`，并提供 pure preflight、authority state
machine、generation/sequence validation、post-grant new-state barrier，以及本地
prepare/cancel/reset-inhibit 服务。

production Runtime 最多进入 `READY_TO_TAKEOVER`，且明确发布
`takeover_supported=false`。它没有 owner acknowledgement production path、actuator
publisher/client 或 dispatch，因此始终保持：

```text
command_authority = NONE
authority_generation = 0
flight_control_active = false
actuation_allowed = false
```

本任务没有执行真实硬件操作，没有 commit、push 或 tag。

## 主要设计

### Authoritative safety readback

- `/motors/safety_state` (`MotorSafetyState`) 直接读取 `StateManager`、lifecycle active
  flag 和既有 feedback safety fault latch，表达内部/公开状态、E-STOP/ERROR latch、
  observation sequence 与最近 transition metadata；
- `/fans/safety_state` (`FanSafetyState`) 直接读取唯一的 `FanControlCore`，表达
  `e_stop_latched`、enabled presence/value、MANUAL armed、legacy AUTO
  requested/active、safety reason 和 passive takeover predicate；
- 两个 publisher 都使用 reliable transient-local QoS，只复制内存状态。发布异常
  不改变 state/latch/arbitration，不访问 driver，也不推进 PWM。

### Global E-STOP 与 freshness

- 任一 authoritative subsystem latch true 时为 `True`，即使另一侧 unknown/stale；
- 两路都已观测、新鲜且 latch false 时才为 `False`；
- 其他情况为 `None`；stale false 不解除，silence 不解除；
- `/e_stop=True` 立即提升风险为 true；只有两路在 trigger 后给出新鲜 false 才能
  解除该本地 trigger 风险；`/e_stop=False` 永远不能单独产生 false；
- `flight_motor_safety_state_freshness_sec` 与
  `flight_fan_safety_state_freshness_sec` 只影响 Flight readback usability，不改变
  motor watchdog、feedback safety、fan timeout 或仍为 `0.0` 的
  `motor_feedback_timeout_sec`。

### Authority / preflight / envelope

- pure authority states：`DISABLED`、`DRY_RUN`、`ARMING`、
  `READY_TO_TAKEOVER`、`ACTIVE`、`INHIBITED`；
- prepare 时分配唯一正 attempt generation，`0` 保留给 no-authority；cancel/inhibit
  后旧 generation 永不复用，reset-inhibit 只回 DRY_RUN；
- pure fake tests 中，只有当前 generation 的 motor + fan ack 都到齐才进入 ACTIVE，
  且 controller `reset()` exactly once；production 以不可配置的
  `takeover_supported=False` 构造 state machine，node 中没有 ack caller；
- preflight 逐项检查 controller、monotonic timing、IMU、required motors、两路 safety
  freshness、global E-STOP、motor MANUAL/ERROR/fault 与 fan enabled/owner/passive
  状态，并返回稳定 reason code；
- READY 丢失任一条件进入锁存 INHIBITED；ARMING 中明确危险、已观测 safety stale/
  invalid 或曾满足的 required inputs 再次失效也会 inhibit；
- `FlightCommandEnvelope` 验证当前非零 generation、严格递增 command sequence、
  `state_sequence > arming_cutoff_state_sequence`、有限 produced time 和合法 command；
- future handoff contract 在全部 ack 后 reset controller 一次，等待 post-cutoff 新
  FlightState，ARMING/READY preview 不缓存、不复用。

### ROS authority status

新增 `/flight_control/authority/status` (`FlightAuthorityStatus`) 以及：

```text
/flight_control/authority/prepare
/flight_control/authority/cancel
/flight_control/authority/reset_inhibit
```

三个 `std_srvs/Trigger` service 只操作 Flight Runtime 本地 state machine，不调用
motor/fan service。status 表达 runtime state、public authority、attempt、preflight、
readback freshness、global E-STOP、last reason 和 `takeover_supported=false`。

## 修改范围

- interfaces：新增 `MotorSafetyState.msg`、`FanSafetyState.msg`、
  `FlightAuthorityStatus.msg` 并更新 CMake/message contract tests；
- motor：新增 `structured_safety.py`，扩展 motor config/node、observer publisher、
  lifecycle/config/readback tests 和 package README；
- fan：为 `FanControlCore` 增加只读 frozen snapshot，在 command manager 增加 safety
  publisher，并增加 dependency/readback tests；
- flight core：扩展 `authority.py`，新增 `preflight.py`、`envelope.py`；
- flight runtime：新增 `safety_adapter.py`，扩展 config、aggregator 与 node；
- tests：新增 global E-STOP、preflight、authority machine、command envelope、motor/
  fan safety readback 和 production no-takeover regression；
- docs/CI：更新根 README、Flight Architecture/API、motor README、CI fan test entry
  与本反馈。

任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改被完整保留；开始和最终核对的
SHA-256 均为
`b16d7fee8cfbb9b2abd07fded17dfd8eca76c2e611cf7840b6cd728719cf0e3f`。

## 软件验证

新增 pure 专项首轮：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest \
  src/windarmor_flight_control/test/test_authority_state_machine.py \
  src/windarmor_flight_control/test/test_command_envelope.py \
  src/windarmor_flight_control/test/test_preflight.py \
  src/windarmor_flight_control/test/test_global_estop.py \
  src/windarmor_flight_control/test/test_state_aggregator.py \
  src/windarmor_flight_control/test/test_runtime_config.py -q
```

- `59 passed`。

首次把多个 ROS Python package 的测试放入同一 pytest 进程时，在 collection 阶段
因各 package 顶层 `test` module 同名出现 `ModuleNotFoundError`；未执行测试体。
改为按 package 独立进程后，新增专项分别为 motor `7 passed`、fan `4 passed`、
flight `51 passed`、interfaces `6 passed`。随后一项旧 runtime test 因仍 monkeypatch
Task 2 的 `build_snapshot()` 而失败；更新为 Task 3 的 `build_runtime_snapshot()`，
并使 invalid snapshot 不进入 authority status cache 后通过。

最终按任务文档执行：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/imu_cybergear_ros2/test -q
python3 -m pytest src/windarmor_fan_controller/test -q
python3 -m pytest src/windarmor_flight_control/test -q
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
./scripts/ci_software.sh
```

最终结果：

- build：`5 packages finished`；
- motor：`373 passed`；
- fan：`102 passed`；
- flight：`154 passed`；
- CI flight + interfaces：`160 passed`；
- workspace：`660 tests, 0 errors, 0 failures, 0 skipped`；
- isolated CI：safety、whitespace、compile、build、各 package tests、full colcon 与
  test-result 全部通过，同样为 `660 tests, 0 errors, 0 failures, 0 skipped`。

所有结果都是 pure/fake/mock/local ROS object 软件验证，不是实机验证或硬件安全
认证。真实 CAN、CyberGear、IMU serial、GPIO12/13、PWM、ESC 和风扇均未访问；
真实硬件测试未执行，因为 Task 3 明确禁止 real takeover 且用户未授权带电操作。

## Compatibility / remaining work

- 既有 `/motor/status`、`/motors/feedback`、`/motors/control_mode`、IMU topics、fan
  topics/services、`/e_stop` trigger、MANUAL/AUTO/HOME、watchdog、ERROR/E-STOP、
  transport recovery 与 safety paths 保持；
- 受保护 motor IDs、signs、min/max limits 未修改；package version 仍为
  `windarmor_interfaces=0.4.0`、`windarmor_flight_control=0.4.0`，稳定 subsystem
  packages 仍为 `0.3.2`；
- Task 4 仍需实现真实 motor/fan owner acknowledgement、atomic grant、production
  ACTIVE 和经既有 safety layer 的 actuator adapters；在此之前 READY 不能解释为
  takeover；
- real hardware validation、calibration、release、commit、push、tag 均未执行。
