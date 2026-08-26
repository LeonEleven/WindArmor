"""DRY_RUN 与显式接管 Runtime 模式的校验后配置。"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping


TOPIC_PATTERN = re.compile(r"/?[A-Za-z_][A-Za-z0-9_/]*")
BOUNDED_VERIFICATION_FACTORY = (
    "windarmor_flight_control.algorithms."
    "bounded_verification_controller:create_controller"
)

PARAMETER_DEFAULTS = {
    "control_rate_hz": 50.0,
    "motor_names": ["left_lift", "left_pitch", "right_pitch", "right_lift"],
    "flight_imu_freshness_sec": 0.2,
    "flight_motor_freshness_sec": 0.5,
    "flight_fan_output_freshness_sec": 1.0,
    "flight_fan_state_freshness_sec": 1.0,
    "flight_control_state_freshness_sec": 1.0,
    "flight_motor_safety_state_freshness_sec": 1.0,
    "flight_fan_safety_state_freshness_sec": 1.0,
    "flight_owner_state_freshness_sec": 1.0,
    "flight_handoff_timeout_sec": 1.0,
    "flight_revoke_timeout_sec": 0.25,
    "fan_observer_min_pwm_us": 800.0,
    "fan_observer_max_pwm_us": 2200.0,
    "controller_factory": (
        "windarmor_flight_control.algorithms.flight_controller:create_controller"
    ),
    "verification_controller_enabled": False,
    "test_motor_name": "",
    "motor_test_offset_configured": False,
    "motor_test_offset_rad": 0.0,
    "fan_left_test_command": 0.0,
    "fan_right_test_command": 0.0,
    "imu_raw_topic": "/imu/data_raw",
    "imu_status_topic": "/imu/status",
    "imu_relative_topic": "/imu/relative_roll_pitch",
    "imu_zero_generation_topic": "/imu/zero_generation",
    "motor_feedback_topic": "/motors/feedback",
    "motor_control_mode_topic": "/motors/control_mode",
    "motor_safety_state_topic": "/motors/safety_state",
    "fan_status_pwm_topic": "/fans/status_pwm",
    "fan_enabled_topic": "/fans/enabled",
    "fan_control_state_topic": "/fans/control_state",
    "fan_safety_state_topic": "/fans/safety_state",
    "e_stop_topic": "/e_stop",
    "runtime_status_topic": "/flight_control/dry_run/status",
    "command_preview_topic": "/flight_control/dry_run/command_preview",
    "authority_status_topic": "/flight_control/authority/status",
    "authority_prepare_service": "/flight_control/authority/prepare",
    "authority_cancel_service": "/flight_control/authority/cancel",
    "authority_reset_inhibit_service": "/flight_control/authority/reset_inhibit",
    "flight_takeover_enabled": False,
    "motor_flight_prepare_service": "/motors/flight_ownership/prepare",
    "motor_flight_commit_service": "/motors/flight_ownership/commit",
    "motor_flight_revoke_service": "/motors/flight_ownership/revoke",
    "fan_flight_prepare_service": "/fans/flight_ownership/prepare",
    "fan_flight_commit_service": "/fans/flight_ownership/commit",
    "fan_flight_revoke_service": "/fans/flight_ownership/revoke",
    "motor_ownership_state_topic": "/motors/ownership_state",
    "fan_ownership_state_topic": "/fans/ownership_state",
    "flight_command_topic": "/flight_control/command",
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
    flight_motor_safety_state_freshness_sec: float
    flight_fan_safety_state_freshness_sec: float
    flight_owner_state_freshness_sec: float
    flight_handoff_timeout_sec: float
    flight_revoke_timeout_sec: float
    fan_observer_min_pwm_us: float
    fan_observer_max_pwm_us: float
    controller_factory: str
    verification_controller_enabled: bool
    test_motor_name: str
    motor_test_offset_configured: bool
    motor_test_offset_rad: float
    fan_left_test_command: float
    fan_right_test_command: float
    imu_raw_topic: str
    imu_status_topic: str
    imu_relative_topic: str
    imu_zero_generation_topic: str
    motor_feedback_topic: str
    motor_control_mode_topic: str
    motor_safety_state_topic: str
    fan_status_pwm_topic: str
    fan_enabled_topic: str
    fan_control_state_topic: str
    fan_safety_state_topic: str
    e_stop_topic: str
    runtime_status_topic: str
    command_preview_topic: str
    authority_status_topic: str
    authority_prepare_service: str
    authority_cancel_service: str
    authority_reset_inhibit_service: str
    flight_takeover_enabled: bool
    motor_flight_prepare_service: str
    motor_flight_commit_service: str
    motor_flight_revoke_service: str
    fan_flight_prepare_service: str
    fan_flight_commit_service: str
    fan_flight_revoke_service: str
    motor_ownership_state_topic: str
    fan_ownership_state_topic: str
    flight_command_topic: str


POSITIVE_FIELDS = (
    "control_rate_hz",
    "flight_imu_freshness_sec",
    "flight_motor_freshness_sec",
    "flight_fan_output_freshness_sec",
    "flight_fan_state_freshness_sec",
    "flight_control_state_freshness_sec",
    "flight_motor_safety_state_freshness_sec",
    "flight_fan_safety_state_freshness_sec",
    "flight_owner_state_freshness_sec",
    "flight_handoff_timeout_sec",
    "flight_revoke_timeout_sec",
)

TOPIC_FIELDS = (
    "imu_raw_topic",
    "imu_status_topic",
    "imu_relative_topic",
    "imu_zero_generation_topic",
    "motor_feedback_topic",
    "motor_control_mode_topic",
    "motor_safety_state_topic",
    "fan_status_pwm_topic",
    "fan_enabled_topic",
    "fan_control_state_topic",
    "fan_safety_state_topic",
    "e_stop_topic",
    "runtime_status_topic",
    "command_preview_topic",
    "authority_status_topic",
    "authority_prepare_service",
    "authority_cancel_service",
    "authority_reset_inhibit_service",
    "motor_flight_prepare_service",
    "motor_flight_commit_service",
    "motor_flight_revoke_service",
    "fan_flight_prepare_service",
    "fan_flight_commit_service",
    "fan_flight_revoke_service",
    "motor_ownership_state_topic",
    "fan_ownership_state_topic",
    "flight_command_topic",
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
    """在创建 ROS 资源前校验全部时序和接口值。"""

    converted = dict(values)
    for name in (
        "flight_takeover_enabled",
        "verification_controller_enabled",
        "motor_test_offset_configured",
    ):
        if not isinstance(converted[name], bool):
            raise ValueError(f"{name} must be a bool")
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

    test_motor_name = converted["test_motor_name"]
    if not isinstance(test_motor_name, str):
        raise ValueError("test_motor_name must be a string")
    if test_motor_name and test_motor_name not in names:
        raise ValueError("test_motor_name must be a configured logical motor name")
    converted["test_motor_name"] = test_motor_name

    offset = _finite("motor_test_offset_rad", converted["motor_test_offset_rad"])
    converted["motor_test_offset_rad"] = offset
    for name in ("fan_left_test_command", "fan_right_test_command"):
        command = _finite(name, converted[name])
        if not 0.0 <= command <= 1.0:
            raise ValueError(f"{name} must be within [0.0, 1.0]")
        converted[name] = command

    if converted["verification_controller_enabled"]:
        if converted["controller_factory"] != BOUNDED_VERIFICATION_FACTORY:
            raise ValueError(
                "verification_controller_enabled requires the bounded verification factory"
            )
        if not test_motor_name:
            raise ValueError(
                "verification_controller_enabled requires test_motor_name"
            )
        if not converted["motor_test_offset_configured"]:
            raise ValueError(
                "verification_controller_enabled requires an explicitly configured motor offset"
            )

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
