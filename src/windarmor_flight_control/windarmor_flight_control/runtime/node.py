"""Flight Runtime with local preparation and no production actuator takeover."""

from __future__ import annotations

import time
from typing import Callable

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Int32MultiArray, String, UInt64
from std_srvs.srv import Trigger
from windarmor_interfaces.msg import (
    FanSafetyState,
    FlightAuthorityStatus,
    FlightCommandPreview,
    FlightRuntimeStatus,
    MotorFeedbackArray,
    MotorSafetyState,
)

from ..core.authority import AuthorityState, AuthorityStateMachine, CommandAuthority
from ..core.models import FlightCommand
from ..core.preflight import PreflightContext, PreflightReason, evaluate_preflight
from ..core.validation import validate_flight_command, validate_flight_state
from .config import PARAMETER_DEFAULTS, RuntimeConfig, build_runtime_config
from .controller_loader import load_controller
from .state_aggregator import StateAggregator


class FlightControlRuntimeNode(Node):
    """Build snapshots, prepare authority, and never dispatch actuators."""

    def __init__(
        self,
        *,
        monotonic_fn: Callable[[], float] = time.monotonic,
        controller_loader: Callable = load_controller,
    ) -> None:
        super().__init__("flight_control_runtime_node")
        self._monotonic = monotonic_fn
        self._controller_loader = controller_loader
        for name, default in PARAMETER_DEFAULTS.items():
            self.declare_parameter(name, default)
        raw = {
            name: self.get_parameter(name).value for name in PARAMETER_DEFAULTS
        }
        self._config: RuntimeConfig = build_runtime_config(raw)
        self._aggregator = StateAggregator(self._config)
        # Task 3 production has no owner acknowledgement path and cannot ACTIVE.
        self._authority = AuthorityStateMachine(takeover_supported=False)
        self._authority.enable_dry_run()
        self._controller = None
        self._controller_inhibited = False
        self._last_error = ""
        self._last_state_sequence = 0
        self._last_runtime_snapshot = None
        self._last_preflight_reason = PreflightReason.MOTOR_SAFETY_UNOBSERVED.value
        self._attempt_inputs_were_fresh = False
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
        self._authority_status_pub = self.create_publisher(
            FlightAuthorityStatus,
            self._config.authority_status_topic,
            state_qos,
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
            MotorSafetyState,
            self._config.motor_safety_state_topic,
            self._on_motor_safety,
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
            FanSafetyState,
            self._config.fan_safety_state_topic,
            self._on_fan_safety,
            state_qos,
        )
        self.create_subscription(
            Bool,
            self._config.e_stop_topic,
            self._on_e_stop,
            observation_qos,
        )
        self._prepare_service = self.create_service(
            Trigger,
            self._config.authority_prepare_service,
            self._on_prepare,
        )
        self._cancel_service = self.create_service(
            Trigger,
            self._config.authority_cancel_service,
            self._on_cancel,
        )
        self._reset_inhibit_service = self.create_service(
            Trigger,
            self._config.authority_reset_inhibit_service,
            self._on_reset_inhibit,
        )
        self._control_timer = self.create_timer(
            1.0 / self._config.control_rate_hz,
            self._control_tick,
        )
        self.get_logger().warn(
            "Flight Runtime started with Task 3 preparation only: "
            "takeover_supported=false, authority=NONE, "
            "actuation_allowed=false, no actuator dispatch exists"
        )

    def _now(self) -> float:
        return float(self._monotonic())

    def _observe(
        self,
        label: str,
        callback: Callable[[], object],
        *,
        safety_critical: bool = False,
    ) -> None:
        try:
            callback()
        except Exception as exc:
            self.get_logger().warn(f"rejected {label} observation: {exc}")
            if safety_critical and self._authority.state in (
                AuthorityState.ARMING,
                AuthorityState.READY_TO_TAKEOVER,
            ):
                self._inhibit(f"invalid {label} observation: {exc}")

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

    def _on_motor_safety(self, message: MotorSafetyState) -> None:
        received_at = self._now()
        self._observe(
            "motor safety",
            lambda: self._aggregator.update_motor_safety(message, received_at),
            safety_critical=True,
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

    def _on_fan_safety(self, message: FanSafetyState) -> None:
        received_at = self._now()
        self._observe(
            "fan safety",
            lambda: self._aggregator.update_fan_safety(message, received_at),
            safety_critical=True,
        )

    def _on_e_stop(self, message: Bool) -> None:
        received_at = self._now()
        self._observe(
            "e-stop trigger",
            lambda: self._aggregator.update_e_stop(
                bool(message.data), received_at
            ),
        )
        if bool(message.data) and self._authority.state in (
            AuthorityState.ARMING,
            AuthorityState.READY_TO_TAKEOVER,
        ):
            self._inhibit("global_estop_active")

    def _on_prepare(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        try:
            generation = self._authority.prepare()
            self._attempt_inputs_were_fresh = False
            response.success = True
            response.message = (
                f"authority preparation started: generation={generation}; "
                "takeover remains unsupported"
            )
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        self._publish_authority_status()
        return response

    def _on_cancel(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        try:
            self._authority.cancel()
            self._attempt_inputs_were_fresh = False
            response.success = True
            response.message = "authority preparation cancelled; attempt invalidated"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        self._publish_authority_status()
        return response

    def _on_reset_inhibit(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        try:
            if self._authority.state is not AuthorityState.INHIBITED:
                raise RuntimeError("authority is not inhibited")
            if self._controller is None:
                self._controller = self._controller_loader(
                    self._config.controller_factory,
                    self._config.motor_names,
                )
            self._controller.reset()
            self._authority.reset_inhibit()
            self._controller_inhibited = False
            self._last_error = ""
            self._last_preflight_reason = ""
            self._attempt_inputs_were_fresh = False
            self._last_tick_at = self._now()
            response.success = True
            response.message = "inhibit reset to DRY_RUN; explicit prepare is required"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
            if self._authority.state is not AuthorityState.INHIBITED:
                self._inhibit(f"reset-inhibit failure: {exc}")
        self._publish_authority_status()
        return response

    def _inhibit(self, error: str) -> None:
        if not self._controller_inhibited:
            self._last_error = error
            self.get_logger().error(
                f"DRY_RUN controller inhibited; explicit reset-inhibit is required: {error}"
            )
        self._controller_inhibited = True
        if self._authority.state is not AuthorityState.INHIBITED:
            self._authority.inhibit(error)

    def _control_tick(self) -> None:
        now = self._now()
        state_valid = False
        command_available = False
        command_valid = False
        latest_safe_stop = False
        try:
            runtime_snapshot = self._aggregator.build_runtime_snapshot(now)
            state = runtime_snapshot.flight_state
            self._last_state_sequence = state.sequence
            validate_flight_state(state, self._config.motor_names)
            self._last_runtime_snapshot = runtime_snapshot
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

        self._evaluate_authority(runtime_snapshot)

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

    def _evaluate_authority(self, runtime_snapshot) -> None:
        if self._authority.state not in (
            AuthorityState.ARMING,
            AuthorityState.READY_TO_TAKEOVER,
        ):
            return
        state = runtime_snapshot.flight_state
        context = PreflightContext(
            state=state,
            motor_safety=runtime_snapshot.motor_safety,
            fan_safety=runtime_snapshot.fan_safety,
            motor_safety_fresh=runtime_snapshot.motor_safety_fresh,
            fan_safety_fresh=runtime_snapshot.fan_safety_fresh,
            controller_loaded=self._controller is not None,
            controller_inhibited=self._controller_inhibited,
            monotonic_valid=True,
            no_conflicting_attempt=self._authority.attempt_generation is not None,
        )
        result = evaluate_preflight(context)
        self._last_preflight_reason = "" if result.ready else result.reason.value
        if state.system.required_inputs_fresh:
            self._attempt_inputs_were_fresh = True

        if self._authority.state is AuthorityState.READY_TO_TAKEOVER:
            self._authority.observe_preflight(
                ready=result.ready,
                reason=result.reason.value,
                current_runtime_state_sequence=state.sequence,
            )
            if self._authority.state is AuthorityState.INHIBITED:
                self._controller_inhibited = True
                self._last_error = result.reason.value
            return

        fatal = self._arming_inhibit_reason(runtime_snapshot)
        if fatal:
            self._inhibit(fatal)
            return
        self._authority.observe_preflight(
            ready=result.ready,
            reason=result.reason.value,
            current_runtime_state_sequence=state.sequence,
        )

    def _arming_inhibit_reason(self, runtime_snapshot) -> str:
        state = runtime_snapshot.flight_state
        motor = runtime_snapshot.motor_safety
        fan = runtime_snapshot.fan_safety
        if state.system.e_stop_active is True:
            return PreflightReason.GLOBAL_ESTOP_ACTIVE.value
        if motor is not None and not runtime_snapshot.motor_safety_fresh:
            return PreflightReason.MOTOR_SAFETY_STALE.value
        if fan is not None and not runtime_snapshot.fan_safety_fresh:
            return PreflightReason.FAN_SAFETY_STALE.value
        if motor is not None:
            if motor.error_latched:
                return PreflightReason.MOTOR_ERROR_LATCHED.value
            if motor.feedback_safety_fault_latched:
                return PreflightReason.MOTOR_FEEDBACK_SAFETY_FAULT.value
            if motor.public_control_mode in {
                "AUTO", "ERROR", "EMERGENCY_STOP", "DISABLED"
            }:
                return PreflightReason.MOTOR_MODE_NOT_MANUAL.value
        if fan is not None:
            if fan.e_stop_latched:
                return PreflightReason.FAN_ESTOP_LATCHED.value
            if fan.enabled_observed and not fan.enabled:
                return PreflightReason.FAN_DISABLED.value
            if fan.legacy_auto_requested or fan.legacy_auto_active:
                return PreflightReason.FAN_LEGACY_AUTO_ACTIVE.value
            if fan.manual_armed:
                return PreflightReason.FAN_MANUAL_ARMED.value
            if not fan.passive_for_takeover:
                return PreflightReason.FAN_NOT_PASSIVE.value
        if self._attempt_inputs_were_fresh and not state.system.required_inputs_fresh:
            return PreflightReason.REQUIRED_INPUTS_STALE.value
        return ""

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
        self._publish_authority_status()

    def _publish_authority_status(self) -> None:
        if not hasattr(self, "_authority_status_pub"):
            return
        message = FlightAuthorityStatus()
        message.stamp = self.get_clock().now().to_msg()
        message.state_sequence = self._last_state_sequence
        message.authority_state = self._authority.state.value
        # Task 3 production truth is fixed regardless of preparation state.
        message.command_authority = CommandAuthority.NONE.value
        message.authority_generation = 0
        attempt = self._authority.attempt_generation
        message.attempt_present = attempt is not None
        message.attempt_generation = 0 if attempt is None else attempt
        message.preparing = self._authority.state in (
            AuthorityState.ARMING,
            AuthorityState.READY_TO_TAKEOVER,
        )
        message.preflight_ready = (
            self._authority.state is AuthorityState.READY_TO_TAKEOVER
        )
        message.controller_inhibited = self._controller_inhibited
        snapshot = self._last_runtime_snapshot
        if snapshot is not None:
            e_stop = snapshot.flight_state.system.e_stop_active
            message.global_e_stop_observed = e_stop is not None
            message.global_e_stop_active = e_stop is True
            message.motor_safety_state_fresh = snapshot.motor_safety_fresh
            message.fan_safety_state_fresh = snapshot.fan_safety_fresh
        message.last_preflight_failure_reason = self._last_preflight_reason
        message.last_inhibit_reason = self._authority.last_inhibit_reason
        message.takeover_supported = False
        try:
            self._authority_status_pub.publish(message)
        except Exception as exc:
            self.get_logger().error(f"failed to publish authority status: {exc}")


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
