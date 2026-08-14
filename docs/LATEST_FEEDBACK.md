# 最新反馈：v0.4.0 Task 6.2.3 Cold-start Hold-current Motor Initialization

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-14

## Root Cause

CyberGear 官方手册明确说明通信类型 6 设置的机械零位“掉电丢失”。这里的关键事件是
CyberGear motor power loss，不能把 Raspberry Pi 单独掉电描述成电机零位必然丢失。
软件也无法从一个合法当前位置判断机器人是否正处于项目机械零位，因此 cold startup
不能自动 set-zero。

真实 Gate B normal feedback baseline 观察到启动前位置约为：

```text
ID4 target=0.000, actual≈0.845 rad
ID3 target=0.000, actual≈0.747 rad
ID2 target=0.000, actual≈0.910 rad
```

旧初始化顺序先写 `run_mode` 和 `limit_spd`，随后无条件写
`loc_ref=0.0`，最后进入 control mode。CyberGear 手册 4.1.9 规定通信类型 18 单参数
写入应答为完整通信类型 2；Task 6.2.2 已使 configure 阶段的合法 type-2 进入 measured
feedback cache。因此旧代码在第一次位置目标之前已经具备取得真实位置的协议路径，却
没有使用它，导致掉电后可能主动运动到已失效的内部零点。

修改代码前增加了 fake reproduction：ID4/3/2/1 分别返回
`0.85/0.74/0.91/0.42 rad`，旧代码仍把四台首次位置目标全部写成 `0.0`。测试按新安全
要求断言后稳定得到 1 failed，明确证明 measured position 与 startup commanded target
不一致。

## Implementation

修改文件：

- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`；
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py`；
- `src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py`；
- `src/imu_cybergear_ros2/test/fake_motor_driver.py`；
- `src/imu_cybergear_ros2/test/test_motor_lifecycle.py`；
- `src/imu_cybergear_ros2/test/test_motor_reliability.py`；
- `src/imu_cybergear_ros2/test/test_motor_safety.py`；
- `src/imu_cybergear_ros2/test/test_structured_feedback_node.py`；
- `src/imu_cybergear_ros2/test/test_transport_lifecycle.py`；
- `README.md`；
- `docs/HARDWARE_REFERENCE.md`；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`；
- `docs/LATEST_FEEDBACK.md`。

每台电机每次初始化 attempt 开始时记录该 ID 的合法 feedback generation。随后仍沿用
当前 communication path 写 `SDO_RUN_MODE` 和 `SDO_TARGET_SPEED`；两者都是 type-18，
其 type-2 response 由既有 SafetyMonitor 完整校验并进入 cache。第一次
`SDO_TARGET_POS` 前必须取得 generation 更新后的同 ID feedback，且同时满足：

- cache、local receive time 和 position 均存在；
- feedback motor ID 与当前 configured motor 完全一致；
- position 是有限数值；
- device mode 属于协议允许集合；
- fault flags 为零；
- temperature 有限且低于 critical threshold；
- motor safety 与 transport latch 均未触发。

任一条件不满足都会使该 attempt 失败；最终 configure 失败并走既有反向 rollback。
没有 `0.0`、软限位中点、旧进程 target、旧 Flight target 或磁盘值 fallback，也没有
自动 set-zero。

成功时 `startup_target` 直接使用 `MotorStatus.position_rad`，再写入同一 driver API 的
`loc_ref`。反馈与 target 都是 CyberGear 原生坐标，因此不乘 `motor_signs`；这避免
negative-sign motor 被重复变换。fake regression 同时覆盖配置 sign 为负的 ID4/ID2 和
sign 为正的 ID3/ID1，并证明四台 first target 都严格等于各自 measured position。

首次 target write 成功后，`current_targets`、`desired_targets` 和 target timestamp 同步
提交为该 measured hold value。active 后 Task 6.2.2 的 periodic same-target probe 因而
重发同一 startup hold，而不是回到零。每次 lifecycle configure 都清空 feedback cache
和 per-motor generation，必须从本次新 response 建立 baseline。

正常日志使用“启动保持已从实测位置初始化”，不描述为 zero calibration。

## Compatibility

- **Task 6.2.2 acquisition：** active periodic probe 保持原 owner、generation、latch 和
  lifecycle gates，只把初始 authoritative target 从固定零改为 measured hold。
- **MANUAL：** 首条 operator target 仍按既有 absolute target、soft limit 和统一推进器
  contract 替换 hold。
- **AUTO：** 姿态目标生成、`motor_signs`、gain、速度和软限位未改变。
- **HOME：** 仍是 operator 请求后按既有 HOME speed 向软件零位推进；cold power cycle
  后必须先由 operator 确认姿态并显式 set-zero。
- **set-zero：** `/motors/set_zero` 和键盘 `x` 协议未改变。fake 验证从非零 startup hold
  显式 set-zero 后，measured coordinate、current target 和 desired target 都同步为零。
- **E-STOP / ERROR：** 既有 latch、stop batch、禁止自动恢复和 position-error monitor
  保持；启动 target 与 measured 相同，不再制造虚假的初始大位置偏差。
- **transport / reconnect：** feedback 建立前或初始化中 transport fault 继续 configure
  failure + rollback；runtime reconnect 仍只恢复 transport 并保持 ERROR，不初始化电机、
  不恢复旧 target。
- **Flight：** ControllerState、CommandAuthority、owner reserve/commit/revoke、Flight API、
  bounded verification controller 和 `flight_takeover_enabled=false` 默认值均未改变；旧
  Flight target 不跨 cleanup/reconfigure 复用。
- **fans：** fan subsystem、GPIO12/13、PWM、ESC 和相关配置均未修改。

## Tests

修改前 reproduction：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/imu_cybergear_ros2/test/test_structured_feedback_node.py::test_cold_start_first_position_target_holds_each_measured_position -q
```

旧代码结果：1 failed；measured 为 `{4: 0.85, 3: 0.74, 2: 0.91, 1: 0.42}`，first targets
为 `{4: 0.0, 3: 0.0, 2: 0.0, 1: 0.0}`。修复后同一测试通过。

专项回归：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest -p no:cacheprovider \
  src/imu_cybergear_ros2/test/test_structured_feedback_node.py \
  src/imu_cybergear_ros2/test/test_motor_lifecycle.py \
  src/imu_cybergear_ros2/test/test_motor_safety.py \
  src/imu_cybergear_ros2/test/test_transport_lifecycle.py -q
```

结果：80 passed。覆盖 non-zero/all-four/sign、first target、no-zero fallback、no feedback、
missing/NaN/Inf position、ID mismatch、invalid mode、fault、critical temperature、software
bookkeeping、same-target probe、set-zero、position-error、transport failure、reconnect lock、
first/middle/last rollback、cleanup 和 fresh reconfigure baseline。

规定的完整验证：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/imu_cybergear_ros2/test -q
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
./scripts/ci_software.sh
```

结果：

- manual build：5 packages finished；
- motor pytest：431 passed；
- manual colcon：827 tests、0 errors、0 failures、0 skipped；
- isolated CI：exit 0；safety、whitespace、compile、五包 build 全部通过；motor 431 passed、
  fan 112 passed、Flight + interfaces 256 passed；最终 827 tests、0 errors、0 failures、
  0 skipped；
- test warnings/skipped：无 pytest warning，无 skipped。受限 sandbox 中部分进程内 ROS
  lifecycle 测试会输出本地 RMW/getifaddrs 权限诊断，但不访问硬件且不构成测试失败。

全部验证只使用 pure/fake/mock/in-memory 路径，不是实机验证。

## Hardware Status

```text
Gate A0: PASS
Gate A1: PASS

Task 6.2.2:
SOFTWARE + HARDWARE PASS

Gate B feedback baseline:
PASS

Gate B Flight DRY_RUN:
PASS

Cold-start hold-current fix:
SOFTWARE READY
HARDWARE RETRY REQUIRED

Flight bounded takeover:
PAUSED
```

```text
cold-start hardware retry:
NOT EXECUTED
```

本任务没有启动 hardware node/launch，没有访问 `/dev/*`、真实 serial、SocketCAN、
can10、CyberGear、GPIO12/13、PWM 或 ESC，也没有给 motor/fan 通电。只能报告：

```text
READY FOR COLD-START HARDWARE RETRY
```

## Next Step

```text
Cold-start Hold-current Verification
```

该验证只确认 controller 启动后保持 motor power-on 时的当前位置，不主动移动到零。
通过后 operator 确认机器人处于正确 physical reference posture，显式执行 set-zero，
确认四轴 feedback 接近零，再准备第一次 bounded Flight takeover。不需要重跑完整 Gate A
或旧 Gate B feedback baseline。

该实机步骤必须等待用户单独授权，并重新列出十项带电门槛；本任务未自动执行。

## Git

- HEAD：`f5f58fb88ac5c523f780911e9d3941ad5832a187`；
- branch：`master...origin/master`，无已知 ahead/behind；
- working tree：dirty，包含本 Task 的 source/tests/README/docs 修改，以及任务开始前用户
  已有的 `docs/NEXT_COMMAND.md` 修改；该用户文件保持未编辑；
- `git diff --check`：通过；
- commit/push/tag：未执行；
- 未 checkout/reset/clean；stable tags `v0.3.0/v0.3.1/v0.3.2` 未改变。
