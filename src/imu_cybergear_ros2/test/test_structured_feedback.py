from types import SimpleNamespace

from imu_cybergear_ros2.structured_feedback import build_structured_feedback


CHANNELS = (
    SimpleNamespace(name="left_lift", motor_id=4),
    SimpleNamespace(name="left_pitch", motor_id=3),
)


def status(**overrides):
    values = dict(
        position_rad=0.25,
        speed_rad_s=-0.5,
        torque_nm=1.5,
        temperature=35.0,
        mode=2,
        fault_flags=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_snapshot_contains_all_configured_motors_and_no_feedback_presence() -> None:
    snapshot = build_structured_feedback(
        CHANNELS,
        {4: status()},
        {4: 9.75},
        now=10.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=False,
    )

    assert [(item.logical_name, item.can_id) for item in snapshot] == [
        ("left_lift", 4),
        ("left_pitch", 3),
    ]
    assert snapshot[0].feedback_age_sec == 0.25
    assert snapshot[0].valid
    assert snapshot[0].fresh
    assert snapshot[0].healthy
    assert not snapshot[1].has_feedback
    assert snapshot[1].position_rad is None
    assert snapshot[1].velocity_rad_s is None
    assert snapshot[1].torque_nm is None
    assert snapshot[1].temperature_c is None
    assert snapshot[1].device_mode is None
    assert snapshot[1].fault_flags is None
    assert snapshot[1].feedback_age_sec is None
    assert not snapshot[1].valid
    assert not snapshot[1].fresh
    assert not snapshot[1].healthy


def test_observer_freshness_and_health_fault_are_independent_of_safety_timeout() -> None:
    stale = build_structured_feedback(
        CHANNELS[:1],
        {4: status()},
        {4: 1.0},
        now=2.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=False,
    )[0]
    assert stale.valid
    assert not stale.fresh
    assert not stale.healthy

    latched = build_structured_feedback(
        CHANNELS[:1],
        {4: status()},
        {4: 2.0},
        now=2.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=True,
    )[0]
    assert latched.valid and latched.fresh
    assert not latched.healthy


def test_firmware_fault_is_visible_and_never_reported_healthy() -> None:
    item = build_structured_feedback(
        CHANNELS[:1],
        {4: status(fault_flags=0x02, temperature=91.0)},
        {4: 3.0},
        now=3.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=True,
    )[0]
    assert item.fault_flags == 0x02
    assert item.temperature_c == 91.0
    assert item.valid and item.fresh
    assert not item.healthy


def test_critical_temperature_is_never_healthy_even_before_global_latch_observed() -> None:
    item = build_structured_feedback(
        CHANNELS[:1],
        {4: status(temperature=90.0)},
        {4: 3.0},
        now=3.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=False,
    )[0]
    assert item.valid and item.fresh
    assert not item.healthy


def test_snapshot_build_only_reads_supplied_memory_objects() -> None:
    feedback = {4: status()}
    received = {4: 4.0}
    before = (dict(feedback), dict(received))

    build_structured_feedback(
        CHANNELS,
        feedback,
        received,
        now=4.0,
        freshness_sec=0.5,
        critical_temperature_c=90.0,
        safety_fault_active=False,
    )

    assert feedback == before[0]
    assert received == before[1]
