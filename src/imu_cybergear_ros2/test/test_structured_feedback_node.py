import os
import time

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.cybergear_driver import MotorStatus
from imu_cybergear_ros2.imu_motor_controller_node import ImuMotorControllerNode

from .fake_motor_driver import FakeMotorDriver


class CapturePublisher:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def valid_status(motor_id=4, **overrides):
    values = dict(
        motor_id=motor_id,
        position_rad=0.25,
        speed_rad_s=-0.5,
        torque_nm=1.0,
        temperature=35.0,
        mode=2,
        fault_flags=0,
        timestamp=1.0,
    )
    values.update(overrides)
    return MotorStatus(**values)


def test_structured_publisher_is_complete_and_adds_no_driver_io() -> None:
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    capture = CapturePublisher()
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(valid_status())
        original = node._motor_feedback_structured_pub
        node._motor_feedback_structured_pub = capture
        calls_before = list(driver.calls)
        node._publish_structured_motor_feedback()
        assert driver.calls == calls_before

        message = capture.messages[-1]
        assert message.sequence == 0
        assert [(item.logical_name, item.can_id) for item in message.motors] == [
            ("left_lift", 4),
            ("left_pitch", 3),
            ("right_pitch", 2),
            ("right_lift", 1),
        ]
        observed = message.motors[0]
        assert observed.has_feedback
        assert observed.position_valid
        assert observed.velocity_valid
        assert observed.torque_valid
        assert observed.temperature_valid
        assert observed.device_mode_valid
        assert observed.fault_flags_valid
        assert observed.valid and observed.fresh and observed.healthy
        assert observed.feedback_age_sec >= 0.0
        missing = message.motors[1]
        assert not missing.has_feedback
        assert not missing.position_valid
        assert not missing.velocity_valid
        assert not missing.torque_valid
        assert not missing.temperature_valid
        assert not missing.device_mode_valid
        assert not missing.fault_flags_valid
        assert not missing.valid and not missing.fresh and not missing.healthy
    finally:
        if original is not None:
            node._motor_feedback_structured_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_observer_stale_and_publication_failure_do_not_change_safety_state() -> None:
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(valid_status())
        with node._lock:
            node._motor_feedback_received_at[4] = time.monotonic() - 10.0
        capture = CapturePublisher()
        original = node._motor_feedback_structured_pub
        node._motor_feedback_structured_pub = capture
        node._publish_structured_motor_feedback()
        assert not capture.messages[-1].motors[0].fresh
        assert not capture.messages[-1].motors[0].healthy

        driver.emit_feedback(valid_status(fault_flags=0x02))
        assert node._motor_safety_fault_active
        fault_snapshot = node._motor_safety_fault_snapshot
        calls_before = list(driver.calls)
        node._motor_feedback_structured_pub = CapturePublisher(
            RuntimeError("injected publication failure")
        )
        node._publish_structured_motor_feedback()
        assert node._motor_safety_fault_active
        assert node._motor_safety_fault_snapshot == fault_snapshot
        assert driver.calls == calls_before
    finally:
        if original is not None:
            node._motor_feedback_structured_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_motor_safety_publisher_is_transient_local_observer_only():
    from rclpy.qos import DurabilityPolicy

    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert (
            node._motor_safety_state_pub.qos_profile.durability
            is DurabilityPolicy.TRANSIENT_LOCAL
        )
        capture = CapturePublisher()
        original = node._motor_safety_state_pub
        node._motor_safety_state_pub = capture
        calls_before = list(driver.calls)
        node._publish_motor_safety_state()
        assert driver.calls == calls_before
        message = capture.messages[-1]
        assert message.node_active
        assert message.controller_state == "MANUAL_RUNNING"
        assert message.public_control_mode == "MANUAL"
        assert not message.e_stop_latched
        assert not message.error_latched
        assert message.transition_present

        state_before = node._state_mgr.state
        node._motor_safety_state_pub = CapturePublisher(RuntimeError("injected"))
        node._publish_motor_safety_state()
        assert node._state_mgr.state is state_before
        assert driver.calls == calls_before
    finally:
        if original is not None:
            node._motor_safety_state_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()
