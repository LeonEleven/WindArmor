import math
import os

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn
from sensor_msgs.msg import Imu

from imu_cybergear_ros2.imu_protocol import quaternion_from_euler
from imu_cybergear_ros2.imu_relative_observer_node import ImuRelativeObserverNode


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


def imu_message(roll: float, pitch: float) -> Imu:
    message = Imu()
    message.header.stamp.sec = 7
    message.header.stamp.nanosec = 8
    message.header.frame_id = "imu_link"
    x, y, z, w = quaternion_from_euler(roll, pitch, 0.0)
    message.orientation.x = x
    message.orientation.y = y
    message.orientation.z = z
    message.orientation.w = w
    return message


def test_observer_publishes_generation_zero_and_correlated_relative_attitude() -> None:
    node = ImuRelativeObserverNode()
    relative = CapturePublisher()
    generation = CapturePublisher()
    original_relative = None
    original_generation = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        original_relative = node._relative_publisher
        original_generation = node._generation_publisher
        node._relative_publisher = relative
        node._generation_publisher = generation
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert generation.messages[-1].data == 0

        message = imu_message(0.2, -0.1)
        node._on_imu(message)
        observed = relative.messages[-1]
        assert observed.header.stamp == message.header.stamp
        assert observed.header.frame_id == "imu_link"
        assert observed.vector.x == pytest.approx(0.2)
        assert observed.vector.y == pytest.approx(-0.1)
        assert observed.vector.z == 0.0

        invalid = imu_message(0.0, 0.0)
        invalid.orientation.x = math.nan
        node._on_imu(invalid)
        assert len(relative.messages) == 1
    finally:
        if original_relative is not None:
            node._relative_publisher = original_relative
        if original_generation is not None:
            node._generation_publisher = original_generation
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_observer_has_no_zero_service_or_actuator_dependency() -> None:
    from pathlib import Path

    source = Path(__file__).parents[1] / "imu_cybergear_ros2" / "imu_relative_observer_node.py"
    text = source.read_text(encoding="utf-8")
    assert "create_service" not in text
    assert "motor_manager" not in text.lower()
    assert "cybergear" not in text.lower()
    assert "gpio" not in text.lower()
