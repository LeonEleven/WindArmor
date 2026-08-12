# 最新反馈：v0.4.0 Task 4 Atomic Owner Handoff & Actuator Adapter

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-12

## Scope

Task 4 已完成软件实现与 pure/fake/in-memory 验证，但 takeover 仍默认关闭，且没有
执行任何真实硬件控制或整机接管。

- authority：正式 token 扩展为 `(authority_epoch, generation)`；Runtime 每个进程
  实例从可注入的 monotonic source 生成一次正 uint64 epoch；旧 epoch ack/envelope
  永久拒绝，newer epoch 不能抢占仍 active 的旧 owner；
- interfaces：新增 `FlightCommandEnvelope.msg`、`OwnershipState.msg` 与结构化
  prepare/commit/revoke ownership services；扩展 authority status；
- motor owner：新增 `MANUAL / LEGACY_AUTO / NONE / FLIGHT_RESERVED /
  FLIGHT_CONTROL`，保持既有 `ControllerState`；`MotionSource.FLIGHT` 复用唯一
  MotorManager timer、软限位、最大步长、速度限制与现有写失败 ERROR 路径；
- fan owner：新增 legacy/none/reserved/flight owner，继续使用唯一
  `FanCommandManager` 和既有 PWM publisher/slew；normalized Flight command 不是
  thrust，默认不超过 legacy AUTO maximum；
- Runtime：仅在 `flight_takeover_enabled=true` 且 READY 后执行双 owner
  reserve/commit，commit response 才作为 ack；两路 readback 匹配后按最新 state
  sequence atomic commit、reset controller、记录 cutoff，并等待 post-cutoff 新状态；
- fail-closed：owner command lease、handoff timeout、owner readback freshness、Runtime
  或 owner restart、partial failure、safe-stop、E-STOP、安全丢失、算法/validation
  异常均会 stop/hold、best-effort revoke 并锁存 Runtime `INHIBITED`；不会自动恢复
  MANUAL/legacy AUTO；
- default：`flight_takeover_enabled: false`；默认 Runtime 不创建 command publisher
  或 ownership clients，不修改 bringup 默认路径；
- docs：已更新 `README.md`、`docs/FLIGHT_CONTROL_ARCHITECTURE.md` 和
  `docs/FLIGHT_CONTROL_API.md`。

主要新增文件：

```text
src/windarmor_interfaces/msg/{FlightCommandEnvelope,OwnershipState}.msg
src/windarmor_interfaces/srv/{PrepareFlightOwnership,CommitFlightOwnership,
RevokeFlightOwnership}.srv
src/imu_cybergear_ros2/imu_cybergear_ros2/motor_ownership.py
src/imu_cybergear_ros2/test/test_motor_ownership.py
src/windarmor_fan_controller/windarmor_fan_controller/fan_ownership.py
src/windarmor_fan_controller/test/test_fan_flight_ownership.py
src/windarmor_flight_control/windarmor_flight_control/runtime/ownership.py
src/windarmor_flight_control/test/test_{owner_handoff,runtime_handoff}.py
```

任务开始前已有的 `docs/NEXT_COMMAND.md` 修改已完整保留且未编辑；任务开始与本
反馈生成前 SHA-256 均为
`6d7420837e9869f835a4dabb4f0f0e8f2ca197dc006a3f79464a32777cb6bcde`。

## Authority 与两阶段交接

- `authority_epoch`、generation、owner/source sequence 均执行正 uint64/顺序校验；
  no-authority 使用零 placeholder；lifecycle/controller reset 不改变 Runtime epoch；
- reserve 只有在 owner 本地安全且 token 新鲜时成功；motor halt 后同步 desired 到
  last successfully written target，fan 走现有 safe-stop；两者都阻止 legacy command，
  但 reserve 阶段不接受 Flight command；
- 两边 reserve 成功后才 commit；commit 必须匹配原 reserve token、重新满足本地安全
  条件，且具有明确幂等行为；第一条有效 envelope 前保持 hold/stop；
- Runtime 只有在两个 commit response ack 与两个 `FLIGHT_CONTROL` ownership
  readback 都匹配当前 token、preflight/safety 仍满足时才 atomic commit；提交瞬间
  sequence 成为 cutoff，controller reset exactly once；
- envelope sequence 从 `0` 开始严格递增，第一条 normal/safe-stop envelope 必须使用
  `FlightState.sequence > cutoff`；pre-commit preview 永不复用；
- Runtime A `(100,1)` 与 Runtime B `(200,1)` 已覆盖：A 的延迟 readback/ack/command
  不能激活或刷新 B session，B 必须重新执行完整 prepare/handoff/commit。

## Actuator adapter 与安全边界

- Motor normal Flight frame 必须覆盖全部配置逻辑名且为有限值；逻辑名映射既有
  motor ID 后仍经 `_set_desired_targets_locked()` 和唯一 motion timer；没有新增
  `FLIGHT_RUNNING`，而是 `AUTO_RUNNING + owner=FLIGHT_CONTROL`；
- fan `0.0` 映射 `fan_stop_pwm_us`，`(0,1]` 映射
  `[fan_start_pwm_us, flight_fan_max_pwm_us]`；默认
  `flight_fan_max_pwm_us=fan_auto_max_pwm_us=1400`，保留 rise/fall slew；
- motor/fan 独立校验 owner、token、严格递增 command sequence、normal/safe-stop
  payload；duplicate/wrong token 不刷新 lease；timeout 后清除 token并进入 owner NONE；
- E-STOP、motor ERROR/feedback latch、fan E-STOP、shutdown 与底层 enabled/mode
  safety 始终优先于 Flight；Runtime 不调用 E-STOP reset、ERROR recovery、set-zero、
  hardware enable，也不直接 import/use driver、CAN、serial、GPIO 或 PWM backend；
- `motor_ids`、`motor_signs`、`motor_limits_min`、`motor_limits_max` 保持
  `[4,3,2,1]`、`[-1,1,-1,1]`、`[-1.57,-1.57,-1.57,0]`、
  `[0,1.57,1.57,1.57]`，未修改安全映射。

## Tests

已按任务文档执行：

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

- build：5 packages finished；
- motor pytest：380 passed；fan pytest：107 passed；flight pytest：192 passed；
- `colcon test-result --verbose`：712 tests，0 errors，0 failures，0 skipped；
- isolated CI：safety、whitespace、compile、build、三组 package pytest、full colcon
  与 test-result 全部通过；其中 flight + interfaces 为 200 passed，最终仍为
  712 tests、0 errors、0 failures、0 skipped。

首次完整 `colcon test` 有 1 个 bringup release-contract failure：测试冻结集合尚未
包含 Task 4 新增且设计要求的 `FLIGHT_WAITING/FLIGHT_ACTIVE`。更新该契约测试和
README 状态说明后，受影响包、完整 test-result 与隔离 CI 均复跑通过。

覆盖包括 epoch/generation replay、owner busy/new-session、reserve/commit 幂等与
partial rollback、atomic commit/reset/update failure、post-cutoff envelope、motor
软限位/步长/write consistency/ERROR、fan mapping/slew/E-STOP、command timeout、
Runtime/owner restart、readback stale、cancel/E-STOP during handoff、safe-stop 和
legacy regression。全部是 pure/fake/mock/local ROS object 软件验证。

真实 CAN、USB-CAN、CyberGear、IMU serial、GPIO12/13、PWM、ESC、电机、风扇和
真实整机 takeover 均未访问、未影响、未执行验证；原因是 Task 4 明确限定软件集成，
且用户未授权硬件操作。剩余风险主要是实机方向、机械动态、PWM/ESC 行为、通信
时序和联合 takeover；这些必须在未来单独满足带电授权门槛后验证，当前不能据软件
结果宣称硬件安全或性能已验证。

## Git 状态（反馈生成时）

- HEAD：`7e3e5bbadfcab79bd99fdfca441c2c4d83674e89`；
- branch：`master`；`origin/master` 与本地 HEAD 一致；
- working tree：dirty；包含本任务实现、测试、长期文档与本反馈修改、新增未跟踪
  Task 4 文件，以及任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改；
- implementation/verification 阶段：未 commit；
- push：未执行；
- tag：未创建、移动、删除或重建；
- 未执行 checkout、reset 或 clean，未覆盖用户既有修改。
