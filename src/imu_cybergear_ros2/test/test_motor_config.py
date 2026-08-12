from dataclasses import FrozenInstanceError

import pytest

from imu_cybergear_ros2.motor_config import (
    build_motor_node_config,
    default_motor_config_values,
)


def test_default_config_preserves_current_motor_mapping_and_control_values() -> None:
    config = build_motor_node_config(default_motor_config_values())
    assert [channel.motor_id for channel in config.channels] == [4, 3, 2, 1]
    assert [channel.sign for channel in config.channels] == [-1.0, 1.0, -1.0, 1.0]
    assert [channel.limit_min for channel in config.channels] == [
        -1.57,
        -1.57,
        -1.57,
        0.0,
    ]
    assert [channel.limit_max for channel in config.channels] == [
        0.0,
        1.57,
        1.57,
        1.57,
    ]
    assert config.control.motion.command_interval_sec == 0.02
    assert config.control.motion.manual_motion_speed_rad_s == 4.0
    assert config.control.motion.auto_motion_speed_rad_s == 4.0
    assert config.control.motion.home_motion_speed_rad_s == 4.0
    assert config.communication.backend == "socketcan_hat"
    assert config.safety.motor_invalid_feedback_limit == 3
    assert config.safety.motor_feedback_timeout_sec == 0.0
    assert config.safety.motor_feedback_startup_grace_sec == 3.0
    assert config.safety.motor_feedback_check_rate_hz == 10.0
    assert config.ros.motor_feedback_structured_topic == "/motors/feedback"
    assert config.ros.motor_safety_state_topic == "/motors/safety_state"
    assert config.ros.motor_feedback_publish_rate_hz == 10.0
    assert config.ros.motor_feedback_observer_freshness_sec == 0.5
    assert config.safety.reconnect_on_disconnect
    assert config.safety.reconnect_policy.max_attempts == 30
    assert config.safety.reconnect_policy.initial_delay_sec == 0.5
    assert config.safety.reconnect_policy.max_delay_sec == 10.0
    assert config.safety.reconnect_policy.backoff_multiplier == 1.5
    assert config.communication.fallback_parameters == ()
    with pytest.raises(FrozenInstanceError):
        config.communication.master_id = 1


def set_all_motor_lists(raw, value):
    for name in (
        "motor_names",
        "motor_ids",
        "motor_signs",
        "motor_limits_min",
        "motor_limits_max",
        "motor_control_axes",
        "motor_keys_forward",
        "motor_keys_backward",
    ):
        raw[name] = list(value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: set_all_motor_lists(raw, []), "不得为空"),
        (lambda raw: raw.update(motor_names=["only_one"]), "长度不一致"),
        (lambda raw: raw.update(motor_ids=[4, 4, 2, 1]), "重复 ID"),
        (lambda raw: raw.update(motor_ids=[0, 3, 2, 1]), "1～127"),
        (
            lambda raw: raw.update(
                motor_names=["left_lift", "left_lift", "right_pitch", "right_lift"]
            ),
            "重复名称",
        ),
        (
            lambda raw: raw.update(
                motor_names=["left_lift", " ", "right_pitch", "right_lift"]
            ),
            "非空字符串",
        ),
        (lambda raw: raw.update(motor_signs=[0.0, 1.0, -1.0, 1.0]), "严格为"),
        (lambda raw: raw.update(motor_signs=[2.0, 1.0, -1.0, 1.0]), "严格为"),
        (lambda raw: raw.update(motor_signs=[float("nan"), 1.0, -1.0, 1.0]), "有限值"),
        (lambda raw: raw.update(motor_signs=[float("inf"), 1.0, -1.0, 1.0]), "有限值"),
        (
            lambda raw: raw.update(
                motor_limits_min=[float("nan"), -1.57, -1.57, 0.0]
            ),
            "有限值",
        ),
        (
            lambda raw: raw.update(
                motor_limits_max=[0.0, float("inf"), 1.57, 1.57]
            ),
            "有限值",
        ),
        (
            lambda raw: raw.update(
                motor_limits_min=[0.0, -1.57, -1.57, 0.0]
            ),
            "严格小于",
        ),
        (
            lambda raw: raw.update(
                motor_control_axes=["yaw", "pitch", "pitch", "roll_right"]
            ),
            "不受支持",
        ),
        (
            lambda raw: raw.update(
                motor_control_axes=[" ", "pitch", "pitch", "roll_right"]
            ),
            "非空字符串",
        ),
        (
            lambda raw: raw.update(motor_keys_forward=["d", "d", "k", "l"]),
            "必须唯一",
        ),
        (
            lambda raw: raw.update(motor_keys_backward=["d", "s", "i", "j"]),
            "必须唯一",
        ),
        (
            lambda raw: raw.update(motor_keys_forward=["m", "w", "k", "l"]),
            "冲突",
        ),
        (
            lambda raw: raw.update(motor_keys_forward=["1", "w", "k", "l"]),
            "数字选中键冲突",
        ),
        (lambda raw: raw.update(control_backend="unknown"), "不受支持"),
        (lambda raw: raw.update(can_channel=""), "can_channel"),
        (lambda raw: raw.update(master_id=256), "0～255"),
        (lambda raw: raw.update(master_id=4), "不得与任何 motor_id"),
        (lambda raw: raw.update(imu_topic=" "), "imu_topic"),
        (lambda raw: raw.update(motor_mode_topic="bad topic"), "motor_mode_topic"),
        (lambda raw: raw.update(motor_mode_publish_rate_hz=0.0), "必须大于 0"),
        (
            lambda raw: raw.update(motor_feedback_publish_rate_hz=0.0),
            "必须大于 0",
        ),
        (
            lambda raw: raw.update(
                motor_feedback_observer_freshness_sec=float("nan")
            ),
            "有限值",
        ),
        (lambda raw: raw.update(imu_zero_timeout_sec=float("nan")), "有限值"),
        (lambda raw: raw.update(manual_loop_hz=0.0), "必须大于 0"),
        (lambda raw: raw.update(roll_axis_sign=0.0), "严格为"),
        (lambda raw: raw.update(pitch_axis_sign=2.0), "严格为"),
        (lambda raw: raw.update(deadband_rad=-0.1), "不得小于 0"),
        (lambda raw: raw.update(watchdog_timeout_ms=-1), "不得为负数"),
        (
            lambda raw: raw.update(
                motor_temp_limit_degC=90.0,
                motor_temp_critical_degC=90.0,
            ),
            "必须严格大于",
        ),
        (lambda raw: raw.update(motor_current_limit_a=0.0), "必须大于 0"),
        (lambda raw: raw.update(motor_invalid_feedback_limit=0), "正整数"),
        (lambda raw: raw.update(motor_invalid_feedback_limit=1.5), "整数"),
        (lambda raw: raw.update(motor_feedback_timeout_sec=-0.1), "不得小于 0"),
        (lambda raw: raw.update(motor_feedback_timeout_sec=float("nan")), "有限值"),
        (lambda raw: raw.update(motor_feedback_startup_grace_sec=0.0), "必须大于 0"),
        (lambda raw: raw.update(motor_feedback_check_rate_hz=float("inf")), "有限值"),
        (lambda raw: raw.update(position_error_threshold_rad=0.0), "必须大于 0"),
        (lambda raw: raw.update(warning_throttle_sec=0.0), "必须大于 0"),
        (lambda raw: raw.update(reconnect_max_attempts=0), "greater than zero"),
        (lambda raw: raw.update(reconnect_max_attempts=1.5), "必须是整数"),
        (lambda raw: raw.update(reconnect_initial_delay_sec=-0.1), "must not be negative"),
        (lambda raw: raw.update(reconnect_max_delay_sec=0.1), "must be >="),
        (lambda raw: raw.update(reconnect_backoff_multiplier=0.5), "must be >= 1.0"),
        (lambda raw: raw.update(reconnect_max_delay_sec=float("inf")), "必须是有限值"),
    ],
)
def test_invalid_configurations_are_rejected(mutate, message) -> None:
    raw = default_motor_config_values()
    mutate(raw)
    with pytest.raises(ValueError, match=message):
        build_motor_node_config(raw)


def test_usb_backend_requires_resolved_port_and_positive_baud() -> None:
    raw = default_motor_config_values()
    raw.update(
        control_backend="usb_can_serial",
        usb_port="",
        motor_port="",
    )
    with pytest.raises(ValueError, match="解析后"):
        build_motor_node_config(raw)

    raw = default_motor_config_values()
    raw.update(
        control_backend="usb_can_serial",
        usb_baud=0,
        motor_baud=0,
    )
    with pytest.raises(ValueError, match="正整数"):
        build_motor_node_config(raw)


@pytest.mark.parametrize(
    ("legacy_name", "value", "replacement"),
    [
        ("left_lift_motor_id", 5, "motor_ids"),
        ("right_pitch_sign", 1.0, "motor_signs"),
        ("m1_min", -0.1, "motor_limits_min"),
        ("m2_max", 1.0, "motor_limits_max"),
    ],
)
def test_changed_ignored_legacy_parameters_fail_with_migration_target(
    legacy_name, value, replacement
) -> None:
    raw = default_motor_config_values()
    raw[legacy_name] = value
    with pytest.raises(ValueError) as exc_info:
        build_motor_node_config(raw)
    message = str(exc_info.value)
    assert legacy_name in message
    assert "已废弃" in message
    assert replacement in message


def test_usb_new_parameters_win_over_conflicting_legacy_values() -> None:
    raw = default_motor_config_values()
    raw.update(
        control_backend="usb_can_serial",
        usb_port="/dev/new_usb_can",
        usb_baud=115200,
        motor_port="/dev/legacy_usb_can",
        motor_baud=460800,
    )
    config = build_motor_node_config(raw)
    assert config.communication.usb_port == "/dev/new_usb_can"
    assert config.communication.usb_baud == 115200
    assert config.communication.fallback_parameters == ()


def test_usb_legacy_fallback_is_explicit_without_opening_serial() -> None:
    raw = default_motor_config_values()
    raw.update(
        control_backend="usb_can_serial",
        usb_port="",
        usb_baud=0,
        motor_port="/dev/legacy_usb_can",
        motor_baud=460800,
    )
    config = build_motor_node_config(raw)
    assert config.communication.usb_port == "/dev/legacy_usb_can"
    assert config.communication.usb_baud == 460800
    assert config.communication.fallback_parameters == ("motor_port", "motor_baud")


def test_watchdog_zero_retains_disabled_compatibility_semantics() -> None:
    raw = default_motor_config_values()
    raw["watchdog_timeout_ms"] = 0
    config = build_motor_node_config(raw)
    assert config.safety.watchdog_timeout_ms == 0
