"""Passive CyberGear feedback observer with no actuator API calls."""

from __future__ import annotations

import threading
import time
from typing import Callable

import rclpy
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from windarmor_interfaces.msg import MotorFeedback, MotorFeedbackArray

from .cybergear_driver import CyberGearDriver
from .motor_health import (
    MotorHealthAction,
    MotorHealthConfig,
    MotorHealthCore,
    MotorHealthReason,
)
from .observation_config import (
    OBSERVER_DEFAULTS,
    OBSERVER_PARAMETER_NAMES,
    MotorObservationConfig,
    build_motor_observation_config,
)
from .structured_feedback import build_structured_feedback
from .transport_recovery import TransportEvent


class MotorFeedbackObserverNode(LifecycleNode):
    """Open only a transport reader and publish validated 0x02 feedback."""

    def __init__(
        self,
        *,
        driver_factory: Callable[..., object] = CyberGearDriver,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__("motor_feedback_observer_node")
        self._driver_factory = driver_factory
        self._monotonic = monotonic_fn
        for name in OBSERVER_PARAMETER_NAMES:
            self.declare_parameter(name, OBSERVER_DEFAULTS[name])

        self._lock = threading.RLock()
        self._config: MotorObservationConfig | None = None
        self._driver = None
        self._health = None
        self._feedback_by_id = {}
        self._received_at_by_id = {}
        self._feedback_publisher = None
        self._status_publisher = None
        self._publish_timer = None
        self._sequence = 0
        self._active = False

    def on_configure(self, _state: State) -> TransitionCallbackReturn:
        try:
            raw = {name: self.get_parameter(name).value for name in OBSERVER_PARAMETER_NAMES}
            config = build_motor_observation_config(raw)
            driver = self._driver_factory(
                backend=config.backend,
                master_id=config.master_id,
                usb_port=config.usb_port,
                usb_baud=config.usb_baud,
                can_channel=config.can_channel,
                can_bustype=config.can_bustype,
            )
            driver.register_feedback_callback(self._on_feedback)
            if hasattr(driver, "register_feedback_error_callback"):
                driver.register_feedback_error_callback(self._on_feedback_error)
            if hasattr(driver, "register_transport_event_callback"):
                driver.register_transport_event_callback(self._on_transport_event)
            # Commit the non-connected driver before ROS resource creation so a
            # later configure failure can release every callback deterministically.
            self._config = config
            self._driver = driver

            state_qos = QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._feedback_publisher = self.create_publisher(
                MotorFeedbackArray, config.feedback_topic, 10
            )
            self._status_publisher = self.create_publisher(
                String, config.status_topic, state_qos
            )
            self._publish_timer = self.create_timer(
                1.0 / config.publish_rate_hz, self._publish_feedback
            )
            self._health = MotorHealthCore(
                MotorHealthConfig(
                    motor_ids=tuple(channel.motor_id for channel in config.channels),
                    temp_warning_deg_c=config.warning_temperature_c,
                    temp_critical_deg_c=config.critical_temperature_c,
                    invalid_feedback_limit=config.invalid_feedback_limit,
                    feedback_timeout_sec=0.0,
                    feedback_startup_grace_sec=1.0,
                )
            )
            self._feedback_by_id = {}
            self._received_at_by_id = {}
            self._sequence = 0
            self._publish_status("configured")
        except Exception as exc:
            self.get_logger().error(f"Motor observer configuration failed: {exc}")
            self._release_resources()
            return TransitionCallbackReturn.FAILURE
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, _state: State) -> TransitionCallbackReturn:
        if self._driver is None or self._config is None or self._health is None:
            return TransitionCallbackReturn.FAILURE
        connected = self._driver.connect_with_retry(
            max_attempts=self._config.connect_max_attempts,
            initial_delay=self._config.connect_initial_delay_sec,
            on_status=self._publish_status,
        )
        if not connected:
            self._publish_status("disconnected")
            return TransitionCallbackReturn.FAILURE
        self._health.activate(self._monotonic())
        self._active = True
        self._publish_status("connected")
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, _state: State) -> TransitionCallbackReturn:
        self._active = False
        if self._health is not None:
            self._health.deactivate()
        self._close_reader()
        self._publish_status("disconnected")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, _state: State) -> TransitionCallbackReturn:
        self._active = False
        return (
            TransitionCallbackReturn.SUCCESS
            if self._release_resources()
            else TransitionCallbackReturn.FAILURE
        )

    def on_shutdown(self, _state: State) -> TransitionCallbackReturn:
        self._active = False
        return (
            TransitionCallbackReturn.SUCCESS
            if self._release_resources()
            else TransitionCallbackReturn.FAILURE
        )

    def _on_feedback(self, status: object) -> None:
        if not self._active or self._health is None:
            return
        received_at = self._monotonic()
        decision = self._health.evaluate(status, received_at=received_at)
        if (
            decision.action is MotorHealthAction.IGNORE
            or decision.reason is MotorHealthReason.INVALID_FEEDBACK
        ):
            self.get_logger().warning(decision.diagnostic_message)
            return
        with self._lock:
            self._feedback_by_id[decision.motor_id] = status
            self._received_at_by_id[decision.motor_id] = received_at
        if decision.action is not MotorHealthAction.ACCEPT:
            self.get_logger().warning(decision.diagnostic_message)

    def _on_feedback_error(self, exc: Exception) -> None:
        self.get_logger().error(f"Motor observer feedback callback failed: {exc}")

    def _on_transport_event(self, event: TransportEvent) -> None:
        self._active = False
        self._close_reader()
        self._publish_status(
            f"disconnected:{event.event_type.value}:{event.operation}"
        )

    def _publish_feedback(self) -> None:
        config = self._config
        publisher = self._feedback_publisher
        if config is None or publisher is None:
            return
        try:
            now = self._monotonic()
            with self._lock:
                snapshot = build_structured_feedback(
                    config.channels,
                    dict(self._feedback_by_id),
                    dict(self._received_at_by_id),
                    now=now,
                    freshness_sec=config.freshness_sec,
                    critical_temperature_c=config.critical_temperature_c,
                    safety_fault_active=None,
                )
                sequence = self._sequence
                self._sequence += 1
            message = MotorFeedbackArray()
            message.stamp = self.get_clock().now().to_msg()
            message.sequence = sequence
            for item in snapshot:
                motor = MotorFeedback()
                motor.logical_name = item.logical_name
                motor.can_id = item.can_id
                motor.has_feedback = item.has_feedback
                if item.has_feedback:
                    motor.position_valid = True
                    motor.position_rad = item.position_rad
                    motor.velocity_valid = True
                    motor.velocity_rad_s = item.velocity_rad_s
                    motor.torque_valid = True
                    motor.torque_nm = item.torque_nm
                    motor.temperature_valid = True
                    motor.temperature_c = item.temperature_c
                    motor.device_mode_valid = True
                    motor.device_mode = item.device_mode
                    motor.fault_flags_valid = True
                    motor.fault_flags = item.fault_flags
                    motor.feedback_age_sec = item.feedback_age_sec
                motor.valid = item.valid
                motor.fresh = item.fresh
                motor.healthy = item.healthy
                message.motors.append(motor)
            publisher.publish(message)
        except Exception as exc:
            self.get_logger().error(f"Motor observer publish failed: {exc}")

    def _publish_status(self, value: str) -> None:
        if self._status_publisher is None:
            return
        message = String()
        message.data = value
        self._status_publisher.publish(message)

    def _close_reader(self) -> bool:
        driver = self._driver
        if driver is None:
            return True
        try:
            driver.close()
            return True
        except Exception as exc:
            self.get_logger().error(f"Motor observer transport close failed: {exc}")
            return False

    def _release_resources(self) -> bool:
        success = self._close_reader()
        driver = self._driver
        self._driver = None
        if driver is not None:
            try:
                if hasattr(driver, "clear_feedback_callbacks"):
                    driver.clear_feedback_callbacks()
                if hasattr(driver, "clear_transport_event_callbacks"):
                    driver.clear_transport_event_callbacks()
            except Exception as exc:
                self.get_logger().error(f"Motor observer callback cleanup failed: {exc}")
                success = False
        if self._publish_timer is not None:
            self.destroy_timer(self._publish_timer)
            self._publish_timer = None
        if self._feedback_publisher is not None:
            self.destroy_publisher(self._feedback_publisher)
            self._feedback_publisher = None
        if self._status_publisher is not None:
            self.destroy_publisher(self._status_publisher)
            self._status_publisher = None
        self._config = None
        self._health = None
        self._feedback_by_id = {}
        self._received_at_by_id = {}
        self._sequence = 0
        return success


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MotorFeedbackObserverNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
