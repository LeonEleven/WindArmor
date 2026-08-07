import math

import pytest

from imu_cybergear_ros2.cybergear_driver import MotorStatus
from imu_cybergear_ros2.motor_health import (
    MotorHealthAction,
    MotorHealthConfig,
    MotorHealthCore,
    MotorHealthReason,
    classify_fault,
    fault_names,
)


def config(**overrides):
    values = dict(
        motor_ids=(4, 3),
        temp_warning_deg_c=80.0,
        temp_critical_deg_c=90.0,
        invalid_feedback_limit=3,
        feedback_timeout_sec=0.0,
        feedback_startup_grace_sec=3.0,
    )
    values.update(overrides)
    return MotorHealthConfig(**values)


def status(motor_id=4, **overrides):
    values = dict(
        motor_id=motor_id,
        position_rad=0.0,
        speed_rad_s=0.0,
        torque_nm=0.0,
        temperature=25.0,
        mode=2,
        fault_flags=0,
        timestamp=1.0,
    )
    values.update(overrides)
    return MotorStatus(**values)


def test_normal_feedback_is_accepted_and_unknown_id_is_ignored():
    core = MotorHealthCore(config())
    assert core.evaluate(status(), received_at=10.0).action is MotorHealthAction.ACCEPT
    decision = core.evaluate(status(99), received_at=11.0)
    assert decision.action is MotorHealthAction.IGNORE
    assert decision.reason is MotorHealthReason.UNKNOWN_MOTOR_ID
    assert 99 not in core.invalid_counts


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("position_rad", math.nan),
        ("position_rad", 4.0 * math.pi + 0.001),
        ("speed_rad_s", math.inf),
        ("speed_rad_s", 30.001),
        ("torque_nm", -math.inf),
        ("torque_nm", -12.001),
        ("temperature", math.nan),
        ("temperature", 200.001),
        ("timestamp", -0.1),
        ("timestamp", math.inf),
        ("mode", 3),
        ("fault_flags", 0x40),
    ],
)
def test_invalid_numeric_protocol_fields_are_rejected(field, value):
    core = MotorHealthCore(config())
    decision = core.evaluate(status(**{field: value}), received_at=10.0)
    assert decision.action is MotorHealthAction.IGNORE
    assert decision.reason is MotorHealthReason.INVALID_FEEDBACK
    assert core.invalid_counts[4] == 1


def test_invalid_count_resets_only_after_complete_valid_frame_before_trip():
    core = MotorHealthCore(config())
    bad = status(position_rad=math.nan)
    assert core.evaluate(bad, received_at=1.0).action is MotorHealthAction.IGNORE
    assert core.evaluate(status(), received_at=2.0).action is MotorHealthAction.ACCEPT
    assert core.invalid_counts[4] == 0
    assert core.evaluate(bad, received_at=3.0).action is MotorHealthAction.IGNORE
    assert core.evaluate(bad, received_at=4.0).action is MotorHealthAction.IGNORE
    trip = core.evaluate(bad, received_at=5.0)
    assert trip.action is MotorHealthAction.TRIP
    assert trip.reason is MotorHealthReason.INVALID_FEEDBACK


@pytest.mark.parametrize(
    ("temperature", "action"),
    [
        (79.999, MotorHealthAction.ACCEPT),
        (80.0, MotorHealthAction.WARNING),
        (85.0, MotorHealthAction.WARNING),
        (90.0, MotorHealthAction.TRIP),
        (100.0, MotorHealthAction.TRIP),
    ],
)
def test_temperature_boundaries(temperature, action):
    decision = MotorHealthCore(config()).evaluate(
        status(temperature=temperature), received_at=1.0
    )
    assert decision.action is action
    if action is MotorHealthAction.WARNING:
        assert decision.reason is MotorHealthReason.TEMPERATURE_WARNING
    if action is MotorHealthAction.TRIP:
        assert decision.reason is MotorHealthReason.CRITICAL_TEMPERATURE


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (0x01, MotorHealthReason.MOTOR_FAULT_UNDERVOLTAGE),
        (0x02, MotorHealthReason.MOTOR_FAULT_OVERCURRENT),
        (0x04, MotorHealthReason.MOTOR_FAULT_OVERTEMPERATURE),
        (0x08, MotorHealthReason.MOTOR_FAULT_ENCODER),
        (0x10, MotorHealthReason.MOTOR_FAULT_ENCODER),
        (0x20, MotorHealthReason.MOTOR_FAULT_UNCALIBRATED),
        (0x03, MotorHealthReason.MOTOR_FAULT_MULTIPLE),
    ],
)
def test_all_firmware_fault_bits_are_immediate_trips(flags, reason):
    decision = MotorHealthCore(config()).evaluate(
        status(fault_flags=flags), received_at=1.0
    )
    assert decision.action is MotorHealthAction.TRIP
    assert decision.reason is reason
    assert decision.fault_names == fault_names(flags)
    assert classify_fault(flags) is reason


def test_fault_bit_precedes_numeric_temperature_and_no_current_is_invented():
    motor_status = status(fault_flags=0x02, torque_nm=12.0, temperature=20.0)
    assert not hasattr(motor_status, "current_a")
    decision = MotorHealthCore(config()).evaluate(motor_status, received_at=1.0)
    assert decision.reason is MotorHealthReason.MOTOR_FAULT_OVERCURRENT
    assert decision.observed_value == 0x02


def test_timeout_zero_disables_trip_but_keeps_age_snapshot():
    core = MotorHealthCore(config(feedback_timeout_sec=0.0))
    core.activate(10.0)
    core.evaluate(status(), received_at=11.0)
    assert core.check_freshness(now=1000.0) == ()
    snapshot = {item.motor_id: item for item in core.freshness_snapshot(now=12.0)}
    assert snapshot[4].age_sec == 1.0
    assert not snapshot[3].has_feedback


def test_startup_grace_missing_first_frame_and_timeout_boundaries_use_fake_time():
    core = MotorHealthCore(config(feedback_timeout_sec=1.0))
    core.activate(10.0)
    assert core.check_freshness(now=12.999) == ()
    missing = core.check_freshness(now=13.0)
    assert {decision.motor_id for decision in missing} == {4, 3}

    core.activate(20.0)
    core.evaluate(status(4), received_at=22.5)
    core.evaluate(status(3), received_at=22.75)
    assert core.check_freshness(now=23.5) == ()  # age exactly timeout is valid
    decisions = core.check_freshness(now=23.5001)
    assert [decision.motor_id for decision in decisions] == [4]


def test_invalid_frame_does_not_refresh_local_receive_time():
    core = MotorHealthCore(config(feedback_timeout_sec=1.0))
    core.activate(0.0)
    core.evaluate(status(), received_at=1.0)
    core.evaluate(status(position_rad=math.nan), received_at=1.9)
    decisions = core.check_freshness(now=3.0)
    assert any(decision.motor_id == 4 for decision in decisions)


def test_deactivate_stops_checks_and_reactivate_does_not_inherit_old_time():
    core = MotorHealthCore(config(feedback_timeout_sec=1.0))
    core.activate(0.0)
    core.evaluate(status(), received_at=1.0)
    core.evaluate(status(position_rad=math.nan), received_at=1.1)
    assert core.invalid_counts[4] == 1
    core.deactivate()
    assert core.check_freshness(now=100.0) == ()
    core.activate(200.0)
    assert core.invalid_counts[4] == 0
    snapshots = {item.motor_id: item for item in core.freshness_snapshot(now=200.0)}
    assert not snapshots[4].has_feedback
    assert core.check_freshness(now=202.9) == ()
