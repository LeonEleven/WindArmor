# WindArmor v0.3.0：阶段 2 软件实现与纯软件验证

## 1. 阶段状态与实施授权

此前的阶段 1 架构分析和补充澄清已经完成，最新方案位于：

```text
docs/LATEST_FEEDBACK.md
```

现批准进入：

```text
阶段 2：软件实现与纯软件验证
```

本次批准仅允许：

- 修改仓库中的产品代码、配置、测试和文档；
- 执行确认不会访问真实硬件的构建；
- 执行纯函数、mock、fake、静态结构和其他硬件隔离测试。

本次批准不包含：

- 真实 IMU 访问；
- CAN 访问；
- GPIO12 或 GPIO13 访问；
- PWM 输出；
- 电调初始化；
- 微电机控制；
- 风扇控制；
- 任何带电测试；
- 任何 ROS 2 硬件节点或 launch 的运行；
- commit、push 或 tag。

本任务必须遵守根目录 `AGENTS.md`。

---

## 2. 当前开发基线

当前实际开发基线为：

```text
分支：master
HEAD：bce019bfeab25e5b04c1fdfa39734aba49b7e4c1
稳定标签：v0.2.1
```

`v0.2.1` 已确认是本地和远程均存在、指向当前 HEAD 的附注标签。

`AGENTS.md` 当前仍记录 `v0.2.0`，这是已知的文档维护事项。本次不要修改
`AGENTS.md`，也不要因为该差异切换、重置或清理工作区。

实际实现必须基于当前分支、当前 HEAD 和用户已有工作区修改。

不得执行：

```bash
git checkout
git switch
git reset
git clean
git restore
git stash
```

除非用户之后明确授权。

---

## 3. 反馈文件约定

每次任务完成后的正式反馈必须覆盖：

```text
docs/LATEST_FEEDBACK.md
```

该文件只保留最新一次反馈。

本次允许修改产品文件，因此最终反馈必须分别列出：

1. 产品代码、配置、测试和文档的修改；
2. 过程反馈文件 `docs/LATEST_FEEDBACK.md`；
3. 用户在任务开始前已经存在的修改。

不得把任务开始前已有的 `docs/NEXT_COMMAND.md` 描述为本次 Codex 修改。

不得修改 `docs/NEXT_COMMAND.md`。

---

## 4. 当前硬件状态与绝对禁令

当前硬件状态没有变化：

- 4 个 CyberGear 微电机没有动力供电；
- 2 个涵道风扇没有动力供电；
- 当前不授权任何带电测试；
- 当前不授权访问真实 IMU；
- 当前不授权访问 CAN；
- 当前不授权访问 GPIO；
- 当前不授权访问真实串口。

本次绝对禁止：

```bash
ros2 run ...
ros2 launch ...
sudo ...
./scripts/setup_can.sh ...
```

也不得：

- 打开 `/dev/imu_usb`；
- 启动 IMU LifecycleNode；
- 创建真实 CAN 后端；
- 初始化 CyberGear；
- 实例化 `fan_controller`；
- 初始化 `lgpio`、Servo 或其他 GPIO 后端；
- 输出真实 PWM；
- 使电调解锁；
- 启动统一硬件 launch；
- 通过 Python 导入并构造会访问真实硬件的节点；
- 因为硬件未通电就启动硬件输出节点；
- 把软件测试描述为实机验证。

如果无法确定某项命令或测试是否会访问硬件，必须停止并询问用户。

---

## 5. 开始实施前的检查

首先执行：

```bash
git status --short --branch
git diff --check
```

随后重新阅读：

- `AGENTS.md`
- `docs/FIRST_COMMAND.md`
- `docs/NEXT_COMMAND.md`
- `docs/LATEST_FEEDBACK.md`
- `README.md`
- `src/imu_cybergear_ros2`
- `src/windarmor_fan_controller`
- `src/windarmor_bringup`
- 相关配置、launch、测试、`package.xml` 和 `setup.py`

在修改前必须确认：

- 用户已有修改不会被覆盖；
- 新增和现有测试不会实例化硬件节点；
- Python 模块导入不会在模块级初始化硬件；
- 构建命令不会启动节点或访问设备；
- 当前接口类型与阶段 1 反馈一致。

如果代码与阶段 1 反馈存在实质差异，应先停止并写入
`docs/LATEST_FEEDBACK.md` 报告，不得在未经说明的情况下改变架构。

---

# 6. 已批准的总体架构

采用以下架构：

```text
imu_motor_controller_node
  ├─ 现有电机目标计算
  ├─ /imu/relative_roll_pitch
  └─ /motors/control_mode

/fans/pwm
/fans/left/pwm
/fans/right/pwm
/imu/relative_roll_pitch
/motors/control_mode
/fans/enabled
/e_stop
        ↓
fan_command_manager
        ↓
/fans/command_pwm
        ↓
fan_controller
        ↓
GPIO12 / GPIO13
```

核心原则：

1. 电机与风扇共享同一组修正和归零后的相对姿态；
2. 不在风扇包中复制另一套 IMU 零点；
3. `fan_command_manager` 完成手动/自动仲裁；
4. 正式运行时只有管理器发布 `/fans/command_pwm`；
5. `fan_controller` 只负责硬件 I/O、最终限幅、底层看门狗、急停和资源清理；
6. 公共手动接口名称和消息类型保持兼容；
7. 外部普通控制源不得绕过管理器直接进入硬件节点；
8. 自动控制启动时默认关闭。

---

# 7. 相对姿态唯一权威来源

## 7.1 新增接口

新增：

```text
/imu/relative_roll_pitch
geometry_msgs/msg/Vector3Stamped
```

消息语义：

```text
header = 原始 sensor_msgs/Imu.header
vector.x = relative roll，单位 rad
vector.y = relative pitch，单位 rad
vector.z = 0.0
```

不得把单位改成度。

## 7.2 处理顺序

相对姿态必须按照以下顺序产生：

1. 检查四元数四个分量均为有限值；
2. 拒绝 `NaN` 和 `Inf`；
3. 拒绝零范数或过小范数；
4. 归一化四元数；
5. 转换为 roll 和 pitch；
6. 应用 `roll_axis_sign` 和 `pitch_axis_sign`；
7. 更新当前有效绝对姿态；
8. 扣除统一 `_imu_zero_roll` 和 `_imu_zero_pitch`；
9. 把相对差值归一化到 `[-π, π]`；
10. 发布统一相对姿态；
11. 只有电机处于 AUTO 时，才继续进行电机专用控制处理。

统一相对姿态必须在以下电机专用步骤之前产生：

- 电机姿态死区；
- ±90° 电机控制限制；
- 电机目标正负方向变换；
- 电机软限位；
- 电机变化率限制。

## 7.3 MANUAL 模式行为

即使电机处于 MANUAL，仍必须持续发布有效相对姿态。

不得因为电机不在 AUTO 就提前返回并停止发布姿态。

但 MANUAL 模式不得发送新的电机自动目标。

## 7.4 无效姿态行为

无效四元数：

- 不更新最新有效姿态；
- 不更新有效 IMU 时间；
- 不发布相对姿态；
- 不填充为零；
- 不产生电机自动目标；
- 最终由电机和风扇各自的数据超时逻辑进入安全状态。

## 7.5 纯函数位置

优先在现有：

```text
src/imu_cybergear_ros2/imu_cybergear_ros2/imu_protocol.py
```

增加可测试的纯函数，包括：

- 四元数有限值检查；
- 四元数范数检查；
- 四元数归一化；
- 角度归一化；
- 修正和零点扣除后的相对 roll/pitch 计算。

本次原则上不新增 `attitude_control.py`，除非实际代码证明继续放入
`imu_protocol.py` 会导致明显职责混乱。若必须偏离，应先在反馈中说明理由。

---

# 8. 统一 IMU 归零

`/imu/set_zero` 和键盘 `z` 必须调用同一个控制节点方法，例如：

```text
set_imu_zero()
```

两种入口必须使用完全相同的：

- 最新姿态来源；
- 数据有效性检查；
- 数据新鲜度检查；
- 成功/失败返回语义；
- 日志语义。

不得再让键盘 `z` 绕过新鲜度检查。

归零成功后：

- 更新统一零点；
- 记录姿态序列号或接收序号；
- 后续发布的相对姿态使用新零点；
- 自动风扇不能使用归零前缓存的数据；
- 已处于自动状态时，风扇自动请求应被清除并立即停止；
- 用户需要重新显式启用风扇 AUTO。

不得修改：

- `motor_ids`
- `motor_signs`
- `motor_limits_min`
- `motor_limits_max`

---

# 9. 电机模式状态接口

新增：

```text
/motors/control_mode
std_msgs/msg/String
```

对外稳定值限定为：

```text
MANUAL
AUTO
EMERGENCY_STOP
DISABLED
ERROR
```

内部状态映射：

- `MANUAL_RUNNING` → `MANUAL`
- `AUTO_RUNNING` → `AUTO`
- `EMERGENCY_STOP` → `EMERGENCY_STOP`
- `ERROR` → `ERROR`
- `UNINITIALIZED` → `DISABLED`
- `INITIALIZING` → `DISABLED`
- Lifecycle inactive/cleanup/shutdown → `DISABLED`
- `SHUTTING_DOWN` → `DISABLED`

要求：

- 状态变化时立即发布；
- 周期性发布心跳；
- 状态心跳频率可通过 YAML 配置；
- 使用 `RELIABLE + TRANSIENT_LOCAL + KEEP_LAST(1)`；
- 风扇管理器仍必须使用本地单调时钟判断状态是否超时；
- 不能无限信任 transient-local 保存的旧消息。

建议初始参数：

```yaml
motor_mode_publish_rate_hz: 5.0
```

## 9.1 电机恢复语义修正

当前 `/enable_motor=true` 从急停恢复后没有正确离开
`EMERGENCY_STOP`。

在不改变现有硬件参数的前提下修正为：

```text
/enable_motor=true
  → 执行现有恢复和保持当前位置逻辑
  → 恢复成功后进入 MANUAL
  → 不得直接恢复 AUTO
```

键盘 `r` 和服务恢复最终都应进入 MANUAL。

该变化必须通过纯软件替身或状态测试覆盖，不得连接真实 CAN 或电机。

---

# 10. 底层 `fan_controller` 的职责

## 10.1 最终命令入口

`fan_controller` 改为只订阅：

```text
/fans/command_pwm
std_msgs/msg/Int32MultiArray
```

正式架构中不得继续直接订阅：

```text
/fans/pwm
/fans/left/pwm
/fans/right/pwm
```

否则外部发布者可以绕过仲裁。

底层仍必须对命令执行最终 PWM 范围限制。

## 10.2 `/fans/stop`

保留现有接口和所有权：

```text
/fans/stop
std_srvs/srv/Trigger
```

仍由 `fan_controller` 提供。

调用后必须：

1. 立即输出左右停止 PWM；
2. 把底层锁存为 disabled；
3. 清除底层最后命令时间；
4. 清除旧命令接受状态；
5. 发布停止状态；
6. 发布 `/fans/enabled=false`；
7. disabled 状态拒绝普通 `/fans/command_pwm`。

不得把 `/fans/stop` 改由管理器提供。

## 10.3 `/fans/enable`

保留：

```text
/fans/enable
std_srvs/srv/SetBool
```

`data=false`：

- 立即输出停止 PWM；
- 锁存 disabled；
- 清除命令时间；
- 发布 `/fans/enabled=false`。

`data=true`：

- 再次输出停止 PWM；
- 清除旧命令时间；
- 恢复接受新命令；
- 发布 `/fans/enabled=true`；
- 不恢复任何旧 PWM；
- 在新命令到达前保持停止。

## 10.4 `/fans/enabled`

新增：

```text
/fans/enabled
std_msgs/msg/Bool
```

要求：

- 状态变化时立即发布；
- 周期发送心跳；
- 使用 `RELIABLE + TRANSIENT_LOCAL + KEEP_LAST(1)`；
- 频率由 YAML 配置。

建议初始值：

```yaml
enabled_status_publish_rate_hz: 5.0
```

## 10.5 `/e_stop`

底层收到：

```text
/e_stop = true
```

必须：

- 立即输出停止 PWM；
- 锁存 disabled；
- 清除命令时间；
- 发布 `/fans/enabled=false`；
- 禁止普通命令恢复输出；
- 必须经过显式 `/fans/enable=true` 才能恢复底层接受能力。

急停不能经过缓降。

## 10.6 底层看门狗

底层现有命令看门狗必须保留。

管理器心跳不能被视为删除底层看门狗的理由。

底层命令超时：

- 立即输出停止 PWM；
- 保持现有安全策略；
- 不得输出旧命令；
- 具体 enabled 状态是否保持不变，应保持与已批准方案一致并通过测试记录。

---

# 11. `fan_command_manager`

新增无 GPIO、无 CAN、无串口访问的 ROS 2 节点：

```text
fan_command_manager
```

职责：

- 接收公共手动命令；
- 接收统一相对姿态；
- 接收电机模式；
- 接收底层 enabled 状态；
- 接收系统 `/e_stop`；
- 提供自动模式启停服务；
- 计算自动目标；
- 维护迟滞和变化率限制；
- 对手动与自动来源进行单一仲裁；
- 处理所有来源超时；
- 输出唯一正常底层命令；
- 发布可观察状态。

不得：

- 导入或初始化 GPIO；
- 连接 CAN；
- 打开串口；
- 初始化电调；
- 直接控制微电机；
- 独立解析原始 IMU 零点；
- 绕过底层 PWM 限幅和看门狗。

核心状态和计算应放入不依赖 ROS 的纯 Python 类或纯函数模块，例如：

```text
fan_control.py
```

---

# 12. 手动命令接口与新鲜度

保持公共接口：

```text
/fans/pwm
std_msgs/msg/Int32MultiArray

/fans/left/pwm
std_msgs/msg/Int32

/fans/right/pwm
std_msgs/msg/Int32
```

## 12.1 双通道消息

`/fans/pwm` 的有效消息必须恰好包含两个元素。

一条有效消息原子更新：

- 左侧命令；
- 右侧命令；
- 左侧接收时间；
- 右侧接收时间。

长度错误时：

- 拒绝整条消息；
- 不更新任何命令；
- 不更新任何时间戳。

## 12.2 单通道消息

`/fans/left/pwm`：

- 只更新左侧值和左侧时间；
- 不更新右侧值；
- 不刷新右侧时间。

`/fans/right/pwm`：

- 只更新右侧值和右侧时间；
- 不更新左侧值；
- 不刷新左侧时间。

## 12.3 越界输入

上层管理器必须检查：

```text
min_pwm_us <= value <= max_pwm_us
```

越界时：

- 拒绝该条消息；
- 不更新时间戳；
- 两元素消息中任一元素越界时拒绝整条消息；
- 不允许部分接受；
- 不进行静默限幅。

底层继续保留最终限幅，作为最后一道防御。

## 12.4 手动超时

左右通道分别维护新鲜度。

- 左侧超时只让左侧输出停止 PWM；
- 右侧超时只让右侧输出停止 PWM；
- 至少一侧新鲜时处于 `MANUAL_ACTIVE`；
- 两侧都超时时进入 `MANUAL_WAITING`；
- 一侧消息不得给另一侧续期。

建议初始参数：

```yaml
manual_command_timeout_sec: 0.5
```

如果现有键盘心跳频率与该值不适配，可选择更合理初值，但必须在反馈中说明
依据。

---

# 13. 自动风扇控制公式

使用经过统一修正和归零的相对姿态。

先转换为度用于控制参数：

```text
roll_deg = degrees(relative_roll_rad)
pitch_deg = degrees(relative_pitch_rad)
```

方向公式固定为：

```text
pitch_activity = abs(pitch_deg)

left_roll_activity = max(0.0, -roll_deg)
right_roll_activity = max(0.0, roll_deg)

left_activity = max(pitch_activity, left_roll_activity)
right_activity = max(pitch_activity, right_roll_activity)
```

不得把 pitch 和 roll 简单相加。

期望行为：

- 正 pitch：左右风扇同时增大；
- 负 pitch：左右风扇同时增大；
- 相同绝对值的正负 pitch 产生相同结果；
- 左倾：左侧增加、右侧只保留 pitch 分量；
- 右倾：右侧增加、左侧只保留 pitch 分量；
- 零姿态：左右停止。

---

# 14. 死区、迟滞、映射和变化率

初始配置：

```yaml
auto_enabled_at_start: false

fan_deadband_on_deg: 5.0
fan_deadband_off_deg: 3.0
fan_full_scale_deg: 45.0

fan_stop_pwm_us: 800
fan_start_pwm_us: 1200
fan_auto_max_pwm_us: 1400

control_rate_hz: 20.0
rise_step_pwm_us: 10
fall_step_pwm_us: 20

imu_timeout_sec: 0.2
manual_command_timeout_sec: 0.5
motor_mode_timeout_sec: 1.0
fan_enabled_timeout_sec: 1.0

motor_mode_publish_rate_hz: 5.0
enabled_status_publish_rate_hz: 5.0
```

这些是软件初始值，不代表已经实机标定。

## 14.1 左右独立迟滞

每侧分别维护运行状态。

```text
停止状态：
activity >= fan_deadband_on_deg
→ 进入运行

运行状态：
activity < fan_deadband_off_deg
→ 退出运行

两个阈值之间：
保持原状态
```

## 14.2 角度到 PWM

运行状态下：

```text
ratio = clamp(
    (activity_deg - fan_deadband_on_deg)
    / (fan_full_scale_deg - fan_deadband_on_deg),
    0.0,
    1.0
)

target_pwm = fan_start_pwm_us + ratio * (
    fan_auto_max_pwm_us - fan_start_pwm_us
)
```

停止状态：

```text
target_pwm = fan_stop_pwm_us
```

## 14.3 正常变化率限制

```text
next_pwm = current_pwm + clamp(
    target_pwm - current_pwm,
    -fall_step_pwm_us,
    rise_step_pwm_us
)
```

以下事件必须绕过变化率限制并立即停止：

- `/e_stop=true`
- `/fans/stop`
- `/fans/enable=false`
- 底层 disabled
- 底层状态超时
- 电机离开 AUTO
- 电机模式超时
- 姿态超时
- 姿态无效
- AUTO 关闭
- 管理器退出
- 参数或消息非法导致的安全停止

---

# 15. 参数校验

启动管理器前必须验证：

```text
0 <= fan_deadband_off_deg
fan_deadband_off_deg < fan_deadband_on_deg
fan_deadband_on_deg < fan_full_scale_deg

fan_stop_pwm_us <= fan_start_pwm_us
fan_start_pwm_us <= fan_auto_max_pwm_us
fan_auto_max_pwm_us <= max_pwm_us

control_rate_hz > 0
rise_step_pwm_us > 0
fall_step_pwm_us > 0
imu_timeout_sec > 0
manual_command_timeout_sec > 0
motor_mode_timeout_sec > 0
fan_enabled_timeout_sec > 0
motor_mode_publish_rate_hz > 0
enabled_status_publish_rate_hz > 0
```

非法参数不得产生硬件命令。

应在节点初始化阶段明确失败，或者进入永久安全停止并输出清晰错误。选择一种
一致策略并通过测试覆盖。

---

# 16. 风扇 AUTO 启用服务

新增：

```text
/fans/auto_enable
std_srvs/srv/SetBool
```

## 16.1 启用条件

`data=true` 只有在以下条件全部成立时才能成功：

- 电机模式为 `AUTO`；
- 电机模式状态新鲜；
- 底层风扇 `enabled=true`；
- 底层 enabled 状态新鲜；
- 管理器不处于未恢复急停；
- 已有有效且新鲜的相对姿态，证明数据源可用；
- 自动控制参数有效。

条件不满足时：

- 返回失败；
- 不记录 AUTO 请求；
- 不进入等待武装状态；
- 返回消息说明失败原因。

不得采用“先记录请求，条件恢复后自动启动”的隐藏武装方案。

## 16.2 成功启用

成功后：

- `auto_requested=true`；
- 发布 `/fans/auto_enabled=true`；
- 进入 `AUTO_WAITING`；
- 立即输出停止；
- 清除手动缓存；
- 清除自动迟滞和平滑状态；
- 记录当前姿态接收序号；
- 必须等待服务成功之后到达的新姿态；
- 新姿态到达后才可进入 `AUTO_ACTIVE`。

## 16.3 关闭 AUTO

`data=false` 始终应成功。

关闭后：

- 立即停止；
- `auto_requested=false`；
- 发布 `/fans/auto_enabled=false`；
- 发布 `/fans/auto_active=false`；
- 清除自动缓存；
- 清除迟滞；
- 清除平滑输出状态；
- 进入 `MANUAL_WAITING`、`DISABLED` 或 `EMERGENCY_STOP` 中符合当前安全条件
  的状态；
- 不自动恢复关闭前的手动缓存。

---

# 17. 电机 AUTO 与风扇 AUTO 同步

自动控制实际生效必须同时满足：

```text
auto_requested
AND motor_mode == AUTO
AND motor_mode 新鲜
AND fan_enabled == true
AND fan_enabled 状态新鲜
AND e_stop_latched == false
AND 已收到启用后的新姿态
AND 姿态有效且新鲜
```

以下任一事件必须：

- 立即停止；
- 清除 AUTO 请求；
- 清除自动缓存；
- 发布 `/fans/auto_enabled=false`；
- 发布 `/fans/auto_active=false`。

事件包括：

- 电机离开 AUTO；
- 电机进入 `EMERGENCY_STOP`；
- 电机进入 `ERROR`；
- 电机进入 `DISABLED`；
- 电机模式状态超时；
- 底层风扇 disabled；
- 底层状态超时；
- `/e_stop=true`；
- 姿态无效；
- 姿态超时；
- `/fans/stop`；
- 管理器重启或退出。

条件恢复后不得自动恢复 AUTO。用户必须重新显式调用：

```text
/fans/auto_enable=true
```

---

# 18. 急停锁存和恢复规则

这是对阶段 1 方案的强制修正。

## 18.1 收到急停

收到：

```text
/e_stop = true
```

管理器必须：

- 设置本地 `e_stop_latched=true`；
- 立即输出停止；
- 绕过变化率限制；
- 清除手动左右缓存；
- 清除所有手动时间戳；
- 清除姿态缓存；
- 清除姿态时间戳；
- 清除迟滞；
- 清除平滑输出状态；
- 清除 AUTO 请求；
- 进入 `EMERGENCY_STOP`。

底层风扇控制器同时：

- 立即输出停止；
- 锁存 disabled；
- 发布 `/fans/enabled=false`。

## 18.2 不允许仅由风扇 enable 清除系统急停

在统一 `windarmor.launch.py` 运行模式中：

```text
/fans/enable=true
```

只能恢复底层风扇接受新命令的能力，**不能单独清除管理器的系统急停锁存**。

统一系统中，管理器清除 `e_stop_latched` 必须同时确认：

1. 在急停事件之后收到了新的 `/fans/enabled=true`；
2. 在急停事件之后收到了新的、有效且新鲜的电机模式；
3. 电机模式已经是 `MANUAL` 或 `AUTO`；
4. 电机模式不是 `EMERGENCY_STOP`、`DISABLED` 或 `ERROR`。

只有上述条件同时满足，才可：

```text
e_stop_latched=false
→ MANUAL_WAITING
```

不得恢复任何旧手动命令或 AUTO 请求。

## 18.3 独立风扇运行模式

为了保持 `fans.launch.py` 的独立手动调试能力，管理器增加参数：

```yaml
require_motor_mode_for_manual: false
```

在独立 `fans.launch.py` 中默认：

```yaml
require_motor_mode_for_manual: false
```

此模式下：

- 自动风扇仍必须要求电机模式为 AUTO，因此没有电机控制器时不能启用 AUTO；
- 手动风扇可以独立工作；
- 急停后，必须在急停事件之后显式执行 `/fans/enable=true`，才能清除本地风扇
  急停锁存并进入 `MANUAL_WAITING`；
- 仍不得恢复旧命令。

在统一 `windarmor.launch.py` 中必须覆盖为：

```yaml
require_motor_mode_for_manual: true
```

统一模式下，如果电机状态为以下任一值，手动风扇也必须停止：

```text
EMERGENCY_STOP
DISABLED
ERROR
```

如果统一模式中曾经收到过电机模式，但其后状态超时，也必须停止手动风扇。

这可以避免电机系统仍处于急停或失效状态时，风扇被单独重新启动。

## 18.4 手动模式允许的电机状态

统一模式中，手动风扇仅在新鲜电机模式为以下状态时允许：

```text
MANUAL
AUTO
```

手动风扇是否运行仍由新鲜手动命令决定。

电机处于 AUTO 不会自动启用风扇 AUTO；未请求风扇 AUTO 时，显式手动命令仍可
按手动模式处理。

---

# 19. 管理器状态机

至少实现以下状态：

```text
SAFE_STOP
MANUAL_WAITING
MANUAL_ACTIVE
AUTO_WAITING
AUTO_ACTIVE
DISABLED
EMERGENCY_STOP
```

## 19.1 `SAFE_STOP`

用于：

- 启动时尚无可信状态；
- 参数非法；
- 自动姿态无效或超时；
- 模式状态出现不一致；
- 无法归类的安全故障。

输出：

```text
[stop_pwm, stop_pwm]
```

## 19.2 `MANUAL_WAITING`

条件：

- 不处于急停；
- 底层 enabled；
- 如果要求电机模式，则电机状态允许且新鲜；
- AUTO 未请求；
- 没有新鲜手动命令。

输出停止 PWM。

## 19.3 `MANUAL_ACTIVE`

条件：

- 满足手动安全条件；
- 至少一侧存在新鲜手动命令；
- AUTO 未请求。

输出：

- 新鲜侧：对应手动命令；
- 超时侧：停止 PWM。

## 19.4 `AUTO_WAITING`

条件：

- AUTO 服务请求已成功；
- 所有启用条件仍成立；
- 正在等待服务成功后的新姿态。

输出停止 PWM。

## 19.5 `AUTO_ACTIVE`

条件：

- AUTO 请求仍有效；
- 电机仍为 AUTO；
- 底层仍 enabled；
- 所有状态均新鲜；
- 存在服务成功后的有效新姿态。

输出自动计算结果。

`AUTO_ACTIVE` 不表示风扇一定旋转。姿态处于死区时输出仍为停止 PWM。

## 19.6 `DISABLED`

用于：

- 底层 enabled=false；
- 底层状态未知或超时。

立即停止并清除所有缓存和 AUTO 请求。

## 19.7 `EMERGENCY_STOP`

用于：

```text
e_stop_latched=true
```

立即停止，清除全部缓存和 AUTO 请求。

只有满足第 18 节的恢复条件才能退出。

---

# 20. 新增状态接口

新增：

```text
/fans/auto_enabled
std_msgs/msg/Bool
```

语义：

```text
管理器已经接受且当前仍保留 auto_requested
```

新增：

```text
/fans/auto_active
std_msgs/msg/Bool
```

语义：

```text
AUTO 的全部运行条件成立，且已收到启用后的新姿态
```

新增：

```text
/fans/auto_target_pwm
std_msgs/msg/Int32MultiArray
```

语义：

```text
自动算法计算出的、变化率限制之前的左右目标
```

新增：

```text
/fans/control_state
std_msgs/msg/String
```

建议内容使用稳定状态值，并通过日志补充停止原因。

状态类话题使用：

```text
RELIABLE + TRANSIENT_LOCAL + KEEP_LAST(1)
```

并按低频心跳发布。

命令和姿态话题使用可靠、volatile、小队列 QoS。

新鲜度判断必须使用：

```text
time.monotonic()
```

IMU `header.stamp` 用于保留源时间和检测明显旧数据，不能替代本地接收超时。

---

# 21. Launch 结构

## 21.1 `fans.launch.py`

正式启动：

- `fan_command_manager`
- `fan_controller`

不得创建两个 `fan_controller`。

独立风扇 launch 默认：

```text
require_motor_mode_for_manual=false
```

自动模式因缺少电机 AUTO 状态而不可启用。

## 21.2 `windarmor.launch.py`

统一系统必须通过包含或复用正式 `fans.launch.py` 来启动风扇系统。

不得：

- 在统一 launch 中再次创建第二个 `fan_controller`；
- 让底层订阅公共手动话题；
- 产生两个 `/fans/command_pwm` 正常发布者。

统一系统覆盖：

```text
require_motor_mode_for_manual=true
```

## 21.3 底层维护模式

单独执行 `fan_controller` 仅属于底层维护模式。

README 必须明确：

- 它不是正常公共控制方式；
- 它只订阅内部 `/fans/command_pwm`；
- 只有在明确硬件测试授权后才能运行；
- 使用该模式前必须确认管理器未运行；
- 正常操作应使用 `fans.launch.py` 或 `windarmor.launch.py`。

本次不得实际运行任何 launch。

---

# 22. 文件修改范围

预计允许修改以下文件；应保持范围最小。

## 22.1 项目文档

- `README.md`
- `src/imu_cybergear_ros2/README.md`
- 必要时更新风扇包 README；若当前不存在，不要为了重复根 README 而创建冗余
  文档。

## 22.2 IMU 和电机包

- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_protocol.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/controller_state.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py`
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`
- `src/imu_cybergear_ros2/package.xml`
- 相关测试文件

不要求必须修改每个文件。若某个目标能以更小范围实现，应选择更小范围。

## 22.3 风扇包

- 新增 `fan_control.py`
- 新增 `fan_command_manager.py`
- 修改 `fan_node.py`
- 必要时修改 `pwm.py`
- 修改 `fan_params.yaml`
- 修改 `fans.launch.py`
- 修改 `setup.py`
- 修改 `package.xml`
- 新增和扩展相关测试

## 22.4 Bringup

- `src/windarmor_bringup/launch/windarmor.launch.py`
- `src/windarmor_bringup/test/test_launch_syntax.py`
- 必要的新静态接口路由测试

## 22.5 禁止修改

本次不得修改：

- `AGENTS.md`
- `docs/FIRST_COMMAND.md`
- `docs/NEXT_COMMAND.md`
- 包版本号
- Git 标签
- `motor_ids`
- `motor_signs`
- `motor_limits_min`
- `motor_limits_max`
- GPIO12 用途
- GPIO13 用途
- 已确认的 CAN 硬件映射

如果实现确实需要超出允许范围，必须停止并报告，不得自行扩大任务。

---

# 23. 建议实施顺序

按以下顺序实施，以降低一次性改动风险。

## 步骤 1：纯函数和测试

先实现并测试：

- 四元数校验和归一化；
- 相对姿态角度计算；
- 姿态到左右活动量；
- 参数校验；
- 左右迟滞；
- 角度到 PWM；
- 变化率限制；
- 手动左右通道缓存和超时；
- 状态机转换。

此阶段不得实例化 ROS 硬件节点。

## 步骤 2：IMU 和电机状态接口

实现：

- 统一相对姿态发布；
- MANUAL 下持续发布；
- 统一归零；
- `/motors/control_mode`；
- 状态心跳；
- `/enable_motor=true` 恢复到 MANUAL。

先运行相关纯软件测试。

## 步骤 3：风扇管理器

实现：

- 公共手动输入；
- 自动启停服务；
- 模式同步；
- enabled 状态；
- 急停锁存；
- 手动/自动仲裁；
- 唯一最终命令发布；
- 状态话题。

不得访问 GPIO。

## 步骤 4：底层路由与锁存安全

修改 `fan_controller`：

- 只订阅内部命令；
- stop 锁存 disabled；
- enable 恢复但不恢复旧命令；
- e-stop 锁存 disabled；
- enabled 状态发布；
- 保留限幅、看门狗和清理。

底层节点不能在测试中真实实例化。将可测逻辑提取为纯类，或使用静态结构测试。

## 步骤 5：Launch 和文档

更新：

- `fans.launch.py`
- `windarmor.launch.py`
- README
- 接口说明
- 安全恢复说明
- 独立和统一模式差异
- 软件验证状态
- 等待实机验证项目

## 步骤 6：完整软件构建和回归

重新审查所有新增测试，确认不会访问硬件后，再执行构建和测试。

---

# 24. 最低测试要求

## 24.1 四元数和相对姿态

至少测试：

- 正常单位四元数；
- 可归一化的非单位四元数；
- 零范数；
- 极小范数；
- `NaN`；
- 正 `Inf`；
- 负 `Inf`；
- roll/pitch 方向；
- 角度跨越 ±π；
- 轴向 sign；
- 零点扣除；
- MANUAL 与 AUTO 发布相同相对姿态；
- 相对姿态位于电机死区和限位之前；
- 原始 IMU header 被保留；
- 无效姿态不刷新有效时间。

## 24.2 归零

至少测试：

- 服务归零成功；
- 键盘归零成功；
- 两者调用同一方法；
- 两者新鲜度规则一致；
- 数据过旧时拒绝；
- 无有效数据时拒绝；
- 归零后旧姿态序列不能启用 AUTO；
- 归零清除已有风扇 AUTO 请求。

## 24.3 电机模式

至少测试：

- 初始化映射为 DISABLED；
- MANUAL；
- AUTO；
- EMERGENCY_STOP；
- ERROR；
- shutdown 映射为 DISABLED；
- 状态变化立即发布；
- 心跳发布；
- `/enable_motor=true` 从急停恢复到 MANUAL；
- 不直接恢复 AUTO。

## 24.4 自动姿态控制

至少测试：

- 零姿态；
- 正 pitch；
- 负 pitch；
- 相同绝对值正负 pitch；
- 左 roll；
- 右 roll；
- pitch 与左 roll 复合；
- pitch 与右 roll 复合；
- 使用 `max()` 而非相加；
- 左右独立迟滞；
- 死区边界；
- 满量程；
- 最大 PWM 限幅；
- 正常上升限制；
- 正常下降限制；
- 安全停止绕过限速。

## 24.5 自动启用条件

至少测试：

- 电机 MANUAL 时拒绝；
- 电机 AUTO 时可申请；
- 电机模式超时时拒绝；
- 底层 disabled 时拒绝；
- enabled 状态超时时拒绝；
- 姿态过旧时拒绝；
- 急停未恢复时拒绝；
- 成功后进入 AUTO_WAITING；
- 服务前姿态不能直接激活；
- 服务后的新姿态进入 AUTO_ACTIVE；
- 关闭 AUTO 始终成功；
- 条件失效清除 AUTO 请求；
- 条件恢复不会自动重新启用。

## 24.6 手动通道

至少测试：

- pair 原子刷新左右；
- pair 错误长度整条拒绝；
- pair 任一越界整条拒绝；
- left 只刷新左侧；
- right 只刷新右侧；
- 左消息不刷新右侧时间；
- 右消息不刷新左侧时间；
- 单侧超时；
- 双侧超时；
- 模式切换清缓存；
- disabled 清缓存；
- 急停清缓存；
- 非法消息不刷新时间。

## 24.7 急停和恢复

至少测试：

- `/e_stop=true` 立即停止；
- 急停清除全部缓存；
- 急停清除 AUTO；
- 急停绕过变化率限制；
- 单独 `/fans/enable=true` 在统一模式中不能清除系统急停；
- 电机仍为 EMERGENCY_STOP 时不能恢复手动风扇；
- 风扇 enabled 与电机 MANUAL/AUTO 均在急停后重新到达时才解除锁存；
- 独立风扇模式中，急停后的新 `/fans/enable=true` 可以恢复到
  MANUAL_WAITING；
- 恢复后不使用旧手动命令；
- 恢复后不使用旧姿态；
- 恢复后不恢复旧 AUTO 请求。

## 24.8 底层控制器

通过纯类、mock 或静态测试覆盖：

- `/fans/stop` 锁存 disabled；
- `/fans/enable=false` 锁存 disabled；
- `/fans/enable=true` 保持停止并等待新命令；
- disabled 时拒绝普通命令；
- `/e_stop=true` 锁存 disabled；
- 新命令到达后才更新时间；
- 命令超时停止；
- 最终范围限幅仍保留；
- 退出清理路径仍存在。

不得为测试而实例化真实 GPIO 节点。

## 24.9 单一最终发布者

静态或结构测试确认：

- 正式 launch 只有一个 `fan_command_manager`；
- 正式 launch 只有一个 `fan_controller`；
- `fan_controller` 不订阅三个公共手动话题；
- `fan_command_manager` 发布 `/fans/command_pwm`；
- 正式仓库代码中没有第二个正常 `/fans/command_pwm` 发布者；
- 统一 launch 不重复创建风扇底层节点；
- 公共手动接口仍存在。

## 24.10 回归

必须保证现有测试继续通过：

- IMU 协议；
- 当前姿态换算；
- 风扇 PWM；
- 风扇键盘伪终端；
- launch AST；
- 现有包构建。

---

# 25. 构建和测试要求

## 25.1 执行前检查

在运行测试前：

1. 阅读全部新增测试；
2. 阅读 fixture；
3. 检查导入链；
4. 确认不会实例化硬件节点；
5. 确认不会访问 IMU、CAN、GPIO 或串口；
6. 确认不会调用 `sudo`；
7. 确认不会执行 launch。

## 25.2 允许的构建命令

确认安全后，可执行：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

## 25.3 允许的软件测试

确认测试集合安全后，可执行：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash

colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup

colcon test-result --verbose
```

还应按实际新增测试文件运行针对性 pytest，例如：

```bash
python3 -m pytest <实际安全测试文件> -v
```

必须使用实际文件路径，不得照抄不存在的名称。

## 25.4 禁止的验证方式

不得运行：

```bash
ros2 node list
ros2 topic list
ros2 topic echo
ros2 topic pub
ros2 service call
ros2 run
ros2 launch
```

因为当前没有授权启动或访问真实 ROS 硬件系统。

不得运行任何需要 GPIO、CAN 或真实串口的集成测试。

---

# 26. README 更新要求

实现后更新 README，至少说明：

- v0.3.0 候选功能；
- 当前稳定发布仍为 v0.2.1；
- 自动风扇默认关闭；
- 姿态与左右风扇关系；
- 相对姿态话题；
- 电机模式状态话题；
- 自动启停服务；
- `auto_enabled` 和 `auto_active` 区别；
- 手动公共话题保持兼容；
- 内部 `/fans/command_pwm` 不属于普通公共控制接口；
- 独立风扇模式和统一系统模式的区别；
- `/fans/stop` 会锁存 disabled；
- `/fans/enable=true` 不恢复旧命令；
- 统一系统急停恢复还要求电机恢复；
- 手动左右通道分别超时；
- 自动姿态超时；
- 底层命令看门狗；
- 正式启动方式；
- 单独运行 `fan_controller` 仅用于授权维护；
- 当前完成的仅是软件验证；
- 电机和风扇尚未通电测试；
- 1200 µs 和 1400 µs 尚未实机标定；
- 后续实机验证前必须获得用户授权。

不得把软件测试写成实机测试。

---

# 27. 实现过程中的偏差处理

如果实现过程中发现以下情况之一，必须停止并先反馈：

- 当前代码与阶段 1 结论明显不一致；
- 必须改变受保护电机参数；
- 必须改变 GPIO12/13 用途；
- 必须运行硬件节点才能继续；
- 必须访问真实串口、CAN 或 GPIO；
- 必须进行带电测试；
- 需要破坏现有公共接口；
- 无法在不实例化硬件节点的情况下测试安全逻辑；
- 需要新增自定义消息包或进行明显扩大范围的重构；
- 用户已有修改与本次实现冲突；
- 构建或测试显示存在与本任务无关的大范围故障。

停止时覆盖 `docs/LATEST_FEEDBACK.md`，说明问题和建议，不得自行突破限制。

---

# 28. 完成后的反馈要求

完成实现和纯软件验证后，覆盖：

```text
docs/LATEST_FEEDBACK.md
```

标题建议：

```markdown
# 最新反馈：阶段 2 软件实现与纯软件验证
```

至少包含：

1. 当前分支、HEAD 和工作区初始状态；
2. 用户任务开始前已有修改；
3. 实际修改文件列表；
4. 每个文件的修改目的；
5. 最终架构；
6. 新增和修改的接口；
7. 新增和修改的参数；
8. 相对姿态的处理顺序；
9. 电机模式状态行为；
10. 手动/自动仲裁行为；
11. 急停锁存和恢复行为；
12. 独立风扇模式和统一模式的区别；
13. 控制公式；
14. 状态机；
15. 参数校验；
16. 已执行的全部命令；
17. 构建结果；
18. 每组测试结果；
19. 测试总数、通过数、失败数、跳过数；
20. 未执行的测试及原因；
21. 是否访问 IMU；
22. 是否访问 CAN；
23. 是否访问 GPIO；
24. 是否访问真实串口；
25. 电机和风扇是否通电；
26. 剩余软件风险；
27. 等待实机验证内容；
28. `git diff --stat`；
29. `git diff --check`；
30. 最终 `git status --short --branch`。

必须明确写明：

```text
本次没有运行任何 ROS 2 节点或 launch。
本次没有访问 IMU、CAN、GPIO、PWM 或真实串口。
4 个微电机和 2 个风扇均未通电、未控制、未影响。
本次完成的是软件实现和纯软件验证，不是实机验证。
```

---

# 29. 最终检查

完成后执行：

```bash
git diff --check
git diff --stat
git status --short --branch
```

根据需要展示关键 diff。

不得：

- commit；
- push；
- 创建标签；
- 修改现有标签；
- 启动节点；
- 运行 launch；
- 访问硬件；
- 要求用户现在通电。

完成阶段 2 反馈后停止，等待用户审查。

只有用户审查通过后，才会另行制定断电接口检查和分级实机验证计划。