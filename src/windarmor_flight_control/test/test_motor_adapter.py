from types import SimpleNamespace

import pytest

from windarmor_flight_control.runtime.motor_adapter import MotorAdapter

from .runtime_helpers import motor_entry, motor_message


MOTOR_NAMES = ("axis_a", "axis_b")


def test_complete_feedback_age_adds_local_elapsed_and_uses_flight_freshness() -> None:
    adapter = MotorAdapter(MOTOR_NAMES)
    adapter.update(motor_message(feedback_age_sec=0.2), received_at=10.0)
    motors = adapter.snapshot(now=10.1, freshness_sec=0.5)
    assert motors["axis_a"].feedback_age_sec == pytest.approx(0.3)
    assert motors["axis_a"].fresh

    stale = adapter.snapshot(now=10.31, freshness_sec=0.5)
    assert stale["axis_a"].valid
    assert not stale["axis_a"].fresh
    assert not stale["axis_a"].healthy


def test_no_feedback_presence_maps_to_none_without_invented_current() -> None:
    adapter = MotorAdapter(MOTOR_NAMES)
    adapter.update(motor_message(has_feedback=False), 1.0)
    motor = adapter.snapshot(now=1.0, freshness_sec=0.5)["axis_a"]
    assert not motor.has_feedback
    assert motor.position_rad is None
    assert motor.velocity_rad_s is None
    assert motor.torque_nm is None
    assert motor.temperature_c is None
    assert motor.device_mode is None
    assert motor.fault_flags is None
    assert motor.feedback_age_sec is None
    assert not hasattr(motor, "current_a")


@pytest.mark.parametrize(
    "message",
    [
        motor_message(names=("axis_a",)),
        motor_message(names=("axis_a", "axis_b", "extra")),
        SimpleNamespace(motors=[motor_entry("axis_a", 1), motor_entry("axis_a", 2)]),
        SimpleNamespace(motors=[motor_entry("axis_a", 1), motor_entry("axis_b", 1)]),
        SimpleNamespace(motors=[motor_entry("", 1), motor_entry("axis_b", 2)]),
    ],
)
def test_missing_unknown_duplicate_name_or_can_id_is_rejected(message) -> None:
    with pytest.raises(ValueError):
        MotorAdapter(MOTOR_NAMES).update(message, 1.0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"position_valid": False},
        {"position_rad": float("nan")},
        {"feedback_age_sec": -0.1},
        {"healthy": True, "fault_flags": 1},
        {"fresh": True, "valid": False, "healthy": False},
    ],
)
def test_presence_nonfinite_age_and_health_conflicts_are_rejected(overrides) -> None:
    entries = [
        motor_entry("axis_a", 1, **overrides),
        motor_entry("axis_b", 2),
    ]
    with pytest.raises(ValueError):
        MotorAdapter(MOTOR_NAMES).update(SimpleNamespace(motors=entries), 1.0)


def test_publisher_health_fault_propagates_without_clearing_it() -> None:
    adapter = MotorAdapter(MOTOR_NAMES)
    message = SimpleNamespace(
        motors=[
            motor_entry("axis_a", 1, fresh=True, healthy=False),
            motor_entry("axis_b", 2),
        ]
    )
    adapter.update(message, 1.0)
    motors = adapter.snapshot(now=1.0, freshness_sec=0.5)
    assert motors["axis_a"].valid and motors["axis_a"].fresh
    assert not motors["axis_a"].healthy
