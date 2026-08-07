# 最新反馈：电机反馈健康、故障位与温度保护加固

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-07

## 1. 执行结论

- 已完成电机反馈来源、合法性、故障位、温度和新鲜度的纯软件安全链加固。
- 任意已配置电机的非零固件故障位、临界温度、连续达到限制的无效反馈，以及
  显式启用后的反馈超时，都会锁存系统级故障、停止全部电机并进入 `ERROR`。
- 严重故障不会被下一帧正常反馈、温度回落、键盘 `r`、
  `/enable_motor=true`、MANUAL/AUTO/HOME 自动恢复；恢复要求受控 lifecycle
  重新配置或重启。
- 反馈 timeout 框架已实现，但默认 `0.0`（关闭强制超时）。原因是代码和现有
  协议实现不能证明电机空闲且没有新目标命令时仍持续周期上报。
- 0x02 反馈没有真实数值 `current_a`；没有从 torque 或其他字段推导电流。
  实际过流保护来自电机固件的过流 fault bit。
- 用户自行实机操作暴露了 0x02 四个 `uint16` 的端序错误：旧 parser 把合理的
  `35.9/35.3/34.6 °C` 解析成 `2636.9/2483.3/2304.1 °C`。公共 parser 已改为
  大端序，position、speed、torque、temperature 同步修正。
- 机械零点流程在反馈安全故障锁存后不再继续恢复运控或输出虚假成功日志。
- 3 个包构建成功；电机包最终 `306 passed`；风扇关键回归 `98 passed`；三包
  完整测试 `406 tests, 0 errors, 0 failures, 0 skipped`。
- Codex 未运行或 spin 任何硬件节点，未访问真实硬件。修正后用户再次自行完成统一
  launch、机械零点和手动控制实机复测，并报告未再出现无效反馈或其他问题。

## 2. 开始前 Git 基线

- 分支：`master`。
- HEAD：`80391d107d9727dad556c05f8df3bc97d2306f8b`。
- upstream：`origin/master`，同为
  `80391d107d9727dad556c05f8df3bc97d2306f8b`。
- 本地领先/落后：`0/0`。
- 最近提交：`80391d1 加固：完善电机配置契约与状态转换确定性`。
- `v0.3.0` commit：`c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1` commit：`5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 后 3 个提交；开始时 describe 为
  `v0.3.1-3-g80391d1-dirty`。
- 任务开始前唯一工作区修改为 `M docs/NEXT_COMMAND.md`，无未跟踪文件；该文件
  是用户任务说明，本任务未修改、暂存、覆盖或还原。

## 3. 修改文件

### 3.1 任务前已有修改

- `docs/NEXT_COMMAND.md`：用户任务说明，原样保留。

### 3.2 本任务产品代码与配置

- `motor_health.py`：新增不依赖 ROS/硬件的反馈合法性、故障分类、温度判断、
  连续无效计数、本地新鲜度与不可变故障快照核心。
- `safety_monitor.py`：接入健康决策、限频诊断、反馈 timer lifecycle、严重故障
  入口，并修正急停不得清除反馈保护。
- `motor_manager.py`：统一反馈安全故障锁存、普通命令阻断、目标同步、全电机
  best-effort stop、ERROR 转换和并发 stop 批次仲裁；零点流程在锁存后立即中止。
- `controller_state.py`：新增稳定的故障位、临界温度、超时和无效反馈原因，以及
  `DRIVER_FEEDBACK` 来源。
- `motor_config.py`、`imu_motor_controller_node.py`：声明、预校验和应用新增参数，
  管理健康会话资源并输出数值电流能力边界提示。
- `cybergear_driver.py`：两个后端均增加 feedback callback 异常诊断；异常不会
  杀死读取线程，后续 callback 继续执行，cleanup 清空回调；公共 0x02 parser
  将四个 `uint16` 按大端序解析。
- `imu_cybergear_params.yaml`：新增反馈合法性/新鲜度参数及准确注释；受保护默认
  参数未改变。

### 3.3 测试和文档

- 新增 `test_motor_health.py`、`test_motor_safety.py`、
  `test_motor_feedback_callbacks.py` 和 `test_cybergear_feedback_parser.py`。
- 更新 `fake_motor_driver.py`、`test_controller_state.py`、
  `test_motor_config.py`、`test_motor_lifecycle.py` 和
  `test_state_call_sites.py`。
- 更新根 `README.md`、电机包 `README.md` 和本文件。
- 未修改 `AGENTS.md`、风扇产品代码或 bringup 产品代码。

## 4. 当前反馈协议能力

- `MotorStatus` 全部字段为：`motor_id`；`raw_position`、`raw_speed`、
  `raw_torque`、`raw_temp`；`position_rad`、`speed_rad_s`、`torque_nm`、
  `temperature`；`mode`、`fault_flags`、`timestamp`。
- 0x02 帧 8 字节数据实际包含大端 uint16 位置、速度、力矩和温度；29-bit CAN ID
  包含电机 ID、2-bit mode 和 6-bit fault flags。用户现场数值的逐字节反推与此
  一致；SDO 发送字段具有不同布局，本次没有做无依据的全局端序替换。
- `timestamp` 在公共 parser 中以 `time.monotonic()` 生成，仅用于诊断；强制
  新鲜度使用反馈回调本地记录的单调接收时刻。
- USB-CAN 和 SocketCAN 后端均由后台线程被动读取并过滤 0x02，然后使用同一
  parser 和回调语义。
- 当前代码没有主动状态查询，也不能证明反馈属于可靠周期主动上报还是命令响应；
  尤其不能保证空闲且无新目标命令时持续反馈。
- 0x02 没有数值安培电流字段，仓库也没有经过协议验证的其他 `current_a` 来源。

## 5. 反馈合法性

- 未配置 motor ID 的反馈只限频 warning，不写入 `_motor_feedback`、不刷新时间、
  不改变保护或全局状态。
- position、speed、torque、temperature、timestamp 必须为有限数值；position、
  speed 和 torque 必须位于 0x02 协议量程，温度必须位于 `[-40, 200] °C` 的
  解析后物理合理范围，timestamp 必须非负。
- mode 只接受 0/1/2；fault flags 只允许 bit0～bit5。
- 单个无效帧被拒绝且增加逐电机连续计数；合法帧在触发前清零计数。默认连续
  3 帧无效触发系统级 `ERROR`。无效帧不会覆盖最近合法反馈或刷新新鲜度。
- `ERROR` 后合法帧不会清除全局 latch、首次故障快照或 protection flag。

## 6. 电机故障位保护

- bit0 欠压：`MOTOR_FAULT_UNDERVOLTAGE`。
- bit1 过流：`MOTOR_OVERCURRENT_FAULT`。
- bit2 过温：`MOTOR_OVERTEMPERATURE_FAULT`。
- bit3 磁编码、bit4 HALL 编码：`MOTOR_FAULT_ENCODER`。
- bit5 未标定：`MOTOR_FAULT_UNCALIBRATED`。
- 多 bit：记录全部故障名称和原始 mask，使用 `MOTOR_FAULT_MULTIPLE`。
- 上述任一非零 bit 都立即停止全部电机并进入 `ERROR`。重复或并发帧只执行一次
  主 stop batch；后续触发电机仍会锁存自己的 protection flag。

## 7. 温度保护

- `temperature < 80.0 °C`：正常接受。
- `80.0 <= temperature < 90.0 °C`：按电机限频 warning，在状态汇总标记；不
  自动降速、不修改三模式速度和 `default_speed`、不停止电机、不进入 ERROR。
- `temperature >= 90.0 °C`：一条完整合法反馈立即停止全部电机、锁存并进入
  `ERROR`。
- 固件过温 bit 独立立即生效，不受数值温度影响；临界后温度回落不自动恢复。

## 8. 电流保护能力边界

- 固件过流 fault bit 已实际接入立即系统级保护。
- `motor_current_limit_a: 5.0` 继续保留和校验，但没有真实 `current_a`，因此不
  参与任何数值阈值比较；configure 输出一次明确能力边界 warning。
- 未新增电流 SDO 或 parser；未从 `torque_nm`、`raw_torque`、速度或其他字段
  推导电流，也未假定固定转矩常数。

## 9. 反馈新鲜度

- 每台电机记录首次合法反馈状态、最近本地单调接收时间和反馈年龄；反馈对象自带
  timestamp 不作为超时依据。
- 新增 `motor_feedback_timeout_sec: 0.0`、
  `motor_feedback_startup_grace_sec: 3.0`、
  `motor_feedback_check_rate_hz: 10.0`。
- 默认 timeout 关闭，因为无法证明空闲周期反馈；关闭时仍可在状态汇总查看年龄。
- 显式设置正 timeout 后，每次 activate 建立新会话；startup grace 结束仍缺首帧，
  或已反馈电机年龄严格超过 timeout，都会停止全部电机并进入 `ERROR`。恰好等于
  timeout 不触发。
- 无效帧不刷新时间；deactivate 停止检查，cleanup/shutdown 幂等销毁 timer；
  重新 configure/activate 不继承旧反馈时间或连续无效计数。

## 10. 统一安全故障路径

1. 在节点状态锁内原子锁存首个不可变故障快照；
2. 设置触发电机 protection flag，并阻断新的普通位置/速度命令；
3. 清除 MANUAL/AUTO/HOME 未完成运动，将 `desired_targets` 同步到最近成功发送的
   `current_targets`；
4. 释放状态锁后，按 `motor_ids` 对全部电机执行 best-effort stop；
5. 一台 stop 失败会记录但不阻止其他电机；
6. 使用稳定 reason/source 转换到 `ERROR`，状态回调发布公共 `ERROR`；
7. 转换被拒绝时仍保留 latch 和停止结果，并输出高优先级错误。

急停、命令故障和反馈安全故障共享原子主 stop batch 仲裁。反馈线程不会在节点
状态锁内等待 driver I/O 锁；重复或并发事件不会反向获取锁或重复刷 stop 命令。
设置机械零点这一直接流程也会在每个步骤前后检查 latch；锁存后立即失败返回，
不再发送后续 `set_zero`、SDO 或进入运控命令，也不会打印“全部电机机械零点已设置”。

## 11. 急停和恢复交互

- 正常、未伴随反馈安全故障的 `EMERGENCY_STOP` 仍可在真实恢复流程成功后显式
  进入 MANUAL，并允许以后独立的急停批次。
- 急停不再无条件清除 `_motor_protection_flags`。
- 急停期间收到严重反馈会锁存并转换到 `ERROR`。
- latch 存在时 `/enable_motor=true` 和键盘恢复均失败；只有 lifecycle 重新配置
  或重启建立干净健康状态。

## 12. 状态转换原因

新增稳定原因：`MOTOR_FEEDBACK_FAULT`、`MOTOR_FAULT_UNDERVOLTAGE`、
`MOTOR_OVERCURRENT_FAULT`、`MOTOR_OVERTEMPERATURE_FAULT`、
`MOTOR_FAULT_ENCODER`、`MOTOR_FAULT_UNCALIBRATED`、
`MOTOR_FAULT_MULTIPLE`、`MOTOR_CRITICAL_TEMPERATURE`、
`MOTOR_FEEDBACK_TIMEOUT`、`MOTOR_INVALID_FEEDBACK`。反馈来源为
`DRIVER_FEEDBACK`，新鲜度超时来源为 `WATCHDOG`。

## 13. 保持不变的行为

- MANUAL/AUTO/HOME 推进算法、三模式 `4.0 rad/s`、dt/step/tolerance、手动按键
  增量和重复字符算法均未改变。
- AUTO roll/pitch 映射、deadband、`1.0` 增益、软限位和 HOME 目标未改变。
- `default_speed: 10.0` 和初始化写入 `0.0` 的策略未改变。
- `motor_ids`、`motor_signs`、`motor_limits_min/max` 保持受保护默认值。
- IMU 四元数、轴向、统一零点、公共 ROS 名称/类型均未改变。
- 风扇产品代码、状态机、曲线、PWM、GPIO12/GPIO13 均未修改。
- 未增加运行期自动重连或自动温度降速。

## 14. 测试

### 14.1 新增覆盖

- pure health：全部数值/量程/mode/fault/timestamp 非法矩阵、未知 ID、连续无效计数、
  温度五个边界、六类 fault 和多 bit、电流能力边界。
- fake clock：timeout 0、startup grace、缺少首帧、逐电机年龄、等于/超过 timeout、
  无效帧不刷新、deactivate 和新激活重置。
- fake driver：全电机 stop、单台 stop 失败、命令阻断、目标同步、ERROR 发布语义、
  普通急停恢复、急停中严重反馈、lifecycle 重配置。
- 确定性并发：双电机同时故障、fault 与临界温度、在途目标写与反馈故障、反馈
  故障与急停；均不使用 `sleep()` 猜测同步。
- 两个 backend callback：异常可诊断、读取分发继续、后续 callback 继续、cleanup
  清空反馈和错误 callback。
- 公共 parser：四个 0x02 `uint16` 大端解析、现场三组室温字节回归、短帧拒绝。
- 零点流程：初始停止后注入反馈安全锁存，断言不再发送零点、SDO 或运控恢复命令，
  且不输出成功日志。

### 14.2 实际命令与结果

- `colcon build --symlink-install`：3 packages finished。
- 电机包最终：`306 passed`。
- 风扇关键回归：`98 passed`。
- 三包完整：`406 tests, 0 errors, 0 failures, 0 skipped`。
- `python3 -m py_compile src/imu_cybergear_ros2/imu_cybergear_ros2/*.py`：通过。
- `git diff --check -- . ':(exclude)docs/NEXT_COMMAND.md'`：通过。
- 全仓 `git diff --check`：未通过；仅因用户保留的 `docs/NEXT_COMMAND.md` 附加
  实机日志含 10 处行尾空格。任务文档禁止修改该文件，因此原样保留并明确报告。

中间电机全量首轮为 `298 passed, 1 failed`：既有测试的 `SimpleNamespace` fake
缺少新增 stop 仲裁复位接口，导致成功急停恢复路径 `AttributeError`。补齐 fake
接口后最终电机包 `300 passed`。这不是产品运行失败，也未访问硬件。

## 15. 文档更新

- 根 README 更新实际 HEAD 与 `v0.3.1` 关系、系统级 fault/温度保护、默认
  timeout 依据、电流能力边界、0x02 端序纠正和纯软件验证范围。
- 电机包 README 补充 MotorStatus、0x02 物理量、合法性、fault bit、温度、
  新鲜度、锁存、恢复、callback、端序和电流边界。
- YAML 注释与参数验证及运行语义一致；受保护默认值未改变。
- 本文件已按模板完整覆盖；`docs/NEXT_COMMAND.md` 未修改。

## 16. 硬件安全声明

- 未执行 `ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
  `scripts/setup_can.sh`。
- 未启动或 spin 真实 IMU、电机、风扇节点或 hardware launch。
- 未打开 `/dev/imu_usb` 或任何真实串口。
- 未创建或连接真实 SocketCAN bus，未访问或配置 `can10`。
- 未构造用于真实连接的 CyberGear driver，未初始化/使能/控制电机，未写真实
  SDO。
- 未访问 GPIO12/GPIO13，未创建 Servo，未初始化/解锁电调，未输出 PWM，未
  控制风扇。
- lifecycle 测试使用内存 fake driver 且不 spin；backend callback 测试只构造
  未连接对象并直接测试内存分发方法。
- 用户自行执行的整机操作访问了真实 IMU、CAN、电机和风扇；首次日志暴露端序
  错误，修正后再次复测统一 launch、机械零点和手动控制并报告正常。这些命令均
  不是 Codex 执行的，也不构成后续硬件授权。

## 17. 最终 Git 状态

- 分支仍为 `master`；HEAD/upstream 仍为
  `80391d107d9727dad556c05f8df3bc97d2306f8b`，领先/落后仍为 `0/0`。
- `docs/NEXT_COMMAND.md` 保留任务前用户修改且未暂存。
- 用户已在修正后实机复测并审查结果后，明确授权使用中文 commit 并推送到
  GitHub；提交 SHA 和 push 结果以本次会话最终终端报告为准。
- 未 checkout、switch、reset、clean、restore、stash、rebase 或 merge。
- `v0.3.0`、`v0.3.1` 未创建、移动、删除或重建。
- 最终详细 status 和 diff 统计以本次会话终端报告为准。

## 18. 未完成或受协议限制的内容

- 没有真实数值电流字段，`motor_current_limit_a` 尚不能形成 5.0 A 软件阈值保护；
  只有固件过流 bit 已生效。
- 无法由当前代码证明空闲周期反馈，因此强制 feedback timeout 默认不启用；启用
  前仍需协议依据或受控实机确认。
- 未执行真实 fault bit、过温、过流、反馈中断、无效帧、CAN 断线、stop 失败或
  异常恢复实机注入。
- 大端 parser 已由用户在正常机械零点和手动控制路径中实机复测；零点流程在真实
  安全故障并发锁存时的中止语义，以及 fault/过温/超时等故障注入仍未实机验证。
- 全仓 `git diff --check` 仍被禁止修改的 `docs/NEXT_COMMAND.md` 行尾空格阻塞；
  除该文件外检查通过。

## 19. 额外发现

- 两个驱动后端原先静默吞掉 feedback callback 异常，可能隐藏安全回调问题；现已
  在本任务范围内增加错误回调诊断，同时保留读取线程存活和后续 callback 规则。
- 原反馈故障只跳过单台电机并在正常帧后自动清除；该行为不符合系统级锁存语义，
  现已替换为全局 ERROR 路径。
- 0x02 parser 原先以小端读取所有 `uint16`。这不仅造成温度假高，也会同时扭曲
  position、speed 和 torque；现已统一修正并增加精确字节向量测试。
- 现场日志还显示安全故障已经进入 `ERROR` 后，零点流程仍继续并打印成功；现已
  在本任务安全路径范围内修复并以 fake driver 验证。

## 20. 后续建议

- 如需默认启用 feedback timeout，应先取得官方周期上报依据，或在重新满足硬件
  授权门槛后验证两种后端在静止、无 SDO 目标时的实际反馈周期。
- 如需数值安培保护，应使用官方验证的真实字段或 SDO，统一两个后端 parser 与
  单位测试；不得从力矩推导。
- 本任务不执行、也不建议顺带开始运行期自动重连任务。
