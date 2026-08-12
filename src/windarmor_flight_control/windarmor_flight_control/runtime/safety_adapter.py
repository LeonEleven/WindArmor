"""Strict ROS-to-core adapters for authoritative safety readback."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ..core.preflight import FanSafetyReadback, MotorSafetyReadback


@dataclass(frozen=True)
class ReceivedMotorSafety:
    value: MotorSafetyReadback
    sequence: int
    received_at: float


@dataclass(frozen=True)
class ReceivedFanSafety:
    value: FanSafetyReadback
    sequence: int
    received_at: float


def _receive_time(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("safety receive time must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("safety receive time must be finite and non-negative")
    return result


def _sequence(message: Any) -> int:
    value = message.observation_sequence
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("safety observation sequence must be non-negative")
    return value


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
        sequence = _sequence(message)
        if self.motor is not None and sequence <= self.motor.sequence:
            raise ValueError("motor safety sequence must strictly increase")
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
        self.motor = ReceivedMotorSafety(value, sequence, received)
        return value

    def update_fan(self, message: Any, received_at: float) -> FanSafetyReadback:
        received = _receive_time(received_at)
        sequence = _sequence(message)
        if self.fan is not None and sequence <= self.fan.sequence:
            raise ValueError("fan safety sequence must strictly increase")
        state = _text(message.control_state, "fan control_state")
        if state not in {
            "SAFE_STOP",
            "MANUAL_DISARMED",
            "MANUAL_WAITING_FOR_NEUTRAL",
            "MANUAL_WAITING",
            "MANUAL_ACTIVE",
            "AUTO_WAITING",
            "AUTO_ACTIVE",
            "DISABLED",
            "EMERGENCY_STOP",
        }:
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
        if value.passive_for_takeover and (
            value.e_stop_latched
            or value.manual_armed
            or value.legacy_auto_requested
            or state not in {"SAFE_STOP", "MANUAL_DISARMED"}
        ):
            raise ValueError("fan passive predicate conflicts with owner state")
        self.fan = ReceivedFanSafety(value, sequence, received)
        return value

    @staticmethod
    def fresh(received_at: float, now: float, freshness_sec: float) -> bool:
        age = now - received_at
        return math.isfinite(age) and 0.0 <= age <= freshness_sec
