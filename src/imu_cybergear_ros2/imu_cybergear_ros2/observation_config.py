"""被动 CyberGear 观测器的纯配置契约。"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping

from .motor_config import (
    MASTER_ID_MAX,
    MASTER_ID_MIN,
    MOTOR_ID_MAX,
    MOTOR_ID_MIN,
    SUPPORTED_BACKENDS,
)


OBSERVER_DEFAULTS = {
    "control_backend": "socketcan_hat",
    "master_id": 253,
    "usb_port": "/dev/ttyUSB0",
    "usb_baud": 921600,
    "can_channel": "can10",
    "can_bustype": "socketcan",
    "motor_names": ["left_lift", "left_pitch", "right_pitch", "right_lift"],
    "motor_ids": [4, 3, 2, 1],
    "motor_feedback_structured_topic": "/motors/feedback",
    "motor_feedback_observer_status_topic": "/motors/observer_status",
    "motor_feedback_publish_rate_hz": 10.0,
    "motor_feedback_observer_freshness_sec": 0.5,
    "motor_temp_limit_degC": 80.0,
    "motor_temp_critical_degC": 90.0,
    "motor_invalid_feedback_limit": 3,
    "observer_connect_max_attempts": 1,
    "observer_connect_initial_delay_sec": 0.5,
}

OBSERVER_PARAMETER_NAMES = tuple(OBSERVER_DEFAULTS)


@dataclass(frozen=True)
class ObservationMotorChannel:
    name: str
    motor_id: int


@dataclass(frozen=True)
class MotorObservationConfig:
    channels: tuple[ObservationMotorChannel, ...]
    backend: str
    master_id: int
    usb_port: str
    usb_baud: int
    can_channel: str
    can_bustype: str
    feedback_topic: str
    status_topic: str
    publish_rate_hz: float
    freshness_sec: float
    warning_temperature_c: float
    critical_temperature_c: float
    invalid_feedback_limit: int
    connect_max_attempts: int
    connect_initial_delay_sec: float


def _integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _nonblank(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _topic(name: str, value: object) -> str:
    result = _nonblank(name, value)
    if (
        any(character.isspace() for character in result)
        or "//" in result
        or result.endswith("/")
        or re.fullmatch(r"/?[A-Za-z_][A-Za-z0-9_/]*", result) is None
    ):
        raise ValueError(f"{name} is not an acceptable ROS 2 topic: {value!r}")
    return result


def build_motor_observation_config(
    raw: Mapping[str, object],
) -> MotorObservationConfig:
    """校验观测器专用参数，不创建 ROS 或硬件 I/O。"""

    missing = [name for name in OBSERVER_PARAMETER_NAMES if name not in raw]
    if missing:
        raise ValueError(f"missing motor observer parameters: {', '.join(missing)}")

    names = [_nonblank(f"motor_names[{index}]", value) for index, value in enumerate(raw["motor_names"])]
    ids = [_integer(f"motor_ids[{index}]", value) for index, value in enumerate(raw["motor_ids"])]
    if not names or len(names) != len(ids):
        raise ValueError("motor_names and motor_ids must be non-empty and equal length")
    if len(set(names)) != len(names):
        raise ValueError("motor_names must be unique")
    if len(set(ids)) != len(ids):
        raise ValueError("motor_ids must be unique")
    if any(not MOTOR_ID_MIN <= motor_id <= MOTOR_ID_MAX for motor_id in ids):
        raise ValueError(f"motor_ids must be in {MOTOR_ID_MIN}..{MOTOR_ID_MAX}")

    backend = _nonblank("control_backend", raw["control_backend"])
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"unsupported control_backend: {backend!r}")
    master_id = _integer("master_id", raw["master_id"])
    if not MASTER_ID_MIN <= master_id <= MASTER_ID_MAX:
        raise ValueError("master_id must be in 0..255")
    if master_id in ids:
        raise ValueError("master_id must differ from every motor_id")

    usb_port = _nonblank("usb_port", raw["usb_port"])
    usb_baud = _integer("usb_baud", raw["usb_baud"])
    if usb_baud <= 0:
        raise ValueError("usb_baud must be positive")
    can_channel = _nonblank("can_channel", raw["can_channel"])
    can_bustype = _nonblank("can_bustype", raw["can_bustype"])

    warning = _finite("motor_temp_limit_degC", raw["motor_temp_limit_degC"])
    critical = _finite("motor_temp_critical_degC", raw["motor_temp_critical_degC"])
    if critical <= warning:
        raise ValueError("critical motor temperature must exceed warning temperature")

    positive_floats = {
        name: _finite(name, raw[name])
        for name in (
            "motor_feedback_publish_rate_hz",
            "motor_feedback_observer_freshness_sec",
            "observer_connect_initial_delay_sec",
        )
    }
    if any(value <= 0.0 for value in positive_floats.values()):
        raise ValueError("observer rates, freshness and retry delay must be positive")
    invalid_limit = _integer(
        "motor_invalid_feedback_limit", raw["motor_invalid_feedback_limit"]
    )
    connect_attempts = _integer(
        "observer_connect_max_attempts", raw["observer_connect_max_attempts"]
    )
    if invalid_limit <= 0 or connect_attempts <= 0:
        raise ValueError("observer count limits must be positive")

    return MotorObservationConfig(
        channels=tuple(
            ObservationMotorChannel(name=name, motor_id=motor_id)
            for name, motor_id in zip(names, ids)
        ),
        backend=backend,
        master_id=master_id,
        usb_port=usb_port,
        usb_baud=usb_baud,
        can_channel=can_channel,
        can_bustype=can_bustype,
        feedback_topic=_topic(
            "motor_feedback_structured_topic",
            raw["motor_feedback_structured_topic"],
        ),
        status_topic=_topic(
            "motor_feedback_observer_status_topic",
            raw["motor_feedback_observer_status_topic"],
        ),
        publish_rate_hz=positive_floats["motor_feedback_publish_rate_hz"],
        freshness_sec=positive_floats["motor_feedback_observer_freshness_sec"],
        warning_temperature_c=warning,
        critical_temperature_c=critical,
        invalid_feedback_limit=invalid_limit,
        connect_max_attempts=connect_attempts,
        connect_initial_delay_sec=positive_floats[
            "observer_connect_initial_delay_sec"
        ],
    )
