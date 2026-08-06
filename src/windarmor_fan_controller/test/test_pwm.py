import math

import pytest

from windarmor_fan_controller.fan_node import initialize_after_timeout_validation
from windarmor_fan_controller.pwm import (
    FanCommandGate,
    PwmRange,
    validate_positive_finite_timeout,
)


def test_clamp() -> None:
    pwm_range = PwmRange(800, 2200)
    assert pwm_range.clamp(700) == 800
    assert pwm_range.clamp(1500) == 1500
    assert pwm_range.clamp(2300) == 2200


def test_servo_mapping() -> None:
    pwm_range = PwmRange(800, 2200)
    assert pwm_range.to_servo_value(800) == pytest.approx(-1.0)
    assert pwm_range.to_servo_value(1500) == pytest.approx(0.0)
    assert pwm_range.to_servo_value(2200) == pytest.approx(1.0)


def test_invalid_range() -> None:
    with pytest.raises(ValueError):
        PwmRange(800, 800)


def test_command_gate_enable_disable_and_new_command_requirement() -> None:
    gate = FanCommandGate()
    assert gate.last_command_time is None
    assert gate.accept(1.0)
    gate.disable()
    assert not gate.enabled
    assert gate.last_command_time is None
    assert not gate.accept(2.0)
    gate.enable()
    assert gate.enabled
    assert gate.last_command_time is None
    assert gate.accept(3.0)


def test_command_gate_timeout_keeps_enabled_but_discards_old_command() -> None:
    gate = FanCommandGate()
    assert not gate.check_timeout(1.0, 0.5)
    gate.accept(1.0)
    assert not gate.check_timeout(1.5, 0.5)
    assert gate.check_timeout(1.51, 0.5)
    assert gate.enabled
    assert gate.last_command_time is None
    assert not gate.check_timeout(2.0, 0.5)


@pytest.mark.parametrize("timeout", [0.0, -0.1, math.nan, math.inf, -math.inf, "bad"])
def test_command_gate_rejects_invalid_timeout(timeout) -> None:
    gate = FanCommandGate()
    with pytest.raises(ValueError):
        gate.check_timeout(1.0, timeout)
    with pytest.raises(ValueError):
        validate_positive_finite_timeout(timeout)


def test_positive_finite_timeout_is_preserved() -> None:
    assert validate_positive_finite_timeout(1.25) == 1.25
    assert validate_positive_finite_timeout("0.5") == 0.5


@pytest.mark.parametrize("timeout", [0.0, -0.1, math.nan, math.inf, -math.inf, "bad"])
def test_invalid_timeout_never_calls_hardware_initializer(timeout) -> None:
    calls = []
    with pytest.raises(ValueError):
        initialize_after_timeout_validation(timeout, lambda: calls.append(True))
    assert calls == []


def test_valid_timeout_calls_initializer_once() -> None:
    calls = []
    timeout = initialize_after_timeout_validation(1.0, lambda: calls.append(True))
    assert timeout == 1.0
    assert calls == [True]
