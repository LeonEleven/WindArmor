# 最新反馈：运行期通信断线检测与受控重连

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-07

## 1. 执行结论

- 已完成 USB-CAN 与 SocketCAN 的运行期 transport fault 检测、明确异常类型、
  独立事件通道、connection generation 和 reader 退出语义。
- `reconnect_on_disconnect` 已具有实际运行期语义：`false` 只执行故障响应和关闭，
  `true` 启动最多一个有界、可取消的 transport-only recovery worker。
- 通信恢复后固定进入 `RECONNECTED_LOCKED`，ControllerState 与
  `/motors/control_mode` 继续保持 `ERROR`；不初始化电机、不恢复 MANUAL/AUTO/HOME、
  不恢复机械零点流程，也不重发旧目标。
- 初始连接重试与运行期重连保持分离，既有四电机初始化顺序和事务式回滚保持。
- 新增 53 项 transport/reconnect 相关测试实例；电机包 `359 passed`，风扇关键
  回归 `98 passed`，三包完整 `475 tests, 0 errors, 0 failures, 0 skipped`。
- `./scripts/ci_software.sh` 完整通过。Codex 未运行真实硬件；用户自行完成
  MANUAL/AUTO 实机正常功能回归并报告无问题。
- 用户已授权本任务使用中文 commit 并 push；`docs/NEXT_COMMAND.md` 继续排除在
  提交之外，tag 不变，实际 commit、push 和远端 CI 结果以最终终端汇报为准。

## 2. 开始前 Git 与 CI 基线

- 分支：`master`。
- HEAD：`d97c51ada431fce5dda87bc2d2b7d9bda945dc71`。
- upstream：`origin/master`，同为 `d97c51ada431fce5dda87bc2d2b7d9bda945dc71`。
- 本地领先/落后：`0/0`。
- 开始时唯一工作区修改：`M docs/NEXT_COMMAND.md`，无未跟踪文件。
- `v0.3.0` commit：`c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1` commit：`5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 后 7 个提交；开始时 describe 为
  `v0.3.1-7-gd97c51a-dirty`。
- 只读 `git ls-remote` 确认远端 `master` 和所有 tag 未漂移。
- 开始时最新 GitHub Hosted `WindArmor Software CI` 为 run `31143934086`：
  HEAD `d97c51a`、结论 `success`、全部 step 成功，并有 1 个未过期日志 artifact。

## 3. 修改文件

### 3.1 任务前已有修改

- `docs/NEXT_COMMAND.md`：用户任务说明；本任务未修改、覆盖、暂存或还原。

### 3.2 本任务修改

- `src/imu_cybergear_ros2/imu_cybergear_ros2/transport_recovery.py`：新增 transport
  类型、事件、策略、状态快照和恢复协调器。
- `cybergear_driver.py`：新增明确 transport exception/event/generation，并加固
  USB-CAN、SocketCAN 的读写、connect、close 和 reader 生命周期。
- `imu_motor_controller_node.py`：接入 transport fault、recovery、ROS 状态发布和
  lifecycle 取消/清理。
- `motor_manager.py`：接入 transport ERROR 锁存、普通命令阻断、目标同步、统一
  stop claim 和键盘状态汇总。
- `motor_config.py`、`controller_state.py`：新增重连参数契约与 transport 状态转换
  reason/source。
- `fake_motor_driver.py`：增加纯内存 transport event、generation 和可控 reconnect。
- `test_transport_backends.py`、`test_transport_recovery.py`、
  `test_transport_lifecycle.py`：新增纯软件故障注入测试。
- `test_motor_config.py`、`test_motor_lifecycle.py`：补充参数与 callback 清理回归。
- `imu_cybergear_params.yaml`：补充运行期重连参数及安全语义注释。
- 根 `README.md`、电机包 `README.md`、`AGENTS.md`：同步行为、锁设计、测试能力与
  硬件边界。
- `docs/LATEST_FEEDBACK.md`：按本次实际结果完整覆盖。

## 4. 修改前通信架构

- 初始连接调用链为 `MotorManager.connect_and_init_motors()` →
  `CyberGearDriver.connect_with_retry(max_attempts=5, initial_delay=1.0)`。
- 初始退避倍率为 `1.5`、最大 delay 为 `10.0s`；连接期间持有 driver I/O lock。
- 初始连接成功后按 ID `[4,3,2,1]` 逐台写 run mode、目标速度、零目标并进入运控
  模式；最终失败进入 `ERROR` 并由 configure 事务回滚已触及电机和资源。
- USB reader 原先对串口关闭、`SerialException`、`OSError` 执行 sleep/continue，
  控制层不知道传输已经异常；write 未连接只抛模糊 `RuntimeError`。
- SocketCAN reader 原先对 bus 缺失和 `recv()` 异常执行 sleep/continue；
  `recv(timeout)` 返回 `None` 正确表示无帧。send 异常没有独立 transport 分类。
- `reconnect_on_disconnect` 原先只声明、校验并存入 `MotorSafetyConfig`，没有控制
  任何运行期逻辑。

## 5. Transport error 类型

- 新增 `CyberGearTransportError` 和 `CyberGearDisconnectedError`。
- 串口读写异常、串口关闭、SocketCAN bus 缺失及 send/recv transport failure
  使用明确类型。
- 参数错误、控制算法错误、普通非 transport driver 错误和 feedback callback
  自身异常不会被归类为断线。

## 6. Transport event 通道

- 新增独立 `TransportEvent`/`TransportEventType`，与 `MotorStatus` feedback 及
  feedback-error callback 完全分离。
- 事件包含 backend、operation、message/exception、单调时间、connection
  generation，并可包含 attempt/max attempts。
- 支持 `DISCONNECTED`、`READ_ERROR`、`WRITE_ERROR`、`CLOSE_ERROR`、
  `RECONNECTING`、`RECONNECTED`、`RECONNECT_FAILED`。
- driver 提供 transport callback 注册和清除 API；cleanup 后不保留节点 callback。

## 7. USB-CAN 断线检测

- reader 遇到串口关闭、`SerialException` 或读 `OSError` 时只报告该 generation
  的首个 transport fault，然后退出，不再 sleep/continue 刷同一错误。
- write/flush 异常及关闭状态向调用者抛明确 transport exception，并报告事件。
- reader 不执行 close、退避、reconnect 或电机初始化。
- connect 会替换旧 reader；close 先请求退出、释放串口，再在锁外限时 join。
  reader 未在 timeout 内退出会阻止新连接，避免并存两个有效 reader。

## 8. SocketCAN 断线检测

- `recv()` 抛异常或 bus 缺失会报告当前 generation 的 fault 并退出 reader。
- `recv(timeout)` 返回 `None` 明确保留为正常无帧，不触发 ERROR/reconnect。
- send 异常和 bus 缺失抛明确 transport exception；不会自动重发原命令。
- connect/close 会替换、shutdown 和限时 join 旧 reader；重复 close 幂等。

## 9. 系统级 transport fault 路径

- 首次当前 generation fault 原子锁存 immutable snapshot。
- 立即把 `_init_complete` 置 false，阻断普通命令，停止 MANUAL/AUTO/HOME，令
  motion source 为 `IDLE`，并把 `desired_targets` 同步到最近成功发送的
  `current_targets`。
- recovery fault-response 阶段复用一次性主 stop claim，逐台 best-effort 停止；
  stop 失败不会阻止 ERROR、close 或后续有界重连。
- ControllerState 转为 `ERROR` 并发布 `/motors/control_mode = ERROR`。
- `/motor/status` 继续用 `std_msgs/String` 发布明确 `motor_transport:*` 状态，未新增
  自定义 ROS message。

## 10. 与 command fault 的关系

- transport write exception 同时记录 command 诊断和 transport snapshot。
- command fault、reader fault 和重复 fault 共享 `_fault_stop_batch_claimed`、transport
  latch 与 coordinator lock，因此只有一个主 stop batch、一个真实 ERROR 转换和
  一个 recovery worker。
- 普通非 transport 的位置/速度写错误保持原 command-fault ERROR 语义，不启动
  reconnect。

## 11. reconnect_on_disconnect 语义

- `false`：锁存 ERROR、丢弃运动、best-effort stop、关闭失效 transport，不调用
  connect，不创建 reconnect worker。
- `true`：完成同一故障响应后启动最多一个 recovery worker，只尝试重开 backend
  connection 和 reader。
- 两种配置都不会自动恢复控制或清除故障。

## 12. 重连协调器

- 状态：`IDLE`、`FAULT_LATCHED`、`RECONNECTING`、`RECONNECTED_LOCKED`、
  `FAILED`、`CANCELLED`。
- 首次 reconnect attempt 立即执行；失败间隔按 initial delay、multiplier 和 max
  delay 有界退避。
- backoff 使用 cancel event wait，不使用不可取消长时间 sleep。
- generation 校验忽略旧 reader 晚到事件；并发 request 通过 lock/state 只允许
  一个 worker。
- lifecycle cancel 与正在进行的 connect 竞态时，若 connect 在取消后才成功，
  worker 会再次 close，绝不在 deactivate/cleanup 后遗留重开连接。

## 13. 重连成功后的锁定状态

- recovery state 为 `RECONNECTED_LOCKED`，ControllerState 和公开模式保持 `ERROR`。
- 不设置 `_init_complete=true`，不清除 command/motor/transport fault。
- 不调用 `connect_and_init_motors()`、SDO run mode/速度/位置、`enter_control_mode()`、
  `set_zero()`，不 enable 电机。
- 不重发旧目标，不恢复 MANUAL、AUTO、HOME 或机械零点流程。
- 必须 lifecycle cleanup/configure 或重启节点才能重新初始化并恢复控制。

## 14. 重连失败

- 达到 `reconnect_max_attempts` 后进入 `FAILED`，ControllerState 继续为 `ERROR`。
- 不超过最大次数，不高速无限重试，不自动开始第二轮，也不回到运行态。

## 15. lifecycle 和线程清理

- deactivate、cleanup、shutdown 和 configure 回滚先禁止新 recovery request，设置
  cancel event 并 join worker。
- 然后停止 motion/watchdog/feedback monitor，清 feedback 与 transport callbacks，
  停止 reader、close backend，再销毁 ROS 资源。
- 正常 deactivate 后可正常 re-activate；若已有 transport fault/recovery，则取消后
  re-activate 不会恢复重连或运动。
- cleanup 后可重新 configure，使用新 driver、reader、callback、fault snapshot 和
  coordinator；旧会话不污染新会话。
- 初始化期间若 reader 报 transport fault，配置立即中止并走既有事务式回滚，不把
  它误当运行期重连，也不继续发送初始化命令。

## 16. 锁与并发

- 节点 state lock 只保护内存状态；绝不持有它等待 recovery lock 或 driver I/O lock。
- coordinator lock 只保护状态、attempt、worker 引用；调用 stop/close/connect 和
  join 时不持有该锁。
- driver I/O lock 串行化单次驱动操作；普通命令、stop、close、connect 都不在持有
  node state lock 时等待它。
- backend resource lock 不在 reader join 或 transport callback 分发时持有。
- transport callback 只做状态锁存和提交 worker；worker 才执行 stop/close/connect，
  避免 reader 自己 close/join/reconnect。

## 17. 与 motor health / temperature / feedback timeout 的关系

- 固件 fault bit、临界温度、连续无效反馈继续走 motor safety ERROR，不启动
  transport reconnect。
- warning 温度仍只告警，不自动降速。
- `motor_feedback_timeout_sec` 默认保持 `0.0`。即使显式开启并触发 timeout，没有
  backend transport error 证据时也不启动 reconnect。
- 0x02 parser、fault bit 定义、反馈健康和数值电流能力边界均未修改。

## 18. 急停与机械零点交互

- MANUAL/AUTO 中的 transport fault 进入 ERROR；EMERGENCY_STOP 中发生 transport
  fault 也从急停转为 ERROR。
- `/enable_motor=true`、键盘 `r` 和普通急停恢复不能清除 transport ERROR。
- 机械零点中发生 transport write failure 会立即中止，不执行后续电机或恢复写入；
  重连成功后不会自动继续，必须重新配置后由用户重新明确发起。

## 19. 参数

新增并集中校验：

```yaml
reconnect_on_disconnect: true
reconnect_max_attempts: 30
reconnect_initial_delay_sec: 0.5
reconnect_max_delay_sec: 10.0
reconnect_backoff_multiplier: 1.5
```

- attempts 必须为正整数；delay 必须有限且非负；max delay 不小于 initial delay；
  multiplier 必须有限且不小于 1.0。
- 默认值沿用原 driver 的 30、0.5、10.0、1.5，没有无依据改变退避策略。

## 20. 保持不变的产品行为

- MANUAL/AUTO/HOME 算法、三模式 `4.0 rad/s`、dt/step/tolerance、键盘重复算法和
  AUTO 姿态增益保持。
- motor IDs `[4,3,2,1]`、signs、软限位、默认速度、初始化零目标保持。
- 温度阈值 `80/90°C`、电流保留参数 `5.0A`、feedback timeout `0.0` 保持。
- IMU、统一零点、0x02 大端序 parser、fault bit、feedback health 保持。
- 风扇算法、PWM、GPIO12/GPIO13 未修改。
- 所有既有 ROS 公共话题、服务、参数和消息类型保持；未新增自动恢复服务。

## 21. 测试

- 新增三个 transport/reconnect 测试文件共收集 `47 tests`；在既有配置测试中新增
  6 个非法重连参数实例，合计新增 `53` 项测试实例。
- USB：正常帧、SerialException、OSError、关闭、write/flush、generation、reader
  替换和幂等 close 均覆盖。
- SocketCAN：正常 message、`None`、recv/send exception、bus 缺失、generation、
  reader 替换和幂等 close 均覆盖。
- coordinator：disabled、两次失败后成功、close failure、exhaustion、backoff、
  cancel、connect/cancel race、generation、并发单 worker/stop 均覆盖。
- lifecycle：configure、activate、fault、reconnecting、deactivate/cleanup/shutdown、
  configure again、初始化期断线均覆盖。
- 运动与安全：MANUAL/AUTO/HOME 旧目标、command fault 幂等、非 transport command
  error、急停、机械零点、motor fault、临界温度和 feedback timeout 均覆盖。
- 电机包 targeted/full：`359 passed`。
- 风扇关键回归：`98 passed`。
- 三包 build：`3 packages finished`。
- 三包完整 colcon：`475 tests, 0 errors, 0 failures, 0 skipped`。
- CI infrastructure：`16 passed`。
- `./scripts/ci_software.sh`：完整通过，包括 safety checker、whitespace、compile、
  build、两组 targeted tests、full colcon 和 test-result。
- `git diff --check -- . ':(exclude)docs/NEXT_COMMAND.md'`：通过。
- 完整 `git diff --check`：通过；用户版 NEXT_COMMAND 未产生 whitespace error。
- 首次手工 targeted pytest 因设置 `PYTHONPATH` 时覆盖 ROS 路径而 collection 失败；
  改为追加 ROS `PYTHONPATH` 后通过。该问题不是产品、测试断言或硬件故障。

## 22. 硬件安全声明

- 未执行 `ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
  `scripts/setup_can.sh`。
- 未打开 `/dev/imu_usb`、`/dev/ttyUSB*` 或任何真实串口。
- 未创建、配置或访问真实 SocketCAN/can10，未连接 CyberGear。
- 未写真实 SDO、未 enable/stop/控制真实电机，未进行拔线、断电或带电测试。
- 未启动或 spin IMU、电机、风扇硬件节点。
- 未访问 GPIO12/GPIO13，未创建 Servo、解锁电调、输出 PWM 或控制风扇。
- 构建、fake/mock 测试和本地等价 CI 只属于纯软件验证，不表述为实机验证。
- 上述“未执行”均指 Codex 的操作。用户在软件完成后自行完成 MANUAL/AUTO 实机
  正常功能回归并报告无问题；该结果不包含拔线、断电、transport fault 或重连
  恢复的实机故障注入。

## 23. 提交范围与 Git 状态约束

- 任务开始时分支为 `master`，HEAD/upstream 均为 `d97c51a`，领先/落后 `0/0`。
- `docs/NEXT_COMMAND.md` 仍是任务前用户修改，未被本任务改动或暂存。
- 本次中文提交只包含本任务修改的 13 个既有文件和 4 个新增文件；实际 commit SHA、
  push 和最终状态以终端汇报为准。
- 未执行 tag、checkout、switch、reset、clean、restore、stash、rebase 或 merge。
- `v0.3.0`、`v0.3.1` 及其他 tag 未修改。

## 24. GitHub Hosted CI

- 开始时远端基线 run `31143934086` 为 success；它不包含本地未提交改动。
- 本地等价 CI 已通过；本次 push 触发的新 `WindArmor Software CI` 必须按实际 run
  结论汇报，不能用基线 run 或本地结果代替。

## 25. 未完成或限制

- 无纯软件实现或验收阻塞项。
- 按任务禁令未进行真实串口、真实 CAN、拔线或带电 fault injection；真实 backend
  的设备断开表现、OS connect 延迟和 reader join 时序仍等待另行授权后的实机验证。
- recovery 可即时取消 backoff；若底层 OS open 调用本身正在阻塞，只能在该调用
  返回后完成关闭，软件已覆盖“取消期间晚到成功必须重新 close”的竞态。

## 26. 额外发现

- transport fault 可能在 configure 连接成功、四电机初始化开始前由 reader 到达；
  本任务显式处理了该边界：停止初始化并事务回滚，不启动运行期 worker。
- backend close 若 reader 在 timeout 内不退出，现在会拒绝继续 connect，避免为了
  重连留下两个有效 reader。

## 27. 后续建议

- push 后检查新的 `WindArmor Software CI` 及日志 artifact，明确区分远端结果与
  本地等价 CI。
- 如后续确需真实断线验证，必须重新提出硬件测试方案并满足 AGENTS.md 十项带电
  授权门槛；本任务授权不包含该操作。
