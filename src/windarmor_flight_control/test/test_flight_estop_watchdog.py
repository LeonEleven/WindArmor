import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import rclpy


REPO_ROOT = Path(__file__).resolve().parents[3]
WATCHDOG_PATH = REPO_ROOT / "scripts" / "flight_estop_watchdog.py"
SPEC = importlib.util.spec_from_file_location(
    "windarmor_flight_estop_watchdog",
    WATCHDOG_PATH,
)
assert SPEC is not None and SPEC.loader is not None
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


class MutableClock:
    def __init__(self, value: float = 1.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class CapturePublisher:
    def __init__(self, *, subscription_count: int = 1, error=None):
        self.subscription_count = subscription_count
        self.error = error
        self.messages = []

    def get_subscription_count(self) -> int:
        return self.subscription_count

    def publish(self, message) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(message)


@pytest.fixture
def ros_context():
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def ready_core(**overrides):
    values = {
        "started_at": 1.0,
        "delay_sec": 2.0,
        "active_timeout_sec": 10.0,
        "publisher_ready_timeout_sec": 5.0,
    }
    values.update(overrides)
    core = watchdog.GateCEstopWatchdogCore(**values)
    assert core.update_publisher_readiness(1, 1.1) is watchdog.WatchdogEvent.READY
    return core


@pytest.mark.parametrize(
    ("authority_state", "command_authority", "actuation_allowed"),
    [
        ("DRY_RUN", "NONE", False),
        ("ARMING", "NONE", False),
        ("READY_TO_TAKEOVER", "NONE", False),
        ("ACTIVE", "NONE", True),
        ("ACTIVE", "FLIGHT_CONTROL", False),
    ],
)
def test_only_real_executable_flight_active_starts_timer(
    authority_state,
    command_authority,
    actuation_allowed,
) -> None:
    core = ready_core()

    assert core.observe_authority(
        authority_state=authority_state,
        command_authority=command_authority,
        actuation_allowed=actuation_allowed,
        now=2.0,
    ) is None
    assert core.active_detected_at is None


def test_active_starts_once_and_delay_publishes_once() -> None:
    core = ready_core()

    assert core.observe_authority(
        authority_state="ACTIVE",
        command_authority="FLIGHT_CONTROL",
        actuation_allowed=True,
        now=2.0,
    ) is watchdog.WatchdogEvent.ACTIVE_DETECTED
    assert core.observe_authority(
        authority_state="ACTIVE",
        command_authority="FLIGHT_CONTROL",
        actuation_allowed=True,
        now=2.5,
    ) is None
    assert core.active_detected_at == 2.0
    assert core.tick(3.999) is None
    assert core.tick(4.0) is watchdog.WatchdogEvent.ESTOP_ACTIVE_DELAY
    assert core.tick(5.0) is None
    assert core.estop_requested_at == 4.0


def test_no_active_timeout_fails_closed_once() -> None:
    core = ready_core(active_timeout_sec=10.0)

    assert core.tick(11.099) is None
    assert core.tick(11.1) is watchdog.WatchdogEvent.ESTOP_NO_ACTIVE_TIMEOUT
    assert core.tick(12.0) is None


def test_readiness_requires_subscriber_and_times_out_without_arming() -> None:
    core = watchdog.GateCEstopWatchdogCore(
        started_at=1.0,
        publisher_ready_timeout_sec=5.0,
    )

    assert core.update_publisher_readiness(0, 5.999) is None
    assert core.update_publisher_readiness(
        0, 6.0
    ) is watchdog.WatchdogEvent.READINESS_TIMEOUT
    assert core.ready_at is None
    assert core.tick(20.0) is None


@pytest.mark.parametrize("delay", [0.0, -0.1, 3.0, 4.0, float("inf")])
def test_invalid_delay_is_rejected(delay: float) -> None:
    with pytest.raises(ValueError, match="delay_sec"):
        watchdog.GateCEstopWatchdogCore(started_at=1.0, delay_sec=delay)


def test_node_uses_prewarmed_publisher_and_reports_flight_observation(
    ros_context,
    capsys,
) -> None:
    clock = MutableClock()
    node = watchdog.FlightEstopWatchdog(monotonic_fn=clock)
    publisher = CapturePublisher()
    original_publisher = node._estop_pub
    node._estop_pub = publisher
    try:
        node._tick()
        status = SimpleNamespace(
            authority_state="ACTIVE",
            command_authority="FLIGHT_CONTROL",
            actuation_allowed=True,
            global_e_stop_active=False,
        )
        node._on_authority_status(status)
        clock.value = 3.0
        node._tick()
        node._tick()

        assert [message.data for message in publisher.messages] == [True]
        status.actuation_allowed = False
        status.global_e_stop_active = True
        clock.value = 3.1
        node._on_authority_status(status)
        assert node.done
        output = capsys.readouterr().out
        for marker in (
            "WATCHDOG READY",
            "ACTIVE DETECTED",
            "E-STOP TIMER START",
            "E-STOP PUBLISHED",
            "ACTIVE_DETECTED_MONOTONIC=",
            "ESTOP_PUBLISHED_MONOTONIC=",
            "ACTIVE_TO_PUBLISH_SEC=",
            "ESTOP OBSERVED BY FLIGHT",
            "PUBLISH_TO_INHIBIT_SEC=",
        ):
            assert marker in output
    finally:
        node._estop_pub = original_publisher
        node.destroy_node()


def test_node_no_active_timeout_publishes_once(ros_context, capsys) -> None:
    clock = MutableClock()
    node = watchdog.FlightEstopWatchdog(
        active_timeout_sec=10.0,
        monotonic_fn=clock,
    )
    publisher = CapturePublisher()
    original_publisher = node._estop_pub
    node._estop_pub = publisher
    try:
        node._tick()
        clock.value = 11.0
        node._tick()
        node._tick()

        assert [message.data for message in publisher.messages] == [True]
        assert "NO ACTIVE WITHIN TIMEOUT" in capsys.readouterr().out
    finally:
        node._estop_pub = original_publisher
        node.destroy_node()


def test_node_does_not_hide_estop_publish_failure(ros_context) -> None:
    clock = MutableClock()
    node = watchdog.FlightEstopWatchdog(monotonic_fn=clock)
    original_publisher = node._estop_pub
    node._estop_pub = CapturePublisher(error=RuntimeError("publish failed"))
    try:
        node._tick()
        node._on_authority_status(
            SimpleNamespace(
                authority_state="ACTIVE",
                command_authority="FLIGHT_CONTROL",
                actuation_allowed=True,
                global_e_stop_active=False,
            )
        )
        clock.value = 3.0
        with pytest.raises(RuntimeError, match="publish failed"):
            node._tick()
    finally:
        node._estop_pub = original_publisher
        node.destroy_node()


def test_watchdog_source_has_no_authority_or_actuator_control_paths() -> None:
    source = WATCHDOG_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "/flight_control/authority/prepare",
        "PrepareFlightOwnership",
        "CommitFlightOwnership",
        "RevokeFlightOwnership",
        "FlightCommandEnvelope",
        "subprocess",
        "ros2 topic pub",
    ):
        assert forbidden not in source
