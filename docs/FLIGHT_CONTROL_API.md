# WindArmor Flight Control API

本文档面向飞控算法开发。v1 API 是 v0.4.0 Flight Control Integration
Foundation 的纯软件接口；当前版本不能控制真实 actuator。后续接入 runtime 时
优先保持这里的模型、单位、校验和安全语义兼容。

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

`dt` 是当前算法 tick 与上一 tick 之间的单调时间差，单位为秒。未来 runtime
负责拒绝或抑制非法 tick；算法不得自行读取 ROS clock 或硬件时钟。`reset()`
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
| `connected` | `bool` | adapter 当前有通信连接证据 |
| `zero_generation` | `int` | 当前 IMU 零点世代，非负 |

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

`windarmor_interfaces/MotorFeedback.msg` 是未来 ROS adapter 的传输契约。ROS
message 不能表达 Python `None`，因此 position、velocity、torque、temperature、
device mode 和 fault flags 都有对应的 `*_valid` presence flag；消费者在 flag 为
false 时必须忽略该数值字段。`has_feedback` 表示整条消息是否携带反馈，不能因
ROS 数值字段默认是零就推断真实反馈为零。`MotorFeedbackArray.msg` 用 stamp、
sequence 和完整 motor 数组表达同一 snapshot。本任务只生成消息类型，尚无真实
节点发布该消息。

### FanSystemState

每个 `FanChannelState` 包含：

- `applied_command: float | None`：经 adapter 表达的无量纲实际应用命令；
- `output_known: bool`：是否有依据认为应用命令已知。

`output_known=False` 时 `applied_command` 必须为 `None`；已知值必须在
`[0.0, 1.0]`。该值不是 RPM 或 thrust。`FanSystemState` 还包含 `enabled` 和
既有状态机的 `control_state` 字符串。

### SystemState

| 字段 | 语义 |
|---|---|
| `command_authority` | `NONE/MANUAL/LEGACY_AUTO/FLIGHT_CONTROL` |
| `authority_generation` | 当前授权世代；旧世代命令不得接受 |
| `e_stop_active` | 系统急停是否有效 |
| `motor_control_mode` | 既有公开电机模式，不被 authority 替代 |
| `fan_control_state` | 既有风扇管理器状态 |
| `flight_control_active` | runtime 是否处于 Flight Control 活动状态 |
| `actuation_allowed` | 上游安全/authority 是否允许普通输出 |
| `required_inputs_fresh` | 本 tick 所需输入是否全部新鲜 |

`CommandAuthority` 与既有 motor/fan 状态机正交。即使 authority 是
`FLIGHT_CONTROL`，E-STOP、ERROR、disabled、watchdog 或 safety layer 仍可拒绝
命令。

## None、valid、fresh 与 healthy

- `None`：真实物理值从未获得、当前未知或不能由现有来源验证；
- `valid`：当前内容通过数据结构、有限值和协议范围等校验；
- `fresh`：合法内容还满足 runtime 配置的新鲜度条件；
- `healthy`：合法且新鲜，并且 adapter/既有安全层未发现该设备健康故障。

四者不是同义词。连接存在不保证已有样本，合法旧样本不等于新鲜，温度回落或
收到正常帧也不能自行清除既有锁存 ERROR。算法应在输入不满足其要求时返回
safe-stop request，不能用零填充 unknown。

## FlightCommand

```python
@dataclass(frozen=True)
class FanCommand:
    left: float
    right: float


@dataclass(frozen=True)
class FlightCommand:
    motor_positions_rad: Mapping[str, float]
    fan_commands: FanCommand
    request_safe_stop: bool = False
```

风扇命令是无量纲闭区间 `[0.0, 1.0]`：`0.0` 是停止请求，`1.0` 是 Flight
API 允许的最大归一化请求。PWM 微秒映射、起转值和实际上限不属于算法层。

正常 tick 必须包含配置要求的全部电机键。缺少一个键不能表示“保持旧目标”，
多一个未知键也不能被忽略。NaN、Inf、越界风扇值和非有限电机目标全部明确
拒绝，不做静默 clamp；硬件软限位和位置推进仍属于后续 adapter 与现有安全层。

`FlightCommand.safe_stop(complete_motor_frame)` 设置双风扇为零并置
`request_safe_stop=True`。完整电机 frame 只维持 API 结构一致，safe-stop flag
要求未来 runtime 放弃普通 flight output 并进入既有安全停止路径；它本身不
发布消息、不操作硬件、不触发 E-STOP，也不能恢复 ERROR。

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
可执行的值。

## Fake state 示例

```python
from windarmor_flight_control.algorithms import NeutralExampleController
from windarmor_flight_control.testing import make_fake_flight_state


motor_names = ("axis_a", "axis_b", "axis_c", "axis_d")
state = make_fake_flight_state(motor_names)
controller = NeutralExampleController({name: 0.0 for name in motor_names})

controller.reset()
command = controller.update(state, dt=0.01)
```

`make_fake_flight_state` 只构造内存数据；其中数值明确是测试数据，不表示实机
反馈或已确认的机械中位。要测试 unknown feedback：

```python
state = make_fake_flight_state(motor_names, with_feedback=False)
assert state.motors["axis_a"].position_rad is None
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

算法与当前 package 没有以下能力：

- 直接访问 CyberGear、CAN、串口、GPIO、PWM 或电调；
- 发布 actuator topic 或调用硬件 service；
- 清除 ERROR 或 E-STOP；
- enable/disable hardware 或 set zero；
- 修改 command authority；
- 绕过现有电机/风扇状态机、软限位、看门狗或安全退出；
- 在 transport 恢复后自动恢复 MANUAL/AUTO/HOME 或重发旧目标。

v0.4.0 foundation 不包含真实 Flight Runtime、状态 adapter、authority service、
generation 执行校验、PWM 映射或 actuator dispatch。这些能力只有在后续任务中
接入既有安全路径后才能存在。
