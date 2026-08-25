"""Structured motor feedback conversion and Flight-specific freshness."""

from __future__ import annotations

import math
from typing import Any, Iterable

from ..core.models import MotorState
from .observations import MotorFeedbackObservation


PRESENCE_FIELDS = (
    "position_valid",
    "velocity_valid",
    "torque_valid",
    "temperature_valid",
    "device_mode_valid",
    "fault_flags_valid",
)


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")
    return value


def _unsigned_int(value: object, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} is outside its unsigned range")
    return value


class MotorAdapter:
    """Convert a complete configured feedback frame into read-only motor state.

    Missing feedback and locally stale samples fail closed in the snapshot. This
    adapter observes lower-level state; it does not issue commands or grant authority.
    """

    def __init__(self, required_motor_names: Iterable[str]) -> None:
        self._required_names = tuple(required_motor_names)
        if not self._required_names or any(not name for name in self._required_names):
            raise ValueError("required motor names must be non-empty")
        if len(set(self._required_names)) != len(self._required_names):
            raise ValueError("required motor names must be unique")
        self._latest: dict[str, MotorFeedbackObservation] | None = None

    def update(self, message: Any, received_at: float) -> None:
        received = _finite(received_at, "received_at")
        if received < 0.0:
            raise ValueError("received_at must not be negative")
        entries = tuple(message.motors)
        names = [entry.logical_name for entry in entries]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("motor feedback contains an empty logical_name")
        if len(set(names)) != len(names):
            raise ValueError("motor feedback contains duplicate logical_name")
        expected = set(self._required_names)
        actual = set(names)
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            raise ValueError(
                f"motor feedback key mismatch: missing={missing}, unknown={unknown}"
            )
        can_ids = [
            _unsigned_int(entry.can_id, "can_id", 0xFFFFFFFF)
            for entry in entries
        ]
        if any(can_id <= 0 for can_id in can_ids) or len(set(can_ids)) != len(can_ids):
            raise ValueError("motor feedback contains invalid or duplicate CAN ID")

        converted: dict[str, MotorFeedbackObservation] = {}
        for entry in entries:
            has_feedback = _bool(entry.has_feedback, "has_feedback")
            presence = tuple(
                _bool(getattr(entry, field), field) for field in PRESENCE_FIELDS
            )
            valid = _bool(entry.valid, "valid")
            publisher_fresh = _bool(entry.fresh, "fresh")
            publisher_healthy = _bool(entry.healthy, "healthy")
            if not has_feedback:
                if any(presence) or valid or publisher_fresh or publisher_healthy:
                    raise ValueError(
                        f"{entry.logical_name} has feedback flags without feedback"
                    )
                converted[entry.logical_name] = MotorFeedbackObservation(
                    logical_name=entry.logical_name,
                    can_id=_unsigned_int(entry.can_id, "can_id", 0xFFFFFFFF),
                    position_rad=None,
                    velocity_rad_s=None,
                    torque_nm=None,
                    temperature_c=None,
                    device_mode=None,
                    fault_flags=None,
                    publisher_reported_age_sec=None,
                    has_feedback=False,
                    valid=False,
                    publisher_fresh=False,
                    publisher_healthy=False,
                    received_at=received,
                )
                continue
            if not all(presence):
                raise ValueError(
                    f"{entry.logical_name} has incomplete presence flags"
                )
            values = {
                "position_rad": _finite(entry.position_rad, "position_rad"),
                "velocity_rad_s": _finite(entry.velocity_rad_s, "velocity_rad_s"),
                "torque_nm": _finite(entry.torque_nm, "torque_nm"),
                "temperature_c": _finite(entry.temperature_c, "temperature_c"),
            }
            age = _finite(entry.feedback_age_sec, "feedback_age_sec")
            if age < 0.0:
                raise ValueError("feedback_age_sec must not be negative")
            mode = _unsigned_int(entry.device_mode, "device_mode", 0xFF)
            flags = _unsigned_int(entry.fault_flags, "fault_flags", 0xFFFFFFFF)
            if publisher_fresh and not valid:
                raise ValueError("publisher fresh requires valid")
            if publisher_healthy and (not valid or not publisher_fresh or flags != 0):
                raise ValueError("publisher healthy conflicts with validity or fault flags")
            converted[entry.logical_name] = MotorFeedbackObservation(
                logical_name=entry.logical_name,
                can_id=_unsigned_int(entry.can_id, "can_id", 0xFFFFFFFF),
                device_mode=mode,
                fault_flags=flags,
                publisher_reported_age_sec=age,
                has_feedback=True,
                valid=valid,
                publisher_fresh=publisher_fresh,
                publisher_healthy=publisher_healthy,
                received_at=received,
                **values,
            )
        self._latest = converted

    def snapshot(self, *, now: float, freshness_sec: float) -> dict[str, MotorState]:
        current = _finite(now, "now")
        if current < 0.0 or not math.isfinite(freshness_sec) or freshness_sec <= 0.0:
            raise ValueError("motor snapshot timing must be finite and positive")
        observations = self._latest or {}
        result: dict[str, MotorState] = {}
        for name in self._required_names:
            item = observations.get(name)
            if item is None or not item.has_feedback:
                result[name] = MotorState(
                    name=name,
                    position_rad=None,
                    velocity_rad_s=None,
                    torque_nm=None,
                    temperature_c=None,
                    device_mode=None,
                    fault_flags=None,
                    feedback_age_sec=None,
                    has_feedback=False,
                    valid=False,
                    fresh=False,
                    healthy=False,
                )
                continue
            age = item.publisher_reported_age_sec + max(
                0.0, current - item.received_at
            )
            fresh = item.valid and age <= freshness_sec
            result[name] = MotorState(
                name=name,
                position_rad=item.position_rad,
                velocity_rad_s=item.velocity_rad_s,
                torque_nm=item.torque_nm,
                temperature_c=item.temperature_c,
                device_mode=item.device_mode,
                fault_flags=item.fault_flags,
                feedback_age_sec=age,
                has_feedback=True,
                valid=item.valid,
                fresh=fresh,
                healthy=(
                    item.valid
                    and fresh
                    and item.publisher_healthy
                    and item.fault_flags == 0
                ),
            )
        return result
