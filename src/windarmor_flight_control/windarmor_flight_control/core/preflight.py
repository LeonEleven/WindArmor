"""Pure, explainable preflight evaluation for authority preparation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import FlightState


class PreflightReason(str, Enum):
    READY = "ready"
    CONTROLLER_UNAVAILABLE = "controller_unavailable"
    CONTROLLER_INHIBITED = "controller_inhibited"
    MONOTONIC_INVALID = "monotonic_invalid"
    AUTHORITY_ATTEMPT_CONFLICT = "authority_attempt_conflict"
    REQUIRED_INPUTS_STALE = "required_inputs_stale"
    IMU_INVALID = "imu_invalid"
    IMU_STALE = "imu_stale"
    MOTOR_INVALID = "motor_invalid"
    MOTOR_STALE = "motor_stale"
    MOTOR_UNHEALTHY = "motor_unhealthy"
    MOTOR_SAFETY_UNOBSERVED = "motor_safety_unobserved"
    MOTOR_SAFETY_STALE = "motor_safety_stale"
    FAN_SAFETY_UNOBSERVED = "fan_safety_unobserved"
    FAN_SAFETY_STALE = "fan_safety_stale"
    GLOBAL_ESTOP_UNKNOWN = "global_estop_unknown"
    GLOBAL_ESTOP_ACTIVE = "global_estop_active"
    MOTOR_NODE_INACTIVE = "motor_node_inactive"
    MOTOR_ERROR_LATCHED = "motor_error_latched"
    MOTOR_FEEDBACK_SAFETY_FAULT = "motor_feedback_safety_fault_latched"
    MOTOR_MODE_NOT_MANUAL = "motor_mode_not_manual"
    FAN_ESTOP_LATCHED = "fan_estop_latched"
    FAN_ENABLED_UNKNOWN = "fan_enabled_unknown"
    FAN_DISABLED = "fan_disabled"
    FAN_LEGACY_AUTO_ACTIVE = "fan_legacy_auto_active"
    FAN_MANUAL_ARMED = "fan_manual_armed"
    FAN_NOT_PASSIVE = "fan_not_passive"


@dataclass(frozen=True)
class MotorSafetyReadback:
    node_active: bool
    controller_state: str
    public_control_mode: str
    e_stop_latched: bool
    error_latched: bool
    feedback_safety_fault_latched: bool


@dataclass(frozen=True)
class FanSafetyReadback:
    e_stop_latched: bool
    control_state: str
    enabled_observed: bool
    enabled: bool
    manual_armed: bool
    legacy_auto_requested: bool
    legacy_auto_active: bool
    passive_for_takeover: bool


@dataclass(frozen=True)
class PreflightContext:
    state: FlightState
    motor_safety: MotorSafetyReadback | None
    fan_safety: FanSafetyReadback | None
    motor_safety_fresh: bool
    fan_safety_fresh: bool
    controller_loaded: bool
    controller_inhibited: bool
    monotonic_valid: bool
    no_conflicting_attempt: bool


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    reason: PreflightReason


def evaluate_preflight(context: PreflightContext) -> PreflightResult:
    """Return the first stable blocker in safety-first deterministic order."""

    state = context.state
    checks = [
        (context.controller_loaded, PreflightReason.CONTROLLER_UNAVAILABLE),
        (not context.controller_inhibited, PreflightReason.CONTROLLER_INHIBITED),
        (context.monotonic_valid, PreflightReason.MONOTONIC_INVALID),
        (context.no_conflicting_attempt, PreflightReason.AUTHORITY_ATTEMPT_CONFLICT),
        (context.motor_safety is not None, PreflightReason.MOTOR_SAFETY_UNOBSERVED),
        (context.motor_safety_fresh, PreflightReason.MOTOR_SAFETY_STALE),
        (context.fan_safety is not None, PreflightReason.FAN_SAFETY_UNOBSERVED),
        (context.fan_safety_fresh, PreflightReason.FAN_SAFETY_STALE),
        (state.system.e_stop_active is not None, PreflightReason.GLOBAL_ESTOP_UNKNOWN),
        (state.system.e_stop_active is False, PreflightReason.GLOBAL_ESTOP_ACTIVE),
    ]
    for passed, reason in checks:
        if not passed:
            return PreflightResult(False, reason)

    motor = context.motor_safety
    fan = context.fan_safety
    assert motor is not None and fan is not None
    owner_checks = [
        (motor.node_active, PreflightReason.MOTOR_NODE_INACTIVE),
        (not motor.error_latched, PreflightReason.MOTOR_ERROR_LATCHED),
        (
            not motor.feedback_safety_fault_latched,
            PreflightReason.MOTOR_FEEDBACK_SAFETY_FAULT,
        ),
        (
            motor.public_control_mode == "MANUAL"
            and state.system.motor_control_mode == "MANUAL",
            PreflightReason.MOTOR_MODE_NOT_MANUAL,
        ),
        (not fan.e_stop_latched, PreflightReason.FAN_ESTOP_LATCHED),
        (fan.enabled_observed, PreflightReason.FAN_ENABLED_UNKNOWN),
        (fan.enabled, PreflightReason.FAN_DISABLED),
        (
            not fan.legacy_auto_requested and not fan.legacy_auto_active,
            PreflightReason.FAN_LEGACY_AUTO_ACTIVE,
        ),
        (not fan.manual_armed, PreflightReason.FAN_MANUAL_ARMED),
        (
            fan.passive_for_takeover
            and state.system.fan_control_state == fan.control_state,
            PreflightReason.FAN_NOT_PASSIVE,
        ),
    ]
    for passed, reason in owner_checks:
        if not passed:
            return PreflightResult(False, reason)
    input_checks = [
        (state.imu.valid, PreflightReason.IMU_INVALID),
        (state.imu.fresh, PreflightReason.IMU_STALE),
        (
            all(motor.valid for motor in state.motors.values()),
            PreflightReason.MOTOR_INVALID,
        ),
        (
            all(motor.fresh for motor in state.motors.values()),
            PreflightReason.MOTOR_STALE,
        ),
        (
            all(motor.healthy for motor in state.motors.values()),
            PreflightReason.MOTOR_UNHEALTHY,
        ),
        (state.system.required_inputs_fresh, PreflightReason.REQUIRED_INPUTS_STALE),
    ]
    for passed, reason in input_checks:
        if not passed:
            return PreflightResult(False, reason)
    return PreflightResult(True, PreflightReason.READY)
