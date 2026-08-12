"""Flight Runtime with local preparation and no production actuator takeover."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Mapping

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
    FlightCommandEnvelope as FlightCommandEnvelopeMessage,
    FlightCommandPreview,
    FlightRuntimeStatus,
    MotorFeedbackArray,
    MotorSafetyState,
    OwnershipState,
)
from windarmor_interfaces.srv import (
    CommitFlightOwnership,
    PrepareFlightOwnership,
    RevokeFlightOwnership,
)

from ..core.authority import (
    AuthorityState,
    AuthorityStateMachine,
    CommandAuthority,
    OwnershipDomain,
)
from ..core.envelope import CommandEnvelopeSequencer
from ..core.models import FlightCommand
from ..core.preflight import PreflightContext, PreflightReason, evaluate_preflight
from ..core.validation import validate_flight_command, validate_flight_state
from .config import PARAMETER_DEFAULTS, RuntimeConfig, build_runtime_config
from .controller_loader import load_controller
from .state_aggregator import StateAggregator
from .ownership import (
    HandoffState,
    OwnerHandoffCoordinator,
    OwnerReply,
    OwnershipReadbackTracker,
)


class FlightControlRuntimeNode(Node):
    """Build snapshots, prepare authority, and never dispatch actuators."""

    def __init__(
        self,
        *,
        monotonic_fn: Callable[[], float] = time.monotonic,
        authority_epoch_fn: Callable[[], int] = time.monotonic_ns,
        controller_loader: Callable = load_controller,
        config_overrides: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__("flight_control_runtime_node")
        self._monotonic = monotonic_fn
        self._controller_loader = controller_loader
        for name, default in PARAMETER_DEFAULTS.items():
            self.declare_parameter(name, default)
        raw = {
            name: self.get_parameter(name).value for name in PARAMETER_DEFAULTS
        }
        if config_overrides:
            raw.update(config_overrides)
        self._config: RuntimeConfig = build_runtime_config(raw)
        self._aggregator = StateAggregator(self._config)
        authority_epoch = authority_epoch_fn()
        self._authority = AuthorityStateMachine(
            authority_epoch=authority_epoch,
            takeover_supported=self._config.flight_takeover_enabled,
        )
        self._authority.enable_dry_run()
        self._envelope_sequencer = CommandEnvelopeSequencer(
            self._config.motor_names
        )
        self._handoff = OwnerHandoffCoordinator()
        self._motor_ownership = OwnershipReadbackTracker(OwnershipDomain.MOTOR)
        self._fan_ownership = OwnershipReadbackTracker(OwnershipDomain.FAN)
        self._owner_source_epochs_at_commit: dict[OwnershipDomain, int] = {}
        self._owner_readback_received_at: dict[OwnershipDomain, float] = {}
        self._handoff_started_at: float | None = None
        self._command_pub = None
        self._motor_prepare_client = None
        self._motor_commit_client = None
        self._motor_revoke_client = None
        self._fan_prepare_client = None
        self._fan_commit_client = None
        self._fan_revoke_client = None
        self._last_command_sequence: int | None = None
        self._last_valid_command_at: float | None = None
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

        if self._config.flight_takeover_enabled:
            self._command_pub = self.create_publisher(
                FlightCommandEnvelopeMessage,
                self._config.flight_command_topic,
                observation_qos,
            )
            self._motor_prepare_client = self.create_client(
                PrepareFlightOwnership, self._config.motor_flight_prepare_service
            )
            self._motor_commit_client = self.create_client(
                CommitFlightOwnership, self._config.motor_flight_commit_service
            )
            self._motor_revoke_client = self.create_client(
                RevokeFlightOwnership, self._config.motor_flight_revoke_service
            )
            self._fan_prepare_client = self.create_client(
                PrepareFlightOwnership, self._config.fan_flight_prepare_service
            )
            self._fan_commit_client = self.create_client(
                CommitFlightOwnership, self._config.fan_flight_commit_service
            )
            self._fan_revoke_client = self.create_client(
                RevokeFlightOwnership, self._config.fan_flight_revoke_service
            )
            self.create_subscription(
                OwnershipState,
                self._config.motor_ownership_state_topic,
                self._on_motor_ownership,
                state_qos,
            )
            self.create_subscription(
                OwnershipState,
                self._config.fan_ownership_state_topic,
                self._on_fan_ownership,
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
            "Flight Runtime started: "
            f"flight_takeover_enabled={str(self._config.flight_takeover_enabled).lower()}, "
            "authority=NONE, actuation_allowed=false"
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
                AuthorityState.ACTIVE,
            ):
                if self._handoff.state is not HandoffState.IDLE:
                    self._rollback_handoff(f"invalid {label} observation")
                else:
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

    def _on_motor_ownership(self, message: OwnershipState) -> None:
        self._on_ownership_observation(
            OwnershipDomain.MOTOR, self._motor_ownership, message
        )

    def _on_fan_ownership(self, message: OwnershipState) -> None:
        self._on_ownership_observation(
            OwnershipDomain.FAN, self._fan_ownership, message
        )

    def _on_ownership_observation(self, owner, tracker, message) -> None:
        try:
            tracker.update(message)
        except Exception as exc:
            self.get_logger().warn(
                f"rejected {owner.value} ownership observation: {exc}"
            )
            if self._authority.state in (
                AuthorityState.READY_TO_TAKEOVER,
                AuthorityState.ACTIVE,
            ) and self._handoff.state is not HandoffState.IDLE:
                self._rollback_handoff(
                    f"invalid_{owner.value}_ownership_readback"
                )
            return
        self._owner_readback_received_at[owner] = self._now()
        if self._authority.state is AuthorityState.ACTIVE:
            reason = self._active_owner_mismatch_reason()
            if reason:
                self._rollback_handoff(reason)

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
            AuthorityState.ACTIVE,
        ):
            if self._handoff.state is not HandoffState.IDLE:
                self._rollback_handoff("global_estop_active")
            else:
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
                f"takeover_enabled={self._config.flight_takeover_enabled}"
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
            if self._handoff.state is not HandoffState.IDLE:
                self._rollback_handoff("handoff_cancelled")
                response.success = True
                response.message = "handoff cancelled; owners revoked; runtime inhibited"
                self._publish_authority_status()
                return response
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
            self._handoff.reset()
            self._envelope_sequencer.invalidate()
            self._owner_source_epochs_at_commit.clear()
            self._owner_readback_received_at.clear()
            self._handoff_started_at = None
            self._last_command_sequence = None
            self._last_valid_command_at = None
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
        self._envelope_sequencer.invalidate()
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
            base_state = runtime_snapshot.flight_state
            self._last_state_sequence = base_state.sequence
            validate_flight_state(base_state, self._config.motor_names)
            self._last_runtime_snapshot = runtime_snapshot
            state_valid = True
        except Exception as exc:
            reason = f"invalid FlightState: {exc}"
            if self._handoff.state is not HandoffState.IDLE:
                self._rollback_handoff(reason)
            else:
                self._inhibit(reason)
            self._publish_status(
                state_valid=False,
                command_available=False,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        if self._authority.state is AuthorityState.ACTIVE:
            active_failure = self._active_gate_reason(runtime_snapshot)
            if active_failure:
                self._rollback_handoff(active_failure)
                self._publish_status(
                    state_valid=state_valid,
                    command_available=False,
                    command_valid=False,
                    latest_safe_stop=False,
                )
                return
            state = replace(
                base_state,
                system=replace(
                    base_state.system,
                    command_authority=CommandAuthority.FLIGHT_CONTROL,
                    authority_epoch=self._authority.authority_epoch,
                    authority_generation=self._authority.authority_generation,
                    flight_control_active=True,
                    actuation_allowed=True,
                ),
            )
            try:
                validate_flight_state(state, self._config.motor_names)
            except Exception as exc:
                self._rollback_handoff(f"invalid ACTIVE FlightState: {exc}")
                self._publish_status(
                    state_valid=False,
                    command_available=False,
                    command_valid=False,
                    latest_safe_stop=False,
                )
                return
        else:
            state = base_state
            self._evaluate_authority(runtime_snapshot)
            if self._authority.state is AuthorityState.READY_TO_TAKEOVER:
                if (
                    self._config.flight_takeover_enabled
                    and self._handoff.state is HandoffState.IDLE
                ):
                    self._start_owner_handoff(state.sequence)
                if self._maybe_atomic_commit(runtime_snapshot):
                    self._publish_status(
                        state_valid=state_valid,
                        command_available=False,
                        command_valid=False,
                        latest_safe_stop=False,
                    )
                    return
                if (
                    self._handoff_started_at is not None
                    and now - self._handoff_started_at
                    > self._config.flight_handoff_timeout_sec
                ):
                    self._rollback_handoff("owner_handoff_timeout")
                    self._publish_status(
                        state_valid=state_valid,
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
            reason = f"non-positive monotonic dt: {dt!r}"
            if self._handoff.state is not HandoffState.IDLE:
                self._rollback_handoff(reason)
            else:
                self._inhibit(reason)
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
            if self._authority.state is AuthorityState.ACTIVE:
                self._rollback_handoff(
                    f"controller update/command validation failure: {exc}"
                )
            else:
                self._inhibit(f"controller update/command validation failure: {exc}")
            self._publish_status(
                state_valid=state_valid,
                command_available=command_available,
                command_valid=False,
                latest_safe_stop=False,
            )
            return

        if self._authority.state is AuthorityState.ACTIVE:
            try:
                envelope = self._envelope_sequencer.build(
                    state_sequence=state.sequence,
                    produced_at_sec=now,
                    command=command,
                )
                self._publish_command_envelope(envelope)
                self._last_command_sequence = envelope.command_sequence
                self._last_valid_command_at = now
            except Exception as exc:
                self._rollback_handoff(f"command envelope failure: {exc}")
                command_valid = False
            if command.request_safe_stop:
                self._rollback_handoff("controller_safe_stop")
        else:
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
            if self._handoff.state is not HandoffState.IDLE:
                failure = self._handoff_safety_reason(runtime_snapshot)
                self._last_preflight_reason = failure
                if failure:
                    self._rollback_handoff(failure)
                return
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

    def _handoff_safety_reason(self, runtime_snapshot) -> str:
        state = runtime_snapshot.flight_state
        motor = runtime_snapshot.motor_safety
        fan = runtime_snapshot.fan_safety
        if state.system.e_stop_active is not False:
            return "global_estop_not_explicitly_clear"
        if not state.system.required_inputs_fresh:
            return "required_inputs_stale"
        if motor is None or not runtime_snapshot.motor_safety_fresh:
            return "motor_safety_unknown_or_stale"
        if fan is None or not runtime_snapshot.fan_safety_fresh:
            return "fan_safety_unknown_or_stale"
        if not motor.node_active or motor.e_stop_latched or motor.error_latched:
            return "motor_lower_level_safety_loss"
        if motor.feedback_safety_fault_latched:
            return "motor_feedback_safety_fault"
        if fan.e_stop_latched or not fan.enabled_observed or not fan.enabled:
            return "fan_lower_level_safety_loss"
        return ""

    def _start_owner_handoff(self, state_sequence: int) -> None:
        generation = self._authority.attempt_generation
        if generation is None:
            self._rollback_handoff("missing_authority_attempt")
            return
        try:
            self._handoff.start(
                authority_epoch=self._authority.authority_epoch,
                generation=generation,
                runtime_state_sequence=state_sequence,
            )
            self._handoff_started_at = self._now()
        except Exception as exc:
            self._rollback_handoff(f"handoff_start_failure:{exc}")
            return
        self._call_owner_service(OwnershipDomain.MOTOR, "prepare")
        if self._handoff.state is not HandoffState.RESERVING:
            return
        self._call_owner_service(OwnershipDomain.FAN, "prepare")

    def _owner_client(self, owner: OwnershipDomain, operation: str):
        return {
            (OwnershipDomain.MOTOR, "prepare"): self._motor_prepare_client,
            (OwnershipDomain.MOTOR, "commit"): self._motor_commit_client,
            (OwnershipDomain.MOTOR, "revoke"): self._motor_revoke_client,
            (OwnershipDomain.FAN, "prepare"): self._fan_prepare_client,
            (OwnershipDomain.FAN, "commit"): self._fan_commit_client,
            (OwnershipDomain.FAN, "revoke"): self._fan_revoke_client,
        }[(owner, operation)]

    @staticmethod
    def _service_ready(client) -> bool:
        if client is None:
            return False
        checker = getattr(client, "service_is_ready", None)
        return True if checker is None else bool(checker())

    def _call_owner_service(self, owner: OwnershipDomain, operation: str) -> None:
        client = self._owner_client(owner, operation)
        if not self._service_ready(client):
            self._rollback_handoff(f"{owner.value}_{operation}_service_unavailable")
            return
        service_type = {
            "prepare": PrepareFlightOwnership,
            "commit": CommitFlightOwnership,
            "revoke": RevokeFlightOwnership,
        }[operation]
        request = service_type.Request()
        request.authority_epoch = self._handoff.authority_epoch or 0
        request.generation = self._handoff.generation or 0
        request.runtime_state_sequence = self._last_state_sequence
        try:
            future = client.call_async(request)
            if operation != "revoke":
                future.add_done_callback(
                    lambda completed, domain=owner, action=operation: (
                        self._on_owner_service_response(domain, action, completed)
                    )
                )
        except Exception as exc:
            if operation != "revoke":
                self._rollback_handoff(
                    f"{owner.value}_{operation}_call_failure:{exc}"
                )

    def _on_owner_service_response(self, owner, operation, future) -> None:
        expected_state = (
            HandoffState.RESERVING
            if operation == "prepare"
            else HandoffState.COMMITTING
        )
        if self._handoff.state is not expected_state:
            return
        try:
            response = future.result()
            reply = OwnerReply(
                success=bool(response.success),
                reason_code=str(response.reason_code),
                authority_epoch=int(response.authority_epoch),
                generation=int(response.generation),
                owner_observation_sequence=int(response.owner_observation_sequence),
            )
        except Exception as exc:
            self._rollback_handoff(
                f"{owner.value}_{operation}_response_failure:{exc}"
            )
            return
        if operation == "prepare":
            accepted = self._handoff.record_reserve(owner, reply)
            if self._handoff.state is HandoffState.FAILED:
                self._rollback_handoff(self._handoff.failure_reason)
                return
            if accepted and self._handoff.reserves_complete:
                self._handoff.begin_commit()
                self._call_owner_service(OwnershipDomain.MOTOR, "commit")
                self._call_owner_service(OwnershipDomain.FAN, "commit")
            return
        accepted = self._handoff.record_commit(owner, reply)
        if self._handoff.state is HandoffState.FAILED:
            self._rollback_handoff(self._handoff.failure_reason)
            return
        if accepted:
            generation = self._handoff.generation
            assert generation is not None
            acknowledged = self._authority.acknowledge_owner(
                owner,
                self._authority.authority_epoch,
                generation,
                owner_observed_state_sequence=reply.owner_observation_sequence,
            )
            if not acknowledged:
                self._rollback_handoff(f"{owner.value}_commit_ack_rejected")

    def _owner_readbacks_match(self, phase: str) -> bool:
        now = self._now()
        token = (self._authority.authority_epoch, self._authority.attempt_generation)
        for owner, tracker in (
            (OwnershipDomain.MOTOR, self._motor_ownership),
            (OwnershipDomain.FAN, self._fan_ownership),
        ):
            value = tracker.latest
            received_at = self._owner_readback_received_at.get(owner)
            if (
                value is None
                or received_at is None
                or now - received_at > self._config.flight_owner_state_freshness_sec
                or value.phase != phase
                or (value.authority_epoch, value.generation) != token
            ):
                return False
        return True

    def _maybe_atomic_commit(self, runtime_snapshot) -> bool:
        if self._handoff.state is not HandoffState.OWNERS_COMMITTED:
            return False
        if not self._owner_readbacks_match("FLIGHT_CONTROL"):
            return False
        failure = self._handoff_safety_reason(runtime_snapshot)
        if failure:
            self._rollback_handoff(failure)
            return False
        generation = self._handoff.generation
        assert generation is not None
        try:
            result = self._authority.commit_active(
                authority_epoch=self._authority.authority_epoch,
                generation=generation,
                current_runtime_state_sequence=(
                    runtime_snapshot.flight_state.sequence
                ),
            )
            self._controller.reset()
            self._envelope_sequencer.activate(
                authority_epoch=result.authority_epoch,
                generation=result.generation,
                state_sequence_cutoff=result.arming_cutoff_state_sequence,
            )
            self._owner_source_epochs_at_commit = {
                OwnershipDomain.MOTOR: self._motor_ownership.latest.source_epoch,
                OwnershipDomain.FAN: self._fan_ownership.latest.source_epoch,
            }
            self._handoff_started_at = None
            self._last_command_sequence = None
            self._last_valid_command_at = None
            self._last_tick_at = self._now()
            return True
        except Exception as exc:
            self._rollback_handoff(f"atomic_runtime_commit_failure:{exc}")
            return False

    def _active_owner_mismatch_reason(self) -> str:
        now = self._now()
        token = (self._authority.authority_epoch, self._authority.authority_generation)
        for owner, tracker in (
            (OwnershipDomain.MOTOR, self._motor_ownership),
            (OwnershipDomain.FAN, self._fan_ownership),
        ):
            value = tracker.latest
            if value is None:
                return f"{owner.value}_ownership_unobserved"
            received_at = self._owner_readback_received_at.get(owner)
            if (
                received_at is None
                or now - received_at > self._config.flight_owner_state_freshness_sec
            ):
                return f"{owner.value}_ownership_stale"
            expected_source = self._owner_source_epochs_at_commit.get(owner)
            if expected_source is not None and value.source_epoch != expected_source:
                return f"{owner.value}_owner_process_epoch_changed"
            if value.phase != "FLIGHT_CONTROL":
                return f"{owner.value}_ownership_lost"
            if (value.authority_epoch, value.generation) != token:
                return f"{owner.value}_authority_token_mismatch"
        return ""

    def _active_gate_reason(self, runtime_snapshot) -> str:
        failure = self._handoff_safety_reason(runtime_snapshot)
        if failure:
            return failure
        owner_failure = self._active_owner_mismatch_reason()
        if owner_failure:
            return owner_failure
        motor = runtime_snapshot.motor_safety
        if motor.public_control_mode != "AUTO":
            return "motor_not_auto_for_flight"
        return ""

    def _rollback_handoff(self, reason: str) -> None:
        if not reason:
            reason = "flight_handoff_failure"
        if self._authority.state is AuthorityState.INHIBITED:
            return
        self._handoff.fail(reason)
        for owner in OwnershipDomain:
            self._call_owner_service(owner, "revoke")
        self._owner_source_epochs_at_commit.clear()
        self._handoff_started_at = None
        self._last_command_sequence = None
        self._last_valid_command_at = None
        self._inhibit(reason)

    def destroy_node(self):
        if (
            hasattr(self, "_handoff")
            and self._handoff.state is not HandoffState.IDLE
            and getattr(self, "_authority", None) is not None
            and self._authority.state is not AuthorityState.INHIBITED
        ):
            self._rollback_handoff("runtime_shutdown")
        return super().destroy_node()

    def _publish_command_envelope(self, envelope) -> None:
        if self._command_pub is None:
            raise RuntimeError("Flight command publisher is unavailable")
        message = FlightCommandEnvelopeMessage()
        message.stamp = self.get_clock().now().to_msg()
        message.authority_epoch = envelope.authority_epoch
        message.generation = envelope.generation
        message.command_sequence = envelope.command_sequence
        message.state_sequence = envelope.state_sequence
        message.request_safe_stop = envelope.command.request_safe_stop
        if not envelope.command.request_safe_stop:
            message.motor_names = list(self._config.motor_names)
            message.motor_positions_rad = [
                envelope.command.motor_positions_rad[name]
                for name in self._config.motor_names
            ]
            message.fan_commands_present = True
            message.fan_left = envelope.command.fan_commands.left
            message.fan_right = envelope.command.fan_commands.right
        self._command_pub.publish(message)

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
        message.mode = (
            "ACTIVE"
            if self._authority.state is AuthorityState.ACTIVE
            else "DRY_RUN"
        )
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
        message.authority_epoch = self._authority.authority_epoch
        message.authority_state = self._authority.state.value
        message.command_authority = self._authority.authority.value
        message.authority_generation = self._authority.authority_generation
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
        message.takeover_supported = self._authority.takeover_supported
        message.takeover_enabled = self._config.flight_takeover_enabled
        motor = self._motor_ownership.latest
        fan = self._fan_ownership.latest
        message.motor_reserved = (
            motor is not None and motor.phase == "FLIGHT_RESERVED"
        )
        message.motor_committed = (
            motor is not None and motor.phase == "FLIGHT_CONTROL"
        )
        message.fan_reserved = fan is not None and fan.phase == "FLIGHT_RESERVED"
        message.fan_committed = fan is not None and fan.phase == "FLIGHT_CONTROL"
        token_generation = (
            self._authority.authority_generation
            if self._authority.state is AuthorityState.ACTIVE
            else self._authority.attempt_generation
        )
        message.owner_tokens_match = all(
            value is not None
            and (value.authority_epoch, value.generation)
            == (self._authority.authority_epoch, token_generation)
            for value in (motor, fan)
        )
        cutoff = self._authority.arming_cutoff_state_sequence
        message.atomic_cutoff_present = cutoff is not None
        message.atomic_cutoff_state_sequence = 0 if cutoff is None else cutoff
        message.last_command_present = self._last_command_sequence is not None
        message.last_command_sequence = self._last_command_sequence or 0
        message.last_valid_command_age_sec = (
            -1.0
            if self._last_valid_command_at is None
            else max(0.0, self._now() - self._last_valid_command_at)
        )
        message.actuation_allowed = (
            self._authority.state is AuthorityState.ACTIVE
            and snapshot is not None
            and not self._active_gate_reason(snapshot)
        )
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
