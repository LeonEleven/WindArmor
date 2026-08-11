from dataclasses import replace

import pytest

from windarmor_flight_control.core.authority import AuthorityGrant, CommandAuthority
from windarmor_flight_control.core.models import (
    FanChannelState,
    FanCommand,
    FlightCommand,
)
from windarmor_flight_control.core.validation import (
    FlightValidationError,
    validate_authority_grant,
    validate_flight_command,
    validate_flight_state,
)
from windarmor_flight_control.testing import make_fake_flight_state


MOTOR_NAMES = ("axis_a", "axis_b", "axis_c", "axis_d")


def command_with(*, left: float = 0.0, right: float = 1.0) -> FlightCommand:
    return FlightCommand(
        motor_positions_rad={name: 0.0 for name in MOTOR_NAMES},
        fan_commands=FanCommand(left=left, right=right),
    )


@pytest.mark.parametrize("left,right", [(0.0, 0.0), (1.0, 1.0), (0.25, 0.75)])
def test_fan_command_accepts_closed_normalized_range(left: float, right: float) -> None:
    validate_flight_command(command_with(left=left, right=right), MOTOR_NAMES)


@pytest.mark.parametrize(
    "value", [-0.001, 1.001, float("nan"), float("inf"), float("-inf")]
)
def test_fan_command_rejects_out_of_range_or_nonfinite(value: float) -> None:
    with pytest.raises(FlightValidationError):
        validate_flight_command(command_with(left=value), MOTOR_NAMES)


def test_motor_command_requires_exact_complete_key_set() -> None:
    complete = command_with()
    validate_flight_command(complete, MOTOR_NAMES)

    missing = FlightCommand(
        motor_positions_rad={name: 0.0 for name in MOTOR_NAMES[:-1]},
        fan_commands=complete.fan_commands,
    )
    with pytest.raises(FlightValidationError, match="missing motors"):
        validate_flight_command(missing, MOTOR_NAMES)

    unknown_targets = dict(complete.motor_positions_rad)
    unknown_targets["unknown"] = 0.0
    unknown = FlightCommand(unknown_targets, complete.fan_commands)
    with pytest.raises(FlightValidationError, match="unknown motors"):
        validate_flight_command(unknown, MOTOR_NAMES)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_motor_command_rejects_nonfinite_target(value: float) -> None:
    targets = {name: 0.0 for name in MOTOR_NAMES}
    targets["axis_b"] = value
    command = FlightCommand(targets, FanCommand(left=0.0, right=0.0))

    with pytest.raises(FlightValidationError, match="must be finite"):
        validate_flight_command(command, MOTOR_NAMES)


def test_state_accepts_valid_and_explicitly_unknown_feedback() -> None:
    validate_flight_state(make_fake_flight_state(MOTOR_NAMES), MOTOR_NAMES)
    validate_flight_state(
        make_fake_flight_state(MOTOR_NAMES, with_feedback=False), MOTOR_NAMES
    )


def test_state_rejects_negative_age_and_nonfinite_value() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    bad_motor = replace(
        state.motors["axis_a"], feedback_age_sec=-0.1, position_rad=float("nan")
    )
    motors = dict(state.motors)
    motors["axis_a"] = bad_motor

    with pytest.raises(FlightValidationError) as raised:
        validate_flight_state(replace(state, motors=motors), MOTOR_NAMES)
    assert "must not be negative" in str(raised.value)
    assert "must be finite" in str(raised.value)


def test_state_rejects_feedback_values_when_presence_is_false() -> None:
    state = make_fake_flight_state(MOTOR_NAMES, with_feedback=False)
    motors = dict(state.motors)
    motors["axis_a"] = replace(motors["axis_a"], position_rad=0.0)

    with pytest.raises(FlightValidationError, match="has values"):
        validate_flight_state(replace(state, motors=motors), MOTOR_NAMES)


def test_state_rejects_valid_imu_with_missing_measurement() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)

    with pytest.raises(FlightValidationError, match="complete measurement"):
        validate_flight_state(
            replace(state, imu=replace(state.imu, relative_pitch_rad=None)),
            MOTOR_NAMES,
        )


def test_state_rejects_healthy_motor_with_fault_flags() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    motors = dict(state.motors)
    motors["axis_a"] = replace(motors["axis_a"], fault_flags=1)

    with pytest.raises(FlightValidationError, match="zero fault_flags"):
        validate_flight_state(replace(state, motors=motors), MOTOR_NAMES)


def test_state_rejects_inconsistent_fan_output_presence() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    bad_fans = replace(
        state.fans,
        left=FanChannelState(applied_command=None, output_known=True),
    )

    with pytest.raises(FlightValidationError, match="output_known conflicts"):
        validate_flight_state(replace(state, fans=bad_fans), MOTOR_NAMES)


def test_state_rejects_actuation_during_estop() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)
    bad_system = replace(state.system, e_stop_active=True)

    with pytest.raises(FlightValidationError, match="e-stop"):
        validate_flight_state(replace(state, system=bad_system), MOTOR_NAMES)


def test_state_rejects_missing_required_substate_explicitly() -> None:
    state = make_fake_flight_state(MOTOR_NAMES)

    with pytest.raises(FlightValidationError, match="imu must be an ImuState"):
        validate_flight_state(replace(state, imu=None), MOTOR_NAMES)


def test_command_rejects_missing_fan_command_explicitly() -> None:
    command = command_with()

    with pytest.raises(FlightValidationError, match="must be a FanCommand"):
        validate_flight_command(replace(command, fan_commands=None), MOTOR_NAMES)


def test_authority_grant_reserves_nonnegative_generation_and_sequence() -> None:
    validate_authority_grant(
        AuthorityGrant(CommandAuthority.FLIGHT_CONTROL, generation=4, sequence=8)
    )
    with pytest.raises(FlightValidationError, match="generation"):
        validate_authority_grant(
            AuthorityGrant(CommandAuthority.FLIGHT_CONTROL, generation=-1, sequence=8)
        )
