import pytest

from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
    normalized_flight_command_to_pwm,
)
from windarmor_fan_controller.fan_ownership import FanCommandOwner


def ready_core() -> FanControlCore:
    core = FanControlCore(FanControlConfig())
    core.update_fan_enabled(True, 1.0)
    core.update_motor_mode("AUTO", 1.0)
    core.update_e_stop(False, 1.0)
    return core


def test_normalized_mapping_endpoints_stay_within_legacy_auto_max():
    config = FanControlConfig()
    assert normalized_flight_command_to_pwm(0.0, config) == config.fan_stop_pwm_us
    assert normalized_flight_command_to_pwm(1.0, config) == config.fan_auto_max_pwm_us
    assert normalized_flight_command_to_pwm(0.5, config) == 1300
    with pytest.raises(ValueError):
        normalized_flight_command_to_pwm(float("nan"), config)


def test_two_phase_flight_owner_blocks_legacy_and_preserves_slew():
    core = ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.ownership.owner is FanCommandOwner.FLIGHT_RESERVED
    assert core.command_pwm == (800, 800)
    assert core.request_manual(True, 1.02)[0] is False
    assert core.request_auto(True, 1.02)[0] is False
    assert core.commit_flight_ownership(100, 1, now=1.03).success
    assert core.update_flight_command(
        100, 1, 0, 1.0, 0.5, now=1.04
    ).success
    output = core.control_tick(1.05)
    assert output.state is FanControlState.FLIGHT_ACTIVE
    assert output.command_pwm == (810, 810)
    assert not core.update_flight_command(
        100, 1, 0, 1.0, 1.0, now=1.06
    ).success


def test_timeout_estop_replay_and_explicit_legacy_reclaim():
    core = ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    assert not core.prepare_flight_ownership(200, 1, now=1.03).success
    core.control_tick(1.28)
    assert core.ownership.owner is FanCommandOwner.NONE
    assert core.command_pwm == (800, 800)
    assert not core.update_flight_command(
        100, 1, 0, 1.0, 1.0, now=1.29
    ).success

    core.update_motor_mode("MANUAL", 1.30)
    assert core.request_manual(True, 1.31)[0]
    assert core.ownership.owner is FanCommandOwner.LEGACY_MANUAL
    core.emergency_stop()
    assert core.ownership.owner is FanCommandOwner.NONE
    assert core.command_pwm == (800, 800)


def test_safe_stop_revokes_without_auto_legacy_recovery():
    core = ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    result = core.accept_flight_safe_stop(100, 1, 0, now=1.03)
    assert result.success
    assert core.ownership.owner is FanCommandOwner.NONE
    assert not core.manual_armed and not core.auto_requested
    assert core.command_pwm == (800, 800)
