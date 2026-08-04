# 最新人工验证指南：统一电机运动速度

> 本文档只保留最近一次改动对应的人工验证方案。
>
> 当前对象：`v0.3.0` 标签之后的 MANUAL、AUTO、HOME 统一速度改进
>
> 更新日期：2026-08-04

## 1. 当前验证状态与边界

本次改动把 MANUAL 键盘、`/motors/manual_targets`、AUTO IMU 跟随、`h` HOME
回零以及 `[`/`]` 快捷目标迁移到同一个固定周期目标推进器。自动测试只能证明
软件目标变化率、状态切换和接口路由符合设计，不能证明负载下的真实机械速度、
力矩、方向或安全余量。

当前默认候选值为：

```yaml
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0
```

这三个值尚未因本次改动进行实机验证，且不属于 `v0.3.0` 标签内容。

本文档中的 ROS 2 节点、launch、CAN、IMU、GPIO、PWM 和动力设备命令均未由
本次软件任务执行。人工验证也不能直接开始带电部分：必须先由用户针对准确命令
明确授权，并满足根目录 `AGENTS.md` 的十项带电授权门槛。

## 2. 每轮记录模板

```text
日期和操作者：
分支与 HEAD：
使用的参数文件：
设备供电状态：
获准验证的设备和准确命令：
初始机械位置：
速度、角度、力矩或 PWM 限制：
预期持续时间：
急停方法：
实际结果：
通过/失败：
日志或视频位置：
异常及恢复动作：
```

开始前记录：

```bash
cd /home/h-goal/workspace/WindArmor
git status --short --branch
git rev-parse HEAD
git tag --points-at HEAD
```

## 3. A 级：纯软件复验

以下命令不启动 ROS 2 节点或 launch。执行前仍应确认测试文件没有新增真实
CAN、IMU、串口或 GPIO 初始化。

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup
colcon test-result --verbose
```

定向运行本次纯软件测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_motor_motion.py \
  src/imu_cybergear_ros2/test/test_motor_manager.py \
  src/imu_cybergear_ros2/test/test_control_interfaces.py -v
```

通过标准：构建成功，所有测试无失败、无错误；受保护配置仍为：

```yaml
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
```

## 4. 带电验证前必须单独确认的十项信息

在执行第 5～8 节前，应把下列内容填写为具体值并得到用户明确同意：

1. 通电设备：先仅 IMU、CAN 和 4 个微电机；最终回归才包含双风扇；
2. 带电原因：验证软件目标速度与真实机械运动、模式切换及停止行为；
3. 准备执行的准确命令：从对应小节逐条复制，不得临时扩大范围；
4. 预计运动设备：列出本轮电机 ID；风扇回归时列出左右风扇；
5. 预计方向：按本轮按键或 IMU 倾斜方向逐项写明；
6. 限制：填写临时模式速度、目标角度、CyberGear 速度上限、风扇 PWM；
7. 持续时间：建议每个动作不超过 2 秒，动作间回中检查；
8. 急停：人员守在 launch 终端，空格为首选，另备 `/e_stop=true` 终端；
9. 异常停止：方向错误、抖动、碰限位、异常声响、过流、过温、通信丢失；
10. 恢复：急停、确认停止、按已验证顺序断开动力，排障后不得自动续测。

未完成这十项或未获明确授权时，到 A 级结束，不得执行后续命令。

## 5. 准备低速临时参数文件

首次实机验证不要直接使用新的 `4.0 rad/s` 候选值。授权后，在不修改仓库
配置的前提下制作临时参数文件：

```bash
cd /home/h-goal/workspace/WindArmor
cp src/imu_cybergear_ros2/config/imu_cybergear_params.yaml \
  /tmp/windarmor_motor_speed_verify.yaml
sed -i \
  -e 's/manual_motion_speed_rad_s: 4.0/manual_motion_speed_rad_s: 0.5/' \
  -e 's/auto_motion_speed_rad_s: 4.0/auto_motion_speed_rad_s: 0.5/' \
  -e 's/home_motion_speed_rad_s: 4.0/home_motion_speed_rad_s: 0.5/' \
  /tmp/windarmor_motor_speed_verify.yaml
```

核对只改变了三项：

```bash
diff -u \
  src/imu_cybergear_ros2/config/imu_cybergear_params.yaml \
  /tmp/windarmor_motor_speed_verify.yaml
```

预期只显示 `4.0` 改为 `0.5`。如果还出现电机 ID、方向、软限位、CAN 或 IMU
配置差异，立即停止，不得启动。

## 6. 仅四电机的分阶段验证

本节会访问真实 IMU 和 CAN，并初始化、控制四个微电机；即使风扇未启动，也
必须先获得第 4 节的明确带电授权。固定机器人，确保手臂完整行程没有人员、
线缆或硬物。

启动终端：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py \
  params_file:=/tmp/windarmor_motor_speed_verify.yaml \
  control_backend:=socketcan_hat \
  can_channel:=can10
```

监视终端：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic echo /motors/control_mode
```

另开终端观察反馈：

```bash
ros2 topic echo /motor/status
```

### 6.1 急停预检

启动后不做运动，先按空格。确认模式为 `EMERGENCY_STOP`，四个电机停止。排除
异常并确认机械位置安全后按 `r`，确认只恢复到 `MANUAL`，且没有恢复任何旧
运动目标。若急停或恢复不符合预期，立即结束本轮。

### 6.2 MANUAL 轻按、长按和反向

依次选择每个 CAN ID，只测试对应的一组既有方向键：

| 电机 | 正/反按键 |
|---|---|
| ID4 | `d` / `a` |
| ID3 | `w` / `s` |
| ID2 | `k` / `i` |
| ID1 | `l` / `j` |

每个电机验证：

1. 轻按正方向一次，确认只产生约 `3°` 的有限期望变化；
2. 等电机停止后轻按反方向一次，确认不会出现由旧时间间隔造成的大步长；
3. 长按约 1 秒，松开后确认目标不再继续增加；
4. 分别短暂长按正、反方向，确认方向切换第一字符仍是精细步进；
5. 确认其他三个电机没有被该字符错误更新；
6. 任一方向或软限位不符立即急停。

### 6.3 绝对目标和快捷目标

保持 MANUAL，先发送小角度绝对目标；数组顺序为 `[4, 3, 2, 1]`：

```bash
ros2 topic pub --once /motors/manual_targets \
  std_msgs/msg/Float64MultiArray \
  "{data: [-0.15, 0.15, -0.15, 0.15]}"
```

确认四个电机逐步逼近，不是一次跳到目标。随后发送回零期望目标：

```bash
ros2 topic pub --once /motors/manual_targets \
  std_msgs/msg/Float64MultiArray \
  "{data: [0.0, 0.0, 0.0, 0.0]}"
```

分别选择电机后短暂测试 `[` 和 `]`，确认它们设置期望目标并按 MANUAL 速度
运动，仍受各电机软限位约束。不要一次让多个轴走完整 90°；看到方向和渐进
行为后即用反向小目标或急停结束。

### 6.4 MANUAL 与 HOME 同速比较

用 `/motors/manual_targets` 从零位设置一个经授权的小目标，例如 `0.20 rad`，
记录开始到停止所需时间；然后按 `h` 回零并记录相同距离的时间。默认三模式
速度相同且电机速度上限更高时，两次软件目标变化率应接近。真实机械时间可因
负载和驱动器控制而有小差异，但 `h` 不应再明显更快，也不应出现独立定时器
引起的突变。

运动过程中发送一个新的有效 MANUAL 按键或绝对目标，确认 HOME 被取消且不
继续追赶旧零目标。

### 6.5 AUTO 与 HOME 行为

机器人保持机械中位和静止，设置 IMU 零点：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
```

在启动终端按 `m` 进入 AUTO，确认 `/motors/control_mode=AUTO`。缓慢倾斜时，
电机应随姿态本身缓慢变化；快速倾斜到一个经授权的小角度时，电机以 AUTO
速度上限平滑追赶，而不是随 IMU 消息频率突然变快。

保持同一小姿态目标时比较 AUTO 与 MANUAL/HOME 的相同距离运动时间。随后在
AUTO 中按 `h`，确认：

1. `/motors/control_mode` 先变为 `MANUAL`；
2. 全部电机按 HOME 速度回零；
3. 到达后保持 MANUAL；
4. IMU 后续消息不再争用 HOME 目标。

测试 AUTO 时停止或断开 IMU 消息会触发看门狗。确认退出 AUTO 后电机保持
最近已发送位置，不继续完成尚未追上的旧姿态目标。

### 6.6 运动中急停和恢复

分别在 MANUAL、AUTO 和 HOME 尚未到达目标时按空格：

- 急停必须立即生效，不等待软件速度限制；
- 未完成的 `desired_targets` 必须被丢弃；
- 按 `r` 或调用 `/enable_motor=true` 后只进入 MANUAL；
- 恢复后不得继续急停前的 MANUAL、AUTO 或 HOME 目标；
- 必须收到新的操作才允许继续运动。

## 7. 逐级提高候选速度

只有 `0.5 rad/s` 的逐电机方向、软限位、HOME、AUTO 和急停全部通过后，才能
另行申请下一轮授权。每轮重新生成临时参数，把三种速度同时改为 `1.0`、
`2.0`，最后才是候选 `4.0 rad/s`；每次只提升一级并重复第 6 节。

若希望三种模式使用不同速度，也必须逐项记录实际值。不要把
`default_speed: 10.0` 误当成已经验证的普通运动速度；实际软件推进还受
当前电机速度上限和 `max_position_step` 共同约束。

## 8. 最终 IMU、电机与双风扇回归

只有四电机速度验证全部通过、风扇 PWM 起转值和上限已经单独标定、并再次
满足包含双风扇的十项授权后，才回归最终目标。启动方式仍以根 README 为准：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch windarmor_bringup windarmor.launch.py \
  motor_params_file:=/tmp/windarmor_motor_speed_verify.yaml
```

另一个终端依次执行：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
```

在 launch 终端按 `m`，确认电机进入 AUTO 后再执行：

```bash
ros2 service call /fans/auto_enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

确认 IMU 倾斜时四电机仍按原方向映射运动，双风扇仍按原风扇 AUTO 公式工作，
而电机快速目标变化由 `auto_motion_speed_rad_s` 限制。重点回归：统一急停、
归零清除风扇 AUTO、AUTO 中按 `h` 会退出电机 AUTO并使风扇自动条件失效、
恢复后不自动恢复旧目标或旧 PWM。

结束时先回中并急停，确认电机模式为 `EMERGENCY_STOP`、风扇输出为
`[800, 800]`，再按已经验证的顺序断开动力并退出。任何异常立即急停，不得
为了完成表格而继续动作。

## 9. 通过标准

- MANUAL、AUTO、HOME 相同速度参数、相同软件距离下不再有明显独立速度路径；
- MANUAL 稳定长按不再简单随键盘重复频率成比例变快；
- 单次轻按仍可精细调节，松开后不会无限增加目标；
- AUTO 最大追赶速度不再直接取决于 IMU 消息频率；
- `h` 无独立快速路径，AUTO 中按下后明确回到 MANUAL；
- `/motors/manual_targets` 与 `[`/`]` 均渐进运动并保持接口兼容；
- IMU 超时、急停、停用和恢复不会继续旧目标；
- 电机 ID、方向、软限位、风扇仲裁和系统急停没有回归；
- 候选 `4.0 rad/s` 只有完成对应实机记录后才能标记为已验证。
