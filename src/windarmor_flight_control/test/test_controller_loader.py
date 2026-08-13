import pytest
from types import SimpleNamespace

from windarmor_flight_control.algorithms import NeutralExampleController
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


def test_loader_passes_verification_configuration_to_factory() -> None:
    controller = load_controller(
        "windarmor_flight_control.algorithms."
        "bounded_verification_controller:create_controller",
        MOTOR_NAMES,
        {
            "verification_controller_enabled": True,
            "test_motor_name": "axis_a",
            "motor_test_offset_configured": True,
            "motor_test_offset_rad": 0.1,
            "fan_left_test_command": 0.0,
            "fan_right_test_command": 0.0,
        },
    )
    state = make_unobserved_flight_state(MOTOR_NAMES)
    assert controller.update(state, 0.01) == FlightCommand.safe_stop()


def test_loader_keeps_legacy_one_argument_factory_compatible(monkeypatch) -> None:
    captured = []

    def legacy_factory(names):
        captured.append(names)
        return NeutralExampleController({name: 0.0 for name in names})

    monkeypatch.setattr(
        "windarmor_flight_control.runtime.controller_loader.importlib.import_module",
        lambda _name: SimpleNamespace(create_controller=legacy_factory),
    )
    controller = load_controller("legacy.module:create_controller", MOTOR_NAMES, {"x": 1})
    assert captured == [MOTOR_NAMES]
    assert controller.update(
        make_unobserved_flight_state(MOTOR_NAMES), 0.01
    ) == FlightCommand.safe_stop()


@pytest.mark.parametrize(
    "contract",
    ["", "missing_colon", "a:b:c", "missing.module:create_controller"],
)
def test_loader_failure_is_explicit(contract) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(contract, MOTOR_NAMES)
