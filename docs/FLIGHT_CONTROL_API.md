# WindArmor Flight Control API

本文档面向飞控算法开发。v1 API 是 v0.4.0 Flight Control Integration
Foundation 的纯算法接口；Task 4 已实现默认关闭的 authority/actuator adapter，
但没有执行真实硬件验证。adapter 必须保持这里的模型、单位、校验和安全语义兼容。

## Quick Start / Handoff

算法开发的主要修改范围是
`src/windarmor_flight_control/windarmor_flight_control/algorithms/`。除非与对应维护者
另行协作，不修改 hardware driver、runtime、authority 或 safety package，也不在
算法模块中 import ROS、CAN、串口、GPIO/PWM 或其他 hardware library。

实现对象只需满足：

```python
class FlightController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

- 输入只使用不可变 `FlightState`，输出只返回 `FlightCommand`；
- `reset()` 只清理算法内部状态；
- normal command 必须包含全部配置逻辑电机和左右风扇的完整 payload；
- 无法继续安全计算时返回 `FlightCommand.safe_stop()`，不复用旧 target；
- algorithm 不 arm、不管理 authority、不 reset E-STOP/ERROR、不 set zero；
- 普通测试使用内存 fake state，不创建 ROS node 或真实 driver。

在仓库根目录可直接运行最小离线测试：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_controller.py -q
```

默认 `flight_takeover_enabled=false`；真实 Flight takeover 与硬件验证不属于算法
开发的默认流程。

`bounded_verification_controller` 仅用于项目硬件验证，不是实际飞控算法模板；
其默认配置不可执行，任何真实 offset 或 fan command 都必须在对应实机 Gate 前由
用户明确确认。

## 算法入口

算法实现 `FlightController`：

```python
from windarmor_flight_control.core.controller import FlightController


class MyController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...


controller: FlightController = MyController()
```

`dt` 是当前算法 tick 与上一 tick 之间的单调时间差，单位为秒。DRY_RUN Runtime
负责拒绝并锁存抑制非法 tick；算法不得自行读取 ROS clock 或硬件时钟。`reset()`
只能修改算法实例内部状态。

纯 core 与 algorithms 可在普通 Python 环境使用，不需要 ROS graph、Raspberry
Pi、CAN、串口或 GPIO。

## FlightState

`FlightState` 及全部子状态使用冻结 dataclass。`motors` 在构造时复制为只读
mapping，算法不能意外改变当前 snapshot 或 adapter 持有的源字典。

### 顶层字段

| 字段 | 类型 | 单位/语义 |
|---|---|---|
| `timestamp_sec` | `float` | snapshot 单调时间，秒 |
| `sequence` | `int` | snapshot 非负序号 |
| `imu` | `ImuState` | IMU 状态 |
| `motors` | `Mapping[str, MotorState]` | 以稳定逻辑名称索引的电机状态 |
| `fans` | `FanSystemState` | 双风扇状态 |
| `system` | `SystemState` | authority 与系统安全条件 |

逻辑电机名称是 Flight API 配置键，不等同于 CAN ID，也不声明未经确认的机械轴
名称。算法应从 runtime 配置获得所需键集合，不应解析或生成 CAN ID。

### ImuState

| 字段 | 类型 | 单位/语义 |
|---|---|---|
| `orientation` | `Quaternion \| None` | 无量纲，`x/y/z/w` |
| `roll_rad`, `pitch_rad`, `yaw_rad` | `float \| None` | rad |
| `relative_roll_rad`, `relative_pitch_rad` | `float \| None` | 统一归零后姿态，rad |
| `angular_velocity_rad_s` | `Vector3 \| None` | rad/s |
| `linear_acceleration_m_s2` | `Vector3 \| None` | m/s² |
| `sample_age_sec` | `float \| None` | snapshot 时的样本年龄，秒 |
| `valid` | `bool` | 内容通过 adapter 的结构/数值校验 |
| `fresh` | `bool` | 内容满足 runtime 配置的新鲜度条件 |
| `connected` | `bool \| None` | 已观测连接状态；未观测为 `None` |
| `zero_generation` | `int \| None` | 已观测 IMU 零点世代，非负；未观测为 `None` |

API 不定义 `relative_yaw_rad`。需要该能力时必须先建立来源、零点和兼容契约。

### MotorState

| 字段 | 类型 | 单位/语义 |
|---|---|---|
| `name` | `str` | 稳定逻辑名称 |
| `position_rad` | `float \| None` | rad |
| `velocity_rad_s` | `float \| None` | rad/s |
| `torque_nm` | `float \| None` | N·m |
| `temperature_c` | `float \| None` | °C |
| `device_mode` | `int \| None` | 经协议解析的设备模式 |
| `fault_flags` | `int \| None` | 经协议解析的设备故障位 |
| `feedback_age_sec` | `float \| None` | snapshot 时的反馈年龄，秒 |
| `has_feedback` | `bool` | 当前对象是否携带反馈 |
| `valid` | `bool` | 完整反馈通过结构/协议数值校验 |
| `fresh` | `bool` | 合法反馈满足新鲜度条件 |
| `healthy` | `bool` | adapter 已确认合法、新鲜且未触发健康保护 |

`has_feedback=False` 时，全部物理反馈、设备模式、故障位和年龄必须为 `None`，
且 `valid/fresh/healthy` 必须为 false。API 不包含 `current_a`：现有 0x02 状态
帧没有经过验证的真实安培字段，不能从 `torque_nm` 推导。API 也不虚构 RPM。

`windarmor_interfaces/MotorFeedback.msg` 是 ROS adapter 的传输契约。ROS
message 不能表达 Python `None`，因此 position、velocity、torque、temperature、
device mode 和 fault flags 都有对应的 `*_valid` presence flag；消费者在 flag 为
false 时必须忽略该数值字段。`has_feedback` 表示整条消息是否携带反馈，不能因
ROS 数值字段默认是零就推断真实反馈为零。`MotorFeedbackArray.msg` 用 stamp、
sequence 和完整 motor 数组表达同一 snapshot。电机节点现在周期发布
`/motors/feedback`：只复制现有合法 feedback cache 和本地 monotonic 接收年龄，
不触发额外 driver I/O。没有反馈的配置电机仍有 entry，且 `has_feedback` 和全部
presence flag 为 false。

### Authoritative Safety Readback 顺序

`MotorSafetyState.msg` 与 `FanSafetyState.msg` 都以两个正 `uint64` 字段定义来源内
顺序：

| 字段 | 语义 |
|---|---|
| `source_epoch` | publisher 进程节点实例的 monotonic epoch；`0` 非法 |
| `observation_sequence` | 该 epoch 内从 `1` 开始严格递增的序列；`0` 非法 |

同一节点实例经过 configure/deactivate/activate 或 reconfigure 时不重置 epoch 或
sequence。消费者首次观测要求两者都大于零；同 epoch 只接受更大 sequence；更大
epoch 接受任意正 sequence 并重建该来源 baseline；更小 epoch 永久拒绝。epoch 不
使用 ROS time 或 wall time，Runtime 自身重启时重新建立接收 baseline。

### FanSystemState

每个 `FanChannelState` 包含：

- `applied_command: float | None`：经 adapter 表达的无量纲实际应用命令；
- `output_known: bool`：是否有依据认为应用命令已知。

`output_known=False` 时 `applied_command` 必须为 `None`；已知值必须在
`[0.0, 1.0]`。该值不是 RPM 或 thrust。`FanSystemState` 还包含
`enabled: bool | None` 和 `control_state: str | None`。`None` 表示 runtime 尚未
收到该状态；它与明确观测到 `enabled=False` 或一个真实状态字符串不同。空字符
串不是 unknown 的合法表达。

### SystemState

| 字段 | 语义 |
|---|---|
| `command_authority` | `NONE/MANUAL/LEGACY_AUTO/FLIGHT_CONTROL` |
| `authority_epoch` | Runtime 进程 session 的正 `uint64`；无 authority 时为 `0` |
| `authority_generation` | 当前授权世代；旧世代命令不得接受 |
| `e_stop_active` | `bool \| None`；已观测急停状态，未观测为 `None` |
| `motor_control_mode` | `str \| None`；既有公开电机模式，未观测为 `None` |
| `fan_control_state` | `str \| None`；既有风扇管理器状态，未观测为 `None` |
| `flight_control_active` | runtime 是否处于 Flight Control 活动状态 |
| `actuation_allowed` | 上游安全/authority 是否允许普通输出 |
| `required_inputs_fresh` | 本 tick 所需输入是否全部新鲜 |

`CommandAuthority` 与既有 motor/fan 状态机正交。即使 authority 是
`FLIGHT_CONTROL`，E-STOP、ERROR、disabled、watchdog 或 safety layer 仍可拒绝
命令。`command_authority`、`flight_control_active`、`actuation_allowed` 和
`required_inputs_fresh` 是 runtime 本地裁决状态，不是假装成硬件观测的默认值；
startup 时 authority 可明确为 `NONE`，其余裁决可明确为 false。

`e_stop_active` 现在来自 motor/fan authoritative safety readback 聚合：任一路
latch true 为 `True`，两路均已观测且新鲜并为 false 才为 `False`，其他情况为
`None`。`/e_stop=False` 不参与解除证明。`e_stop_active=None` 绝不等于 `False`。
State validation 只允许在
`e_stop_active is False`、fan enabled 明确为 true、电机/风扇模式均已观测、
所需输入新鲜、两个 owner readback 均为当前 `(authority_epoch, generation)` 的
`FLIGHT_CONTROL`，且 Flight authority 已 atomic commit 时声明
`actuation_allowed=True`。默认 takeover 关闭时，即使进入 `READY_TO_TAKEOVER`
也始终保持 `actuation_allowed=False`。

## None、valid、fresh 与 healthy

- `None`：真实物理值或外部状态从未获得、当前未知或不能由现有来源验证；
- `valid`：当前内容通过数据结构、有限值和协议范围等校验；
- `fresh`：合法内容还满足 runtime 配置的新鲜度条件；
- `healthy`：合法且新鲜，并且 adapter/既有安全层未发现该设备健康故障。

四者不是同义词。`False` 是明确的布尔裁决或观测，不能用来代替尚未观测的外部
状态；`valid/fresh/healthy=False` 则明确表示对应条件当前不成立。连接存在不
保证已有样本，合法旧样本不等于新鲜，温度回落或收到正常帧也不能自行清除既有
锁存 ERROR。算法应在输入不满足其要求时返回 safe-stop request，不能用零、空
字符串或默认 false 填充 unknown。

## FlightCommand

```python
@dataclass(frozen=True)
class FanCommand:
    left: float
    right: float


@dataclass(frozen=True)
class FlightCommand:
    motor_positions_rad: Mapping[str, float] | None
    fan_commands: FanCommand | None
    request_safe_stop: bool = False
```

风扇命令是无量纲闭区间 `[0.0, 1.0]`：`0.0` 是停止请求，`1.0` 是 Flight
API 允许的最大归一化请求。PWM 微秒映射、起转值和实际上限不属于算法层。

normal command 的 `request_safe_stop` 为 false，两个 payload 都必须存在，且
motor frame 必须包含配置要求的全部电机键。缺少一个键不能表示“保持旧目标”，
多一个未知键也不能被忽略。NaN、Inf、越界风扇值和非有限电机目标全部明确
拒绝，不做静默 clamp；硬件软限位和位置推进仍属于后续 adapter 与现有安全层。

`FlightCommand.safe_stop()` 无参数返回：

```python
FlightCommand(
    motor_positions_rad=None,
    fan_commands=None,
    request_safe_stop=True,
)
```

safe-stop 只表示算法主动放弃继续提供普通 actuator command。它不携带可执行
target，runtime 不得缓存、复制或重发上一帧 command，也不得把 `None`
替换成伪造的零目标。人为构造 safe-stop flag 与任一 actuator payload 的混合
命令会被 validation 拒绝。

Task 2 DRY_RUN 只把 safe-stop 发布为无 payload preview。后续 authority runtime
才能把它解释为撤销或 inhibit Flight authority 的请求。它本身不操作硬件、
不等于 hardware E-STOP、不清除 ERROR，也不恢复 MANUAL、AUTO、HOME 或任何旧
控制状态。

## Validation

在把算法输出交给任何 adapter 前调用：

```python
from windarmor_flight_control.core.validation import (
    FlightValidationError,
    validate_flight_command,
    validate_flight_state,
)

required_motors = ("axis_a", "axis_b", "axis_c", "axis_d")
validate_flight_state(state, required_motors)
command = controller.update(state, dt)
validate_flight_command(command, required_motors)
```

示例名称只用于测试，不代表实际机械命名。validation 是纯函数，失败时抛出
`FlightValidationError`；它不修改输入、不访问硬件，也不把非法值修正为看似
可执行的值。safe-stop 只校验 flag 与 payload 互斥，不运行 normal actuator
payload 或 required motor-key 校验，因此 stale/invalid state、尚未建立 actuator
key 集合都不会妨碍算法放弃控制。

## DRY_RUN / Authority Preparation Runtime 与 controller factory

独立 observer launch 为 `flight_control_dry_run.launch.py`，只启动 Flight Runtime
本身；它不会启动 IMU、电机、风扇或 bringup。默认
`flight_takeover_enabled=false` 时不创建 actuator envelope publisher 或 ownership
clients。
Runtime 从 `flight_control.yaml` 读取逻辑电机键、observer PWM 范围、各输入
freshness 和 factory contract：

```yaml
controller_factory: "windarmor_flight_control.algorithms.flight_controller:create_controller"
```

factory 必须提供：

```python
def create_controller(required_motor_names: tuple[str, ...]) -> FlightController:
    ...
```

factory 和算法模块不得 import ROS。默认示例以每个逻辑 key 的测试值 `0.0` 构造
`NeutralExampleController`，不声明这些值是真实机械中位。由于 DRY_RUN state 的
`actuation_allowed` 始终为 false，默认示例在线返回 payload-free safe-stop；normal
command 可继续用 fake state 离线测试，或用明确的 test controller 验证 preview。

每个 control timer tick 使用一次 monotonic snapshot 和真实 monotonic `dt`。loader、
`reset()`、state validation、`update()` 或 command validation 失败都会锁存本地
inhibited，停止继续调用故障 controller，且不会因 sensor 恢复自动解除。非 ACTIVE
output 只发布到：

```text
/flight_control/dry_run/status
/flight_control/dry_run/command_preview
```

这两个 topic 是只读观察契约，不是 actuator command。

Task 3 另提供：

```text
/flight_control/authority/status
/flight_control/authority/prepare
/flight_control/authority/cancel
/flight_control/authority/reset_inhibit
```

算法不负责调用这些服务，也不负责 arm、清除 E-STOP/ERROR 或管理 generation。
prepare 只使本地状态进入 ARMING 并检查 preflight；满足后进入
READY_TO_TAKEOVER。READY 阶段算法仍看到 authority `NONE`、epoch/generation `0`、
`flight_control_active=false`、`actuation_allowed=false`。默认 takeover 关闭时
`takeover_supported=false`，所以不会进入 ACTIVE。

pure authority core 在 Runtime 构造时固定正 `authority_epoch`，在 prepare 时分配
attempt generation；正式 token 为 `(authority_epoch, generation)`。cancel/inhibit
后旧 token 永久失效，Runtime 重启也不会恢复旧 authority。owner ack 只记录 owner、当前 token 和 owner 观察到的
诊断 state sequence；ack 成功不改变 READY 状态，也不设置 cutoff。两路 owner 可按
任意顺序 ack，duplicate、旧 generation、cancel/inhibit 后或 READY 前的 ack 均被
拒绝。

takeover 开启时，Runtime 必须在 READY 后依次完成 motor/fan reserve 与 commit；
只有 commit response 可作为 ack。当前 token、两路 ack 与 ownership readback 齐全
后才能另行调用一次
atomic commit，并传入提交瞬间的当前 `FlightState.sequence`。该 sequence 不得早于
进入 READY 时记录的 barrier，并且仅它能成为不可变
`arming_cutoff_state_sequence`。commit 成功产生一次 immutable result，要求上层
重置 controller 并丢弃 pre-commit preview；authority core 不导入或调用算法实现。
duplicate/旧 token commit 被拒绝。ACTIVE 的第一条 command 必须封装在不可变
`FlightCommandEnvelope` 中，并满足 epoch/generation、严格递增 command sequence、
`FlightState.sequence > arming_cutoff_state_sequence` 和有限 produced time。
handoff 前计算的 preview 从不缓存或复用。

ownership endpoints 为 `/motors|fans/flight_ownership/{prepare,commit,revoke}`，
owner readback 为 `/motors|fans/ownership_state`，唯一 actuator transport 为
`/flight_control/command`。Motor adapter 仍走 `MotorManager` 的 FLIGHT motion source
与原有安全推进；fan adapter 仍走 `FanCommandManager`，把 `(0,1]` 映射到
`[fan_start_pwm_us, flight_fan_max_pwm_us]`，`0` 映射 stop，并保留既有 slew。该
归一化值不是 thrust fraction。

双方分别维护 handoff lease 与 ACTIVE command heartbeat lease，Runtime owner-readback
freshness 与 transaction timeout 也都使用本地 monotonic 时间。reserve 启动 handoff
deadline，commit 不重置；第一条 token、sequence、post-cutoff 与 payload 均合法的
normal envelope 才切换到 ACTIVE command lease。后续只有合法 normal command 刷新；
duplicate、wrong epoch/generation、invalid payload 与 safe-stop 都不刷新。

默认 `flight_handoff_timeout_sec=1.0`，motor/fan
`*_flight_handoff_timeout_sec=1.5`，motor/fan
`*_flight_command_timeout_sec=0.25`，`flight_revoke_timeout_sec=0.25`。单位均为
monotonic seconds，必须是严格大于零的有限值；owner handoff 默认比 Runtime transaction
多 `0.5 s` 软件调度余量，ACTIVE timeout 没有为掩盖 handoff 延迟而放宽。这些默认值
均未经过真实硬件 timing validation。

rollback 和 ARMING/READY/ACTIVE shutdown 都先本地 invalidate token、关闭 executable
command gate、清除 pending handoff 并锁存 `INHIBITED`，再分别执行一次非阻塞
best-effort revoke。cleanup 内部状态区分 `not_attempted`、`success`、
`service_unavailable`、`timeout`、`exception`、`rejected`（以及 malformed response）；
cleanup failure 不会再次触发 rollback。owner 自身 lease 仍是 Runtime crash/失联后的
独立 fail-closed 后盾，任何释放都不会自动恢复 legacy owner。

## Fake state 示例

```python
from windarmor_flight_control.algorithms import NeutralExampleController
from windarmor_flight_control.testing import (
    make_fake_flight_state,
    make_stale_flight_state,
    make_unobserved_flight_state,
)


motor_names = ("axis_a", "axis_b", "axis_c", "axis_d")
state = make_fake_flight_state(motor_names)
controller = NeutralExampleController({name: 0.0 for name in motor_names})

controller.reset()
command = controller.update(state, dt=0.01)
```

`make_fake_flight_state` 只构造内存数据；其中数值明确是测试数据，不表示实机
反馈、真实安全默认值或已确认的机械中位。它用于 fully observed healthy 场景。
startup unknown 和 stale 场景分别使用：

```python
startup = make_unobserved_flight_state(motor_names)
assert startup.system.e_stop_active is None
assert startup.fans.enabled is None

stale = make_stale_flight_state(motor_names)
assert stale.system.required_inputs_fresh is False
assert stale.system.actuation_allowed is False
```

算法可以直接放弃控制，不应保存或复制旧 target：

```python
if not state.system.required_inputs_fresh:
    return FlightCommand.safe_stop()
```

## Unit test 示例

```python
def test_controller_returns_valid_complete_frame():
    names = ("axis_a", "axis_b", "axis_c", "axis_d")
    state = make_fake_flight_state(names)
    controller = MyController()

    controller.reset()
    command = controller.update(state, 0.01)

    validate_flight_state(state, names)
    validate_flight_command(command, names)
```

这类测试不应创建 ROS node、连接 CAN/串口、初始化 GPIO/PWM 或实例化真实硬件
driver。

## 禁止能力与当前边界

算法没有以下能力，Flight Runtime 也不得直接取得这些能力：

- 直接访问 CyberGear、CAN、串口、GPIO、PWM 或电调；
- 直接调用 hardware service 或 backend；
- 清除 ERROR 或 E-STOP；
- enable/disable hardware 或 set zero；
- 修改 command authority；
- 绕过现有电机/风扇状态机、软限位、看门狗或安全退出；
- 在 transport 恢复后自动恢复 MANUAL/AUTO/HOME 或重发旧目标。

v0.4.0 Task 4 已包含 restart-safe epoch、两阶段 owner handoff、atomic commit、
post-grant new-state barrier、motor/fan adapter 与 fail-closed lease，但 takeover
默认关闭。验证仅覆盖 pure/fake/in-memory 软件路径；硬件方向、动态响应、PWM/ESC、
电机与风扇联合 takeover 均等待单独授权后的实机验证。
