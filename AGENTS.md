# WindArmor 仓库协作规则

本文件适用于整个 WindArmor 仓库。若以后在子目录中增加更具体的
`AGENTS.md`，子目录规则可以补充开发细节，但不得覆盖、放宽或绕过本文件
中的硬件安全规则、带电授权门槛和 Git 操作限制。

## 1. 项目范围与权威来源

WindArmor 是运行于树莓派 5（Ubuntu 24.04、ROS 2 Jazzy）的飞行机器人
工作空间，整合 Hiwonder IMU、4 个 CyberGear 微电机和 2 个涵道风扇。
`v0.3.1` 是当前稳定发布基线；实际工作基线以当前分支、`HEAD` 和任务开始时
已有的工作区修改为准。

- `docs/FIRST_COMMAND.md`：项目目标、硬件背景和前置项目约束。
- `README.md`：当前安装、配置、接口和操作说明。
- `src/` 中各 ROS 2 包的源代码、`config/`、`launch/` 和测试：行为的
  最终依据。

不要在本文件复制大段操作文档。若文档和代码不一致，停止涉及硬件的工作，
先报告差异；不得猜测命令、节点、话题、服务或硬件参数。

## 2. 不可违反的硬件安全规则

当前树莓派处于开发状态；4 个 CyberGear 微电机和 2 个涵道风扇均无动力
供电，当前阶段不允许电机或风扇带电测试。除非用户明确更新该状态，否则：

- 未经用户明确授权，不得使电机运动或使风扇旋转。
- 不得仅因动力电源断开就启动任何硬件输出节点或 launch。
- 不得启动可能发送 CyberGear CAN 控制指令的节点或 launch。
- 不得启动可能输出风扇 PWM 的节点或 launch，不得操作 GPIO12 或 GPIO13，
  也不得改变这两个 GPIO 的用途。
- 不得解锁、使能或校准电调，不得使用 `sudo` 启动硬件控制程序。
- 未经授权，不得改变树莓派运行时硬件状态、系统硬件配置或已确认的
  CAN、GPIO、PWM 物理映射。在已确认的任务范围内可以修改仓库中的控制
  算法、YAML、测试和文档，但这不授权运行真实硬件节点。
- 仅在带电测试确有必要时，才可按下方十项授权门槛申请用户给相关设备
  通电；用户明确同意前不得执行，也不得假设设备已经通电。
- 未经明确授权，不得改变
  `src/imu_cybergear_ros2/config/imu_cybergear_params.yaml` 中的
  `motor_ids`、`motor_signs`、`motor_limits_min` 或 `motor_limits_max`。
  当前值分别为 `[4, 3, 2, 1]`、`[-1.0, 1.0, -1.0, 1.0]`、
  `[-1.57, -1.57, -1.57, 0.0]` 和 `[0.0, 1.57, 1.57, 1.57]`。
- `/e_stop` 及现有看门狗、软限位、停用和安全退出机制不得删除、绕过或
  弱化。
- 不得把构建、静态检查、纯软件测试、mock 测试或断电检查表述为实机
  验证。未执行的测试必须写明“未执行”或“等待实机验证”。

允许阅读与搜索代码、执行只读 Git 检查和静态检查；在不访问真实硬件 I/O
的前提下，也允许在已确认的任务范围内创建和修改代码、配置、测试及文档，
并运行纯函数或使用 mock、fake、依赖注入隔离硬件 I/O 的测试。修改源代码
不等于获得硬件执行授权。只有确认命令不会访问 CAN、GPIO 或串口后，才可
执行构建或测试；不能确认时必须先停止并询问用户。

### 带电测试授权门槛

任何需要给微电机或风扇通电的测试，都必须先停止并向用户报告以下内容：

1. 需要通电的设备；
2. 此时需要带电测试的原因；
3. 准备执行的准确命令；
4. 预计运动的电机或旋转的风扇；
5. 预计运动方向；
6. 初始角度、速度、力矩、PWM 或油门限制；
7. 预计持续时间；
8. 急停方法；
9. 异常停止条件；
10. 测试后恢复安全状态的方法。

用户明确同意前不得执行，也不得假设设备已经通电。

## 3. 开发工作流

1. 每项任务开始先运行 `git status --short --branch`，识别并保留用户已有
   修改。
   未经用户允许，不得 `checkout`、`reset`、`clean` 或以其他方式丢弃这些
   修改。
2. 先阅读相关代码、配置、测试和文档，再提出实施计划。大型或跨组件修改
   必须先等待用户确认。
3. 修改保持最小范围，不改无关文件，不覆盖用户改动。
4. 不自动创建 commit、push 或 tag。执行其中任何操作前，先汇报修改和
   验证结果并等待用户明确确认。
5. 控制代码改变后，同步更新相关测试和 `README.md`。

## 4. 构建与分级测试

### 默认：纯软件构建与测试

下列现有测试已确认不实例化硬件节点，不访问 CAN、GPIO 或真实串口：

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
colcon test --packages-select \
  imu_cybergear_ros2 windarmor_fan_controller windarmor_bringup
colcon test-result --verbose
```

这项确认只适用于当前测试集合。新增或修改测试后，运行前必须重新检查相关
测试及其 fixture、插件和依赖是否会访问硬件；不得只因上述 `colcon` 命令
已列在本文件中就认定其安全。

当前覆盖包括 IMU 协议/姿态换算纯函数、风扇 PWM 映射纯函数、统一 launch
文件的 Python AST 语法检查，以及通过伪终端和 `monkeypatch` 隔离键盘输入
的测试。需要只运行这些测试时，可在完成构建后执行：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 -m pytest \
  src/imu_cybergear_ros2/test/test_imu_protocol.py \
  src/windarmor_fan_controller/test/test_pwm.py \
  src/windarmor_fan_controller/test/test_fan_keyboard.py \
  src/windarmor_bringup/test/test_launch_syntax.py -v
```

仓库已有完全内存化的 fake motor driver，以及不连接硬件的进程内 lifecycle
测试，覆盖电机命令故障、初始化回滚、资源释放和部分确定性并发边界；这些测试
不创建真实 CyberGear 驱动，也不连接 CAN 或串口。仓库仍没有真实 CAN、真实
串口或 GPIO 的自动验证，风扇底层 GPIO 控制器也不得在默认测试中实例化。不得
把 fake/mock 覆盖表述为真实硬件验证，硬件测试不得加入默认测试命令。

### GitHub Actions 安全边界

GitHub Actions 只能使用 GitHub 托管 runner 执行纯软件构建，以及 pure
logic、fake/mock、未连接 backend 和无硬件进程内 lifecycle 测试。仓库统一
入口为 `scripts/ci_software.sh`，并由 `scripts/check_ci_safety.py` 约束 workflow
和该入口。CI 禁止使用机器人或其他 self-hosted runner，禁止映射或访问真实
`/dev`、配置 SocketCAN 或 `can10`、初始化 CyberGear、GPIO 或电调、输出 PWM、
运行硬件节点/launch，或使用 secret 执行任何硬件操作。现有 fake motor driver、
fake feedback 和 fake clock 不构成真实硬件验证。

### 非默认：真实硬件验证

- **真实 IMU：** `ros2 launch imu_cybergear_ros2
  imu_cybergear_system.launch.py start_controller:=false` 会激活
  `/dev/imu_usb` 串口读取；仅在用户明确允许访问 IMU 后运行。
- **CAN 总线：** `sudo ./scripts/setup_can.sh can10` 会修改系统 CAN 配置；
  电机控制节点会连接 CAN 并初始化电机。当前没有独立的 CAN-only 自动测试，
  未经明确授权不得运行相关命令。
- **微电机动力：** 任何电机控制节点、launch、控制话题或服务验证都可能
  发送控制指令；必须满足上面的带电授权门槛，结果标为实机验证。
- **风扇动力：** `fan_controller` 构造时即占用 GPIO12/13、输出最低 PWM
  并执行电调解锁等待。任何风扇节点、launch、PWM 话题或使能服务验证均须
  明确授权；通电旋转还必须满足上面的带电授权门槛。

`windarmor.launch.py` 默认启动电机控制器和风扇控制器，绝不能作为默认测试。
`start_controller:=false` 仍会访问真实 IMU；`start_fans:=false` 仍会启动
IMU/电机部分，因此二者都不是完整的软件模拟模式。

## 5. ROS 2 与控制代码约束

- 保持现有话题、服务、参数和 launch 接口兼容；需要破坏性变更时先获得用户
  确认并提供迁移说明。
- 可配置参数放入对应包的 YAML；不得把硬件参数散落为新的代码常量。
- 控制计算尽量提取为可测试的纯函数；硬件 I/O 与控制策略分离，并优先使用
  可注入的接口以支持 mock/fake 测试。
- 新控制节点必须具备合理的命令超时、禁用、退出清理和 `/e_stop` 行为；
  异常或关闭时应回到已有安全状态。
- 不得创建两个会同时争用同一硬件控制话题或硬件资源的发布者/控制节点。
- 安全相关改动必须增加相应软件测试；不能仅凭代码审查宣称硬件安全。

## 6. 完成与汇报标准

每次任务结束至少汇报：

- 修改的文件；
- 主要设计；
- 已运行的命令及测试结果；
- 未运行的测试及原因；
- 是否访问或影响硬件；
- 剩余风险和实机验证需求；
- 最终 `git diff` 和 `git status` 状态。
