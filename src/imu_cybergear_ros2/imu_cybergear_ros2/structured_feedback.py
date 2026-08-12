"""Pure construction of read-only structured motor feedback snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Protocol, Sequence


class MotorChannelLike(Protocol):
    name: str
    motor_id: int


class MotorStatusLike(Protocol):
    position_rad: float
    speed_rad_s: float
    torque_nm: float
    temperature: float
    mode: int
    fault_flags: int


@dataclass(frozen=True)
class StructuredMotorFeedback:
    logical_name: str
    can_id: int
    has_feedback: bool
    position_rad: float | None
    velocity_rad_s: float | None
    torque_nm: float | None
    temperature_c: float | None
    device_mode: int | None
    fault_flags: int | None
    feedback_age_sec: float | None
    valid: bool
    fresh: bool
    healthy: bool


def build_structured_feedback(
    channels: Sequence[MotorChannelLike],
    feedback_by_id: Mapping[int, MotorStatusLike],
    received_at_by_id: Mapping[int, float],
    *,
    now: float,
    freshness_sec: float,
    critical_temperature_c: float,
    safety_fault_active: bool | None,
) -> tuple[StructuredMotorFeedback, ...]:
    """Copy one complete configured snapshot without driver interaction."""

    if not math.isfinite(now) or now < 0.0:
        raise ValueError("structured feedback now must be finite and non-negative")
    if not math.isfinite(freshness_sec) or freshness_sec <= 0.0:
        raise ValueError("structured feedback freshness must be finite and positive")
    if not math.isfinite(critical_temperature_c):
        raise ValueError("critical motor temperature must be finite")

    snapshot: list[StructuredMotorFeedback] = []
    for channel in channels:
        status = feedback_by_id.get(channel.motor_id)
        received_at = received_at_by_id.get(channel.motor_id)
        if status is None or received_at is None:
            snapshot.append(
                StructuredMotorFeedback(
                    logical_name=channel.name,
                    can_id=channel.motor_id,
                    has_feedback=False,
                    position_rad=None,
                    velocity_rad_s=None,
                    torque_nm=None,
                    temperature_c=None,
                    device_mode=None,
                    fault_flags=None,
                    feedback_age_sec=None,
                    valid=False,
                    fresh=False,
                    healthy=False,
                )
            )
            continue

        age = max(0.0, now - float(received_at))
        fresh = age <= freshness_sec
        fault_flags = int(status.fault_flags)
        snapshot.append(
            StructuredMotorFeedback(
                logical_name=channel.name,
                can_id=channel.motor_id,
                has_feedback=True,
                position_rad=float(status.position_rad),
                velocity_rad_s=float(status.speed_rad_s),
                torque_nm=float(status.torque_nm),
                temperature_c=float(status.temperature),
                device_mode=int(status.mode),
                fault_flags=fault_flags,
                feedback_age_sec=age,
                valid=True,
                fresh=fresh,
                healthy=(
                    fresh
                    and safety_fault_active is False
                    and fault_flags == 0
                    and float(status.temperature) < critical_temperature_c
                ),
            )
        )
    return tuple(snapshot)
