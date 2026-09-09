import math

import pytest

from windarmor_flight_control.core.models import Quaternion, Vector3
from windarmor_flight_control.runtime.imu_adapter import (
    corrected_relative_pitch_rate_rad_s,
    euler_pitch_rate_from_body_angular_velocity,
    normalize_quaternion,
    quaternion_to_euler,
)


def quaternion_from_euler(roll: float, pitch: float, yaw: float) -> Quaternion:
    return Quaternion(
        x=(
            math.sin(roll / 2.0)
            * math.cos(pitch / 2.0)
            * math.cos(yaw / 2.0)
            - math.cos(roll / 2.0)
            * math.sin(pitch / 2.0)
            * math.sin(yaw / 2.0)
        ),
        y=(
            math.cos(roll / 2.0)
            * math.sin(pitch / 2.0)
            * math.cos(yaw / 2.0)
            + math.sin(roll / 2.0)
            * math.cos(pitch / 2.0)
            * math.sin(yaw / 2.0)
        ),
        z=(
            math.cos(roll / 2.0)
            * math.cos(pitch / 2.0)
            * math.sin(yaw / 2.0)
            - math.sin(roll / 2.0)
            * math.sin(pitch / 2.0)
            * math.cos(yaw / 2.0)
        ),
        w=(
            math.cos(roll / 2.0)
            * math.cos(pitch / 2.0)
            * math.cos(yaw / 2.0)
            + math.sin(roll / 2.0)
            * math.sin(pitch / 2.0)
            * math.sin(yaw / 2.0)
        ),
    )


def integrate_body_rate(
    orientation: Quaternion,
    angular_velocity: Vector3,
    dt: float,
) -> Quaternion:
    x, y, z, w = (
        orientation.x,
        orientation.y,
        orientation.z,
        orientation.w,
    )
    p, q, r = (
        angular_velocity.x,
        angular_velocity.y,
        angular_velocity.z,
    )
    return normalize_quaternion(
        Quaternion(
            x=x + 0.5 * (w * p + y * r - z * q) * dt,
            y=y + 0.5 * (w * q + z * p - x * r) * dt,
            z=z + 0.5 * (w * r + x * q - y * p) * dt,
            w=w - 0.5 * (x * p + y * q + z * r) * dt,
        )
    )


def test_identity_zero_and_signed_pitch_axis_body_rates() -> None:
    identity = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
    assert euler_pitch_rate_from_body_angular_velocity(
        identity, Vector3(x=0.0, y=0.0, z=0.0)
    ) == 0.0
    assert euler_pitch_rate_from_body_angular_velocity(
        identity, Vector3(x=1.2, y=0.6, z=-0.4)
    ) == pytest.approx(0.6)
    assert euler_pitch_rate_from_body_angular_velocity(
        identity, Vector3(x=-1.2, y=-0.6, z=0.4)
    ) == pytest.approx(-0.6)


def test_nonzero_roll_couples_body_z_rate_into_euler_pitch_rate() -> None:
    roll = math.pi / 6.0
    orientation = quaternion_from_euler(roll, 0.25, -0.4)
    body_rate = Vector3(x=9.0, y=0.4, z=-0.2)

    result = euler_pitch_rate_from_body_angular_velocity(
        orientation,
        body_rate,
    )

    assert result == pytest.approx(
        math.cos(roll) * body_rate.y - math.sin(roll) * body_rate.z
    )
    assert result != pytest.approx(body_rate.y)


def test_body_rate_to_pitch_rate_is_odd_symmetric() -> None:
    orientation = quaternion_from_euler(-0.7, 0.3, 0.9)
    positive = Vector3(x=0.8, y=0.35, z=-0.45)
    negative = Vector3(x=-positive.x, y=-positive.y, z=-positive.z)

    assert euler_pitch_rate_from_body_angular_velocity(
        orientation, negative
    ) == pytest.approx(
        -euler_pitch_rate_from_body_angular_velocity(orientation, positive)
    )


@pytest.mark.parametrize("pitch_axis_sign", [1.0, -1.0])
def test_pitch_axis_sign_corrects_rate_direction(pitch_axis_sign: float) -> None:
    orientation = quaternion_from_euler(0.3, -0.2, 0.1)
    body_rate = Vector3(x=0.0, y=0.5, z=0.2)
    raw_rate = euler_pitch_rate_from_body_angular_velocity(
        orientation, body_rate
    )

    assert corrected_relative_pitch_rate_rad_s(
        orientation,
        body_rate,
        pitch_axis_sign=pitch_axis_sign,
    ) == pytest.approx(pitch_axis_sign * raw_rate)


@pytest.mark.parametrize("pitch_axis_sign", [0.0, 2.0, -2.0, True])
def test_invalid_pitch_axis_sign_is_rejected(pitch_axis_sign) -> None:
    with pytest.raises(ValueError, match="exactly"):
        corrected_relative_pitch_rate_rad_s(
            Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
            Vector3(x=0.0, y=0.0, z=0.0),
            pitch_axis_sign=pitch_axis_sign,
        )


@pytest.mark.parametrize(
    "orientation",
    [
        Quaternion(x=0.0, y=0.0, z=0.0, w=0.0),
        Quaternion(x=math.nan, y=0.0, z=0.0, w=1.0),
        Quaternion(x=0.0, y=math.inf, z=0.0, w=1.0),
        quaternion_from_euler(0.0, math.pi / 2.0, 0.0),
    ],
)
def test_invalid_or_singular_orientation_is_rejected(
    orientation: Quaternion,
) -> None:
    with pytest.raises(ValueError):
        euler_pitch_rate_from_body_angular_velocity(
            orientation,
            Vector3(x=0.0, y=0.1, z=0.0),
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_body_rate_is_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        euler_pitch_rate_from_body_angular_velocity(
            Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
            Vector3(x=0.0, y=value, z=0.0),
        )


@pytest.mark.parametrize(
    ("roll", "pitch", "yaw", "body_rate"),
    [
        (0.0, 0.0, 0.0, Vector3(x=0.2, y=0.5, z=-0.1)),
        (0.45, -0.35, 0.6, Vector3(x=0.7, y=-0.4, z=0.3)),
        (-0.8, 0.5, -0.2, Vector3(x=-0.5, y=0.2, z=-0.6)),
    ],
)
def test_derived_rate_matches_numerical_quaternion_derivative(
    roll: float,
    pitch: float,
    yaw: float,
    body_rate: Vector3,
) -> None:
    orientation = quaternion_from_euler(roll, pitch, yaw)
    expected = euler_pitch_rate_from_body_angular_velocity(
        orientation,
        body_rate,
    )
    dt = 1.0e-7
    advanced = integrate_body_rate(orientation, body_rate, dt)
    _roll_0, pitch_0, _yaw_0 = quaternion_to_euler(orientation)
    _roll_1, pitch_1, _yaw_1 = quaternion_to_euler(advanced)
    numerical = (pitch_1 - pitch_0) / dt

    assert numerical == pytest.approx(expected, rel=1.0e-6, abs=1.0e-8)
