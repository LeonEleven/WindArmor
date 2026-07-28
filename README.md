# WindArmor

WindArmor 当前把两个已经过实机测试的前置项目整合为一个 ROS 2 Jazzy
工作空间，可同时运行：

- Hiwonder IMU；
- 4 个小米 CyberGear 电机；
- 2 个涵道风扇。

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

启动前让机器人可靠固定，移除风扇周围的人员和松散物体，并先断开风扇动力电池。

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch windarmor_bringup windarmor.launch.py
```

节点开始输出 800 μs 最低油门后，再按电调的正常解锁顺序接通风扇动力。
该终端用于原电机控制键盘；其中空格键现在会同时急停电机和风扇。
双风扇键盘应在第二个终端运行，避免两个程序争用
同一个终端输入：

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

双路同时控制（数组顺序为左、右）：

```bash
ros2 topic pub -r 10 /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [800, 800]}"
```

由于默认启用了 1 秒指令看门狗，直接用话题控制时应持续发布。也可分别发布
`/fans/left/pwm` 和 `/fans/right/pwm`。当前实际输出可从
`/fans/status_pwm` 查看。

系统急停：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

急停后分别恢复电机与风扇（恢复时风扇仍保持最低油门）：

```bash
ros2 service call /enable_motor std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
```

只停止风扇而不影响电机：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
```

## 单独调试

只启动 IMU 和电机：

```bash
ros2 launch imu_cybergear_ros2 imu_cybergear_system.launch.py
```

只启动双风扇：

```bash
ros2 launch windarmor_fan_controller fans.launch.py
```

统一启动时也可关闭部分组件：

```bash
ros2 launch windarmor_bringup windarmor.launch.py start_fans:=false
ros2 launch windarmor_bringup windarmor.launch.py start_controller:=false
```
