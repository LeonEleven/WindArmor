# WindArmor：统一 MANUAL、AUTO 与 HOME 电机运动速度

## 1. 当前任务目标

当前稳定里程碑已经创建 `v0.3.0` 标签，IMU 驱动电机和双风扇联动的主要功能
已经实现并经过用户手动验证。

本次任务不修改 `v0.3.0` 标签，而是在当前分支和当前 `HEAD` 基础上改进电机
目标位置的推进方式，使以下三种运动路径具有统一、可预测、可配置的速度控制：

1. MANUAL 模式下通过 `w/s/a/d/i/k/j/l` 控制电机；
2. AUTO 模式下电机跟随 IMU 相对姿态；
3. 按 `h` 后全部电机回到零目标。

当前观测到：

- `h` 自动回零明显快于手动按键；
- `h` 自动回零也可能快于 AUTO 跟随 IMU；
- 手动速度受键盘字符重复频率影响；
- AUTO 目标推进受 IMU 消息到达频率影响；
- `h` 使用固定定时器，因此能够稳定、连续地推进目标。

本次目标不是简单增大某个步长，而是建立统一的固定周期电机目标推进器：

```text
手动按键 ─────────┐
IMU AUTO 目标 ────┼──> desired_targets
h 回零目标 ───────┘
                         ↓
               固定周期目标推进器
                         ↓
       根据模式速度和真实 dt 逐步逼近目标
                         ↓
                  CyberGear 位置命令
```

完成后：

- MANUAL、AUTO 和 HOME 都通过同一个推进器写入电机目标；
- 三种模式分别具有明确的速度参数；
- 初始值设置为相同，使三种运动速度大致一致；
- AUTO 运动速度不再直接依赖 IMU 消息频率；
- HOME 不再拥有一条独立且更快的目标写入路径；
- 手动长按时的平均目标速度尽量不依赖具体键盘重复频率；
- 单次轻按仍保留较小角度的精细控制能力。

---

## 2. 强制遵守的规则

本任务必须遵守：

- 根目录 `AGENTS.md`
- `docs/FIRST_COMMAND.md`
- 当前 `README.md`
- 当前代码和配置
- 用户已有工作区修改

`v0.3.0` 标签已经存在，本次不得：

- 移动、删除或覆盖 `v0.3.0` 标签；
- 为现有提交重新创建同名标签；
- 自动创建新标签；
- 自动 commit；
- 自动 push。

本次只允许软件实现和不访问硬件的测试。

未经用户另行明确授权，不得：

- 启动 ROS 2 节点或 launch；
- 访问真实 IMU；
- 打开真实串口；
- 连接 CAN；
- 运行 `scripts/setup_can.sh`；
- 初始化 CyberGear；
- 访问 GPIO12 或 GPIO13；
- 输出 PWM；
- 使电机运动；
- 使风扇旋转；
- 进行任何带电测试；
- 使用 `sudo` 运行硬件程序。

本次完成的是软件实现和纯软件验证，不是实机验证。

---

## 3. 本次明确不处理的事项

此前代码审核中提出的其他风扇或安全问题，本次暂不修复，也不得借本任务扩大
修改范围。

本次不要主动修改：

- 风扇 PWM 缓升缓降的回调频率问题；
- 风扇急停恢复消息乱序问题；
- 风扇 AUTO 故障后回落到手动心跳的问题；
- 风扇未知电机模式处理问题；
- 风扇底层看门狗参数问题；
- 其他与电机运动速度统一无直接关系的重构。

如果本次修改不可避免地触及这些区域，应停止并在
`docs/LATEST_FEEDBACK.md` 中说明，不得自行扩大任务。

---

## 4. 开始前检查

首先执行：

```bash
git status --short --branch
git rev-parse HEAD
git tag --points-at HEAD
git diff --check
```

记录：

- 当前分支；
- 当前 HEAD；
- 当前 HEAD 是否带标签；
- 用户任务开始前已有修改；
- `docs/NEXT_COMMAND.md` 的状态。

随后阅读：

- `AGENTS.md`
- `docs/FIRST_COMMAND.md`
- `docs/NEXT_COMMAND.md`
- `docs/LATEST_FEEDBACK.md`
- `README.md`
- `src/imu_cybergear_ros2/README.md`
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`
- `imu_motor_controller_node.py`
- `motor_manager.py`
- `keyboard_handler.py`
- `controller_state.py`
- `safety_monitor.py`
- 相关测试
- 相关 launch
- `package.xml`
- `setup.py`

必须先核对当前代码是否仍符合以下情况：

1. `write_target()` 根据 `_current_speeds × command_interval_sec` 限制单次变化；
2. MANUAL 按键每收到一个字符调用一次 `manual_step()`；
3. AUTO 在 IMU 回调中直接调用 `apply_targets()`；
4. `h` 通过周期为 `command_interval_sec` 的定时器反复调用目标写入；
5. `/motors/manual_targets` 当前直接调用 `apply_targets()`；
6. `[` 和 `]` 当前可能直接写入 ±90° 目标；
7. `default_speed` 当前同时用于 CyberGear 目标速度配置和软件步进计算；
8. `manual_step_deg` 当前为每个按键字符的固定角度增量。

如果当前代码与以上描述存在实质差异，先停止实施，将差异写入
`docs/LATEST_FEEDBACK.md`，等待用户确认。

---

## 5. 当前速度差异的原因必须保留在文档中

实现和 README 更新中应准确说明当前差异原因。

### MANUAL

当前手动目标变化近似为：

```text
每个字符的目标增量 = manual_step_deg
平均目标速度 ≈ manual_step_deg × 键盘字符重复频率
```

因此 `manual_loop_hz` 只是键盘读取线程的轮询频率，不等于操作系统实际产生
字符的频率。

### AUTO

当前 AUTO 只有在收到并接受 IMU 消息时才推进一次目标。

因此：

```text
AUTO 目标推进速度
≈ 每次允许变化量 × 实际 IMU 控制消息频率
```

### HOME

当前 `h` 使用固定定时器，每 `command_interval_sec` 推进一步，因此目标推进
稳定，不依赖键盘或 IMU 消息频率。

这就是 `h` 目前明显较快的主要原因。

---

## 6. 新的统一目标模型

新增并明确区分两组目标：

```text
desired_targets
current_targets
```

语义：

- `desired_targets`：各输入源希望电机最终到达的位置；
- `current_targets`：最近一次实际发送给 CyberGear 的软件位置命令。

要求：

- 所有普通运动输入只更新 `desired_targets`；
- 固定周期目标推进器是正常运行时唯一逐步更新 `current_targets` 并发送位置
  命令的路径；
- MANUAL、AUTO、HOME、`/motors/manual_targets`、`[` 和 `]` 不得各自拥有
  不同的正常速度限制路径；
- 软限位在设置 `desired_targets` 时应用；
- 发送前仍进行最终软限位防御；
- 急停、配置、设机械零点和退出等特殊安全/初始化流程可以保留必要的直接硬件
  操作，但不得被普通运动控制复用。

建议在节点初始化后建立：

```python
_current_targets: dict[int, float]
_desired_targets: dict[int, float]
```

初始时两者必须一致，避免激活定时器后出现意外跳变。

---

## 7. 固定周期电机目标推进器

继续使用现有参数：

```yaml
command_interval_sec: 0.02
```

但重新明确其语义：

> 固定电机目标推进定时器的期望周期，而不是由各输入回调自行使用的时间假设。

在节点激活后创建一个固定周期定时器：

```text
周期 = command_interval_sec
```

在停用、cleanup 和 shutdown 时销毁或停止该定时器。

输入回调不得直接推进普通电机位置命令。

### 7.1 使用真实时间差

每次推进使用：

```python
now = time.monotonic()
dt = now - last_motion_tick_time
```

不能始终假设真实周期恰好等于 `command_interval_sec`。

为避免线程暂停或系统卡顿后产生巨大一步，增加参数：

```yaml
motion_dt_max_sec: 0.05
```

计算时：

```text
dt_used = clamp(dt, 0.0, motion_dt_max_sec)
```

第一帧定时器回调应安全初始化时间，不产生异常大步进。

### 7.2 每周期变化量

根据当前运动源选择模式速度：

```text
MANUAL → manual_motion_speed_rad_s
AUTO   → auto_motion_speed_rad_s
HOME   → home_motion_speed_rad_s
```

每个电机还保留当前 SDO 速度上限：

```text
effective_speed =
    min(mode_motion_speed_rad_s, current_motor_speed_limit_rad_s)
```

本周期允许最大变化：

```text
time_step = effective_speed × dt_used

allowed_step = min(
    max_position_step,
    time_step
)
```

新命令：

```text
new_target = current_target + clamp(
    desired_target - current_target,
    -allowed_step,
    +allowed_step
)
```

最终继续应用既有软限位。

### 7.3 到达判定

当：

```text
abs(desired_target - current_target) <= target_reached_tolerance_rad
```

可直接令：

```text
new_target = desired_target
```

增加参数：

```yaml
target_reached_tolerance_rad: 0.001
```

不得使用姿态死区 `deadband_rad` 代替位置推进器的到达容差，因为二者用途不同。

---

## 8. 新增模式速度参数

在 `imu_cybergear_params.yaml` 中增加：

```yaml
# 固定周期目标推进时使用的模式速度。
# 这些是软件目标变化率，不等同于真实负载下测得的机械角速度。
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0

# 定时器实际周期异常时允许使用的最大 dt。
motion_dt_max_sec: 0.05

# 软件目标认为已经到达的容差。
target_reached_tolerance_rad: 0.001
```

三种模式初始设置为相同的 `4.0 rad/s`，目的是让三种模式的软件目标推进速度
大致一致。

`4.0 rad/s` 只是初始候选值，尚未经过本轮实机验证。

不得把它描述为已验证安全速度。

### 8.1 `default_speed` 的新语义

保留：

```yaml
default_speed: 10.0
```

但文档和代码注释应明确：

- 它是启动时写给 CyberGear 的位置模式目标速度上限；
- 它也是每个电机的硬件/底层速度上限初值；
- 普通软件目标推进速度由三个新模式速度参数决定；
- 实际软件推进速度不会超过当前电机速度上限。

### 8.2 `+` 和 `-`

保留现有按键兼容性：

- `+` 提高当前选中电机的速度上限；
- `-` 降低当前选中电机的速度上限。

目标推进器使用：

```text
min(模式速度, 当前电机速度上限)
```

因此：

- 当电机速度上限低于模式速度时，`+/-` 会直接影响该电机运动速度；
- 当电机速度上限已经高于模式速度时，继续增加不会超过模式速度参数；
- 日志必须明确显示“电机速度上限”和当前模式速度，避免让用户误以为
  `+` 一定会继续提高运动速度。

不得删除现有：

```yaml
manual_speed_min
manual_speed_max
manual_speed_step
```

除非代码检查证明它们可以在保持兼容的情况下被更清晰地重命名。若需要破坏性
重命名，应停止并报告，不得自行实施。

---

## 9. MANUAL 键盘目标更新

### 9.1 单次轻按

保留现有参数：

```yaml
manual_step_deg: 3.0
```

重新定义为：

> 一个不属于连续重复序列的单次按键，对 `desired_target` 增加的精细步进角度。

单次按键：

```text
desired_target += direction × manual_step_deg
```

然后应用软限位。

单次按键不得直接写 CyberGear 位置。

这样仍保留轻按一次约 3° 的精细调节能力。

### 9.2 长按和重复字符

为了降低长按速度对操作系统字符重复频率的依赖，增加：

```yaml
manual_repeat_gap_sec: 0.8
manual_repeat_dt_max_sec: 0.08
```

为每个电机和方向维护上一条相同运动按键的接收时间。

如果某个按键事件不属于连续重复序列：

```text
增量 = manual_step_deg
```

如果同一电机、同一方向的字符在 `manual_repeat_gap_sec` 内再次到达，则：

```text
event_dt = 当前接收时间 - 上一次相同按键接收时间

repeat_dt = clamp(
    event_dt,
    0.0,
    manual_repeat_dt_max_sec
)

增量 = manual_motion_speed_rad_s × repeat_dt
```

再应用：

- 当前电机速度上限；
- `max_position_step`；
- 电机软限位。

目标是使稳定重复阶段的平均期望目标变化率近似：

```text
manual_motion_speed_rad_s
```

而不是：

```text
manual_step_deg × 某台机器的键盘重复频率
```

### 9.3 手动输入安全要求

- 不得在没有新字符时持续无限增加目标；
- 终端没有可靠 key-up 事件，因此不能把单个字符理解为永久按住；
- 每个字符只产生有限的期望目标增量；
- 松开按键、字符停止后，`desired_target` 不再继续变化；
- 推进器可以继续把 `current_target` 追到最后一个有限的
  `desired_target`，随后停止；
- 换方向时重置对应重复序列；
- 切换电机时不复用另一个电机的重复时间；
- 错误按键不得刷新运动重复时间；
- 进入 AUTO、HOME、急停、停用或退出时清除手动重复状态。

### 9.4 快速反向

同一电机从正方向按键切换为负方向按键时：

- 取消上一方向的重复序列；
- 新方向的第一次按键按 `manual_step_deg` 处理；
- 不允许把上一方向的大时间间隔用于计算反方向大步长。

---

## 10. `/motors/manual_targets`

保留现有接口和消息类型：

```text
/motors/manual_targets
std_msgs/msg/Float64MultiArray
```

行为改为：

- 只在 MANUAL 模式接受；
- 校验长度；
- 校验所有元素均为有限值；
- 按 `motor_ids` 顺序更新全部 `desired_targets`；
- 应用软限位；
- 不直接调用普通位置写入；
- 使用 `manual_motion_speed_rad_s` 由固定推进器逐步逼近；
- 收到新的绝对目标时停止 HOME；
- 清除键盘重复序列，避免键盘旧状态继续影响该目标。

错误消息：

- 不进行部分更新；
- 不改变任何 `desired_target`；
- 不刷新任何运动状态。

---

## 11. AUTO 模式

IMU 回调继续负责：

- 四元数校验；
- roll/pitch 解析；
- 轴向修正；
- 统一零点扣除；
- 相对姿态发布；
- 姿态死区；
- 电机方向映射；
- ±90° 控制限制；
- 软限位目标计算。

但 AUTO 回调改为：

```text
计算 targets
→ 更新 desired_targets
→ 更新时间戳
```

不得在 IMU 回调中直接调用正常电机位置写入。

固定推进器继续在两帧 IMU 消息之间逼近最近的有效姿态目标。

这样：

- 快速倾斜 IMU 时，电机以 `auto_motion_speed_rad_s` 限速追赶；
- IMU 消息频率不再直接决定每秒允许推进多少次；
- 缓慢倾斜 IMU 时，目标本身变化慢，电机仍会自然缓慢跟随；
- IMU 看门狗和 AUTO 退出行为保持原有安全语义；
- IMU 超时后不得继续向旧 AUTO 目标运动。

### 11.1 AUTO 超时

当现有 IMU 看门狗使控制器退出 AUTO 时：

- 立即停止继续追赶旧 AUTO `desired_targets`；
- 把 `desired_targets` 同步为当前已发送的 `current_targets`；
- 保持当前位置；
- 不得继续完成尚未追上的旧姿态目标；
- 保持现有从 AUTO 切回 MANUAL 的行为；
- 不得削弱现有风扇 AUTO 清除和安全行为。

### 11.2 切换到 AUTO

从 MANUAL 切换到 AUTO 时：

- 取消 HOME；
- 清除手动按键重复状态；
- 在收到新的有效 IMU 姿态前，`desired_targets` 保持为
  `current_targets`；
- 不得使用模式切换前缓存的陈旧姿态产生突然运动；
- 收到新有效姿态后才更新 AUTO `desired_targets`。

如当前代码已经通过其他序列号或时间戳保证新姿态，请复用，不要重复建立不一致
机制。

---

## 12. `h` 自动回零

删除 HOME 独立反复调用 `write_target()` 的快速定时器路径。

`h` 改为：

1. 检查控制器处于可以运动的正常状态；
2. 如果当前为 AUTO，先显式切换到 MANUAL；
3. 停止使用 AUTO 姿态目标；
4. 清除手动按键重复状态；
5. 将全部 `desired_targets` 设置为 `0.0`，并应用软限位；
6. 设置当前运动源为 `HOME`；
7. 由统一目标推进器使用 `home_motion_speed_rad_s` 回零；
8. 全部电机到达目标后结束 HOME；
9. 回零完成后保持 MANUAL，并保持零目标。

因此 `h` 不得创建自己的运动定时器。

可以保留：

```text
go_all_to_zero()
stop_auto_zero()
```

等现有方法名以减少调用方修改，但内部语义应改为启停 HOME 目标状态，不再管理
独立 ROS 定时器。

### 12.1 HOME 被其他操作中断

以下操作应取消 HOME：

- 任意有效 MANUAL 运动按键；
- 新的 `/motors/manual_targets`；
- `[` 或 `]`；
- 切换到 AUTO；
- 急停；
- 节点停用；
- cleanup；
- shutdown。

取消时不得突然写入额外位置，只改变运动源和 `desired_targets`。

### 12.2 HOME 速度

当三个模式速度参数都为 `4.0` 时，相同初始目标误差下：

- MANUAL 目标追赶；
- AUTO 目标追赶；
- HOME 回零；

应使用相同的软件位置变化率上限。

不得保留 HOME 特有的更快步进。

---

## 13. `[` 和 `]` 快捷目标

现有 `[` 和 `]` 快捷键保持兼容，但改为：

- 只在 MANUAL 模式使用；
- 设置选中电机的 `desired_target` 为正或负 90°；
- 应用该电机软限位；
- 取消 HOME；
- 清除对应手动重复状态；
- 由统一推进器使用 `manual_motion_speed_rad_s` 运动；
- 不得直接一次性向 CyberGear 写入完整 ±90° 目标。

日志应使用“设置期望目标”，不能误写为“已经到达”。

---

## 14. 正常位置写入职责拆分

当前 `write_target()` 同时：

- 计算单步限速；
- 更新 `_current_targets`；
- 写入 SDO。

实施后应清楚拆分职责。

建议至少区分：

```text
set_desired_target()
advance_targets()
write_command_target()
```

### `set_desired_target()`

负责：

- 输入有限值校验；
- 软限位；
- 更新 `desired_targets`；
- 不访问 CAN。

### `advance_targets()`

负责：

- 根据运动源选取速度；
- 使用真实 `dt`；
- 应用电机速度上限；
- 应用 `max_position_step`；
- 逼近 `desired_targets`；
- 调用最终命令写入。

核心数学计算应提取为纯函数，不能只存在于 ROS 定时器回调中。

### `write_command_target()`

负责：

- 最终有限值检查；
- 最终软限位；
- 向 CyberGear 写入本周期已经算好的位置；
- 更新 `current_targets`；
- 更新相关状态和时间。

不得在这里再次乘以 `command_interval_sec` 做第二层普通速度限制，否则会出现
双重限速。

如果硬件写入失败，应保持当前错误处理语义。若计划改变
`current_targets` 在写失败时的更新顺序，必须增加测试并在反馈中说明。

---

## 15. 运动源和状态

建议定义清晰的内部运动源，例如：

```text
IDLE
MANUAL
AUTO
HOME
```

该运动源不是新的公共电机控制模式，不需要改变现有：

```text
MANUAL
AUTO
EMERGENCY_STOP
DISABLED
ERROR
```

公共状态话题语义。

映射要求：

- 公共 MANUAL 可对应内部 IDLE、MANUAL 或 HOME；
- 公共 AUTO 对应内部 AUTO；
- 急停、DISABLED、ERROR 不允许普通目标推进；
- HOME 完成后进入内部 IDLE，公共模式保持 MANUAL。

不要为本任务破坏 `/motors/control_mode` 已有稳定值。

---

## 16. 安全行为

### 16.1 急停

收到急停时：

- 立即停止正常推进定时器的电机写入；
- 取消 HOME；
- 清除手动重复状态；
- 把 `desired_targets` 同步为当前 `current_targets`；
- 保留现有电机停止、状态切换和系统 `/e_stop` 行为；
- 不得通过运动速度限制延迟急停。

### 16.2 从急停恢复

恢复后：

- 进入 MANUAL；
- `desired_targets = current_targets`；
- 运动源为 IDLE；
- 不恢复急停前的 MANUAL、AUTO 或 HOME 目标；
- 等待新的操作指令。

### 16.3 Lifecycle

停用、cleanup 和 shutdown 时：

- 取消推进定时器；
- 取消 HOME；
- 清除手动重复状态；
- 不保留会在重新激活后立即执行的旧期望目标；
- 保留既有真实硬件停止和资源释放行为。

### 16.4 参数非法

以下参数必须是有限值：

- `command_interval_sec`
- `motion_dt_max_sec`
- `target_reached_tolerance_rad`
- `manual_motion_speed_rad_s`
- `auto_motion_speed_rad_s`
- `home_motion_speed_rad_s`
- `manual_step_deg`
- `manual_repeat_gap_sec`
- `manual_repeat_dt_max_sec`
- `max_position_step`
- `default_speed`
- 手动速度上下限和步长

并满足：

```text
command_interval_sec > 0
motion_dt_max_sec >= command_interval_sec
target_reached_tolerance_rad >= 0

manual_motion_speed_rad_s > 0
auto_motion_speed_rad_s > 0
home_motion_speed_rad_s > 0

manual_step_deg > 0
manual_repeat_gap_sec > 0
manual_repeat_dt_max_sec > 0
manual_repeat_dt_max_sec <= manual_repeat_gap_sec

max_position_step > 0

default_speed > 0
manual_speed_min > 0
manual_speed_max >= manual_speed_min
manual_speed_step > 0
```

参数非法时应在配置阶段明确失败，不得启动正常电机控制。

---

## 17. 推荐初始参数

本次建议的初始配置：

```yaml
# CyberGear 位置模式速度上限初值。
default_speed: 10.0

# 固定电机目标推进周期。
command_interval_sec: 0.02

# 任何单周期允许的绝对位置变化保护上限。
max_position_step: 0.4

# 三种普通运动的软件目标速度。
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0

# 定时器延迟保护。
motion_dt_max_sec: 0.05

# 目标到达容差。
target_reached_tolerance_rad: 0.001

# 单次轻按的精细步进。
manual_step_deg: 3.0

# 同一按键连续重复识别参数。
manual_repeat_gap_sec: 0.8
manual_repeat_dt_max_sec: 0.08
```

不得擅自把三种模式设为当前理论最大 `10.0 rad/s`。

用户完成低速实机验证后，可以通过 YAML 逐步调整三种模式速度。

---

## 18. 需要新增或修改的测试

测试必须完全隔离真实 CAN、电机、IMU、GPIO 和风扇硬件。

核心推进计算应提取为纯函数或纯状态类进行测试。

### 18.1 目标推进数学

至少测试：

- 正方向推进；
- 负方向推进；
- 到达目标时不越过；
- 三种模式速度选择；
- 三种模式相同参数时，相同距离和时间产生相同结果；
- `max_position_step` 成为最终单周期上限；
- 当前电机速度上限低于模式速度；
- 当前电机速度上限高于模式速度；
- `dt=0`；
- 正常 `dt`；
- `dt` 超过 `motion_dt_max_sec`；
- 到达容差；
- 软限位；
- `NaN`；
- `Inf`；
- 非法负速度；
- 非法参数关系。

### 18.2 固定周期和回调解耦

至少测试：

- AUTO 姿态回调只更新 `desired_targets`；
- AUTO 姿态回调不直接写普通位置命令；
- 连续收到多条相同姿态消息，不会因回调数量增加单周期位置变化；
- 在相同经过时间内，10 Hz、20 Hz 和 50 Hz 姿态输入得到相同的最大目标追赶
  速度；
- 固定推进器可以在两条姿态消息之间继续追赶最后一个新鲜目标；
- IMU 超时后立即停止追赶旧 AUTO 目标。

### 18.3 MANUAL 单次按键

至少测试：

- 第一次 `w/s/a/d/i/k/j/l` 使用 `manual_step_deg`；
- 单次按键只更新对应电机；
- 单次按键不直接写硬件；
- 单次按键应用软限位；
- 松开后没有新字符，不继续增加 `desired_target`。

### 18.4 MANUAL 连续重复

使用可控的单调时间测试：

- 相同电机和方向的重复字符；
- 不同重复间隔；
- 重复间隔小于 `manual_repeat_gap_sec`；
- 重复间隔大于该值后重新按轻按处理；
- `event_dt` 被 `manual_repeat_dt_max_sec` 限制；
- 20 Hz 和 25 Hz 重复流的平均期望速度接近
  `manual_motion_speed_rad_s`；
- 快速重复不会超过模式速度推进；
- 改变方向会重置重复状态；
- 改变电机会使用独立状态；
- 非运动按键不刷新重复时间；
- 模式切换清除重复状态；
- 急停清除重复状态。

测试允许存在由首个轻按造成的小固定差异，但稳定重复阶段必须证明平均速度不再
简单等于固定角度乘以字符频率。

### 18.5 `/motors/manual_targets`

至少测试：

- 正确长度更新全部 `desired_targets`；
- 不直接写普通硬件位置；
- 错误长度整条拒绝；
- 任一 `NaN` 整条拒绝；
- 任一 `Inf` 整条拒绝；
- 软限位；
- 取消 HOME；
- 清除键盘重复状态；
- 非 MANUAL 模式拒绝。

### 18.6 AUTO

至少测试：

- IMU 目标更新到 `desired_targets`；
- 电机方向关系保持不变；
- 电机死区保持不变；
- ±90° 限制保持不变；
- 软限位保持不变；
- AUTO 使用 `auto_motion_speed_rad_s`；
- AUTO 切换后等待新姿态；
- AUTO 超时同步 desired/current 并保持当前位置；
- AUTO 退出不会继续追赶旧姿态目标。

### 18.7 HOME

至少测试：

- `h` 设置所有 `desired_targets=0`；
- `h` 使用 `home_motion_speed_rad_s`；
- HOME 不创建独立运动定时器；
- HOME 和 AUTO 使用相同参数时，相同距离下的软件推进时间一致；
- HOME 完成后公共模式为 MANUAL；
- HOME 完成后内部运动源为 IDLE；
- MANUAL 按键取消 HOME；
- `/motors/manual_targets` 取消 HOME；
- `[` 和 `]` 取消 HOME；
- 切换 AUTO 取消 HOME；
- 急停取消 HOME；
- 在 AUTO 中按 `h` 先安全切换为 MANUAL；
- HOME 不与 IMU 回调争用目标。

### 18.8 快捷目标

至少测试：

- `[` 设置正向期望目标；
- `]` 设置负向期望目标；
- 应用软限位；
- 不直接跳写完整 ±90°；
- 使用 MANUAL 速度推进。

### 18.9 Lifecycle 和急停

至少测试：

- 激活时创建一个推进定时器；
- 重复激活不创建多个定时器；
- 停用时停止推进；
- cleanup 销毁推进资源；
- shutdown 销毁推进资源；
- 急停后不进行普通位置推进；
- 恢复后不恢复旧目标。

### 18.10 回归测试

必须保持以下行为和测试通过：

- IMU 协议和相对姿态；
- 电机方向；
- 软限位；
- 键盘映射；
- `/motors/manual_targets` 接口名称和类型；
- `/motors/control_mode`；
- IMU 看门狗；
- 电机急停；
- 风扇 AUTO 与电机模式同步；
- 现有风扇控制测试；
- launch 语法和结构测试。

---

## 19. 建议文件范围

预计主要修改：

- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py`
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`
- `src/imu_cybergear_ros2/README.md`
- 根目录 `README.md`
- `src/imu_cybergear_ros2/test/` 中现有或新增的软件测试
- 必要的 launch 静态测试

如果纯推进逻辑较复杂，可以新增一个不依赖 ROS 和硬件的模块，例如：

```text
motor_motion.py
```

该模块可包含：

- 模式速度选择；
- 单周期目标推进；
- 手动重复增量计算；
- 参数校验；
- 到达判断。

是否新增该文件由当前结构决定，但不得进行与任务无关的大型重构。

原则上不应修改：

- 风扇控制算法；
- 风扇状态机；
- 风扇 GPIO；
- 电机 ID；
- 电机符号；
- 电机软限位；
- CAN 配置；
- IMU 安装方向参数。

---

## 20. 实施顺序

按以下顺序执行：

### 步骤 1：静态确认

确认现有三种速度路径和调用关系。

### 步骤 2：纯推进逻辑

先实现纯函数或纯状态类，并完成针对性测试。

### 步骤 3：desired/current 模型

加入 `desired_targets`，确保初始化时与 `current_targets` 一致。

### 步骤 4：统一定时器

实现固定周期推进器，并正确处理真实 `dt`、Lifecycle 和急停。

### 步骤 5：迁移输入源

依次迁移：

1. `/motors/manual_targets`
2. 键盘单次和重复输入
3. `[` 和 `]`
4. AUTO IMU 目标
5. `h` HOME

每迁移一条路径后运行相关软件测试。

### 步骤 6：清理旧路径

删除或停用：

- HOME 独立运动定时器；
- AUTO 回调中的正常直接位置推进；
- MANUAL 普通按键中的正常直接位置写入；
- 快捷 ±90° 的正常直接位置跳写。

必须确认配置、设机械零点、急停和关闭等特殊硬件流程没有被错误删除。

### 步骤 7：文档

更新参数、速度公式、按键行为和调节方法。

### 步骤 8：完整软件回归

检查测试不会访问硬件后，执行完整构建和测试。

---

## 21. 构建与测试限制

运行前必须审查测试代码、fixture 和导入链，确认不会：

- 创建真实 CAN 后端；
- 初始化 CyberGear；
- 访问真实 IMU；
- 打开串口；
- 初始化 GPIO；
- 输出 PWM；
- 启动 ROS 2 硬件节点或 launch。

确认安全后，可以运行：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

随后：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash

colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup

colcon test-result --verbose
```

并按实际文件名运行新增的纯软件 pytest：

```bash
python3 -m pytest <实际安全测试文件> -v
```

本次禁止运行：

```bash
ros2 run ...
ros2 launch ...
ros2 topic ...
ros2 service ...
sudo ...
./scripts/setup_can.sh ...
```

---

## 22. README 更新要求

根 README 和电机包 README 至少说明：

### 22.1 三类速度参数

```yaml
manual_motion_speed_rad_s
auto_motion_speed_rad_s
home_motion_speed_rad_s
```

说明这些是软件目标位置变化率，不一定等于负载下实际测得的机械角速度。

### 22.2 共同推进公式

```text
allowed_step =
min(
    max_position_step,
    min(mode_speed, motor_speed_limit) × dt
)
```

### 22.3 `default_speed`

说明它是 CyberGear 位置模式速度上限初值，不再直接等同于所有模式的软件目标
推进速度。

### 22.4 `+/-`

说明：

- 改变选中电机的速度上限；
- 低于模式速度时会限制运动；
- 高于模式速度后继续增加不会突破模式速度参数。

### 22.5 手动按键

说明：

- 轻按一次使用 `manual_step_deg`；
- 长按产生的重复字符按实际间隔换算为目标增量；
- 稳定重复阶段尽量接近 `manual_motion_speed_rad_s`；
- 终端不存在可靠 key-up，因此单个字符只产生有限运动，不会永久持续。

### 22.6 AUTO

说明：

- IMU 回调只更新期望目标；
- 固定推进器按 `auto_motion_speed_rad_s` 追赶；
- 缓慢倾斜时运动仍由姿态本身变化速度决定；
- 快速倾斜时由 AUTO 速度上限约束。

### 22.7 HOME

说明：

- `h` 会使用统一推进器；
- 如果在 AUTO 中按 `h`，会退出 AUTO并进入 MANUAL 回零；
- HOME 使用 `home_motion_speed_rad_s`；
- HOME 不再具有独立快速路径。

### 22.8 当前验证状态

明确写明：

- 本次只是软件实现和纯软件测试；
- 新的 `4.0 rad/s` 三模式速度尚未实机验证；
- `v0.3.0` 标签不包含本次改进；
- 后续需要在低速、固定机器人、逐电机条件下重新实机验证；
- 未经用户授权不得运行硬件验证。

---

## 23. 不得破坏的兼容性

必须保持：

- `w/s/a/d/i/k/j/l` 键位；
- `h` 键；
- `[` 和 `]` 键；
- `+` 和 `-` 键；
- `m` 模式切换；
- `/motors/manual_targets` 名称和类型；
- `/motors/control_mode` 名称和稳定值；
- `/imu/relative_roll_pitch`；
- 电机 ID；
- 电机方向；
- 电机软限位；
- AUTO 姿态映射；
- IMU 零点；
- 电机急停；
- 风扇与电机模式联动；
- `v0.3.0` 标签内容。

允许改变的是普通运动命令在内部如何平滑逼近期望目标。

---

## 24. 停止并报告的条件

出现以下任一情况时，不得继续实施，覆盖
`docs/LATEST_FEEDBACK.md` 报告并等待用户：

- 当前代码与本任务的基础判断明显不一致；
- 必须改变电机 ID、方向或软限位；
- 必须访问真实硬件才能继续；
- 无法在不连接 CAN 的情况下测试核心推进逻辑；
- 新设计会破坏现有公共接口；
- 必须修改风扇状态机才能完成；
- 用户已有修改与任务冲突；
- 构建失败来自与本任务无关的大范围问题；
- 需要移动或重建 `v0.3.0` 标签；
- 需要执行带电测试。

---

## 25. `docs/LATEST_FEEDBACK.md` 输出要求

完成后覆盖：

```text
docs/LATEST_FEEDBACK.md
```

标题建议：

```markdown
# 最新反馈：统一电机运动速度的软件实现
```

至少包含：

1. 当前分支和 HEAD；
2. `v0.3.0` 标签与当前 HEAD 的关系；
3. 任务开始时用户已有修改；
4. 修改前 MANUAL、AUTO 和 HOME 的速度路径；
5. 为什么原来的 `h` 更快；
6. 最终统一架构；
7. `desired_targets` 与 `current_targets` 的语义；
8. 固定推进器的周期和真实 `dt` 处理；
9. 三种模式速度参数；
10. `default_speed` 的最终语义；
11. `+/-` 的最终语义；
12. 手动轻按和连续重复算法；
13. AUTO 目标更新方式；
14. HOME 回零方式；
15. AUTO 中按 `h` 的最终行为；
16. `/motors/manual_targets` 的最终行为；
17. `[` 和 `]` 的最终行为；
18. Lifecycle 和急停行为；
19. 实际修改文件；
20. 每个文件的修改目的；
21. 新增和修改的参数；
22. 已执行的全部命令；
23. 构建结果；
24. 测试总数；
25. 通过、失败、跳过数量；
26. 每组关键测试结果；
27. 未执行的测试及原因；
28. 是否访问 IMU；
29. 是否访问 CAN；
30. 是否访问 GPIO 或 PWM；
31. 电机和风扇是否通电；
32. 剩余风险；
33. 实机验证建议，但不得直接要求用户通电；
34. `git diff --stat`；
35. `git diff --check`；
36. 最终 `git status --short --branch`。

必须明确写明：

```text
本次没有运行 ROS 2 节点或 launch。
本次没有访问 IMU、CAN、GPIO、PWM 或真实串口。
4 个微电机和 2 个风扇均未因本任务被控制。
本次完成的是软件实现和纯软件验证，不是实机验证。
v0.3.0 标签未被修改。
```

---

## 26. 最终检查

完成后执行：

```bash
git diff --check
git diff --stat
git status --short --branch
```

不要：

- commit；
- push；
- 创建 tag；
- 修改 tag；
- 运行硬件节点；
- 进行实机测试；
- 修改 `docs/NEXT_COMMAND.md`；
- 修改 `AGENTS.md`，除非用户另行批准。

完成反馈后停止，等待用户审核和后续低速实机验证授权。