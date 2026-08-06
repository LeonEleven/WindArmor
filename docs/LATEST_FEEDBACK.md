# 最新反馈：风扇控制安全与确定性加固

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-05

## 1. 执行结论

- 五项风扇控制安全与确定性问题均已完成代码修复。
- 五项问题均已增加或迁移对应纯软件回归测试。
- 没有阻塞项和未完成验收项。
- 已完成风扇针对性测试、三包纯软件构建和三包完整测试。
- 没有运行任何 ROS 2 节点或 launch。
- 没有访问 IMU、CAN、GPIO、PWM、Servo、电调、电机或风扇。
- 开发与验证完成后，用户已明确授权将本任务改动提交并推送到 GitHub。
- 未创建、移动、删除或重建任何 tag；v0.3.1 继续指向任务开始时的基线提交。

## 2. 开始前基线

- 分支：master
- HEAD：5d7bd0fbf0acac3be4f2354a616d109928d5091d
- upstream：origin/master
- upstream 提交：5d7bd0fbf0acac3be4f2354a616d109928d5091d
- 本地领先：0
- 本地落后：0
- v0.3.1 标签类型：annotated tag
- v0.3.1 标签对象：ff527a370af7203e96480e56901206bdb978932a
- v0.3.1 指向提交：5d7bd0fbf0acac3be4f2354a616d109928d5091d
- HEAD 与 v0.3.1：完全一致
- 任务开始时无未跟踪文件

任务开始前已经存在：

    M docs/LATEST_FEEDBACK.md
    M docs/NEXT_COMMAND.md

其中 NEXT_COMMAND.md 是用户提供的本任务说明，本任务没有修改、暂存或覆盖。
LATEST_FEEDBACK.md 在任务开始时也已有上一项会话反馈修改；本任务按明确要求
将它完整覆盖为当前最新反馈。

## 3. 修改文件

### 3.1 任务前已有修改

- docs/NEXT_COMMAND.md：用户任务说明，本任务只读。
- docs/LATEST_FEEDBACK.md：上一项会话反馈；本任务按要求完整覆盖。

### 3.2 本任务新增修改

- AGENTS.md：只把稳定发布称谓从 v0.2.0 修正为实际 v0.3.1；硬件安全和 Git
  限制未改。
- README.md：更新 v0.3.1 基线、两个新服务、显式急停复位、手动授权和停止
  基线、唯一控制 tick、未知模式及看门狗语义。
- src/windarmor_fan_controller/config/fan_params.yaml：说明命令看门狗必须为
  正有限数值，并更新兼容参数注释。
- src/windarmor_fan_controller/launch/fans.launch.py：更新手动模式兼容参数
  说明。
- fan_control.py：集中实现显式授权、安全状态和唯一正常推进入口。
- fan_command_manager.py：分离观察回调与控制 tick，注册两个新服务，并为核心
  状态访问增加互斥保护。
- fan_node.py：在 GPIO 初始化前严格校验 command_timeout_sec。
- pwm.py：增加正有限超时纯函数校验，并在 FanCommandGate 中重复防御。
- fan_keyboard.py：订阅 /fans/control_state，安全状态下清除本地旧 PWM，并在
  停止基线建立前禁止用户调节。
- test_fan_control.py：覆盖五项问题、授权、复位、停止基线和状态转换。
- test_pwm.py：覆盖全部非法超时及 fake initializer 零调用。
- test_fan_keyboard.py：覆盖状态变化后的旧值清理和调节门控。
- test_interface_routing.py：覆盖新服务、唯一控制 tick 和硬件初始化顺序。
- docs/LATEST_FEEDBACK.md：本文件。

没有修改 setup.py、package.xml、电机代码、IMU 代码或 bringup 架构。

## 4. 问题一：控制定时器唯一推进

### 原因

原管理器的姿态、模式、enabled、零点、手动命令、急停和服务回调都会调用
同一个评估函数；该函数进入核心 step，再进入 AUTO slew。一个控制周期中的
多条消息因此可能多次推进 PWM。

### 修改方案

- 核心增加 control_tick(now)，作为唯一正常输出推进入口。
- 管理器只有 _control_tick() 调用 core.control_tick()。
- 普通消息和服务回调只校验输入、更新观察缓存、授权、请求或状态。
- 普通回调不调用 step 或 control_tick，不推进正常 MANUAL 输出或 AUTO slew。
- 控制定时器每次只计算一次目标、最多执行一次 slew，并发布一次正常
  /fans/command_pwm。

### 安全立即停止

核心 force_safe_stop() 会清除 AUTO、MANUAL 授权和所有旧命令，直接把命令
置为双路停止值并设置立即停止标志。管理器普通回调可以消费该标志并立即发布
停止命令，不等待下一个控制 tick。

急停、底层 disabled、未知模式、姿态或零点失效，以及在控制 tick 检出的关键
状态超时都使用该路径。重复安全事件是幂等停止，不会恢复旧目标。

### 参数语义

control_rate_hz=20.0、rise_step_pwm_us=10 和 fall_step_pwm_us=20 的默认值
未改变，语义仍是每个控制定时周期允许的 PWM 步长，不是 PWM/s。

## 5. 问题二：急停显式复位

原实现以本地接收序号和 enabled、motor mode 心跳自动解除急停，延迟或乱序
旧心跳可能被误认为恢复状态。

当前行为：

- /e_stop=true 立即停止并锁存急停。
- 急停清除 AUTO 请求、MANUAL 授权、手动缓存、姿态缓存、AUTO 目标和未完成
  输出。
- /e_stop=false 只更新观察输入，不解除锁存。
- enabled、motor mode、姿态、零点和手动 PWM 心跳都不能解除锁存。

新增服务：

    /fans/reset_e_stop
    std_srvs/srv/Trigger

复位前检查：

- 急停当前已锁存；
- 明确观察到 /e_stop=false；
- /fans/enabled 存在、新鲜且为 true；
- /motors/control_mode 存在、新鲜且为 MANUAL 或 AUTO。

失败会返回 success=false 和具体原因。成功后：

- 急停锁存清除；
- 输出保持双路停止值；
- AUTO 未请求；
- MANUAL 未授权；
- 姿态和全部旧命令保持清空；
- 状态进入 MANUAL_DISARMED，等待用户重新选择控制路径。

该服务不会调用底层 /fans/enable，也不会启动风扇。

## 6. 问题三：AUTO 故障后的手动授权

核心新增 manual_armed 和本次授权后的停止基线状态。

新增服务：

    /fans/manual_enable
    std_srvs/srv/SetBool

/fans/manual_enable 与 /fans/enable 不同：

- /fans/enable 是底层硬件输出接受状态；
- /fans/manual_enable 只改变命令管理器是否允许 MANUAL。

启用 MANUAL 前检查：

- 急停未锁存且观察输入不是 true；
- 底层 enabled 新鲜且为 true；
- motor mode 新鲜且为 MANUAL 或 AUTO；
- AUTO 未请求、未等待、未活动。

授权成功后进入 MANUAL_WAITING_FOR_NEUTRAL，清除全部旧手动值。此状态：

- 非停止双路命令被拒绝；
- 单路命令被拒绝；
- 必须先收到本次授权之后的双路停止命令；
- 建立停止基线后进入 MANUAL_WAITING；
- 之后的新鲜合法非停止命令才可在控制 tick 生效。

AUTO 成功启用、AUTO 主动关闭、AUTO 故障、急停、disabled、未知模式、关键
状态超时、姿态或零点失效，以及 manual_enable=false 都会取消手动授权并立即
停止。

fan_keyboard 现在订阅 /fans/control_state。AUTO、SAFE_STOP、急停、disabled、
MANUAL_DISARMED 和 MANUAL_WAITING_FOR_NEUTRAL 会把本地左右值清回停止值并
禁止调节。进入 MANUAL_WAITING 后，只有新的用户调节输入才能产生非停止值。
核心仍独立强制同样约束，因此其他外部 PWM 发布者不能绕过。

## 7. 问题四：未知电机模式

收到未知、空白、格式非法或不受支持模式时：

- _motor_mode 设置为 None；
- _motor_mode_at 设置为 None；
- AUTO 请求清除；
- MANUAL 授权清除；
- 手动缓存和时间戳清除；
- 输出立即置为停止；
- 进入 SAFE_STOP，或在急停已锁存时保持 EMERGENCY_STOP；
- 管理器记录清晰错误日志。

之后的新合法模式只更新观察状态，不恢复 AUTO、MANUAL 或旧 PWM。控制必须
重新调用适用的 reset_e_stop、manual_enable 或 auto_enable 服务。

## 8. 问题五：看门狗参数

command_timeout_sec 现在必须能转换为 float，且严格大于零并为有限数值。

明确拒绝：

- 0；
- 负数；
- NaN；
- 正 Inf；
- 负 Inf；
- 非法字符串或其他无法转换的值。

fan_node 使用 initialize_after_timeout_validation() 先调用纯校验，再允许调用
_initialize_gpio。测试以 fake initializer 断言全部非法值时调用次数为零。

FanCommandGate.check_timeout() 也调用相同纯校验形成双层防御，不再把非正值
解释为关闭看门狗。没有新增看门狗关闭开关。

## 9. 状态机和接口变化

新增状态：

- MANUAL_DISARMED：输出停止，MANUAL 未授权；
- MANUAL_WAITING_FOR_NEUTRAL：MANUAL 已授权，等待本次授权后的双路停止基线。

继续保留：

- SAFE_STOP；
- MANUAL_WAITING；
- MANUAL_ACTIVE；
- AUTO_WAITING；
- AUTO_ACTIVE；
- DISABLED；
- EMERGENCY_STOP。

新增服务：

- /fans/reset_e_stop，std_srvs/srv/Trigger；
- /fans/manual_enable，std_srvs/srv/SetBool。

现有话题、服务名称和消息类型均保留。公共 /fans/pwm、/fans/left/pwm 和
/fans/right/pwm 现在需要显式 MANUAL 授权；单路命令不能建立停止基线。

兼容参数 require_motor_mode_for_manual 仍保留。根据本任务安全要求，显式
manual_enable=true 始终要求新鲜合法 motor mode，因此独立 fans.launch.py
不再能仅靠后台 PWM 心跳进入手动输出。这是本次有意的安全流程变化。

## 10. 保持不变的行为

- 风扇 activity 仍使用左右独立 max() 合成，没有相加或使用 hypot。
- linear、smoothstep 和 quadratic 数学定义未改变。
- 默认响应曲线仍为 smoothstep。
- fan_deadband_on_deg 仍为 5.0。
- fan_deadband_off_deg 仍为 3.0。
- fan_full_scale_deg 仍为 45.0。
- fan_stop_pwm_us 仍为 800。
- fan_start_pwm_us 仍为 1200。
- fan_auto_max_pwm_us 仍为 1400。
- control_rate_hz 仍为 20.0。
- rise_step_pwm_us 仍为 10。
- fall_step_pwm_us 仍为 20。
- max_pwm_us 仍为 2200。
- GPIO12、GPIO13 和左右风扇映射未改变。
- PWM 单位未改变。
- 电机 AUTO 增益、方向、软限位和统一推进器未改变。
- IMU 姿态和统一零点算法未改变。

## 11. 测试

### 测试安全检查

运行前静态检查了测试及导入链：

- 核心测试只调用纯 Python 状态逻辑；
- 看门狗初始化测试使用 fake initializer；
- 没有实例化 DualFanController 或 FanCommandManager；
- 没有构造 LGPIOFactory、Servo 或电调；
- 键盘测试使用 os.openpty 和 __new__，不构造 ROS Node；
- 接口和 launch 测试只读取源码及 AST；
- 电机测试继续使用既有 fake 或纯函数；
- 没有访问 IMU、CAN、GPIO 或真实串口。

### 风扇针对性测试

命令：

    source /opt/ros/jazzy/setup.bash
    source install/setup.bash
    python3 -m pytest +      src/windarmor_fan_controller/test/test_fan_control.py +      src/windarmor_fan_controller/test/test_pwm.py +      src/windarmor_fan_controller/test/test_fan_keyboard.py +      src/windarmor_fan_controller/test/test_interface_routing.py -v

最终结果：98 passed。

实现迁移中的首轮组合测试为 80 passed、9 failed；9 项失败均为旧测试仍期待
默认手动授权或心跳自动解除急停。迁移旧测试后为 89 passed，补强硬件初始化
顺序和前置条件测试后最终为 98 passed。

### 纯软件构建

命令：

    source /opt/ros/jazzy/setup.bash
    colcon build --symlink-install

结果：3 个包构建成功。

### 完整纯软件测试

命令：

    source /opt/ros/jazzy/setup.bash
    source install/setup.bash
    colcon test --packages-select +      imu_cybergear_ros2 windarmor_fan_controller windarmor_bringup
    colcon test-result --verbose

结果：

- 总数：219；
- passed：219；
- failed：0；
- errors：0；
- skipped：0。

git diff --check：通过。

以上均为纯软件测试，不是实机验证。

## 12. 文档更新

- README.md 已更新发布基线、状态、服务、恢复顺序、手动停止基线、唯一控制
  tick、未知模式和看门狗规则。
- fan_params.yaml 已说明 command_timeout_sec 必须正有限且不可关闭看门狗。
- fans.launch.py 已说明 require_motor_mode_for_manual 的兼容性。
- AGENTS.md 只把稳定发布称谓修正为实际 v0.3.1；硬件安全规则、十项授权门槛、
  Git 禁止操作和真实硬件限制均未修改。
- docs/LATEST_FEEDBACK.md 已完整覆盖为本次反馈。

## 13. 硬件安全声明

- 未启动真实 IMU。
- 未访问 /dev/imu_usb。
- 未访问任何真实串口。
- 未访问或配置 CAN。
- 未初始化 CyberGear。
- 未控制任何电机。
- 未访问 GPIO12 或 GPIO13。
- 未构造真实 LGPIOFactory。
- 未构造真实 Servo。
- 未初始化或解锁电调。
- 未输出真实 PWM。
- 未控制任何风扇。
- 未运行 ROS 2 节点或 launch。
- 未使用 sudo。
- 未执行 scripts/setup_can.sh。
- 未进行带电测试。

## 14. Git 状态

- 提交分支：master。
- 提交说明：`修复：加固风扇控制安全与确定性`。
- 用户已在开发与验证完成后明确授权 commit 和 push。
- commit SHA、push 结果及最终远端状态以本次会话的最终报告为准。
- 本任务没有创建、移动、删除或重建标签。
- v0.3.0 和 v0.3.1 均未修改；v0.3.1 仍指向
  `5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- docs/NEXT_COMMAND.md 的任务前修改不纳入本次提交，并完整保留在工作区。

## 15. 额外发现

没有发现需要越过本任务范围修复的新增问题。任务明确排除的电机写入一致性、
CyberGear 初始化回滚和 lifecycle 重构均未修改。

## 16. 后续建议

- 在提交前人工审查新的显式恢复流程和独立 fans.launch.py 的兼容性影响。
- 后续如需实机验证，必须重新满足仓库十项带电测试授权门槛。
- 电机可靠性问题应继续作为独立任务处理，不与本次风扇安全修改混合。
