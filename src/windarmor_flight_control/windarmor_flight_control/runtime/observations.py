"""Immutable intermediate values used by ROS adapters and the aggregator."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.models import Quaternion, Vector3


@dataclass(frozen=True)
class RawImuObservation:
    source_stamp_ns: int
    orientation: Quaternion
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    angular_velocity_rad_s: Vector3
    linear_acceleration_m_s2: Vector3
    received_at: float


@dataclass(frozen=True)
class RelativeAttitudeObservation:
    source_stamp_ns: int
    roll_rad: float
    pitch_rad: float
    received_at: float


@dataclass(frozen=True)
class PairedImuObservation:
    raw: RawImuObservation
    relative: RelativeAttitudeObservation


@dataclass(frozen=True)
class MotorFeedbackObservation:
    logical_name: str
    can_id: int
    position_rad: float | None
    velocity_rad_s: float | None
    torque_nm: float | None
    temperature_c: float | None
    device_mode: int | None
    fault_flags: int | None
    publisher_reported_age_sec: float | None
    has_feedback: bool
    valid: bool
    publisher_fresh: bool
    publisher_healthy: bool
    received_at: float
