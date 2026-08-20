# WindArmor

WindArmor 当前把两个已经过实机测试的前置项目整合为一个 ROS 2 Jazzy
工作空间，可同时运行：

- Hiwonder IMU；
- 4 个小米 CyberGear 电机；
- 2 个涵道风扇。

当前发布状态：

- 稳定发布：`v0.3.2`；
- 当前代码基线已通过 `v0.3.2` 发布前纯软件验证、GitHub Hosted CI 与用户
  最终整机正常功能回归。

当前开发目标为 `v0.4.0 Flight Control Integration Foundation`。开发中的
Flight API 保持纯 Python 算法边界；Structured State、DRY_RUN Runtime、权威安全
readback、authority/owner handoff、actuator adapter 和 fail-closed lease 已完成软件
集成。详细的数据流、安全裁决、ownership 和 rollback 契约以
[Flight Control Architecture](docs/FLIGHT_CONTROL_ARCHITECTURE.md) 为准，算法接口以
[Flight Control API](docs/FLIGHT_CONTROL_API.md) 为准。

接管开关 `flight_takeover_enabled=false` 默认保持关闭：默认 Runtime 不创建
ownership client 或可执行 command publisher，不改变 v0.3.2 的电机、风扇、IMU
或安全运行语义。Flight combined takeover 已完成 B1 bounded functional hardware
verification：atomic ACTIVE、`command_authority=FLIGHT_CONTROL`、`left_pitch +0.05 rad`、
其他三轴 baseline hold、motor/fan E-STOP、owner release 和 E-STOP 后
`actuation_allowed=false` 均有实机证据；fan/ESC 在该场景保持断电。随后 B2 也已取得
operator-provided hardware PASS：LEFT command `0.05` 的 continuous PWM 从 `(800,800)`
有界达到 1210/800 us 并最终回到 `(800,800)`，四 motor baseline hold、无意外运动，
E-STOP 后 authority/owners/latches 和 LEFT physical stop 均通过。RIGHT command 保持
`0.0 / 800 us`，但 RIGHT ESC 在该次最终 B2 session 中独立断电，不把它表述为 powered
physical Flight verification。Gate B 现为 COMPLETE；Gate C fail-closed 和 Gate D 最终
回归仍未完成。
分阶段验证协议见
[v0.4.0 Hardware Verification Plan](docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md)。
Gate A0/A1、normal controller 的 Gate B feedback baseline、Flight DRY_RUN、冷启动
当前位置保持 B0 和 B1 functional hardware verification 已通过。B1 closure run 没有满足
procedural `ACTIVE <= 3.0 sec`：watchdog 在 ACTIVE 后等待 2.5 秒才临时启动新的
`ros2 topic pub --once`，额外 ROS process/DDS discovery 延迟使实际 `/e_stop` 送达超时；
lower-level 收到 E-STOP 后的停止和状态转换本身很快。该 timing 证据将在 Gate C 使用
预创建 publisher 的 watchdog 顺便闭合，不为此重跑 B1 functional test。Task 6.2.7 的
shutdown cleanup 和 watchdog 已通过纯软件验证，Gate C 仅处于等待新授权的
`NEXT / READY FOR HARDWARE VERIFICATION / NOT AUTHORIZED`，本次未执行 Gate C。
这些状态不构成任何后续硬件操作授权。

仓库另提供默认禁用的 `bounded_verification_controller`，仅用于该计划中的受控
实机验证。它先从当前 authority session 的新鲜、合法、健康电机反馈捕获相对
baseline，再对一个显式逻辑电机应用用户批准的 offset；其他电机保持 baseline，
风扇默认请求停止。仓库配置没有可执行的默认 motor offset，不能直接据此进行
带电测试。

### Gate A 只读观测入口

仓库提供未来 Gate A2 专用的
`windarmor_observation_only.launch.py`：它只组合 IMU driver、独立 IMU 相对姿态
observer、CyberGear passive-RX observer 和 takeover 固定为 `false` 的 Flight Runtime。
该入口不创建普通电机控制器、MotorManager、fan controller、GPIO/PWM/ESC、owner
service 或 executable Flight command publisher。风扇与 motor safety/ownership 在
Runtime 中保持 unknown/fail-closed，不伪造 stop PWM 或健康状态。

```bash
ros2 launch windarmor_bringup windarmor_observation_only.launch.py
```

这不是默认软件测试命令：它会访问真实 IMU 串口并打开 CAN receive transport，任何
再次运行都必须按硬件验证计划单独获得授权。既有实机观测已经确认：transport 可连接，
但四台 CyberGear 在零 host command TX 下没有持续主动发送 0x02 feedback。该 passive
能力不再是 release requirement；普通 `windarmor.launch.py` 和既有控制行为不变。

### 飞控算法开发

1. 先读 [Flight Control API](docs/FLIGHT_CONTROL_API.md)；
2. 需要理解系统边界时再读
   [Flight Control Architecture](docs/FLIGHT_CONTROL_ARCHITECTURE.md)；
3. 机械、坐标和接线映射见
   [Hardware Reference](docs/HARDWARE_REFERENCE.md)。

算法主要位于
`src/windarmor_flight_control/windarmor_flight_control/algorithms/`。最小无硬件
unit-test 入口为：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_controller.py -q
```

该命令只构造内存 fake state，不创建 ROS node 或访问 CAN、串口、GPIO/PWM。

`v0.3.1` 在 `v0.3.0` 的统一相对姿态、电机模式状态和风扇手动/自动仲裁基础上，
包含统一 MANUAL/AUTO/HOME 电机推进速度、AUTO 姿态增益和三种风扇响应曲线。
`v0.3.2` 完成了风扇安全与确定性、电机命令/lifecycle 可靠性、电机配置和状态
转换契约、电机反馈健康、故障位与温度保护、CyberGear 0x02 状态帧大端序修正，
以及运行期通信断线检测与受控 transport-only 重连。完整变化与验证边界见
[`v0.3.2` Release Notes](docs/RELEASE_NOTES_v0.3.2.md)。

用户报告最终 RC 整机正常功能回归通过，未报告新的异常或明显功能回归。覆盖的
正常功能范围包括系统启动、IMU 零点、机械零点、MANUAL、HOME、小幅 AUTO、
风扇 MANUAL/AUTO、普通急停、正常急停恢复与正常退出；未提供逐项测量值，因此
本文不虚构具体数据。该结果是正常功能回归，不是消息乱序、SDO 写入失败、
初始化中断、停止失败、资源销毁失败、真实断线或其他危险故障注入认证。三模式
`4.0 rad/s` 及 `1200 μs`、`1400 μs` 等值的精确性能边界仍应按实际设备继续
验证或标定。

## 硬件默认配置

长期机械、坐标与接线契约见
[Hardware Reference](docs/HARDWARE_REFERENCE.md)；本节只保留运行配置摘要。

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

### 电机统一运动速度

MANUAL 键盘、AUTO IMU 跟随和 `h` HOME 回零现在只更新各电机的
`desired_targets`。激活后的唯一固定周期推进器根据真实单调时间差，把最近
已发送的 `current_targets` 逐步逼近期望目标：

```text
allowed_step = min(
    max_position_step,
    min(mode_speed, motor_speed_limit) × min(real_dt, motion_dt_max_sec)
)
```

默认参数为：

```yaml
command_interval_sec: 0.02
max_position_step: 0.4
manual_motion_speed_rad_s: 4.0
auto_motion_speed_rad_s: 4.0
home_motion_speed_rad_s: 4.0
motion_dt_max_sec: 0.05
target_reached_tolerance_rad: 0.001
manual_step_deg: 3.0
manual_repeat_gap_sec: 0.8
manual_repeat_dt_max_sec: 0.08
default_speed: 10.0
auto_roll_gain: 1.0
auto_pitch_gain: 1.0
```

三个 `*_motion_speed_rad_s` 是软件目标位置变化率，不保证等于负载下实测机械
角速度。`default_speed` 是启动时写给 CyberGear 的位置模式速度上限初值；
它不再直接决定三种模式的软件推进速度。`+/-` 调整选中电机的该速度上限：
当上限低于当前模式速度时会限制运动，高于模式速度后继续增加也不会突破模式
速度参数。

MANUAL 轻按一次仍使用 `manual_step_deg` 作精细目标增量；同一电机、同一方向
的连续重复字符按实际事件间隔换算有限增量，使稳定长按阶段尽量接近
`manual_motion_speed_rad_s`。终端没有可靠 key-up 事件，因此每个字符只产生
有限目标变化，松开后不会继续无限增加目标。

AUTO 的 IMU 回调只更新最新期望目标，推进速度不再由 IMU 消息频率直接决定；
缓慢倾斜时目标本身仍会缓慢变化，快速倾斜时由
`auto_motion_speed_rad_s` 限速追赶。`h` 不再使用独立快速定时器；在 AUTO
中按 `h` 会先退出 AUTO、进入 MANUAL，再由统一推进器按
`home_motion_speed_rad_s` 回零。

`auto_roll_gain` 和 `auto_pitch_gain` 控制电机 AUTO 目标角度的幅度，默认
`1.0` 保持原比例。增益在既有姿态死区之后应用，结果仍经过正负 90° AUTO
范围、既有电机方向映射、软限位和统一推进器；`auto_motion_speed_rad_s`
控制电机追赶目标的最大软件速度，两者不是同一概念。增益只用于电机 AUTO
目标，不改变 `/imu/relative_roll_pitch` 的真实相对姿态语义，因此不改变风扇
姿态输入，也不影响 MANUAL 或 HOME。

### 电机命令提交与故障语义

控制器区分三种位置：

- `desired_targets`：MANUAL、AUTO 或 HOME 希望最终到达的期望位置；
- `current_targets`：最近一次已经成功写入驱动的位置目标，不是待发送计算值，
  也不是真实反馈位置；
- `motor_feedback.position_rad`：最近一次电机真实反馈位置。

固定推进器先在节点状态锁内生成单台待发送命令，释放状态锁后通过独立驱动 I/O
锁完成一次写入，再回到状态锁内提交成功结果。位置写入失败时，该电机的
`current_targets` 和目标时间戳保持旧值；同一周期前面已经成功的电机保留成功
提交，失败电机之后的普通位置命令不再发送。速度上限也只有在
`SDO_TARGET_SPEED` 成功写入后才更新软件记录，失败时继续保留旧上限。

运行时普通位置或速度写入失败会丢弃未完成的 MANUAL/AUTO/HOME 运动、逐台
尽力停止全部电机并发布 `/motors/control_mode = ERROR`。停止其中一台失败不会
阻止后续电机停止。`ERROR` 不允许通过 `/enable_motor=true` 或键盘 `r` 自动
恢复；排除通信或驱动故障后必须受控地重新配置 lifecycle 或重启节点。

USB-CAN 串口关闭、串口读写异常、SocketCAN bus 缺失以及 `recv()`/`send()`
抛出的传输异常属于独立的 transport fault，不会伪装成电机反馈，也不等同于
电机固件 fault bit、临界温度或长时间没有 `MotorStatus`。明确 transport fault
会立即锁存、丢弃未完成运动、同步 `desired_targets` 到最近成功发送目标、尽力
停止全部电机并保持 `/motors/control_mode = ERROR`。SocketCAN
`recv(timeout)` 正常返回 `None` 仍只表示当前没有帧，不算断线。

`reconnect_on_disconnect: true` 时，独立后台协调器会以可取消、有界指数退避
尝试重开 transport 和 reader；为 `false` 时只关闭失效 transport，不启动运行期
重连。重连不会调用 `connect_and_init_motors()`，不会写 run mode、速度、位置或
enable/set-zero 指令。即使通信恢复，状态仍是 `ERROR`，`init_complete` 仍为
false，也不会恢复旧 MANUAL、AUTO、HOME 或机械零点流程。排除原因后必须执行
lifecycle cleanup/configure 或重启节点，才能重新初始化并恢复控制。

`motor_feedback_timeout_sec` 默认仍为 `0.0`；即使用户显式开启并发生反馈超时，
在没有 backend transport error 证据时也只走既有 motor safety ERROR，不会推断
需要重连。本轮断线与恢复验证全部使用 fake driver/backend、可控事件和内存故障
注入，没有进行真实拔线、CAN/串口故障注入或带电测试。软件完成后，用户自行
完成 MANUAL/AUTO 实机正常功能回归并报告无问题；该结果只验证正常控制路径，
不等同于 transport 断线检测、受控重连或恢复后锁定语义的实机故障注入。

电机反馈现在先按配置 ID、有限值、0x02 协议量程、模式、支持的故障 bit 和
timestamp 合法性检查；无效帧不会覆盖最近合法反馈，默认连续 3 帧无效会锁存
系统级故障。任意一台电机报告非零故障位（欠压、过流、过温、磁/HALL 编码器
故障或未标定），或一条合法反馈温度达到 `90.0 °C` 临界值，都会丢弃未完成
运动、同步期望目标到最近成功发送目标、best-effort 停止全部电机并进入
`ERROR`。`80.0～<90.0 °C` 只限频告警，不自动降速。故障和保护标志在本次
lifecycle 会话中锁存；正常反馈、温度回落、键盘 `r`、`/enable_motor=true`、
MANUAL/AUTO/HOME 均不能恢复，必须排除原因后重新配置或重启。

0x02 数据区的四个 `uint16` 按大端序解析。用户实机日志中曾出现
`2636.9/2483.3/2304.1 °C`，其原始值分别为 `0x6701/0x6101/0x5A01`；按正确
字节序还原为 `0x0167/0x0161/0x015A`，即 `35.9/35.3/34.6 °C`。position、
speed、torque 与 temperature 共用这一端序修正；SDO 发送字段不在本次改动范围。

反馈新鲜度使用回调本地记录的单调接收时间，不信任反馈对象的 timestamp。合法反馈
在 configure/初始化阶段也会进入 measured feedback cache；fault bit、临界温度和连续
无效反馈仍按原安全路径 fail-closed，不能因 lifecycle 尚未 active 而被描述为 healthy。

实机已经确认电机 idle/hold 时不会持续主动广播 0x02。正常控制节点 active 后以
`motor_feedback_acquisition_rate_hz: 10.0` 周期重发每台电机当前会话中最近成功提交、
当前 owner 仍授权的同值 `loc_ref`；CyberGear 通信类型 18 的应答是完整通信类型 2，
因此 position、velocity、torque、temperature、mode 和 fault flags 仍来自真实反馈。
该采集不提交或修改 `current_targets`/`desired_targets`，不切换 run mode，不 enable、
recover 或 set-zero。Flight 新 generation 在首条合法 normal command 前、owner revoke、
E-STOP、ERROR、transport fault、deactivate、cleanup 和 shutdown 后均不发送 probe；写入
失败复用既有位置命令 fail-closed ERROR 路径。

`motor_feedback_timeout_sec: 0.0` 保持不变，只表示 legacy safety 不因固定时长无反馈
进入 ERROR；它与 `/motors/feedback`/Flight 的 observer freshness 仍是两个不同概念。
用户显式配置正值后，既有启动宽限和逐电机超时保护才会启用。

0x02 状态帧提供位置、速度、力矩和温度，没有经过协议验证的安培电流字段。
`motor_current_limit_a: 5.0` 仍是保留参数，不参与数值比较；实际过流保护来自
电机固件的过流 fault bit。软件没有、也不允许从 `torque_nm` 或原始力矩推导
电流。

CyberGear 的机械零位会在电机动力掉电后丢失。normal controller 冷启动时，每台
电机先通过 `run_mode`/`limit_spd` 的通信类型 18 应答取得并验证本次 type-2 实测位置，
再把首次 `loc_ref` 写成同一 CyberGear 原生坐标值，仅保持上电时的当前物理姿态；
`motor_signs` 不会在这条 driver-to-driver 保持路径上重复应用。若没有本次新鲜合法
反馈，或反馈 ID、位置、设备状态、故障位、温度不可信，configure 失败并回滚，绝不
fallback 到 `0.0`，也不会自动 set-zero。成功后 `current_targets`、`desired_targets`
和 idle feedback probe 都从同一保持值开始。

只有速度、保持目标和进入运控模式各自成功后才提交相应软件状态；后续电机最终
失败时，会按已触及电机的反向顺序尽力停止、关闭驱动、销毁已创建 ROS 资源并返回
配置失败。连接失败同样会关闭驱动并释放资源。配置失败、`on_cleanup()` 与
`on_shutdown()` 共用幂等释放流程；单项释放失败会记录阶段、资源或电机 ID，并继续
执行剩余清理。

### 电机配置与状态转换契约

电机控制节点现在先把全部关键参数构造为不可变的通道、通信、运动、安全、ROS
接口和键盘配置，并完成纯函数校验；只有全部成功后才创建驱动、注册反馈回调、
创建 ROS publisher/subscription/service/timer、连接总线或发送电机命令。空列表、
列表长度不一致、重复或越界 ID、重复名称、非 `+/-1` 方向、非法软限位、未知
控制轴、重复/冲突键位、未知后端、空接口参数和非有限安全参数都会在零硬件接触
和零 ROS 运行资源创建的情况下拒绝配置。受保护的默认电机 ID、方向、软限位和
控制算法均未改变。

旧版电机 ID、方向和 `m1_*～m4_*` 软限位标量参数仍保持声明默认值以兼容旧参数
文件，但用户把其中任何一项改为非默认值时会明确配置失败，并提示迁移到对应
列表参数，不再静默忽略。`motor_port`/`motor_baud` 继续作为 USB-CAN fallback：
有效的新参数优先；仅当 `usb_port` 为空或 `usb_baud=0` 时使用旧参数并输出一次
废弃警告。

内部状态现在使用显式合法转换表。每次请求携带稳定的 reason/source，并返回
`CHANGED`、`NO_CHANGE` 或 `REJECTED`；同状态请求不重复运行回调，非法请求保持
原状态。最近一次真实变化保存为只读的序号、旧/新状态、原因、来源和单调时间
快照。`ERROR` 只能进入 `SHUTTING_DOWN`，`SHUTTING_DOWN` 不能离开；
`EMERGENCY_STOP` 只有在显式电机恢复成功后才能进入 MANUAL，状态提交若失败会
重新尽力停止电机。公开 `/motors/control_mode` 值和 QoS 保持不变。

### 双风扇

代码使用 BCM GPIO 编号：

| 风扇 | BCM GPIO | 树莓派物理引脚 |
|---|---:|---:|
| 左风扇 PWM | GPIO12 | 32 |
| 右风扇 PWM | GPIO26 | 37 |
| GND | — | 34 或其他 GND |

GPIO12 是原单风扇项目已验证的连接。右风扇不再使用旧映射 GPIO13（物理 33
脚），因为 Waveshare 2-CH CAN HAT+ 的 CAN_1 INT_1 默认占用 BCM GPIO13；当前
Raspberry Pi 5 + 该 CAN HAT 组合不得同时把 GPIO13 用作右 ESC PWM。本项目选择将
右风扇改到 GPIO26（物理 37 脚），而不修改 HAT 上 INT_1 的 0Ω 电阻或设备树中断
配置。首次上电前仍须确认实际接线。官方参考：
[Waveshare 2-CH CAN HAT+](https://www.waveshare.net/wiki/2-CH_CAN_HAT%2B)。

## 安装与构建

```bash
cd ~/workspace/WindArmor
source /opt/ros/jazzy/setup.bash
sudo apt update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

## 纯软件 CI

仓库的 GitHub Actions 软件 CI 使用 GitHub 托管的 Ubuntu 24.04 runner 和
ROS 2 Jazzy。向 `master` push、向 `master` 提交 pull request，或手动执行
`workflow_dispatch` 都会触发。CI 只执行 Python 编译、五包构建、pure
logic/fake/mock 单元与故障注入测试、五包完整测试、提交 whitespace 检查和
CI 自身安全检查；它不使用机器人或自托管 runner，不访问串口、CAN、
CyberGear、GPIO 或 PWM，也不启动 ROS 硬件节点或 launch。

已经安装 ROS 2 Jazzy 和仓库声明依赖的本地环境可运行同一入口：

```bash
cd ~/workspace/WindArmor
./scripts/ci_software.sh
```

脚本把 `build`、`install`、`log` 和 ROS 日志放在隔离的临时目录，不依赖仓库中
已有的构建产物。历史纯软件基线曾包含 406 项完整测试；实际数量会随测试增加
而变化，不作为脚本中的固定通过条件。

每次树莓派开机后，初始化一次 `can10`：

```bash
cd ~/workspace/WindArmor
sudo ./scripts/setup_can.sh can10
```

## 启动整套系统

> 以下启动操作会访问真实 IMU、CAN 和 GPIO，且可能控制电机或风扇。只有在
> 获得明确硬件测试授权、完成安全检查并满足仓库带电测试门槛后才能执行。

启动前让机器人可靠固定，移除风扇周围的人员和松散物体，并先断开风扇动力电池。

统一 launch 参数 `imu_auto_activate:=true` 保持默认正常行为：IMU 自动 configure 后继续
自动 activate。受控维护或已授权硬件验证可设置 `imu_auto_activate:=false`，此时 IMU 仍
自动 configure，但停在 inactive，必须由 operator 显式执行 lifecycle activate。该参数不
构成任何真实硬件操作授权。

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
> v0.4.0 分阶段验证计划仍为未执行状态；任何带电操作都必须先满足根目录
> [AGENTS.md](AGENTS.md) 的十项授权门槛，并取得对应 Stage 的单独明确授权，
> 不得从本节或验证计划推断授权。

仅执行 `windarmor.launch.py` 不会立即进入最终联动：电机初始化后默认处于
MANUAL，风扇 AUTO 也默认关闭。启动后按以下顺序操作。

1. 保持 IMU 和机器人静止。控制器配置阶段会先保持四台电机的本次实测当前位置，
   不会把当前位置自动定义为零。若 CyberGear motor bus 自上次显式 set-zero 后发生过
   动力掉电，先确认机器人处于正确物理 reference posture，再显式调用
   `/motors/set_zero`；完成该步骤前不要运行依赖准确机械坐标的 MANUAL/AUTO/HOME/
   Flight 动作。Raspberry Pi 单独掉电不等同于 CyberGear 零位必然丢失。
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

确认设备处于中位且异常原因已经排除后，按以下顺序恢复。管理器急停锁存不会
再被 enabled、motor mode 或姿态心跳自动清除，必须显式观察到
`/e_stop=false` 并调用 `/fans/reset_e_stop`：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: false}"
ros2 service call /enable_motor \
  std_srvs/srv/SetBool \
  "{data: true}"
ros2 service call /fans/enable \
  std_srvs/srv/SetBool \
  "{data: true}"
ros2 service call /fans/reset_e_stop std_srvs/srv/Trigger "{}"
```

`/fans/reset_e_stop` 只复位管理器授权状态，不会调用底层启用服务，也不会恢复
旧 AUTO、旧手动 PWM 或旧变化率目标；成功后仍保持 `[800, 800]`，MANUAL 和
AUTO 都未授权。`/enable_motor=true` 只恢复到 MANUAL。随后必须重新选择一种
控制路径：

1. AUTO：在 launch 终端按 `m` 进入电机 AUTO，确认新鲜状态和姿态后调用
   `/fans/auto_enable=true`；或
2. MANUAL：调用 `/fans/manual_enable=true`，先发送本次授权后的双路停止基线
   `[800, 800]`，之后才发送新的非停止命令。

系统不会在急停条件消失后、收到普通心跳后或 AUTO 故障退出后偷偷恢复旧 AUTO、
MANUAL 授权或旧 PWM。

### 正常结束

先让机器人回中，然后按空格或发布 `/e_stop=true`。确认电机为
`EMERGENCY_STOP`、风扇状态为 `[800, 800]` 后，按已经验证的安全顺序断开
风扇和电机动力，最后在 launch 终端按 `q` 或 `Ctrl+C` 退出。不得直接断开
终端而让动力设备在未知状态下继续供电。

### 手动风扇键盘（非 AUTO）

需要手动控制风扇时，可在另一个终端运行键盘节点，避免与电机键盘争用同一个
终端输入。开始调节前必须确认急停未锁存、底层风扇 enabled 和电机模式状态
均新鲜，然后显式授权管理器 MANUAL：

```bash
ros2 service call /fans/manual_enable std_srvs/srv/SetBool "{data: true}"
```

授权成功后进入 `MANUAL_WAITING_FOR_NEUTRAL`。键盘观察
`/fans/control_state`，清除本地旧油门并发送 `[800, 800]` 停止基线；管理器
收到这条本次授权后的双路停止命令后进入 `MANUAL_WAITING`，此后用户新的调节
输入才可生效。启用风扇 AUTO 后不要同时发送手动命令：

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
- `r`：只调用底层 `/fans/enable`，仍保持 800 μs；它不会复位管理器急停或
  自动授权 MANUAL；
- `q`：风扇回到 800 μs并退出键盘节点。

电机键位沿用前置项目，详见
`src/imu_cybergear_ros2/README.md`。

## ROS 2 控制接口

公共手动话题名称和消息类型保持兼容，但现在必须先通过
`/fans/manual_enable=true` 显式授权并建立新的双路停止基线。未授权、等待停止
基线、AUTO、急停、disabled 或安全停止状态会拒绝非停止命令。双路同时控制
（数组顺序为左、右）：

```bash
ros2 topic pub -r 10 /fans/pwm std_msgs/msg/Int32MultiArray \
  "{data: [800, 800]}"
```

也可分别发布 `/fans/left/pwm` 和 `/fans/right/pwm`。管理器分别记录左右
通道时间；默认 `0.5 s` 后仅停止超时的一侧，一侧消息不会为另一侧续期。
越界消息会被拒绝，不会静默限幅或刷新时间。

这些公共话题只进入 `fan_command_manager`。普通回调只校验并更新缓存，不发布
正常命令；唯一的 `control_rate_hz` 控制定时器每周期最多推进一次 AUTO 斜坡并
通过内部
`/fans/command_pwm` 向底层发送唯一正常命令；该内部话题不属于普通公共
控制接口。急停、disabled、未知模式、关键状态超时或姿态/零点失效仍会绕过
普通斜坡并立即发送停止值。底层保留最终限幅和默认 `1.0 s` 命令看门狗；
`command_timeout_sec` 必须是严格大于零的有限数值，非法值会在 GPIO 初始化前
使节点构造失败，不能用 `0` 关闭看门狗。当前实际输出可从
`/fans/status_pwm` 查看，底层接受状态可从 `/fans/enabled` 查看。

manager 启动后、底层 `/fans/enabled` 首次真实观测到达前，会持续保持 stop PWM、
`SAFE_STOP` 和 owner NONE；即使底层默认 3 秒解锁等待超过 enabled 的 1 秒运行期
freshness timeout，也不会把“首观测尚未到达”误锁为 `DISABLED`。首个 fresh
`enabled=true` 只建立无 owner 的 passive state，不会启动 MANUAL、AUTO 或 Flight。
首个 false、任意无效观测，以及已经完成首观测后的 false/stale 仍 fail-closed 为
sticky `DISABLED`，后到的 true 不会自动恢复；E-STOP 和 motor safety 保持更高优先级。
manager 一旦锁存 E-STOP，ownership revoke、Flight safe-stop、command/handoff lease
timeout、enabled 或 motor mode 更新、统一零点变化及其他普通 safe-stop cleanup 都只能
清 owner/token/旧命令并保持 stop PWM，control state 必须持续为 `EMERGENCY_STOP`。
只有满足既有恢复条件并显式调用 `/fans/reset_e_stop` 后才允许离开该状态；不会恢复旧
Flight generation、owner 或 command。

`fan_command_manager` 退出时也使用同一 safe-stop cleanup。ROS context 仍有效时会先发布
最终 STOP 和只读状态，再销毁 ROS 资源；若 SIGINT/launch 已先使 context 无效，则仍清除
内部 owner、token 和旧命令，但不会向 invalid context 发布。重复 destroy 是幂等的，正常
运行期间的其他 publish error 不会被无条件吞掉。

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

新增的公开状态包括 `MANUAL_DISARMED`（手动未授权）和
`MANUAL_WAITING_FOR_NEUTRAL`（已授权但仍等待本次授权后的双路停止基线）。
原有 `MANUAL_WAITING`、`MANUAL_ACTIVE`、`AUTO_WAITING`、`AUTO_ACTIVE`、
`SAFE_STOP`、`DISABLED` 和 `EMERGENCY_STOP` 继续保留；Flight ownership 路径另有
`FLIGHT_WAITING` 与 `FLIGHT_ACTIVE`，分别表示已 commit 后等待首条有效命令和正在
通过既有 manager 输出 Flight 目标。Flight safety readback consumer 将这 11 个明确状态
作为封闭词汇表；识别 Flight 状态不等于判定其永远安全，`FLIGHT_WAITING`/
`FLIGHT_ACTIVE` 仍必须是 enabled 已真实观测且为 true、非 E-STOP、非 passive，且没有
legacy MANUAL/AUTO owner。任意未知状态或 cross-field 冲突仍 fail-closed 拒绝。

AUTO 使用 `max()` 合成姿态活动量：正负 pitch 都同时提高左右目标；左倾只
增加左侧 roll 分量，右倾只增加右侧 roll 分量。任一姿态、电机模式或底层
状态超时都会立即停止、清除 AUTO 请求并取消 MANUAL 授权；条件恢复和后台
手动心跳都不会自动重新启用。未知、空白或不受支持的电机模式会使旧模式缓存
失效并进入安全停止，只能通过适用的显式授权路径恢复。

活动角到 AUTO 目标 PWM 的响应曲线由以下参数选择：

```yaml
fan_response_curve: "smoothstep"
```

支持 `linear`（线性）、`smoothstep`（`x²(3-2x)`，端点斜率为零）和
`quadratic`（`x²`，中间区间不高于线性）。默认 `smoothstep` 只改变“当前
活动角对应多少目标 PWM”；`control_rate_hz`、`rise_step_pwm_us` 和
`fall_step_pwm_us` 仍决定实际输出以多快速度接近目标。用户后续整机功能测试
未观察到明显异常，但这不等于三种曲线都完成了独立恢复能力标定，也不能据此
认定任一曲线已覆盖当前机器人的全部姿态和故障边界。

`fan_full_scale_deg: 45.0` 是活动角达到 `fan_auto_max_pwm_us` 的配置点，45°
只是当前默认候选值。它不是风扇启动角、机械极限、由质量/重心/推力/力臂模型
计算出的必然值，也不是已证明可恢复机器人的最大倾角；后续需要结合实测推力
和结构重新标定。调小会让较小倾角更早达到自动最大目标，调大会让目标在更大
倾角范围内逐渐增加。

`fan_auto_max_pwm_us` 仍为 `1400`；底层 `max_pwm_us` 仍为 `2200`，后者只是
软件允许范围上限，不表示 AUTO 已获准或已标定到 2200。默认曲线为
`smoothstep`。用户报告的后续整机功能验证不替代三种曲线的逐项性能标定，也
不覆盖超时、乱序和故障注入路径。

系统急停：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: true}"
```

### Hardware verification continuous evidence

仓库提供只读 evidence recorder，把 authority、Flight command、motor feedback、安全
状态、ownership 和 fan PWM 持续写入同一个带时间戳的 session。它只管理
`ros2 topic echo` subscriber，不 publish、不调用 service，也不控制 E-STOP、authority、
CAN、GPIO、PWM、motor 或 fan。未来已获授权的硬件 gate 可在独立 Terminal C 启动：

```bash
python3 scripts/hardware_verification/record_gate_evidence.py \
  --output-root ~/windarmor_evidence
```

看到 `READY` 后再执行独立的 gate trigger/watchdog。结束时按 `Ctrl+C`，工具会统一停止
children 并在 `manifest.json` 记录 topic/file mapping、开始/停止时间、样本状态和退出码。
可用 JSON config 或重复的 `--topic NAME=/topic:package/msg/Type` 替换默认 topic 集。

B2 software analyzer 离线读取该 session：

```bash
python3 scripts/hardware_verification/analyze_b2_evidence.py <SESSION_DIR>
```

它只判定 required software evidence，不能替代 operator 的物理观察，也不能单独宣布
hardware PASS。continuous `fan_pwm.log` 的最终 `(800,800)` 是 required evidence；optional
`post_fan_pwm.txt` 缺失或为空只报告 non-blocking supplemental warning，不再造成
false-negative。若 optional snapshot 含有与 stop 冲突的有效 PWM，analyzer 仍会
fail-closed。

`ros2 topic echo ... --once` 只等待订阅后的下一条消息，适合稳态抽查，不适合作为
ACTIVE、handoff、ownership 或 command transition 的唯一历史证据。瞬态验证应使用
continuous recorder，避免人工追高速 topic 或临时 awk/grep pipeline。

### Gate C 预热 E-STOP watchdog

仓库提供 `scripts/flight_estop_watchdog.py` 作为受控硬件验证辅助工具；它不加入正常 launch，
也不参与 production safety architecture。只有获得对应 Gate C 的单独硬件授权后才可用于
实机流程：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 scripts/flight_estop_watchdog.py
```

工具启动时即创建 `/e_stop` publisher 和 Flight authority subscription，确认至少一个
E-STOP subscriber 后才打印 `WATCHDOG READY`。它只在首次同时观察到 `ACTIVE`、
`FLIGHT_CONTROL` 和 `actuation_allowed=true` 后启动 monotonic 计时，默认 2.0 秒后由同一
预热 publisher 发布一次 `/e_stop=true`；10 秒内没有 ACTIVE 也会 fail-closed 发布一次并
报告 `NO ACTIVE WITHIN TIMEOUT`。`--delay-sec` 只允许 `0 < value < 3.0`。工具不会调用
prepare/reset、操作 ownership 或发送 motor/fan command；prepare 仍由单独获授权的操作员
执行。它的纯软件测试不会连接真实硬件。

MANUAL 模式下可按 `motor_ids` 的配置顺序（默认 `[4, 3, 2, 1]`）发送
电机绝对期望目标，单位为弧度。整条消息通过长度和有限值校验后才会更新，
节点应用软限位并由统一推进器按 MANUAL 速度逐步逼近，不会直接跳写完整目标：

```bash
ros2 topic pub --once /motors/manual_targets \
  std_msgs/msg/Float64MultiArray "{data: [0.0, 0.0, 0.0, 0.0]}"
```

IMU 与电机归零服务：

```bash
ros2 service call /imu/set_zero std_srvs/srv/Trigger "{}"
ros2 service call /motors/set_zero std_srvs/srv/Trigger "{}"
```

急停后分别恢复电机与底层风扇，再显式复位管理器（全过程保持最低油门和空命令
缓存）：

```bash
ros2 topic pub --once /e_stop std_msgs/msg/Bool "{data: false}"
ros2 service call /enable_motor std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/enable std_srvs/srv/SetBool "{data: true}"
ros2 service call /fans/reset_e_stop std_srvs/srv/Trigger "{}"
```

`/enable_motor=true` 成功后只恢复到 `MANUAL`，不会直接进入 AUTO。
`/fans/enable=true` 会保持停止并等待新命令，绝不恢复旧 PWM。在统一
`windarmor.launch.py` 模式中，底层启用和新鲜合法电机模式也不能自动清除管理器
急停；只有 `/fans/reset_e_stop` 可以显式复位。复位后还要选择
`/fans/manual_enable=true` 或 `/fans/auto_enable=true`，两者都不会代替底层
`/fans/enable`。

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

`fans.launch.py` 启动一个管理器和一个底层控制器。为保持 launch 参数兼容，
`require_motor_mode_for_manual` 仍存在且默认 `false`；安全加固后的显式
`/fans/manual_enable=true` 仍始终要求新鲜合法的 `MANUAL` 或 `AUTO` 电机模式，
因此不能再只靠独立风扇 launch 和后台 PWM 心跳进入手动输出。统一
`windarmor.launch.py` 继续覆盖该兼容参数为 `true`。

单独运行 `fan_controller` 只用于已授权的底层维护：它会占用 GPIO12/26、
初始化电调，只订阅内部 `/fans/command_pwm`，且运行前必须确认管理器未运行。
它不是正常公共控制方式；正式操作应使用 `fans.launch.py` 或
`windarmor.launch.py`。

电机可靠性以及配置/状态契约开发只执行了纯软件验证，没有运行硬件节点或
launch，也没有访问 IMU、CAN、GPIO 或串口。软件完成后，用户自行启动整个系统
并完成 MANUAL/AUTO 功能实机测试；此前也已报告统一 launch 下的电机和风扇基本
功能正常。上述用户测试不等于真实故障注入、极限测试或标定，也不构成后续
硬件操作授权。

本轮反馈健康、故障位和温度保护的开发验证只使用 pure logic、fake feedback、
fake clock 和 fake driver。用户随后自行启动整机，在设置机械零点和手动控制时
发现 0x02 温度端序问题；修正后用户再次完成统一 launch、机械零点和手动控制
实机复测，并报告未再出现无效反馈或其他问题。这验证了本次端序修正在上述正常
功能路径中的实际效果，但真实 fault bit、过温、反馈中断和异常恢复仍未实机注入。

统一启动时也可关闭部分组件：

```bash
ros2 launch windarmor_bringup windarmor.launch.py start_fans:=false
ros2 launch windarmor_bringup windarmor.launch.py start_controller:=false
```
