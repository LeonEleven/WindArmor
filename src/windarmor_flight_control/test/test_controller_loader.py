import pytest

from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.runtime.controller_loader import (
    ControllerLoadError,
    load_controller,
)
from windarmor_flight_control.testing import make_unobserved_flight_state


MOTOR_NAMES = ("axis_a", "axis_b")


def test_default_factory_loads_pure_controller_without_ros() -> None:
    controller = load_controller(
        "windarmor_flight_control.algorithms.flight_controller:create_controller",
        MOTOR_NAMES,
    )
    controller.reset()
    command = controller.update(make_unobserved_flight_state(MOTOR_NAMES), 0.01)
    assert command == FlightCommand.safe_stop()


@pytest.mark.parametrize(
    "contract",
    ["", "missing_colon", "a:b:c", "missing.module:create_controller"],
)
def test_loader_failure_is_explicit(contract) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(contract, MOTOR_NAMES)
