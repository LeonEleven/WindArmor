# WindArmor

WindArmor 当前把两个已经过实机测试的前置项目整合为一个 ROS 2 Jazzy
工作空间，可同时运行：

- Hiwonder IMU；
- 4 个小米 CyberGear 电机；
- 2 个涵道风扇。

当前稳定发布仍为 `v0.2.1`。本分支包含 `v0.3.0` 候选的软件实现：统一相对
姿态、电机模式状态、风扇手动/自动仲裁和强化急停恢复。该候选目前只完成
纯软件构建、纯函数/替身测试和静态路由检查；电机与风扇均未通电验证，
自动风扇默认关闭。`1200 μs` 启动值和 `1400 μs` 自动上限也尚未实机标定。

## 硬件默认配置

### 电机与 IMU

- IMU：`/dev/imu_usb`，9600 baud；
- CyberGear：微雪 2-CH CAN HAT+ 的 `can10`，1 Mbps；
- 电机 CAN ID 顺序：4、3、2、1。

以下实机方向和软限位配置保持自前置项目，没有改动：

```yaml
motor_signs: [-1.0, 1.0, -1.0, 1.0]
motor_limits_min: [-1.57, -1.57, -1.57, 0.0]
motor_limits_max: [0.0, 1.57, 1.57, 1.57]
```

### 双风扇

代码使用 BCM GPIO 编号：

| 风扇 | BCM GPIO | 树莓派物理引脚 |
|---|---:|---:|
| 左风扇 PWM | GPIO12 | 32 |
| 右风扇 PWM | GPIO13 | 33 |
| GND | — | 34 或其他 GND |

GPIO12 是原单风扇项目已验证的连接。GPIO13 是为第二路风扇设置的默认值，
首次上电前必须确认它确实接到了第二个电调的信号线；如实际接线不同，请修改
`src/windarmor_fan_controller/config/fan_params.yaml`。

## 安装与构建

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
sudo apt update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

每次树莓派开机后，初始化一次 `can10`：

```bash
cd ~/workspace/WindArmor
sudo ./scripts/setup_can.sh can10
```

## 启动整套系统

> 以下启动操作会访问真实 IMU、CAN 和 GPIO，且可能控制电机或风扇。只有在
> 获得明确硬件测试授权、完成安全检查并满足仓库带电测试门槛后才能执行。

启动前让机器人可靠固定，移除风扇周围的人员和松散物体，并先断开风扇动力电池。

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch windarmor_bringup windarmor.launch.py
```

节点开始输出 800 μs 最低油门后，再按电调的正常解锁顺序接通风扇动力。
该终端用于原电机控制键盘；其中空格键现在会同时急停电机和风扇。
按 `q` 会先停止全部电机，再关闭整套系统中的电机、IMU 和风扇节点。

### 正常运行：让电机和风扇随 IMU 联动

> 本节是完成单设备方向、零点、软限位、风扇起转值和急停验证后的正常运行
> 流程，不是首次带电调试流程。当前候选值 `1200 μs` 和 `1400 μs` 尚未实机
> 标定；标定完成并获得硬件运行授权前，不得直接按本节给全部动力设备通电。
> 完整的首次实机验证和十项授权要求见
> [人工验证指南的 D3 节](docs/MANUAL_VERIFICATION.md#d3-最终目标imu-倾斜联动四电机与双风扇)。

仅执行 `windarmor.launch.py` 不会立即进入最终联动：电机初始化后默认处于
MANUAL，风扇 AUTO 也默认关闭。启动后按以下顺序操作。

1. 在机械中位保持 IMU 和机器人静止。注意控制器配置阶段会给四个电机写入
   目标位置 0；如果机构不在已标定零位，电机可能在进入 AUTO 前就向零位
   修正。
2. 在第二个终端加载环境：

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

3. 设置统一 IMU 零点：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
```

4. 显式清除风扇旧状态并重新启用底层。`enable=true` 之后仍保持 800 μs，
   不会恢复旧命令：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
```

5. 在运行 `windarmor.launch.py` 的终端按一次 `m`，将电机从 MANUAL 切换到
   AUTO。先确认模式确实为 AUTO：

```bash
ros2 topic echo /motors/control_mode
```

6. 此时电机开始使用统一相对姿态，但风扇仍不会自动旋转。显式启用风扇
   AUTO：

```bash
ros2 service call /fans/auto_enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

7. 观察以下状态。每条 `topic echo` 应在独立终端运行：

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

预期进入：

```text
/motors/control_mode = AUTO
/fans/control_state = AUTO_ACTIVE
/fans/auto_enabled = true
/fans/auto_active = true
```

`AUTO_ACTIVE` 只表示自动条件成立；中位或小于风扇死区的姿态仍输出
`[800, 800]`。当前方向关系为：

| 统一相对姿态 | 电机软件目标 | 风扇行为 |
|---|---|---|
| `pitch > +5°` | ID3 正、ID2 负，ID4/ID1 回零 | 左右同时增加 |
| `pitch < -5°` | ID3 负、ID2 正，ID4/ID1 回零 | 左右同时增加 |
| `roll < -5°` | ID4 负，其他轴回零 | 左风扇增加 |
| `roll > +5°` | ID1 正，其他轴回零 | 右风扇增加 |
| roll/pitch 接近 0 | 四电机回到零目标 | 左右最终回到 800 μs |

表中的正负是软件目标符号；实际机械前后方向必须在单设备验证中确认。正常姿态
回中时风扇按下降步长回落；急停或状态超时才会绕过缓降并立即输出停止值。

运行中再次调用 `/imu/set_zero` 会清除风扇 AUTO 请求并立即停止风扇。归零
后需要等待新姿态，再重新执行：

```bash
ros2 service call /fans/auto_enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

### 急停后的正常恢复

空格键或 `/e_stop=true` 会停止电机、把风扇锁存为 disabled，并清除全部旧
手动命令、姿态缓存和风扇 AUTO 请求：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

确认设备处于中位且异常原因已经排除后，按以下顺序恢复：

```bash
ros2 service call /enable_motor \
  std_srvs/srv/SetBool \
  "{data: true}"
ros2 service call /fans/enable \
  std_srvs/srv/SetBool \
  "{data: true}"
```

`/enable_motor=true` 只恢复到 MANUAL。随后仍需：

1. 在 launch 终端按一次 `m`，重新进入电机 AUTO；
2. 确认 `/motors/control_mode=AUTO`；
3. 再调用 `/fans/auto_enable=true`。

系统不会在急停条件消失后偷偷恢复旧 AUTO 或旧 PWM。

### 正常结束

先让机器人回中，然后按空格或发布 `/e_stop=true`。确认电机为
`EMERGENCY_STOP`、风扇状态为 `[800, 800]` 后，按已经验证的安全顺序断开
风扇和电机动力，最后在 launch 终端按 `q` 或 `Ctrl+C` 退出。不得直接断开
终端而让动力设备在未知状态下继续供电。

### 手动风扇键盘（非 AUTO）

需要手动控制风扇时，可在另一个终端运行键盘节点，避免与电机键盘争用同一个
终端输入。启用风扇 AUTO 后不要同时发送手动命令：

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run windarmor_fan_controller fan_keyboard
```

风扇键盘：

- `1` / `2` / `3`：选择左、右或双路；
- `↑` / `↓`：以 20 μs 步进增加或降低所选风扇；
- `s`：两个风扇回到 800 μs；
- `空格`：向 `/e_stop` 发布系统急停，电机和风扇都会停止；
- `r`：重新启用风扇控制，但仍保持 800 μs；
- `q`：风扇回到 800 μs并退出键盘节点。

电机键位沿用前置项目，详见
`src/imu_cybergear_ros2/README.md`。

## ROS 2 控制接口

正常模式下，公共手动接口保持兼容。双路同时控制（数组顺序为左、右）：

```bash
ros2 topic pub -r 10 /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [800, 800]}"
```

也可分别发布 `/fans/left/pwm` 和 `/fans/right/pwm`。管理器分别记录左右
通道时间；默认 `0.5 s` 后仅停止超时的一侧，一侧消息不会为另一侧续期。
越界消息会被拒绝，不会静默限幅或刷新时间。

这些公共话题只进入 `fan_command_manager`。管理器仲裁后通过内部
`/fans/command_pwm` 向底层发送唯一正常命令；该内部话题不属于普通公共
控制接口。底层仍保留最终限幅和默认 `1.0 s` 命令看门狗。当前实际输出可从
`/fans/status_pwm` 查看，底层接受状态可从 `/fans/enabled` 查看。

### 相对姿态、电机模式与风扇 AUTO

`/imu/relative_roll_pitch` 使用
`geometry_msgs/msg/Vector3Stamped`，`x/y` 分别为统一修正并归零后的
roll/pitch（rad），header 沿用原始 IMU 消息。MANUAL 和 AUTO 电机模式都会
持续发布有效姿态。`/motors/control_mode` 的稳定值为 `MANUAL`、`AUTO`、
`EMERGENCY_STOP`、`DISABLED` 或 `ERROR`。

风扇 AUTO 默认关闭。只有电机模式是新鲜的 `AUTO`、底层风扇已启用、姿态
有效且新鲜、急停锁存已恢复时，以下请求才会成功：

```bash
ros2 service call /fans/auto_enable std_srvs/srv/SetBool "{data: true}"
```

成功后先进入 `AUTO_WAITING` 并保持停止，收到服务成功之后的新姿态才进入
`AUTO_ACTIVE`。`/fans/auto_enabled` 表示 AUTO 请求仍被保留，
`/fans/auto_active` 表示全部运行条件成立且已有启用后的新姿态；
`/fans/auto_target_pwm` 是变化率限制前的目标，
`/fans/control_state` 是管理器状态。

AUTO 使用 `max()` 合成姿态活动量：正负 pitch 都同时提高左右目标；左倾只
增加左侧 roll 分量，右倾只增加右侧 roll 分量。任一姿态、电机模式或底层
状态超时都会立即停止、清除 AUTO 请求，条件恢复后也不会自动重新启用。

系统急停：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

MANUAL 模式下可按 `motor_ids` 的配置顺序（默认 `[4, 3, 2, 1]`）发送
电机绝对目标，单位为弧度。节点仍会应用已有软限位与单步变化限制：

```bash
ros2 topic pub --once /motors/manual_targets \
  std_msgs/msg/Float64MultiArray "{data: [0.0, 0.0, 0.0, 0.0]}"
```

IMU 与电机归零服务：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
ros2 service call /motors/set_zero std_srvs/srv/Trigger "{}"
```

急停后分别恢复电机与风扇（恢复时风扇仍保持最低油门和空命令缓存）：

```bash
ros2 service call /enable_motor std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
```

`/enable_motor=true` 成功后只恢复到 `MANUAL`，不会直接进入 AUTO。
`/fans/enable=true` 会保持停止并等待新命令，绝不恢复旧 PWM。在统一
`windarmor.launch.py` 模式中，单独恢复风扇还不能清除管理器的系统急停
锁存；急停事件之后还必须收到新的、允许的电机 `MANUAL` 或 `AUTO` 状态。

只停止风扇而不影响电机（该服务会把底层锁存为 disabled）：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
```

## 单独调试

以下同样属于真实硬件操作，必须先获得明确授权。

只启动 IMU 和电机：

```bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py
```

只启动双风扇：

```bash
ros2 launch windarmor_fan_controller fans.launch.py
```

`fans.launch.py` 启动一个管理器和一个底层控制器，默认
`require_motor_mode_for_manual=false`，因此可独立接收公共手动命令；没有
电机 AUTO 状态时仍不能启用风扇 AUTO。统一 `windarmor.launch.py` 会覆盖为
`true`，手动风扇也要求新鲜的 `MANUAL` 或 `AUTO` 电机状态。

单独运行 `fan_controller` 只用于已授权的底层维护：它会占用 GPIO12/13、
初始化电调，只订阅内部 `/fans/command_pwm`，且运行前必须确认管理器未运行。
它不是正常公共控制方式；正式操作应使用 `fans.launch.py` 或
`windarmor.launch.py`。

当前尚未运行任何 ROS 2 节点或 launch，也未访问 IMU、CAN、GPIO 或串口。
后续真实硬件、通电或标定验证都必须另行获得用户明确授权。

统一启动时也可关闭部分组件：

```bash
ros2 launch windarmor_bringup windarmor.launch.py start_fans:=false
ros2 launch windarmor_bringup windarmor.launch.py start_controller:=false
```
