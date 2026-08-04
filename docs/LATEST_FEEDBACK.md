# 最新反馈：统一电机运动速度的软件实现

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-04

## 1. 结论

已按 `docs/NEXT_COMMAND.md` 完成 MANUAL、AUTO 与 HOME 电机运动速度统一的
软件实现和纯软件验证：

- MANUAL、AUTO、HOME、`/motors/manual_targets` 和 `[`/`]` 的普通位置运动
  全部改为先更新 `desired_targets`；
- 激活后的唯一固定周期推进器根据真实单调时间差更新 `current_targets` 并发送
  普通 CyberGear 位置命令；
- HOME 删除独立快速定时器，AUTO 不再在 IMU 回调中推进位置，MANUAL 不再按
  每个字符直接写位置；
- 三种模式默认软件目标速度都为 `4.0 rad/s`；
- MANUAL 连续重复字符根据实际事件间隔生成有限目标增量；
- 急停、IMU 超时、模式切换和 Lifecycle 停止均丢弃未完成旧目标；
- 三包构建成功，最终 `153` 项测试全部通过。

本次没有运行 ROS 2 节点或 launch。
本次没有访问 IMU、CAN、GPIO、PWM 或真实串口。
4 个微电机和 2 个风扇均未因本任务被控制。
本次完成的是软件实现和纯软件验证，不是实机验证。
`v0.3.0` 标签未被修改。

## 2. Git 基线与标签关系

- 当前分支：`master`
- 当前 HEAD：`c3b3c3989674c2c1c902e940953da87fd5812db5`
- `origin/master`：任务开始时与当前 HEAD 相同
- 当前 HEAD 上的标签：`v0.3.0`
- 任务开始时用户已有修改：`docs/NEXT_COMMAND.md`

任务开始状态：

```text
## master...origin/master
 M docs/NEXT_COMMAND.md
```

`docs/NEXT_COMMAND.md` 只读取、未修改。当前 HEAD 仍是 `v0.3.0` 的提交，但
本次尚未提交的工作区改进不在该标签内。未 checkout、reset、clean、commit、
push，也未创建、移动、删除或覆盖任何标签。

## 3. 修改前的三条速度路径

### MANUAL

每收到一个 `w/s/a/d/i/k/j/l` 字符就调用一次 `manual_step()`，近似关系为：

```text
每字符目标增量 = manual_step_deg
平均目标速度 ≈ manual_step_deg × 操作系统字符重复频率
```

`manual_loop_hz` 只是键盘线程轮询频率，并不是终端实际字符重复频率。

### AUTO

每次有效 IMU 回调直接调用 `apply_targets()`；旧 `write_target()` 使用
`current_motor_speed × command_interval_sec` 限制该次变化。因此近似为：

```text
AUTO 目标推进速度 ≈ 单次允许变化量 × 实际接受的 IMU 回调频率
```

### HOME

`h` 创建独立的 `command_interval_sec` 固定定时器，并在每次回调反复调用旧
`write_target()`。它稳定地按固定周期推进，不依赖键盘字符或 IMU 消息到达
频率，所以此前通常明显快于 MANUAL，也可能快于 AUTO。

另外，`/motors/manual_targets` 旧行为直接进入 `apply_targets()`，`[`/`]`
则直接向 CyberGear 写入经过软限位的完整 ±90° 目标，二者也不是同一路径。

## 4. 最终统一架构

```text
MANUAL 字符 / 绝对目标 / ±90° ─┐
AUTO 新鲜 IMU 姿态 ────────────┼──> desired_targets
h HOME 零目标 ─────────────────┘
                                      ↓
                         固定周期统一目标推进器
                         真实 dt + dt 延迟上限
                                      ↓
              模式速度 ∩ 当前电机速度上限 ∩ 单周期位置上限
                                      ↓
                 current_targets + CyberGear 位置命令
```

内部运动源为 `IDLE`、`MANUAL`、`AUTO`、`HOME`，只用于选择推进语义和模式
速度；公开 `/motors/control_mode` 仍只使用 `MANUAL`、`AUTO`、
`EMERGENCY_STOP`、`DISABLED`、`ERROR`，没有破坏公共接口。

### `desired_targets`

输入源希望各电机最终到达的位置。输入有限值检查后立即应用软限位，但普通输入
不访问 CAN，不直接改变最近已发送命令。

### `current_targets`

最近一次实际尝试发送给 CyberGear 的软件位置命令。初始化时与
`desired_targets` 均为零，模式切换、急停、停用和恢复时两者重新同步，避免
旧目标在以后突然恢复。

## 5. 固定推进器和真实 dt

节点激活时只创建一个周期为 `command_interval_sec=0.02 s` 的推进定时器；
重复激活不会创建多个。第一帧仅初始化单调时间，不产生大步。以后每帧使用：

```text
dt_used = clamp(real_monotonic_dt, 0, motion_dt_max_sec)
effective_speed = min(mode_motion_speed, current_motor_speed_limit)
allowed_step = min(max_position_step, effective_speed × dt_used)
new_target = current + clamp(desired - current, -allowed_step, allowed_step)
```

默认 `motion_dt_max_sec=0.05`，防止线程暂停或调度延迟后出现巨大一步；
`target_reached_tolerance_rad=0.001` 用于位置到达判定，不复用姿态死区。
发送前再次检查有限值并应用软限位。

底层写入失败时保持原有软件状态更新顺序：先更新 `current_targets` 和命令时间，
再尝试驱动写入并记录错误。该语义已增加替身测试并在此明确记录。

## 6. 三种模式速度与 `default_speed`

新增参数：

```yaml
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0
motion_dt_max_sec: 0.05
target_reached_tolerance_rad: 0.001
manual_repeat_gap_sec: 0.8
manual_repeat_dt_max_sec: 0.08
```

三种 `4.0 rad/s` 是软件目标位置变化率的初始候选值，目的是让相同距离下三种
模式具有相同的软件推进上限。它们不等于负载下实测机械角速度，尚未进行本轮
实机验证，不得表述为已验证安全速度。

`default_speed: 10.0` 的最终语义是：启动时写给 CyberGear 的位置模式目标
速度上限，也是每台电机当前底层速度上限的初值。它不再直接决定三种模式的
软件目标推进速度，实际普通推进不超过 `min(模式速度, 当前电机速度上限)`。

`+/-` 仍调整选中电机的速度上限，保留
`manual_speed_min`、`manual_speed_max`、`manual_speed_step`：

- 电机速度上限低于模式速度时，`+/-` 会直接影响该电机推进速度；
- 上限高于模式速度后，继续提高不会突破模式速度参数；
- 新日志同时显示电机速度上限、当前模式速度和最终有效推进上限。

## 7. MANUAL 最终行为

单次轻按 `w/s/a/d/i/k/j/l` 仍使用 `manual_step_deg=3.0°` 对对应电机的
`desired_target` 做有限精细调整，不直接写位置。

同一电机、同一方向字符在 `manual_repeat_gap_sec=0.8 s` 内重复时：

```text
event_dt = 当前事件时间 - 上一相同运动事件时间
repeat_dt = clamp(event_dt, 0, manual_repeat_dt_max_sec)
increment = min(
    max_position_step,
    min(manual_motion_speed_rad_s, current_motor_speed_limit) × repeat_dt
)
```

稳定重复阶段的平均期望目标变化率因此接近 MANUAL 模式速度，而不是固定角度
乘以字符频率。字符停止后不再增加 `desired_target`；推进器只把
`current_target` 追到最后一个有限目标后停止。

反向第一字符按单次精细步进处理，上一方向时间不会用于反向大步；不同电机分别
记录时间。模式切换、绝对目标、HOME、急停、停用和退出都会清除重复状态，
错误或非运动按键不会刷新运动时间。

## 8. AUTO 最终行为

IMU 回调继续完成四元数校验、统一相对姿态、死区、±90°、方向映射和软限位，
但最终只调用 `set_auto_targets()` 更新期望目标，不再发送普通位置命令。

固定推进器在两帧新鲜 IMU 消息之间继续按
`auto_motion_speed_rad_s` 追赶最新目标。快速倾斜时受 AUTO 速度限制，缓慢
倾斜时仍会因目标本身变化慢而自然缓慢运动；IMU 消息数量不再直接增加单周期
允许位置变化。

从 MANUAL 切换到 AUTO 时立即同步 desired/current 并等待切换后的新 IMU
回调。IMU 看门狗退出 AUTO 时，状态变化回调同步 desired/current、内部运动源
回到 IDLE，未完成旧姿态目标不会继续运动；现有风扇模式联动和 AUTO 清除语义
保持不变。

## 9. HOME、绝对目标和快捷目标

`h` 不再创建独立定时器：

1. AUTO 中先显式切为 MANUAL；
2. 清除手动重复状态；
3. 全部 `desired_targets` 设为经过软限位的零目标；
4. 内部运动源设为 HOME；
5. 唯一推进器按 `home_motion_speed_rad_s` 回零；
6. 全部到达后内部转为 IDLE，公开模式保持 MANUAL。

有效 MANUAL 字符、`/motors/manual_targets`、`[`/`]`、切换 AUTO、急停和
Lifecycle 停止都会取消 HOME，不会额外跳写位置。

`/motors/manual_targets` 名称、类型和 `motor_ids` 顺序不变。现在只在 MANUAL
接受，先检查长度和全部元素有限性；任一错误整条拒绝且不部分更新。有效消息
一次更新全部期望目标、应用软限位、取消 HOME、清除重复状态，再按 MANUAL
速度渐进运动。

`[` 和 `]` 只在 MANUAL 设置选中电机经过软限位的 ±90° 期望目标，取消 HOME
并由统一推进器运动。日志使用“设置期望目标”，不再暗示已经到达，也不再一次
跳写完整位置。

## 10. Lifecycle、急停和恢复

- activate：创建唯一推进定时器并安全初始化时间；
- deactivate：销毁推进定时器，清除重复状态，desired 同步 current；
- cleanup/shutdown：重复安全销毁推进资源，不保留重新激活后会执行的旧目标；
- 急停：先冻结普通推进和未完成目标，再执行既有直接电机停止，不受速度限制
  延迟；
- 恢复：直接保持最近软件命令位置，成功后只进入 MANUAL，内部为 IDLE，不恢复
  急停前 MANUAL、AUTO 或 HOME 目标；
- 机械零点和初始化仍保留必要的特殊直接硬件流程，没有复用普通运动路径。

状态管理回调改为在状态锁外执行，避免统一推进器持有节点锁时与状态转换形成
锁顺序反转。

## 11. 实际修改文件和目的

### 文档

- `README.md`
  - 更新 `v0.3.0` 稳定基线、统一推进公式、模式速度、按键和绝对目标语义。
- `docs/MANUAL_VERIFICATION.md`
  - 覆盖为本次速度改动的最新分级人工验证方案，包含低速临时参数、逐电机、
    AUTO/HOME、急停及最终双风扇回归步骤。
- `docs/LATEST_FEEDBACK.md`
  - 覆盖为本次实现与验证反馈。
- `src/imu_cybergear_ros2/README.md`
  - 说明 desired/current、三种速度、`default_speed`、`+/-`、字符重复和 HOME。

### 实现与配置

- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_motion.py`
  - 新增完全不依赖 ROS/硬件的参数校验、模式速度、单周期推进和重复字符计算。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py`
  - 实现统一推进器、运动源、desired/current、MANUAL/AUTO/HOME 和安全同步。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`
  - 声明/读取/校验新参数，接入生命周期定时器，迁移 IMU 和绝对目标输入。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py`
  - 更新键盘帮助；原键位继续调用迁移后的管理器语义。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/controller_state.py`
  - 在状态锁外执行回调，避免推进器与模式切换死锁。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py`
  - 急停直接操作前先冻结普通运动目标。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/__init__.py`
  - 保留包根导出兼容并改为延迟导入，使纯计算模块可在无 ROS 环境测试。
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`
  - 增加三模式速度、dt 上限、到达容差和字符重复参数；明确默认速度语义。

### 测试

- `src/imu_cybergear_ros2/test/test_motor_motion.py`
  - 31 项纯函数测试：正反推进、三模式同速、真实 dt、步长/速度上限、容差、
    软限位、NaN/Inf、非法关系及 20/25 Hz 重复字符。
- `src/imu_cybergear_ros2/test/test_motor_manager.py`
  - 18 项替身测试：输入不直写、10/20/50 Hz AUTO 等速、HOME、快捷目标、
    模式切换、Lifecycle、保护、急停及写失败语义。
- `src/imu_cybergear_ros2/test/test_control_interfaces.py`
  - 增加静态检查：AUTO/绝对目标路由、Lifecycle 定时器、新默认值和受保护映射。

未修改风扇算法、风扇状态机、launch、包版本号、CAN 配置、IMU 安装方向、
GPIO12/13 用途，也未改变受保护电机参数：

```yaml
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
left_gpio: 12
right_gpio: 13
```

## 12. 已执行命令与结果

### 启动前与静态检查

执行了以下只读检查：

```bash
git status --short --branch
git rev-parse HEAD
git tag --points-at HEAD
git diff --check
git diff --stat
git diff --name-only
rg --files ...
rg -n <速度路径、普通位置写入、参数、受保护映射> ...
sed -n <分段范围> <文档、源码、配置、测试、launch、package.xml、setup.py>
wc -l ...
sha256sum docs/NEXT_COMMAND.md
```

确认任务开始时八项旧路径与命令描述一致，且测试导入链只使用纯函数、替身和
静态源码检查，不实例化硬件节点。

### Python 语法与兼容导入

```bash
python3 -m py_compile <本次修改的 Python 文件>
source /opt/ros/jazzy/setup.bash
PYTHONPATH=src/imu_cybergear_ros2:${PYTHONPATH} \
python3 -c 'from imu_cybergear_ros2 import ...'
```

结果：成功；延迟导出的原包根符号可以正常导入。

### 定向 pytest

第一次只给纯模块设置源码 `PYTHONPATH` 时，测试收集因旧包
`__init__.py` 会立即导入 `motor_manager`，进而需要 `std_msgs`，出现
`ModuleNotFoundError: std_msgs`。没有执行任何测试或硬件代码。随后把包根
兼容导出改为延迟导入，纯模块测试在不加载 ROS 子模块的情况下通过。

后续定向结果依次为：

```text
31 passed
42 passed
142 passed
149 passed
56 passed（最终速度相关定向集合）
```

### 三包构建与完整回归

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
Summary: 153 tests, 0 errors, 0 failures, 0 skipped
```

测试分组：

| 分组 | 结果 |
|---|---:|
| 新增目标推进纯函数 | 31 项通过 |
| 新增 MotorManager 替身集成 | 18 项通过 |
| 电机静态接口（含原有 4 项） | 8 项通过 |
| 原 IMU、状态、风扇、PWM、键盘与 launch 回归 | 96 项通过 |
| **总计** | **153 通过，0 失败，0 错误，0 跳过** |

构建、测试和语法命令均未启动节点或 launch，也未构造真实驱动后端。

## 13. 未执行验证与硬件状态

未执行：

- 任何 `ros2 run`、`ros2 launch`、`ros2 topic` 或 `ros2 service`；
- 真实 IMU、串口、SocketCAN、CAN HAT+ 或 CyberGear 初始化；
- GPIO12/13、PWM、电调解锁或风扇控制；
- 电机或风扇断电/带电实机测试；
- 新 `4.0 rad/s` 三模式速度的真实机械验证；
- 真实终端字符重复率、ROS 回调时序和进程级 Lifecycle 验证。

原因：本任务只授权软件实现和不访问硬件的测试。

硬件影响：IMU 未访问；CAN 未连接；GPIO/PWM 未访问；真实串口未打开；4 个
微电机和 2 个风扇均未因本任务通电、运动或旋转；未使用 `sudo`。

## 14. 剩余风险与人工验证建议

- `4.0 rad/s` 只是软件候选值，负载下真实速度、力矩和机构冲击未知；
- 自动测试使用替身时钟和驱动，尚未测量 ROS 定时器在树莓派负载下的抖动；
- 真实终端 20/25 Hz 以外的重复字符行为需要人工感受精细度；
- IMU 缓慢/快速倾斜、看门狗与推进器的真实并发时序尚未实机观察；
- `current_targets` 保持原有写失败更新语义，连续 CAN 写失败仍依赖既有错误和
  安全监控，不代表硬件已经到达软件命令位置；
- 当前仍没有完整节点级 fake CAN/IMU 集成测试。

最新分级步骤已写入 `docs/MANUAL_VERIFICATION.md`。建议未来另行授权后先使用
临时 `0.5 rad/s` 参数、固定机器人、逐电机验证，再按 `1.0 → 2.0 → 4.0`
逐级提高；本反馈不要求用户现在通电。

## 15. 最终 Git 检查

`git diff --check`：无输出，通过。

本文件写入后的 `git diff --stat`（标准命令不统计三个新建未跟踪文件）：

```text
 README.md                                          |   63 +-
 docs/LATEST_FEEDBACK.md                            |  748 +++----
 docs/MANUAL_VERIFICATION.md                        | 1061 ++--------
 docs/NEXT_COMMAND.md                               | 2195 ++++++++------------
 src/imu_cybergear_ros2/README.md                   |   61 +-
 .../config/imu_cybergear_params.yaml               |   31 +-
 .../imu_cybergear_ros2/__init__.py                 |   28 +-
 .../imu_cybergear_ros2/controller_state.py         |   14 +-
 .../imu_motor_controller_node.py                   |  160 +-
 .../imu_cybergear_ros2/keyboard_handler.py         |   10 +-
 .../imu_cybergear_ros2/motor_manager.py            |  474 +++--
 .../imu_cybergear_ros2/safety_monitor.py           |    2 +
 .../test/test_control_interfaces.py                |   51 +
 13 files changed, 2081 insertions(+), 2817 deletions(-)
```

其中 `docs/NEXT_COMMAND.md` 的差异是任务开始前用户已有修改。三个新文件为：

```text
src/imu_cybergear_ros2/imu_cybergear_ros2/motor_motion.py
src/imu_cybergear_ros2/test/test_motor_manager.py
src/imu_cybergear_ros2/test/test_motor_motion.py
```

最终 `git status --short --branch`：

```text
## master...origin/master
 M README.md
 M docs/LATEST_FEEDBACK.md
 M docs/MANUAL_VERIFICATION.md
 M docs/NEXT_COMMAND.md
 M src/imu_cybergear_ros2/README.md
 M src/imu_cybergear_ros2/config/imu_cybergear_params.yaml
 M src/imu_cybergear_ros2/imu_cybergear_ros2/__init__.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/controller_state.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/keyboard_handler.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/motor_manager.py
 M src/imu_cybergear_ros2/imu_cybergear_ros2/safety_monitor.py
 M src/imu_cybergear_ros2/test/test_control_interfaces.py
?? src/imu_cybergear_ros2/imu_cybergear_ros2/motor_motion.py
?? src/imu_cybergear_ros2/test/test_motor_manager.py
?? src/imu_cybergear_ros2/test/test_motor_motion.py
```

未创建 commit，未 push，未创建或修改 tag，`v0.3.0` 保持不变。
