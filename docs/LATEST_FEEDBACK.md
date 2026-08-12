# 最新反馈：v0.4.0 Structured State Integration & DRY_RUN Runtime

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-12

## 执行结论

v0.4.0 Task 2 已完成：现有电机合法 feedback cache 现在周期生成结构化只读
`/motors/feedback`；IMU、motor、fan、system observations 可按本地 monotonic
时间聚合为不可变 `FlightState`；Flight Runtime 可通过 factory 加载并周期调用纯
Python controller，严格校验 state/command，并只发布 DRY_RUN status/preview。

Runtime 始终保持 command authority `NONE`、generation `0`、
`flight_control_active=False` 和 `actuation_allowed=False`。本任务没有实现 Task 3
authority/arming，也没有 actuator adapter、publisher、service client 或 dispatch。

## Scope

### 修改文件

- 根文档：`README.md`、`docs/FLIGHT_CONTROL_ARCHITECTURE.md`、
  `docs/FLIGHT_CONTROL_API.md`、`docs/LATEST_FEEDBACK.md`；
- CI：`scripts/ci_software.sh`；
- interfaces：`src/windarmor_interfaces/CMakeLists.txt`、
  `msg/FlightRuntimeStatus.msg`、`msg/FlightCommandPreview.msg`、
  `test/test_message_contract.py`；
- motor package：`README.md`、`package.xml`、
  `config/imu_cybergear_params.yaml`、`motor_config.py`、
  `imu_motor_controller_node.py`、`safety_monitor.py`、新增
  `structured_feedback.py`，以及 `test_motor_config.py`、
  `test_motor_lifecycle.py`、`test_structured_feedback.py`、
  `test_structured_feedback_node.py`；
- flight package：`package.xml`、`setup.py`、新增
  `config/flight_control.yaml`、`launch/flight_control_dry_run.launch.py`、
  `algorithms/flight_controller.py`；
- flight runtime：新增 `runtime/__init__.py`、`config.py`、
  `controller_loader.py`、`observations.py`、`imu_adapter.py`、
  `motor_adapter.py`、`fan_adapter.py`、`state_aggregator.py`、`node.py`；
- flight tests：新增 `test/__init__.py`、`runtime_helpers.py`、
  `test_runtime_config.py`、`test_imu_adapter.py`、`test_motor_adapter.py`、
  `test_fan_adapter.py`、`test_state_aggregator.py`、
  `test_controller_loader.py`、`test_runtime_node.py`、
  `test_runtime_safety_boundary.py`，并更新 `test_import_boundary.py`。

任务开始前已有的 `docs/NEXT_COMMAND.md` 修改被完整保留，本任务未覆盖或重写。
开始与反馈生成前 SHA-256 均为
`8e71c11a9c06c7610c48c0c2b7c757d0929b32f267eac0a7f74ae5679ddda449`。

### ROS message / topic

- 新增 `FlightRuntimeStatus.msg`：结构化表达 DRY_RUN mode、state sequence、state/
  command validation、controller inhibited、safe-stop 和 last error；
- 新增 `FlightCommandPreview.msg`：normal preview 使用完整平行 motor arrays 和 fan
  presence；safe-stop preview 使用空 motor arrays、`fan_commands_present=false`；
- 新增实际 publisher `/motors/feedback`
  (`windarmor_interfaces/msg/MotorFeedbackArray`)；旧 `/motor/status` 保留；
- 新增只读 `/flight_control/dry_run/status` 与
  `/flight_control/dry_run/command_preview`；
- 没有修改现有 IMU、motor mode、fan 或 E-STOP public interface 行为。

### Config / launch / dependency

- motor observer 参数：structured topic、`10.0 Hz` publish rate、`0.5 s` observer
  freshness；
- flight config：`50.0 Hz` control rate、required motor names、IMU/motor/fan/state
  freshness、fan observer `800–2200 us`、controller factory 和全部只读 topic；
- standalone `flight_control_dry_run.launch.py` 只启动 Runtime；未修改
  `windarmor_bringup` 默认路径；
- `imu_cybergear_ros2` 增加 `windarmor_interfaces` dependency；
- `windarmor_flight_control` 增加 `rclpy`、ROS messages、launch 和
  `windarmor_interfaces` dependencies，并安装 config/launch/console entry point；
- `windarmor_interfaces` 与 `windarmor_flight_control` 保持 `0.4.0`；
  `imu_cybergear_ros2` 保持 `0.3.2`。

## Structured Motor Feedback

- publisher rate：默认 `10.0 Hz`；observer freshness：默认 `0.5 s`；
- 每帧按配置顺序包含全部 `motor_names`/`motor_ids`；
- 无反馈 entry 使用 `has_feedback=false`、全部 `*_valid=false`，物理量 presence
  不成立，ROS 默认零不可解释为反馈；
- `valid`：数据来自现有 `MotorHealthCore` 已接受并写入的完整合法 cache；
- `fresh`：本地 monotonic 接收年龄不超过 observer freshness；
- `healthy`：valid、observer fresh、firmware fault 为零、低于 critical temperature，
  且本 lifecycle 会话没有全局 motor safety fault 锁存；
- fault/critical temperature 在全局锁存提交前的短并发窗口内也不会被发布为
  healthy；正常新反馈不会清除已锁存 fault/ERROR；
- publisher 只复制 cache 和本地 receive-time map，没有注册额外 callback、没有
  driver read/query/call，也没有发送任何 motor command；
- publication exception 在 timer 内捕获，不退出 feedback/transport reader，也不
  改变 safety trip 或 ERROR transition；
- `motor_feedback_timeout_sec` 默认值仍为 `0.0`，与 observer freshness 完全分离。

## StateAggregator

### 数据源

- IMU：`/imu/data_raw`、`/imu/status`、`/imu/relative_roll_pitch`、
  `/imu/zero_generation`；
- motor：`/motors/feedback`、`/motors/control_mode`；
- fan：`/fans/status_pwm`、`/fans/enabled`、`/fans/control_state`；
- system trigger observation：`/e_stop`。

ROS callback 只进行 validate/convert/cache update；controller 只由固定 control timer
调用。每 tick 只构造一次 frozen `FlightState`，mapping 会复制并冻结，后续 callback
不会改变旧 snapshot。sequence 由 Runtime 单调递增；snapshot time、`dt` 和所有
freshness 使用本地 monotonic 时间，ROS header stamp 不参与 control `dt`。

### Adapter 语义

- IMU quaternion 必须有限且可归一化，再计算 roll/pitch/yaw；raw 与 relative
  roll/pitch 必须使用完全相同的正 source stamp 才能配对。duplicate、倒退、
  mismatch 不会被静默拼接；
- 合法 raw IMU 可作为 `connected=True` 的正向证据；disconnected/reconnecting
  设置 false；unknown status 不伪造 connected；zero generation 未收到时保持
  `None`；
- Flight motor age 为
  `publisher_reported_age + local_elapsed_since_message_receipt`；Runtime 使用独立
  `flight_motor_freshness_sec`，不把 publisher `fresh` 当作算法 freshness；
- motor array 严格拒绝 missing/unknown/duplicate logical name、duplicate CAN ID、
  presence conflict、NaN/Inf 和 negative age；API 不含 `current_a`；
- fan applied PWM 仅按配置范围线性映射到 `[0.0, 1.0]`，不 clamp，不代表 RPM 或
  thrust；长度、数值或范围非法时立即 unknown；
- stale fan output 变为 `output_known=false/applied_command=None`；stale fan enabled、
  fan state 和 motor mode 变为 `None`；system/fan control state 始终一致；
- E-STOP startup 为 `None`。现有 `/e_stop` 是 trigger channel，不是权威 clear
  readback；收到 `True` 后永久锁存为 `True`，收到 `False` 或 silence 都不会推断
  已解除；
- `required_inputs_fresh = IMU fresh AND all configured motors fresh`；fan/system
  observation 不属于该传感器 freshness，但也绝不被解释为可 actuation。

## Runtime

- controller contract：`module.path:create_controller`，factory 接收
  `tuple[str, ...]` required motor names，返回具有 `reset()`/`update()` 的纯
  controller；不使用 `eval()`；
- 默认 factory 为
  `windarmor_flight_control.algorithms.flight_controller:create_controller`；其中
  `0.0` 仅是 API 示例测试值，不声明真实机械中位；
- startup 加载 controller 后只调用一次 `reset()`；control timer 默认 `50.0 Hz`，
  `dt` 使用相邻 tick 的真实 monotonic 差；
- 每个 snapshot 固定使用 authority `NONE`、generation `0`、
  `flight_control_active=False`、`actuation_allowed=False`；不会为 normal preview
  伪造 authority；
- 默认 controller 因真实 DRY_RUN system state 返回 payload-free safe-stop；normal
  preview 只在明确 test controller/fake controller 测试中产生；
- loader、reset、update、state validation、command validation 或非法 monotonic
  `dt` 会锁存本地 inhibited、清除 controller 引用、停止后续 update；sensor 恢复
  不自动恢复，需重启 Runtime；
- safe-stop 在 Task 2 只发布无 payload preview，不 revoke authority、不执行安全
  stop、不缓存或重发 previous target；正式 safe-stop authority 语义留给 Task 3。

## Safety

- Flight Runtime 只有 status 与 preview 两个 publisher；没有 actuator publisher；
- 没有 service/client 创建路径，不调用 enable、zero、reset 或 recovery service；
- 没有 `MotionSource.FLIGHT`，没有 fan `FLIGHT_CONTROL` source，没有 authority
  grant、ARMING、ACTIVE 或 takeover；
- 没有运行真实 ROS hardware node/launch，没有访问 `/dev/*`、IMU 串口、CAN、
  SocketCAN、USB-CAN、CyberGear、GPIO12/GPIO13、PWM 或电调；
- 没有改变 v0.3.2 MANUAL/AUTO/HOME、watchdog、软限位、E-STOP、ERROR、motor
  feedback/temperature safety、fan arbitration 或安全退出；
- ERROR 不自动恢复；transport reconnect 仍只恢复通信，不初始化电机、不恢复
  控制、不重发旧目标；
- `motor_feedback_timeout_sec` 默认仍为 `0.0`；受保护 motor IDs、signs、limits
  分别仍为 `[4,3,2,1]`、`[-1,1,-1,1]`、
  `[-1.57,-1.57,-1.57,0]`、`[0,1.57,1.57,1.57]`。

以上结果全部是纯软件/fake/mock/local ROS object 验证，不是实机验证或硬件安全
认证。真实 motor/fan/IMU 验证均未执行，原因是本任务未授权硬件操作且 Task 2
没有 actuator path。

## Tests

执行的主要命令与最终结果：

```bash
python3 -m py_compile <motor/flight runtime and test Python files>
PYTHONPATH=src/imu_cybergear_ros2 python3 -m pytest \
  src/imu_cybergear_ros2/test/test_motor_config.py \
  src/imu_cybergear_ros2/test/test_structured_feedback.py -q
```

- compile：通过；首轮 motor config/structured pure 专项：`63 passed`。

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest \
  src/windarmor_flight_control/test/test_runtime_config.py \
  src/windarmor_flight_control/test/test_imu_adapter.py \
  src/windarmor_flight_control/test/test_motor_adapter.py \
  src/windarmor_flight_control/test/test_fan_adapter.py \
  src/windarmor_flight_control/test/test_state_aggregator.py \
  src/windarmor_flight_control/test/test_controller_loader.py -q
```

- adapters/aggregator/loader pure 专项：`50 passed`。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest src/windarmor_flight_control/test/test_runtime_node.py -q
python3 -m pytest src/imu_cybergear_ros2/test/test_structured_feedback.py \
  src/imu_cybergear_ros2/test/test_structured_feedback_node.py -q
```

- runtime node fake/in-memory 最终：`8 passed`；
- structured motor publisher 最终：`7 passed`（5 pure + 2 fake lifecycle）；
- runtime node 首轮曾有 1 项测试断言失败：ROS 生成的 float sequence 是
  `array('d')` 而不是 Python list；只调整测试 presence 断言后通过，runtime 行为
  未修改。

```bash
python3 -m pytest src/imu_cybergear_ros2/test -q
```

- 首轮：`351 passed, 16 failed`。原因是旧 pure `FakeNode` 没有新增 observer
  receive-time dict，feedback callback 在进入既有 trip 前触发 `AttributeError`；
- 修复为与现有 warning flags 相同的惰性内存初始化，并更新新增 publisher 后的
  lifecycle 资源数量断言；故障位、温度、并发、E-STOP/ERROR 与 cleanup 专项
  `36 passed`，随后全量通过；
- 隔离 CI 最终 motor package：`368 passed`。

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_interfaces \
  windarmor_flight_control windarmor_bringup
colcon test-result --verbose
```

- build：`5 packages finished`；
- workspace：`599 tests, 0 errors, 0 failures, 0 skipped`。

```bash
./scripts/ci_software.sh
```

- CI safety：通过；Git whitespace：通过；Python compile：通过；
- isolated build：`5 packages finished`；
- motor：`368 passed`；fan：`98 passed`；flight/interfaces：`108 passed`；
- full colcon：`599 tests, 0 errors, 0 failures, 0 skipped`。

最终验证没有 pytest warning summary、error、failure 或 skipped。测试过程只创建
fake driver、pure model 和本地 ROS objects；没有 spin 或 launch 真实硬件节点。

Task 2 没有遗留实现阻塞。进入 Task 3 前仍必须建立独立 authority/arming 设计和
权威 E-STOP clear readback；当前 `/e_stop=False` 明确不能作为解除依据。真实
actuator 接入、motor 空闲反馈持续性和所有带电行为仍等待后续任务及单独硬件授权。

## Git 状态（反馈生成时）

- HEAD：`d359711d2a27cb9ded5634f3ade912453220c873`；
- 分支：`master`；本地 tracking ref 显示与 `origin/master` ahead/behind `0/0`；
- 本任务实现/验证阶段执行 commit：否；
- 本任务实现/验证阶段执行 push：否；
- 本任务实现/验证阶段执行 tag：否；
- 远端状态在本任务内核验：否；只检查本地 tracking ref，未执行网络查询；
- annotated `v0.3.2` tag object 为
  `29ae0bbcfa22206686cb86f5896a08bccfcb5a37`，仍指向
  `398ea9b035929f745be79c4d75cfd99d73c77702`；
- 稳定 tag 未创建、移动、删除或重建；
- working tree 包含本 Task 2 的未暂存修改/新增文件，以及任务开始前用户已修改的
  `docs/NEXT_COMMAND.md`；没有 staged 文件。
