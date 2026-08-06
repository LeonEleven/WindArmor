# 最新反馈：电机命令与生命周期可靠性加固

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-06

## 1. 执行结论

- 四个目标均已完成：位置命令成功提交、速度上限成功提交、初始化事务式回滚、
  lifecycle 统一幂等释放。
- 没有阻塞项和未完成验收项。
- 已完成 fake driver 故障注入、确定性并发测试、电机包针对性测试、上一项风扇
  关键回归、三包纯软件构建和三包完整测试。
- Codex 没有连接或控制任何真实硬件；软件完成后，用户自行启动整套系统并完成
  MANUAL/AUTO 及风扇基本实机功能测试，报告基本正常。
- 用户已在开发、软件验证和上述人工功能测试完成后明确授权中文 commit 并推送
  到 GitHub；提交 SHA 与 push 结果见本次会话最终终端报告。
- `docs/NEXT_COMMAND.md` 是任务开始前已有用户修改，本任务只读且继续保留。

## 2. 开始前 Git 基线

- 分支：`master`。
- HEAD：`8673fb06b5e630d07a49033ee1218147d06c34cb`。
- upstream：`origin/master`。
- upstream 提交：`8673fb06b5e630d07a49033ee1218147d06c34cb`。
- 本地领先/落后：`0/0`。
- 最近提交：`8673fb0 修复：加固风扇控制安全与确定性`。
- `v0.3.0`：annotated tag；tag 对象
  `f7d2a476a1aa7493271e60f202fe53ec5a5218de`，指向提交
  `c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1`：annotated tag；tag 对象
  `ff527a370af7203e96480e56901206bdb978932a`，指向提交
  `5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 之后一个提交：`v0.3.1-1-g8673fb0`；工作区已有修改时
  `git describe` 为 `v0.3.1-1-g8673fb0-dirty`。
- 任务开始时工作区只有：`M docs/NEXT_COMMAND.md`。
- 任务开始时无未跟踪文件。
- 开始前 `git diff --check` 通过。

## 3. 上一项风扇任务状态补充

- 风扇安全与确定性加固已提交到 `master` 并推送到 `origin/master`，对应当前
  HEAD `8673fb0`。
- 用户随后完成了整机实机功能测试，报告功能正常，未出现报错或明显 Bug。
- 根 README 已修正“风扇加固尚未提交、尚未实机测试”的过时描述。
- 文档明确把该记录限定为用户报告的功能验证，不把它夸大为对三种响应曲线、
  消息乱序、超时、异常注入和全部故障恢复路径的穷尽认证。
- 上一项风扇实机验证不构成本任务访问电机、CAN、IMU、GPIO 或风扇的授权。

## 4. 修改文件

### 4.1 任务前已有修改

- `docs/NEXT_COMMAND.md`：用户提供的任务说明；本任务只读，未修改、暂存、
  覆盖或还原。

### 4.2 本任务新增修改

- `README.md`：更新 HEAD 与稳定标签关系、上一项风扇验证事实、电机成功提交、
  ERROR、初始化回滚、统一释放和本轮纯软件验证状态。
- `src/imu_cybergear_ros2/README.md`：说明三类位置、命令故障、初始化事务、
  lifecycle 返回规则和恢复要求。
- `cybergear_driver.py`：增加反馈回调清理入口；SocketCAN close 不再静默吞掉
  shutdown 异常。
- `imu_motor_controller_node.py`：增加 driver factory/sleep 注入、独立驱动 I/O
  锁、配置事务回滚、统一 `_release_resources()` 和逐资源诊断。
- `motor_manager.py`：实现成功后提交、批次失败中止、ERROR 故障路径、初始化
  进度跟踪、best-effort 停止、机械零点和急停恢复一致性。
- `safety_monitor.py`：急停复用统一逐台停止；ERROR 禁止 `/enable_motor=true`
  自动恢复；反馈状态按节点锁快照访问。
- `keyboard_handler.py`：ERROR 禁止键盘恢复；退出停止失败不再静默吞掉。
- `test_motor_manager.py`：迁移旧写失败预期并补齐新 fake 状态字段。
- `test_controller_state.py`：覆盖 ERROR 拒绝远程恢复。
- `test_control_interfaces.py`：同步 cleanup/shutdown 使用统一释放入口的结构断言。
- `fake_motor_driver.py`：新增完全内存化可记录、可阻塞、可按操作/电机/索引失败
  的 fake driver。
- `test_motor_reliability.py`：新增提交一致性、部分批次、初始化、特殊流程和锁边界
  行为测试。
- `test_motor_lifecycle.py`：新增配置失败回滚、再次配置、close/stop/ROS 销毁
  失败和重复清理测试。
- `docs/LATEST_FEEDBACK.md`：完整覆盖为本次反馈。

未修改 `AGENTS.md`、电机 YAML、setup.py、package.xml、bringup 产品代码或任何
风扇产品代码。

## 5. 位置命令提交一致性

修改前，`write_command_target()` 会先更新 `_current_targets` 和时间戳，再尝试
驱动写入；异常后软件会误认为失败命令已经发送。

当前顺序为：

```text
校验有限值并按软限位钳位
→ 保存待发送 command
→ 不持有节点状态锁，在驱动 I/O 锁内执行单次 SDO_TARGET_POS 写入
→ 写入成功
→ 节点锁内提交 current_targets 和 last_target_change_time
→ 清除该电机命令失败计数
```

`current_targets` 的唯一含义是“最近一次成功写入驱动的位置目标”。它不是
`desired_targets`，也不是 `motor_feedback.position_rad`。失败时目标和时间戳
保持旧值，未完成 desired targets 被同步回最近成功目标，HOME 不会被标记完成。
位置误差监控继续比较最近成功命令与真实反馈位置。

多电机部分成功场景按提交边界处理：例如 ID4 成功、ID3 失败时，ID4 保留本次
成功目标，ID3 保留旧目标，ID2/ID1 不再接收本周期普通位置命令；随后进入统一
命令故障路径，HOME 保持未完成。

## 6. 速度上限提交一致性

修改前，速度设置会先更新 `_current_speeds`，再写 `SDO_TARGET_SPEED`。

当前先校验有限值并按既有最小/最大值钳位，再执行驱动写入；只有成功后才更新
`_current_speeds`。失败时保留旧速度和旧时间戳，返回 `False` 并进入统一命令
故障路径。

`change_motor_speed()` 现在返回真实结果：成功日志显示“旧值 -> 实际新值”；
失败日志明确显示“仍保持旧值”，不会声称失败速度已经生效。

## 7. 运行时命令故障处理

以下已配置并运行后的普通异常进入统一路径：

- `SDO_TARGET_POS` 写入异常；
- `SDO_TARGET_SPEED` 写入异常；
- 驱动对象在普通发送时不可用。

用户输入非有限值仍在发送前拒绝，不伪造驱动故障。正常软限位、反馈位置偏差、
IMU watchdog 和用户主动急停保持各自原有语义。

统一路径会先锁存 `_command_fault_active`，停止普通推进、清空重复按键状态、把
desired targets 同步到最近成功目标，然后按配置顺序逐台 best-effort 调用
`stop_motor()`。每台停止分别持有一次 I/O 锁；任一停止失败会记录 motor ID、
reason 和异常，但不阻止后续电机。最后进入 `ControllerState.ERROR` 并通过
`/motors/control_mode` 发布 `ERROR`。

ERROR 不伪造用户急停，也不允许 `/enable_motor=true` 或键盘 `r` 自动恢复。
恢复要求是排除故障后重新配置 lifecycle 或重启节点。

## 8. 锁与驱动 I/O

- 节点 `_lock`：保护 desired/current targets、current speeds、运动源、提交
  时间戳、命令故障状态和运行快照。
- `_driver_io_lock`：串行化 connect、SDO int/float、enter control mode、
  stop、set zero、清回调和 close。
- `_release_lock`：串行化整套资源释放，避免 cleanup/shutdown 重入。

统一锁规则是：不得持有节点 `_lock` 后等待 `_driver_io_lock`。普通位置/速度
写入使用“节点锁取快照 → 释放节点锁 → 单次驱动锁 I/O → 节点锁提交成功结果”。
驱动锁内不执行普通运动 sleep、publisher 销毁、键盘 join 或 lifecycle 大范围
清理。

普通推进不会把整批多电机命令包在一个 I/O 锁中。急停先冻结运动，最多等待
当前单次驱动写入结束，然后可在后续普通命令前取得锁并逐台发送停止。确定性
Event 测试验证了节点锁在阻塞驱动写入期间仍可取得、普通写入互斥串行，以及
急停在当前单次写入结束后取得 I/O 权限。

## 9. 初始化事务与回滚

初始化显式跟踪：

- `init_touched_motor_ids`；
- `init_entered_control_mode_ids`；
- `init_successful_motor_ids`；
- `current_init_stage`。

每台顺序保持不变：`SDO_RUN_MODE` → `SDO_TARGET_SPEED` →
`SDO_TARGET_POS(0.0)` → `enter_control_mode`。速度写入成功后才提交软件速度；
位置写入成功后才提交最近成功目标；进入运控成功后才标记该电机完成。只有全部
电机完成后才设置 `init_complete=true` 并进入 MANUAL_RUNNING。

失败注入覆盖连接、首台运行模式、中间电机速度、中间电机目标、最后电机进入
运控模式。最终失败后停止后续初始化，把状态置为 ERROR，按触及顺序的反向顺序
尝试停止电机，清除未完成运动和全部成功标志，清反馈回调，关闭驱动，销毁全部
已创建 ROS 资源并返回配置 FAILURE。回滚 stop 或 close 失败不会阻止其余清理。

连接最终失败不发送任何电机初始化命令，只清回调、关闭 fake driver 并释放
ROS 资源。测试还验证第一次配置失败完整回滚后，使用无故障的新 fake driver
可以第二次配置成功，没有旧 timer、publisher、subscription、service 或
callback 引用。

启动目标策略没有改变，初始化仍写目标位置 `0.0`；没有改成保持反馈位置。

## 10. lifecycle 资源释放

主节点新增统一 `_release_resources(reason, attempt_motor_stop, motor_ids)`，供：

- 配置失败回滚；
- `on_cleanup()`；
- `on_shutdown()`。

流程依次禁止新控制、停止运动 timer、停止键盘、停止 watchdog、best-effort
停止适用电机、清反馈回调、关闭驱动、销毁 motor mode timer、所有 publisher、
subscription 和 service，最后清除运行对象与软件状态。

资源引用在销毁尝试前置空，因此每个 ROS 资源最多尝试销毁一次；driver 引用在
close 前从节点移除，因此重复 cleanup/shutdown 不会重复 close。单项失败记录
reason、stage、资源类型或电机 ID，汇总失败数，并继续执行所有后续步骤。

返回规则：

- `on_cleanup()`：全部释放成功返回 SUCCESS；任一释放步骤失败返回 FAILURE；
- `on_shutdown()`：同上；
- 配置失败回滚：无论 best-effort 回滚是否全部成功，配置都返回 FAILURE；
- 回滚后的重复 cleanup/shutdown：对已清空资源执行幂等空操作，可返回 SUCCESS。

测试覆盖 cleanup → cleanup → shutdown、配置失败回滚 → cleanup → shutdown、
stop 失败、close 失败和某个 publisher 销毁失败；其他停止和销毁仍全部继续。

## 11. 特殊硬件流程

- 机械零点：每次 stop、set zero、运行模式、目标和 enter 调用均受驱动 I/O 锁
  串行化；只有目标写入和进入运控都成功后才提交该电机成功目标。部分失败返回
  `False`，best-effort 重新停止全部电机并进入 ERROR。
- 急停恢复：先快照最近成功发送目标，不使用未成功的 desired target。任一电机
  恢复失败即停止后续恢复，重新尝试停止全部电机，返回 `False`，运动源保持
  IDLE，状态不会进入 MANUAL_RUNNING。
- 急停：先冻结普通推进，再逐台 best-effort 停止；单台停止失败不会阻止后续
  电机，也不会静默吞掉异常。

## 12. 保持不变的行为

- MANUAL/AUTO/HOME 的 `4.0 rad/s` 软件推进速度、固定周期、dt 上限、单步上限
  和到达容差未变。
- AUTO roll/pitch 增益、死区和计算未变。
- `motor_ids`、方向、软限位和 ID1～ID4 映射未变。
- 初始化仍写 `0.0` 启动目标，机械零点语义未变。
- IMU 四元数校验、roll/pitch 轴向、统一零点和相对姿态语义未变。
- 风扇产品代码、状态机、响应曲线、PWM 参数和 GPIO12/GPIO13 未变。
- ROS 公共话题、服务和消息类型未删除或重命名；只使用既有公开 `ERROR` 值。

## 13. 测试

### 13.1 fake driver 与安全隔离

`FakeMotorDriver` 记录操作顺序、motor ID、SDO index 和数值，可按操作/电机/索引
持续失败，可模拟连接失败、stop 失败、close 失败，并用 Event 确定性阻塞指定
驱动调用。所有 lifecycle 测试通过构造函数注入 fake 和空 sleep；没有构造真实
CyberGearDriver，没有 SocketCAN bus 或串口对象。

纯软件 lifecycle 测试会在 pytest 进程内创建 LifecycleNode 及 ROS publisher、
subscription、service、timer，以验证真实资源释放 API；节点不激活、不 spin，
驱动始终是 fake。ROS 测试日志定向到 `/tmp`。

### 13.2 新增覆盖

- 位置成功后提交、失败保持、软限位、非有限拒绝、HOME 失败和部分批次中止；
- 速度成功后提交、失败保持、日志和原有钳位；
- 普通故障冻结运动、全电机停止、stop 失败继续和 ERROR 不恢复；
- 初始化成功顺序、五类主要失败点、反向停止、close 失败和再次配置；
- cleanup/shutdown 幂等、ROS 销毁失败继续和 callback 清理；
- 急停恢复使用最近成功目标、部分恢复失败重新停止；
- 机械零点恢复成功提交边界；
- 节点锁可用性、I/O 串行化和急停锁优先级。

### 13.3 实际命令与结果

电机包全量针对性测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ROS_LOG_DIR=/tmp python3 -m pytest src/imu_cybergear_ros2/test -q
```

结果：`146 passed`。

风扇上一任务关键回归：

```bash
python3 -m pytest \
  src/windarmor_fan_controller/test/test_fan_control.py \
  src/windarmor_fan_controller/test/test_pwm.py \
  src/windarmor_fan_controller/test/test_fan_keyboard.py \
  src/windarmor_fan_controller/test/test_interface_routing.py -q
```

结果：`98 passed`。

纯软件构建：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

结果：3 个包构建成功。

三包完整测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ROS_LOG_DIR=/tmp colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_bringup
colcon test-result --verbose
```

结果：

- 总数：246；
- passed：246；
- failed：0；
- errors：0；
- skipped：0。

`git diff --check`：通过。

### 13.4 中间诊断记录

- lifecycle 首轮组合测试中，命令/并发部分先得到 `16 passed`，lifecycle 用例
  因沙箱内默认 `~/.ros/log` 只读而在 setup 阶段出现 8 errors；没有进入配置
  逻辑。将测试日志定向到 `/tmp` 后该组 `8 passed`。
- 整个电机包迁移旧源码结构断言时曾为 `142 passed, 1 failed`；失败是旧测试仍
  要求 cleanup/shutdown 直接出现 `stop_motion_timer()`，更新为统一释放入口后
  最终为 `146 passed`。
- 额外裸 `flake8` 全文件扫描返回非零；仓库现有代码和本次沿用风格均触发该
  命令的引号、docstring、长行规则，且未改的 `test_imu_protocol.py` 还有既有
  F401。它不是仓库现有验收命令。对本次变更文件执行 `flake8 --select=E9,F`
  通过，Python `py_compile` 通过。

以上自动测试全部是纯软件验证。其后另有用户执行的基本实机功能测试，范围见
下一节；两者不得混为故障注入验证。

## 14. 文档更新

- 根 README：更新标签/HEAD 关系、上一项风扇用户验证、电机成功提交、ERROR、
  初始化回滚、统一释放和硬件验证边界。
- 电机包 README：明确 desired target、最近成功发送目标、反馈位置、失败语义、
  lifecycle 返回规则和恢复要求。
- `AGENTS.md`：未修改；当前 `v0.3.1` 稳定基线称谓与实际标签一致。
- `docs/LATEST_FEEDBACK.md`：完整覆盖为本次反馈。
- `docs/NEXT_COMMAND.md`：未修改。

## 15. 硬件安全声明

- Codex 在开发和自动验证过程中未启动或 spin 真实硬件节点，未运行 launch，
  未访问 IMU、真实串口、CAN、`can10`、CyberGear、GPIO12/GPIO13、Servo、
  电调或 PWM，也未使用 sudo。
- pytest 内只创建了注入 fake driver 的进程内 LifecycleNode 资源，不连接硬件。
- 软件验证完成后，用户报告自行执行了：

```bash
ros2 launch windarmor_bringup windarmor.launch.py
```

- 用户测试了 MANUAL、AUTO 和风扇功能，结果“基本都正常”。
- 该记录是用户报告的整机正常功能测试；没有提供逐电机测量值、完整持续时间或
  异常注入矩阵，因此不得表述为对 SDO 写失败、初始化中断、stop/close 失败、
  ROS 资源销毁失败或全部安全恢复路径的实机认证。
- Codex 未执行本任务对应的带电或实机故障注入；后续硬件操作仍需重新获得明确
  授权。

## 16. 提交前 Git 状态与授权

- 分支：`master`。
- 提交前 HEAD 为 `8673fb06b5e630d07a49033ee1218147d06c34cb`。
- `docs/NEXT_COMMAND.md` 的任务前用户修改继续保留，未暂存、未覆盖、未还原。
- 用户已明确授权把本任务改动用中文 commit 并推送到 GitHub；本文件将包含在该
  提交中，commit SHA 和最终远端状态以终端最终报告为准。
- 未创建、移动、删除或重建任何 tag；`v0.3.0`、`v0.3.1` 均未改变。

提交前 `git status --short`：

```text
 M README.md
 M docs/LATEST_FEEDBACK.md
 M docs/NEXT_COMMAND.md
 M src/imu_cybergear_ros2/README.md
 M src/imu_cybergear_ros2/imu_cybergear_ros2/cybergear_driver.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py
 M src/imu_cybergear_ros2/test/test_control_interfaces.py
 M src/imu_cybergear_ros2/test/test_controller_state.py
 M src/imu_cybergear_ros2/test/test_motor_manager.py
?? src/imu_cybergear_ros2/test/fake_motor_driver.py
?? src/imu_cybergear_ros2/test/test_motor_lifecycle.py
?? src/imu_cybergear_ros2/test/test_motor_reliability.py
```

其中 `docs/NEXT_COMMAND.md` 的 diff 仍为任务开始时的 `1249 insertions, 968
deletions`；其余为本任务修改。tracked diff 统计与三个新增未跟踪测试文件以
终端最终报告为准。

## 17. 额外发现

- 没有发现需要越过本任务范围顺带修改的其他产品问题。
- 沙箱环境的默认 ROS 日志目录不可写；测试已在命令和 fixture 中显式使用
  `/tmp`，不影响产品运行逻辑。
- 仓库没有统一采用裸 `flake8` 当前加载插件的全量风格规则；本任务未进行无关
  大范围格式化。

## 18. 后续建议

- 若后续确需电机实机故障注入或带电验证，必须作为独立任务重新报告十项授权
  信息并等待用户明确同意；本任务不自动进入该阶段。
- 正常功能已经由用户初步验证；后续可按实际需要单独设计可控、低风险的通信
  断开或 lifecycle 故障验证，但不能从本次“基本正常”推断全部异常路径已验证。
