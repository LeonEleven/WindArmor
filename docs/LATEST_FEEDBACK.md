# 最新反馈：v0.4.0 Task 6.1 True Read-only Hardware Observation Path

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-13

## Scope

Task 6.1 已建立未来 Stage 1 专用的软件观测链路，但没有执行真实 Stage 1 或任何
硬件操作。

新增：

- `imu_relative_observer_node.py`：独立 IMU relative roll/pitch observer；
- `motor_feedback_observer_node.py`：CyberGear passive-RX structured feedback observer；
- `observation_config.py`：observer-only 纯配置校验；
- `windarmor_observation_only.launch.py`：IMU RX、IMU relative observer、motor passive
  RX observer 和 Flight DRY_RUN 的专用 launch；
- 三组 observer 配置/lifecycle/guard tests。

修改：

- `structured_feedback.py`：允许 authoritative safety latch 为 unknown；此时 feedback
  可 valid/fresh，但不得声称 control subsystem `healthy`；
- motor YAML：新增两个 observer node 的独立参数 section，normal controller section
  与受保护 mapping/sign/limits 未改；
- `imu_cybergear_ros2/setup.py`：新增两个 observer executable entry point；
- `windarmor_bringup/setup.py`、`package.xml`：安装新 launch 并声明 Flight Runtime
  runtime dependency；
- Runtime state aggregator、structured feedback 与 bringup launch tests；
- `README.md`、`docs/HARDWARE_REFERENCE.md`、
  `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 和本反馈。

普通 `windarmor.launch.py`、`imu_cybergear_system.launch.py`、motor/fan control node、
ownership protocol、Flight command/authority implementation 和 interfaces 均未修改。

## CyberGear Read-only Contract

选择结论：**A — Passive RX supported by software path**。

当前 0x02 feedback 的软件路径为：

```text
register feedback callback
-> connect receive transport / start reader
-> receive 0x02 frame
-> existing big-endian parser -> MotorStatus
-> existing validation -> structured /motors/feedback
```

- SocketCAN backend `connect()` 只打开 bus 并启动 `recv()` reader，不发送 CAN frame；
- USB-CAN backend `connect()` 会向 USB-CAN adapter 写 AT transport setup，然后启动
  reader；这些 write 配置 transport adapter，不是 CyberGear actuator command；
- 当前 driver 没有独立 GET/status query；本任务没有新增 query；
- 当前 parser 不要求先执行 control TX，fake RX 也不依赖 command TX；
- 尚未实机证明真实 CyberGear 在零 host command TX 时会主动发送 0x02。未来 Stage 1
  若没有 frame，必须保持 `has_feedback=false`，不得补发初始化 command 或伪造值。

observer 可达 driver method list：

```text
CyberGearDriver(...)
register_feedback_callback(...)
register_feedback_error_callback(...)
register_transport_event_callback(...)
connect_with_retry(...) -> backend connect / reader only
feedback callback
close()
clear_feedback_callbacks()
clear_transport_event_callbacks()
```

observer 不可达 `MotorManager`、run-mode/SDO/target、enter-control、enable/disable、stop、
set-zero、manual/HOME/AUTO、Flight command subscriber 或 ownership service。初次
transport open 默认只尝试一次；runtime disconnect 立即标记 disconnected/stale 并
关闭 reader，不自动 reconnect，也不发送 stop。

Stage 1 的 software-path blocker 已关闭；真实 passive feedback 是否存在仍是 Stage 1
必须实测并记录的 acceptance item，不是本任务的硬件结论。

## IMU Relative Observation

`imu_relative_observer_node` 订阅 `/imu/data_raw`，复用
`corrected_relative_roll_pitch()`，保留 raw message header/source stamp，发布：

```text
/imu/relative_roll_pitch
/imu/zero_generation
```

startup zero reference 固定为 roll/pitch `0.0`，generation 固定为 `0`。节点不提供
`/imu/set_zero`，不校准 IMU、不写串口、不 import motor driver，也不依赖 motor
controller。无效四元数被拒绝，不发布伪造 relative sample。

## Fan Observation

Stage 1 launch 不启动 `fan_controller` 或 fan command manager，不 import `gpiozero`，
不创建 `LGPIOFactory`/`Servo`，不访问 GPIO12/13，不输出 PWM，不执行 ESC arm。

没有发布 synthetic `/fans/status_pwm`、`/fans/enabled`、control/safety state、RPM、
thrust 或 stop measurement。Flight Runtime 中 fan output、enabled、control state 和 fan
safety 保持 unknown/fail-closed。

## Stage 1 Launch

专用入口：

```text
windarmor_bringup/windarmor_observation_only.launch.py
```

包含：

- `imu_driver_node`；
- `imu_relative_observer_node`；
- `motor_feedback_observer_node`；
- `flight_control_runtime_node`。

明确排除 normal `imu_motor_controller_node`、MotorManager、fan controller/manager、
owner control 和 executable actuator publisher。`flight_takeover_enabled` 在 launch 内
固定为 `false`，没有 launch argument 可以将其打开。

预期 Runtime 状态：`DRY_RUN`、authority `NONE`、generation `0`、
`flight_control_active=false`、`actuation_allowed=false`。缺少 motor safety/ownership
和全部 fan state 是设计内的 unknown；即使 IMU/motor observations fresh，也不构成
preflight-ready 或 actuator authority。

该 launch 会在未来访问真实 IMU serial 和 CAN transport，因此本任务没有运行它；
未来仍须 Stage 0 PASS、software gate green 和 Stage 1 单独明确硬件授权。

## Safety Boundary

- 未执行 Stage 0/1，未访问 `/dev/*`、can10、真实 SocketCAN、USB-CAN、IMU serial；
- 未启动任何 ROS node/launch；
- 未发送 CyberGear actuator command，未初始化或移动 motor；
- 未初始化 GPIO/PWM/ESC，未使 fan 旋转；
- 未 owner reserve/commit/revoke，未发送 `FlightCommandEnvelope`；
- 未触发 E-STOP/fault，未执行 E-STOP/ERROR recovery；
- normal control、ERROR、E-STOP、reconnect、ownership、lease 行为不变；
- `flight_takeover_enabled=false` 不变；
- `motor_feedback_timeout_sec=0.0` 不变；
- 受保护 `motor_ids/signs/limits` 不变；stable tag 不变。

## Tests

执行的 observer 专项测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_observation_config.py \
  src/imu_cybergear_ros2/test/test_imu_relative_observer_node.py \
  src/imu_cybergear_ros2/test/test_motor_feedback_observer_node.py \
  src/imu_cybergear_ros2/test/test_structured_feedback.py \
  src/windarmor_bringup/test/test_launch_syntax.py -v
```

结果：23 passed。覆盖 config/mapping、IMU correlation/generation/invalid quaternion、
motor configure/activate/fake receive/stale/invalid/unknown/disconnect/cleanup、完整 no-
feedback entries、unknown safety health 和 launch AST exclusion。

执行完整软件验证：

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
- motor pytest：400 passed；
- fan pytest：112 passed；
- Flight pytest：209 passed；
- standalone colcon：756 tests，0 errors，0 failures，0 skipped；
- unified CI：safety/whitespace/compile/build 全部 PASS，motor 400、fan 112、Flight +
  interfaces 217 passed，colcon 756/0/0/0，exit code 0；
- `rg` forbidden-call audit：observer source/launch 中无 actuator API、MotorManager、
  command/owner service、normal motor controller、fan controller/manager 或 GPIO/PWM
  implementation match；
- warnings/skipped：无。

最终小范围复核曾尝试在同一 pytest process 中混合三个 package 的单文件测试；ROS
`launch_testing` 因各 package 顶层模块同名 `test` 在 collection 阶段报
`ModuleNotFoundError`（0 test executed）。随后按仓库既定分包方式分别重跑：motor
observer 4 passed、bringup launch 3 passed、Flight aggregator 7 passed。该收集错误
不是产品断言失败，也没有创建 node 或访问硬件。

所有新增测试使用 pure/fake/in-memory、直接 callback 或 AST/source inspection；没有
实例化真实 driver/backend/GPIO/serial。这些结果不是实机验证。

## Hardware Plan Status

```text
Stage 0: unchanged
Stage 1: READY FOR SEPARATE AUTHORIZATION
Stage 2–9: BLOCKED / NOT AUTHORIZED
```

`READY FOR SEPARATE AUTHORIZATION` 只表示软件 observation path 和测试已就绪，不是
Stage 1 hardware PASS。Stage 1 仍依赖 Stage 0 PASS、当次 explicit authorization 和
真实证据；如果零 command TX 下收不到 motor feedback，Stage 1 不得 PASS，也不得
自动进入 query/init/control fallback。Task 6.2 staged ownership 和 Task 6.3 bounded
controller 均未进入。

## Git 状态（反馈生成时）

- HEAD：`af8db74b05fc94ba4db03ea7eac89a032305971e`；
- branch：`master...origin/master`，无本地 ahead/behind；
- working tree：dirty；包含本 Task 的 source/config/launch/test/docs 修改，以及任务开始
  前用户已有的 `docs/NEXT_COMMAND.md` 修改；
- `docs/NEXT_COMMAND.md` 保持未编辑，任务前后 SHA-256 均为
  `7f5cf63cc08ea634d03196be00fa9f47bd129041cb42b02a4b6fafe0845d8e8d`；
- implementation/verification 阶段：未 commit；
- push：未执行；tag：未创建、移动、删除或重建；
- 未执行 checkout、reset 或 clean，未覆盖用户既有修改。
