# 最新人工验证指南

> 本文档只保留最近一次改动对应的人工验证方案。
>
> 当前对象：`v0.3.0` 候选的软件实现
>
> 当前稳定发布：`v0.2.1`
>
> 更新日期：2026-07-29

## 1. 使用规则

以后只要一次改动存在需要人工确认的行为、接口、运行时集成或实机效果，就应
覆盖更新本文档，删除已经不再适用于最新改动的旧步骤。若某次改动完全由自动
测试覆盖且不需要人工验证，应在最新反馈中明确写“无需更新人工验证指南”。

本文档中的验证分为四级，必须按顺序进行：

1. A 级：纯软件构建与自动测试；
2. B 级：只启动无硬件 I/O 的 `fan_command_manager`，使用伪造 ROS 消息；
3. C 级：经明确授权后的单设备、断电或只读硬件验证；
4. D 级：经十项带电授权门槛批准后的真实动力验证。

通过低等级验证不代表高等级验证通过。尤其不能把 A/B 级结果写成 IMU、CAN、
GPIO、电机或风扇实机验证。

## 2. 本次需要人工验证的内容

### 软件和接口

- 三个包能够从干净终端构建和加载；
- 正式风扇链路只有一个管理器和一个底层控制器；
- 公共手动话题只进入管理器；
- `/fans/command_pwm` 是唯一正常底层命令；
- 双路手动命令原子更新；
- 左右单通道分别计时和超时；
- 越界或错误长度消息被拒绝且不续期；
- 自动风扇默认关闭；
- AUTO 启用条件、`AUTO_WAITING` 和 `AUTO_ACTIVE` 符合设计；
- 姿态方向、迟滞、映射和变化率限制符合公式；
- 姿态、电机模式和 enabled 状态超时会立即安全停止并清除 AUTO；
- `/imu/zero_generation` 会清除旧姿态和 AUTO；
- 独立模式与统一模式的急停恢复条件不同。

### 需要真实设备才能确认

- `/imu/relative_roll_pitch` 的实际方向、单位、header 和归零效果；
- `/motors/control_mode` 的生命周期、模式切换和恢复时序；
- `/enable_motor=true` 成功后确实只进入 MANUAL；
- GPIO12/13 的实际对应关系；
- `/fans/stop`、`/fans/enable`、`/e_stop` 的底层锁存和退出清理；
- 真实进程间 QoS、心跳、超时和 launch 参数覆盖；
- 1200 μs 是否为可靠起转点；
- 1400 μs 是否为合适的 AUTO 上限；
- 电机与风扇的真实运动方向、响应速度和机械安全余量。

## 3. 通用准备

所有终端先执行：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
```

需要使用已构建工作空间时再执行：

```bash
source install/setup.bash
```

每轮人工验证都应记录：

```text
日期和操作者：
分支：
HEAD：
设备供电状态：
执行的验证等级：
执行的准确命令：
预期结果：
实际结果：
通过/失败：
日志或截图位置：
异常及恢复动作：
```

验证前保存基线：

```bash
git status --short --branch
git rev-parse HEAD
```

## 4. A 级：纯软件复验

这一部分不会启动 ROS 2 节点，也不应访问 IMU、CAN、GPIO 或真实串口。

### A1. 构建

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

通过标准：

- 三个包全部显示 `Finished`；
- 总结为 `3 packages finished`；
- 没有依赖、语法或安装入口错误。

### A2. 三包自动测试

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_bringup
colcon test-result --verbose
```

当前预期：

```text
Summary: 100 tests, 0 errors, 0 failures, 0 skipped
```

若测试数量因后续改动改变，以最新测试集合为准，但错误和失败必须为 0。不得
为了得到通过结果而删除、跳过或放宽安全测试。

### A3. 差异与受保护参数

```bash
git diff --check
git diff --stat
git status --short --branch
```

人工确认以下配置仍为：

```yaml
motor_ids: [4, 3, 2, 1]
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
left_gpio: 12
right_gpio: 13
```

## 5. B 级：无硬件管理器运行时验证

本节只允许启动：

```text
fan_command_manager
```

不得启动 `fan_controller`、IMU 节点、电机控制节点或任何 launch。管理器本身
不导入 GPIO、不连接 CAN、不开串口。所有 enabled、电机模式和姿态均由测试
终端伪造。

为避免混淆，每条持续发布命令使用独立终端。按 `Ctrl+C` 停止对应发布者。

### B1. 启动管理器

终端 A：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run windarmor_fan_controller fan_command_manager \
  --ros-args \
  --params-file src/windarmor_fan_controller/config/fan_params.yaml \
  -p require_motor_mode_for_manual:=false
```

终端 B 观察管理器状态：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic echo /fans/control_state
```

终端 C 观察唯一底层命令：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic echo /fans/command_pwm
```

初始预期：

- `/fans/control_state` 为 `DISABLED`；
- `/fans/command_pwm` 为 `[800, 800]`；
- `/fans/auto_enabled=false`；
- `/fans/auto_active=false`。

### B2. 伪造底层 enabled 心跳

终端 D：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic pub -r 5 \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /fans/enabled std_msgs/msg/Bool \
  "{data: true}"
```

预期：

- 独立模式进入 `MANUAL_WAITING`；
- 命令仍为 `[800, 800]`；
- 没有旧命令被恢复。

停止终端 D 的 enabled 心跳并等待超过 1 秒，预期：

- 状态变为 `DISABLED`；
- 命令立即保持 `[800, 800]`；
- 手动缓存和 AUTO 请求被清除。

后续测试前重新启动终端 D。

### B3. 双路手动命令和超时

终端 E：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic pub -r 10 \
  /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [1000, 1100]}"
```

预期：

- 状态为 `MANUAL_ACTIVE`；
- `/fans/command_pwm` 为 `[1000, 1100]`。

停止终端 E 并等待超过 0.5 秒，预期：

- 左右同时回到 800；
- 状态为 `MANUAL_WAITING`。

### B4. 左右通道独立新鲜度

终端 E 只持续发布左侧：

```bash
ros2 topic pub -r 10 \
  /fans/left/pwm std_msgs/msg/Int32 \
  "{data: 1050}"
```

终端 F 单次发布右侧：

```bash
ros2 topic pub --once \
  /fans/right/pwm std_msgs/msg/Int32 \
  "{data: 1150}"
```

预期：

- 刚发布时为 `[1050, 1150]`；
- 0.5 秒后右侧单独回到 800；
- 左侧保持 1050；
- 左侧消息没有给右侧续期。

停止终端 E 并等待 0.5 秒，预期双侧回到 `[800, 800]`。

### B5. 错误消息拒绝

错误长度：

```bash
ros2 topic pub --once \
  /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [1000]}"
```

pair 任一值越界：

```bash
ros2 topic pub --once \
  /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [1000, 2300]}"
```

单侧越界：

```bash
ros2 topic pub --once \
  /fans/left/pwm std_msgs/msg/Int32 \
  "{data: 799}"
```

预期：

- 管理器日志明确拒绝；
- 命令不采用非法值；
- 有效命令时间不被刷新；
- pair 不发生部分接受。

### B6. AUTO 启用条件

确保终端 D 正在发布 enabled=true。

终端 E 发布新鲜电机 AUTO：

```bash
ros2 topic pub -r 5 \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /motors/control_mode std_msgs/msg/String \
  "{data: AUTO}"
```

终端 F 先发布零姿态：

```bash
ros2 topic pub -r 20 \
  /imu/relative_roll_pitch geometry_msgs/msg/Vector3Stamped \
  "{vector: {x: 0.0, y: 0.0, z: 0.0}}"
```

启用 AUTO：

```bash
ros2 service call /fans/auto_enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

预期：

- 服务成功；
- 服务返回后先等待一帧新姿态；
- 随后 `/fans/auto_enabled=true`；
- `/fans/auto_active=true`；
- 零姿态时目标和命令仍为 `[800, 800]`。

分别验证以下姿态；每次只运行一个姿态发布命令：

正 pitch 10°：

```bash
ros2 topic pub -r 20 \
  /imu/relative_roll_pitch geometry_msgs/msg/Vector3Stamped \
  "{vector: {x: 0.0, y: 0.1745329252, z: 0.0}}"
```

负 pitch 10°：

```bash
ros2 topic pub -r 20 \
  /imu/relative_roll_pitch geometry_msgs/msg/Vector3Stamped \
  "{vector: {x: 0.0, y: -0.1745329252, z: 0.0}}"
```

左倾 roll 20°：

```bash
ros2 topic pub -r 20 \
  /imu/relative_roll_pitch geometry_msgs/msg/Vector3Stamped \
  "{vector: {x: -0.3490658504, y: 0.0, z: 0.0}}"
```

右倾 roll 20°：

```bash
ros2 topic pub -r 20 \
  /imu/relative_roll_pitch geometry_msgs/msg/Vector3Stamped \
  "{vector: {x: 0.3490658504, y: 0.0, z: 0.0}}"
```

预期：

- 正负 10° pitch 的左右目标相同；
- 左倾只提高左侧目标；
- 右倾只提高右侧目标；
- `/fans/auto_target_pwm` 是限速前目标；
- `/fans/command_pwm` 从 800 每个 20 Hz 周期最多上升 10；
- 正常下降每周期最多下降 20；
- 45° 及更大活动量的自动目标不超过 1400。

停止姿态发布并等待超过 0.2 秒，预期：

- 立即输出 `[800, 800]`，不经过缓降；
- `auto_enabled=false`；
- `auto_active=false`；
- 恢复姿态发布后不会自动恢复 AUTO，必须重新调用服务。

### B7. 归零代次清除 AUTO

重新满足条件并启用 AUTO 后执行：

```bash
ros2 topic pub --once \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /imu/zero_generation std_msgs/msg/UInt64 \
  "{data: 1}"
```

预期：

- AUTO 请求立即清除；
- 双路立即回到 800；
- 归零前姿态不能重新激活 AUTO；
- 必须先有代次之后的新姿态，再显式申请 AUTO。

### B8. 独立模式急停恢复

先停止旧的 enabled 持续发布者，并在其 1 秒新鲜度过期前立即执行：

```bash
ros2 topic pub --once \
  /e_stop std_msgs/msg/Bool \
  "{data: true}"
```

预期立即进入 `EMERGENCY_STOP`、清除全部缓存并输出 `[800, 800]`。

随后重新启动 B2 的 enabled=true 发布命令，以模拟急停事件后的显式底层
恢复。预期独立模式进入 `MANUAL_WAITING`，但不恢复旧手动命令或 AUTO。

### B9. 统一模式双条件恢复

停止终端 A，重新以统一模式启动管理器：

```bash
ros2 run windarmor_fan_controller fan_command_manager \
  --ros-args \
  --params-file src/windarmor_fan_controller/config/fan_params.yaml \
  -p require_motor_mode_for_manual:=true
```

先发布新鲜 enabled=true 和电机 MANUAL：

```bash
ros2 topic pub -r 5 \
  --qos-reliability reliable \
  --qos-durability transient_local \
  /motors/control_mode std_msgs/msg/String \
  "{data: MANUAL}"
```

确认状态为 `MANUAL_WAITING` 后：

1. 先停止急停前的 enabled 和 motor mode 持续发布者；
2. 在两类状态的 1 秒新鲜度过期前立即触发 `/e_stop=true`；
3. 只重新启动 enabled=true；
4. 确认仍为 `EMERGENCY_STOP`；
5. 发布新的 `EMERGENCY_STOP` 电机模式，确认仍不能恢复；
6. 停止该发布者，再发布新的 MANUAL；
7. 确认只有此时进入 `MANUAL_WAITING`；
8. 确认没有恢复任何旧 PWM 或 AUTO。

测试完成后，在所有 B 级终端按 `Ctrl+C`，确认没有残留测试节点。

## 6. C 级：经授权的单设备验证

本节不是当前自动执行步骤。每次执行前必须由用户明确授权相应设备和准确命令。

### C1. 真实 IMU 只读验证

授权范围应明确为“允许访问 `/dev/imu_usb`，不启动电机控制器和风扇”。

准确启动命令：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 \
  imu_cybergear_system.launch.py \
  start_controller:=false \
  start_rviz:=false
```

另一个终端观察：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic echo /imu/data_raw
```

验证：

- 消息持续到达；
- `header.frame_id` 符合配置；
- 四元数为有限值且范数合理；
- 静止时数据没有明显跳变；
- 拔出或停止 IMU 后节点能进入已有安全/重连行为。

注意：此模式没有启动电机控制器，因此不会发布本次新增的统一相对姿态。

### C2. 断开风扇动力后的底层 GPIO 维护验证

即使风扇动力电池断开，`fan_controller` 仍会占用 GPIO12/13 并输出 PWM，
因此也必须先获得明确授权。确认两个电调的动力供电物理断开，且管理器未运行。

启动命令：

```bash
ros2 run windarmor_fan_controller fan_controller \
  --ros-args \
  --params-file src/windarmor_fan_controller/config/fan_params.yaml
```

只允许用停止值验证路由：

```bash
ros2 topic pub --once \
  /fans/command_pwm std_msgs/msg/Int32MultiArray \
  "{data: [800, 800]}"
```

观察：

```bash
ros2 topic echo /fans/enabled
ros2 topic echo /fans/status_pwm
```

依次验证；每一步完成后先确认没有持续的命令发布者：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
ros2 topic pub --once /fans/command_pwm \
  std_msgs/msg/Int32MultiArray "{data: [800, 800]}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
ros2 topic pub --once /fans/command_pwm \
  std_msgs/msg/Int32MultiArray "{data: [800, 800]}"
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

预期：

- stop 和 e-stop 后 enabled=false；
- disabled 时拒绝 `/fans/command_pwm`；
- stop 后的命令被拒绝；
- enable=true 后 enabled=true，但收到下一条新命令前状态仍为 `[800, 800]`；
- 只有 enable 之后的新命令才更新时间；
- 新命令到达后再等待超过 1 秒，仍保持 `[800, 800]`；
- `Ctrl+C` 退出后 GPIO 资源释放。

不得在这一级发送大于 800 μs 的值，不得接通风扇动力。

## 7. D 级：带电实机验证

当前不得直接执行本节。任何微电机或风扇通电测试都必须先停止，由执行者向用户
提交并获得以下十项明确授权：

1. 需要通电的设备；
2. 为什么此时必须带电；
3. 准备执行的准确命令；
4. 哪些电机预计运动或哪些风扇预计旋转；
5. 预计运动方向；
6. 初始角度、速度、力矩、PWM 或油门限制；
7. 预计持续时间；
8. 急停方法；
9. 异常停止条件；
10. 测试后恢复安全状态的方法。

必须逐项填入实际值，不能只引用本模板。用户明确同意前，不得执行 CAN 初始化、
电机控制节点、风扇 GPIO 节点、统一 launch 或任何非停止动力命令。

### D1. 电机验证建议顺序

获得针对电机的十项授权后：

1. 可靠固定机器人；
2. 风扇动力保持断开；
3. 确认四个电机 ID、方向和软限位；
4. 准备键盘空格、`/e_stop` 和物理断电；
5. 经授权后初始化 CAN：

```bash
cd /home/h-goal/workspace/WindArmor
sudo ./scripts/setup_can.sh can10
```

6. 经授权后启动 IMU 和电机，关闭键盘以避免误按：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch imu_cybergear_ros2 \
  imu_cybergear_system.launch.py \
  enable_keyboard:=false \
  start_rviz:=false \
  control_backend:=socketcan_hat \
  can_channel:=can10
```

7. 先观察，不发布手动目标：

```bash
ros2 topic echo /motors/control_mode
ros2 topic echo /imu/relative_roll_pitch
ros2 topic echo /motor/status
```

8. 按授权的最小角度逐台验证方向和软限位；
9. 触发急停，确认模式为 `EMERGENCY_STOP`；
10. 调用恢复服务，确认成功后只进入 `MANUAL`：

```bash
ros2 service call /enable_motor \
  std_srvs/srv/SetBool \
  "{data: true}"
```

11. 测试结束立即急停、关闭 launch、断开动力，并记录各电机最终位置。

手动目标命令必须根据当次授权填写，不能直接照抄通用大角度值。

### D2. 风扇验证建议顺序

风扇测试必须与电机授权分开描述。首次验证建议电机动力保持断开，机器人可靠
固定，风道前后无人和松散物体。

获得针对风扇的十项授权后：

1. 先以 800 μs 启动并确认停止状态；
2. 验证 `/fans/stop`、`/fans/enable` 和 `/e_stop`；
3. 每次只测一侧，确认 GPIO12/13 与左右实际接线；
4. 从 800 μs 以最小步长缓慢增加，记录首次稳定起转值；
5. 未完成起转标定前，不直接假定 1200 μs 安全；
6. 单侧方向和停止可靠后，再测试双侧；
7. 手动链路验证后，才考虑 AUTO；
8. AUTO 首轮应限制在当次授权的更低上限和短持续时间；
9. 验证姿态超时、电机离开 AUTO、enabled 超时和急停都会立即停止；
10. 结束时调用 stop、关闭节点、断开风扇动力。

正式风扇启动命令会同时启动管理器和 GPIO 底层：

```bash
ros2 launch windarmor_fan_controller fans.launch.py
```

统一系统命令会同时涉及 IMU、CAN、电机和 GPIO，只有所有相关设备均获得授权
后才能使用：

```bash
ros2 launch windarmor_bringup windarmor.launch.py
```

首次带电验证不建议直接从统一系统开始。

### D3. 最终目标：IMU 倾斜联动四电机与双风扇

这一节回答“怎样直接验证最终联动目标”。它是整套系统风险最高的验证，不能用来
替代 D1/D2。只有以下前置项全部通过，才进入本节：

- A、B 级通过；
- C1 的 IMU 数据稳定；
- D1 已逐台确认四个电机的 ID、方向、机械零点、软限位和急停；
- D2 已分别确认左右风扇接线、停止可靠性和实际起转 PWM；
- 已确认 1200/1400 μs 是否适用于当前电调、风扇和电源；
- 机器人被刚性固定，运动机构和风道均有足够净空；
- 一人操作，一人专职看护急停和物理断电；
- 四个电机和两个风扇的十项带电授权已针对本次准确命令获批。

#### D3.1 本轮十项授权建议填写内容

提交授权时至少填成如下具体形式；`<...>` 必须替换为 D1/D2 的实测值：

1. 通电设备：CyberGear ID 4、3、2、1，左风扇 GPIO12、右风扇 GPIO13；
2. 原因：验证最终目标——四电机和双风扇是否随统一 IMU 相对姿态联动；
3. 准确命令：本节 D3.3 至 D3.9 列出的 CAN 初始化、统一 launch、服务和急停
   命令；
4. 预计运动设备：启动初始化时四个电机可能以 0.5 rad/s 修正到各自已标定的
   机械零点；进入 AUTO 后每个方向只运动对应电机和风扇，见 D3.7 表格；
5. 预计方向：按 `/imu/relative_roll_pitch` 的正负号说明，不能只写“随倾斜”；
6. 初始限制：
   - 相对 roll/pitch 均限制在 `±10°`（`±0.1745 rad`）；
   - 电机 `default_speed=0.5 rad/s`；
   - 电机 `max_position_step=0.03 rad/次`；
   - 风扇停止值 `800 μs`；
   - 风扇起转值 `<D2 实测值> μs`；
   - 风扇 AUTO 上限 `<本轮批准值> μs`，不得高于已实测安全值；
   - 风扇正常上升/下降步长保持 `10/20 μs`；
7. 持续时间：每个倾斜方向首次保持不超过 2 秒，回中确认后再测下一方向，
   本轮总带电时间不超过 2 分钟；
8. 急停：launch 键盘空格、独立 `/e_stop=true` 终端、风扇电池断开和电机
   主电源断开；
9. 异常停止：方向错误、越限、冲击、抖动、异常声响/电流/温度、风扇非预期
   起转、状态超时不停止、任一急停无效；
10. 恢复：发布急停，确认 800 μs 和 `EMERGENCY_STOP`，先断风扇动力，再断
    电机动力，最后退出 launch 并保存日志。

用户必须明确同意填写后的内容。仅回复“可以测试”但没有明确设备、限制和命令，
不足以满足本仓库的带电授权门槛。

#### D3.2 生成本轮保守参数副本

不要为了验证而修改仓库中的受保护电机映射。使用 `/tmp` 副本降低电机速度和
单次目标变化：

```bash
cd /home/h-goal/workspace/WindArmor
cp src/imu_cybergear_ros2/config/imu_cybergear_params.yaml \
  /tmp/windarmor_motor_integrated_test.yaml
cp src/windarmor_fan_controller/config/fan_params.yaml \
  /tmp/windarmor_fan_integrated_test.yaml
sed -i 's/default_speed: 10.0/default_speed: 0.5/' \
  /tmp/windarmor_motor_integrated_test.yaml
sed -i 's/max_position_step: 0.4/max_position_step: 0.03/' \
  /tmp/windarmor_motor_integrated_test.yaml
```

然后人工打开风扇临时副本：

```bash
nano /tmp/windarmor_fan_integrated_test.yaml
```

只把以下两项改成 D2 已验证且本轮获批的值：

```yaml
fan_start_pwm_us: <D2 实测起转值>
fan_auto_max_pwm_us: <本轮批准且不高于实测安全上限的值>
```

必须满足：

```text
800 <= fan_start_pwm_us <= fan_auto_max_pwm_us <= 已实测安全上限
```

若尚无 D2 实测起转值，不得继续本节，也不得直接把软件候选值
`1200/1400 μs` 当作已验证值。

检查临时文件没有改变受保护映射：

```bash
rg -n \
  "motor_ids:|motor_signs:|motor_limits_min:|motor_limits_max:|default_speed:|max_position_step:" \
  /tmp/windarmor_motor_integrated_test.yaml
rg -n \
  "left_gpio:|right_gpio:|fan_stop_pwm_us:|fan_start_pwm_us:|fan_auto_max_pwm_us:" \
  /tmp/windarmor_fan_integrated_test.yaml
```

#### D3.3 物理准备和急停终端

1. 让机器人机械固定，把四个电机机构放在 D1 已确认的机械零位，并保证批准的
   `±10°` 范围内没有干涉；
2. 清空两个风道前后区域；
3. IMU 固定方向与 D1 一致；
4. 风扇动力电池暂时保持断开；
5. 电机主电源暂时保持断开；
6. 操作者把手放在 launch 终端的空格键附近；
7. 安全员能够立即断开风扇电池和电机主电源。

准备一个专用急停终端，但此时不要发送：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

该命令应保留在终端历史中，以便异常时立即回车执行。

#### D3.4 CAN 和供电顺序

只有十项授权生效后才执行：

1. 风扇动力继续断开；
2. 接通电机动力；
3. 初始化 CAN：

```bash
cd /home/h-goal/workspace/WindArmor
sudo ./scripts/setup_can.sh can10
```

4. 确认 `can10` 没有报错；
5. 不要手工发布任何电机目标；
6. 先启动统一系统，让风扇 GPIO 在无动力状态下建立 800 μs 停止输出；
7. 系统状态全部正确后，才按 D2 已验证的电调流程接通风扇动力。

#### D3.5 启动统一系统

launch 终端：

```bash
cd /home/h-goal/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch windarmor_bringup windarmor.launch.py \
  motor_params_file:=/tmp/windarmor_motor_integrated_test.yaml \
  fan_params_file:=/tmp/windarmor_fan_integrated_test.yaml \
  enable_motor_keyboard:=true \
  control_backend:=socketcan_hat \
  can_channel:=can10
```

启动后暂时不要按 `m`，不要倾斜 IMU。预期：

- 电机模式为 MANUAL；
- 风扇 AUTO 仍为 false；
- 风扇保持 800 μs；
- 没有电机自动跟随动作；
- 没有风扇旋转。

电机初始化会写入目标位置 0；若机构没有准确位于已标定零位，四个电机可能以
0.5 rad/s 向零位做小幅修正，这一运动必须包含在本轮授权中。若运动方向不是
朝已确认零位、幅度超出预期或任何风扇启动时旋转，立即急停并断电，本轮失败。

#### D3.6 监视状态、归零和启用顺序

以下观察命令分别放在独立终端：

```bash
ros2 topic echo /imu/relative_roll_pitch
ros2 topic echo /motors/control_mode
ros2 topic echo /fans/control_state
ros2 topic echo /fans/auto_enabled
ros2 topic echo /fans/auto_active
ros2 topic echo /fans/auto_target_pwm
ros2 topic echo /fans/status_pwm
ros2 topic echo /motor/status
```

按以下顺序操作：

1. 把机器人和 IMU 保持在机械中位；
2. 设置统一 IMU 零点：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
```

3. 确认相对 roll/pitch 接近 0；
4. 先把风扇底层显式锁存停止：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
```

5. 再显式启用底层；它必须仍保持 800，不能恢复旧命令：

```bash
ros2 service call /fans/enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

6. 在 launch 终端按一次 `m`，把电机从 MANUAL 切换到 AUTO；
7. 确认 `/motors/control_mode` 明确为 `AUTO`；
8. 确认此时风扇仍未自动启动；
9. 显式启用风扇 AUTO：

```bash
ros2 service call /fans/auto_enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

10. 预期先出现 `AUTO_WAITING`，收到服务后的新姿态后变成
    `AUTO_ACTIVE`；
11. 中位姿态下即使 `AUTO_ACTIVE=true`，双风扇仍应保持 800。

任一步骤状态不符都不要继续倾斜。

#### D3.7 分方向小角度联动验证

以 `/imu/relative_roll_pitch` 的实际数值为准，不能凭肉眼假定正负。每次从
0° 缓慢增加到 6°，确认方向正确后最多增加到 10°；首次只保持 1～2 秒，
随后缓慢回中并等系统稳定。

| 相对姿态 | 预期电机目标方向 | 预期风扇 |
|---|---|---|
| `pitch > +5°` | ID3 正方向、ID2 负方向；ID4/ID1 回零 | 左右同时增加，目标相同 |
| `pitch < -5°` | ID3 负方向、ID2 正方向；ID4/ID1 回零 | 左右同时增加，与同绝对值正 pitch 相同 |
| `roll < -5°` | ID4 负方向；ID1 回零；俯仰电机回零 | 左风扇增加，右风扇保持 800 |
| `roll > +5°` | ID1 正方向；ID4 回零；俯仰电机回零 | 右风扇增加，左风扇保持 800 |
| roll/pitch 均接近 0 | 四电机回到各自零目标 | 左右最终回到 800 |

这里的“正/负方向”指软件目标符号，不代表尚未确认的机械前后方向。D1 必须已把
这些软件符号与实际机械运动方向对应起来。

每个方向都记录：

```text
relative roll/pitch：
ID4/ID3/ID2/ID1 实际位置和方向：
左/右 auto_target_pwm：
左/右 status_pwm：
是否符合表格：
回中所需时间：
是否有抖动、冲击、异常声响或温升：
```

预期变化规律：

- 5° 以下保持风扇停止；
- 从停止跨到 5° 时，目标进入已标定起转值；
- 自动目标不超过临时配置中的获批上限；
- 正常风扇命令每个 20 Hz 周期最多上升 10 μs、下降 20 μs；
- 姿态正常回中属于正常缓降，不要求瞬间从运行值跳到 800；
- 急停或状态超时必须绕过缓降并立即到 800；
- pitch 和 roll 复合时每侧取较大活动量，不应把两者简单相加。

任何一侧、电机或方向与表格不符，立即急停，不要尝试通过现场修改
`motor_signs`、软限位或 GPIO 映射来继续。

#### D3.8 统一归零和 AUTO 清退验证

在小角度、短持续时间且所有方向正确后，可验证归零联动：

1. 先回到机械中位并确认风扇回到 800；
2. 重新启用风扇 AUTO，确认状态正常；
3. 调用：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
```

预期：

- `/imu/zero_generation` 递增；
- 风扇 AUTO 请求立即清除；
- `auto_enabled=false`、`auto_active=false`；
- 风扇立即保持 800；
- 归零前缓存姿态不能重新启动风扇；
- 电机继续使用新零点计算后续 AUTO 目标；
- 用户必须再次显式调用 `/fans/auto_enable=true`。

#### D3.9 急停、恢复和结束

在不倾斜设备时先做一次计划内急停：

```bash
ros2 topic pub --once \
  /e_stop std_msgs/msg/Bool \
  "{data: true}"
```

必须观察到：

- 电机立即停止并进入 `EMERGENCY_STOP`；
- 风扇立即回到 800；
- `/fans/enabled=false`；
- 管理器进入 `EMERGENCY_STOP`；
- 所有旧手动命令、旧姿态和 AUTO 请求被清除。

若本轮授权包含恢复测试，严格按以下顺序：

1. 保持设备中位；
2. 恢复电机：

```bash
ros2 service call /enable_motor \
  std_srvs/srv/SetBool \
  "{data: true}"
```

3. 确认电机只进入 `MANUAL`，不进入 AUTO；
4. 恢复风扇底层：

```bash
ros2 service call /fans/enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

5. 确认统一模式只有收到急停后的新 MANUAL 和 enabled=true 后，管理器才进入
   `MANUAL_WAITING`；
6. 确认没有恢复任何旧 PWM；
7. 不再继续联动，除非本轮授权明确包含第二轮 AUTO。

结束顺序：

1. 再次发布 `/e_stop=true`；
2. 确认 `/fans/status_pwm=[800, 800]` 和电机 `EMERGENCY_STOP`；
3. 物理断开风扇动力；
4. 物理断开电机动力；
5. 在 launch 终端按 `Ctrl+C`；
6. 确认进程退出且 GPIO/CAN 不再由程序占用；
7. 保存所有终端日志和记录；
8. 删除临时参数文件：

```bash
rm /tmp/windarmor_motor_integrated_test.yaml
rm /tmp/windarmor_fan_integrated_test.yaml
```

只有上述分方向、归零、急停和恢复均符合预期，才能把“风扇和微电机随 IMU
倾斜而转动”记录为已完成实机验证；否则应记录为部分通过或失败。

## 8. 失败和异常处理

出现以下任一情况立即停止当前验证：

- 实际节点、话题、服务或参数与本文档不一致；
- 出现第二个 `/fans/command_pwm` 正常发布者；
- 底层继续订阅公共手动话题；
- 无效/超时消息产生非停止命令；
- 急停后输出没有立即回到停止值；
- enable 恢复了旧 PWM；
- 风扇 AUTO 在没有新姿态时激活；
- 电机恢复后直接进入 AUTO；
- GPIO 接线、CAN ID 或方向与配置不一致；
- 电机越过软限位或出现异常电流、温度、声音、振动；
- 风扇意外起转、反向、抖动或停止不可靠；
- 任何设备、线缆、电调、驱动或电源异常发热。

软件验证失败时保存日志并退出节点。硬件验证失败时优先急停和物理断电，再保存
日志；不得为了继续测试而绕过 `/e_stop`、看门狗、软限位或 disabled 锁存。

## 9. 本次推荐的实际执行范围

当前代码已经完成 A 级自动验证。下一步人工审查优先执行：

1. 阅读代码和本文档；
2. 复跑 A 级；
3. 执行 B 级管理器伪消息验证；
4. 汇报结果；
5. 再决定是否单独授权 C1 或 C2。

当前不建议直接执行 D 级，也不要求现在给任何设备通电。
