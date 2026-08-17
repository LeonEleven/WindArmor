import os

import pytest
import rclpy
from rclpy.node import Node

from windarmor_fan_controller.fan_command_manager import FanCommandManager
from windarmor_fan_controller.fan_control import FanControlState
from windarmor_fan_controller.fan_ownership import FanCommandOwner


class CapturePublisher:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


@pytest.fixture
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def test_destroy_after_context_shutdown_does_not_publish_or_raise(
    ros_context,
) -> None:
    node = FanCommandManager(source_epoch_fn=lambda: 700)
    try:
        rclpy.shutdown()

        node.destroy_node()

        assert node._core.state is FanControlState.SAFE_STOP
        assert node._core.ownership.owner is FanCommandOwner.NONE
    finally:
        Node.destroy_node(node)


def test_valid_context_shutdown_publishes_final_stop_and_releases_owner(
    ros_context,
) -> None:
    node = FanCommandManager(source_epoch_fn=lambda: 701)
    command_publisher = node._command_pub
    capture = CapturePublisher()
    node._command_pub = capture
    try:
        with node._core_lock:
            assert node._core.update_fan_enabled(True, 1.0)
            assert node._core.update_motor_mode("AUTO", 1.0)
            assert node._core.update_e_stop(False, 1.0)
            assert node._core.prepare_flight_ownership(10, 1, now=1.01).success
            assert node._core.ownership.owner is FanCommandOwner.FLIGHT_RESERVED

        node.destroy_node()

        assert [list(message.data) for message in capture.messages] == [[800, 800]]
        assert node._core.state is FanControlState.SAFE_STOP
        assert node._core.ownership.owner is FanCommandOwner.NONE
    finally:
        node._command_pub = command_publisher
        Node.destroy_node(node)


def test_repeated_destroy_is_idempotent_and_does_not_republish(
    ros_context,
) -> None:
    node = FanCommandManager(source_epoch_fn=lambda: 702)
    command_publisher = node._command_pub
    capture = CapturePublisher()
    node._command_pub = capture
    try:
        node.destroy_node()
        node.destroy_node()

        assert [list(message.data) for message in capture.messages] == [[800, 800]]
        assert node._core.ownership.owner is FanCommandOwner.NONE
    finally:
        node._command_pub = command_publisher
        Node.destroy_node(node)


def test_shutdown_preserves_estop_dominance(ros_context) -> None:
    node = FanCommandManager(source_epoch_fn=lambda: 703)
    command_publisher = node._command_pub
    capture = CapturePublisher()
    node._command_pub = capture
    try:
        with node._core_lock:
            assert node._core.update_e_stop(True, 1.0)

        node.destroy_node()

        assert [list(message.data) for message in capture.messages] == [[800, 800]]
        assert node._core.e_stop_latched
        assert node._core.state is FanControlState.EMERGENCY_STOP
        assert node._core.ownership.owner is FanCommandOwner.NONE
    finally:
        node._command_pub = command_publisher
        Node.destroy_node(node)


def test_valid_context_publish_failure_is_not_swallowed(ros_context) -> None:
    node = FanCommandManager(source_epoch_fn=lambda: 704)
    command_publisher = node._command_pub
    node._command_pub = CapturePublisher(RuntimeError("injected publish failure"))
    try:
        with pytest.raises(RuntimeError, match="injected publish failure"):
            node.destroy_node()

        node.destroy_node()
        assert node._core.ownership.owner is FanCommandOwner.NONE
    finally:
        node._command_pub = command_publisher
        Node.destroy_node(node)
