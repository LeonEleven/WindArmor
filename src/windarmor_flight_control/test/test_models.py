from dataclasses import FrozenInstanceError

import pytest

from windarmor_flight_control.core.authority import CommandAuthority
from windarmor_flight_control.core.models import FanCommand, FlightCommand
from windarmor_flight_control.testing import make_fake_flight_state


MOTOR_NAMES = ("axis_a", "axis_b", "axis_c", "axis_d")


def test_state_and_nested_values_are_immutable() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    command = FlightCommand(
        {name: 0.0 for name in MOTOR_NAMES},
        FanCommand(left=0.0, right=0.0),
    )

    mutations = (
        (state, "sequence", 2),
        (state.imu, "roll_rad", 1.0),
        (state.motors["axis_a"], "position_rad", 1.0),
        (state.fans.left, "applied_command", 1.0),
        (state.fans, "enabled", False),
        (state.system, "actuation_allowed", False),
        (command, "request_safe_stop", True),
        (command.fan_commands, "left", 1.0),
    )
    for value, field, replacement in mutations:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)
    with pytest.raises(TypeError):
        state.motors["axis_a"] = state.motors["axis_a"]


def test_command_copies_and_freezes_motor_mapping() -> None:
    source = {name: 0.0 for name in MOTOR_NAMES}
    command = FlightCommand(source, FanCommand(left=0.0, right=0.0))
    source["axis_a"] = 1.0

    assert command.motor_positions_rad is not None
    assert command.motor_positions_rad["axis_a"] == 0.0
    with pytest.raises(TypeError):
        command.motor_positions_rad["axis_a"] = 1.0


def test_state_copies_motor_mapping_before_freezing_it() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    source = dict(state.motors)
    copied_state = type(state)(
        timestamp_sec=state.timestamp_sec,
        sequence=state.sequence,
        imu=state.imu,
        motors=source,
        fans=state.fans,
        system=state.system,
    )

    source.pop("axis_a")

    assert set(copied_state.motors) == set(MOTOR_NAMES)


def test_unknown_feedback_uses_none_instead_of_physical_zero() -> None:
    state = make_fake_flight_state(MOTOR_NAMES, with_feedback=False)
    motor = state.motors["axis_a"]

    assert motor.has_feedback is False
    assert motor.position_rad is None
    assert motor.velocity_rad_s is None
    assert motor.torque_nm is None
    assert motor.temperature_c is None
    assert motor.feedback_age_sec is None


def test_authority_is_distinct_from_existing_motor_mode_string() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)

    assert state.system.command_authority is CommandAuthority.FLIGHT_CONTROL
    assert state.system.motor_control_mode == "AUTO"
