"""跨越纯飞控算法边界传递的不可变状态值。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .authority import CommandAuthority


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class Vector3:
    """三维 SI 向量；各分量单位由具体字段用途决定。"""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Quaternion:
    """按 x、y、z、w 排列的无量纲姿态四元数。"""

    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class ImuState:
    """IMU 状态快照；``None`` 表示未知的物理测量。"""

    orientation: Quaternion | None
    roll_rad: float | None
    pitch_rad: float | None
    yaw_rad: float | None
    relative_roll_rad: float | None
    relative_pitch_rad: float | None
    angular_velocity_rad_s: Vector3 | None
    linear_acceleration_m_s2: Vector3 | None
    sample_age_sec: float | None
    valid: bool
    fresh: bool
    connected: bool | None
    zero_generation: int | None


@dataclass(frozen=True)
class MotorState:
    """不暴露传输层或物理 CAN 标识的逻辑电机状态。"""

    name: str
    position_rad: float | None
    velocity_rad_s: float | None
    torque_nm: float | None
    temperature_c: float | None
    device_mode: int | None
    fault_flags: int | None
    feedback_age_sec: float | None
    has_feedback: bool
    valid: bool
    fresh: bool
    healthy: bool


@dataclass(frozen=True)
class FanChannelState:
    """Runtime 能够验证时给出的归一化风扇实际输出。"""

    applied_command: float | None
    output_known: bool


@dataclass(frozen=True)
class FanSystemState:
    """已观测的底层风扇状态，与请求的 ``FanCommand`` 明确区分。

    过期或未观测值使用 ``None`` 表示未知。只有对应通道的 ``output_known`` 为 true，
    实际应用命令才有意义。
    """

    left: FanChannelState
    right: FanChannelState
    enabled: bool | None
    control_state: str | None


@dataclass(frozen=True)
class SystemState:
    """向算法公开的 Runtime 安全状态与控制权摘要。

    ``required_inputs_fresh`` 覆盖已配对 IMU 样本和每个配置电机反馈样本，不包含风扇
    观测、权威安全回读、控制归属和控制权就绪条件。``actuation_allowed`` 是 Runtime
    对普通命令能否下发作出的独立裁决。可选安全/控制观测使用 ``None`` 表示未知；
    未知绝不能解释为 false、已解除、已停止或健康。
    """

    command_authority: CommandAuthority
    authority_epoch: int
    authority_generation: int
    e_stop_active: bool | None
    motor_control_mode: str | None
    fan_control_state: str | None
    flight_control_active: bool
    actuation_allowed: bool
    required_inputs_fresh: bool


@dataclass(frozen=True)
class FlightState:
    """供一个算法周期使用的一致、不可变输入状态快照。"""

    timestamp_sec: float
    sequence: int
    imu: ImuState
    motors: Mapping[str, MotorState]
    fans: FanSystemState
    system: SystemState

    def __post_init__(self) -> None:
        object.__setattr__(self, "motors", _freeze_mapping(self.motors))


@dataclass(frozen=True)
class FanCommand:
    """无量纲风扇请求；每个值都必须位于 [0.0, 1.0]。"""

    left: float
    right: float


@dataclass(frozen=True)
class FlightCommand:
    """完整普通帧，或不含载荷的 safe-stop 请求。"""

    motor_positions_rad: Mapping[str, float] | None
    fan_commands: FanCommand | None
    request_safe_stop: bool = False

    def __post_init__(self) -> None:
        if self.motor_positions_rad is not None:
            object.__setattr__(
                self,
                "motor_positions_rad",
                _freeze_mapping(self.motor_positions_rad),
            )

    @classmethod
    def safe_stop(cls) -> "FlightCommand":
        """放弃普通控制且不携带执行器目标。"""

        return cls(
            motor_positions_rad=None,
            fan_commands=None,
            request_safe_stop=True,
        )
