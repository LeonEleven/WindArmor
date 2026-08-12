import os
from pathlib import Path

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.cybergear_driver import MotorStatus
from imu_cybergear_ros2.motor_feedback_observer_node import MotorFeedbackObserverNode
from imu_cybergear_ros2.transport_recovery import TransportEvent, TransportEventType

from .fake_motor_driver import FakeMotorDriver


ACTUATOR_OPERATIONS = {
    "send_motor_cmd",
    "send_motion_control",
    "write_sdo_int",
    "write_sdo_float",
    "enter_control_mode",
    "stop_motor",
    "set_zero",
    "enable_motor",
    "disable_motor",
}


class Clock:
    def __init__(self, now=10.0):
        self.now = now

    def __call__(self):
        return self.now


class CapturePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def status(motor_id=4, **overrides):
    values = dict(
        motor_id=motor_id,
        position_rad=0.25,
        speed_rad_s=-0.5,
        torque_nm=1.0,
        temperature=35.0,
        mode=2,
        fault_flags=0,
        timestamp=10.0,
    )
    values.update(overrides)
    return MotorStatus(**values)


def assert_no_actuator_calls(driver) -> None:
    assert ACTUATOR_OPERATIONS.isdisjoint(call[0] for call in driver.calls)


def test_lifecycle_feedback_and_cleanup_are_receive_only() -> None:
    driver = FakeMotorDriver()
    clock = Clock()
    node = MotorFeedbackObserverNode(
        driver_factory=lambda **_kwargs: driver,
        monotonic_fn=clock,
    )
    capture = CapturePublisher()
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert_no_actuator_calls(driver)
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert_no_actuator_calls(driver)

        driver.emit_feedback(status())
        original = node._feedback_publisher
        node._feedback_publisher = capture
        node._publish_feedback()
        message = capture.messages[-1]
        assert [(item.logical_name, item.can_id) for item in message.motors] == [
            ("left_lift", 4),
            ("left_pitch", 3),
            ("right_pitch", 2),
            ("right_lift", 1),
        ]
        observed = message.motors[0]
        assert observed.has_feedback and observed.valid and observed.fresh
        assert not observed.healthy
        assert observed.position_rad == pytest.approx(0.25)
        assert not message.motors[1].has_feedback

        clock.now = 11.0
        node._publish_feedback()
        assert not capture.messages[-1].motors[0].fresh
        assert_no_actuator_calls(driver)
    finally:
        if original is not None:
            node._feedback_publisher = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        assert_no_actuator_calls(driver)
        node.destroy_node()


def test_invalid_and_unknown_feedback_are_not_published_as_measurements() -> None:
    driver = FakeMotorDriver()
    clock = Clock()
    node = MotorFeedbackObserverNode(
        driver_factory=lambda **_kwargs: driver,
        monotonic_fn=clock,
    )
    capture = CapturePublisher()
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(status(position_rad=float("nan")))
        driver.emit_feedback(status(motor_id=99))
        original = node._feedback_publisher
        node._feedback_publisher = capture
        node._publish_feedback()
        assert all(not item.has_feedback for item in capture.messages[-1].motors)
    finally:
        if original is not None:
            node._feedback_publisher = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        assert_no_actuator_calls(driver)
        node.destroy_node()


def test_transport_fault_closes_reader_without_reconnect_or_stop() -> None:
    driver = FakeMotorDriver()
    node = MotorFeedbackObserverNode(driver_factory=lambda **_kwargs: driver)
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        event = TransportEvent(
            event_type=TransportEventType.READ_ERROR,
            backend="fake",
            operation="read",
            message="injected",
            monotonic_timestamp=1.0,
            connection_generation=driver.connection_generation,
        )
        driver.emit_transport_event(event)
        assert not node._active
        assert [call[0] for call in driver.calls].count("connect") == 1
        assert [call[0] for call in driver.calls].count("close") == 1
        assert_no_actuator_calls(driver)
    finally:
        node.on_cleanup(None)
        assert_no_actuator_calls(driver)
        node.destroy_node()


def test_observer_source_has_no_control_manager_or_forbidden_driver_call() -> None:
    source_path = Path(__file__).parents[1] / "imu_cybergear_ros2" / "motor_feedback_observer_node.py"
    source = source_path.read_text(encoding="utf-8")
    assert "motor_manager" not in source.lower()
    assert "create_service" not in source
    for operation in ACTUATOR_OPERATIONS:
        assert f".{operation}(" not in source
