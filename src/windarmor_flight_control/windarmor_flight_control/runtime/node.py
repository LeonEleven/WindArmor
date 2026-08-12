"""Observation-only Flight Runtime node with non-negotiable DRY_RUN semantics."""

from __future__ import annotations

import time
from typing import Callable

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Int32MultiArray, String, UInt64
from windarmor_interfaces.msg import (
    FlightCommandPreview,
    FlightRuntimeStatus,
    MotorFeedbackArray,
)

from ..core.models import FlightCommand
from ..core.validation import validate_flight_command, validate_flight_state
from .config import PARAMETER_DEFAULTS, RuntimeConfig, build_runtime_config
from .controller_loader import load_controller
from .state_aggregator import StateAggregator


class FlightControlRuntimeNode(Node):
    """Build snapshots and preview controller output; never dispatch actuators."""

    def __init__(
        self,
        *,
        monotonic_fn: Callable[[], float] = time.monotonic,
        controller_loader: Callable = load_controller,
    ) -> None:
        super().__init__("flight_control_runtime_node")
        self._monotonic = monotonic_fn
        for name, default in PARAMETER_DEFAULTS.items():
            self.declare_parameter(name, default)
        raw = {
            name: self.get_parameter(name).value for name in PARAMETER_DEFAULTS
        }
        self._config: RuntimeConfig = build_runtime_config(raw)
        self._aggregator = StateAggregator(self._config)
        self._controller = None
        self._controller_inhibited = False
        self._last_error = ""
        self._last_state_sequence = 0
        self._last_tick_at = self._monotonic()

        try:
            self._controller = controller_loader(
                self._config.controller_factory,
                self._config.motor_names,
            )
            self._controller.reset()
        except Exception as exc:
            self._inhibit(f"controller startup failure: {exc}")

        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        observation_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
        )

        # These are the only publishers owned by Task 2 Runtime.
        self._status_pub = self.create_publisher(
            FlightRuntimeStatus,
            self._config.runtime_status_topic,
            state_qos,
        )
        self._preview_pub = self.create_publisher(
            FlightCommandPreview,
            self._config.command_preview_topic,
            observation_qos,
        )

        self.create_subscription(
            Imu,
            self._config.imu_raw_topic,
            self._on_imu_raw,
            observation_qos,
        )
        self.create_subscription(
            String,
            self._config.imu_status_topic,
            self._on_imu_status,
            observation_qos,
        )
        self.create_subscription(
            Vector3Stamped,
            self._config.imu_relative_topic,
            self._on_imu_relative,
            observation_qos,
        )
        self.create_subscription(
            UInt64,
            self._config.imu_zero_generation_topic,
            self._on_zero_generation,
            state_qos,
        )
        self.create_subscription(
            MotorFeedbackArray,
            self._config.motor_feedback_topic,
            self._on_motor_feedback,
            observation_qos,
        )
        self.create_subscription(
            String,
            self._config.motor_control_mode_topic,
            self._on_motor_mode,
            state_qos,
        )
        self.create_subscription(
            Int32MultiArray,
            self._config.fan_status_pwm_topic,
            self._on_fan_output,
            observation_qos,
        )
        self.create_subscription(
            Bool,
            self._config.fan_enabled_topic,
            self._on_fan_enabled,
            state_qos,
        )
        self.create_subscription(
            String,
            self._config.fan_control_state_topic,
            self._on_fan_control_state,
            state_qos,
        )
        self.create_subscription(
            Bool,
            self._config.e_stop_topic,
            self._on_e_stop,
            observation_qos,
        )
        self._control_timer = self.create_timer(
            1.0 / self._config.control_rate_hz,
            self._control_tick,
        )
        self.get_logger().warn(
            "Flight Runtime started in DRY_RUN: authority=NONE, "
            "actuation_allowed=false, no actuator dispatch exists"
        )

    def _now(self) -> float:
        return float(self._monotonic())

    def _observe(self, label: str, callback: Callable[[], object]) -> None:
        try:
            callback()
        except Exception as exc:
            self.get_logger().warn(f"rejected {label} observation: {exc}")

    def _on_imu_raw(self, message: Imu) -> None:
        received_at = self._now()
        self._observe(
            "IMU raw",
            lambda: self._aggregator.update_imu_raw(message, received_at),
        )

    def _on_imu_status(self, message: String) -> None:
        accepted = self._aggregator.update_imu_status(message.data)
        if not accepted:
            self.get_logger().warn(f"ignored unknown IMU status: {message.data!r}")

    def _on_imu_relative(self, message: Vector3Stamped) -> None:
        received_at = self._now()
        self._observe(
            "IMU relative",
            lambda: self._aggregator.update_imu_relative(message, received_at),
        )

    def _on_zero_generation(self, message: UInt64) -> None:
        self._observe(
            "IMU zero generation",
            lambda: self._aggregator.update_zero_generation(int(message.data)),
        )

    def _on_motor_feedback(self, message: MotorFeedbackArray) -> None:
        received_at = self._now()
        self._observe(
            "motor feedback",
            lambda: self._aggregator.update_motors(message, received_at),
        )

    def _on_motor_mode(self, message: String) -> None:
        received_at = self._now()
        self._observe(
            "motor control mode",
            lambda: self._aggregator.update_motor_mode(message.data, received_at),
        )

    def _on_fan_output(self, message: Int32MultiArray) -> None:
        received_at = self._now()
        self._observe(
            "fan output",
            lambda: self._aggregator.update_fan_output(message, received_at),
        )

    def _on_fan_enabled(self, message: Bool) -> None:
        received_at = self._now()
        self._observe(
            "fan enabled",
            lambda: self._aggregator.update_fan_enabled(
                bool(message.data), received_at
            ),
        )

    def _on_fan_control_state(self, message: String) -> None:
        received_at = self._now()
        self._observe(
            "fan control state",
            lambda: self._aggregator.update_fan_control_state(
                message.data, received_at
            ),
        )

    def _on_e_stop(self, message: Bool) -> None:
        self._observe(
            "e-stop trigger",
            lambda: self._aggregator.update_e_stop(bool(message.data)),
        )

    def _inhibit(self, error: str) -> None:
        if not self._controller_inhibited:
            self._last_error = error
            self.get_logger().error(
                f"DRY_RUN controller inhibited until node restart: {error}"
            )
        self._controller_inhibited = True
        self._controller = None

    def _control_tick(self) -> None:
        now = self._now()
        state_valid = False
        command_available = False
        command_valid = False
        latest_safe_stop = False
        try:
            state = self._aggregator.build_snapshot(now)
            self._last_state_sequence = state.sequence
            validate_flight_state(state, self._config.motor_names)
            state_valid = True
        except Exception as exc:
            self._inhibit(f"invalid FlightState: {exc}")
            self._publish_status(
                state_valid=False,
                command_available=False,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        if self._controller_inhibited or self._controller is None:
            self._publish_status(
                state_valid=state_valid,
                command_available=False,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        dt = now - self._last_tick_at
        self._last_tick_at = now
        if dt <= 0.0:
            self._inhibit(f"non-positive monotonic dt: {dt!r}")
            self._publish_status(
                state_valid=state_valid,
                command_available=False,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        try:
            command = self._controller.update(state, dt)
            command_available = True
            validate_flight_command(command, self._config.motor_names)
            command_valid = True
            latest_safe_stop = command.request_safe_stop
        except Exception as exc:
            self._inhibit(f"controller update/command validation failure: {exc}")
            self._publish_status(
                state_valid=state_valid,
                command_available=command_available,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        self._publish_preview(state.sequence, command)
        self._publish_status(
            state_valid=state_valid,
            command_available=command_available,
            command_valid=command_valid,
            latest_safe_stop=latest_safe_stop,
        )

    def _publish_preview(self, sequence: int, command: FlightCommand) -> None:
        message = FlightCommandPreview()
        message.stamp = self.get_clock().now().to_msg()
        message.state_sequence = sequence
        message.request_safe_stop = command.request_safe_stop
        if not command.request_safe_stop:
            message.motor_names = list(self._config.motor_names)
            message.motor_positions_rad = [
                command.motor_positions_rad[name]
                for name in self._config.motor_names
            ]
            message.fan_commands_present = True
            message.fan_left = command.fan_commands.left
            message.fan_right = command.fan_commands.right
        try:
            self._preview_pub.publish(message)
        except Exception as exc:
            self.get_logger().error(f"failed to publish DRY_RUN preview: {exc}")

    def _publish_status(
        self,
        *,
        state_valid: bool,
        command_available: bool,
        command_valid: bool,
        latest_safe_stop: bool,
    ) -> None:
        message = FlightRuntimeStatus()
        message.stamp = self.get_clock().now().to_msg()
        message.state_sequence = self._last_state_sequence
        message.mode = "DRY_RUN"
        message.state_valid = state_valid
        message.controller_inhibited = self._controller_inhibited
        message.command_available = command_available
        message.command_valid = command_valid
        message.latest_command_safe_stop = latest_safe_stop
        message.last_error = self._last_error
        try:
            self._status_pub.publish(message)
        except Exception as exc:
            self.get_logger().error(f"failed to publish DRY_RUN status: {exc}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = FlightControlRuntimeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
