"""Read-only IMU relative-attitude adapter for Flight observation."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import UInt64

from .imu_protocol import corrected_relative_roll_pitch


class ImuRelativeObserverNode(LifecycleNode):
    """Publish corrected roll/pitch without control services or actuator access."""

    def __init__(self) -> None:
        super().__init__("imu_relative_observer_node")
        self.declare_parameter("imu_topic", "/imu/data_raw")
        self.declare_parameter(
            "relative_attitude_topic", "/imu/relative_roll_pitch"
        )
        self.declare_parameter("imu_zero_generation_topic", "/imu/zero_generation")
        self.declare_parameter("roll_axis_sign", 1.0)
        self.declare_parameter("pitch_axis_sign", 1.0)

        self._subscription = None
        self._relative_publisher = None
        self._generation_publisher = None
        self._active = False
        self._roll_axis_sign = 1.0
        self._pitch_axis_sign = 1.0

    def on_configure(self, _state: State) -> TransitionCallbackReturn:
        roll_sign = self.get_parameter("roll_axis_sign").value
        pitch_sign = self.get_parameter("pitch_axis_sign").value
        if roll_sign not in (-1.0, 1.0) or pitch_sign not in (-1.0, 1.0):
            self.get_logger().error("IMU observer axis signs must be +1.0 or -1.0")
            return TransitionCallbackReturn.FAILURE
        self._roll_axis_sign = float(roll_sign)
        self._pitch_axis_sign = float(pitch_sign)
        imu_topic = self.get_parameter("imu_topic").value
        relative_topic = self.get_parameter("relative_attitude_topic").value
        generation_topic = self.get_parameter("imu_zero_generation_topic").value
        if not all(isinstance(value, str) and value for value in (
            imu_topic, relative_topic, generation_topic
        )):
            self.get_logger().error("IMU observer topic names must be non-empty")
            return TransitionCallbackReturn.FAILURE

        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._relative_publisher = self.create_publisher(
            Vector3Stamped, relative_topic, 20
        )
        self._generation_publisher = self.create_publisher(
            UInt64, generation_topic, state_qos
        )
        self._subscription = self.create_subscription(
            Imu, imu_topic, self._on_imu, 20
        )
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, _state: State) -> TransitionCallbackReturn:
        self._active = True
        generation = UInt64()
        generation.data = 0
        self._generation_publisher.publish(generation)
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, _state: State) -> TransitionCallbackReturn:
        self._active = False
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, _state: State) -> TransitionCallbackReturn:
        self._active = False
        if self._subscription is not None:
            self.destroy_subscription(self._subscription)
            self._subscription = None
        if self._relative_publisher is not None:
            self.destroy_publisher(self._relative_publisher)
            self._relative_publisher = None
        if self._generation_publisher is not None:
            self.destroy_publisher(self._generation_publisher)
            self._generation_publisher = None
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        return self.on_cleanup(state)

    def _on_imu(self, message: Imu) -> None:
        if not self._active:
            return
        try:
            _roll, _pitch, relative_roll, relative_pitch = (
                corrected_relative_roll_pitch(
                    message.orientation.x,
                    message.orientation.y,
                    message.orientation.z,
                    message.orientation.w,
                    roll_axis_sign=self._roll_axis_sign,
                    pitch_axis_sign=self._pitch_axis_sign,
                    zero_roll=0.0,
                    zero_pitch=0.0,
                )
            )
        except ValueError as exc:
            self.get_logger().warning(f"Ignoring invalid IMU quaternion: {exc}")
            return
        result = Vector3Stamped()
        result.header = message.header
        result.vector.x = relative_roll
        result.vector.y = relative_pitch
        result.vector.z = 0.0
        self._relative_publisher.publish(result)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ImuRelativeObserverNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
