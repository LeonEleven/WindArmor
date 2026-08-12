# 最新反馈：v0.4.0 Task 3.1 Authority Handoff Contract Hardening

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-12

## Scope

Task 3.1 已完成 safety publisher restart 判序和 atomic grant cutoff 两项加固，
但没有实现 Task 4 owner handoff 或任何真实输出。

- interface：为 `MotorSafetyState.msg`、`FanSafetyState.msg` 增加正 `uint64
  source_epoch`，保留全部既有字段；
- motor/fan publisher：节点实例构造时生成一次可注入 epoch；同一实例复用 epoch，
  safety sequence 从 `1` 起严格递增，motor lifecycle reconfigure 不重置二者；
- Flight safety adapter：分别按 `(source_epoch, observation_sequence)` 维护 motor
  与 fan 接收 baseline；
- authority API：owner ack 只记录诊断；新增 pure `commit_active(generation,
  current_runtime_state_sequence)`，成功返回 immutable reset/discard event；
- Runtime：preflight READY barrier 使用当 tick 的 `FlightState.sequence`，inhibit
  日志改为 `controller inhibited; explicit reset-inhibit is required`；production
  没有 ack/commit caller；
- tests：增加 restart/stale epoch、zero/duplicate/rollback、publisher lifecycle、
  乱序/旧 generation/duplicate ack、explicit commit 和 post-cutoff barrier 回归；
- 长期文档：更新 `README.md`、`docs/FLIGHT_CONTROL_ARCHITECTURE.md`、
  `docs/FLIGHT_CONTROL_API.md`；本文件是本次最终反馈。

具体实现/测试文件：

```text
src/windarmor_interfaces/msg/{MotorSafetyState,FanSafetyState}.msg
src/windarmor_interfaces/test/test_message_contract.py
src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py
src/imu_cybergear_ros2/test/test_structured_feedback_node.py
src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py
src/windarmor_fan_controller/test/test_fan_safety_readback.py
src/windarmor_flight_control/windarmor_flight_control/core/authority.py
src/windarmor_flight_control/windarmor_flight_control/runtime/{node,safety_adapter}.py
src/windarmor_flight_control/test/runtime_helpers.py
src/windarmor_flight_control/test/test_{authority_state_machine,command_envelope,
global_estop,runtime_safety_boundary,safety_epoch}.py
```

任务开始前已有的 `docs/NEXT_COMMAND.md` 修改已保留且未编辑；开始与反馈生成时
SHA-256 均为
`3dcc22c410b3811156d9f75448fde4a94329c2843372ecb146e6997330e53e1d`。

## Safety Epoch

- 生产默认使用 `time.monotonic_ns()`；这是同一 Linux boot session 内 system-wide
  monotonic 值，节点进程重启后重新取值并得到更新的 epoch，不依赖 wall/ROS time；
- epoch 生成函数可注入；正常值必须在正 uint64 范围，`0` invalid；
- epoch 在 node instance 构造时只生成一次；configure/deactivate/activate 或
  reconfigure 不改变 epoch，也不重置 sequence；
- 首条消息仅接受 epoch/sequence 都大于 `0`；同 epoch 仅接受更大 sequence；
  newer epoch 接受任意正 sequence 并重建 baseline；older epoch 永久拒绝；
- 已覆盖 motor/fan 的 `epoch 100, seq 5000 -> epoch 200, seq 1` 接受，以及随后
  `epoch 100, seq 5001` 拒绝；duplicate、rollback、epoch/sequence 0 均拒绝；
- publisher 仍只读取内存 snapshot，没有增加 CAN、serial、GPIO、PWM 或 driver I/O；
  publication failure 仍不改变 safety state。

## Atomic Grant Contract

- `acknowledge_owner()` 只接受 READY、当前正 generation、required owner 和合法诊断
  sequence；保存 immutable owner/generation/observed sequence，永不设置 cutoff；
- motor/fan 都 ack 后仍为 `READY_TO_TAKEOVER`；duplicate、旧 generation、READY 前、
  cancel 后或 inhibit 后 ack 均确定性拒绝；
- `commit_active()` 只允许 READY、当前正 generation、两路 ack 齐全、合法且不早于
  ready barrier 的 Runtime 当前 sequence，并且只能成功一次；
- commit 瞬间的 `current_runtime_state_sequence` 是唯一 immutable cutoff 来源；
  pure core 返回一次 `controller_reset_required` 和
  `discard_precommit_previews_required` 事件，不导入或调用算法实现；
- 乱序案例 `MOTOR 100 -> FAN 90 -> commit 120` 得到 cutoff 120；反序案例
  `FAN 200 -> MOTOR 150 -> commit 220` 得到 cutoff 220；ack 顺序不影响 cutoff；
- cutoff 120 时，envelope state sequence `90/95/100/119/120` 全部拒绝，只有
  `>=121` 接受；READY preview 不进入 envelope sequencer，也不能在 ACTIVE 后复用。

## Production Boundary

production Runtime 仍以不可配置的 `takeover_supported=false` 构造 authority core，
最多进入 `READY_TO_TAKEOVER`，且始终保持：

```text
CommandAuthority.NONE
authority_generation = 0
flight_control_active = false
actuation_allowed = false
```

没有 owner ack subscriber/service/callback、active commit production service、
actuator publisher/client、`MotionSource.FLIGHT`、fan FLIGHT source、ACTIVE 或 dispatch。
没有启动 ROS hardware node/launch，没有访问 `/dev/*`、CAN、CyberGear、IMU serial、
GPIO12/13、PWM、ESC 或风扇，也没有改变 E-STOP/ERROR/recovery/软限位安全路径。

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

结果：

- build：5 packages finished；
- motor pytest：374 passed；fan pytest：103 passed；flight pytest：170 passed；
- `colcon test-result --verbose`：678 tests，0 errors，0 failures，0 skipped；
- isolated CI：safety、whitespace、compile、build、package pytest、full colcon 和
  test-result 全部通过；CI 中 flight + interfaces 为 176 passed，最终仍为
  678 tests、0 errors、0 failures、0 skipped；
- 无 warnings，0 skipped。

定向验证另覆盖 interface 6 passed、authority/epoch/cutoff 34 passed、motor fake
lifecycle 4 passed、fan in-memory core/node 5 passed。首次把多个 ROS Python package
测试放入同一 pytest 进程时因顶层 `test` 模块同名在 collection 阶段失败，未执行
测试体；随后按 package 独立执行全部通过。增加字段类型断言时曾把 `(type, name)`
元组方向写反，定向测试发现后已修正并复跑通过。

这些均为 pure/fake/mock/local ROS object 软件验证，不是实机验证。真实硬件测试、
带电测试和 calibration 均未执行，因为本任务禁止真实 takeover 且用户未授权硬件
操作。Task 4 仍需实现真实 owner handoff、production atomic commit、ACTIVE 和经
既有安全层的 actuator adapter；本任务没有跨入该范围。

## Git 状态（反馈生成时）

- HEAD：`9467c997faff62b4239989d60e04c006add26bd1`；
- branch：`master`；
- working tree：dirty；包含本任务实现/测试/文档修改、未跟踪的
  `test_safety_epoch.py`，以及任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改；
- implementation/verification 阶段：未 commit；
- push：未执行；
- tag：未创建、移动、删除或重建；
- remote：已只读核验，`origin/master` 为
  `9467c997faff62b4239989d60e04c006add26bd1`，与本地 HEAD 一致；
- stable tags：本地与远端均保持
  `v0.3.0=f7d2a476a1aa7493271e60f202fe53ec5a5218de`、
  `v0.3.1=ff527a370af7203e96480e56901206bdb978932a`、
  `v0.3.2=29ae0bbcfa22206686cb86f5896a08bccfcb5a37`，未变化。
