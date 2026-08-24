import math
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms.example_algorithm_controller import (
    ExampleAlgorithmController,
    MAX_FAN_COMMAND,
    MAX_TARGET_OFFSET_RAD,
)
from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.core.validation import validate_flight_command
from windarmor_flight_control.runtime.controller_loader import load_controller
from windarmor_flight_control.testing import (
    make_fake_flight_state,
    make_stale_flight_state,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
)


def state_with_pitch(pitch_rad: float, *, baseline: float = 0.0):
    state = make_fake_flight_state(MOTOR_NAMES)
    motors = {
        name: replace(motor, position_rad=baseline)
        for name, motor in state.motors.items()
    }
    return replace(
        state,
        imu=replace(
            state.imu,
            pitch_rad=pitch_rad,
            relative_pitch_rad=pitch_rad,
        ),
        motors=motors,
    )


def test_reset_is_callable_and_recaptures_motor_baseline() -> None:
    controller = ExampleAlgorithmController(MOTOR_NAMES)
    first = controller.update(state_with_pitch(0.0, baseline=0.2), 0.02)
    controller.reset()
    second = controller.update(state_with_pitch(0.0, baseline=-0.3), 0.02)

    assert first.motor_positions_rad is not None
    assert second.motor_positions_rad is not None
    assert first.motor_positions_rad["left_pitch"] == pytest.approx(0.2)
    assert second.motor_positions_rad["left_pitch"] == pytest.approx(-0.3)


def test_neutral_input_holds_complete_frame_and_stops_fans() -> None:
    command = ExampleAlgorithmController(MOTOR_NAMES).update(
        state_with_pitch(0.0), 0.02
    )

    validate_flight_command(command, MOTOR_NAMES)
    assert command.motor_positions_rad == {name: 0.0 for name in MOTOR_NAMES}
    assert command.fan_commands is not None
    assert command.fan_commands.left == 0.0
    assert command.fan_commands.right == 0.0


@pytest.mark.parametrize(
    ("pitch_rad", "target_rad", "fan_left", "fan_right"),
    [
        (0.10, 0.025, 0.05, 0.0),
        (-0.10, -0.025, 0.0, 0.05),
    ],
)
def test_positive_and_negative_pitch_are_explicit(
    pitch_rad, target_rad, fan_left, fan_right
) -> None:
    command = ExampleAlgorithmController(MOTOR_NAMES).update(
        state_with_pitch(pitch_rad), 0.02
    )

    assert command.motor_positions_rad is not None
    assert command.fan_commands is not None
    assert command.motor_positions_rad["left_pitch"] == pytest.approx(target_rad)
    assert command.fan_commands.left == pytest.approx(fan_left)
    assert command.fan_commands.right == pytest.approx(fan_right)


@pytest.mark.parametrize("pitch_rad", [10.0, -10.0])
def test_motor_and_fan_outputs_are_clamped(pitch_rad: float) -> None:
    command = ExampleAlgorithmController(MOTOR_NAMES).update(
        state_with_pitch(pitch_rad), 0.02
    )

    assert command.motor_positions_rad is not None
    assert command.fan_commands is not None
    assert abs(command.motor_positions_rad["left_pitch"]) == pytest.approx(
        MAX_TARGET_OFFSET_RAD
    )
    assert max(command.fan_commands.left, command.fan_commands.right) == pytest.approx(
        MAX_FAN_COMMAND
    )


@pytest.mark.parametrize(
    "state,dt",
    [
        (make_stale_flight_state(MOTOR_NAMES), 0.02),
        (state_with_pitch(0.1), 0.0),
        (
            replace(
                state_with_pitch(0.1),
                imu=replace(state_with_pitch(0.1).imu, relative_pitch_rad=None),
            ),
            0.02,
        ),
    ],
)
def test_invalid_or_unfresh_input_returns_payload_free_safe_stop(state, dt) -> None:
    command = ExampleAlgorithmController(MOTOR_NAMES).update(state, dt)

    assert command == FlightCommand.safe_stop()
    validate_flight_command(command, MOTOR_NAMES)


def test_output_shape_is_complete_finite_and_factory_loadable() -> None:
    controller = load_controller(FACTORY, MOTOR_NAMES)
    command = controller.update(state_with_pitch(0.2, baseline=0.3), 0.02)

    validate_flight_command(command, MOTOR_NAMES)
    assert command.motor_positions_rad is not None
    assert command.fan_commands is not None
    assert set(command.motor_positions_rad) == set(MOTOR_NAMES)
    assert all(math.isfinite(value) for value in command.motor_positions_rad.values())
    assert math.isfinite(command.fan_commands.left)
    assert math.isfinite(command.fan_commands.right)


def test_missing_required_logical_motor_is_rejected() -> None:
    with pytest.raises(ValueError, match="left_pitch"):
        ExampleAlgorithmController(("axis_a", "axis_b"))
