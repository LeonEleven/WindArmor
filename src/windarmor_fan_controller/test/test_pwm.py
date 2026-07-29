import pytest

from windarmor_fan_controller.pwm import FanCommandGate, PwmRange


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
