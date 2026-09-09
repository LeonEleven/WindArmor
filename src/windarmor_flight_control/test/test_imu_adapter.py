import math
from types import SimpleNamespace

import pytest

from windarmor_flight_control.runtime.imu_adapter import ImuAdapter

from .runtime_helpers import imu_message, relative_message


def test_valid_quaternion_euler_and_source_stamp_pairing() -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    adapter.update_zero_generation(0)
    half = math.sqrt(0.5)
    raw = imu_message(
        10,
        orientation=SimpleNamespace(x=half, y=0.0, z=0.0, w=half),
    )
    adapter.update_relative(relative_message(10, 0.4, -0.5), 1.01)
    adapter.update_raw(raw, 1.0)
    state = adapter.snapshot(now=1.1, freshness_sec=0.2)

    assert state.valid and state.fresh and state.connected is True
    assert state.zero_generation == 0
    assert state.roll_rad == pytest.approx(math.pi / 2.0)
    assert state.pitch_rad == pytest.approx(0.0)
    assert state.yaw_rad == pytest.approx(0.0)
    assert state.relative_roll_rad == 0.4
    assert state.relative_pitch_rad == -0.5
    assert state.relative_pitch_rate_rad_s == pytest.approx(-0.3)
    assert state.angular_velocity_rad_s.x == pytest.approx(0.1)
    assert state.angular_velocity_rad_s.y == pytest.approx(0.2)
    assert state.angular_velocity_rad_s.z == pytest.approx(0.3)
    assert state.sample_age_sec == pytest.approx(0.1)


@pytest.mark.parametrize(
    "orientation",
    [
        SimpleNamespace(x=math.nan, y=0.0, z=0.0, w=1.0),
        SimpleNamespace(x=math.inf, y=0.0, z=0.0, w=1.0),
        SimpleNamespace(x=0.0, y=0.0, z=0.0, w=0.0),
    ],
)
def test_invalid_quaternion_is_rejected(orientation) -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    with pytest.raises(ValueError):
        adapter.update_raw(imu_message(1, orientation=orientation), 1.0)
    assert adapter.snapshot(now=1.0, freshness_sec=0.2).connected is None


def test_mismatched_duplicate_and_out_of_order_stamps_never_silently_pair() -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    adapter.update_zero_generation(1)
    adapter.update_raw(imu_message(100), 1.0)
    adapter.update_relative(relative_message(101), 1.0)
    assert not adapter.snapshot(now=1.0, freshness_sec=0.2).valid
    adapter.update_relative(relative_message(100), 1.01)
    assert adapter.snapshot(now=1.01, freshness_sec=0.2).valid
    with pytest.raises(ValueError, match="duplicate or out of order"):
        adapter.update_raw(imu_message(100), 1.02)


def test_pitch_rate_uses_raw_message_with_the_paired_source_stamp() -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    adapter.update_zero_generation(1)
    first_rate = SimpleNamespace(x=0.0, y=0.15, z=0.0)
    second_rate = SimpleNamespace(x=0.0, y=0.75, z=0.0)
    adapter.update_raw(
        imu_message(20, angular_velocity=first_rate),
        1.0,
    )
    adapter.update_raw(
        imu_message(21, angular_velocity=second_rate),
        1.01,
    )

    adapter.update_relative(relative_message(20), 1.02)
    first = adapter.snapshot(now=1.02, freshness_sec=0.2)
    assert first.relative_pitch_rate_rad_s == pytest.approx(0.15)

    adapter.update_relative(relative_message(21), 1.03)
    second = adapter.snapshot(now=1.03, freshness_sec=0.2)
    assert second.relative_pitch_rate_rad_s == pytest.approx(0.75)


def test_connection_status_data_evidence_and_zero_generation_semantics() -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    assert not adapter.update_status("unknown")
    assert adapter.snapshot(now=0.0, freshness_sec=0.2).connected is None
    assert adapter.update_status("reconnecting")
    assert adapter.snapshot(now=0.0, freshness_sec=0.2).connected is False

    adapter.update_raw(imu_message(1), 1.0)
    adapter.update_relative(relative_message(1), 1.0)
    without_generation = adapter.snapshot(now=1.0, freshness_sec=0.2)
    assert without_generation.connected is True
    assert without_generation.zero_generation is None
    assert not without_generation.valid

    adapter.update_zero_generation(2)
    assert not adapter.snapshot(now=1.0, freshness_sec=0.2).valid
    adapter.update_raw(imu_message(2), 1.1)
    adapter.update_relative(relative_message(2), 1.1)
    assert adapter.snapshot(now=1.1, freshness_sec=0.2).valid
    assert adapter.update_status("disconnected")
    assert not adapter.snapshot(now=1.1, freshness_sec=0.2).valid


def test_stale_pair_is_valid_but_not_fresh() -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    adapter.update_zero_generation(0)
    adapter.update_raw(imu_message(1), 1.0)
    adapter.update_relative(relative_message(1), 1.0)
    state = adapter.snapshot(now=2.0, freshness_sec=0.2)
    assert state.valid
    assert not state.fresh


@pytest.mark.parametrize("pitch_axis_sign", [1.0, -1.0])
def test_pitch_axis_sign_applies_to_angle_and_derived_rate(
    pitch_axis_sign: float,
) -> None:
    adapter = ImuAdapter(pitch_axis_sign=pitch_axis_sign)
    adapter.update_zero_generation(3)
    roll = 0.4
    raw_pitch = 0.2
    half_roll = roll / 2.0
    half_pitch = raw_pitch / 2.0
    orientation = SimpleNamespace(
        x=math.sin(half_roll) * math.cos(half_pitch),
        y=math.cos(half_roll) * math.sin(half_pitch),
        z=-math.sin(half_roll) * math.sin(half_pitch),
        w=math.cos(half_roll) * math.cos(half_pitch),
    )
    body_rate = SimpleNamespace(x=0.7, y=0.5, z=-0.25)
    expected_raw_rate = math.cos(roll) * body_rate.y - math.sin(roll) * body_rate.z
    adapter.update_raw(
        imu_message(11, orientation=orientation, angular_velocity=body_rate),
        2.0,
    )
    adapter.update_relative(
        relative_message(11, roll=roll, pitch=pitch_axis_sign * raw_pitch),
        2.0,
    )

    state = adapter.snapshot(now=2.0, freshness_sec=0.2)

    assert state.relative_pitch_rad == pytest.approx(pitch_axis_sign * raw_pitch)
    assert state.relative_pitch_rate_rad_s == pytest.approx(
        pitch_axis_sign * expected_raw_rate
    )
    assert state.angular_velocity_rad_s.y == body_rate.y
    assert state.angular_velocity_rad_s.z == body_rate.z


def test_zero_offset_changes_relative_angle_but_not_derived_rate() -> None:
    orientation = SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)
    body_rate = SimpleNamespace(x=0.0, y=0.35, z=0.0)
    observed_rates = []
    for generation, relative_pitch in ((1, 0.4), (2, -0.7)):
        adapter = ImuAdapter(pitch_axis_sign=1.0)
        adapter.update_zero_generation(generation)
        adapter.update_raw(
            imu_message(
                generation,
                orientation=orientation,
                angular_velocity=body_rate,
            ),
            3.0,
        )
        adapter.update_relative(
            relative_message(generation, pitch=relative_pitch),
            3.0,
        )
        state = adapter.snapshot(now=3.0, freshness_sec=0.2)
        assert state.relative_pitch_rad == relative_pitch
        observed_rates.append(state.relative_pitch_rate_rad_s)

    assert observed_rates == pytest.approx([0.35, 0.35])


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_body_rate_is_rejected(value: float) -> None:
    adapter = ImuAdapter(pitch_axis_sign=1.0)
    angular_velocity = SimpleNamespace(x=0.0, y=value, z=0.0)

    with pytest.raises(ValueError, match="angular_velocity.y must be finite"):
        adapter.update_raw(
            imu_message(1, angular_velocity=angular_velocity),
            1.0,
        )


@pytest.mark.parametrize("value", [0.0, 2.0, -2.0, True])
def test_invalid_pitch_axis_sign_is_rejected(value) -> None:
    with pytest.raises(ValueError, match="exactly"):
        ImuAdapter(pitch_axis_sign=value)
