"""Strict ROS-to-core adapters for authoritative safety readback."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ..core.preflight import FanSafetyReadback, MotorSafetyReadback


_KNOWN_FAN_CONTROL_STATES = frozenset(
    {
        "SAFE_STOP",
        "MANUAL_DISARMED",
        "MANUAL_WAITING_FOR_NEUTRAL",
        "MANUAL_WAITING",
        "MANUAL_ACTIVE",
        "AUTO_WAITING",
        "AUTO_ACTIVE",
        "FLIGHT_WAITING",
        "FLIGHT_ACTIVE",
        "DISABLED",
        "EMERGENCY_STOP",
    }
)
_FLIGHT_FAN_CONTROL_STATES = frozenset({"FLIGHT_WAITING", "FLIGHT_ACTIVE"})
_PASSIVE_FAN_CONTROL_STATES = frozenset({"SAFE_STOP", "MANUAL_DISARMED"})


@dataclass(frozen=True)
class ReceivedMotorSafety:
    value: MotorSafetyReadback
    source_epoch: int
    sequence: int
    received_at: float


@dataclass(frozen=True)
class ReceivedFanSafety:
    value: FanSafetyReadback
    source_epoch: int
    sequence: int
    received_at: float


def _receive_time(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("safety receive time must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("safety receive time must be finite and non-negative")
    return result


def _positive_uint64(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= (2**64 - 1)
    ):
        raise ValueError(f"{name} must be a positive uint64")
    return value


def _ordering(message: Any) -> tuple[int, int]:
    return (
        _positive_uint64(message.source_epoch, "safety source epoch"),
        _positive_uint64(
            message.observation_sequence,
            "safety observation sequence",
        ),
    )


def _validate_ordering(
    *,
    subsystem: str,
    source_epoch: int,
    sequence: int,
    previous: ReceivedMotorSafety | ReceivedFanSafety | None,
) -> None:
    if previous is None:
        return
    if source_epoch < previous.source_epoch:
        raise ValueError(f"{subsystem} safety source epoch moved backwards")
    if source_epoch == previous.source_epoch and sequence <= previous.sequence:
        raise ValueError(
            f"{subsystem} safety sequence must strictly increase within an epoch"
        )


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{name} must be a string with valid presence")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")
    return value


class SafetyReadbackAdapter:
    def __init__(self) -> None:
        self.motor: ReceivedMotorSafety | None = None
        self.fan: ReceivedFanSafety | None = None

    def update_motor(self, message: Any, received_at: float) -> MotorSafetyReadback:
        received = _receive_time(received_at)
        source_epoch, sequence = _ordering(message)
        _validate_ordering(
            subsystem="motor",
            source_epoch=source_epoch,
            sequence=sequence,
            previous=self.motor,
        )
        controller_state = _text(message.controller_state, "controller_state")
        public_mode = _text(message.public_control_mode, "public_control_mode")
        if controller_state not in {
            "UNINITIALIZED",
            "INITIALIZING",
            "AUTO_RUNNING",
            "MANUAL_RUNNING",
            "EMERGENCY_STOP",
            "ERROR",
            "SHUTTING_DOWN",
        }:
            raise ValueError("unknown motor controller state")
        if public_mode not in {"DISABLED", "MANUAL", "AUTO", "EMERGENCY_STOP", "ERROR"}:
            raise ValueError("unknown public motor mode")
        value = MotorSafetyReadback(
            node_active=_boolean(message.node_active, "node_active"),
            controller_state=controller_state,
            public_control_mode=public_mode,
            e_stop_latched=_boolean(message.e_stop_latched, "e_stop_latched"),
            error_latched=_boolean(message.error_latched, "error_latched"),
            feedback_safety_fault_latched=_boolean(
                message.feedback_safety_fault_latched,
                "feedback_safety_fault_latched",
            ),
        )
        if value.e_stop_latched != (controller_state == "EMERGENCY_STOP"):
            raise ValueError("motor e-stop latch conflicts with controller state")
        if controller_state == "ERROR" and not value.error_latched:
            raise ValueError("motor ERROR must be latched")
        if value.feedback_safety_fault_latched and not value.error_latched:
            raise ValueError("motor feedback safety fault requires error latch")
        self.motor = ReceivedMotorSafety(value, source_epoch, sequence, received)
        return value

    def update_fan(self, message: Any, received_at: float) -> FanSafetyReadback:
        received = _receive_time(received_at)
        source_epoch, sequence = _ordering(message)
        _validate_ordering(
            subsystem="fan",
            source_epoch=source_epoch,
            sequence=sequence,
            previous=self.fan,
        )
        state = _text(message.control_state, "fan control_state")
        if state not in _KNOWN_FAN_CONTROL_STATES:
            raise ValueError("unknown fan control state")
        value = FanSafetyReadback(
            e_stop_latched=_boolean(message.e_stop_latched, "e_stop_latched"),
            control_state=state,
            enabled_observed=_boolean(message.enabled_observed, "enabled_observed"),
            enabled=_boolean(message.enabled, "enabled"),
            manual_armed=_boolean(message.manual_armed, "manual_armed"),
            legacy_auto_requested=_boolean(
                message.legacy_auto_requested, "legacy_auto_requested"
            ),
            legacy_auto_active=_boolean(
                message.legacy_auto_active, "legacy_auto_active"
            ),
            passive_for_takeover=_boolean(
                message.passive_for_takeover, "passive_for_takeover"
            ),
        )
        if not value.enabled_observed and value.enabled:
            raise ValueError("unobserved fan enabled cannot be true")
        if value.e_stop_latched != (state == "EMERGENCY_STOP"):
            raise ValueError("fan e-stop latch conflicts with control state")
        if value.legacy_auto_active and not value.legacy_auto_requested:
            raise ValueError("active legacy fan AUTO requires a request")
        if state in _FLIGHT_FAN_CONTROL_STATES and (
            value.manual_armed or value.legacy_auto_requested
        ):
            raise ValueError("fan Flight state conflicts with legacy owner state")
        if state in _FLIGHT_FAN_CONTROL_STATES and (
            not value.enabled_observed or not value.enabled
        ):
            raise ValueError("fan Flight state requires enabled readback")
        if value.passive_for_takeover and (
            value.e_stop_latched
            or value.manual_armed
            or value.legacy_auto_requested
            or state not in _PASSIVE_FAN_CONTROL_STATES
        ):
            raise ValueError("fan passive predicate conflicts with owner state")
        self.fan = ReceivedFanSafety(value, source_epoch, sequence, received)
        return value

    @staticmethod
    def fresh(received_at: float, now: float, freshness_sec: float) -> bool:
        age = now - received_at
        return math.isfinite(age) and 0.0 <= age <= freshness_sec
