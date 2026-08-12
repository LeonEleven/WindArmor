import math
from types import SimpleNamespace

import pytest

from windarmor_flight_control.runtime.imu_adapter import ImuAdapter

from .runtime_helpers import imu_message, relative_message


def test_valid_quaternion_euler_and_source_stamp_pairing() -> None:
    adapter = ImuAdapter()
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
    adapter = ImuAdapter()
    with pytest.raises(ValueError):
        adapter.update_raw(imu_message(1, orientation=orientation), 1.0)
    assert adapter.snapshot(now=1.0, freshness_sec=0.2).connected is None


def test_mismatched_duplicate_and_out_of_order_stamps_never_silently_pair() -> None:
    adapter = ImuAdapter()
    adapter.update_zero_generation(1)
    adapter.update_raw(imu_message(100), 1.0)
    adapter.update_relative(relative_message(101), 1.0)
    assert not adapter.snapshot(now=1.0, freshness_sec=0.2).valid
    adapter.update_relative(relative_message(100), 1.01)
    assert adapter.snapshot(now=1.01, freshness_sec=0.2).valid
    with pytest.raises(ValueError, match="duplicate or out of order"):
        adapter.update_raw(imu_message(100), 1.02)


def test_connection_status_data_evidence_and_zero_generation_semantics() -> None:
    adapter = ImuAdapter()
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
    adapter = ImuAdapter()
    adapter.update_zero_generation(0)
    adapter.update_raw(imu_message(1), 1.0)
    adapter.update_relative(relative_message(1), 1.0)
    state = adapter.snapshot(now=2.0, freshness_sec=0.2)
    assert state.valid
    assert not state.fresh
