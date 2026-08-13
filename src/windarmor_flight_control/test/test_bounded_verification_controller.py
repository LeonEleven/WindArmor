from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms import BoundedVerificationController
from windarmor_flight_control.core.authority import CommandAuthority
from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.core.validation import validate_flight_command
from windarmor_flight_control.testing import make_fake_flight_state


MOTOR_NAMES = ("axis_a", "axis_b", "axis_c", "axis_d")


def controller(**overrides):
    values = dict(
        verification_controller_enabled=True,
        test_motor_name="axis_b",
        motor_test_offset_rad=0.125,
        fan_left_test_command=0.0,
        fan_right_test_command=0.0,
    )
    values.update(overrides)
    return BoundedVerificationController(MOTOR_NAMES, **values)


def state_with_positions(**positions):
    state = make_fake_flight_state(MOTOR_NAMES)
    motors = {
        name: replace(motor, position_rad=positions.get(name, index + 0.25))
        for index, (name, motor) in enumerate(state.motors.items())
    }
    return replace(state, motors=motors)


def normal_after_capture(instance, state=None):
    state = state or state_with_positions()
    return instance.update(state, 0.01)


def test_disabled_and_incomplete_configuration_are_fail_closed() -> None:
    state = state_with_positions()
    assert controller(verification_controller_enabled=False).update(
        state, 0.01
    ) == FlightCommand.safe_stop()
    assert controller(motor_test_offset_rad=None).update(
        state, 0.01
    ) == FlightCommand.safe_stop()
    assert controller(test_motor_name="unknown").update(
        state, 0.01
    ) == FlightCommand.safe_stop()


@pytest.mark.parametrize(
    "system_changes",
    [
        {"command_authority": CommandAuthority.NONE,
         "authority_epoch": 0, "authority_generation": 0},
        {"flight_control_active": False},
        {"actuation_allowed": False},
        {"required_inputs_fresh": False},
        {"e_stop_active": True},
    ],
)
def test_authority_and_system_preconditions_fail_closed(system_changes) -> None:
    state = state_with_positions()
    state = replace(state, system=replace(state.system, **system_changes))
    assert controller().update(state, 0.01) == FlightCommand.safe_stop()


@pytest.mark.parametrize(
    "imu_changes",
    [{"fresh": False}, {"valid": False, "fresh": False}],
)
def test_imu_must_be_valid_and_fresh(imu_changes) -> None:
    state = state_with_positions()
    state = replace(state, imu=replace(state.imu, **imu_changes))
    assert controller().update(state, 0.01) == FlightCommand.safe_stop()


@pytest.mark.parametrize(
    "motor_changes",
    [
        {"fresh": False, "healthy": False},
        {"valid": False, "fresh": False, "healthy": False},
        {"healthy": False},
        {"position_rad": None},
    ],
)
def test_every_motor_requires_usable_position_feedback(motor_changes) -> None:
    state = state_with_positions()
    motors = dict(state.motors)
    motors["axis_c"] = replace(motors["axis_c"], **motor_changes)
    state = replace(state, motors=motors)
    assert controller().update(state, 0.01) == FlightCommand.safe_stop()


def test_incomplete_motor_set_is_fail_closed() -> None:
    state = state_with_positions()
    motors = dict(state.motors)
    motors.pop("axis_d")
    assert controller().update(replace(state, motors=motors), 0.01) == (
        FlightCommand.safe_stop()
    )


def test_capture_builds_complete_feedback_relative_immutable_frame() -> None:
    state = state_with_positions(axis_a=-0.4, axis_b=0.7, axis_c=1.1, axis_d=-1.2)
    command = normal_after_capture(controller(), state)

    validate_flight_command(command, MOTOR_NAMES)
    assert command.motor_positions_rad == {
        "axis_a": -0.4,
        "axis_b": 0.825,
        "axis_c": 1.1,
        "axis_d": -1.2,
    }
    assert command.fan_commands.left == 0.0
    assert command.fan_commands.right == 0.0
    with pytest.raises(TypeError):
        command.motor_positions_rad["axis_a"] = 99.0


def test_configured_fan_commands_are_preserved_without_clamping() -> None:
    command = normal_after_capture(
        controller(fan_left_test_command=0.2, fan_right_test_command=0.3)
    )
    assert command.fan_commands.left == 0.2
    assert command.fan_commands.right == 0.3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fan_left_test_command", -0.01),
        ("fan_right_test_command", 1.01),
        ("fan_left_test_command", float("nan")),
        ("fan_right_test_command", float("inf")),
        ("motor_test_offset_rad", float("nan")),
        ("motor_test_offset_rad", float("inf")),
    ],
)
def test_invalid_numeric_configuration_is_fail_closed(field, value) -> None:
    assert controller(**{field: value}).update(
        state_with_positions(), 0.01
    ) == FlightCommand.safe_stop()


def test_finite_values_that_overflow_the_target_fail_closed() -> None:
    instance = controller(motor_test_offset_rad=1e308)
    state = state_with_positions(axis_b=1e308)
    assert instance.update(state, 0.01) == FlightCommand.safe_stop()


def test_offset_never_accumulates_and_live_feedback_does_not_move_baseline() -> None:
    instance = controller()
    initial = state_with_positions(axis_b=0.7)
    first = normal_after_capture(instance, initial)
    changed_feedback = state_with_positions(axis_b=0.9)
    second = instance.update(changed_feedback, 0.01)
    third = instance.update(changed_feedback, 0.01)

    assert first.motor_positions_rad["axis_b"] == pytest.approx(0.825)
    assert second.motor_positions_rad["axis_b"] == pytest.approx(0.825)
    assert third.motor_positions_rad["axis_b"] == pytest.approx(0.825)


def test_reset_clears_baseline_and_recaptures_from_the_next_valid_state() -> None:
    instance = controller()
    normal_after_capture(instance, state_with_positions(axis_b=0.7))
    instance.reset()
    new_state = state_with_positions(axis_b=1.0)

    assert instance.update(new_state, 0.01).motor_positions_rad["axis_b"] == (
        pytest.approx(1.125)
    )


@pytest.mark.parametrize(
    "session_change",
    [{"authority_generation": 2}, {"authority_epoch": 2}],
)
def test_authority_session_change_never_reuses_old_baseline(session_change) -> None:
    instance = controller()
    normal_after_capture(instance, state_with_positions(axis_b=0.7))
    new_state = state_with_positions(axis_b=1.0)
    new_state = replace(
        new_state,
        system=replace(new_state.system, **session_change),
    )

    assert instance.update(new_state, 0.01) == FlightCommand.safe_stop()
    command = instance.update(new_state, 0.01)
    assert command.motor_positions_rad["axis_b"] == pytest.approx(1.125)


def test_transient_invalid_input_discards_baseline() -> None:
    instance = controller()
    normal_after_capture(instance, state_with_positions(axis_b=0.7))
    stale = state_with_positions(axis_b=0.8)
    stale = replace(stale, imu=replace(stale.imu, fresh=False))
    assert instance.update(stale, 0.01) == FlightCommand.safe_stop()

    recovered = state_with_positions(axis_b=1.0)
    assert instance.update(recovered, 0.01).motor_positions_rad["axis_b"] == (
        pytest.approx(1.125)
    )
