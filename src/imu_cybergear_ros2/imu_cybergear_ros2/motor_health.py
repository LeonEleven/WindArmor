"""Pure motor-feedback validation and freshness tracking.

This module deliberately has no ROS or driver dependency.  Callers provide a
status-like object and the local monotonic receive time explicitly.
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Dict, Optional, Protocol, Tuple, Union


POSITION_MIN_RAD = -4.0 * math.pi
POSITION_MAX_RAD = 4.0 * math.pi
SPEED_MIN_RAD_S = -30.0
SPEED_MAX_RAD_S = 30.0
TORQUE_MIN_NM = -12.0
TORQUE_MAX_NM = 12.0
TEMPERATURE_MIN_DEG_C = -40.0
TEMPERATURE_MAX_DEG_C = 200.0
VALID_MODES = frozenset({0, 1, 2})
SUPPORTED_FAULT_MASK = 0x3F

FAULT_NAMES = {
    0: "欠压",
    1: "过流",
    2: "过温",
    3: "磁编码故障",
    4: "HALL编码故障",
    5: "未标定",
}


class MotorStatusLike(Protocol):
    motor_id: int
    position_rad: float
    speed_rad_s: float
    torque_nm: float
    temperature: float
    mode: int
    fault_flags: int
    timestamp: float


class MotorHealthAction(str, Enum):
    ACCEPT = "accept"
    WARNING = "warning"
    TRIP = "trip"
    IGNORE = "ignore"


class MotorHealthReason(str, Enum):
    HEALTHY = "healthy"
    UNKNOWN_MOTOR_ID = "unknown_motor_id"
    INVALID_FEEDBACK = "invalid_feedback"
    TEMPERATURE_WARNING = "temperature_warning"
    CRITICAL_TEMPERATURE = "critical_temperature"
    FEEDBACK_TIMEOUT = "feedback_timeout"
    MOTOR_FAULT_UNDERVOLTAGE = "motor_fault_undervoltage"
    MOTOR_FAULT_OVERCURRENT = "motor_fault_overcurrent"
    MOTOR_FAULT_OVERTEMPERATURE = "motor_fault_overtemperature"
    MOTOR_FAULT_ENCODER = "motor_fault_encoder"
    MOTOR_FAULT_UNCALIBRATED = "motor_fault_uncalibrated"
    MOTOR_FAULT_MULTIPLE = "motor_fault_multiple"


ObservedValue = Union[float, int, str, None]


@dataclass(frozen=True)
class MotorHealthConfig:
    motor_ids: Tuple[int, ...]
    temp_warning_deg_c: float
    temp_critical_deg_c: float
    invalid_feedback_limit: int
    feedback_timeout_sec: float
    feedback_startup_grace_sec: float


@dataclass(frozen=True)
class MotorHealthDecision:
    action: MotorHealthAction
    motor_id: int
    reason: MotorHealthReason
    observed_value: ObservedValue
    threshold: Optional[float]
    timestamp: float
    diagnostic_message: str
    fault_flags: int = 0
    fault_names: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MotorSafetyFaultSnapshot:
    motor_id: int
    reason: MotorHealthReason
    observed_value: ObservedValue
    threshold: Optional[float]
    fault_flags: int
    fault_names: Tuple[str, ...]
    first_triggered_at: float
    diagnostic_message: str


@dataclass(frozen=True)
class MotorFreshnessSnapshot:
    motor_id: int
    has_feedback: bool
    age_sec: Optional[float]
    last_received_at: Optional[float]


def fault_names(flags: int) -> Tuple[str, ...]:
    return tuple(name for bit, name in FAULT_NAMES.items() if flags & (1 << bit))


def classify_fault(flags: int) -> MotorHealthReason:
    """Classify one supported non-zero firmware fault mask."""
    bits = [bit for bit in FAULT_NAMES if flags & (1 << bit)]
    if len(bits) != 1:
        return MotorHealthReason.MOTOR_FAULT_MULTIPLE
    bit = bits[0]
    if bit == 0:
        return MotorHealthReason.MOTOR_FAULT_UNDERVOLTAGE
    if bit == 1:
        return MotorHealthReason.MOTOR_FAULT_OVERCURRENT
    if bit == 2:
        return MotorHealthReason.MOTOR_FAULT_OVERTEMPERATURE
    if bit in (3, 4):
        return MotorHealthReason.MOTOR_FAULT_ENCODER
    return MotorHealthReason.MOTOR_FAULT_UNCALIBRATED


class MotorHealthCore:
    """Stateful pure logic for validation, warnings and feedback freshness."""

    def __init__(self, config: MotorHealthConfig):
        self._config = config
        self._motor_ids = frozenset(config.motor_ids)
        self._invalid_counts: Dict[int, int] = {
            motor_id: 0 for motor_id in config.motor_ids
        }
        self._last_received_at: Dict[int, Optional[float]] = {
            motor_id: None for motor_id in config.motor_ids
        }
        self._activation_time: Optional[float] = None

    @property
    def invalid_counts(self) -> Dict[int, int]:
        return dict(self._invalid_counts)

    @property
    def timeout_enabled(self) -> bool:
        return self._config.feedback_timeout_sec > 0.0

    @property
    def activation_time(self) -> Optional[float]:
        return self._activation_time

    def activate(self, now: float) -> None:
        self._require_local_time(now)
        self._activation_time = now
        self._invalid_counts = {motor_id: 0 for motor_id in self._config.motor_ids}
        self._last_received_at = {motor_id: None for motor_id in self._config.motor_ids}

    def deactivate(self) -> None:
        self._activation_time = None

    def evaluate(self, status: MotorStatusLike, *, received_at: float) -> MotorHealthDecision:
        self._require_local_time(received_at)
        motor_id = getattr(status, "motor_id", None)
        if motor_id not in self._motor_ids:
            return MotorHealthDecision(
                MotorHealthAction.IGNORE,
                int(motor_id) if isinstance(motor_id, int) else -1,
                MotorHealthReason.UNKNOWN_MOTOR_ID,
                motor_id,
                None,
                received_at,
                f"忽略未配置电机 ID 的反馈: {motor_id!r}",
            )

        invalid = self._validate_status(status)
        if invalid is not None:
            self._invalid_counts[motor_id] += 1
            count = self._invalid_counts[motor_id]
            action = (
                MotorHealthAction.TRIP
                if count >= self._config.invalid_feedback_limit
                else MotorHealthAction.IGNORE
            )
            return MotorHealthDecision(
                action,
                motor_id,
                MotorHealthReason.INVALID_FEEDBACK,
                invalid,
                float(self._config.invalid_feedback_limit),
                received_at,
                f"电机 ID{motor_id} 无效反馈 ({count}/"
                f"{self._config.invalid_feedback_limit}): {invalid}",
            )

        self._invalid_counts[motor_id] = 0
        self._last_received_at[motor_id] = received_at
        flags = int(status.fault_flags)
        if flags:
            names = fault_names(flags)
            return MotorHealthDecision(
                MotorHealthAction.TRIP,
                motor_id,
                classify_fault(flags),
                flags,
                None,
                received_at,
                f"电机 ID{motor_id} 固件故障: {', '.join(names)} "
                f"(0x{flags:02X})",
                fault_flags=flags,
                fault_names=names,
            )

        temperature = float(status.temperature)
        if temperature >= self._config.temp_critical_deg_c:
            return MotorHealthDecision(
                MotorHealthAction.TRIP,
                motor_id,
                MotorHealthReason.CRITICAL_TEMPERATURE,
                temperature,
                self._config.temp_critical_deg_c,
                received_at,
                f"电机 ID{motor_id} 临界温度: {temperature:.1f}°C >= "
                f"{self._config.temp_critical_deg_c:.1f}°C",
            )
        if temperature >= self._config.temp_warning_deg_c:
            return MotorHealthDecision(
                MotorHealthAction.WARNING,
                motor_id,
                MotorHealthReason.TEMPERATURE_WARNING,
                temperature,
                self._config.temp_warning_deg_c,
                received_at,
                f"电机 ID{motor_id} 温度警告: {temperature:.1f}°C >= "
                f"{self._config.temp_warning_deg_c:.1f}°C（不自动降速）",
            )
        return MotorHealthDecision(
            MotorHealthAction.ACCEPT,
            motor_id,
            MotorHealthReason.HEALTHY,
            temperature,
            self._config.temp_warning_deg_c,
            received_at,
            f"电机 ID{motor_id} 反馈合法",
        )

    def check_freshness(self, *, now: float) -> Tuple[MotorHealthDecision, ...]:
        self._require_local_time(now)
        if not self.timeout_enabled or self._activation_time is None:
            return ()
        if now - self._activation_time < self._config.feedback_startup_grace_sec:
            return ()

        decisions = []
        for motor_id in self._config.motor_ids:
            received_at = self._last_received_at[motor_id]
            if received_at is None:
                decisions.append(
                    MotorHealthDecision(
                        MotorHealthAction.TRIP,
                        motor_id,
                        MotorHealthReason.FEEDBACK_TIMEOUT,
                        None,
                        self._config.feedback_startup_grace_sec,
                        now,
                        f"电机 ID{motor_id} 启动宽限期结束仍无合法反馈",
                    )
                )
                continue
            age = max(0.0, now - received_at)
            if age > self._config.feedback_timeout_sec:
                decisions.append(
                    MotorHealthDecision(
                        MotorHealthAction.TRIP,
                        motor_id,
                        MotorHealthReason.FEEDBACK_TIMEOUT,
                        age,
                        self._config.feedback_timeout_sec,
                        now,
                        f"电机 ID{motor_id} 反馈超时: {age:.3f}s > "
                        f"{self._config.feedback_timeout_sec:.3f}s",
                    )
                )
        return tuple(decisions)

    def freshness_snapshot(self, *, now: float) -> Tuple[MotorFreshnessSnapshot, ...]:
        self._require_local_time(now)
        snapshots = []
        for motor_id in self._config.motor_ids:
            received_at = self._last_received_at[motor_id]
            snapshots.append(
                MotorFreshnessSnapshot(
                    motor_id=motor_id,
                    has_feedback=received_at is not None,
                    age_sec=(None if received_at is None else max(0.0, now - received_at)),
                    last_received_at=received_at,
                )
            )
        return tuple(snapshots)

    @staticmethod
    def _require_local_time(value: float) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("本地接收时间必须是有限非负数")
        if not math.isfinite(float(value)) or float(value) < 0.0:
            raise ValueError("本地接收时间必须是有限非负数")

    @staticmethod
    def _validate_status(status: MotorStatusLike) -> Optional[str]:
        numeric_ranges = (
            ("position_rad", POSITION_MIN_RAD, POSITION_MAX_RAD),
            ("speed_rad_s", SPEED_MIN_RAD_S, SPEED_MAX_RAD_S),
            ("torque_nm", TORQUE_MIN_NM, TORQUE_MAX_NM),
            ("temperature", TEMPERATURE_MIN_DEG_C, TEMPERATURE_MAX_DEG_C),
        )
        for name, minimum, maximum in numeric_ranges:
            value = getattr(status, name, None)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                return f"{name} 不是有限数值: {value!r}"
            if not minimum <= float(value) <= maximum:
                return f"{name} 超出允许范围 [{minimum}, {maximum}]: {value!r}"

        timestamp = getattr(status, "timestamp", None)
        if (
            not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
            or not math.isfinite(float(timestamp))
            or float(timestamp) < 0.0
        ):
            return f"timestamp 必须是有限非负数: {timestamp!r}"
        mode = getattr(status, "mode", None)
        if not isinstance(mode, int) or isinstance(mode, bool) or mode not in VALID_MODES:
            return f"mode 不在协议允许集合 {sorted(VALID_MODES)}: {mode!r}"
        flags = getattr(status, "fault_flags", None)
        if (
            not isinstance(flags, int)
            or isinstance(flags, bool)
            or flags < 0
            or flags & ~SUPPORTED_FAULT_MASK
        ):
            return f"fault_flags 包含不支持的 bit: {flags!r}"
        return None
