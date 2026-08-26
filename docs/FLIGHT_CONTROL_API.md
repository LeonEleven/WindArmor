# WindArmor 飞控 API

## 阅读对象

本文供算法开发者查阅类型、单位、字段语义、工厂函数（factory）和校验规则（validation）。
第一次编写控制器时，请先阅读[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)；Runtime、
控制权（authority）、控制归属（ownership）、命令时效租约（lease）和回滚（rollback）见
[飞控架构](FLIGHT_CONTROL_ARCHITECTURE.md)。

v0.4.0 飞控栈已完成该版本对应的硬件与功能验证，结果和限制记录在
[v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)。该事实
不表示任意新算法、性能边界或新硬件场景已经验证或获得授权。默认配置仍为
`flight_takeover_enabled=false`。

## 核心契约

算法边界是纯 Python：

```python
class FlightController:
    def reset(self) -> None:
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        ...
```

- 输入是不可变 `FlightState`，输出是新的 `FlightCommand`；
- 普通命令包含全部配置电机键和左右风扇载荷；
- 无法安全计算时返回不含载荷的 `FlightCommand.safe_stop()`；
- 算法不导入 ROS/硬件库，不发布消息、不调用服务，也不管理控制权；
- Runtime 与底层安全机制始终保留最终拒绝权；
- 算法测试使用 fake/synthetic 状态，不构成实机验证。

## FlightController

### `reset()`

```python
def reset(self) -> None:
    ...
```

只清理算法内部状态，例如积分、滤波历史、基线或算法内部模式。Runtime 创建控制器后会
调用它；新的原子控制权会话提交时也会调用 `reset()`，并丢弃交接前的预览。它不能清除
ERROR/E-STOP、启用硬件、设置零点或恢复控制权。

### `update(state, dt)`

```python
def update(self, state: FlightState, dt: float) -> FlightCommand:
    ...
```

`dt` 是相邻控制器周期之间的本地单调时钟时间差，单位秒。算法必须把它作为可变的正有限值
处理，不能假设固定频率，也不应读取 ROS 时钟或硬件时钟。

## 控制器工厂函数

配置使用 `module.path:factory_name`：

```yaml
controller_factory: "windarmor_flight_control.algorithms.flight_controller:create_controller"
```

工厂函数支持以下当前契约：

```python
def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> FlightController:
    ...
```

加载器也兼容只接受 `required_motor_names` 的旧工厂函数。模块导入、属性查找、函数签名
绑定、工厂函数执行失败，或返回对象缺少可调用的 `reset/update` 时，都会抛出
`ControllerLoadError`。工厂函数和算法模块必须保持不导入 ROS/硬件的边界。

当前工厂函数：

- 默认：`algorithms.flight_controller:create_controller`，继续使用无状态 API fixture；
- 新人示例：`algorithms.example_algorithm_controller:create_controller`，非默认、软件优先；
- 验证专用：`algorithms.bounded_verification_controller:create_controller`，仅用于受控的
  版本/硬件验证，不是新算法模板。

## FlightState

`FlightState` 及其嵌套值都是冻结的 dataclass。`motors` 在构造时复制为只读映射，因此算法
不能修改当前状态快照或适配器缓存。

### 顶层字段

| 字段 | Python 类型 | 单位 / 含义 | 是否可为 `None` | 安全使用说明 |
|---|---|---|---|---|
| `timestamp_sec` | `float` | Runtime 内部单调时钟时间，单位秒 | 否 | 只作状态快照时间，不与墙上时钟或 ROS 时间混用 |
| `sequence` | `int` | Runtime 内部非负状态快照序号 | 否 | 只比较同一 Runtime 会话内的顺序 |
| `imu` | `ImuState` | 已配对的 IMU 状态快照 | 否 | 先检查 `valid/fresh` |
| `motors` | `Mapping[str, MotorState]` | 逻辑电机名 → 电机反馈 | 否 | 普通输出使用同一组必要键 |
| `fans` | `FanSystemState` | 已观测的风扇状态 / 输出 | 否 | 未知状态与明确停止分开处理 |
| `system` | `SystemState` | Runtime 安全状态与控制权摘要 | 否 | 分别判断新鲜度和执行器就绪条件 |

### ImuState

| 字段 | 类型 | 单位 / 坐标系 / 符号 | `None` 与有效性 |
|---|---|---|---|
| `orientation` | `Quaternion \| None` | 无量纲 `x/y/z/w`，由适配器归一化 | 未知时为 `None`；有效 IMU 必须存在 |
| `roll_rad` | `float \| None` | rad；原始姿态的欧拉滚转角 | 未知时为 `None` |
| `pitch_rad` | `float \| None` | rad；原始姿态的欧拉俯仰角 | 未知时为 `None` |
| `yaw_rad` | `float \| None` | rad；原始姿态的欧拉偏航角 | 未知时为 `None` |
| `relative_roll_rad` | `float \| None` | rad；轴向修正后的滚转角减去当前零点，并完成归一化 | 有效配对状态必须存在 |
| `relative_pitch_rad` | `float \| None` | rad；轴向修正后的俯仰角减去当前零点，并完成归一化 | 有效配对状态必须存在 |
| `angular_velocity_rad_s` | `Vector3 \| None` | IMU 坐标系中的 rad/s | 有效状态必须存在 |
| `linear_acceleration_m_s2` | `Vector3 \| None` | IMU 坐标系中的 m/s² | 有效状态必须存在 |
| `sample_age_sec` | `float \| None` | 非负的本地样本年龄，单位秒 | `valid/fresh` 时必须存在 |
| `valid` | `bool` | 结构、有限数值、连接和零点代次均有效 | 否 |
| `fresh` | `bool` | 有效且年龄未超过配置阈值 | `True` 要求 `valid=True` |
| `connected` | `bool \| None` | 已观测的 IMU 连接状态 | 未观测时为 `None`，不是 false |
| `zero_generation` | `int \| None` | 已观测的非负 IMU 零点代次 | 未观测时为 `None` |

原始观测与相对观测必须使用相同来源时间戳才能配对。当前没有公开
`relative_yaw_rad`。物理安装为 X+ 前、Y+ 左、Z+ 上；API 正负值沿发布的校正坐标系，
算法不得未经机械审核推断执行器方向。详见[硬件参考](HARDWARE_REFERENCE.md)。

示例：`relative_pitch_rad=0.10` 表示修正后的当前俯仰角相对最新零点为 `+0.10 rad`，
不是 `+0.10°`，也不自动表示某个电机应正转。

### MotorState

| 字段 | 类型 | 单位 / 含义 | `None` 与安全使用说明 |
|---|---|---|---|
| `name` | `str` | 稳定的逻辑名称 | 非空；与映射键相同 |
| `position_rad` | `float \| None` | CyberGear 反馈位置，rad | 没有可验证反馈时为 `None`，不是零 |
| `velocity_rad_s` | `float \| None` | rad/s | 没有可验证反馈时为 `None` |
| `torque_nm` | `float \| None` | N·m | 不得据此推导电流 |
| `temperature_c` | `float \| None` | °C | 没有可验证反馈时为 `None` |
| `device_mode` | `int \| None` | 已验证的协议设备模式 | 是否存在受完整反馈约束 |
| `fault_flags` | `int \| None` | 已验证的无符号固件故障位 | `healthy` 要求为 `0` |
| `feedback_age_sec` | `float \| None` | 非负的本地反馈年龄，单位秒 | `valid/fresh` 时存在 |
| `has_feedback` | `bool` | 是否存在完整反馈帧 | false 时物理字段必须全为 `None` |
| `valid` | `bool` | 完整帧通过结构与协议检查 | 否 |
| `fresh` | `bool` | 有效反馈未超过新鲜度阈值 | `True` 要求 `valid=True` |
| `healthy` | `bool` | 有效、新鲜且通过适配器安全检查 | `True` 要求故障位为零 |

当前逻辑名称和单位：

```text
left_lift    位置（rad）
left_pitch   位置（rad）
right_pitch  位置（rad）
right_lift   位置（rad）
```

这些名称是算法键，不是 CAN ID。普通命令必须包含配置中的完整键集合；保持其他轴时应
显式输出本次基线目标，不能省略键或依赖旧帧。

### 风扇状态

每个 `FanChannelState`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `applied_command` | `float \| None` | 已观测的归一化实际输出，范围 `[0,1]`；不是 RPM 或推力 |
| `output_known` | `bool` | 是否有依据确认实际输出已知 |

`output_known=False` 时 `applied_command` 必须为 `None`；只有已知值才能位于 `[0,1]`。
`FanSystemState.enabled` 和 `control_state` 均可为 `None`，表示尚未观测；它不同于明确的
`enabled=False` 或明确状态。空字符串不是合法的未知值。

### SystemState

| 字段 | 类型 | 含义 / 安全使用说明 |
|---|---|---|
| `command_authority` | `CommandAuthority` | `NONE/MANUAL/LEGACY_AUTO/FLIGHT_CONTROL` |
| `authority_epoch` | `int` | 当前 Flight Runtime 会话标识；没有 Flight 控制权时为 `0` |
| `authority_generation` | `int` | 当前控制权代次；没有 Flight 控制权时为 `0` |
| `e_stop_active` | `bool \| None` | 权威聚合结果；未知时为 `None`，绝不能当作 false |
| `motor_control_mode` | `str \| None` | 已观测的公开电机模式 |
| `fan_control_state` | `str \| None` | 已观测的风扇管理器状态 |
| `flight_control_active` | `bool` | Runtime 控制权状态是否为 ACTIVE |
| `actuation_allowed` | `bool` | Runtime 是否已满足当前命令下发门槛 |
| `required_inputs_fresh` | `bool` | 已配对 IMU 新鲜，且每个配置电机反馈都新鲜 |

`required_inputs_fresh` 表示当前已配对 IMU 数据和全部配置电机反馈是否满足 Runtime 的
新鲜度条件。它有意排除风扇输出/状态、电机和风扇的权威安全回读、E-STOP 是否解除、
控制归属/token 是否就绪以及控制权提交；它不是“整个系统已经可以执行”的总状态。
算法通常可在其为 false 时请求安全停止，但绝不能在其为 true 时自行接触硬件。
`actuation_allowed` 是 Runtime 独立作出的命令下发裁决；底层管理器、E-STOP、ERROR、
看门狗、命令时效租约和软限位仍保留最终否决权。

示例：

```python
if not state.system.required_inputs_fresh:
    return FlightCommand.safe_stop()

# 这仍然只是算法控制意图，算法不得自行向硬件下发命令。
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

### 普通命令

- `request_safe_stop=False`；
- `motor_positions_rad` 包含且只包含全部必要电机键；各值为有限的 rad；
- `fan_commands.left/right` 是 `[0.0,1.0]` 内的有限归一化命令；
- `0.0` 风扇命令表示停止意图；`1.0` 不是 RPM、推力或 PWM 微秒值；
- 校验过程不会静默限幅或补齐缺失键；适配器和底层继续执行软限位与 PWM 映射。

### 安全停止命令

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

safe-stop 与普通载荷互斥；不能携带执行器目标，也不能复用上一帧。它表示算法放弃普通
控制意图，不等于系统 E-STOP、不清除 ERROR，也不恢复旧控制路径。

## 单位与坐标约定

| 物理量 | 单位 / 约定 |
|---|---|
| 角度与电机位置 | rad |
| 角速度 | rad/s |
| 力矩 | N·m |
| 温度 | °C |
| 线加速度 | m/s² |
| 状态快照年龄 / `dt` | 单调时钟秒数 |
| 风扇命令 | 无量纲 `[0,1]` |
| 四元数 | 无量纲 `x,y,z,w` |

不要把角度制、PWM 微秒值、CAN ID、电机方向符号或物理引脚混入算法接口。

## 有效性、新鲜度与 `None`

- `None`：来源尚未观测、当前未知或不能验证；
- `valid`：结构、有限值和来源契约通过；
- `fresh`：有效且年龄在配置阈值内；
- `healthy`：电机有效、新鲜，且适配器/安全检查没有设备健康故障；
- `False`：明确裁决为 false，不是未知状态的替代。

连接不保证已有样本，有效的旧样本不等于新鲜，收到正常帧也不能自动清除已锁存的 ERROR。
算法不能用数值零、空字符串或 false 填充未知状态。

## 校验规则

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

校验函数是无副作用的纯函数，失败时抛出 `FlightValidationError`，不修改输入、不访问硬件、
也不修正非法值。主要拒绝：

- NaN/Inf、负年龄、非法的布尔值/存在性组合；
- `invalid/fresh/healthy` 互相矛盾；
- 未知状态被伪装成已知；
- 电机键缺失或多余；
- 普通载荷缺失；
- 风扇命令超出 `[0,1]`；
- safe-stop 混入执行器载荷；
- 控制权/token/执行许可的跨字段冲突。

## 最小示例

### Fake 单元测试状态

```python
from windarmor_flight_control.algorithms import ExampleAlgorithmController
from windarmor_flight_control.testing import make_fake_flight_state

names = ("left_lift", "left_pitch", "right_pitch", "right_lift")
state = make_fake_flight_state(names)
controller = ExampleAlgorithmController(names)
controller.reset()
command = controller.update(state, 0.02)
```

`make_fake_flight_state()` 中的数值是测试 fixture，不是真实机械中位或硬件安全默认值。

### 定向测试

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_algorithm_controller.py -q
```

### 纯软件 synthetic DRY_RUN

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run
```

该演示通过工厂加载器、fake `FlightState` 和真实校验逻辑生成易读的预览；它保持
`authority=NONE`、`actuation_allowed=false`，不创建 ROS 或硬件对象。

## 进阶参考

- 分步教程：[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)
- Runtime/安全/控制权内部机制：[飞控架构](FLIGHT_CONTROL_ARCHITECTURE.md)
- 物理映射、坐标系和接线：[硬件参考](HARDWARE_REFERENCE.md)
- 特定版本的硬件证据：
  [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)
- 完整历史执行过程与来源：
  [v0.4.0 硬件验证执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)
- 实际行为：`core/`、`algorithms/`、`runtime/`、配置和测试

算法不得直接访问 CyberGear/CAN/串口/GPIO/PWM 或硬件服务/后端，不得清除 ERROR/E-STOP、
启用/停用硬件、设置零点、修改控制权，或绕过管理器、看门狗、软限位和关闭清理。需要这些
机制的维护者应查阅架构文档，而不是扩展算法 API。
