"""Immutable values crossing the pure flight-algorithm boundary."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .authority import CommandAuthority


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class Vector3:
    """Three-dimensional SI vector; component units come from its field use."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Quaternion:
    """Unitless orientation quaternion in x, y, z, w order."""

    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class ImuState:
    """IMU snapshot. None represents an unknown physical measurement."""

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
    connected: bool
    zero_generation: int


@dataclass(frozen=True)
class MotorState:
    """Logical motor state without exposing a transport or physical CAN identity."""

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
    """Normalized applied fan output, if the runtime can verify it."""

    applied_command: float | None
    output_known: bool


@dataclass(frozen=True)
class FanSystemState:
    left: FanChannelState
    right: FanChannelState
    enabled: bool
    control_state: str


@dataclass(frozen=True)
class SystemState:
    command_authority: CommandAuthority
    authority_generation: int
    e_stop_active: bool
    motor_control_mode: str
    fan_control_state: str
    flight_control_active: bool
    actuation_allowed: bool
    required_inputs_fresh: bool


@dataclass(frozen=True)
class FlightState:
    """One immutable, coherent input snapshot for an algorithm tick."""

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
    """Dimensionless fan request; each value must be within [0.0, 1.0]."""

    left: float
    right: float


@dataclass(frozen=True)
class FlightCommand:
    """Complete logical motor targets and normalized fan requests for one tick."""

    motor_positions_rad: Mapping[str, float]
    fan_commands: FanCommand
    request_safe_stop: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "motor_positions_rad",
            _freeze_mapping(self.motor_positions_rad),
        )

    @classmethod
    def safe_stop(
        cls, motor_positions_rad: Mapping[str, float]
    ) -> "FlightCommand":
        """Request relinquishing control while retaining a complete target frame."""

        return cls(
            motor_positions_rad=motor_positions_rad,
            fan_commands=FanCommand(left=0.0, right=0.0),
            request_safe_stop=True,
        )
