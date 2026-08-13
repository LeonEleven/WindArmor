# 最新反馈：v0.4.0 Task 6.2.2 Motor Feedback Acquisition Fix

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-13

## Root Cause

真实 Gate A passive observation 已确认：CAN transport connected，但四台 CyberGear 在
零 host command TX 下均持续 `has_feedback=false`。真实 Gate B baseline 随后确认
normal controller 可完成 ID4/3/2/1 初始化、进入 `MANUAL_RUNNING` 并保持，但
`/motors/feedback` 仍永久没有 feedback。

代码审计确认两层原因：

1. `on_configure()` 先注册 driver feedback callback，再调用
   `connect_and_init_motors()`；初始化中的通信类型 18 `loc_ref` 写入以及 enable 等命令
   可能立即收到 type-2 response，但此时 lifecycle 尚未执行 `on_activate()`，所以
   `node._is_active == false`。
2. `SafetyMonitor.on_motor_feedback()` 原先在 `_is_active == false` 时直接 return，导致
   回调已经收到的真实 measured frame 没有进入 `_motor_feedback` 和本地 monotonic
   receive-time cache。即使只保存一次初始化反馈，实机 idle/hold 又没有持续 spontaneous
   0x02，因此它也会很快变 stale。

修改代码前新增 fake regression：fake driver 在 configure 写 `SDO_TARGET_POS` 时同步返回
合法 type-2。baseline 稳定失败，回调到达但 cache 为 `set()`；修复后同一测试确认
ID4/3/2/1 全部进入 cache。

## Protocol Review

本次重新检查了：

- `reference/document/CyberGear/CyberGear微电机使用说明书.pdf` 第 4.1、4.2 节；
- `reference/document/CyberGear/串口转CAN AT指令表V1.1.pdf` 的 AT 模式扩展帧格式；
- `reference/document/CyberGear/USB-CAN适配器说明书 V1.2.pdf` 的 2.0B、1 Mbps 与扩展帧说明；
- 本地 `reference/code/imu_cybergear_2.0_ros2_ws`；
- 只读远端 `https://github.com/LeonEleven/imu_cybergear_2.0_ros2_ws`。

确认的协议事实：

- CyberGear 使用 CAN 2.0 扩展帧、1 Mbps；发送 ID 是
  `(communication_type << 24) | (master_id << 8) | motor_id`。
- type-2 response ID 的 bit8–15 是 motor ID、bit16–21 是 fault、bit22–23 是 device
  mode、bit0–7 是 master ID；payload 是大端 position/velocity/torque/temperature 四个
  `uint16`。
- 手册 4.1.9 明确 type-18 单参数写入应答为完整 type-2。当前 position mode 已使用
  `0x7016 loc_ref`，payload 是 little-endian index、两个零字节和 little-endian float。
- type-17 request 使用同一 extended-ID 布局，payload byte0–1 为 little-endian index，
  byte2–7 为零；response 交换 motor/master 位置，byte4–7 返回参数值。
- `0x7019 mechPos`、`0x701A iqf`、`0x701B mechVel`、`0x701C VBUS` 存在，但手册注明
  `0x7019–0x7020` 只在 firmware 1.2.1.5 可读。本任务没有查询真实 firmware。

前置项目同样只有 type-2 reader、type-18 SDO write 和 `_is_active` feedback guard，
没有可直接采用的持续 status request。最终选择 Option A：在 normal controller active、
当前 owner 仍合法时，重发严格等于最近成功提交的当前 hold target 的 `loc_ref`，利用
documented type-18 -> type-2 response。它提供 Flight 当前需要的全部 position、velocity、
torque、temperature、device mode 和 fault fields。

未采用的方案：

- passive zero-TX：实机已证明没有 spontaneous 0x02，不再是 release requirement；
- type-17：真实 firmware 能力未知，而且不能单独提供完整 temperature/fault/mode/torque；
- enable、stop、set-zero、type-1：会改变运行状态、机械零位或控制语义，不符合本任务；
- 扩大 driver/authority architecture：没有必要。

## Implementation

修改文件：

- `src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py`；
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py`；
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_config.py`；
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`；
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`；
- `src/imu_cybergear_ros2/test/test_motor_config.py`；
- `src/imu_cybergear_ros2/test/test_motor_manager.py`；
- `src/imu_cybergear_ros2/test/test_motor_ownership.py`；
- `src/imu_cybergear_ros2/test/test_motor_safety.py`；
- `src/imu_cybergear_ros2/test/test_structured_feedback_node.py`；
- `README.md`；
- `docs/FLIGHT_CONTROL_ARCHITECTURE.md`；
- `docs/FLIGHT_CONTROL_API.md`；
- `docs/HARDWARE_REFERENCE.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`。

反馈 ingestion 不再与 lifecycle active gate 绑定：完整合法 frame 会以 callback 本地
monotonic receive time 更新 measured cache。invalid frame 仍不覆盖最新合法 frame；
INITIALIZING/inactive configured 状态的 fault bit、连续 invalid 和 critical temperature
仍可触发既有 stop + ERROR。初始化流程新增 feedback-safety latch 检查，已锁存时停止
后续初始化命令并进入事务式 rollback；SHUTTING_DOWN/UNINITIALIZED 不启动新的 safety
action。

active 后创建独立 10 Hz feedback acquisition timer。每个 tick 只在以下条件全部成立时
发送：node active/running、init complete、无 command/safety/transport latch、state 与
MANUAL/LEGACY_AUTO/FLIGHT owner 一致、四台 current target 完整。Flight owner 还必须已
接受当前 generation 的首条 normal command。每次 I/O 前重新核对 owner 和同值 target。

probe 只调用既有 `write_sdo_float(ID, 0x7016, exact_current_target)`，不走 target commit，
所以不改变 `current_targets`、`desired_targets`、speed、last accepted Flight sequence、
run mode 或 ownership。deactivate/cleanup/shutdown 在关闭 driver 前销毁 timer；E-STOP、
ERROR、transport fault、reconnect-locked、reserved/NONE owner 和 revoked generation 均不
发送。probe write failure 复用既有 position-command fail-closed ERROR、全电机 best-effort
stop 和 transport event/reconnect-locked 路径。

## Safety

- 没有启动 hardware node/launch，没有访问 `/dev/*`、真实 serial、SocketCAN、can10、
  CyberGear、GPIO12/13、PWM 或 ESC；没有给 motor/fan 通电。
- probe 值严格等于当前 authoritative committed target；没有用 0、configured value 或
  target 伪造 measured feedback。
- 没有改变 run mode、enable/recover、set-zero、HOME、MANUAL/AUTO 默认语义。
- invalid/fault/temperature、position monitoring、ERROR latch、E-STOP、transport fault、
  reconnect locked、no automatic recovery 均未弱化。
- owner revoke/safe-stop 后不继续 probe；新 Flight generation 的首条 normal command 前
  不读取或重放旧 Flight target。
- 没有新增 `current_a`，没有把 `iqf` 或 torque 伪装成 current。
- `motor_feedback_timeout_sec=0.0` 未改变；Flight observer freshness 未放宽或关闭。
- `flight_takeover_enabled=false` 默认未改变。
- motor IDs、names、signs、limits 和三种 legacy motion speed 未改变。

## FlightRuntimeStatus CLI

`FlightRuntimeStatus.msg`、`CMakeLists.txt` 的 `rosidl_generate_interfaces`、package export、
install 中的 `.msg/.idl/.json`、C/C++ headers、Python module/typesupport 均存在且可加载。
以下检查通过：

```bash
ros2 interface show windarmor_interfaces/msg/FlightRuntimeStatus
ros2 interface list | rg 'windarmor_interfaces/msg/FlightRuntimeStatus'
python3 -c "from rosidl_runtime_py.utilities import get_message; get_message('windarmor_interfaces/msg/FlightRuntimeStatus')"
```

Jazzy 的显式 type 参数语法本身有效；在当前 rebuild + source 环境中原命令不再返回
`The passed message type is invalid`。因此没有 message/package/install bug，历史现象是
运行该 CLI 的终端使用了 stale 或未重新 source 的 workspace overlay。正确恢复与观察：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 interface show windarmor_interfaces/msg/FlightRuntimeStatus
ros2 topic type /flight_control/dry_run/status
ros2 topic echo /flight_control/dry_run/status
```

hardware plan 已改为先检查 topic type，再由 `echo` 自动推断，避免手工 type 与旧环境混淆。

## Tests

根因修复前 regression reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/imu_cybergear_ros2/test/test_structured_feedback_node.py::test_configure_feedback_response_populates_observation_cache -q
```

结果：1 failed；callback 收到 frame，但 `_motor_feedback == {}`。修复后：1 passed。

专项回归：

```bash
python3 -m pytest -p no:cacheprovider \
  src/imu_cybergear_ros2/test/test_motor_config.py \
  src/imu_cybergear_ros2/test/test_motor_manager.py \
  src/imu_cybergear_ros2/test/test_motor_safety.py \
  src/imu_cybergear_ros2/test/test_motor_ownership.py \
  src/imu_cybergear_ros2/test/test_structured_feedback.py \
  src/imu_cybergear_ros2/test/test_structured_feedback_node.py -q
```

结果：133 passed。

规定的完整验证：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/imu_cybergear_ros2/test -q
python3 -m pytest src/windarmor_flight_control/test -q
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
./scripts/ci_software.sh
```

结果：

- build：5 packages finished；
- motor pytest：415 passed；
- Flight pytest：248 passed；
- manual colcon：811 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety/whitespace/compile/build 全部通过；motor 415 passed、fan
  112 passed、Flight + interfaces 256 passed；最终 811 tests、0 errors、0 failures、
  0 skipped；
- `windarmor_interfaces/test/test_message_contract.py`：8 passed；
- warnings/skipped：无测试 warning，无 skipped。受限 sandbox 中一次无 publisher 的
  `ros2 topic echo --timeout` 输出本地 RMW 网络权限诊断，但没有 type-invalid，且不属于
  产品/测试失败。

所有测试只使用 pure/fake/mock/in-memory 路径，不是实机验证。

## Hardware Status

```text
Gate A0: PASS
Gate A1: PASS

Passive zero-TX motor observation:
NOT SUPPORTED / NOT REQUIRED

Gate B baseline:
PAUSED

After this software fix:
READY FOR SEPARATE HARDWARE RETRY
```

没有自动运行 Gate B retry，不能写 hardware PASS。持续 type-2 acquisition、实际总线
timing、无可观察运动和长期稳定性仍等待独立带电验证。

## Next Step

```text
NEXT:
Gate B baseline hardware retry
```

执行前必须再次向用户列出并确认：需要通电的 Raspberry Pi/IMU/CAN 与 CyberGear motor
bus、保持断电的 fan/ESC、exact commands、预期输出、PASS/FAIL、预计动作/方向/限制/
持续时间、急停方法、立即停止条件和恢复断电顺序。本任务不自动执行 retry。

## Git 状态（反馈生成时）

- HEAD：`9f2b3f5c8736838884f96125c329575a7ad2bd61`；
- branch：`master...origin/master`，无已知 ahead/behind；
- working tree：dirty，包含本 Task 的 source/config/tests/docs 修改，以及任务开始前用户
  已有的 `docs/NEXT_COMMAND.md` 修改；该用户文件保持未编辑；
- `git diff --check`：通过；
- commit/push/tag：未执行；
- 未 checkout/reset/clean；stable tags `v0.3.0/v0.3.1/v0.3.2` 未改变。
