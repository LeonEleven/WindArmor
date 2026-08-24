# WindArmor Flight Control API

## Audience

本文是算法开发者查阅类型、单位、字段语义、factory 和 validation 的 reference。第一次写
controller 请先按 [Algorithm Developer Guide](ALGORITHM_DEVELOPER_GUIDE.md) 操作；Runtime、
authority、ownership、lease 和 rollback 见
[Flight Control Architecture](FLIGHT_CONTROL_ARCHITECTURE.md)。

v0.4.0 Flight control stack 已完成该 release 对应的 hardware/functional verification，结果和
限制记录在 [v0.4.0 Hardware Verification Plan](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)。该事实
不表示任意新算法、性能边界或新硬件场景已经验证或获得授权。默认配置仍为
`flight_takeover_enabled=false`。

## Quick contract

算法边界是纯 Python：

```python
class FlightController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

- 输入是不可变 `FlightState`，输出是新的 `FlightCommand`；
- normal command 包含全部配置 motor keys 和左右 fan payload；
- 无法安全计算时返回 payload-free `FlightCommand.safe_stop()`；
- 算法不 import ROS/hardware library，不 publish/call service，不管理 authority；
- Runtime 与 lower-level safety 始终保留最终拒绝权；
- 算法测试使用 fake/synthetic state，不构成实机验证。

## FlightController

### `reset()`

```python
def reset(self) -> None:
    ...
```

只清理 algorithm-local state，例如积分、滤波历史、baseline 或算法内部 mode。Runtime 创建
controller 后调用它；新的 atomic authority session 提交时也会 reset，并丢弃 handoff 前的
preview。它不能清除 ERROR/E-STOP、enable hardware、set zero 或恢复 authority。

### `update(state, dt)`

```python
def update(self, state: FlightState, dt: float) -> FlightCommand:
    ...
```

`dt` 是相邻 controller tick 的本地 monotonic 时间差，单位秒。它必须按可变的正有限值处理，
不能假设固定频率，也不应在算法中读取 ROS clock 或 hardware clock。

## Controller factory

配置使用 `module.path:factory_name`：

```yaml
controller_factory: "windarmor_flight_control.algorithms.flight_controller:create_controller"
```

factory 支持以下 current contract：

```python
def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> FlightController:
    ...
```

loader 也兼容只接受 `required_motor_names` 的旧 factory。module import、attribute lookup、
signature binding、factory execution 或返回对象缺少 callable `reset/update` 时抛出
`ControllerLoadError`。factory 和算法模块必须保持 no-ROS/no-hardware import boundary。

当前 factory：

- default：`algorithms.flight_controller:create_controller`，继续使用 stateless API fixture；
- newcomer：`algorithms.example_algorithm_controller:create_controller`，non-default、
  software-first；
- verification：`algorithms.bounded_verification_controller:create_controller`，仅用于受控
  release/hardware verification，不是新算法模板。

## FlightState

`FlightState` 及嵌套值是 frozen dataclass。`motors` 在构造时复制为只读 mapping，因此算法
不能修改当前 snapshot 或 adapter cache。

### Top-level fields

| Field | Python type | Unit / meaning | `None`? | Safe usage |
|---|---|---|---|---|
| `timestamp_sec` | `float` | Runtime-local monotonic seconds | No | 只作 snapshot 时间，不与 wall/ROS time 混用 |
| `sequence` | `int` | Runtime-local non-negative snapshot sequence | No | 只比较同一 Runtime session 内顺序 |
| `imu` | `ImuState` | paired IMU snapshot | No | 先检查 `valid/fresh` |
| `motors` | `Mapping[str, MotorState]` | logical motor → feedback | No | normal output 使用同一 required key set |
| `fans` | `FanSystemState` | observed fan state/output | No | unknown 与明确 stopped 分开 |
| `system` | `SystemState` | Runtime safety/authority summary | No | freshness 与 actuation readiness 分开判断 |

### ImuState

| Field | Type | Unit / frame / sign | `None` and validity |
|---|---|---|---|
| `orientation` | `Quaternion \| None` | unitless `x/y/z/w`, normalized by adapter | unknown 时 `None`; valid IMU 必须存在 |
| `roll_rad` | `float \| None` | rad; raw orientation Euler roll | unknown 时 `None` |
| `pitch_rad` | `float \| None` | rad; raw orientation Euler pitch | unknown 时 `None` |
| `yaw_rad` | `float \| None` | rad; raw orientation Euler yaw | unknown 时 `None` |
| `relative_roll_rad` | `float \| None` | rad; axis-corrected roll minus current zero reference, normalized | valid paired state 必须存在 |
| `relative_pitch_rad` | `float \| None` | rad; axis-corrected pitch minus current zero reference, normalized | valid paired state 必须存在 |
| `angular_velocity_rad_s` | `Vector3 \| None` | rad/s in IMU frame | valid state 必须存在 |
| `linear_acceleration_m_s2` | `Vector3 \| None` | m/s² in IMU frame | valid state 必须存在 |
| `sample_age_sec` | `float \| None` | non-negative local age, seconds | valid/fresh 时必须存在 |
| `valid` | `bool` | structure, finite values, connection and zero generation valid | No |
| `fresh` | `bool` | valid and age within configured threshold | `True` requires `valid=True` |
| `connected` | `bool \| None` | observed IMU connection | unobserved is `None`, not false |
| `zero_generation` | `int \| None` | observed non-negative IMU-zero generation | unobserved is `None` |

raw 与 relative observation 必须使用相同 source stamp 才能配对。当前没有公开
`relative_yaw_rad`。物理安装为 X+ 前、Y+ 左、Z+ 上；API 正负值沿发布的 corrected frame，
算法不得未经机械审核推断 actuator 方向。详见 [Hardware Reference](HARDWARE_REFERENCE.md)。

示例：`relative_pitch_rad=0.10` 表示当前 corrected pitch 相对最新 zero reference 为
`+0.10 rad`，不是 `+0.10°`，也不自动表示某个 motor 应正转。

### MotorState

| Field | Type | Unit / meaning | `None` and safe usage |
|---|---|---|---|
| `name` | `str` | stable logical name | non-empty; 与 mapping key 相同 |
| `position_rad` | `float \| None` | CyberGear feedback position, rad | no verified feedback 时 `None`，不是零 |
| `velocity_rad_s` | `float \| None` | rad/s | no verified feedback 时 `None` |
| `torque_nm` | `float \| None` | N·m | 不得推导 current |
| `temperature_c` | `float \| None` | °C | no verified feedback 时 `None` |
| `device_mode` | `int \| None` | verified protocol device mode | presence 受完整 feedback 约束 |
| `fault_flags` | `int \| None` | verified unsigned firmware fault bits | healthy 要求为 `0` |
| `feedback_age_sec` | `float \| None` | non-negative local age, seconds | valid/fresh 时存在 |
| `has_feedback` | `bool` | complete feedback frame presence | false 时物理字段必须全为 `None` |
| `valid` | `bool` | complete frame passes structural/protocol checks | No |
| `fresh` | `bool` | valid feedback within threshold | `True` requires valid |
| `healthy` | `bool` | valid + fresh + adapter safety checks | `True` requires zero fault flags |

Current logical names and units:

```text
left_lift    position in rad
left_pitch   position in rad
right_pitch  position in rad
right_lift   position in rad
```

这些名称是算法 key，不是 CAN ID。normal command 必须包含配置中的完整 key set；保持其他轴
应显式输出其本次 baseline target，不能省略 key 或依赖旧 frame。

### Fan state

每个 `FanChannelState`：

| Field | Type | Meaning |
|---|---|---|
| `applied_command` | `float \| None` | observed normalized applied output in `[0,1]`; not RPM/thrust |
| `output_known` | `bool` | 是否有依据认为 applied output 已知 |

`output_known=False` 时 `applied_command` 必须为 `None`；known value 才能是 `[0,1]`。
`FanSystemState.enabled` 和 `control_state` 均可为 `None`，表示尚未观测；它不同于明确的
`enabled=False` 或明确 state。空字符串不是合法 unknown。

### SystemState

| Field | Type | Meaning / safe usage |
|---|---|---|
| `command_authority` | `CommandAuthority` | `NONE/MANUAL/LEGACY_AUTO/FLIGHT_CONTROL` |
| `authority_epoch` | `int` | current Flight Runtime session identity; no Flight authority 时 `0` |
| `authority_generation` | `int` | current authority generation; no Flight authority 时 `0` |
| `e_stop_active` | `bool \| None` | authoritative aggregate; unknown is `None`, never treat as false |
| `motor_control_mode` | `str \| None` | observed public motor mode |
| `fan_control_state` | `str \| None` | observed fan manager state |
| `flight_control_active` | `bool` | Runtime authority state is active |
| `actuation_allowed` | `bool` | Runtime has satisfied current dispatch gate |
| `required_inputs_fresh` | `bool` | paired IMU fresh **and** every configured motor feedback fresh |

`required_inputs_fresh` deliberately excludes fan output/state, motor/fan authoritative safety readback,
E-STOP clearance, ownership/token readiness and authority commit. It is an input-freshness summary, not
“the whole system is ready.” An algorithm commonly uses false as a reason to safe-stop, but must not use
true as permission to touch hardware. `actuation_allowed` is the separate Runtime dispatch decision;
lower-level managers, E-STOP, ERROR, watchdogs, leases and soft limits still retain final veto.

Examples:

```python
if not state.system.required_inputs_fresh:
    return FlightCommand.safe_stop()

# This is still only an algorithm intent. Do not dispatch hardware yourself.
command_is_preview = not state.system.actuation_allowed
```

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

### Normal command

- `request_safe_stop=False`；
- `motor_positions_rad` 包含且只包含全部 required motor keys；values 是有限 rad；
- `fan_commands.left/right` 是有限 `[0.0,1.0]` normalized command；
- `0.0` fan command 是 stop intent；`1.0` 不是 RPM、thrust 或 PWM microseconds；
- validation 不 silent clamp、不补缺失 key；adapter/lower layer 继续执行软限位和 PWM mapping。

### Safe-stop command

```python
FlightCommand.safe_stop()
```

等价于：

```python
FlightCommand(
    motor_positions_rad=None,
    fan_commands=None,
    request_safe_stop=True,
)
```

safe-stop 与 normal payload 互斥；不能携带 actuator targets，也不能复用上一帧。它是算法放弃
普通控制的意图，不等于 system E-STOP、不清除 ERROR，也不恢复 legacy control。

## Units and coordinate conventions

| Quantity | Unit / convention |
|---|---|
| angles and motor positions | rad |
| angular velocity | rad/s |
| torque | N·m |
| temperature | °C |
| linear acceleration | m/s² |
| snapshot age / `dt` | monotonic seconds |
| fan command | dimensionless `[0,1]` |
| quaternion | unitless `x,y,z,w` |

不要把 degrees、PWM microseconds、CAN ID、motor sign 或 physical pin 混入算法 interface。

## Validity, freshness and `None`

- `None`：来源尚未观测、当前 unknown 或不能验证；
- `valid`：结构、有限值和来源契约通过；
- `fresh`：valid 且年龄在 configured threshold 内；
- `healthy`：motor valid/fresh 且 adapter/safety checks 没有设备健康故障；
- `False`：明确裁决为 false，不是 unknown 的替代。

连接不保证已有样本，valid old sample 不等于 fresh，收到正常 frame 也不能自动清除 latched
ERROR。算法不能用数值零、空字符串或 false 填充 unknown。

## Validation rules

```python
from windarmor_flight_control.core.validation import (
    FlightValidationError,
    validate_flight_command,
    validate_flight_state,
)

required = ("left_lift", "left_pitch", "right_pitch", "right_lift")
validate_flight_state(state, required)
command = controller.update(state, dt=0.02)
validate_flight_command(command, required)
```

validation 是 side-effect-free pure function，失败时抛出 `FlightValidationError`，不修改输入、
不访问硬件、不修正非法值。主要拒绝：

- NaN/Inf、负 age、非法 boolean/presence 组合；
- invalid/fresh/healthy 矛盾；
- unknown 被伪装成已知；
- motor key 缺失或多余；
- normal payload 缺失；
- fan command 超出 `[0,1]`；
- safe-stop 混入 actuator payload；
- authority/token/actuation cross-field 冲突。

## Minimal examples

### Fake unit state

```python
from windarmor_flight_control.algorithms import ExampleAlgorithmController
from windarmor_flight_control.testing import make_fake_flight_state

names = ("left_lift", "left_pitch", "right_pitch", "right_lift")
state = make_fake_flight_state(names)
controller = ExampleAlgorithmController(names)
controller.reset()
command = controller.update(state, 0.02)
```

`make_fake_flight_state()` 的数字是 test fixture，不是真实机械中位或硬件 safety default。

### Targeted tests

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_algorithm_controller.py -q
```

### Software-only synthetic DRY_RUN

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run
```

该 demo 用 factory loader、fake `FlightState` 和真实 validation 生成 human-readable preview；
它保持 `authority=NONE`、`actuation_allowed=false`，不创建 ROS/hardware objects。

## Advanced references

- step-by-step tutorial：[Algorithm Developer Guide](ALGORITHM_DEVELOPER_GUIDE.md)
- Runtime/safety/authority internals：[Flight Control Architecture](FLIGHT_CONTROL_ARCHITECTURE.md)
- physical mapping/frame/wiring：[Hardware Reference](HARDWARE_REFERENCE.md)
- release-specific hardware evidence：
  [v0.4.0 Hardware Verification Plan](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)
- actual behavior：`core/`、`algorithms/`、`runtime/`、config 和 tests

算法不得直接访问 CyberGear/CAN/serial/GPIO/PWM、hardware service/backend，不得清除
ERROR/E-STOP、enable/disable hardware、set zero、修改 authority 或绕过 manager、watchdog、
soft limit 和 shutdown。需要这些机制的维护者应进入 Architecture，而不是扩展算法 API。
