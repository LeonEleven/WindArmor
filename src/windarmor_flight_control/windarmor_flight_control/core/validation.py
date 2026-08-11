"""Strict, side-effect-free validation for flight API values."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .authority import AuthorityGrant, CommandAuthority
from .models import (
    FanChannelState,
    FanCommand,
    FlightCommand,
    FlightState,
    FanSystemState,
    ImuState,
    MotorState,
    Quaternion,
    SystemState,
    Vector3,
)


class FlightValidationError(ValueError):
    """Raised when an API value violates one or more explicit contracts."""

    def __init__(self, issues: Iterable[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


def _finite(value: object, path: str, issues: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(f"{path} must be a finite number")
    elif not math.isfinite(float(value)):
        issues.append(f"{path} must be finite")


def _optional_finite(value: object | None, path: str, issues: list[str]) -> None:
    if value is not None:
        _finite(value, path, issues)


def _nonnegative_int(value: object, path: str, issues: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(f"{path} must be a non-negative integer")


def _boolean(value: object, path: str, issues: list[str]) -> None:
    if not isinstance(value, bool):
        issues.append(f"{path} must be a bool")


def _optional_boolean(value: object | None, path: str, issues: list[str]) -> None:
    if value is not None:
        _boolean(value, path, issues)


def _optional_nonempty_string(
    value: object | None, path: str, issues: list[str]
) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        issues.append(f"{path} must be None or a non-empty string")


def _validate_vector(value: Vector3, path: str, issues: list[str]) -> None:
    for component in ("x", "y", "z"):
        _finite(getattr(value, component), f"{path}.{component}", issues)


def _validate_quaternion(
    value: Quaternion, path: str, issues: list[str]
) -> None:
    for component in ("x", "y", "z", "w"):
        _finite(getattr(value, component), f"{path}.{component}", issues)


def _validate_imu(imu: ImuState, issues: list[str]) -> None:
    if imu.orientation is not None:
        _validate_quaternion(imu.orientation, "imu.orientation", issues)
    for field in (
        "roll_rad",
        "pitch_rad",
        "yaw_rad",
        "relative_roll_rad",
        "relative_pitch_rad",
        "sample_age_sec",
    ):
        _optional_finite(getattr(imu, field), f"imu.{field}", issues)
    if imu.angular_velocity_rad_s is not None:
        _validate_vector(
            imu.angular_velocity_rad_s, "imu.angular_velocity_rad_s", issues
        )
    if imu.linear_acceleration_m_s2 is not None:
        _validate_vector(
            imu.linear_acceleration_m_s2,
            "imu.linear_acceleration_m_s2",
            issues,
        )
    if imu.sample_age_sec is not None and imu.sample_age_sec < 0.0:
        issues.append("imu.sample_age_sec must not be negative")
    if imu.zero_generation is not None:
        _nonnegative_int(imu.zero_generation, "imu.zero_generation", issues)
    for field in ("valid", "fresh"):
        _boolean(getattr(imu, field), f"imu.{field}", issues)
    _optional_boolean(imu.connected, "imu.connected", issues)
    if imu.fresh and not imu.valid:
        issues.append("imu.fresh requires imu.valid")
    if imu.valid and imu.connected is not True:
        issues.append("imu.valid requires connected to be explicitly true")
    if imu.valid and imu.zero_generation is None:
        issues.append("imu.valid requires an observed zero_generation")
    if (imu.valid or imu.fresh) and imu.sample_age_sec is None:
        issues.append("valid or fresh IMU data requires sample_age_sec")
    imu_measurements = (
        imu.orientation,
        imu.roll_rad,
        imu.pitch_rad,
        imu.yaw_rad,
        imu.relative_roll_rad,
        imu.relative_pitch_rad,
        imu.angular_velocity_rad_s,
        imu.linear_acceleration_m_s2,
    )
    if imu.valid and any(value is None for value in imu_measurements):
        issues.append("imu.valid requires a complete measurement set")


def _validate_motor(motor: MotorState, path: str, issues: list[str]) -> None:
    if not motor.name:
        issues.append(f"{path}.name must not be empty")
    physical_fields = (
        "position_rad",
        "velocity_rad_s",
        "torque_nm",
        "temperature_c",
    )
    for field in physical_fields:
        _optional_finite(getattr(motor, field), f"{path}.{field}", issues)
    _optional_finite(motor.feedback_age_sec, f"{path}.feedback_age_sec", issues)
    if motor.feedback_age_sec is not None and motor.feedback_age_sec < 0.0:
        issues.append(f"{path}.feedback_age_sec must not be negative")
    for field, maximum in (("device_mode", 0xFF), ("fault_flags", 0xFFFFFFFF)):
        value = getattr(motor, field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= maximum
        ):
            issues.append(f"{path}.{field} is outside its unsigned range")
    for field in ("has_feedback", "valid", "fresh", "healthy"):
        _boolean(getattr(motor, field), f"{path}.{field}", issues)

    feedback_values = [
        *(getattr(motor, field) for field in physical_fields),
        motor.device_mode,
        motor.fault_flags,
        motor.feedback_age_sec,
    ]
    if not motor.has_feedback:
        if any(value is not None for value in feedback_values):
            issues.append(f"{path} has values while has_feedback is false")
        if motor.valid or motor.fresh or motor.healthy:
            issues.append(f"{path} cannot be valid, fresh, or healthy without feedback")
    else:
        if motor.feedback_age_sec is None:
            issues.append(f"{path}.has_feedback requires feedback_age_sec")
        if motor.valid and any(value is None for value in feedback_values):
            issues.append(f"{path}.valid requires a complete verified feedback frame")
        if motor.fresh and not motor.valid:
            issues.append(f"{path}.fresh requires valid")
        if motor.healthy and not (motor.valid and motor.fresh):
            issues.append(f"{path}.healthy requires valid and fresh")
        if motor.healthy and motor.fault_flags != 0:
            issues.append(f"{path}.healthy requires zero fault_flags")


def _validate_fan_channel(
    channel: FanChannelState, path: str, issues: list[str]
) -> None:
    _boolean(channel.output_known, f"{path}.output_known", issues)
    _optional_finite(channel.applied_command, f"{path}.applied_command", issues)
    if channel.output_known != (channel.applied_command is not None):
        issues.append(f"{path}.output_known conflicts with applied_command presence")
    if channel.applied_command is not None and not 0.0 <= channel.applied_command <= 1.0:
        issues.append(f"{path}.applied_command must be within [0.0, 1.0]")


def _required_names(required_motor_names: Iterable[str]) -> frozenset[str]:
    names = tuple(required_motor_names)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise FlightValidationError(("required motor names must be non-empty strings",))
    if len(set(names)) != len(names):
        raise FlightValidationError(("required motor names must be unique",))
    return frozenset(names)


def _check_motor_keys(
    actual: Iterable[str], expected: frozenset[str], path: str, issues: list[str]
) -> None:
    actual_set = frozenset(actual)
    missing = sorted(expected - actual_set, key=repr)
    unknown = sorted(actual_set - expected, key=repr)
    if missing:
        issues.append(f"{path} is missing motors: {', '.join(map(str, missing))}")
    if unknown:
        issues.append(f"{path} contains unknown motors: {', '.join(map(str, unknown))}")


def validate_flight_state(
    state: FlightState, required_motor_names: Iterable[str]
) -> None:
    """Reject an inconsistent snapshot without changing it."""

    if not isinstance(state, FlightState):
        raise FlightValidationError(("state must be a FlightState",))
    expected = _required_names(required_motor_names)
    issues: list[str] = []
    _finite(state.timestamp_sec, "timestamp_sec", issues)
    if isinstance(state.timestamp_sec, (int, float)) and state.timestamp_sec < 0.0:
        issues.append("timestamp_sec must not be negative")
    _nonnegative_int(state.sequence, "sequence", issues)
    if not isinstance(state.imu, ImuState):
        issues.append("imu must be an ImuState")
    else:
        _validate_imu(state.imu, issues)
    _check_motor_keys(state.motors.keys(), expected, "motors", issues)
    for name, motor in state.motors.items():
        if not isinstance(name, str) or not name:
            issues.append("motor mapping keys must be non-empty strings")
            continue
        if not isinstance(motor, MotorState):
            issues.append(f"motors[{name!r}] must be a MotorState")
            continue
        _validate_motor(motor, f"motors[{name!r}]", issues)
        if motor.name != name:
            issues.append(f"motors[{name!r}].name must match its mapping key")
    if not isinstance(state.fans, FanSystemState):
        issues.append("fans must be a FanSystemState")
    else:
        if not isinstance(state.fans.left, FanChannelState):
            issues.append("fans.left must be a FanChannelState")
        else:
            _validate_fan_channel(state.fans.left, "fans.left", issues)
        if not isinstance(state.fans.right, FanChannelState):
            issues.append("fans.right must be a FanChannelState")
        else:
            _validate_fan_channel(state.fans.right, "fans.right", issues)
        _optional_boolean(state.fans.enabled, "fans.enabled", issues)
        _optional_nonempty_string(
            state.fans.control_state, "fans.control_state", issues
        )
    if not isinstance(state.system, SystemState):
        issues.append("system must be a SystemState")
    else:
        if not isinstance(state.system.command_authority, CommandAuthority):
            issues.append("system.command_authority must be a CommandAuthority")
        _nonnegative_int(
            state.system.authority_generation, "system.authority_generation", issues
        )
        for field in (
            "flight_control_active",
            "actuation_allowed",
            "required_inputs_fresh",
        ):
            _boolean(getattr(state.system, field), f"system.{field}", issues)
        _optional_boolean(
            state.system.e_stop_active, "system.e_stop_active", issues
        )
        _optional_nonempty_string(
            state.system.motor_control_mode,
            "system.motor_control_mode",
            issues,
        )
        _optional_nonempty_string(
            state.system.fan_control_state,
            "system.fan_control_state",
            issues,
        )
        if isinstance(state.fans, FanSystemState) and (
            state.system.fan_control_state != state.fans.control_state
        ):
            issues.append("system and fan snapshot control states must agree")
        if (
            state.system.flight_control_active is True
            and state.system.command_authority is not CommandAuthority.FLIGHT_CONTROL
        ):
            issues.append("flight_control_active requires FLIGHT_CONTROL authority")
        if state.system.actuation_allowed is True:
            if state.system.e_stop_active is not False:
                issues.append(
                    "actuation requires e_stop_active to be explicitly false"
                )
            if state.system.motor_control_mode is None:
                issues.append("actuation requires an observed motor_control_mode")
            if state.system.fan_control_state is None:
                issues.append("actuation requires an observed fan_control_state")
            if not state.system.required_inputs_fresh:
                issues.append("actuation requires fresh required inputs")
            if not state.system.flight_control_active:
                issues.append("actuation requires flight_control_active")
            if isinstance(state.fans, FanSystemState) and state.fans.enabled is not True:
                issues.append("actuation requires fans.enabled to be explicitly true")
    if issues:
        raise FlightValidationError(issues)


def _validate_fan_command(command: FanCommand, issues: list[str]) -> None:
    for field in ("left", "right"):
        value = getattr(command, field)
        _finite(value, f"fan_commands.{field}", issues)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            if not 0.0 <= value <= 1.0:
                issues.append(f"fan_commands.{field} must be within [0.0, 1.0]")


def validate_flight_command(
    command: FlightCommand, required_motor_names: Iterable[str]
) -> None:
    """Reject an invalid command; never clamp or fill an incomplete frame."""

    if not isinstance(command, FlightCommand):
        raise FlightValidationError(("command must be a FlightCommand",))
    issues: list[str] = []
    _boolean(command.request_safe_stop, "request_safe_stop", issues)
    if command.request_safe_stop is True:
        if command.motor_positions_rad is not None or command.fan_commands is not None:
            issues.append("safe-stop command must not carry actuator payload")
        if issues:
            raise FlightValidationError(issues)
        return

    expected = _required_names(required_motor_names)
    if command.request_safe_stop is not True:
        if command.motor_positions_rad is None:
            issues.append("normal command requires motor_positions_rad")
        else:
            _check_motor_keys(
                command.motor_positions_rad.keys(),
                expected,
                "motor_positions_rad",
                issues,
            )
            for name, value in command.motor_positions_rad.items():
                _finite(value, f"motor_positions_rad[{name!r}]", issues)
        if not isinstance(command.fan_commands, FanCommand):
            issues.append("normal command requires fan_commands")
        else:
            _validate_fan_command(command.fan_commands, issues)
    if issues:
        raise FlightValidationError(issues)


def validate_authority_grant(grant: AuthorityGrant) -> None:
    """Validate generation metadata without changing runtime authority."""

    issues: list[str] = []
    if not isinstance(grant, AuthorityGrant):
        raise FlightValidationError(("grant must be an AuthorityGrant",))
    if not isinstance(grant.authority, CommandAuthority):
        issues.append("authority must be a CommandAuthority")
    _nonnegative_int(grant.generation, "generation", issues)
    _nonnegative_int(grant.sequence, "sequence", issues)
    if issues:
        raise FlightValidationError(issues)
