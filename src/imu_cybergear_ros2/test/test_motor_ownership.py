from imu_cybergear_ros2.controller_state import ControllerState
from imu_cybergear_ros2.motor_motion import MotionSource
from imu_cybergear_ros2.motor_ownership import MotorCommandOwner

from .test_motor_manager import build_system, position_writes, switch_mode


def test_two_phase_flight_owner_gates_legacy_and_uses_existing_timer():
    node, state, manager = build_system()
    assert manager.command_owner is MotorCommandOwner.MANUAL
    manager.set_manual_targets({1: 0.2, 2: -0.2})

    reserved = manager.prepare_flight_ownership(100, 1, now=1.0)
    assert reserved.success
    assert manager.command_owner is MotorCommandOwner.FLIGHT_RESERVED
    assert manager.motion_source is MotionSource.IDLE
    assert node._desired_targets == node._current_targets
    assert position_writes(node) == []
    assert not manager.manual_step(1, 1.0, now=1.1)
    assert not manager.set_auto_targets({1: 0.0, 2: 0.0})

    committed = manager.commit_flight_ownership(100, 1, now=1.1)
    assert committed.success
    assert state.state is ControllerState.AUTO_RUNNING
    assert manager.command_owner is MotorCommandOwner.FLIGHT_CONTROL
    accepted = manager.set_flight_targets(
        100,
        1,
        0,
        {"axis_1": 0.8, "axis_2": -0.8},
        now=1.2,
    )
    # Test node has no configured logical channels, so an incomplete mapping
    # is rejected before touching its fake driver.
    assert not accepted.success


def test_flight_target_reuses_soft_limit_step_write_consistency_and_timeout():
    node, state, manager = build_system()
    node._motor_configs = [
        type("Channel", (), {"name": "a", "motor_id": 1})(),
        type("Channel", (), {"name": "b", "motor_id": 2})(),
    ]
    assert manager.prepare_flight_ownership(100, 1, now=1.0).success
    assert manager.commit_flight_ownership(100, 1, now=1.1).success
    assert manager.set_flight_targets(
        100, 1, 0, {"a": 2.0, "b": -2.0}, now=1.2
    ).success
    assert manager.motion_source is MotionSource.FLIGHT
    assert node._desired_targets == {1: 1.0, 2: -1.0}
    manager._motion_tick(now=1.21)
    manager._motion_tick(now=1.23)
    assert node._current_targets[1] <= 0.4
    assert node._current_targets[2] >= -0.4
    assert position_writes(node)

    manager._motion_tick(now=1.5)
    assert manager.command_owner is MotorCommandOwner.NONE
    assert manager.motion_source is MotionSource.IDLE
    assert node._desired_targets == node._current_targets
    assert not manager.set_auto_targets({1: 0.0, 2: 0.0})


def test_epoch_replay_and_newer_epoch_cannot_preempt_active_owner():
    _node, _state, manager = build_system()
    assert manager.prepare_flight_ownership(100, 1, now=1.0).success
    assert manager.commit_flight_ownership(100, 1, now=1.1).success
    busy = manager.prepare_flight_ownership(200, 1, now=1.2)
    assert not busy.success and busy.reason_code == "flight_owner_busy"
    assert manager.revoke_flight_ownership(100, 1).success
    assert manager.prepare_flight_ownership(200, 1, now=2.0).success
    delayed = manager.revoke_flight_ownership(100, 1)
    assert not delayed.success


def test_stale_reserve_cannot_quiesce_current_manual_target():
    node, _state, manager = build_system()
    assert manager.prepare_flight_ownership(100, 1, now=1.0).success
    assert manager.revoke_flight_ownership(100, 1).success
    assert manager.prepare_flight_ownership(200, 1, now=2.0).success
    assert manager.revoke_flight_ownership(200, 1).success
    manager.ownership.claim_legacy_for_state(auto=False)
    manager.set_manual_targets({1: 0.4, 2: -0.4})
    before = dict(node._desired_targets)
    rejected = manager.prepare_flight_ownership(100, 2, now=3.0)
    assert not rejected.success
    assert node._desired_targets == before
    assert manager.motion_source is MotionSource.MANUAL


def test_flight_write_failure_uses_existing_error_and_releases_owner():
    node, state, manager = build_system()
    node._motor_configs = [
        type("Channel", (), {"name": "a", "motor_id": 1})(),
        type("Channel", (), {"name": "b", "motor_id": 2})(),
    ]
    assert manager.prepare_flight_ownership(100, 1, now=1.0).success
    assert manager.commit_flight_ownership(100, 1, now=1.1).success
    assert manager.set_flight_targets(
        100, 1, 0, {"a": 0.5, "b": -0.5}, now=1.2
    ).success

    def fail(*_args):
        raise RuntimeError("injected Flight position write failure")

    node._driver.write_sdo_float = fail
    manager._motion_tick(now=1.21)
    manager._motion_tick(now=1.23)
    assert state.state is ControllerState.ERROR
    assert manager.command_owner is MotorCommandOwner.NONE
    assert manager.motion_source is MotionSource.IDLE
    assert node._current_targets == {1: 0.0, 2: 0.0}
    assert node._driver.stopped == [1, 2]


def test_explicit_operator_mode_toggle_reclaims_legacy_after_release():
    _node, state, manager = build_system()
    assert manager.prepare_flight_ownership(100, 1, now=1.0).success
    assert manager.commit_flight_ownership(100, 1, now=1.1).success
    assert manager.revoke_flight_ownership(100, 1).success
    assert manager.command_owner is MotorCommandOwner.NONE
    switch_mode(state, ControllerState.AUTO_RUNNING)
    switch_mode(state, ControllerState.MANUAL_RUNNING)
    assert manager.command_owner is MotorCommandOwner.MANUAL
