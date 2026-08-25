# WindArmor

WindArmor 是运行于树莓派 5、Ubuntu 24.04 和 ROS 2 Jazzy 的飞行机器人工作空间，
整合 Hiwonder IMU、4 个 CyberGear 微电机和 2 个涵道风扇。仓库提供硬件驱动、
安全状态管理、统一 bringup、Flight 控制接口以及不连接真实硬件的软件测试。

## 当前版本

- 当前正式稳定发布：**v0.3.2**
- 当前开发目标：**v0.4.0（尚未发布）**
- v0.4.0 Gate B、C、D 硬件与功能验证：**COMPLETE**
- v0.4.0 release readiness：**PENDING**

v0.4.0 的最终验证判定及限制见
[硬件与功能验证记录](docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)。
验证完成不等于版本已经发布，也不改变 v0.3.2 的 stable 身份。

## 安全边界

本仓库连接真实电机、风扇、CAN、GPIO 和串口。默认把硬件视为未获运行授权：

- 未经明确授权，不得启动会访问 CAN、GPIO、PWM 或真实串口的节点和 launch；
- 不得因动力电源断开就跳过授权或安全步骤；
- 风扇固定使用 GPIO12（LEFT）和 GPIO26（RIGHT），GPIO13 保留给 CAN HAT INT_1；
- 不得绕过 `/e_stop`、看门狗、软限位、失权和安全退出机制；
- 修改代码、构建或 mock/fake 测试不构成真实硬件验证；
- 任何新的带电场景都必须重新满足 `AGENTS.md` 的十项授权门槛。

出现异常时优先执行全局急停，并准备使用现场物理断电：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

完整接线、方向、限位和物理映射见
[硬件参考](docs/HARDWARE_REFERENCE.md)。

## 系统要求

- Raspberry Pi 5
- Ubuntu 24.04
- ROS 2 Jazzy
- Hiwonder IMU（串口）
- Waveshare 2-CH CAN HAT+ / SocketCAN `can10`
- 4 个 CyberGear 微电机
- 2 个涵道风扇及对应电调

建议先用 `rosdep` 安装工作空间依赖：

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
```

## 构建

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

构建本身不会授权硬件运行。开始任何测试前仍须确认测试不会实例化真实 CAN、串口
或 GPIO 后端。

## 正常启动

以下命令会访问真实硬件，只能在已确认接线、安全空间、急停和本次运行授权后执行。
统一 launch 默认启动电机与风扇控制器，不能用作软件模拟命令。

1. 配置 CAN：

   ```bash
   sudo ./scripts/setup_can.sh can10
   ```

2. 构建并加载工作空间：

   ```bash
   source /opt/ros/jazzy/setup.bash
   source install/setup.bash
   ```

3. 启动统一系统：

   ```bash
   ros2 launch windarmor_bringup windarmor.launch.py
   ```

4. 启动后先确认电机保持当前测得位置、风扇为停止值、状态和反馈均新鲜。冷启动不会
   隐式建立机械零点。

5. 若电机曾断电或机械参考发生变化，人工回到已知 physical reference posture 后，
   显式建立机械零点：

   ```bash
   ros2 service call /motors/set_zero std_srvs/srv/Trigger "{}"
   ```

6. 在需要相对姿态控制前设置 IMU 零点：

   ```bash
   ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
   ```

`start_fans:=false` 仍会访问 IMU/电机；`start_controller:=false` 仍会访问真实 IMU。
两者都不是完整的软件模拟模式。

## 基本操作

### 电机 MANUAL 与 HOME

统一 launch 的前台终端接收电机键盘输入。默认键位如下：

| 按键 | 功能 |
| --- | --- |
| `w` / `s` | 左俯仰电机正向 / 反向 |
| `a` / `d` | 左升降电机反向 / 正向 |
| `i` / `k` | 右俯仰电机反向 / 正向 |
| `j` / `l` | 右升降电机反向 / 正向 |
| `1`…`4` | 按 CAN ID 选择电机 |
| `+`（或 `=`）/ `-`（或 `_`） | 提高 / 降低所选电机速度上限 |
| `[` / `]` | 所选电机快捷目标 `+90°` / `-90°`，仍受软限位约束 |
| `h` | HOME；若当前为 AUTO，会先切回 MANUAL |
| `m` | 切换 MANUAL / LEGACY AUTO |
| `z` | 设置 IMU 零点 |
| `x` | 将全部电机当前位置设为机械零点 |
| `p` | 打印状态摘要 |
| `空格` | 发布全局急停，电机和风扇同时停止 |
| `r` | 从普通急停恢复电机授权；不能恢复 `ERROR` |
| `q` | 安全停止并退出统一 launch |

MANUAL、HOME 和 AUTO 共用固定周期的目标推进器；方向、速度和软限位来自包配置。
任何依赖准确机械坐标的动作都应在本次上电后显式确认机械零点。

### 风扇 MANUAL

先确认两路都处于停止值，再启用底层风扇并授权新的 MANUAL 会话：

```bash
ros2 service call /fans/stop std_srvs/srv/Trigger "{}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/manual_enable std_srvs/srv/SetBool "{data: true}"
```

授权成功后先发送新的双路停止基线，再在独立终端启动键盘，避免与电机键盘争用：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run windarmor_fan_controller fan_keyboard
```

| 按键 | 功能 |
| --- | --- |
| `1` / `2` / `3` | 选择 LEFT / RIGHT / BOTH |
| `↑` / `↓` | 增加 / 降低所选风扇命令 |
| `s` | 两路回到停止值 |
| `空格` | 发布全局急停 |
| `r` | 只调用底层 `/fans/enable`；不复位管理器急停或恢复旧命令 |
| `q` | 两路停止并退出键盘节点 |

MANUAL 未授权、等待停止基线、AUTO、急停、disabled 或安全停止状态都会拒绝非停止
命令。不要在 AUTO 已授权时同时发送手动风扇命令。

### LEGACY AUTO

LEGACY AUTO 保留 v0.3.2 的正常操作接口；Flight takeover 默认仍为 false。

1. 在电机键盘按 `m`，确认 `/motors/control_mode` 为新鲜的 `AUTO`；
2. 确认 IMU 已归零且相对姿态有效；
3. 显式启用风扇 AUTO：

   ```bash
   ros2 service call /fans/auto_enable std_srvs/srv/SetBool "{data: true}"
   ```

4. 监控模式、风扇状态和输出：

   ```bash
   ros2 topic echo /motors/control_mode
   ros2 topic echo /fans/control_state
   ros2 topic echo /fans/status_pwm
   ```

风扇先进入 `AUTO_WAITING` 并保持停止；只有服务成功之后的新鲜姿态满足条件时才进入
`AUTO_ACTIVE`。再次设置 IMU 零点会清除旧姿态和风扇 AUTO 请求，之后必须重新授权。

## E-stop 与恢复

键盘空格或下面的话题都会锁存全局急停，停止电机，禁用风扇，并清除旧 MANUAL、
AUTO、Flight 和姿态命令：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

只有在异常原因已排除、机构处于安全姿态且现场仍允许继续运行时，才按顺序恢复：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: false}"
ros2 service call /enable_motor std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/reset_e_stop std_srvs/srv/Trigger "{}"
```

恢复后电机只回到 MANUAL，风扇保持 `[800, 800]` 且没有 owner。随后必须重新选择
`/fans/manual_enable=true` 或 `/fans/auto_enable=true`，并建立新的停止基线/新鲜输入。
任何旧 PWM、旧 AUTO 或旧 Flight 命令都不会自动恢复。

`ERROR`、transport fault、过温锁存或硬件通信异常不属于普通急停恢复。排除原因后，
需要重新执行对应 lifecycle 配置/激活或重启流程；不得反复调用恢复接口绕过故障。

正常关机前应先全局急停，确认电机状态为 `EMERGENCY_STOP`、风扇 PWM 为停止值，
再按现场安全流程断开动力，最后按 `q` 或 `Ctrl+C` 退出软件。

## 算法开发

算法开发按以下顺序阅读：

1. [算法开发者指南](docs/ALGORITHM_DEVELOPER_GUIDE.md)：如何构建、运行 synthetic
   demo、接入算法和解释状态；
2. [Flight Control API](docs/FLIGHT_CONTROL_API.md)：消息、服务、参数和时序契约；
3. [Flight Control Architecture](docs/FLIGHT_CONTROL_ARCHITECTURE.md)：authority、
   lease、generation、fail-close 与状态机设计；
4. [硬件参考](docs/HARDWARE_REFERENCE.md)：轴、符号、限位、接线和机械边界。

算法开发默认使用 synthetic/fake 路径，不应通过启动真实硬件节点来验证纯控制逻辑。

## 测试

仓库完整纯软件 CI 入口为：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

它执行安全与 whitespace 检查、Python 编译、五包构建、pure/fake/mock 测试、完整
包测试和结果汇总。测试结果只能描述为软件验证，不是 CAN、串口、GPIO、电调或机械
实机验证。

新开发者可在完成构建后运行核心隔离测试：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_imu_protocol.py \
  src/windarmor_fan_controller/test/test_pwm.py \
  src/windarmor_fan_controller/test/test_fan_keyboard.py \
  src/windarmor_bringup/test/test_launch_syntax.py -v
```

Flight newcomer software-only controller integration demo：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run
```

该命令不连接 ROS graph、不访问硬件，也不创建 actuator authority。它与
`flight_control_dry_run.launch.py` 不同；后者启动 observer Runtime，需要外部 state
publisher 才能形成 meaningful live preview，不是同一个 newcomer software-only demo。

运行新增或修改后的测试前，必须重新检查 fixture、插件和依赖没有访问硬件 I/O。

## 文档导航

| 文档 | 角色 |
| --- | --- |
| [硬件参考](docs/HARDWARE_REFERENCE.md) | 当前硬件、机械、坐标和接线契约 |
| [算法开发者指南](docs/ALGORITHM_DEVELOPER_GUIDE.md) | 算法开发主入口 |
| [Flight Control API](docs/FLIGHT_CONTROL_API.md) | 稳定算法接口契约 |
| [Flight Control Architecture](docs/FLIGHT_CONTROL_ARCHITECTURE.md) | Flight 长期架构依据 |
| [IMU/CyberGear 包 README](src/imu_cybergear_ros2/README.md) | 电机/IMU 包专属接口与实现约束 |
| [v0.4.0 验证记录](docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md) | 当前版本最终硬件与功能验证证据 |
| [v0.4.0 历史执行计划](docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md) | 完整过程、无效尝试和 runbook 历史；不是当前授权 |
| [v0.3.2 发布说明](docs/RELEASE_NOTES_v0.3.2.md) | 当前 stable release 的版本化发布记录 |
| [v0.3.2 RC 检查表](docs/V0.3.2_RC_HARDWARE_CHECKLIST.md) | v0.3.2 历史验证记录 |

`docs/LATEST_FEEDBACK.md` 是仓库内的可变任务交接，不是 release evidence 或长期接口
来源；`docs/NEXT_COMMAND.md` 是可选的本地任务 scratchpad，且不纳入 Git。

## 发布与验证历史

- **v0.4.0（未发布）：** Gate B/C/D 已完成；最终证据、无效尝试、已知限制和
  非阻塞观察固化在
  [v0.4.0 验证记录](docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)。
- **v0.3.2（stable）：** 发布内容见
  [发布说明](docs/RELEASE_NOTES_v0.3.2.md)，历史硬件结果见
  [RC 检查表](docs/V0.3.2_RC_HARDWARE_CHECKLIST.md)。

历史验证证据不会授权未来硬件操作；任何新的实机场景仍须重新确认设备、命令、
运动边界、持续时间、急停和恢复方法。
