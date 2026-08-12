# 最新反馈：v0.4.0 Task 4.1 Handoff Reliability Hardening

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-12

## Scope

Task 4.1 已完成软件实现、文档同步与 pure/fake/mock/in-memory 验证。修改范围如下：

- Runtime rollback：
  `src/windarmor_flight_control/windarmor_flight_control/runtime/{node,ownership,config}.py`
  与 `src/windarmor_flight_control/config/flight_control.yaml`；
- motor lease：
  `src/imu_cybergear_ros2/imu_cybergear_ros2/{motor_ownership,motor_manager,motor_config,imu_motor_controller_node}.py`
  与 `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`；
- fan lease：
  `src/windarmor_fan_controller/windarmor_fan_controller/{fan_ownership,fan_control,fan_command_manager}.py`
  与 `src/windarmor_fan_controller/config/fan_params.yaml`；
- tests：motor config/ownership、fan config/ownership、Runtime config/handoff 与 bringup
  release-contract 测试；
- docs：`README.md`、`docs/FLIGHT_CONTROL_ARCHITECTURE.md`、
  `docs/FLIGHT_CONTROL_API.md` 和本反馈。

核心变化：rollback helper 不再用会递归 rollback 的 prepare/commit service helper
执行 revoke；cleanup 使用独立 best-effort 路径和结构化结果。motor/fan owner 将
handoff reservation lease 与 ACTIVE command heartbeat lease 分离。

任务开始前已有的 `docs/NEXT_COMMAND.md` 修改已完整保留且未编辑；任务开始与本反馈
生成前 SHA-256 均为
`9e25a9edc6c721d28dc73820d2964b5ff453dccb1cc88078293cb1442a375fa3`。

## Rollback

Runtime 的 rollback 顺序现在固定为：

1. 关闭 executable Flight command gate；
2. invalidate pending/active authority 与 envelope sequencer；
3. 清除 pending owner ack/commit、owner source、handoff timing 和 command bookkeeping；
4. 本地锁存 `INHIBITED`，使 `flight_control_active=False`、
   `actuation_allowed=False` 且 public command authority 为 `NONE`；
5. 最后对 motor 和 fan 各执行一次 best-effort revoke。

revoke service unavailable、service call exception、future exception、future timeout、
rejected 与 malformed response 都只写入独立 cleanup diagnostic，不改变本地 inhibit
原因、不重新进入 rollback、不恢复 command path。内部 cleanup status 至少区分
`not_attempted`、`pending`、`success`、`service_unavailable`、`timeout`、
`exception`、`rejected` 和 `malformed_response`。

ARMING、READY_TO_TAKEOVER 或 ACTIVE shutdown 使用相同的 local-first 顺序；shutdown
不等待 revoke future。fake call count 验证 rollback 只进入一次，motor/fan revoke
各只尝试预期次数，因此 revoke unavailable 导致的递归路径已完全消除。

## Lease Contract

- Runtime handoff transaction timeout：`flight_handoff_timeout_sec=1.0`；
- motor handoff lease：`motor_flight_handoff_timeout_sec=1.5`；
- fan handoff lease：`fan_flight_handoff_timeout_sec=1.5`；
- motor ACTIVE command lease：`motor_flight_command_timeout_sec=0.25`；
- fan ACTIVE command lease：`fan_flight_command_timeout_sec=0.25`；
- best-effort cleanup diagnostic deadline：`flight_revoke_timeout_sec=0.25`。

这些值单位均为本地 monotonic seconds 且必须为严格大于零的有限数值。owner handoff
lease 比 Runtime transaction timeout 多 `0.5 s` 软件调度余量；ACTIVE command
timeout 没有被放宽。所有默认值均未经过真实硬件 timing validation。

reserve 启动 handoff deadline；commit 保留 reserve 时的原 deadline，不把 commit
当作 heartbeat。只有第一条 authority epoch、generation、严格递增 sequence、
post-cutoff 与 payload 均合法的 normal envelope 才结束 handoff lease并启动 ACTIVE
command lease；后续合法 normal envelope 刷新 ACTIVE lease。duplicate、wrong epoch、
wrong generation、invalid payload 与 safe-stop 均不刷新任何 lease。handoff 或 ACTIVE
lease 到期后 owner 独立 stop/hold、清 token 并进入 `NONE`，不会自动恢复 legacy owner。

## Safety Boundary

- `flight_takeover_enabled=false` 默认保持不变；默认 launch 不创建 ownership client
  或 executable command publisher；
- Runtime 启用后仍只经 ownership protocol 与 `FlightCommandEnvelope` 传输意图，
  不直接访问 CyberGear driver、CAN、USB-CAN、IMU serial、GPIO 或 PWM backend；
- 未执行真实 CAN、串口、GPIO12/13、PWM、ESC、电机、风扇或整机 takeover；
- 未 reset 或弱化 ERROR、E-STOP、watchdog、软限位、停用与安全退出；
- 未自动恢复 MANUAL、LEGACY_AUTO 或其他 legacy owner；
- `motor_feedback_timeout_sec=0.0` 保持不变；
- `motor_ids`、`motor_signs`、`motor_limits_min`、`motor_limits_max` 保持
  `[4,3,2,1]`、`[-1,1,-1,1]`、`[-1.57,-1.57,-1.57,0]`、
  `[0,1.57,1.57,1.57]`。

## Tests

按任务文档执行的最终命令：

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
- motor pytest：385 passed；
- fan pytest：112 passed；
- flight pytest：208 passed；
- `colcon test-result --verbose`：739 tests，0 errors，0 failures，0 skipped；
- 完整 `./scripts/ci_software.sh`：safety、whitespace、py-compile、干净 build、
  motor 385、fan 112、flight + interfaces 216、full colcon test 与 test-result 全部通过；
  最终仍为 739 tests，0 errors，0 failures，0 skipped。

开发期间有两类非最终失败：首次把多个 package 测试放入同一 pytest 进程时，因仓库
各包顶层 `test` package 名冲突而在 collection 阶段失败，没有执行测试体；改为文档
规定的分包命令后通过。第一轮 fan ownership 目标测试仍保留旧的 `0.25 s` handoff
预期，出现 1 个断言失败；更新为新的两段 lease 契约后复跑通过。完整 CI 的前两次
运行因干净接口构建长时间不输出进度而被人工中断；确认日志持续编译后，独立 clean
build stage 和最终完整 CI 均成功完成。最终验证没有 warning 或 skipped。

新增覆盖包括 local-first rollback、motor/fan/双侧 revoke unavailable、call/future
exception、timeout、rejected/malformed cleanup、partial reserve/commit、atomic commit
failure、ACTIVE owner process disappearance、shutdown with missing owners、fake delayed
handoff、first-command lease transition、valid refresh，以及 invalid/duplicate/wrong-token/
safe-stop 不续租。全部使用 fake client、fake future、fake clock、fake driver 或纯函数，
没有硬件 I/O。

当前未发现进入独立 hardware verification planning 前的软件 blocker。真实方向、机械
动态、通信 timing、PWM/ESC 与联合 takeover 仍未验证，后续实机工作必须另行满足仓库
带电授权门槛；本反馈不把软件结果表述为实机安全或性能验证。

## Git 状态（反馈生成时）

- HEAD：`c6a9bde49d99236fff74a32d9e27cf463205ca9f`；
- branch：`master`，本地 tracking 状态显示 `master...origin/master`，无 ahead/behind；
- working tree：dirty；包含本 Task 4.1 的实现、测试、README/架构/API/本反馈修改，
  以及任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改；没有本任务新增的未跟踪文件；
- implementation/verification 阶段：未 commit；
- push：未执行；tag：未创建、移动、删除或重建；
- remote：仅核验本地配置为 `git@github-windarmor:LeonEleven/WindArmor.git`，未进行
  网络 fetch/ls-remote，因此不声称远端实时状态已核验；
- 本地 `v0.3.0`、`v0.3.1`、`v0.3.2` stable tags 均保持存在；
- 未执行 checkout、reset 或 clean，未覆盖用户既有修改。
