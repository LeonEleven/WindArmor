# 最新反馈：电机配置契约与状态转换确定性加固

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-06

## 1. 执行结论

- `docs/NEXT_COMMAND.md` 规定的状态转换契约、集中配置校验、废弃参数策略、
  私有耦合清理、测试和文档目标均已完成。
- 状态请求现在返回 `CHANGED`、`NO_CHANGE` 或 `REJECTED`，真实转换携带稳定的
  reason/source 并保存不可变快照；非法转换和同状态请求均无状态回调副作用。
- 所有关键参数在 driver factory、反馈回调和 ROS 运行资源创建前完成纯函数
  校验。代表性非法配置测试明确断言上述创建入口均为 0 次调用。
- 旧 ID、方向和软限位标量参数非默认时明确失败；USB 旧端口/波特率保留有警告
  的 fallback，新参数始终优先。
- 3 个包构建成功；电机包 `237 passed`；风扇关键回归 `98 passed`；三包完整
  测试 `337 tests, 0 errors, 0 failures, 0 skipped`。
- Codex 未运行或 spin 任何硬件节点，未运行 launch，也未访问真实硬件。软件完成
  后，用户自行启动整个系统并完成 MANUAL/AUTO 功能实机测试。
- 用户已在审查和实机功能测试后明确授权使用中文 commit 并推送到 GitHub；提交
  SHA 和 push 结果以本次会话最终终端报告为准。

## 2. 开始前 Git 基线

- 分支：`master`。
- HEAD：`aa22ea3dfe5214c8091a4905aa42a98e82db77dd`。
- upstream：`origin/master`，提交同为 `aa22ea3dfe5214c8091a4905aa42a98e82db77dd`。
- 本地领先/落后：`0/0`。
- 最近提交：`aa22ea3 修复：加固电机命令一致性与生命周期可靠性`。
- `v0.3.0` 指向提交 `c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1` 指向提交 `5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 后两个提交；开始时 describe 为
  `v0.3.1-2-gaa22ea3-dirty`。
- 任务开始前工作区唯一修改是 `M docs/NEXT_COMMAND.md`，无未跟踪文件。
- 该任务说明的原有 diff 为 `1155 insertions, 959 deletions`，本任务未修改、
  暂存、覆盖或还原该文件。

## 3. 修改文件

### 3.1 任务前已有修改

- `docs/NEXT_COMMAND.md`：用户提供的任务说明；保持原样。

### 3.2 本任务产品代码与配置

- `controller_state.py`：显式合法转换表、结果/原因/来源枚举、不可变最近转换
  快照、幂等语义、非法转换拒绝和受控回调注册。
- `motor_config.py`：新增不可变分层配置对象及完整纯函数解析/校验。
- `imu_motor_controller_node.py`：重排 configure 顺序，在任何驱动或 ROS 资源
  创建前校验；迁移 lifecycle 状态原因；使用公开回调注册接口。
- `motor_manager.py`：迁移初始化、命令故障、HOME、机械零点等状态调用点，检查
  关键结果，并在状态汇总中显示最近转换。
- `safety_monitor.py`：移除私有状态锁访问；区分 watchdog、话题/服务急停、远程
  disable 和显式恢复；恢复状态提交失败时重新停止电机。
- `keyboard_handler.py`：区分键盘模式、急停和恢复来源，并检查转换结果。
- `imu_cybergear_params.yaml`：更新校验、废弃参数和未生效参数边界注释；所有受
  保护默认值保持不变。

### 3.3 测试与文档

- `test_controller_state.py`：覆盖全部合法转换、关键非法转换、幂等、回调、快照、
  并发读取和注册规则。
- `test_motor_config.py`：覆盖默认值、所有主要非法配置、废弃参数和 USB fallback。
- `test_state_call_sites.py`：覆盖 watchdog、键盘模式、话题/服务/键盘急停和键盘
  恢复来源。
- `test_motor_lifecycle.py`：增加配置失败零副作用、fallback 单次警告和 shutdown
  原因测试。
- `test_motor_manager.py`、`test_motor_reliability.py`：迁移状态调用签名并断言 HOME、
  命令故障、连接/初始化和机械零点原因。
- `test_control_interfaces.py`：确认产品模块不再访问状态管理器私有锁/回调字段。
- 根 `README.md`、电机包 `README.md`：更新 Git 基线、配置与状态契约、废弃参数、
  用户既有功能验证和硬件验证边界。
- `AGENTS.md`：修正“没有 fake driver/lifecycle 测试”的过时描述，未削弱任何
  硬件安全或 Git 规则。
- `docs/LATEST_FEEDBACK.md`：完整覆盖为本次反馈。

## 4. 状态转换表

全部同状态请求均允许，但只返回 `NO_CHANGE`，不算真实转换。真实合法转换为：

```text
UNINITIALIZED
  → INITIALIZING
  → ERROR
  → SHUTTING_DOWN

INITIALIZING
  → MANUAL_RUNNING
  → EMERGENCY_STOP
  → ERROR
  → SHUTTING_DOWN

MANUAL_RUNNING
  → AUTO_RUNNING
  → EMERGENCY_STOP
  → ERROR
  → SHUTTING_DOWN

AUTO_RUNNING
  → MANUAL_RUNNING
  → EMERGENCY_STOP
  → ERROR
  → SHUTTING_DOWN

EMERGENCY_STOP
  → MANUAL_RUNNING（仅 EXPLICIT_ESTOP_RECOVERY）
  → ERROR
  → SHUTTING_DOWN

ERROR
  → SHUTTING_DOWN

SHUTTING_DOWN
  → 无其他状态
```

`UNINITIALIZED → ERROR` 保留用于配置前异常语义，并由真实 `StateManager` 行为
测试覆盖。公开模式仍只使用 `MANUAL`、`AUTO`、`EMERGENCY_STOP`、`DISABLED`
和 `ERROR`，消息类型与 QoS 未变。

## 5. 转换结果、原因和来源

- `TransitionOutcome`：`CHANGED`、`NO_CHANGE`、`REJECTED`。
- `TransitionResult`：包含 outcome、旧状态、请求状态、reason 和 source。
- 原因覆盖配置开始/成功/失败、驱动连接失败、电机初始化失败、用户模式切换、
  HOME、watchdog、键盘/话题/服务急停、远程停用、显式恢复、位置/速度写失败、
  机械零点失败和 shutdown。
- 来源覆盖 lifecycle、motor manager、safety monitor、keyboard、service、topic 和
  watchdog。
- 初始化完成、急停、恢复、命令 ERROR 和 shutdown 等关键调用方都检查转换结果；
  被拒绝时记录高优先级错误，不继续报告虚假成功。

## 6. 幂等与非法转换

- `STATE_X → STATE_X` 返回 `NO_CHANGE`，不更新序号/快照，不调用状态变化回调，
  不停止 HOME，也不清除普通运动。
- 非法请求返回 `REJECTED`，原状态保持不变；结果和错误日志记录 old/new、reason
  和 source，最近真实转换快照保持不变。
- `ERROR` 不能回到 MANUAL/AUTO；`SHUTTING_DOWN` 不能离开；急停恢复必须使用
  显式恢复原因。
- 回调在状态锁外分别执行。回调异常会被记录，不回滚已经原子提交的状态，也不
  阻止另一个回调按规则执行。

## 7. 最近转换快照

- `TransitionRecord` 是 frozen dataclass，字段包括 sequence、old/new state、
  reason、source 和 monotonic timestamp。
- 只有真实变化递增 sequence 并替换快照；幂等或拒绝请求不覆盖。
- 读取在状态锁下返回完整不可变对象，测试覆盖外部修改失败、可控单调时钟以及
  多线程并发读取不会观察到部分更新。
- 键盘 `p` 状态汇总现在附带最近转换序号、状态、原因、来源和单调时间；没有
  新增 ROS message 或 topic。

## 8. 私有耦合清理

- 主节点通过 `register_stop_auto_zero_callback()` 完成受控一次性注册，不再写
  `_stop_auto_zero_callback`。
- 首次注册成功；相同回调重复注册是明确幂等；不同回调覆盖被拒绝并有测试。
- `SafetyMonitor` 使用公共 `is_in()`、状态属性和结构化 `transition_to()`，不再
  访问 `_state_lock`；锁没有被公开。
- 产品代码结构测试确认上述私有访问已经消失。

## 9. 配置对象和校验顺序

新增 frozen 配置层：

- `MotorChannelConfig`；
- `MotorCommunicationConfig`；
- `MotorControlConfig`（复用既有 `MotionParameters`）；
- `MotorSafetyConfig`；
- `MotorRosInterfaceConfig`；
- `MotorKeyboardConfig`；
- `MotorNodeConfig`。

configure 顺序为：

```text
读取 ROS 参数
→ 兼容参数处理
→ build_motor_node_config() 完整纯函数校验
→ 保存已验证配置和初始化内存状态
→ 创建 driver
→ 创建子模块并注册 fake/真实驱动反馈回调
→ 创建 ROS 资源
→ 连接和初始化电机
→ 非零 watchdog 才创建定时器
```

代表性重复 ID、非默认废弃参数和非法告警限频均验证 driver factory、publisher、
subscription、service、timer 调用次数为 0；driver、callback、watchdog、keyboard
和电机命令均未创建或启动。`watchdog_timeout_ms=0` 明确保留禁用语义。

## 10. 电机列表校验

- 至少一台电机，八个列表长度必须完全一致；错误列出全部实际长度。
- motor ID 必须为唯一的 `1～127` 整数；master ID 为 `0～255` 且不得冲突。
- 名称去除首尾空白后非空且唯一。
- sign 必须是有限的 `+1.0` 或 `-1.0`。
- 软限位必须有限、`min < max`，并处于驱动明确的 `[-4π, +4π]` 协议范围。
- control axis 只接受 `roll_left`、`roll_right` 和 `pitch`。
- 前后键必须是全局唯一的小写单字符；固定控制键、相同前后键和所有数字选择键
  均拒绝，不能再静默覆盖 `_key_to_motor`。
- 默认 `[4,3,2,1]`、方向和软限位完全保持原值。

## 11. 通信、ROS 和安全参数校验

- 后端只接受 `socketcan_hat`、`usb_can_serial`；SocketCAN 要求非空 channel 和
  bustype；USB 要求最终端口非空、波特率为正整数。本任务不检查设备是否存在。
- 五个可配置话题拒绝空白、空值和明显非法名称，不创建 ROS 实体做校验。
- 发布频率、IMU 零点新鲜度、键盘频率、位置误差阈值和告警限频均为正有限值。
- 既有 motion/gain 校验继续复用；deadband 非负，roll/pitch sign 严格为 +/-1。
- watchdog 是非负整数，0 禁用；温度阈值有限且 critical 严格大于 limit；电流、
  位置误差和告警限频阈值必须为正。
- 当前温度、电流和 `reconnect_on_disconnect` 参数只被解析校验，尚未直接实现
  独立温度降速/停机、电流暂停或运行期重连算法；YAML 和 README 已明确这一点。

## 12. 废弃参数兼容

- 旧 motor ID、sign、`m1_min/m1_max` 至 `m4_min/m4_max` 保持默认时允许配置。
- 任一旧标量非默认时立即 `ValueError`，错误同时给出旧参数名和新的列表参数名。
- `usb_port` 非空、`usb_baud` 非零时始终优先，即使 legacy 参数不同也无警告。
- 仅当新端口为空或新波特率为 0 时使用 `motor_port`/`motor_baud`；解析后的端口和
  波特率仍须合法，并合并输出一次明确废弃警告。
- lifecycle fallback 测试注入 `FakeMotorDriver`，确认传给 factory 的解析结果，
  没有打开串口。

## 13. 保持不变的行为

- MANUAL/AUTO/HOME 软件推进算法、速度、dt 上限、单步上限和容差未变。
- AUTO roll/pitch 映射、死区、增益和统一目标推进器未变。
- 电机 ID、方向、软限位、初始化 `0.0` 目标和 HOME 目标未变。
- IMU 四元数、轴向、相对姿态和统一零点算法未变。
- `/e_stop`、看门狗、软限位、停用、ERROR 和安全退出机制未删除或弱化。
- 风扇产品代码、状态机、曲线、PWM 和 GPIO12/GPIO13 未修改。
- ROS 公共话题、服务、类型和模式值未删除或重命名；没有新增自动恢复路径。

## 14. 测试

### 14.1 新增覆盖

- 全合法转换表、关键非法转换、ERROR/SHUTTING_DOWN 终态、急停恢复原因；
- 幂等/拒绝副作用、锁外回调、回调异常、序号/单调时间/不可变和并发快照；
- 默认配置及空列表、长度、ID、名称、sign、软限位、轴、键、后端、话题、频率、
  watchdog、温度、电流、位置误差和告警限频非法矩阵；
- 配置失败零 driver/ROS/runtime 副作用；
- 废弃参数迁移、新参数优先、legacy fallback 和单次警告；
- watchdog、HOME、键盘切换、三种急停、恢复、命令故障、初始化和 shutdown 来源；
- 既有命令提交、初始化回滚、lifecycle、并发锁、IMU 和运动回归。

### 14.2 实际命令与最终结果

纯软件构建：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

结果：3 个包构建成功。

电机包全量：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ROS_LOG_DIR=/tmp python3 -m pytest src/imu_cybergear_ros2/test -q
```

结果：`237 passed`。

风扇关键回归：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/windarmor_fan_controller/test/test_fan_control.py \
  src/windarmor_fan_controller/test/test_pwm.py \
  src/windarmor_fan_controller/test/test_fan_keyboard.py \
  src/windarmor_fan_controller/test/test_interface_routing.py -q
```

结果：`98 passed`。

三包完整测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ROS_LOG_DIR=/tmp colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_bringup
colcon test-result --verbose
```

结果：

- 总数：337；
- passed：337；
- failed：0；
- errors：0；
- skipped：0。

Python `py_compile` 通过；最终 `git diff --check` 通过。

### 14.3 中间诊断

- 风扇回归首轮命令未加载工作区 setup，在 pytest 收集阶段以
  `ModuleNotFoundError: windarmor_fan_controller` 结束；没有执行测试逻辑。
- 加载 ROS 和 `install/setup.bash` 后同一测试集最终 `98 passed`。这属于测试
  环境加载问题，不是产品失败，也未触发任何硬件访问。

全部自动结果均为纯软件验证，不是实机验证。

## 15. 文档更新

- 根 README 已更新当前 HEAD 与 `v0.3.1` 关系、上一项已提交/推送状态、用户既有
  功能验证、配置契约、状态契约和废弃参数行为。
- 电机包 README 已补充分层配置、列表/键位/后端规则、watchdog 0、温度关系、
  合法转换、原因/来源、fallback 和未生效参数边界。
- YAML 注释与实际校验一致；受保护默认值未改。
- AGENTS 仅修正 fake driver/lifecycle 覆盖描述，安全门槛不变。
- 本文件已完整更新；`docs/NEXT_COMMAND.md` 未修改。

## 16. 硬件安全声明

- 未执行 `ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
  `scripts/setup_can.sh`。
- 未启动或 spin 真实 IMU/电机/风扇节点。
- 未打开 `/dev/imu_usb` 或任何真实串口，未创建真实 SocketCAN bus，未访问或
  配置 `can10`。
- 未构造用于连接硬件的真实 CyberGear driver，未初始化、使能或控制电机，未
  写真实 SDO。
- 未访问 GPIO12/GPIO13，未创建 Servo，未解锁电调，未输出 PWM，未控制风扇。
- lifecycle 测试创建的 ROS 资源不 spin、不激活硬件，driver 始终为内存 fake。
- 软件完成后，用户报告自行启动了整个系统并完成 MANUAL/AUTO 功能实机测试。
  这是用户执行的正常功能验证，不是 Codex 硬件操作，也不代表配置拒绝、非法
  状态转换、SDO、初始化、stop/close、资源销毁等故障路径完成实机注入。
- 带电故障注入、极限和标定测试仍未执行；上述用户测试不能替代这些验证，也不
  构成 Codex 后续硬件操作授权。

## 17. 最终 Git 状态

- 分支仍为 `master`；HEAD 仍为
  `aa22ea3dfe5214c8091a4905aa42a98e82db77dd`，upstream 未变。
- `docs/NEXT_COMMAND.md` 仍保留任务前 `1155/959` diff，未被本任务修改或暂存。
- 工作区包含本任务产品、测试和文档修改，以及 3 个本任务新增文件：
  `motor_config.py`、`test_motor_config.py`、`test_state_call_sites.py`。
- 用户已明确授权把本任务改动使用中文 commit 并推送到 GitHub；任务前已有的
  `docs/NEXT_COMMAND.md` 继续排除在暂存和提交之外。实际 commit SHA、push 和
  提交后工作区状态以本次会话最终终端报告为准。
- 未执行 checkout、switch、reset、clean、restore、stash、rebase 或 merge。
- `v0.3.0`、`v0.3.1` 未创建、移动、删除或重建。
- 最终详细 `git status --short --branch` 和 diff 统计以终端最终报告为准。

## 18. 额外发现

- 原 YAML 把温度阈值描述为自动降速/停机、把电流阈值描述为暂停目标，但当前
  产品代码没有直接使用这些数值实现对应算法；本任务仅集中校验并修正文档，未
  越界新增保护算法。
- `reconnect_on_disconnect` 同样保持兼容声明并校验布尔类型，但当前控制节点尚未
  用它切换运行期重连策略。
- 没有发现需要越过任务边界顺带修改的其他产品问题。

## 19. 后续建议

- 本任务提交后继续保留未暂存的 `docs/NEXT_COMMAND.md` 用户修改；后续是否单独
  处理该文件仍由用户决定。
- 若后续要让温度、电流或运行期重连参数真正参与保护，应作为独立控制安全任务，
  明确故障语义、锁边界、mock 测试和硬件授权，不应从“已校验”推断“已生效”。
- 任何真实 CAN、串口、带电电机或风扇验证仍必须重新满足仓库十项授权门槛。
