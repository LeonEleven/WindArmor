import pytest

from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
)
from windarmor_fan_controller.fan_ownership import FanCommandOwner


STOP_PWM = (800, 800)


def flight_ready_core() -> FanControlCore:
    core = FanControlCore(FanControlConfig())
    assert core.update_fan_enabled(True, 1.0)
    assert core.update_motor_mode("AUTO", 1.0)
    assert core.update_e_stop(False, 1.0)
    return core


@pytest.mark.parametrize("committed", [False, True])
def test_flight_revoke_preserves_latched_estop_state(committed: bool) -> None:
    core = flight_ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    if committed:
        assert core.commit_flight_ownership(100, 1, now=1.02).success

    assert core.update_e_stop(True, 1.03)
    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP

    result = core.revoke_flight_ownership(100, 1)

    assert result.success
    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP
    assert core.command_pwm == STOP_PWM
    assert core.ownership.owner is FanCommandOwner.NONE
    assert core.ownership.authority_epoch is None
    assert core.ownership.generation is None
    assert not core.safety_snapshot.passive_for_takeover


def test_flight_safe_stop_preserves_latched_estop_state() -> None:
    core = flight_ready_core()
    assert core.update_e_stop(True, 1.01)
    # Isolate the safe-stop handler from emergency_stop()'s eager owner cleanup.
    assert core.ownership.prepare(200, 2, now=1.02, safe=True).success
    assert core.ownership.commit(200, 2, now=1.03, safe=True).success

    result = core.accept_flight_safe_stop(200, 2, 0, now=1.04)

    assert result.success
    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP
    assert core.command_pwm == STOP_PWM


def test_rejected_late_flight_command_fallback_preserves_latched_estop() -> None:
    core = flight_ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    assert core.update_e_stop(True, 1.03)

    rejected = core.update_flight_command(
        100, 1, 0, 0.5, 0.5, now=1.04
    )
    assert rejected.reason_code == "flight_command_not_allowed"
    core.force_safe_stop(
        f"Flight command rejected: {rejected.reason_code}"
    )

    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP
    assert core.command_pwm == STOP_PWM
    assert core.ownership.owner is FanCommandOwner.NONE


@pytest.mark.parametrize("with_command", [False, True])
def test_flight_lease_timeout_preserves_latched_estop_state(
    with_command: bool,
) -> None:
    core = flight_ready_core()
    assert core.update_e_stop(True, 1.01)
    assert core.ownership.prepare(200, 2, now=1.02, safe=True).success
    if with_command:
        assert core.ownership.commit(200, 2, now=1.03, safe=True).success
        assert core.ownership.accept_command(
            200, 2, 7, now=1.04
        ).success

    timeout_at = 2.60 if not with_command else 1.30
    output = core.control_tick(timeout_at)

    assert core.e_stop_latched
    assert output.state is FanControlState.EMERGENCY_STOP
    assert output.command_pwm == STOP_PWM
    assert core.ownership.owner is FanCommandOwner.NONE


@pytest.mark.parametrize(
    "enabled,observation_at,tick_at",
    [
        (True, 1.10, 1.10),
        (False, 1.10, 1.10),
        (True, 1.10, 2.20),
    ],
)
def test_fan_enabled_updates_and_staleness_cannot_lower_estop(
    enabled: bool,
    observation_at: float,
    tick_at: float,
) -> None:
    core = flight_ready_core()
    assert core.update_e_stop(True, 1.01)

    assert core.update_fan_enabled(enabled, observation_at)
    output = core.control_tick(tick_at)

    assert core.e_stop_latched
    assert output.state is FanControlState.EMERGENCY_STOP
    assert output.command_pwm == STOP_PWM
    assert not core.safety_snapshot.passive_for_takeover


@pytest.mark.parametrize(
    "mode",
    ["MANUAL", "AUTO", "ERROR", "DISABLED", "EMERGENCY_STOP"],
)
def test_motor_mode_updates_cannot_lower_latched_estop(mode: str) -> None:
    core = flight_ready_core()
    assert core.update_e_stop(True, 1.01)

    assert core.update_motor_mode(mode, 1.10)

    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP
    assert core.command_pwm == STOP_PWM
    assert not core.safety_snapshot.passive_for_takeover


@pytest.mark.parametrize("generation", [0, 1])
def test_zero_generation_changes_cannot_lower_latched_estop(
    generation: int,
) -> None:
    core = flight_ready_core()
    assert core.update_zero_generation(0)
    assert core.update_e_stop(True, 1.01)

    assert core.update_zero_generation(generation)

    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP
    assert core.command_pwm == STOP_PWM


@pytest.mark.parametrize(
    "requested_state",
    [
        FanControlState.SAFE_STOP,
        FanControlState.MANUAL_DISARMED,
        FanControlState.DISABLED,
        FanControlState.FLIGHT_WAITING,
    ],
)
def test_ordinary_force_safe_stop_cannot_lower_latched_estop(
    requested_state: FanControlState,
) -> None:
    core = flight_ready_core()
    assert core.update_e_stop(True, 1.01)

    core.force_safe_stop("ordinary cleanup", state=requested_state)

    snapshot = core.safety_snapshot
    assert snapshot.e_stop_latched
    assert snapshot.control_state == "EMERGENCY_STOP"
    assert not snapshot.passive_for_takeover
    assert not snapshot.manual_armed
    assert not snapshot.legacy_auto_requested
    assert not snapshot.legacy_auto_active
    assert core.command_pwm == STOP_PWM


def test_normal_revoke_safe_stop_and_timeouts_keep_non_estop_contracts() -> None:
    core = flight_ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    assert core.revoke_flight_ownership(100, 1).success
    assert not core.e_stop_latched
    assert core.state is FanControlState.SAFE_STOP
    assert core.ownership.owner is FanCommandOwner.NONE

    assert core.prepare_flight_ownership(100, 2, now=1.03).success
    assert core.commit_flight_ownership(100, 2, now=1.04).success
    assert core.accept_flight_safe_stop(100, 2, 0, now=1.05).success
    assert not core.e_stop_latched
    assert core.state is FanControlState.SAFE_STOP
    assert core.ownership.owner is FanCommandOwner.NONE

    assert core.prepare_flight_ownership(100, 3, now=1.06).success
    output = core.control_tick(2.60)
    assert not core.e_stop_latched
    assert output.state is FanControlState.SAFE_STOP
    assert core.ownership.owner is FanCommandOwner.NONE


def test_explicit_reset_is_only_exit_and_old_flight_state_never_replays() -> None:
    core = flight_ready_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    assert core.update_flight_command(
        100, 1, 7, 1.0, 1.0, now=1.03
    ).success
    assert core.control_tick(1.04).command_pwm == (810, 810)

    assert core.update_e_stop(True, 1.05)
    core.force_safe_stop("runtime rollback")
    assert core.update_e_stop(False, 1.10)
    assert core.update_fan_enabled(True, 1.10)
    assert core.update_motor_mode("MANUAL", 1.10)
    assert core.e_stop_latched
    assert core.state is FanControlState.EMERGENCY_STOP

    reset, _ = core.reset_e_stop(1.11)
    assert reset
    assert not core.e_stop_latched
    assert core.state is FanControlState.MANUAL_DISARMED
    assert core.command_pwm == STOP_PWM
    assert core.ownership.owner is FanCommandOwner.NONE
    assert core.ownership.authority_epoch is None
    assert core.ownership.generation is None
    assert core.ownership.last_command_sequence is None
    assert core.ownership.last_valid_command_at is None
    assert not core.update_flight_command(
        100, 1, 8, 1.0, 1.0, now=1.12
    ).success
    assert not core.prepare_flight_ownership(100, 1, now=1.12).success
    assert core.control_tick(1.12).command_pwm == STOP_PWM

    assert core.prepare_flight_ownership(200, 2, now=1.13).success
    assert core.commit_flight_ownership(200, 2, now=1.14).success
    assert core.update_flight_command(
        200, 2, 0, 0.0, 0.0, now=1.15
    ).success
