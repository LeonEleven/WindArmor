import pytest

from windarmor_fan_controller.pwm import PwmRange


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
