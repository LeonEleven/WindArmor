# 最新反馈：v0.4.0 Task 6.2 Bounded Hardware Verification Controller

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-13

## Scope

Task 6.2 已完成专用 bounded hardware verification controller 和最终实机测试前的
软件准备，没有执行任何真实硬件验证。

新增：

- `windarmor_flight_control/algorithms/bounded_verification_controller.py`；
- `test_bounded_verification_controller.py`，27 项纯算法测试。

修改：

- Flight Runtime config/loader/node：把独立 verification 参数传给 controller factory，
  并在 ROS resource 创建前严格校验；既有单参数 factory 保持兼容；
- `flight_control.yaml`：增加默认禁用的 verification section；
- controller loader、Runtime config、Runtime node/handoff 和 import boundary tests；
- algorithms public export 和默认 example factory 的兼容签名；
- `README.md`、`docs/FLIGHT_CONTROL_API.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`：执行入口收敛为 Gate A–D。

未修改：Flight API models/validation、AuthorityStateMachine、ownership protocol、epoch/
generation、FlightCommandEnvelope、MotorManager、FanCommandManager、command lease、
rollback、observation-only launch、motor/fan lower-level config 和受保护 motor mapping。

## Verification Controller

实现与 factory：

```text
windarmor_flight_control.algorithms.bounded_verification_controller:create_controller
```

- `reset()` 清除全部 captured baseline 和 authority session identity；
- normal command 前要求 authority 为 `FLIGHT_CONTROL`、Flight active、actuation allowed、
  required inputs fresh、E-STOP 明确 false、IMU valid/fresh；
- 每个 required logical motor 必须存在且 name 匹配，并有 finite position、feedback、
  valid、fresh、healthy；缺一项即 `FlightCommand.safe_stop()`；
- 在当前 ACTIVE `(authority_epoch, authority_generation)` 首个合法 snapshot 中一次性
  捕获全部 `MotorState.position_rad`；Runtime 在 atomic commit 时已调用 controller
  `reset()`，因此首帧使用当前 session 新反馈，不使用前次 takeover 数据；
- selected motor 始终为 `captured baseline + configured offset`；其他 motor 每 tick
  明确发送 captured baseline hold，frame 始终包含全部 required logical names；
- baseline 不随 live feedback 或前一 target 递增，不存在 cumulative drift；
- authority epoch/generation 意外变化时先清除 baseline并返回 safe-stop；旧 baseline
  永不进入新 session。任何暂时输入失效也清除 baseline；
- fan 默认 `left=0.0, right=0.0`；可选配置只接受有限 `[0.0,1.0]` 值，不 silent clamp，
  normalized value 不解释为 thrust；
- `verification_controller_enabled=false` 默认 gate；即使误选专用 factory也只返回
  safe-stop；
- enabled 时必须同时选择专用 factory、有效 logical `test_motor_name` 和显式
  `motor_test_offset_configured=true`；仓库的 `motor_test_offset_rad: 0.0` 只是禁用状态
  下的类型占位，不是获准实机 offset；
- NaN、Inf、非法 logical name、越界 fan command、缺失 offset、非法 bool 和目标加法
  溢出均 fail-closed；
- normal 输出是通过现有 validation 的 immutable `FlightCommand`；controller 不 import
  ROS、interfaces、socket/CAN、serial、GPIO/PWM 或 actuator implementation。

控制器只保持 `baseline_positions` 与 session token 两类最小内部状态；没有 verification
authority/state machine、自动 motor cycling、定时序列或 return trajectory。combined
motor+fan atomic ownership 保持不变：B1 为 motor bounded + fan stop，B2 为 motor
feedback-relative hold + single fan bounded command。

## Hardware Readiness

```text
Gate A — Physical + Powered Read-only:
READY FOR SEPARATE AUTHORIZATION / NOT EXECUTED

Gate B — Bounded Actuator Verification:
SOFTWARE READY / PARAMETERS TO BE SET / NOT AUTHORIZED / NOT EXECUTED

Gate C — Fail-closed Verification:
PLANNED / NOT AUTHORIZED / NOT EXECUTED

Gate D — Legacy + Final RC Regression:
PLANNED / NOT AUTHORIZED / NOT EXECUTED
```

- Gate A0 全断电；A1 只给 Raspberry Pi/IMU 必要逻辑供电；A2 明确需要 CyberGear
  motor bus 通电，fan/ESC 仍断电；A3 保留 fan 无真实 readback 的 unknown 边界；
- Gate B1 需要 motor bus 通电，fan manager/controller 逻辑运行但 fan/ESC 动力保持
  断开；B2 需要 motor bus 和获准 fan/ESC 通电，授权不从 B1 延续；
- Gate C 按 safe-stop、command timeout、Runtime stop/restart、owner loss、E-STOP
  子场景分别授权和声明动力；
- Gate D 需要 motor 与 fan/ESC 分步上电，覆盖 MANUAL、LEGACY_AUTO、HOME、E-STOP、
  shutdown/restart 和 explicit legacy reclaim，全部 PASS 后才可进入 RC；
- 仍需用户在执行前决定：唯一 test motor、motor offset/方向/初始位置/持续时间、
  fan channel/normalized command/持续时间、各 Gate C 初始 bounded command；
- 所有 `ros2 launch/topic/service/lifecycle/run`、package、executable、topic/service type、
  parameter 和 controller factory 已按当前 source/config/launch/interface 核对；未决定
  的实机值使用明确占位符，含占位符的命令禁止执行；
- 不再设计 staged reserve pause、reservation keepalive 或新的 production verification
  framework。现有 reserve/commit/atomic ownership 在 Gate B/C 正式路径一起验证。

## Safety Boundary

- 本任务未给 CyberGear 通电；
- 本任务未给 fan/ESC 通电；
- 未访问 `/dev/*`、真实 SocketCAN、can10、IMU serial、GPIO12/13、PWM 或 ESC；
- 未启动任何 ROS hardware node/launch；
- 未执行 motor initialization/movement、fan output/spin 或真实 Flight takeover；
- 未执行 owner prepare/reserve/commit/revoke；
- 未发送真实 `FlightCommandEnvelope`，未触发 E-STOP/fault 或 recovery；
- authority/ownership architecture、ERROR/E-STOP/reconnect 行为未改；
- `flight_takeover_enabled=false` 默认未改；
- `motor_feedback_timeout_sec=0.0` 未改；
- `motor_ids/signs/limits` 仍为 `[4,3,2,1]`、`[-1,1,-1,1]`、
  `[-1.57,-1.57,-1.57,0]`、`[0,1.57,1.57,1.57]`；
- fake/mock/software 结果没有表述为实机验证。

## Tests

新增测试在运行前经 source/fixture 审计：只使用 immutable fake `FlightState`、fake motor
state、pure config/factory 与 AST/source import guard；不创建 hardware node/backend，
不连接 CAN/串口，不初始化 GPIO/PWM。

专项 controller/config/loader/import 测试：

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_bounded_verification_controller.py \
  src/windarmor_flight_control/test/test_runtime_config.py \
  src/windarmor_flight_control/test/test_controller_loader.py \
  src/windarmor_flight_control/test/test_import_boundary.py -q
```

结果：首轮 65 passed；最终 controller 单文件复核 27 passed。覆盖 disabled、authority/
actuation/freshness、IMU、missing/stale/unhealthy motor、完整 frame、baseline、selected
offset、other hold、fan stop/config、invalid config、overflow、immutability、no drift、reset、
generation/epoch isolation 和 import boundary。

构建与 Flight tests：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install

source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest src/windarmor_flight_control/test -q
```

结果：5 packages finished；最终 Flight tests 248 passed。

五包测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
```

结果：5 packages finished；795 tests，0 errors，0 failures，0 skipped。

统一软件 CI：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

结果：exit code 0；CI safety、Git whitespace、Python compile、隔离五包 build 全部通过；
motor 400 passed，fan 112 passed，Flight + interfaces 256 passed；最终 colcon
795/0/0/0。隔离环境首次构建 `windarmor_interfaces` 用时 4 min 41 s，最终正常完成。
warnings/skipped：无。

一次完整 Flight pytest 尝试把 `PYTHONPATH` 临时覆盖为 package source，因覆盖掉 ROS
Jazzy Python path，两个既有 in-process Runtime test 在 collection 阶段找不到 `rclpy`；
0 项相关测试执行。这是测试环境设置错误，不是产品断言失败。随后按指定顺序完成
build 并 source ROS + workspace，最终 248 passed；统一 CI 也独立通过。

真实 Gate A–D、powered observation、motor/fan motion、timeout/E-STOP physical behavior
均未执行，等待逐场景实机授权与验证。

## Next Step

```text
NEXT:
Gate A — Physical + Powered Read-only

NOT AUTHORIZED / NOT EXECUTED
```

真正执行前必须先依据更新后的 plan 向用户提供当次子阶段的设备通电/断电清单、
完整逐终端命令、预期 ROS/物理结果、PASS/FAIL、立即停止条件和安全退出顺序，并等待
新的明确授权。默认从 A0 断电物理检查开始；A0 PASS 不自动授权 A1/A2。

## Git 状态（反馈生成时）

- HEAD：`918270e2fe970860819e222a22c68b8ef546041d`；
- branch：`master...origin/master`，status 未显示本地 ahead/behind；
- working tree：dirty；包含本 Task 的 controller/config/runtime/tests/docs 修改，以及
  任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改；
- `docs/NEXT_COMMAND.md` 未被本任务编辑或覆盖；任务读取时工作区 SHA-256 为
  `3237027a2a81d62c89dbb9d6962464ba2f4c32978f175e70788b972192acea21`，与 HEAD
  版本 `5a46a62e735610460c78a004aa985cdd016504dace4073fe3e0036a59f4715f8` 不同；
- `git diff --check`：PASS；
- implementation/verification：未 commit；push/tag：未执行；未 checkout/reset/clean；
- origin URL 只做本地配置核对，未 fetch、未联系 remote；
- local stable tags 保持：`v0.3.0=f7d2a476...`、`v0.3.1=ff527a37...`、
  `v0.3.2=29ae0bbc...`；未创建、移动、删除或重建 tag。
