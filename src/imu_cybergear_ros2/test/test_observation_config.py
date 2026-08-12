from copy import deepcopy

import pytest

from imu_cybergear_ros2.observation_config import (
    OBSERVER_DEFAULTS,
    build_motor_observation_config,
)


def values(**overrides):
    result = deepcopy(OBSERVER_DEFAULTS)
    result.update(overrides)
    return result


def test_defaults_preserve_protected_controller_identity_map() -> None:
    config = build_motor_observation_config(values())
    assert [(channel.name, channel.motor_id) for channel in config.channels] == [
        ("left_lift", 4),
        ("left_pitch", 3),
        ("right_pitch", 2),
        ("right_lift", 1),
    ]
    assert config.backend == "socketcan_hat"
    assert config.feedback_topic == "/motors/feedback"
    assert config.status_topic == "/motors/observer_status"
    assert config.connect_max_attempts == 1


@pytest.mark.parametrize(
    "raw",
    [
        values(motor_ids=[4, 4, 2, 1]),
        values(motor_names=["left_lift"]),
        values(master_id=4),
        values(control_backend="invalid"),
        values(motor_feedback_publish_rate_hz=0.0),
        values(motor_temp_limit_degC=90.0, motor_temp_critical_degC=90.0),
        values(observer_connect_max_attempts=0),
    ],
)
def test_invalid_observer_config_fails_before_driver_creation(raw) -> None:
    with pytest.raises(ValueError):
        build_motor_observation_config(raw)


def test_yaml_observer_map_matches_protected_values() -> None:
    config_file = __import__("pathlib").Path(__file__).parents[1] / "config" / "imu_cybergear_params.yaml"
    source = config_file.read_text(encoding="utf-8")
    observer = source.split("motor_feedback_observer_node:", 1)[1]
    assert 'motor_names: ["left_lift", "left_pitch", "right_pitch", "right_lift"]' in observer
    assert "motor_ids: [4, 3, 2, 1]" in observer
    assert "motor_signs:" not in observer
    assert "motor_limits_min:" not in observer
    assert "motor_limits_max:" not in observer
