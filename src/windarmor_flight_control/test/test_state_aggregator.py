from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from windarmor_flight_control.core.authority import CommandAuthority
from windarmor_flight_control.core.validation import validate_flight_state
from windarmor_flight_control.runtime.state_aggregator import StateAggregator

from .runtime_helpers import (
    imu_message,
    motor_message,
    relative_message,
    runtime_config,
)


MOTOR_NAMES = ("axis_a", "axis_b")


def populated_aggregator() -> StateAggregator:
    aggregator = StateAggregator(runtime_config(motor_names=list(MOTOR_NAMES)))
    aggregator.update_zero_generation(0)
    aggregator.update_imu_raw(imu_message(1), 10.0)
    aggregator.update_imu_relative(relative_message(1), 10.0)
    aggregator.update_motors(motor_message(MOTOR_NAMES), 10.0)
    return aggregator


def test_dry_run_system_truth_and_required_sensor_freshness() -> None:
    aggregator = populated_aggregator()
    state = aggregator.build_snapshot(10.1)
    validate_flight_state(state, MOTOR_NAMES)
    assert state.system.command_authority is CommandAuthority.NONE
    assert state.system.authority_generation == 0
    assert not state.system.flight_control_active
    assert not state.system.actuation_allowed
    assert state.system.required_inputs_fresh
    assert state.system.e_stop_active is None


def test_fan_state_is_not_part_of_default_required_inputs_fresh() -> None:
    state = populated_aggregator().build_snapshot(10.1)
    assert state.fans.enabled is None
    assert state.fans.control_state is None
    assert state.system.required_inputs_fresh


def test_observation_only_feedback_does_not_claim_control_safety_or_authority() -> None:
    aggregator = StateAggregator(runtime_config(motor_names=list(MOTOR_NAMES)))
    aggregator.update_zero_generation(0)
    aggregator.update_imu_raw(imu_message(1), 10.0)
    aggregator.update_imu_relative(relative_message(1), 10.0)
    aggregator.update_motors(
        motor_message(MOTOR_NAMES, healthy=False),
        10.0,
    )
    snapshot = aggregator.build_runtime_snapshot(10.1)
    state = snapshot.flight_state
    assert state.system.required_inputs_fresh
    assert all(not motor.healthy for motor in state.motors.values())
    assert snapshot.motor_safety is None and not snapshot.motor_safety_fresh
    assert snapshot.fan_safety is None and not snapshot.fan_safety_fresh
    assert state.fans.enabled is None and state.fans.control_state is None
    assert state.system.command_authority is CommandAuthority.NONE
    assert not state.system.flight_control_active
    assert not state.system.actuation_allowed


def test_motor_mode_stales_to_none_and_fan_control_states_agree() -> None:
    aggregator = populated_aggregator()
    aggregator.update_motor_mode("MANUAL", 10.0)
    aggregator.update_fan_control_state("DISABLED", 10.0)
    fresh = aggregator.build_snapshot(10.1)
    assert fresh.system.motor_control_mode == "MANUAL"
    assert fresh.system.fan_control_state == fresh.fans.control_state == "DISABLED"
    stale = aggregator.build_snapshot(11.1)
    assert stale.system.motor_control_mode is None
    assert stale.system.fan_control_state is None


def test_e_stop_startup_false_trigger_and_true_latch_are_fail_closed() -> None:
    aggregator = populated_aggregator()
    assert aggregator.build_snapshot(10.0).system.e_stop_active is None
    aggregator.update_e_stop(False)
    assert aggregator.build_snapshot(10.1).system.e_stop_active is None
    aggregator.update_e_stop(True)
    assert aggregator.build_snapshot(10.2).system.e_stop_active is True
    aggregator.update_e_stop(False)
    assert aggregator.build_snapshot(1000.0).system.e_stop_active is True


def test_snapshots_are_coherent_immutable_and_monotonic() -> None:
    aggregator = populated_aggregator()
    first = aggregator.build_snapshot(10.0)
    aggregator.update_fan_enabled(True, 10.1)
    second = aggregator.build_snapshot(10.1)
    assert first.sequence == 0 and second.sequence == 1
    assert first.timestamp_sec == 10.0 and second.timestamp_sec == 10.1
    assert first.fans.enabled is None
    assert second.fans.enabled is True
    with pytest.raises(FrozenInstanceError):
        first.system.actuation_allowed = True
    with pytest.raises(TypeError):
        first.motors["axis_a"] = first.motors["axis_a"]
    with pytest.raises(ValueError, match="backwards"):
        aggregator.build_snapshot(10.0)


def test_stale_imu_or_motor_clears_required_inputs_fresh() -> None:
    aggregator = populated_aggregator()
    state = aggregator.build_snapshot(11.0)
    assert not state.imu.fresh
    assert not all(motor.fresh for motor in state.motors.values())
    assert not state.system.required_inputs_fresh
