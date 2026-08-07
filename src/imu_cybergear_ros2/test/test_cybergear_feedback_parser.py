import math

import pytest

from imu_cybergear_ros2.cybergear_driver import (
    POS_RANGE_MAX,
    POS_RANGE_MIN,
    SPD_RANGE_MAX,
    SPD_RANGE_MIN,
    TORQUE_RANGE_MAX,
    TORQUE_RANGE_MIN,
    _parse_feedback_frame,
    _uint16_to_range,
)


def test_status_payload_uint16_fields_are_big_endian():
    can_id = (0x02 << 24) | (2 << 22) | (0x21 << 16) | (4 << 8) | 0xFD
    payload = bytes.fromhex("8000 4000 c000 0167")

    status = _parse_feedback_frame(4, can_id, payload)

    assert status is not None
    assert status.raw_position == 0x8000
    assert status.raw_speed == 0x4000
    assert status.raw_torque == 0xC000
    assert status.raw_temp == 0x0167
    assert status.position_rad == pytest.approx(
        _uint16_to_range(0x8000, POS_RANGE_MIN, POS_RANGE_MAX)
    )
    assert status.speed_rad_s == pytest.approx(
        _uint16_to_range(0x4000, SPD_RANGE_MIN, SPD_RANGE_MAX)
    )
    assert status.torque_nm == pytest.approx(
        _uint16_to_range(0xC000, TORQUE_RANGE_MIN, TORQUE_RANGE_MAX)
    )
    assert status.temperature == pytest.approx(35.9)
    assert status.mode == 2
    assert status.fault_flags == 0x21
    assert math.isfinite(status.timestamp)
    assert status.timestamp >= 0.0


@pytest.mark.parametrize(
    ("temperature_bytes", "expected_deg_c"),
    [("0167", 35.9), ("0161", 35.3), ("015a", 34.6)],
)
def test_status_temperature_matches_observed_room_temperature_bytes(
    temperature_bytes, expected_deg_c
):
    payload = bytes.fromhex(f"8000 8000 8000 {temperature_bytes}")

    status = _parse_feedback_frame(1, 2 << 22, payload)

    assert status is not None
    assert status.temperature == pytest.approx(expected_deg_c)


def test_short_status_payload_is_rejected():
    assert _parse_feedback_frame(1, 2 << 22, b"\x00" * 7) is None
