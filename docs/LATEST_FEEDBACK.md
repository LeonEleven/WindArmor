# 最新反馈：阶段 2 软件实现与纯软件验证

> 本文件只保留最近一次反馈。
>
> 日期：2026-07-29

## 1. 结论

已按 `docs/NEXT_COMMAND.md` 完成阶段 2 的软件实现和纯软件验证：

- 新增统一相对姿态与电机公开模式；
- 键盘和服务使用同一 IMU 归零方法；
- 新增无硬件 I/O 的风扇命令管理器和纯 Python 状态机；
- 公共手动命令不再直接进入 GPIO 底层节点；
- 补齐风扇 AUTO、双通道新鲜度、急停锁存和恢复条件；
- 正式风扇 launch 只有一个管理器和一个底层控制器；
- 三个包构建成功；
- 最终共 100 项测试，全部通过。

当前稳定发布仍为 `v0.2.1`；本次实现是 `v0.3.0` 候选功能，未修改包版本号、
Git 标签或受保护硬件参数。

本次没有运行任何 ROS 2 节点或 launch。
本次没有访问 IMU、CAN、GPIO、PWM 或真实串口。
4 个微电机和 2 个风扇均未通电、未控制、未影响。
本次完成的是软件实现和纯软件验证，不是实机验证。

## 2. Git 基线和用户已有修改

- 分支：`master`
- HEAD：`bce019bfeab25e5b04c1fdfa39734aba49b7e4c1`
- HEAD 上的稳定标签：`v0.2.1`
- 任务开始时：

```text
## master...origin/master
 M docs/NEXT_COMMAND.md
?? docs/LATEST_FEEDBACK.md
```

`docs/NEXT_COMMAND.md` 是用户在任务开始前已有的修改，本次只读取、未修改。
`docs/LATEST_FEEDBACK.md` 是用户指定的反馈文件，本次已覆盖，旧反馈未保留。
未 checkout、reset、clean 或覆盖用户已有修改。

## 3. 实际修改文件与目的

### 项目文档

- `README.md`
  - 说明 `v0.3.0` 候选状态、正式控制路径、AUTO、急停恢复和未实机验证事项。
- `docs/LATEST_FEEDBACK.md`
  - 覆盖写入本次阶段 2 反馈。

### IMU 与电机包

- `src/imu_cybergear_ros2/README.md`
  - 补充统一姿态、零点代次、电机模式和 MANUAL 恢复语义。
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`
  - 增加姿态、零点代次、电机模式话题和心跳/归零超时参数。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_protocol.py`
  - 增加四元数校验/归一化、角度归一化和统一相对姿态纯函数。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/controller_state.py`
  - 增加状态变化回调和稳定公开模式映射。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`
  - 发布统一相对姿态、零点代次、电机模式及心跳；统一归零入口。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py`
  - 键盘 `z` 改用统一归零；恢复成功后才进入 MANUAL。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py`
  - 恢复方法返回真实成功/失败结果。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py`
  - `/enable_motor=true` 仅在恢复成功后进入 MANUAL，失败时保持原安全状态。
- `src/imu_cybergear_ros2/package.xml`
  - 增加 `geometry_msgs` 依赖；版本号未变。
- `src/imu_cybergear_ros2/test/test_imu_protocol.py`
  - 覆盖有效/无效四元数、方向、零点和 ±π 跨越。
- `src/imu_cybergear_ros2/test/test_control_interfaces.py`
  - 静态覆盖统一姿态处理顺序、header、归零入口、QoS 和心跳结构。
- `src/imu_cybergear_ros2/test/test_controller_state.py`
  - 纯替身覆盖公开模式映射和电机恢复成功/失败。

### 风扇包

- `src/windarmor_fan_controller/windarmor_fan_controller/fan_control.py`
  - 新增无 ROS、无硬件依赖的配置校验、公式、迟滞、限速和完整状态机。
- `src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py`
  - 新增无 GPIO/CAN/串口的公共命令仲裁 ROS 节点。
- `src/windarmor_fan_controller/windarmor_fan_controller/fan_node.py`
  - 底层只接收内部命令；增加 enabled 状态、stop/enable/e-stop 锁存。
- `src/windarmor_fan_controller/windarmor_fan_controller/pwm.py`
  - 增加可独立测试的底层命令门和看门狗状态。
- `src/windarmor_fan_controller/config/fan_params.yaml`
  - 增加管理器参数和 enabled 状态心跳参数；GPIO 映射未变。
- `src/windarmor_fan_controller/launch/fans.launch.py`
  - 正式启动一个管理器和一个底层控制器。
- `src/windarmor_fan_controller/setup.py`
  - 注册 `fan_command_manager` 入口；版本号未变。
- `src/windarmor_fan_controller/package.xml`
  - 增加 `geometry_msgs` 依赖；版本号未变。
- `src/windarmor_fan_controller/test/test_fan_control.py`
  - 覆盖公式、状态机、超时、AUTO、急停和恢复。
- `src/windarmor_fan_controller/test/test_pwm.py`
  - 覆盖底层命令门、重新启用和看门狗。
- `src/windarmor_fan_controller/test/test_interface_routing.py`
  - 静态确认单一内部命令发布者、底层路由、最终限幅和清理路径。

### Bringup

- `src/windarmor_bringup/launch/windarmor.launch.py`
  - 统一系统复用 `fans.launch.py`，并覆盖统一手动安全参数。
- `src/windarmor_bringup/test/test_launch_syntax.py`
  - 检查 launch 语法、复用关系和不重复创建底层节点。

未修改 `AGENTS.md`、`docs/FIRST_COMMAND.md`、`docs/NEXT_COMMAND.md`、包版本号、
标签、GPIO12/13 用途或以下受保护参数：

```yaml
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
left_gpio: 12
right_gpio: 13
```

## 4. 最终架构

```text
imu_motor_controller_node
  ├─ /imu/relative_roll_pitch
  ├─ /imu/zero_generation
  └─ /motors/control_mode

/fans/pwm
/fans/left/pwm
/fans/right/pwm
/imu/relative_roll_pitch
/imu/zero_generation
/motors/control_mode
/fans/enabled
/e_stop
        ↓
fan_command_manager（无硬件 I/O）
        ↓
/fans/command_pwm（内部唯一正常命令）
        ↓
fan_controller（最终限幅、底层看门狗、锁存、GPIO 清理）
        ↓
GPIO12 / GPIO13
```

`fan_controller` 不再订阅三个公共手动话题。正式 launch 中只有
`fan_command_manager` 发布内部命令，且只有一个 `fan_controller`。

## 5. 新增或改变的接口

### 新增

| 接口 | 类型 | 语义 |
|---|---|---|
| `/imu/relative_roll_pitch` | `geometry_msgs/Vector3Stamped` | x/y 为相对 roll/pitch（rad），z=0，保留原 header |
| `/imu/zero_generation` | `std_msgs/UInt64` | 每次成功统一归零递增 |
| `/motors/control_mode` | `std_msgs/String` | MANUAL/AUTO/EMERGENCY_STOP/DISABLED/ERROR |
| `/fans/command_pwm` | `std_msgs/Int32MultiArray` | 管理器到硬件底层的内部双路命令 |
| `/fans/enabled` | `std_msgs/Bool` | 底层是否接受新命令 |
| `/fans/auto_enable` | `std_srvs/SetBool` | 显式启停风扇 AUTO |
| `/fans/auto_enabled` | `std_msgs/Bool` | AUTO 请求是否仍被保留 |
| `/fans/auto_active` | `std_msgs/Bool` | AUTO 条件成立且已有启用后新姿态 |
| `/fans/auto_target_pwm` | `std_msgs/Int32MultiArray` | 变化率限制前的自动目标 |
| `/fans/control_state` | `std_msgs/String` | 风扇管理器稳定状态 |

状态话题使用 `RELIABLE + TRANSIENT_LOCAL + KEEP_LAST(1)`；姿态和命令使用可靠、
volatile、小队列 QoS。新鲜度使用 `time.monotonic()`。

### 保持兼容但路由或语义强化

- `/fans/pwm`、`/fans/left/pwm`、`/fans/right/pwm`
  - 名称和消息类型不变，只进入管理器，不再直达 GPIO 节点。
- `/fans/stop`
  - 仍归底层所有；现在立即停止并锁存 disabled。
- `/fans/enable`
  - `false` 立即停止并锁存；`true` 保持停止、清除旧命令并等待新命令。
- `/enable_motor=true`
  - 恢复成功后进入 MANUAL；失败不离开原安全状态；不直接进入 AUTO。
- `/imu/set_zero` 和键盘 `z`
  - 现在共用同一方法、有效性和新鲜度规则。

## 6. 新增和修改的参数

### IMU/电机控制器

```yaml
relative_attitude_topic: "/imu/relative_roll_pitch"
imu_zero_generation_topic: "/imu/zero_generation"
motor_mode_topic: "/motors/control_mode"
motor_mode_publish_rate_hz: 5.0
imu_zero_timeout_sec: 1.0
```

### 风扇管理器

```yaml
min_pwm_us: 800
max_pwm_us: 2200
fan_stop_pwm_us: 800
fan_start_pwm_us: 1200
fan_auto_max_pwm_us: 1400
auto_enabled_at_start: false
fan_deadband_on_deg: 5.0
fan_deadband_off_deg: 3.0
fan_full_scale_deg: 45.0
control_rate_hz: 20.0
status_publish_rate_hz: 5.0
rise_step_pwm_us: 10
fall_step_pwm_us: 20
imu_timeout_sec: 0.2
manual_command_timeout_sec: 0.5
motor_mode_timeout_sec: 1.0
fan_enabled_timeout_sec: 1.0
require_motor_mode_for_manual: false
```

### 风扇底层

```yaml
enabled_status_publish_rate_hz: 5.0
```

`fans.launch.py` 默认 `require_motor_mode_for_manual=false`；
`windarmor.launch.py` 覆盖为 `true`。

## 7. 相对姿态和统一归零

有效 IMU 姿态依次经过：

1. 检查 x/y/z/w 均为有限值；
2. 拒绝零范数或小于阈值的范数；
3. 归一化四元数；
4. 转换 roll/pitch；
5. 应用 roll/pitch axis sign；
6. 更新最新有效绝对姿态和本地单调时间；
7. 扣除统一零点；
8. 把相对差归一化到 `[-π, π]`；
9. 保留原 IMU header，发布 rad 单位相对姿态；
10. 仅在电机 AUTO 时继续死区、±90°、方向、软限位和变化率处理。

MANUAL 下仍发布相同的统一相对姿态，但不产生电机 AUTO 目标。无效四元数不会
更新最新有效姿态、有效时间或发布消息。

归零成功会记录当前有效姿态、序列号并递增零点代次。风扇管理器收到任何新的
零点代次（包括启动后首次可信代次）都会丢弃此前姿态、清除 AUTO 并立即停止；
必须收到归零后的新姿态且由用户重新显式启用 AUTO。

## 8. 电机模式状态

内部状态映射：

```text
MANUAL_RUNNING   -> MANUAL
AUTO_RUNNING     -> AUTO
EMERGENCY_STOP   -> EMERGENCY_STOP
ERROR            -> ERROR
其他内部状态或 Lifecycle inactive -> DISABLED
```

状态变化立即发布，并以默认 5 Hz 心跳发布。QoS 为 reliable、
transient-local、depth 1。风扇管理器不无限信任缓存消息，默认 1 秒超时。

## 9. 手动和自动仲裁

- pair 消息必须恰好两个值，任一越界则整条拒绝且不刷新时间。
- left/right 分别更新各自缓存和本地单调时间，一侧不会为另一侧续期。
- 默认 0.5 秒超时；新鲜侧输出对应手动值，超时侧立即输出 800。
- 至少一侧新鲜为 `MANUAL_ACTIVE`；两侧均无新鲜命令为 `MANUAL_WAITING`。
- AUTO 默认关闭，且必须通过 `/fans/auto_enable=true` 显式申请。
- 申请时要求新鲜电机 AUTO、新鲜 enabled=true、新鲜有效姿态且无急停锁存。
- 成功后进入 `AUTO_WAITING`，清除手动和自动旧缓存并等待服务后的新姿态。
- 服务后新姿态到达才进入 `AUTO_ACTIVE`。
- AUTO 任一条件失效会立即停止并清除请求；条件恢复不会自动重新启用。

## 10. 控制公式、迟滞和变化率

```text
pitch_activity = abs(pitch_deg)
left_roll_activity = max(0, -roll_deg)
right_roll_activity = max(0, roll_deg)
left_activity = max(pitch_activity, left_roll_activity)
right_activity = max(pitch_activity, right_roll_activity)
```

左右分别以 5° 启动、低于 3° 停止，在两阈值之间保持各自迟滞状态。运行状态从
1200 μs 线性映射到 45° 时的 1400 μs；正常每周期最多上升 10 μs、下降
20 μs。急停、disabled、状态/姿态超时、离开 AUTO 或关闭 AUTO 都绕过限速，
立即回到 800 μs。

## 11. 急停锁存和恢复

管理器收到 `/e_stop=true` 后：

- 立即输出双路停止；
- 锁存 `e_stop_latched=true`；
- 清除手动值/时间、姿态值/时间、迟滞、平滑值和 AUTO 请求；
- 进入 `EMERGENCY_STOP`。

底层同时停止、清除命令时间、锁存 disabled 并发布
`/fans/enabled=false`。普通命令不能解除底层锁存。

独立风扇模式要求急停事件之后收到新的 `/fans/enabled=true` 才解除本地锁存。
统一模式还必须在急停事件之后收到新的、新鲜的电机 `MANUAL` 或 `AUTO`；
仅调用 `/fans/enable=true`、电机仍为急停/禁用/错误，或使用急停前旧状态都
不能恢复。恢复后不使用任何旧手动命令、旧姿态或旧 AUTO 请求。

## 12. 风扇状态机

实现以下稳定状态：

- `SAFE_STOP`
- `MANUAL_WAITING`
- `MANUAL_ACTIVE`
- `AUTO_WAITING`
- `AUTO_ACTIVE`
- `DISABLED`
- `EMERGENCY_STOP`

参数非法时节点初始化明确失败；消息非法、状态未知/超时或条件不一致时拒绝
输入或进入停止状态，不产生非停止硬件命令。

## 13. 参数校验

纯配置类检查：

- 所有相关浮点值必须有限；
- `min_pwm_us < max_pwm_us`；
- `0 <= off < on < full_scale`；
- `min <= stop <= start <= auto_max <= max`；
- 上升/下降步长均大于 0；
- IMU、手动、电机模式和 enabled 超时均大于 0。

ROS 管理器还检查控制频率和状态频率大于 0；底层检查 GPIO 不重复、帧宽和
enabled 心跳频率大于 0。底层继续对最终 PWM 做范围限幅。

## 14. 已执行命令与结果

### 只读检查

任务开始及结束期间执行了以下类别的只读命令：

```bash
git status --short --branch
git rev-parse HEAD
git branch --show-current
git describe --tags --exact-match HEAD
git diff
git diff --stat
git diff --check
git diff --name-status
rg --files
rg -n <相关接口、硬件访问、参数和版本模式> <仓库文件>
sed -n <分段范围> <AGENTS.md、FIRST_COMMAND.md、README、NEXT_COMMAND 及源码>
wc -l docs/NEXT_COMMAND.md
```

这些命令只读取仓库和 Git 元数据。

### 静态语法

```bash
python3 -m py_compile \
  <本次修改的 Python 模块和 launch 文件>
```

结果：成功，无输出。该命令没有导入或实例化硬件节点。

### 定向 pytest

首次定向命令错误地用新 `PYTHONPATH` 覆盖了 ROS 2 已设置的路径，在测试收集
阶段因找不到 `std_msgs/rclpy` 停止，未执行测试。修正为保留原
`${PYTHONPATH}` 后：

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=src/imu_cybergear_ros2:src/windarmor_fan_controller:${PYTHONPATH} \
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_imu_protocol.py \
  src/imu_cybergear_ros2/test/test_controller_state.py \
  src/imu_cybergear_ros2/test/test_control_interfaces.py \
  src/windarmor_fan_controller/test/test_fan_control.py \
  src/windarmor_fan_controller/test/test_pwm.py \
  src/windarmor_fan_controller/test/test_fan_keyboard.py \
  src/windarmor_fan_controller/test/test_interface_routing.py \
  src/windarmor_bringup/test/test_launch_syntax.py -v
```

阶段结果：

- 84 项通过；
- 扩展最低覆盖后 99 项通过；
- 再扩展零点首次代次和失败日志测试时，测试替身缺少 `logger.error()`，
  出现 1 项替身失败、99 项通过；
- 补齐替身后最终为 100 项通过。

上述测试只运行纯函数、状态替身、伪终端解析和静态源码/launch AST 检查。
没有构造 `DualFanController`、IMU 驱动节点或电机控制节点。

### 构建与三包回归

执行两轮，最终轮命令为：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup
colcon test-result --verbose
```

最终结果：

```text
Summary: 3 packages finished
Summary: 100 tests, 0 errors, 0 failures, 0 skipped
```

构建和测试命令没有启动节点、执行 launch 或访问设备。

## 15. 测试分组结果

| 分组 | 最终结果 |
|---|---:|
| IMU 协议、四元数和相对姿态纯函数 | 46 项通过 |
| 电机公开状态、恢复替身和接口静态结构 | 8 项通过 |
| 风扇公式、配置、缓存、AUTO、状态机和急停 | 32 项通过 |
| PWM 范围、底层命令门和看门狗 | 5 项通过 |
| 键盘伪终端解析 | 2 项通过 |
| 风扇接口路由与底层静态安全结构 | 5 项通过 |
| Bringup launch AST 与复用结构 | 2 项通过 |
| **合计** | **100 项通过，0 失败，0 错误，0 跳过** |

## 16. 未执行的验证

以下均未执行：

- 任何 ROS 2 节点、launch、topic、service 或运行时 ROS graph 检查；
- 真实 IMU 串口读取；
- SocketCAN/CAN-USB 连接和电机控制；
- GPIO12/13 占用、PWM 输出、电调解锁或风扇控制；
- 电机或风扇断电实机测试；
- 电机或风扇带电测试；
- 1200/1400 μs 标定；
- 真实消息时序、QoS、进程退出和 launch 集成验证。

原因：本阶段只授权软件实现与纯软件验证，并明确禁止运行节点、launch 和访问
硬件。未执行项均等待后续单独授权，不能视为已验证。

## 17. 硬件影响声明

- IMU：未访问。
- CAN：未访问，未修改系统 CAN 状态。
- GPIO：未访问，GPIO12/13 映射和用途未改变。
- PWM：未输出。
- 真实串口：未访问。
- 微电机动力：未通电、未控制、未影响。
- 风扇动力：未通电、未控制、未影响。
- `sudo`：未使用。

## 18. 剩余风险与等待实机验证

### 剩余软件风险

- 尚未通过运行时 ROS graph 验证 QoS 匹配、transient-local 初值、回调时序和
  服务交互；
- 尚未验证 Lifecycle 状态变化时公开模式的实际发布时序；
- 尚未验证独立/统一 launch 的真实参数覆盖和进程退出顺序；
- 相对姿态源时间戳倒退检测尚未在真实 IMU 时间源上观察；
- 急停后底层 enabled 和电机模式消息的跨进程到达顺序仅由纯状态测试覆盖；
- 当前没有 GPIO、CAN、真实串口或完整节点的 mock/fake 集成测试。

### 后续实机验证需求

- 在另行授权后验证相对姿态方向、零点和 header；
- 验证电机模式心跳和恢复后只进入 MANUAL；
- 验证公共手动命令只能经管理器到达底层；
- 验证单侧/双侧超时、底层看门狗、stop/enable/e-stop 锁存；
- 验证统一急停需要风扇和电机双条件恢复；
- 在满足十项带电授权门槛后，谨慎标定 1200/1400 μs 和 AUTO 方向、迟滞、
  变化率及停止行为。

本反馈不要求用户现在通电。

## 19. 最终 Git 检查

`git diff --check`：

```text
无输出，通过
```

`git diff --stat`（标准命令不统计未跟踪文件）：

```text
 README.md                                          |   70 +-
 docs/NEXT_COMMAND.md                               | 1768 ++++++++++++++++++++
 src/imu_cybergear_ros2/README.md                   |   22 +-
 .../config/imu_cybergear_params.yaml               |   13 +
 .../imu_cybergear_ros2/controller_state.py         |   25 +-
 .../imu_motor_controller_node.py                   |  191 ++-
 .../imu_cybergear_ros2/imu_protocol.py             |   59 +
 .../imu_cybergear_ros2/keyboard_handler.py         |   13 +-
 .../imu_cybergear_ros2/motor_manager.py            |    8 +-
 .../imu_cybergear_ros2/safety_monitor.py           |   10 +-
 src/imu_cybergear_ros2/package.xml                 |    1 +
 src/imu_cybergear_ros2/test/test_imu_protocol.py   |   57 +
 src/windarmor_bringup/launch/windarmor.launch.py   |   23 +-
 src/windarmor_bringup/test/test_launch_syntax.py   |    8 +
 .../config/fan_params.yaml                         |   29 +
 src/windarmor_fan_controller/launch/fans.launch.py |   21 +
 src/windarmor_fan_controller/package.xml           |    1 +
 src/windarmor_fan_controller/setup.py              |    1 +
 src/windarmor_fan_controller/test/test_pwm.py      |   27 +-
 .../windarmor_fan_controller/fan_node.py           |   88 +-
 .../windarmor_fan_controller/pwm.py                |   41 +
 21 files changed, 2371 insertions(+), 105 deletions(-)
```

其中 `docs/NEXT_COMMAND.md` 的大段差异属于任务开始前用户已有修改。
标准 `git diff --stat` 未显示 7 个未跟踪文件：本反馈文件、两个新增 IMU 测试、
两个新增风扇测试，以及 `fan_control.py`、`fan_command_manager.py`。

最终 `git status --short --branch`：

```text
## master...origin/master
 M README.md
 M docs/NEXT_COMMAND.md
 M src/imu_cybergear_ros2/README.md
 M src/imu_cybergear_ros2/config/imu_cybergear_params.yaml
 M src/imu_cybergear_ros2/imu_cybergear_ros2/controller_state.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/imu_protocol.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py
 M src/imu_cybergear_ros2/package.xml
 M src/imu_cybergear_ros2/test/test_imu_protocol.py
 M src/windarmor_bringup/launch/windarmor.launch.py
 M src/windarmor_bringup/test/test_launch_syntax.py
 M src/windarmor_fan_controller/config/fan_params.yaml
 M src/windarmor_fan_controller/launch/fans.launch.py
 M src/windarmor_fan_controller/package.xml
 M src/windarmor_fan_controller/setup.py
 M src/windarmor_fan_controller/test/test_pwm.py
 M src/windarmor_fan_controller/windarmor_fan_controller/fan_node.py
 M src/windarmor_fan_controller/windarmor_fan_controller/pwm.py
?? docs/LATEST_FEEDBACK.md
?? src/imu_cybergear_ros2/test/test_control_interfaces.py
?? src/imu_cybergear_ros2/test/test_controller_state.py
?? src/windarmor_fan_controller/test/test_fan_control.py
?? src/windarmor_fan_controller/test/test_interface_routing.py
?? src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py
?? src/windarmor_fan_controller/windarmor_fan_controller/fan_control.py
```

未 commit、push、创建或修改标签。阶段 2 到此停止，等待用户审查。
