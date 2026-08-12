import math
from pathlib import Path

import pytest

from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
    apply_response_curve,
    activity_to_pwm,
    attitude_activities,
    slew_pwm,
    update_hysteresis,
)


CURVE_EXPECTATIONS = {
    "linear": (0.0, 0.25, 0.5, 0.75, 1.0),
    "smoothstep": (0.0, 0.15625, 0.5, 0.84375, 1.0),
    "quadratic": (0.0, 0.0625, 0.25, 0.5625, 1.0),
}


def enabled_core(*, require_motor: bool = False) -> FanControlCore:
    core = FanControlCore(
        FanControlConfig(require_motor_mode_for_manual=require_motor)
    )
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("MANUAL", 0.0)
    assert core.request_manual(True, 0.0)[0]
    assert core.update_manual_pair(800, 800, 0.0)
    return core


def auto_ready_core() -> FanControlCore:
    core = enabled_core(require_motor=True)
    core.update_motor_mode("AUTO", 0.0)
    core.update_pose(0.0, 0.0, 0.0)
    return core


@pytest.mark.parametrize(
    ("roll_deg", "pitch_deg", "expected"),
    [
        (0.0, 10.0, (10.0, 10.0)),
        (0.0, -10.0, (10.0, 10.0)),
        (-20.0, 5.0, (20.0, 5.0)),
        (20.0, 5.0, (5.0, 20.0)),
        (0.0, 0.0, (0.0, 0.0)),
    ],
)
def test_attitude_activity_formula(roll_deg, pitch_deg, expected) -> None:
    assert attitude_activities(
        math.radians(roll_deg), math.radians(pitch_deg)
    ) == pytest.approx(expected)


def test_hysteresis_mapping_and_slew() -> None:
    config = FanControlConfig()
    assert not update_hysteresis(4.0, False, on_deg=5.0, off_deg=3.0)
    assert update_hysteresis(5.0, False, on_deg=5.0, off_deg=3.0)
    assert update_hysteresis(4.0, True, on_deg=5.0, off_deg=3.0)
    assert not update_hysteresis(2.9, True, on_deg=5.0, off_deg=3.0)
    assert activity_to_pwm(5.0, True, config) == 1200
    assert activity_to_pwm(45.0, True, config) == 1400
    assert activity_to_pwm(90.0, True, config) == 1400
    assert activity_to_pwm(10.0, False, config) == 800
    assert slew_pwm(800, 1200, 10, 20) == 810
    assert slew_pwm(1200, 800, 10, 20) == 1180


@pytest.mark.parametrize("curve_name", CURVE_EXPECTATIONS)
def test_response_curve_exact_values_clamps_and_is_finite(curve_name) -> None:
    inputs = (0.0, 0.25, 0.5, 0.75, 1.0)
    outputs = [apply_response_curve(value, curve_name) for value in inputs]
    assert outputs == pytest.approx(CURVE_EXPECTATIONS[curve_name])
    assert apply_response_curve(-1.0, curve_name) == 0.0
    assert apply_response_curve(2.0, curve_name) == 1.0
    assert all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in outputs)
    assert outputs == sorted(outputs)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_response_curve_rejects_non_finite_input(bad) -> None:
    with pytest.raises(ValueError):
        apply_response_curve(bad, "smoothstep")


def test_invalid_response_curve_is_rejected() -> None:
    with pytest.raises(ValueError):
        apply_response_curve(0.5, "cubic")
    with pytest.raises(ValueError):
        FanControlConfig(fan_response_curve="cubic").validate()


def test_response_curve_shapes_relative_to_linear() -> None:
    assert apply_response_curve(0.25, "smoothstep") < apply_response_curve(
        0.25, "linear"
    )
    assert apply_response_curve(0.5, "smoothstep") == apply_response_curve(
        0.5, "linear"
    )
    assert apply_response_curve(0.75, "smoothstep") > apply_response_curve(
        0.75, "linear"
    )
    for x in (0.01, 0.25, 0.5, 0.75, 0.99):
        assert apply_response_curve(x, "quadratic") <= apply_response_curve(
            x, "linear"
        )


@pytest.mark.parametrize(
    ("curve_name", "activity_deg", "expected_pwm"),
    [
        ("linear", 15.0, 1250),
        ("smoothstep", 15.0, 1231),
        ("smoothstep", 25.0, 1300),
        ("smoothstep", 35.0, 1369),
        ("quadratic", 25.0, 1250),
    ],
)
def test_activity_to_pwm_uses_selected_curve_and_existing_rounding(
    curve_name, activity_deg, expected_pwm
) -> None:
    config = FanControlConfig(fan_response_curve=curve_name)
    assert activity_to_pwm(activity_deg, True, config) == expected_pwm


def test_pwm_mapping_boundaries_and_limits_for_every_curve() -> None:
    for curve_name in CURVE_EXPECTATIONS:
        config = FanControlConfig(fan_response_curve=curve_name)
        assert activity_to_pwm(5.0, True, config) == 1200
        assert activity_to_pwm(45.0, True, config) == 1400
        assert activity_to_pwm(90.0, True, config) == 1400
        assert activity_to_pwm(20.0, False, config) == 800


def test_default_config_uses_smoothstep_without_changing_pwm_limits() -> None:
    config = FanControlConfig()
    assert config.fan_response_curve == "smoothstep"
    assert config.fan_auto_max_pwm_us == 1400
    assert config.max_pwm_us == 2200


@pytest.mark.parametrize(
    "overrides",
    [
        {"fan_deadband_off_deg": 5.0},
        {"fan_deadband_on_deg": 45.0},
        {"fan_start_pwm_us": 700},
        {"fan_auto_max_pwm_us": 2300},
        {"rise_step_pwm_us": 0},
        {"imu_timeout_sec": 0.0},
        {"manual_command_timeout_sec": math.inf},
        {"fan_flight_handoff_timeout_sec": 0.0},
        {"fan_flight_handoff_timeout_sec": math.nan},
        {"fan_flight_command_timeout_sec": 0.0},
        {"fan_stop_pwm_us": math.inf},
        {"fan_deadband_on_deg": math.nan},
        {"fan_response_curve": "LINEAR"},
    ],
)
def test_invalid_configuration_is_rejected(overrides) -> None:
    values = FanControlConfig().__dict__ | overrides
    with pytest.raises(ValueError):
        FanControlConfig(**values).validate()


def test_pair_is_atomic_and_out_of_range_does_not_refresh() -> None:
    core = enabled_core()
    assert core.update_manual_pair(1000, 1100, 0.0)
    assert core.step(0.1).command_pwm == (1000, 1100)
    assert not core.update_manual_pair(1200, 9999, 0.4)
    assert core.step(0.51).command_pwm == (800, 800)


def test_side_freshness_is_independent() -> None:
    core = enabled_core()
    assert core.update_manual_pair(1000, 1100, 0.0)
    assert core.update_manual_side(0, 1200, 0.4)
    output = core.step(0.6)
    assert output.state == FanControlState.MANUAL_ACTIVE
    assert output.command_pwm == (1200, 800)
    output = core.step(0.91)
    assert output.state == FanControlState.MANUAL_WAITING
    assert output.command_pwm == (800, 800)


def test_auto_enable_requires_all_fresh_inputs() -> None:
    core = FanControlCore(FanControlConfig())
    success, message = core.request_auto(True, 0.0)
    assert not success
    assert "电机模式" in message
    assert not core.auto_requested


@pytest.mark.parametrize(
    ("prepare", "now", "message_fragment"),
    [
        (
            lambda core: (
                core.update_fan_enabled(True, 0.0),
                core.update_motor_mode("MANUAL", 0.0),
                core.update_pose(0.0, 0.0, 0.0),
            ),
            0.1,
            "电机模式",
        ),
        (
            lambda core: (
                core.update_fan_enabled(True, 0.0),
                core.update_motor_mode("AUTO", 0.0),
                core.update_pose(0.0, 0.0, 0.0),
            ),
            1.01,
            "电机模式",
        ),
        (
            lambda core: (
                core.update_fan_enabled(False, 0.0),
                core.update_motor_mode("AUTO", 0.0),
                core.update_pose(0.0, 0.0, 0.0),
            ),
            0.1,
            "底层风扇",
        ),
        (
            lambda core: (
                core.update_fan_enabled(True, 0.0),
                core.update_motor_mode("AUTO", 0.9),
                core.update_pose(0.0, 0.0, 0.9),
            ),
            1.01,
            "enabled",
        ),
        (
            lambda core: (
                core.update_fan_enabled(True, 0.9),
                core.update_motor_mode("AUTO", 0.9),
                core.update_pose(0.0, 0.0, 0.0),
            ),
            1.01,
            "姿态",
        ),
    ],
)
def test_each_auto_precondition_is_fail_closed(
    prepare, now, message_fragment
) -> None:
    core = FanControlCore(FanControlConfig())
    prepare(core)
    success, message = core.request_auto(True, now)
    assert not success
    assert message_fragment in message
    assert not core.auto_requested


def test_unrecovered_e_stop_rejects_auto() -> None:
    core = auto_ready_core()
    core.emergency_stop()
    success, message = core.request_auto(True, 0.1)
    assert not success
    assert "急停" in message


def test_auto_waits_for_post_enable_pose_and_then_slews() -> None:
    core = auto_ready_core()
    success, _ = core.request_auto(True, 0.05)
    assert success
    assert core.step(0.06).state == FanControlState.AUTO_WAITING
    core.update_pose(math.radians(-20.0), 0.0, 0.07)
    output = core.step(0.08)
    assert output.state == FanControlState.AUTO_ACTIVE
    assert output.auto_target_pwm[0] > 1200
    assert output.auto_target_pwm[1] == 800
    assert output.command_pwm == (810, 800)


def test_both_fans_use_same_curve_with_independent_hysteresis() -> None:
    core = FanControlCore(
        FanControlConfig(
            require_motor_mode_for_manual=True,
            fan_response_curve="quadratic",
        )
    )
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("AUTO", 0.0)
    core.update_pose(0.0, 0.0, 0.0)
    assert core.request_auto(True, 0.01)[0]
    core.update_pose(math.radians(-25.0), math.radians(15.0), 0.02)
    output = core.step(0.03)
    assert output.auto_target_pwm == (1250, 1212)

    core.update_pose(math.radians(-4.0), 0.0, 0.04)
    output = core.step(0.05)
    assert output.auto_target_pwm == (1200, 800)


def test_auto_condition_loss_clears_request_and_stops_immediately() -> None:
    core = auto_ready_core()
    assert core.request_auto(True, 0.01)[0]
    core.update_pose(0.0, math.radians(20.0), 0.02)
    assert core.step(0.03).auto_active
    core.update_motor_mode("MANUAL", 0.04)
    output = core.step(0.04)
    assert not output.auto_enabled
    assert output.command_pwm == (800, 800)
    core.update_motor_mode("AUTO", 0.05)
    core.update_pose(0.0, math.radians(20.0), 0.05)
    assert core.step(0.05).state == FanControlState.MANUAL_DISARMED


def test_auto_disable_always_succeeds_and_clears_manual_cache() -> None:
    core = enabled_core()
    core.update_manual_pair(1000, 1100, 0.0)
    success, _ = core.request_auto(False, 0.1)
    assert success
    output = core.step(0.1)
    assert output.state == FanControlState.MANUAL_DISARMED
    assert output.command_pwm == (800, 800)


def test_pose_timeout_and_zero_generation_clear_auto() -> None:
    core = auto_ready_core()
    core.update_zero_generation(0)
    core.update_pose(0.0, 0.0, 0.005)
    assert core.request_auto(True, 0.01)[0]
    core.update_pose(0.0, math.radians(10.0), 0.02)
    assert core.step(0.03).auto_active
    assert core.step(0.23).command_pwm == (800, 800)
    assert not core.auto_requested

    core.update_motor_mode("AUTO", 0.24)
    core.update_fan_enabled(True, 0.24)
    core.update_pose(0.0, 0.0, 0.24)
    assert core.request_auto(True, 0.25)[0]
    core.update_zero_generation(1)
    assert not core.auto_requested
    assert core.command_pwm == (800, 800)


def test_first_zero_generation_discards_pose_received_before_it() -> None:
    core = auto_ready_core()
    core.update_zero_generation(0)
    success, message = core.request_auto(True, 0.01)
    assert not success
    assert "姿态" in message


def test_bottom_disabled_and_timeout_clear_caches() -> None:
    core = enabled_core()
    core.update_manual_pair(1000, 1100, 0.0)
    core.update_fan_enabled(False, 0.1)
    assert core.step(0.1).state == FanControlState.DISABLED
    core.update_fan_enabled(True, 0.2)
    core.update_motor_mode("MANUAL", 0.2)
    assert core.step(0.2).state == FanControlState.DISABLED
    assert core.request_manual(True, 0.21)[0]
    assert core.update_manual_pair(800, 800, 0.22)
    assert core.update_manual_pair(1000, 1100, 0.3)
    assert core.step(1.31).state == FanControlState.DISABLED
    core.update_fan_enabled(True, 1.32)
    assert core.step(1.32).command_pwm == (800, 800)


def test_independent_e_stop_requires_explicit_reset() -> None:
    core = enabled_core()
    core.emergency_stop()
    core.update_fan_enabled(False, 0.1)
    assert core.e_stop_latched
    core.update_fan_enabled(True, 0.2)
    core.update_motor_mode("MANUAL", 0.2)
    core.update_e_stop(False, 0.2)
    assert core.e_stop_latched
    assert core.reset_e_stop(0.2)[0]
    assert not core.e_stop_latched
    assert core.step(0.2).state == FanControlState.MANUAL_DISARMED


def test_unified_e_stop_requires_explicit_reset_after_observations() -> None:
    core = enabled_core(require_motor=True)
    core.emergency_stop()
    core.update_fan_enabled(True, 0.1)
    assert core.e_stop_latched
    core.update_motor_mode("EMERGENCY_STOP", 0.1)
    assert core.e_stop_latched
    core.update_motor_mode("MANUAL", 0.2)
    core.update_e_stop(False, 0.2)
    assert core.e_stop_latched
    assert core.reset_e_stop(0.2)[0]
    assert core.step(0.2).state == FanControlState.MANUAL_DISARMED


def test_unified_e_stop_recovery_does_not_restore_old_data() -> None:
    core = enabled_core(require_motor=True)
    core.update_motor_mode("AUTO", 0.0)
    core.update_pose(0.0, math.radians(20.0), 0.0)
    assert core.request_auto(True, 0.01)[0]
    core.update_pose(0.0, math.radians(20.0), 0.02)
    assert core.step(0.03).auto_active
    core.emergency_stop()
    core.update_fan_enabled(True, 0.1)
    core.update_motor_mode("AUTO", 0.1)
    core.update_e_stop(False, 0.1)
    assert core.reset_e_stop(0.1)[0]
    output = core.step(0.1)
    assert output.state == FanControlState.MANUAL_DISARMED
    assert output.command_pwm == (800, 800)
    assert not output.auto_enabled


def test_unified_manual_stops_when_motor_mode_times_out() -> None:
    core = enabled_core(require_motor=True)
    core.update_manual_pair(1000, 1100, 0.0)
    assert core.step(0.1).state == FanControlState.MANUAL_ACTIVE
    core.update_fan_enabled(True, 1.01)
    output = core.step(1.01)
    assert output.state == FanControlState.MANUAL_DISARMED
    assert output.command_pwm == (800, 800)


def test_yaml_defaults_select_smoothstep_and_preserve_pwm_limits() -> None:
    config = (
        Path(__file__).parents[1] / "config" / "fan_params.yaml"
    ).read_text(encoding="utf-8")
    assert 'fan_response_curve: "smoothstep"' in config
    assert "fan_auto_max_pwm_us: 1400" in config
    assert "max_pwm_us: 2200" in config


# ---------------------------------------------------------------------------
# 风扇安全与确定性加固回归规格
# ---------------------------------------------------------------------------


def prepared_auto_core() -> FanControlCore:
    core = FanControlCore(
        FanControlConfig(require_motor_mode_for_manual=True)
    )
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("AUTO", 0.0)
    core.update_pose(0.0, 0.0, 0.0)
    assert core.request_auto(True, 0.01)[0]
    core.update_pose(0.0, math.radians(20.0), 0.02)
    return core


def test_only_control_tick_advances_auto_slew_in_either_direction() -> None:
    core = prepared_auto_core()
    first = core.control_tick(0.03)
    assert first.command_pwm == (810, 810)

    for timestamp in (0.031, 0.032, 0.033):
        core.update_pose(0.0, math.radians(25.0), timestamp)
        core.update_motor_mode("AUTO", timestamp)
        core.update_fan_enabled(True, timestamp)
        assert core.command_pwm == (810, 810)

    assert core.control_tick(0.04).command_pwm == (820, 820)
    core.update_pose(0.0, 0.0, 0.041)
    assert core.command_pwm == (820, 820)
    assert core.control_tick(0.05).command_pwm == (800, 800)


@pytest.mark.parametrize("event", ["e_stop", "disabled", "unknown", "pose"])
def test_safety_events_force_immediate_stop(event: str) -> None:
    core = prepared_auto_core()
    assert core.control_tick(0.03).command_pwm == (810, 810)

    if event == "e_stop":
        core.update_e_stop(True, 0.04)
    elif event == "disabled":
        core.update_fan_enabled(False, 0.04)
    elif event == "unknown":
        assert not core.update_motor_mode("UNKNOWN", 0.04)
    else:
        core.invalidate_pose()

    assert core.command_pwm == (800, 800)
    assert core.take_immediate_stop()


def test_e_stop_heartbeats_and_false_input_never_auto_reset_latch() -> None:
    core = prepared_auto_core()
    core.control_tick(0.03)
    core.update_e_stop(True, 0.04)

    for timestamp in (0.05, 0.06, 0.07):
        core.update_fan_enabled(True, timestamp)
        core.update_motor_mode("MANUAL", timestamp)
        core.update_pose(0.0, 0.0, timestamp)
        assert not core.update_manual_pair(1000, 1000, timestamp)
    core.update_e_stop(False, 0.08)

    assert core.e_stop_latched
    assert core.control_tick(0.08).command_pwm == (800, 800)


@pytest.mark.parametrize(
    ("prepare", "message_fragment"),
    [
        (lambda core: None, "急停输入"),
        (lambda core: core.update_e_stop(False, 0.1), "enabled"),
        (
            lambda core: (
                core.update_e_stop(False, 0.1),
                core.update_fan_enabled(False, 0.1),
            ),
            "enabled",
        ),
        (
            lambda core: (
                core.update_e_stop(False, 0.1),
                core.update_fan_enabled(True, 0.1),
            ),
            "电机模式",
        ),
        (
            lambda core: (
                core.update_e_stop(False, 0.1),
                core.update_fan_enabled(True, 0.1),
                core.update_motor_mode("ERROR", 0.1),
            ),
            "电机模式",
        ),
    ],
)
def test_reset_e_stop_reports_missing_or_unsafe_preconditions(
    prepare, message_fragment
) -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(True, 0.0)
    prepare(core)
    success, message = core.reset_e_stop(0.2)
    assert not success
    assert message_fragment in message
    assert core.e_stop_latched


def test_explicit_e_stop_reset_keeps_every_control_path_disarmed() -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(True, 0.0)
    core.update_e_stop(False, 0.1)
    core.update_fan_enabled(True, 0.1)
    core.update_motor_mode("MANUAL", 0.1)

    success, _ = core.reset_e_stop(0.2)
    assert success
    assert not core.e_stop_latched
    assert not core.auto_requested
    assert not core.manual_armed
    assert core.command_pwm == (800, 800)
    assert core.state == FanControlState.MANUAL_DISARMED

    core.update_e_stop(True, 0.3)
    assert core.e_stop_latched
    assert core.state == FanControlState.EMERGENCY_STOP


def test_reset_e_stop_rejects_stale_fan_and_motor_observations() -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(True, 0.0)
    core.update_e_stop(False, 2.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("MANUAL", 2.0)
    assert not core.reset_e_stop(2.0)[0]

    core.update_fan_enabled(True, 2.1)
    core.update_motor_mode("MANUAL", 0.0)
    success, message = core.reset_e_stop(2.1)
    assert not success
    assert "电机模式" in message


def test_manual_authorization_rejects_each_unsafe_condition() -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(True, 0.0)
    assert not core.request_manual(True, 0.1)[0]

    core = FanControlCore(FanControlConfig())
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(False, 0.0)
    core.update_motor_mode("MANUAL", 0.0)
    assert not core.request_manual(True, 0.1)[0]

    core = FanControlCore(FanControlConfig())
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("ERROR", 0.0)
    assert not core.request_manual(True, 0.1)[0]

    core = prepared_auto_core()
    assert not core.request_manual(True, 0.03)[0]
    assert core.command_pwm == (800, 800)


def test_auto_fault_rejects_background_manual_heartbeats_until_rearmed() -> None:
    core = prepared_auto_core()
    core.control_tick(0.03)
    core.update_motor_mode("MANUAL", 0.04)
    for timestamp in (0.05, 0.06, 0.07):
        assert not core.update_manual_pair(1200, 1200, timestamp)
        assert core.control_tick(timestamp).command_pwm == (800, 800)
    assert not core.manual_armed
    assert core.state == FanControlState.MANUAL_DISARMED


def test_manual_authorization_requires_new_pair_stop_baseline() -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("MANUAL", 0.0)

    success, _ = core.request_manual(True, 0.1)
    assert success
    assert core.manual_armed
    assert core.state == FanControlState.MANUAL_WAITING_FOR_NEUTRAL
    assert not core.update_manual_pair(1200, 1200, 0.11)
    assert core.update_manual_pair(800, 800, 0.12)
    assert core.state == FanControlState.MANUAL_WAITING
    assert core.update_manual_pair(1200, 1210, 0.13)
    assert core.control_tick(0.14).command_pwm == (1200, 1210)

    assert core.request_manual(False, 0.15)[0]
    assert core.command_pwm == (800, 800)
    assert not core.manual_armed
    assert core.request_manual(True, 0.16)[0]
    assert not core.update_manual_pair(1200, 1200, 0.17)


def test_unknown_motor_mode_invalidates_cache_and_all_authorizations() -> None:
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("MANUAL", 0.0)
    assert core.request_manual(True, 0.01)[0]
    assert core.update_manual_pair(800, 800, 0.02)
    assert core.update_manual_pair(1100, 1100, 0.03)
    assert core.control_tick(0.04).command_pwm == (1100, 1100)

    assert not core.update_motor_mode("not-a-mode", 0.05)
    assert core._motor_mode is None
    assert core._motor_mode_at is None
    assert not core.auto_requested
    assert not core.manual_armed
    assert core.command_pwm == (800, 800)

    core.update_motor_mode("MANUAL", 0.06)
    assert not core.update_manual_pair(1100, 1100, 0.07)
    assert core.control_tick(0.08).command_pwm == (800, 800)
