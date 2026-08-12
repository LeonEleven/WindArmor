from copy import deepcopy

import pytest

from windarmor_flight_control.runtime.config import (
    PARAMETER_DEFAULTS,
    build_runtime_config,
)


def test_default_runtime_config_is_explicitly_dry_run_observability() -> None:
    config = build_runtime_config(deepcopy(PARAMETER_DEFAULTS))
    assert config.control_rate_hz == 50.0
    assert config.motor_names == (
        "left_lift",
        "left_pitch",
        "right_pitch",
        "right_lift",
    )
    assert config.runtime_status_topic == "/flight_control/dry_run/status"
    assert config.command_preview_topic.endswith("/command_preview")
    assert config.flight_takeover_enabled is False
    assert config.flight_command_topic == "/flight_control/command"
    assert config.flight_handoff_timeout_sec == 1.0
    assert config.flight_revoke_timeout_sec == 0.25


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("control_rate_hz", 0.0),
        ("flight_imu_freshness_sec", float("nan")),
        ("flight_motor_freshness_sec", -1.0),
        ("flight_fan_output_freshness_sec", float("inf")),
        ("flight_fan_state_freshness_sec", 0.0),
        ("flight_control_state_freshness_sec", 0.0),
        ("flight_owner_state_freshness_sec", 0.0),
        ("flight_handoff_timeout_sec", 0.0),
        ("flight_handoff_timeout_sec", float("inf")),
        ("flight_revoke_timeout_sec", 0.0),
        ("flight_revoke_timeout_sec", float("nan")),
        ("fan_observer_min_pwm_us", float("nan")),
        ("controller_factory", ""),
        ("imu_raw_topic", "bad topic"),
        ("runtime_status_topic", "/flight_control/status"),
        ("command_preview_topic", "/flight_control/command"),
        ("flight_takeover_enabled", "false"),
        ("motor_flight_prepare_service", "bad service"),
    ],
)
def test_invalid_runtime_config_fails_before_ros_resources(name, value) -> None:
    values = deepcopy(PARAMETER_DEFAULTS)
    values[name] = value
    with pytest.raises(ValueError):
        build_runtime_config(values)


def test_motor_names_and_observer_range_are_strict() -> None:
    values = deepcopy(PARAMETER_DEFAULTS)
    values["motor_names"] = ["same", "same"]
    with pytest.raises(ValueError, match="unique"):
        build_runtime_config(values)

    values = deepcopy(PARAMETER_DEFAULTS)
    values["fan_observer_min_pwm_us"] = 2200.0
    with pytest.raises(ValueError, match="less"):
        build_runtime_config(values)
