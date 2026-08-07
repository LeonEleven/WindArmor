# 最新反馈：v0.3.2 Release Candidate 冻结与发布审计

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-07

## 1. 执行结论

- 已完成 `v0.3.1 -> cc9e75e` 的发布前审计、版本元数据统一、文档冻结、
  公共接口/默认参数契约测试与完整纯软件回归。
- 未发现未解决的 `v0.3.2` 发布阻塞项。
- 三个 ROS 2 package 的 `package.xml` 与 `setup.py` 已全部统一为 `0.3.2`，
  name、description、maintainer、email 和 license 在同一 package 内一致。
- 公共 ROS 接口未发现非预期删除、重命名、类型或 QoS 变化；默认控制
  参数未发现非预期变化。
- 本 RC 不修改任何运行时控制算法、状态机、急停或 transport recovery 实现。
- `./scripts/ci_software.sh` 完整通过：三包完整结果为
  `480 tests, 0 errors, 0 failures, 0 skipped`。
- 达到 RC 本地纯软件条件，建议在用户审查、授权 commit/push 且新 Hosted CI
  green 后，进入用户最终整机正常功能回归。

## 2. 开始前 Git 与 CI 基线

- 分支：`master`。
- HEAD：`cc9e75e0473bfdc1764577904e71c7f9bab21e93`。
- upstream：`origin/master`，同为 `cc9e75e0473bfdc1764577904e71c7f9bab21e93`。
- 本地领先/落后：`0/0`。
- `v0.3.0` commit：`c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1` commit：`5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 后 8 个提交；开始时 describe 为 `v0.3.1-8-gcc9e75e-dirty`。
- 开始时唯一工作区修改：`M docs/NEXT_COMMAND.md`，无未跟踪文件。
- 只读 `git ls-remote` 确认 `origin/master` 与现有 tags 未漂移。
- 开始时最新 GitHub Hosted `WindArmor Software CI` 为 run
  `31157555077`：HEAD `cc9e75e`、`completed/success`、全部 steps 成功。
- run `31157555077` 有 1 个未过期 artifact：
  `windarmor-software-ci-logs-31157555077`，过期时间为 2026-08-17。

## 3. v0.3.1 到当前 HEAD 的变化审计

### 3.1 Fan safety

- 定时器是唯一正常 PWM slew 推进和内部命令发布路径。
- e-stop 不再被 heartbeat 自动恢复，必须显式 `/fans/reset_e_stop`。
- MANUAL 新增显式 `/fans/manual_enable` 授权和本次授权后的双路 neutral handshake。
- 未知电机模式失效化缓存并立即安全停止。
- 看门狗必须为正有限值，且在 GPIO 初始化前校验。
- 死区、滞回、响应曲线、PWM 上下限与 slew 步长未发现非预期改变。

### 3.2 Motor command

- `current_targets` 继续严格表示最近成功发送给驱动的目标。
- position/speed 写入失败不提前提交软件状态或时间戳。
- batch partial write 保留失败前已成功的前缀，失败后阻断普通命令。
- command fault 尽力停止全部电机、进入 `ERROR` 并不自动恢复。

### 3.3 Lifecycle

- 部分初始化失败按已触及电机的反向顺序 best-effort stop，随后关闭 driver、
  清 callback 并释放 ROS 资源。
- configure 回滚、cleanup 和 shutdown 的释放流程幂等，单项失败不中断后续
  清理。
- 第二次 configure 使用全新 driver、callback、health/recovery session 和 ROS 资源。

### 3.4 State transition

- 转换结果为 `CHANGED`、`NO_CHANGE`、`REJECTED`，同状态请求幂等。
- 合法转换表显式；`ERROR` 不能回到运行态，`SHUTTING_DOWN` 为 terminal。
- reason/source 和最近转换快照保持，callback 在不持状态锁时执行。

### 3.5 Config

- 电机数组长度、ID 范围/唯一性、sign、软限位、control axes、键盘冲突、
  backend 和 ROS/safety 参数在驱动创建前集中校验。
- deprecated 标量电机参数的非默认值明确失败并指向列表参数。
- USB 新参数优先，仅在新值为空/零时显式 fallback 到旧值。

### 3.6 Motor health

- 非法反馈不覆盖最近合法反馈，未配置 motor ID 不污染状态。
- firmware fault bit、temperature warning/critical、无效帧计数和 fault latch 语义与测试一致。
- `motor_feedback_timeout_sec: 0.0` 默认仍关闭强制超时。
- 0x02 没有已验证的 `current_a`，不从 torque 推导 current。

### 3.7 Parser

- 0x02 feedback 的 position、speed、torque 和 temperature 四个 `uint16`
  继续使用大端序解析。
- 该端序有独立 parser 测试和用户正常实机复测记录；本 RC 没有再次修改。

### 3.8 CI

- `.github/workflows/ci.yml` 使用 GitHub hosted `ubuntu-24.04` 和 ROS 2 Jazzy。
- 仅 `contents: read`，无 self-hosted、secrets、设备映射、`--privileged`、真实 CAN/GPIO、
  硬件节点或 launch。
- Actions 均用 40 位 commit SHA 固定；artifact 设为 `if-no-files-found: error`。
- `scripts/check_ci_safety.py` 同时约束 workflow 和 `scripts/ci_software.sh`。

### 3.9 Transport recovery

- transport fault 与 motor health fault 分离，USB-CAN/SocketCAN 异常有明确类型与独立
  event 通道。
- generation 屏蔽旧 reader 事件，重连使用有界次数和可取消退避。
- 重连成功后为 `RECONNECTED_LOCKED`，ControllerState 仍为 `ERROR`。
- 不重新初始化电机、不 `enter_control_mode`、不恢复 MANUAL/AUTO/HOME/旧目标。
- cleanup/shutdown/deactivate 可取消 worker，取消期间晚到的 connect success 会再次 close。

## 4. 发布阻塞项审计

### 阻塞问题

未发现。

### 非阻塞技术债

- package 的 maintainer/email 包含历史占位值；同一 package 内部一致，本 RC 不随意
  改变责任人元数据。
- 部分资源释放和诊断路径使用 best-effort `except Exception`；静态复核显示这些路径
  不绕过已建立的安全状态，且现有故障注入覆盖后续清理，因此不扩大 RC
  重构。
- 结构化 `DiagnosticArray`、真实数值 `current_a`、空闲反馈周期能力和物理标定继续
  作为后续任务。

## 5. Package 版本

| Package | package.xml | setup.py | 其他版本源 |
|---|---:|---:|---|
| `imu_cybergear_ros2` | `0.3.2` | `0.3.2` | 无 `pyproject.toml` / `__version__` |
| `windarmor_fan_controller` | `0.3.2` | `0.3.2` | 无 `pyproject.toml` / `__version__` |
| `windarmor_bringup` | `0.3.2` | `0.3.2` | 无 `pyproject.toml` / `__version__` |

- 三包 name、description、maintainer/email 和 license 已做内部一致性测试。
- dependencies/test dependencies、entry points/console scripts 和 data files 已静态审计；未发现
  会阻塞当前构建、安装或入口的错误，本 RC 不做无关美化。
- `src/imu_cybergear_ros2/docs/项目总览与功能清单.md` 的过时“当前版本 v0.2.0”已更正，
  并明确该页保留早期 v0.2 功能分区。

## 6. 公共 ROS 接口冻结

| 接口 | 类型 | 相比 v0.3.1 |
|---|---|---|
| `/imu/data_raw` | `sensor_msgs/msg/Imu` | 不变 |
| `/imu/relative_roll_pitch` | `geometry_msgs/msg/Vector3Stamped` | 不变 |
| `/imu/zero_generation` | `std_msgs/msg/UInt64` | 不变 |
| `/motors/control_mode` | `std_msgs/msg/String` | 不变 |
| `/motors/manual_targets` | `std_msgs/msg/Float64MultiArray` | 不变 |
| `/motor/status` | `std_msgs/msg/String` | 不变 |
| `/e_stop` topic | `std_msgs/msg/Bool` | 不变 |
| `/e_stop` service | `std_srvs/srv/Trigger` | 不变 |
| `/enable_motor` | `std_srvs/srv/SetBool` | 不变 |
| `/imu/set_zero` | `std_srvs/srv/Trigger` | 不变 |
| `/motors/set_zero` | `std_srvs/srv/Trigger` | 不变 |
| `/fans/pwm` | `std_msgs/msg/Int32MultiArray` | 不变 |
| `/fans/left/pwm`, `/fans/right/pwm` | `std_msgs/msg/Int32` | 不变 |
| `/fans/status_pwm`, `/fans/auto_target_pwm` | `std_msgs/msg/Int32MultiArray` | 不变 |
| `/fans/enabled`, `/fans/auto_enabled`, `/fans/auto_active` | `std_msgs/msg/Bool` | 不变 |
| `/fans/control_state` | `std_msgs/msg/String` | 新增两个状态值，接口未改名 |
| `/fans/enable`, `/fans/auto_enable` | `std_srvs/srv/SetBool` | 不变 |
| `/fans/stop` | `std_srvs/srv/Trigger` | 不变 |
| `/fans/manual_enable` | `std_srvs/srv/SetBool` | 有意新增 |
| `/fans/reset_e_stop` | `std_srvs/srv/Trigger` | 有意新增 |

- 公开电机模式仍为 `MANUAL`、`AUTO`、`EMERGENCY_STOP`、`DISABLED`、`ERROR`。
- 风扇有意新增公开状态值 `MANUAL_DISARMED` 与 `MANUAL_WAITING_FOR_NEUTRAL`。
- 零点代次、电机模式和风扇状态仍使用 reliable、transient-local QoS；其他关键
  命令接口的 QoS 未发现非预期变化。
- `/fans/command_pwm` 仍是管理器到底层控制器的内部路由，不是普通公共控制入口。

## 7. 默认参数冻结

### 电机

- `motor_ids: [4, 3, 2, 1]`
- `motor_signs: [-1.0, 1.0, -1.0, 1.0]`
- `motor_limits_min: [-1.57, -1.57, -1.57, 0.0]`
- `motor_limits_max: [0.0, 1.57, 1.57, 1.57]`
- `command_interval_sec: 0.02`；`max_position_step: 0.4`
- MANUAL/AUTO/HOME motion speed：全部 `4.0 rad/s`
- `motion_dt_max_sec: 0.05`；`target_reached_tolerance_rad: 0.001`
- `manual_step_deg: 3.0`；`manual_repeat_gap_sec: 0.8`；
  `manual_repeat_dt_max_sec: 0.08`
- `default_speed: 10.0`；AUTO roll/pitch gain：`1.0/1.0`
- temperature warning/critical：`80.0/90.0 °C`
- `motor_current_limit_a: 5.0`；只作保留参数，不执行数值电流比较。
- `motor_feedback_timeout_sec: 0.0`；默认关闭强制超时。
- `reconnect_on_disconnect: true`；策略为 `30 / 0.5 / 10.0 / 1.5`。

### 风扇

- deadband on/off：`5.0/3.0 deg`；`fan_full_scale_deg: 45.0`。
- stop/start/AUTO max：`800/1200/1400 μs`。
- `control_rate_hz: 20.0`；rise/fall step：`10/20 μs`。
- `fan_response_curve: smoothstep`。

实际 YAML 与代码默认值已由 RC 契约测试同时冻结。本任务未调整任何上述
控制参数。

## 8. v0.3.2 Release Notes

- 新增 `docs/RELEASE_NOTES_v0.3.2.md`。
- 定位为“安全性、确定性与运行可靠性版本”，不声称为性能调优或最终标定版本。
- 包含风扇、电机命令、lifecycle、config/state contract、motor health、温度/fault bit、
  0x02 端序、CI 与 transport recovery 的用户向变化。
- 明确数值电流保护、feedback timeout 默认、重连后锁定和真实故障注入边界。

## 9. README / package README / YAML

- 根 `README.md` 已区分稳定标签 `v0.3.1` 与 `master` 上的 `v0.3.2` release candidate，
  明确 `v0.3.2` tag 尚未创建。
- 电机包 `README.md` 已标明 package RC 版本 `0.3.2`，并将 `4.0 rad/s` 描述修正为
  已进入正常功能回归、但尚未完成精确机械速度标定。
- 电机 YAML 的三模式速度注释已同步为 RC 冻结与标定边界。
- `motor_current_limit_a`、`motor_feedback_timeout_sec`、reconnect、温度、
  `fan_auto_max_pwm_us` 和 `fan_full_scale_deg` 现有 YAML 注释与实际行为一致，
  没有伪称最终物理标定。
- 风扇包和 bringup 没有独立 package README，本 RC 不凭空新建。

## 10. 已知验证边界

### 纯软件故障注入

- pure logic、fake driver、fake feedback、fake clock、fake USB/SocketCAN backend 和可控事件
  已覆盖命令失败、初始化回滚、清理、状态转换、motor health、transport fault 和受控重连。
- 这些是纯软件故障注入，不是真实硬件认证。

### 用户此前正常实机验证

- 用户此前完成统一 launch、MANUAL、AUTO、机械零点与风扇正常功能验证。
- 0x02 大端序修正后，用户完成正常机械零点/手动控制复测。
- 这些是用户报告的正常功能路径，不是极限、全部异常或故障注入认证。

### 未执行的真实故障注入

- 欠压、过流、真实 90 °C 过温、编码器 fault、feedback timeout。
- USB-CAN 拔线、CAN 断线、破坏串口、真实自动重连认证。
- `stop_motor` 失败、真实 cleanup 故障或机械卡死。

这些不阻塞 `v0.3.2`，但需要后续专门硬件故障验证任务和单独授权。

## 11. RC 自动化测试

- RC release contract 专项：`5 passed`。
  - release metadata：1 项；
  - 关键接口/公开模式/QoS：2 项；
  - 电机/风扇默认参数：2 项。
- CI infrastructure：`16 passed`。
- 电机包 pytest：`359 passed`。
- 风扇关键回归：`98 passed`。
- 三包隔离 build：`3 packages finished`。
- 三包完整 colcon：`480 tests, 0 errors, 0 failures, 0 skipped`。
- CI safety checker：通过，检查 2 个目标文件。
- Python compile：通过。
- whitespace：统一 CI 检查通过；
  `git diff --check -- . ':(exclude)docs/NEXT_COMMAND.md'` 通过。
- 失败：0；错误：0；跳过：0。

## 12. scripts/ci_software.sh

`./scripts/ci_software.sh` 已完整执行并通过，包括：

1. CI safety checker；
2. Git whitespace checker；
3. Python compile；
4. 三 package 隔离 colcon build；
5. 电机 package pytest；
6. 风扇 safety regression；
7. 三 package 完整 colcon test；
8. `colcon test-result --verbose`。

该脚本使用隔离临时 build/install/log/ROS log 目录，未使用真实硬件 I/O。

## 13. GitHub Hosted CI

- 开始基线 run `31157555077` 对 HEAD `cc9e75e` 为 `success`，有 1 个未过期
  日志 artifact。
- 本 RC 工作区未 commit、未 push，因此尚未触发包含当前 RC 修改的新
  GitHub Hosted CI。
- 本地等价 CI 的通过不代替 push 后 Hosted CI green。

## 14. 用户最终整机回归清单

- 新增 `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md`。
- 范围仅包含启动前、系统启动、IMU/机械零点、MANUAL、HOME、小幅 AUTO、
  风扇 MANUAL/AUTO、急停、普通急停恢复与正常退出。
- 清单明确排除拔线、真实欠压/过流/过温、编码器故障、机械卡死、故意
  stop 失败和极限推力测试。
- 实际通电前仍必须完成 `AGENTS.md` 十项授权门槛。

## 15. 硬件安全声明

Codex 本任务未：

- 执行 `ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
  `scripts/setup_can.sh`；
- 访问 IMU、`/dev/imu_usb`、真实串口或任何硬件设备文件；
- 创建、配置或访问 SocketCAN/`can10`；
- 初始化 CyberGear，写真实 SDO，使能、停止或控制真实电机；
- 访问 GPIO12/GPIO13，初始化 Servo/电调，输出 PWM 或控制风扇；
- 启动硬件节点或 launch；
- 执行带电测试或真实硬件故障注入。

构建、静态契约、pure logic 和 fake/mock 测试只是纯软件验证，不表述为实机验证。

## 16. 任务完成但提交前 Git 状态

- branch：`master`。
- HEAD/upstream：均为 `cc9e75e0473bfdc1764577904e71c7f9bab21e93`，ahead/behind `0/0`。
- `docs/NEXT_COMMAND.md` 仍是任务前用户修改；Codex 未修改、覆盖、暂存或还原。
- `docs/NEXT_COMMAND.md` 任务前与最终 SHA-256 均为
  `30613c6f4457dd479ac41b6694cb54c5ce5b1fddf4b41c97a1291c52fcfa39c9`。
- 本任务修改 11 个已跟踪文件，新增 3 个文件；另有用户原有
  `M docs/NEXT_COMMAND.md`。
- 未执行 `git add`、commit、push、tag、checkout、switch、reset、clean、restore、stash、
  rebase 或 merge。
- `v0.3.2` tag 未创建；`v0.3.0`/`v0.3.1` 未修改。

## 17. 是否可以进入最终实机回归

**YES**。

当前建议是：先由用户审查本 RC 工作区，再单独授权 commit/push；确认新
GitHub Hosted CI green 后，按 `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md` 进行一次正常整机
功能回归。本结论不授权 Codex 执行硬件操作，也不等于已完成实机回归。

## 18. v0.3.2 尚缺步骤

1. 用户审查当前 RC 工作区差异。
2. 用户单独授权 RC commit 和 push。
3. 等待并确认新 GitHub Hosted CI green 及日志 artifact。
4. 用户完成 RC 正常整机功能回归并报告结果。
5. 执行最终发布审查。
6. 用户单独明确授权创建 annotated `v0.3.2` tag。
7. push tag；根据用户决定可选创建 GitHub Release。

## 19. 后续版本建议

只记录，本 RC 未实施：

- 结构化 `DiagnosticArray`；
- 经协议与实机验证的 `current_a` 数据能力；
- 电机空闲反馈周期能力验证；
- 风扇 PWM/推力与 `fan_full_scale_deg` 物理标定；
- MANUAL/AUTO/HOME 三模式实际机械速度标定；
- 真实 transport 断线/重连与其他危险故障注入；
- 高级姿态控制、动态平衡和 PID 优化。
