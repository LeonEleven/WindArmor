import math

import pytest

from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
    activity_to_pwm,
    attitude_activities,
    slew_pwm,
    update_hysteresis,
)


def enabled_core(*, require_motor: bool = False) -> FanControlCore:
    core = FanControlCore(
        FanControlConfig(require_motor_mode_for_manual=require_motor)
    )
    core.update_fan_enabled(True, 0.0)
    if require_motor:
        core.update_motor_mode("MANUAL", 0.0)
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
    assert core.step(0.05).state == FanControlState.MANUAL_WAITING


def test_auto_disable_always_succeeds_and_clears_manual_cache() -> None:
    core = enabled_core()
    core.update_manual_pair(1000, 1100, 0.0)
    success, _ = core.request_auto(False, 0.1)
    assert success
    output = core.step(0.1)
    assert output.state == FanControlState.MANUAL_WAITING
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
    assert core.step(0.2).state == FanControlState.MANUAL_WAITING
    core.update_manual_pair(1000, 1100, 0.3)
    assert core.step(1.31).state == FanControlState.DISABLED
    core.update_fan_enabled(True, 1.32)
    assert core.step(1.32).command_pwm == (800, 800)


def test_independent_e_stop_requires_post_event_fan_enable() -> None:
    core = enabled_core()
    core.emergency_stop()
    core.update_fan_enabled(False, 0.1)
    assert core.e_stop_latched
    core.update_fan_enabled(True, 0.2)
    assert not core.e_stop_latched
    assert core.step(0.2).state == FanControlState.MANUAL_WAITING


def test_unified_e_stop_requires_both_post_event_recoveries() -> None:
    core = enabled_core(require_motor=True)
    core.emergency_stop()
    core.update_fan_enabled(True, 0.1)
    assert core.e_stop_latched
    core.update_motor_mode("EMERGENCY_STOP", 0.1)
    assert core.e_stop_latched
    core.update_motor_mode("MANUAL", 0.2)
    assert not core.e_stop_latched
    assert core.step(0.2).state == FanControlState.MANUAL_WAITING


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
    output = core.step(0.1)
    assert output.state == FanControlState.MANUAL_WAITING
    assert output.command_pwm == (800, 800)
    assert not output.auto_enabled


def test_unified_manual_stops_when_motor_mode_times_out() -> None:
    core = enabled_core(require_motor=True)
    core.update_manual_pair(1000, 1100, 0.0)
    assert core.step(0.1).state == FanControlState.MANUAL_ACTIVE
    core.update_fan_enabled(True, 1.01)
    output = core.step(1.01)
    assert output.state == FanControlState.SAFE_STOP
    assert output.command_pwm == (800, 800)
