"""Validated configuration for the observation-only runtime."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping


TOPIC_PATTERN = re.compile(r"/?[A-Za-z_][A-Za-z0-9_/]*")

PARAMETER_DEFAULTS = {
    "control_rate_hz": 50.0,
    "motor_names": ["left_lift", "left_pitch", "right_pitch", "right_lift"],
    "flight_imu_freshness_sec": 0.2,
    "flight_motor_freshness_sec": 0.5,
    "flight_fan_output_freshness_sec": 1.0,
    "flight_fan_state_freshness_sec": 1.0,
    "flight_control_state_freshness_sec": 1.0,
    "fan_observer_min_pwm_us": 800.0,
    "fan_observer_max_pwm_us": 2200.0,
    "controller_factory": (
        "windarmor_flight_control.algorithms.flight_controller:create_controller"
    ),
    "imu_raw_topic": "/imu/data_raw",
    "imu_status_topic": "/imu/status",
    "imu_relative_topic": "/imu/relative_roll_pitch",
    "imu_zero_generation_topic": "/imu/zero_generation",
    "motor_feedback_topic": "/motors/feedback",
    "motor_control_mode_topic": "/motors/control_mode",
    "fan_status_pwm_topic": "/fans/status_pwm",
    "fan_enabled_topic": "/fans/enabled",
    "fan_control_state_topic": "/fans/control_state",
    "e_stop_topic": "/e_stop",
    "runtime_status_topic": "/flight_control/dry_run/status",
    "command_preview_topic": "/flight_control/dry_run/command_preview",
}


@dataclass(frozen=True)
class RuntimeConfig:
    control_rate_hz: float
    motor_names: tuple[str, ...]
    flight_imu_freshness_sec: float
    flight_motor_freshness_sec: float
    flight_fan_output_freshness_sec: float
    flight_fan_state_freshness_sec: float
    flight_control_state_freshness_sec: float
    fan_observer_min_pwm_us: float
    fan_observer_max_pwm_us: float
    controller_factory: str
    imu_raw_topic: str
    imu_status_topic: str
    imu_relative_topic: str
    imu_zero_generation_topic: str
    motor_feedback_topic: str
    motor_control_mode_topic: str
    fan_status_pwm_topic: str
    fan_enabled_topic: str
    fan_control_state_topic: str
    e_stop_topic: str
    runtime_status_topic: str
    command_preview_topic: str


POSITIVE_FIELDS = (
    "control_rate_hz",
    "flight_imu_freshness_sec",
    "flight_motor_freshness_sec",
    "flight_fan_output_freshness_sec",
    "flight_fan_state_freshness_sec",
    "flight_control_state_freshness_sec",
)

TOPIC_FIELDS = (
    "imu_raw_topic",
    "imu_status_topic",
    "imu_relative_topic",
    "imu_zero_generation_topic",
    "motor_feedback_topic",
    "motor_control_mode_topic",
    "fan_status_pwm_topic",
    "fan_enabled_topic",
    "fan_control_state_topic",
    "e_stop_topic",
    "runtime_status_topic",
    "command_preview_topic",
)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _topic(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or TOPIC_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a non-empty ROS topic name")
    if "//" in value or value.endswith("/"):
        raise ValueError(f"{name} must be a non-empty ROS topic name")
    return value


def build_runtime_config(values: Mapping[str, object]) -> RuntimeConfig:
    """Validate all timing and interface values before ROS resources exist."""

    converted = dict(values)
    for name in POSITIVE_FIELDS:
        value = _finite(name, converted[name])
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
        converted[name] = value

    minimum = _finite("fan_observer_min_pwm_us", converted["fan_observer_min_pwm_us"])
    maximum = _finite("fan_observer_max_pwm_us", converted["fan_observer_max_pwm_us"])
    if minimum >= maximum:
        raise ValueError("fan observer PWM minimum must be less than maximum")
    converted["fan_observer_min_pwm_us"] = minimum
    converted["fan_observer_max_pwm_us"] = maximum

    names_raw = converted["motor_names"]
    if not isinstance(names_raw, (list, tuple)):
        raise ValueError("motor_names must be a sequence")
    names = tuple(names_raw)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("motor_names must contain non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError("motor_names must be unique")
    converted["motor_names"] = names

    factory = converted["controller_factory"]
    if not isinstance(factory, str) or not factory.strip():
        raise ValueError("controller_factory must be a non-empty import contract")
    converted["controller_factory"] = factory.strip()

    for name in TOPIC_FIELDS:
        converted[name] = _topic(name, converted[name])
    if "dry_run" not in converted["runtime_status_topic"]:
        raise ValueError("runtime_status_topic must explicitly contain dry_run")
    if not any(
        marker in converted["command_preview_topic"]
        for marker in ("dry_run", "preview")
    ):
        raise ValueError("command_preview_topic must contain dry_run or preview")

    return RuntimeConfig(**converted)
