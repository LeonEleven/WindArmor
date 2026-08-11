from dataclasses import replace

from windarmor_flight_control.algorithms import NeutralExampleController
from windarmor_flight_control.core.controller import FlightController
from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.core.validation import validate_flight_command
from windarmor_flight_control.testing import make_fake_flight_state


MOTOR_NAMES = ("axis_a", "axis_b", "axis_c", "axis_d")
NEUTRAL_TARGETS = {name: 0.0 for name in MOTOR_NAMES}


def test_example_controller_uses_pure_api_without_ros_graph() -> None:
    controller: FlightController = NeutralExampleController(NEUTRAL_TARGETS)
    state = make_fake_flight_state(MOTOR_NAMES)

    controller.reset()
    command = controller.update(state, dt=0.01)

    validate_flight_command(command, MOTOR_NAMES)
    assert command.motor_positions_rad == NEUTRAL_TARGETS
    assert command.fan_commands.left == 0.0
    assert command.fan_commands.right == 0.0
    assert command.request_safe_stop is False


def test_example_controller_requests_safe_stop_when_actuation_is_inhibited() -> None:
    controller = NeutralExampleController(NEUTRAL_TARGETS)
    state = make_fake_flight_state(MOTOR_NAMES)
    inhibited = replace(
        state,
        system=replace(state.system, actuation_allowed=False),
    )

    command = controller.update(inhibited, dt=0.01)

    validate_flight_command(command, MOTOR_NAMES)
    assert command == FlightCommand.safe_stop(NEUTRAL_TARGETS)
    assert command.request_safe_stop is True


def test_safe_stop_is_only_an_immutable_api_value() -> None:
    command = FlightCommand.safe_stop(NEUTRAL_TARGETS)

    assert command.request_safe_stop is True
    assert command.fan_commands.left == 0.0
    assert command.fan_commands.right == 0.0
    assert not callable(command.request_safe_stop)
