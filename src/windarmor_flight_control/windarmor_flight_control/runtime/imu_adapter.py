"""按精确来源时间戳配对、带状态的 IMU 观测适配器。"""

from __future__ import annotations

import math
from typing import Any

from ..core.models import ImuState, Quaternion, Vector3
from .observations import (
    PairedImuObservation,
    RawImuObservation,
    RelativeAttitudeObservation,
)


EULER_GIMBAL_LOCK_COS_TOLERANCE = 1.0e-9


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _received_at(value: object) -> float:
    result = _finite(value, "received_at")
    if result < 0.0:
        raise ValueError("received_at must not be negative")
    return result


def source_stamp_ns(message: Any) -> int:
    stamp = message.header.stamp
    sec = int(stamp.sec)
    nanosec = int(stamp.nanosec)
    if sec < 0 or not 0 <= nanosec < 1_000_000_000:
        raise ValueError("source stamp is outside its valid range")
    result = sec * 1_000_000_000 + nanosec
    if result <= 0:
        raise ValueError("source stamp must be positive for IMU correlation")
    return result


def normalize_quaternion(quaternion: Quaternion) -> Quaternion:
    """Return a finite unit quaternion without changing its rotation."""

    values = tuple(
        _finite(getattr(quaternion, field), f"orientation.{field}")
        for field in ("x", "y", "z", "w")
    )
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError("orientation quaternion cannot be normalized")
    x, y, z, w = (value / norm for value in values)
    return Quaternion(x=x, y=y, z=z, w=w)


def _normalize_quaternion(message: Any) -> Quaternion:
    return normalize_quaternion(
        Quaternion(
            x=getattr(message.orientation, "x"),
            y=getattr(message.orientation, "y"),
            z=getattr(message.orientation, "z"),
            w=getattr(message.orientation, "w"),
        )
    )


def quaternion_to_euler(quaternion: Quaternion) -> tuple[float, float, float]:
    sinr_cosp = 2.0 * (quaternion.w * quaternion.x + quaternion.y * quaternion.z)
    cosr_cosp = 1.0 - 2.0 * (quaternion.x**2 + quaternion.y**2)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (quaternion.w * quaternion.y - quaternion.z * quaternion.x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)
    siny_cosp = 2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y)
    cosy_cosp = 1.0 - 2.0 * (quaternion.y**2 + quaternion.z**2)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return roll, pitch, yaw


def euler_pitch_rate_from_body_angular_velocity(
    orientation: Quaternion,
    angular_velocity_rad_s: Vector3,
) -> float:
    """Derive Z-Y-X Euler pitch rate from body-frame angular velocity.

    For body rates ``(p, q, r)`` and Euler roll ``phi``, the current convention
    gives ``pitch_dot = cos(phi) * q - sin(phi) * r``.  The Euler representation
    is not differentiable at pitch gimbal lock, so those orientations are
    rejected instead of assigning an ambiguous rate.
    """

    quaternion = normalize_quaternion(orientation)
    body_rates = Vector3(
        x=_finite(angular_velocity_rad_s.x, "angular_velocity.x"),
        y=_finite(angular_velocity_rad_s.y, "angular_velocity.y"),
        z=_finite(angular_velocity_rad_s.z, "angular_velocity.z"),
    )
    roll, pitch, _yaw = quaternion_to_euler(quaternion)
    if abs(math.cos(pitch)) <= EULER_GIMBAL_LOCK_COS_TOLERANCE:
        raise ValueError("Euler pitch rate is undefined at pitch gimbal lock")
    result = math.cos(roll) * body_rates.y - math.sin(roll) * body_rates.z
    if not math.isfinite(result):
        raise ValueError("Euler pitch rate must be finite")
    return result


def corrected_relative_pitch_rate_rad_s(
    orientation: Quaternion,
    angular_velocity_rad_s: Vector3,
    *,
    pitch_axis_sign: float,
) -> float:
    """Return pitch rate in the corrected ``relative_pitch_rad`` direction."""

    if isinstance(pitch_axis_sign, bool) or pitch_axis_sign not in (-1.0, 1.0):
        raise ValueError("pitch_axis_sign must be exactly +1.0 or -1.0")
    return float(pitch_axis_sign) * euler_pitch_rate_from_body_angular_velocity(
        orientation,
        angular_velocity_rad_s,
    )


def _vector(message: Any, field: str, unit_name: str) -> Vector3:
    value = getattr(message, field)
    return Vector3(
        x=_finite(value.x, f"{unit_name}.x"),
        y=_finite(value.y, f"{unit_name}.y"),
        z=_finite(value.z, f"{unit_name}.z"),
    )


class ImuAdapter:
    """缓存原始/相对观测，并提供一致的配对状态。"""

    _PENDING_LIMIT = 8

    def __init__(self, *, pitch_axis_sign: float) -> None:
        if isinstance(pitch_axis_sign, bool) or pitch_axis_sign not in (-1.0, 1.0):
            raise ValueError("pitch_axis_sign must be exactly +1.0 or -1.0")
        self._pitch_axis_sign = float(pitch_axis_sign)
        self._raw: dict[int, RawImuObservation] = {}
        self._relative: dict[int, RelativeAttitudeObservation] = {}
        self._paired: PairedImuObservation | None = None
        self._last_paired_stamp_ns = 0
        self._connected: bool | None = None
        self._zero_generation: int | None = None

    def update_raw(self, message: Any, received_at: float) -> None:
        received = _received_at(received_at)
        orientation = _normalize_quaternion(message)
        roll, pitch, yaw = quaternion_to_euler(orientation)
        angular_velocity = _vector(
            message, "angular_velocity", "angular_velocity"
        )
        relative_pitch_rate = corrected_relative_pitch_rate_rad_s(
            orientation,
            angular_velocity,
            pitch_axis_sign=self._pitch_axis_sign,
        )
        stamp = source_stamp_ns(message)
        if stamp <= self._last_paired_stamp_ns or stamp in self._raw:
            raise ValueError("raw IMU source stamp is duplicate or out of order")
        observation = RawImuObservation(
            source_stamp_ns=stamp,
            orientation=orientation,
            roll_rad=roll,
            pitch_rad=pitch,
            yaw_rad=yaw,
            angular_velocity_rad_s=angular_velocity,
            relative_pitch_rate_rad_s=relative_pitch_rate,
            linear_acceleration_m_s2=_vector(
                message, "linear_acceleration", "linear_acceleration"
            ),
            received_at=received,
        )
        # 完整校验通过的原始帧，才是当前观测链路可用的正面证据。
        self._connected = True
        self._raw[stamp] = observation
        self._try_pair(stamp)
        self._trim_pending()

    def update_relative(self, message: Any, received_at: float) -> None:
        received = _received_at(received_at)
        stamp = source_stamp_ns(message)
        if stamp <= self._last_paired_stamp_ns or stamp in self._relative:
            raise ValueError("relative IMU source stamp is duplicate or out of order")
        self._relative[stamp] = RelativeAttitudeObservation(
            source_stamp_ns=stamp,
            roll_rad=_finite(message.vector.x, "relative_roll_rad"),
            pitch_rad=_finite(message.vector.y, "relative_pitch_rad"),
            received_at=received,
        )
        self._try_pair(stamp)
        self._trim_pending()

    def update_status(self, status: str) -> bool:
        normalized = status.strip().lower() if isinstance(status, str) else ""
        if normalized == "connected":
            self._connected = True
            return True
        if normalized in {"disconnected", "reconnecting"}:
            self._connected = False
            return True
        return False

    def update_zero_generation(self, generation: object) -> None:
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
            raise ValueError("zero_generation must be a non-negative integer")
        if self._zero_generation != generation:
            self._paired = None
            self._raw.clear()
            self._relative.clear()
        self._zero_generation = generation

    def snapshot(self, *, now: float, freshness_sec: float) -> ImuState:
        current = _received_at(now)
        if not math.isfinite(freshness_sec) or freshness_sec <= 0.0:
            raise ValueError("IMU freshness must be finite and positive")
        paired = self._paired
        if paired is None:
            return ImuState(
                orientation=None,
                roll_rad=None,
                pitch_rad=None,
                yaw_rad=None,
                relative_roll_rad=None,
                relative_pitch_rad=None,
                relative_pitch_rate_rad_s=None,
                angular_velocity_rad_s=None,
                linear_acceleration_m_s2=None,
                sample_age_sec=None,
                valid=False,
                fresh=False,
                connected=self._connected,
                zero_generation=self._zero_generation,
            )
        sample_received_at = min(
            paired.raw.received_at, paired.relative.received_at
        )
        age = max(0.0, current - sample_received_at)
        valid = self._connected is True and self._zero_generation is not None
        return ImuState(
            orientation=paired.raw.orientation,
            roll_rad=paired.raw.roll_rad,
            pitch_rad=paired.raw.pitch_rad,
            yaw_rad=paired.raw.yaw_rad,
            relative_roll_rad=paired.relative.roll_rad,
            relative_pitch_rad=paired.relative.pitch_rad,
            relative_pitch_rate_rad_s=paired.raw.relative_pitch_rate_rad_s,
            angular_velocity_rad_s=paired.raw.angular_velocity_rad_s,
            linear_acceleration_m_s2=paired.raw.linear_acceleration_m_s2,
            sample_age_sec=age,
            valid=valid,
            fresh=valid and age <= freshness_sec,
            connected=self._connected,
            zero_generation=self._zero_generation,
        )

    def _try_pair(self, stamp: int) -> None:
        raw = self._raw.get(stamp)
        relative = self._relative.get(stamp)
        if raw is None or relative is None:
            return
        self._paired = PairedImuObservation(raw=raw, relative=relative)
        self._last_paired_stamp_ns = stamp
        self._raw = {key: value for key, value in self._raw.items() if key > stamp}
        self._relative = {
            key: value for key, value in self._relative.items() if key > stamp
        }

    def _trim_pending(self) -> None:
        for cache in (self._raw, self._relative):
            while len(cache) > self._PENDING_LIMIT:
                del cache[min(cache)]
