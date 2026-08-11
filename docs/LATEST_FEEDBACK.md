# 最新反馈：v0.4.0 Flight Control Core & Interface Foundation

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-11

## 1. 执行结论

v0.4.0 Task 1 已完成纯软件基础层：仓库现在具备长期飞控架构文档、Flight API
开发文档、ROS 结构化电机反馈消息包，以及不依赖 ROS runtime 或硬件库的
Flight Core、示例算法、fake state helper 和严格 validation。

本任务没有实现真实 Flight Runtime、topic adapter、authority service 或
actuator dispatch。现有 IMU、电机、风扇和 bringup 运行路径未接入新包，
v0.3.2 的运行行为与安全语义保持不变。

## 2. 任务基线与 Git 边界

- 分支：`master`；
- 任务开始 HEAD/upstream：
  `398ea9b035929f745be79c4d75cfd99d73c77702`，ahead/behind `0/0`；
- 任务开始时用户已有修改：`docs/NEXT_COMMAND.md`；
- 该文件任务开始和结束时 SHA-256 均为
  `754994ed67ec1c4ccbd90c578a76d0ce37700c4ccb91cc695253a3f0c0809503`，
  本任务没有修改、覆盖、还原或暂存它；
- `v0.3.2` annotated tag object 仍为
  `29ae0bbcfa22206686cb86f5896a08bccfcb5a37`，仍指向
  `398ea9b035929f745be79c4d75cfd99d73c77702`；
- `v0.3.0`、`v0.3.1` 和 `v0.3.2` 均未创建、移动、删除或重建；
- 未执行 commit、push 或 tag。

## 3. 修改文件与目的

文档：

- `docs/FLIGHT_CONTROL_ARCHITECTURE.md`：长期架构边界、package 职责、
  authority/generation 和不可妥协安全契约；
- `docs/FLIGHT_CONTROL_API.md`：算法入口、全部字段、单位、presence/validity、
  fake state 和 unit test 用法；
- `README.md`：记录 v0.4.0 foundation 状态、文档入口和五包纯软件 CI；
- `docs/LATEST_FEEDBACK.md`：本任务结果与验证边界。

新 `windarmor_interfaces` package（版本 `0.4.0`）：

- `CMakeLists.txt`、`package.xml`；
- `msg/MotorFeedback.msg`；
- `msg/MotorFeedbackArray.msg`；
- `test/test_message_contract.py`。

新 `windarmor_flight_control` package（版本 `0.4.0`）：

- `package.xml`、`setup.py`、`setup.cfg`、resource marker；
- `core/authority.py`、`controller.py`、`models.py`、`validation.py`；
- `algorithms/base.py`、`example_controller.py`；
- `testing.py` 和 package exports；
- `test/test_import_boundary.py`、`test_models.py`、`test_validation.py`、
  `test_example_controller.py`。

纯软件 CI：

- `scripts/ci_software.sh`：编译新 Python 源码，增加 `flight-tests`，并将五包
  纳入完整 colcon test；
- `.github/workflows/ci.yml`：执行新增专项和五包完整测试；
- `src/windarmor_bringup/test/test_ci_infrastructure.py`：冻结新增 CI 覆盖契约。

现有三个 v0.3.2 package 的产品代码、配置、版本、launch 和 package metadata
均未修改。

## 4. 新增接口

### MotorFeedback.msg

最终字段为：

```text
logical_name
can_id
has_feedback
position_valid / position_rad
velocity_valid / velocity_rad_s
torque_valid / torque_nm
temperature_valid / temperature_c
device_mode_valid / device_mode
fault_flags_valid / fault_flags
feedback_age_sec
valid
fresh
healthy
```

ROS 数值字段没有 `None`，因此每个可能缺失的反馈值使用显式 presence flag。
`has_feedback=false` 时消费者不得把默认数值零解释为真实反馈。没有加入
`current_a`、RPM 或 thrust。

`MotorFeedbackArray.msg` 使用 `builtin_interfaces/Time stamp`、`uint64 sequence`
和 `MotorFeedback[] motors` 表达完整 snapshot。本任务只完成消息生成和契约测试，
没有修改现有电机节点去发布该消息。

## 5. Flight API 最终模型

- `Vector3(x, y, z)`；
- `Quaternion(x, y, z, w)`；
- `ImuState`：orientation，三轴绝对姿态，relative roll/pitch，角速度，线加速度，
  sample age，valid/fresh/connected，zero generation；
- `MotorState`：逻辑名称，position/velocity/torque/temperature，device mode，
  fault flags，feedback age，has feedback，valid/fresh/healthy；
- `FanChannelState`：归一化 applied command 或 `None`，以及 output known；
- `FanSystemState`：左右通道、enabled、control state；
- `SystemState`：command authority、authority generation、E-STOP、电机/风扇状态、
  Flight active、actuation allowed、required inputs fresh；
- `FlightState`：timestamp、sequence、IMU、只读 logical motor mapping、fans、system；
- `FanCommand`：左右 `[0.0, 1.0]` 无量纲请求；
- `FlightCommand`：完整 logical motor position frame、fan command、
  `request_safe_stop`；
- `FlightController.reset()/update(state, dt)` Protocol；
- `CommandAuthority`：`NONE/MANUAL/LEGACY_AUTO/FLIGHT_CONTROL`；
- `AuthorityGrant`：authority、generation、sequence。

所有 snapshot/command dataclass 均冻结，mapping 在构造时复制为只读 mapping。
未知真实物理量使用 `None`，不使用 `0.0` 伪装反馈。

## 6. Validation 与示例行为

纯 validation 明确拒绝：

- NaN、Inf、负 age 和非法无符号 mode/fault 值；
- 缺少必要子状态、类型错误或 presence/valid/fresh/healthy 自相矛盾；
- 不完整、带未知 key 或含非有限值的电机命令；
- 超出 `[0.0, 1.0]` 的风扇状态/命令；
- E-STOP 下仍声明 actuation allowed；
- Flight active 但 authority 不是 `FLIGHT_CONTROL`；
- 非法 authority generation/sequence。

validation 不做 clamp，不读取硬件，也不替代现有软限位或状态机。
`FlightCommand.safe_stop(complete_motor_frame)` 只产生不可变算法意图；它不会发布
E-STOP、恢复 ERROR 或调用任何硬件能力。中性示例控制器的目标由测试/调用方
显式提供，不声称 `0.0` 是实机机械中位，也不包含 PID 或真实姿态控制逻辑。

## 7. 相比任务建议的必要细化

- `MotorFeedback.msg` 为每个可缺失数值增加 `*_valid`，而不只依赖一个
  `has_feedback`，使 partial/unknown 的 ROS 表达可无歧义转换为 Python `None`；
- `MotorFeedbackArray.msg` 增加 stamp 和 sequence，使未来 adapter 能识别完整
  snapshot 的时间与顺序；
- `SystemState` 增加 `authority_generation`，为已确认的旧 generation 永久拒绝
  契约保留纯模型字段；
- `FlightCommand.safe_stop()` 要求调用者仍提供完整 motor frame，避免把省略 key
  误解为保留旧目标。其 safe-stop flag 才是未来 runtime 的停止裁决依据；
- `MotorState` 不暴露 CAN ID。CAN ID 保留在 ROS transport interface，算法只看
  logical name，进一步维持硬件解耦。

这些细化不接入 actuator，也不改变现有 runtime。

## 8. 已执行的软件验证

所有测试均为 pure logic、源码契约、fake state 或无硬件 colcon build/test。

1. 新包早期 Python 专项：`27 passed`；
2. Flight/interface/CI 基础设施组合专项：`46 passed`；
3. 两个新包隔离 `colcon build`：`2 packages finished`；
4. 两个新包隔离 `colcon test`：`30 tests, 0 errors, 0 failures, 0 skipped`；
5. 第一轮 `./scripts/ci_software.sh`：
   - 电机 package：`359 passed`；
   - 风扇关键回归：`98 passed`；
   - Flight/interface 专项：`29 passed`；
   - 五包完整 colcon：`511 tests, 0 errors, 0 failures, 0 skipped`；
6. validation 补强后专项：`31 passed`；
7. 最终 `./scripts/ci_software.sh`：
   - CI safety、whitespace、Python compile：通过；
   - 五包 build：`5 packages finished`；
   - 电机 package：`359 passed`；
   - 风扇关键回归：`98 passed`；
   - Flight/interface 专项：`33 passed`；
   - 五包完整 colcon：`515 tests, 0 errors, 0 failures, 0 skipped`。

最终构建和测试没有报告 warning、failure、error 或 skipped。

## 9. Task 2 后续项

Task 1 没有阻塞项。Task 2 接入前仍需明确并实现：

- 正式 logical motor names 及其与现有配置/CAN ID 的 adapter 映射；
- 现有电机节点的结构化 feedback snapshot publisher；
- IMU、电机、风扇和系统状态的 `StateAggregator`；
- runtime 的 authority grant、generation/sequence 拒绝和
  ARMING/ACTIVE/INHIBITED 状态机；
- 归一化 fan command 与既有安全 fan manager 之间的 adapter；
- flight motor command 进入现有 `MotorManager` 安全路径的接口。

这些后续项不得绕过 E-STOP、ERROR、看门狗、软限位或既有命令仲裁，也不得在
transport 恢复后自动恢复控制或重发旧目标。

## 10. 硬件与未执行验证

本次没有运行 `ros2 run`、`ros2 launch`、`ros2 topic` 或 `ros2 service`，没有
运行 `sudo` 或 CAN setup。没有访问 IMU、`/dev/*`、真实串口、CAN、SocketCAN、
USB-CAN、CyberGear、GPIO12/GPIO13、PWM 或电调。4 个微电机和 2 个风扇均未因
本任务被控制，未执行任何实机测试或带电测试。

真实消息发布、runtime integration、actuator authority 和所有实机验证均未执行，
原因是它们明确属于后续任务且当前没有硬件授权。本次结果是纯软件验证，不是
实机验证或硬件安全认证。

## 11. 最终工作区状态

- `git diff --check`：通过；
- `git diff --stat`（tracked）为 `6 files changed, 799 insertions(+),
  1263 deletions(-)`；其中 `docs/NEXT_COMMAND.md` 的大段差异完全是任务开始前的
  用户修改；
- 新增未跟踪文件共 25 个：Flight package 18 个、interfaces package 5 个、
  架构/API 文档 2 个；
- 最终状态包含本任务的 tracked 修改、新增两个 package/两份文档，以及用户原有
  `docs/NEXT_COMMAND.md` 修改；
- 未暂存任何文件；
- 未执行 commit、push 或 tag；
- 所有稳定标签保持不变。
