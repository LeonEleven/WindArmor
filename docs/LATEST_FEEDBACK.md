# 最新反馈：v0.4.0 Task 6 Hardware Verification Planning

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-12

## Scope

Task 6 已完成 v0.4.0 分阶段真实硬件验证计划与当前仓库接口审计，但没有执行任何
Stage 或硬件操作。

新增：

- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`：状态为
  `PLANNED / NOT YET EXECUTED`，包含 Stage 0–9、逐阶段授权、安全 gate、证据模板、
  config snapshot、authorization/hardware scope matrix、global stop/recovery 规则和
  当前执行 blocker。

修改：

- `README.md`：新增长期计划入口，并把“尚未建立 v0.4.0 checklist”的过期说明改为
  “计划仍未执行、每个 Stage 单独授权”；
- `docs/LATEST_FEEDBACK.md`：更新为本 Task 6 反馈。

未修改：

- `AGENTS.md`：现有十项带电授权门槛已经覆盖最高安全要求，无需复制 checklist；
- motor/fan/IMU/Flight source、config、launch、test 和 ROS interface；
- motor/fan ownership、Flight Runtime、authority、envelope、safety monitor 或 timeout
  implementation；
- 任何 config 值或 launch 默认行为。

任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改保持未编辑；本任务写入前后核验
SHA-256 为：

```text
5a46a62e735610460c78a004aa985cdd016504dace4073fe3e0036a59f4715f8
```

## Verification Plan

### Stage 0–9 summary

| Stage | Purpose | Authorization / current gate |
|---|---|---|
| 0 | 断电物理 preflight：机械、CAN、IMU frame、GPIO/fan/ESC、soft limits | 只可由用户下一步单独选择；本任务未执行 |
| 1 | powered read-only state chain 与 DRY_RUN | 单独授权；当前被 read-only path blocker 阻止 |
| 2 | READY 后 ownership reserve/revoke、rollback/lease | 单独 owner 授权；当前被 Runtime 自动 commit blocker 阻止 |
| 3 | 单 motor/单轴 bounded Flight command，fan stop | 单独 motor-motion 授权；等待 bounded controller |
| 4 | fan low normalized command，motor hold | 单独 fan-spin 授权；等待 bounded controller |
| 5 | combined ownership、atomic commit、minimal command | 单独 combined actuator 授权 |
| 6 | algorithm safe-stop、heartbeat/handoff timeout、Runtime/owner loss | 每个 timeout/crash 场景单独授权 |
| 7 | E-STOP during Flight、ERROR interaction | 每个 trigger/recovery/fault 单独高风险授权 |
| 8 | Flight 后 v0.3.2 normal behavior/legacy regression | 单独 legacy motion 授权 |
| 9 | 最终 v0.4.0 RC 摘要回归 | 独立 RC 授权；不在 Task 6 执行 |

计划固定使用：

```text
physical confirmation
-> read-only observation
-> ownership reservation without motion
-> single-subsystem takeover
-> bounded actuator command
-> combined takeover
-> timeout/fault injection
-> legacy regression
```

每个 Stage 都包含 risk、hardware scope、prerequisites、explicit authorization、allowed/
forbidden operations、exact command 状态、expected ROS/physical behavior、observations、
abort/rollback、pass/fail 和 next-stage gate。Stage N PASS 不授权 Stage N+1；FAIL 或
依赖项 `NOT VERIFIED` 时停止。

### Authorization matrix and hardware scope matrix

计划按 Stage 0–9 分别记录是否真实硬件、是否带电、是否可能运动、是否需要单独
授权、software-only 能否部分替代。所有 powered observation、owner takeover、motor
motion、fan spin、combined actuator、timeout/crash、E-STOP/fault、legacy regression
和 final RC 都要求单独授权。

hardware scope matrix 覆盖：

```text
IMU
Motor/CAN
Fan/GPIO/PWM
Flight Runtime
Ownership protocol
E-STOP
Power/mechanical environment
```

其中 Stage 3/4 明确记录当前 combined envelope/owner 契约：未产生动作的一侧仍是
`hold/state` 或 `stop/state`，不能宣称真正获得单 subsystem owner。

### Global stop conditions

计划覆盖 unexpected motor direction、fan side/direction、target/mapping mismatch、
fault/temperature、transport instability、IMU axis mismatch、unknown/stale owner 或
E-STOP、token/sequence anomaly、unexpected ACTIVE/movement、lease timeout、机械干涉、
异常声音/振动/气味/热量、日志不足和用户要求停止。

任一项发生时：停止当前 Stage、不自动继续、记录 evidence、回到 safe state。

### Evidence, config and recovery

统一 evidence template 记录 date/time、operator、HEAD/working tree、config hash、授权、
分域供电、takeover、epoch/generation、owner/source sequence、ControllerState、E-STOP、
motor health、fan state、cutoff/command sequence、expected/observed、PASS/FAIL、stop reason
和 rollback 结果。

config snapshot 要求展开保存：

- motor ID/name/sign/soft limits、manual/auto/home/flight speed、底层 speed/max step、
  `motor_feedback_timeout_sec`、handoff/command timeout；
- fan pins、stop/start/max/Flight max、ramp、底层 watchdog、handoff/command timeout；
- Flight rate、全部 freshness、takeover、handoff/revoke timeout、controller factory 和
  interface 参数。

recovery 保持 fail-closed：ERROR、E-STOP clear、transport reconnect、Runtime restart、
old epoch/generation、owner timeout 和 Flight safe-stop 均不自动恢复 Flight/legacy；新
attempt 要 explicit reset/prepare/handoff，legacy 要 operator explicit reclaim。

计划禁止堵转、越 soft limit、critical overtemperature、过流、破坏 CAN、带电拔插、
触碰 fan、超过 Flight max、修改 safety threshold、绕过 E-STOP/watchdog 或直接写 SDO。

## Interface Audit

### Confirmed topics

- IMU：`/imu/data_raw`、`/imu/status`、`/imu/relative_roll_pitch`、
  `/imu/zero_generation`；
- motor：`/motors/feedback`、`/motors/control_mode`、`/motors/safety_state`、
  `/motors/ownership_state`、`/motors/manual_targets`、`/motor/status`；
- fan：`/fans/status_pwm`、`/fans/enabled`、`/fans/control_state`、
  `/fans/safety_state`、`/fans/ownership_state`、legacy manual/auto status topics；
- Flight：`/flight_control/dry_run/status`、`/flight_control/dry_run/command_preview`、
  `/flight_control/authority/status`、`/flight_control/command`；
- safety：`/e_stop` Bool topic。Motor 还提供同名 Trigger service，计划明确避免混淆。

### Confirmed services

- authority：`/flight_control/authority/{prepare,cancel,reset_inhibit}`；
- motor owner：`/motors/flight_ownership/{prepare,commit,revoke}`；
- fan owner：`/fans/flight_ownership/{prepare,commit,revoke}`；
- existing control/recovery：`/imu/set_zero`、`/motors/set_zero`、`/enable_motor`、
  `/fans/enable`、`/fans/stop`、`/fans/manual_enable`、`/fans/auto_enable`、
  `/fans/reset_e_stop`。

owner services 的 request/response 字段已从当前 `windarmor_interfaces/srv` 核对；计划
没有发明 token、epoch、generation 或 owner state。Stage 2 的示例使用明确非法的
`0` 占位防止误执行，真实正值必须由未来批准工具从当次 Runtime capture。

### Confirmed launch/package/parameters and enums

- `imu_cybergear_ros2/imu_cybergear_system.launch.py`；
- `windarmor_fan_controller/fans.launch.py`；
- `windarmor_flight_control/flight_control_dry_run.launch.py`；
- `windarmor_bringup/windarmor.launch.py`；
- motor、fan 和 Flight 三个 current YAML 的 topic/service、timeout、mapping 和 factory；
- authority states、command authority、motor ControllerState/public mode、motor/fan owner
  phases 和 fan control states。

未发现文档中引用不存在的 topic/service/launch/package/enum。发现的差异不是名称
错误，而是计划目标与当前可执行路径之间的安全能力缺口。

### Task 6.x blockers

1. **Stage 1 read-only path：** motor controller configure 会连接 CAN、写 run mode、
   speed、target `0.0` 并 enter control；relative attitude/zero generation、structured
   motor feedback/safety 又依赖该 controller。fan controller 构造会初始化 GPIO/PWM
   并执行 ESC arm delay。因此当前不能在“零 actuator command”条件下完成完整
   powered read-only state chain。
2. **Stage 2 staged handoff：** takeover=true 的 Runtime 在 READY 后自动 reserve 两路，
   随后自动 commit/atomic commit，没有正式接口停在 reserve 后等待人工 revoke。
3. **Stage 3+ test controller：** 默认 `NeutralExampleController` 的四个 `0.0` target
   明确不是实机机械中位；当前没有以 fresh feedback 为基准、限制单轴幅度、保持
   其余轴并控制 fan stop/low command 的正式 controller。
4. **Stage 3/4 subsystem semantics：** normal envelope 必须同时携带完整 motor frame
   和 fan payload，Runtime ACTIVE 需要两路 owner；当前只能做单域“产生动作”，不能
   做真正单 owner takeover。

建议依次建立：

- Task 6.1：真正 read-only 的 hardware observation/relative-state path；
- Task 6.2：受测试的 staged reserve/revoke verification mode 或等价正式工具；
- Task 6.3：bounded hardware test controller 和 session config；
- Task 6.4：明确接受 combined owner + single-domain actuation，或另行设计兼容的
  single-subsystem ownership contract。

这些 blocker 未在 Task 6 修复。Stage 1–9 保持 `BLOCKED / NOT AUTHORIZED`；只有
Stage 0 可由用户下一步单独选择是否执行。

## Safety Boundary

- 未执行 Stage 0–9，未进行真实硬件验证；
- 未访问 `/dev/*`，未配置 SocketCAN，未启动 ROS node/launch；
- 未连接或控制 CAN、USB-CAN、CyberGear、IMU serial、GPIO12/13、PWM、ESC、motor
  或 fan；
- 未开启 takeover，未实际 reserve/commit/revoke owner，未发布 executable
  `FlightCommandEnvelope`；
- 未触发 E-STOP/fault，未调用 E-STOP/ERROR recovery；
- 未执行 set-zero、enable、Runtime crash/owner loss；
- 未修改 source、control logic、safety、interface、launch 或 config；
- `flight_takeover_enabled=false` 不变；
- `motor_feedback_timeout_sec=0.0` 不变；
- protected motor mapping/limits 不变；stable tags 不变。

## Tests

执行：

```bash
git diff --check
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

结果：

- `git diff --check`：PASS；
- CI safety、Git whitespace、Python compile：PASS；
- clean build：5 packages finished；
- motor pytest：385 passed；
- fan pytest：112 passed；
- Flight + interfaces pytest：216 passed；
- full five-package colcon test：5 packages finished；
- `colcon test-result --verbose`：739 tests，0 errors，0 failures，0 skipped；
- warnings/skipped：无；
- CI exit code：0。

该结果只证明 software/pure/fake/mock gate green，不是 Stage 0–9 或真实硬件验证。
进入 Stage 0 前没有软件 blocker，但仍需用户单独授权断电物理检查；进入 Stage 1
前存在上述 Task 6.1–6.4 blocker。

## Git 状态（反馈生成时）

- HEAD：`413dbc152ddd0ef7f8b949fdfb51c5b0b96ec3de`；
- branch：`master`，本地显示 `master...origin/master`，无 ahead/behind；
- working tree：dirty；本 Task 修改 `README.md`、`docs/LATEST_FEEDBACK.md`，新增
  `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；另有任务开始前用户已有且保持原
  SHA-256 的 `docs/NEXT_COMMAND.md` 修改；
- implementation/verification 阶段：未 commit；
- push：未执行；tag：未创建、移动、删除或重建；
- remote：仅只读核验本地配置为
  `git@github-windarmor:LeonEleven/WindArmor.git`，未进行网络 fetch/ls-remote，
  因此不声称远端实时状态已核验；
- 本地 stable tag 保持：v0.3.0 tag object `f7d2a47`（commit `c3b3c39`）、
  v0.3.1 tag object `ff527a3`（commit `5d7bd0f`）、v0.3.2 tag object `29ae0bb`
  （commit `398ea9b`）；
- 未执行 checkout、reset 或 clean，未覆盖用户既有修改。
