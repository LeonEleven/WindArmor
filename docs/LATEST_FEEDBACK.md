# 最新反馈：AUTO 姿态增益与风扇响应曲线

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-04

## 1. 结论

已完成阶段 A 的软件实现和纯软件验证：

- 电机新增 `auto_roll_gain` 和 `auto_pitch_gain`，默认均为 `1.0`；
- 增益只作用于电机 AUTO 目标，不改变真实相对姿态话题、风扇输入、MANUAL
  或 HOME；
- 风扇新增 `linear`、`smoothstep`、`quadratic` 三种响应曲线，默认
  `smoothstep`；
- `fan_auto_max_pwm_us` 仍为 `1400`，`max_pwm_us` 仍为 `2200`；
- 三包构建成功，完整测试共 `185` 项，全部通过。

`auto_roll_gain` 和 `auto_pitch_gain` 默认均为 `1.0`。
默认风扇响应曲线为 `smoothstep`。
`fan_auto_max_pwm_us` 仍为 `1400`。
`max_pwm_us` 仍为 `2200`。
本次没有把风扇 AUTO 最大油门改为 `2200`。

本次没有运行 ROS 2 节点或 launch。
本次没有访问 IMU、CAN、GPIO、PWM 或真实串口。
本次没有进行实机或带电测试。
本次完成的是软件实现和纯软件验证。

## 2. Git 基线

- 任务开始分支：`master`
- 任务开始 HEAD：`9196d60e5b9b698ff5e48afe5959c1d7c0d766b3`
- upstream：`origin/master`
- 任务开始时本地/upstream：领先 `0`、落后 `0`
- `v0.3.0` 指向提交 `c3b3c3989674c2c1c902e940953da87fd5812db5`
- 任务开始 HEAD 比 `v0.3.0` 领先 `1` 个提交
- 任务开始前已有用户修改：`docs/NEXT_COMMAND.md`

`docs/NEXT_COMMAND.md` 只作为任务说明读取；本任务未修改、未暂存，也不会纳入
本次 commit。没有 checkout、reset、clean、restore、stash、rebase、merge
或 force push。`v0.3.0` 标签没有被修改、移动、删除或重新创建，也没有创建
新标签。

## 3. 电机 AUTO 姿态增益

新增配置：

```yaml
auto_roll_gain: 1.0
auto_pitch_gain: 1.0
```

`auto_attitude_commands()` 是不依赖 ROS、CAN 或节点状态的纯函数。最终计算链：

```text
真实统一相对 roll/pitch
→ 既有姿态死区
→ 对应轴 AUTO 姿态增益
→ 正负 90° AUTO 范围
→ 既有电机方向映射
→ 电机软限位
→ desired_targets
→ 既有统一速度推进器
```

增益必须是大于或等于 `0.0` 的有限数值；负值、`NaN` 和正负 `Inf` 在节点
配置阶段明确拒绝。`0.0` 表示关闭对应轴，`1.0` 保持修改前比例。

`/imu/relative_roll_pitch` 仍在 AUTO 门控、死区和增益计算前发布真实、修正并
归零后的相对姿态。因此风扇和其他订阅者不会看到增益后的值，调整电机增益
不会隐式改变风扇油门。MANUAL、`/motors/manual_targets`、`[`/`]`、HOME、
急停恢复和机械零点流程均不读取 AUTO 增益。既有电机 ID、方向、软限位、
AUTO 速度和统一推进器没有改变。

## 4. 风扇 AUTO 响应曲线

新增配置：

```yaml
fan_response_curve: "smoothstep"
```

纯函数 `apply_response_curve(normalized_activity, curve_name)` 支持：

- `linear`：`x`
- `smoothstep`：`x² × (3 - 2x)`
- `quadratic`：`x²`

输入先钳位到 `[0, 1]`；非法曲线名以及 `NaN`、正负 `Inf` 会明确失败。
`smoothstep` 是默认曲线，其中点仍为 `0.5`，起点和终点斜率为零。

左右活动量仍使用原有 `max()` 合成方式，左右迟滞状态仍独立。运行状态下继续
按 `(activity - deadband_on) / (full_scale - deadband_on)` 归一化，然后应用
曲线并沿用原有 `round()` 取整。停止值、启动值、死区、自动最大 PWM、底层
范围、看门狗、急停和变化率限制均保持原样。

`fan_full_scale_deg: 45.0` 的语义是活动角达到自动最大目标 PWM 的配置点；
45°只是当前候选值，不是机械极限、风扇启动角、力矩模型结论或已验证恢复
极限，后续需要结合实测推力与机器人结构标定。调小会更早达到最大自动目标，
调大会扩大逐渐增加的倾角范围。

响应曲线决定“当前活动角对应多少目标 PWM”；现有 `control_rate_hz`、
`rise_step_pwm_us` 和 `fall_step_pwm_us` 决定“实际输出多快接近目标”。本次
没有改变变化率限制的调度方式，也没有处理已暂缓的多回调推进问题。

## 5. 实际修改文件

- `README.md`：说明 AUTO 增益、增益与速度的区别、三种风扇曲线、满量程角度
  和 PWM 上限语义及当前验证状态。
- `docs/LATEST_FEEDBACK.md`：覆盖为本次实现、验证和 Git 反馈。
- `src/imu_cybergear_ros2/README.md`：说明电机增益的作用范围与控制链。
- `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml`：增加两个默认
  `1.0` 的 AUTO 增益参数。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py`：
  声明、读取、校验增益，并只在 AUTO 电机目标分支应用。
- `src/imu_cybergear_ros2/imu_cybergear_ros2/motor_motion.py`：增加纯函数增益
  校验和死区后增益/正负 90° 计算。
- `src/imu_cybergear_ros2/test/test_motor_motion.py`：覆盖默认兼容、轴独立、
  `1.25`、`0.0`、非法值、死区顺序和正负 90°。
- `src/imu_cybergear_ros2/test/test_motor_manager.py`：覆盖 AUTO 目标软限位。
- `src/imu_cybergear_ros2/test/test_control_interfaces.py`：覆盖相对姿态语义、
  AUTO 分支隔离、默认 YAML 和既有方向映射。
- `src/windarmor_fan_controller/config/fan_params.yaml`：增加默认
  `smoothstep` 曲线参数。
- `src/windarmor_fan_controller/windarmor_fan_controller/fan_control.py`：增加
  三种纯函数曲线、配置校验并接入既有 PWM 映射。
- `src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py`：
  声明并读取曲线参数。
- `src/windarmor_fan_controller/test/test_fan_control.py`：覆盖精确曲线值、钳位、
  单调性、非有限输入、映射取整、左右迟滞、默认配置和 PWM 上限。

未修改两个包的 `package.xml`、launch 架构、GPIO/CAN 配置、风扇状态机、
`motor_ids`、`motor_signs`、`motor_limits_min` 或 `motor_limits_max`。

## 6. 构建与测试

测试代码、fixture、导入链和静态 launch 测试已在运行前检查：纯函数测试不依赖
硬件；电机管理器测试使用内存 fake 节点和 fake 驱动；键盘测试使用伪终端；
launch 测试只解析文本/AST；没有构造真实风扇 GPIO 节点、CAN 后端或串口节点。

### 构建

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

结果：3 个包构建成功。

### 针对性测试

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_motor_motion.py \
  src/imu_cybergear_ros2/test/test_motor_manager.py \
  src/imu_cybergear_ros2/test/test_control_interfaces.py -v
```

结果：`69 passed`。

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/windarmor_fan_controller/test/test_fan_control.py -v
```

结果：`52 passed`。

实现后的首轮组合针对性测试也为 `121 passed`。此前两次尝试分别因未加载工作区
风扇包、以及临时 `PYTHONPATH` 覆盖 ROS Python 路径而在收集阶段停止；均为
环境路径问题，收集阶段未执行测试。修正环境后全部通过。

### 完整测试

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup
colcon test-result --verbose
```

结果：总数 `185`，通过 `185`，失败 `0`，错误 `0`，跳过 `0`。

## 7. 未执行测试、硬件影响和剩余风险

未执行真实 IMU、CAN、CyberGear、GPIO、PWM、电调、风扇或整机联动测试，原因
是本任务只授权软件实现和纯软件验证，真实硬件运行仍需单独授权。没有执行
`ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
`scripts/setup_can.sh`。

- 没有运行 ROS 2 节点或 launch；
- 没有访问 IMU 或真实串口；
- 没有连接或初始化 CAN/CyberGear；
- 没有访问 GPIO12/GPIO13；
- 没有输出 PWM 或初始化电调；
- 4 个电机和 2 个风扇均未因本任务被控制。

剩余风险与等待实机验证内容：默认增益 `1.0` 的实际机械响应、非默认增益的动作
幅度、默认 `smoothstep` 曲线的风扇响应、`fan_full_scale_deg=45.0`、起转 PWM、
自动最大 PWM 和实际推力关系仍未完成本轮实机验证。此前基础联动实机验证记录
继续有效，但不等于本次新增增益和曲线已通过实机验证。

## 8. 差异、提交和推送计划

最终任务差异（不含任务开始前已有的 `docs/NEXT_COMMAND.md`）：

```text
13 files changed, 550 insertions(+), 403 deletions(-)
```

`git diff --check`：通过，无空白错误。构建产物、日志、临时文件和
`docs/NEXT_COMMAND.md` 不纳入 commit。

- 计划 commit message：`功能：增加AUTO姿态增益和风扇响应曲线`
- 计划推送分支：`origin/master`
- commit SHA：创建 commit 后在最终回复报告
- push 结果：执行后在最终回复报告
