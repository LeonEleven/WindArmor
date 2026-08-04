import math

import pytest

from imu_cybergear_ros2.motor_motion import (
    MotionParameters,
    MotionSource,
    advance_target,
    auto_attitude_commands,
    manual_event_increment,
    speed_for_source,
    validate_auto_attitude_gains,
    validate_motion_parameters,
)


def parameters(**overrides) -> MotionParameters:
    values = {
        "command_interval_sec": 0.02,
        "motion_dt_max_sec": 0.05,
        "target_reached_tolerance_rad": 0.001,
        "manual_motion_speed_rad_s": 4.0,
        "auto_motion_speed_rad_s": 4.0,
        "home_motion_speed_rad_s": 4.0,
        "manual_step_rad": math.radians(3.0),
        "manual_repeat_gap_sec": 0.8,
        "manual_repeat_dt_max_sec": 0.08,
        "max_position_step": 0.4,
        "default_speed": 10.0,
        "manual_speed_min": 0.5,
        "manual_speed_max": 20.0,
        "manual_speed_step": 0.5,
    }
    values.update(overrides)
    return MotionParameters(**values)


def advance(current, desired, **overrides) -> float:
    values = {
        "mode_speed_rad_s": 4.0,
        "motor_speed_limit_rad_s": 10.0,
        "elapsed_sec": 0.02,
        "motion_dt_max_sec": 0.05,
        "max_position_step": 0.4,
        "target_reached_tolerance_rad": 0.001,
        "limit_min": -1.57,
        "limit_max": 1.57,
    }
    values.update(overrides)
    return advance_target(current, desired, **values)


def test_motion_parameters_and_mode_speeds() -> None:
    params = parameters()
    validate_motion_parameters(params)
    assert speed_for_source(MotionSource.MANUAL, params) == 4.0
    assert speed_for_source(MotionSource.AUTO, params) == 4.0
    assert speed_for_source(MotionSource.HOME, params) == 4.0
    assert speed_for_source(MotionSource.IDLE, params) == 0.0


def test_default_auto_gains_preserve_both_axes() -> None:
    roll, pitch = auto_attitude_commands(
        math.radians(10.0),
        math.radians(-20.0),
        deadband_rad=0.02,
        roll_gain=1.0,
        pitch_gain=1.0,
    )
    assert math.degrees(roll) == pytest.approx(10.0)
    assert math.degrees(pitch) == pytest.approx(-20.0)


def test_auto_gains_scale_only_their_own_axes() -> None:
    roll_only = auto_attitude_commands(
        math.radians(20.0),
        math.radians(20.0),
        deadband_rad=0.02,
        roll_gain=1.25,
        pitch_gain=1.0,
    )
    pitch_only = auto_attitude_commands(
        math.radians(20.0),
        math.radians(20.0),
        deadband_rad=0.02,
        roll_gain=1.0,
        pitch_gain=1.25,
    )
    assert tuple(map(math.degrees, roll_only)) == pytest.approx((25.0, 20.0))
    assert tuple(map(math.degrees, pitch_only)) == pytest.approx((20.0, 25.0))


def test_zero_auto_gain_disables_only_corresponding_axis() -> None:
    roll, pitch = auto_attitude_commands(
        0.5,
        -0.5,
        deadband_rad=0.02,
        roll_gain=0.0,
        pitch_gain=1.0,
    )
    assert roll == 0.0
    assert pitch == pytest.approx(-0.5)


def test_auto_gain_is_applied_after_existing_deadband() -> None:
    roll, pitch = auto_attitude_commands(
        0.01,
        -0.019,
        deadband_rad=0.02,
        roll_gain=100.0,
        pitch_gain=100.0,
    )
    assert (roll, pitch) == (0.0, 0.0)


def test_auto_gain_result_is_limited_to_90_degrees() -> None:
    roll, pitch = auto_attitude_commands(
        math.radians(80.0),
        math.radians(-80.0),
        deadband_rad=0.02,
        roll_gain=2.0,
        pitch_gain=2.0,
    )
    assert roll == pytest.approx(math.pi / 2.0)
    assert pitch == pytest.approx(-math.pi / 2.0)


@pytest.mark.parametrize("gain", [-0.1, math.nan, math.inf, -math.inf])
def test_invalid_auto_gains_are_rejected(gain: float) -> None:
    with pytest.raises(ValueError):
        validate_auto_attitude_gains(gain, 1.0)
    with pytest.raises(ValueError):
        validate_auto_attitude_gains(1.0, gain)


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("command_interval_sec", 0.0),
        ("motion_dt_max_sec", 0.01),
        ("target_reached_tolerance_rad", -0.1),
        ("manual_motion_speed_rad_s", 0.0),
        ("auto_motion_speed_rad_s", -1.0),
        ("home_motion_speed_rad_s", 0.0),
        ("manual_step_rad", 0.0),
        ("manual_repeat_gap_sec", 0.0),
        ("manual_repeat_dt_max_sec", 0.9),
        ("max_position_step", 0.0),
        ("default_speed", 0.0),
        ("manual_speed_min", 0.0),
        ("manual_speed_max", 0.1),
        ("manual_speed_step", 0.0),
    ],
)
def test_invalid_parameter_relationships(override: str, value: float) -> None:
    with pytest.raises(ValueError):
        validate_motion_parameters(parameters(**{override: value}))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_parameters_are_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        validate_motion_parameters(parameters(default_speed=value))


def test_advance_target_in_both_directions_without_overshoot() -> None:
    assert advance(0.0, 1.0) == pytest.approx(0.08)
    assert advance(0.0, -1.0) == pytest.approx(-0.08)
    assert advance(0.98, 1.0) == pytest.approx(1.0)


def test_equal_mode_speeds_produce_equal_motion() -> None:
    params = parameters()
    results = [
        advance(
            0.0,
            1.0,
            mode_speed_rad_s=speed_for_source(source, params),
            elapsed_sec=0.03,
        )
        for source in (MotionSource.MANUAL, MotionSource.AUTO, MotionSource.HOME)
    ]
    assert results == pytest.approx([0.12, 0.12, 0.12])


def test_dt_and_position_step_caps() -> None:
    assert advance(0.0, 1.0, elapsed_sec=0.0) == 0.0
    assert advance(0.0, 1.0, elapsed_sec=1.0) == pytest.approx(0.2)
    assert advance(
        0.0,
        1.0,
        elapsed_sec=0.05,
        max_position_step=0.1,
    ) == pytest.approx(0.1)


def test_motor_speed_limit_and_mode_speed_limit() -> None:
    assert advance(
        0.0, 1.0, motor_speed_limit_rad_s=2.0, elapsed_sec=0.05
    ) == pytest.approx(0.1)
    assert advance(
        0.0,
        1.0,
        mode_speed_rad_s=2.0,
        motor_speed_limit_rad_s=10.0,
        elapsed_sec=0.05,
    ) == pytest.approx(0.1)


def test_tolerance_and_soft_limits() -> None:
    assert advance(0.0, 0.0005) == pytest.approx(0.0005)
    assert advance(0.0, 2.0, limit_max=0.5) == pytest.approx(0.08)
    assert advance(0.49, 2.0, limit_max=0.5) == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_advance_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        advance(0.0, bad)


def test_invalid_advance_speed_is_rejected() -> None:
    with pytest.raises(ValueError):
        advance(0.0, 1.0, mode_speed_rad_s=-1.0)


def test_manual_first_press_is_finite_precision_step() -> None:
    increment = manual_event_increment(
        is_repeat=False,
        event_dt_sec=99.0,
        manual_step_rad=math.radians(3.0),
        manual_motion_speed_rad_s=4.0,
        motor_speed_limit_rad_s=10.0,
        manual_repeat_dt_max_sec=0.08,
        max_position_step=0.4,
    )
    assert increment == pytest.approx(math.radians(3.0))


@pytest.mark.parametrize("frequency", [20.0, 25.0])
def test_manual_repeat_stream_tracks_mode_speed(frequency: float) -> None:
    dt = 1.0 / frequency
    increments = [
        manual_event_increment(
            is_repeat=True,
            event_dt_sec=dt,
            manual_step_rad=math.radians(3.0),
            manual_motion_speed_rad_s=4.0,
            motor_speed_limit_rad_s=10.0,
            manual_repeat_dt_max_sec=0.08,
            max_position_step=0.4,
        )
        for _ in range(round(frequency))
    ]
    assert sum(increments) == pytest.approx(4.0)


def test_manual_repeat_caps_dt_speed_and_position_step() -> None:
    assert manual_event_increment(
        is_repeat=True,
        event_dt_sec=1.0,
        manual_step_rad=0.05,
        manual_motion_speed_rad_s=4.0,
        motor_speed_limit_rad_s=2.0,
        manual_repeat_dt_max_sec=0.08,
        max_position_step=0.1,
    ) == pytest.approx(0.1)
