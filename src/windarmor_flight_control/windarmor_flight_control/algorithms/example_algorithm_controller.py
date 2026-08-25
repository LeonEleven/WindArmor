"""Software-first pitch example for newcomer algorithm development."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from ..core.models import FanCommand, FlightCommand, FlightState


PITCH_TARGET_GAIN = 0.25
MAX_TARGET_OFFSET_RAD = 0.05
FAN_COMMAND_GAIN = 0.5
MAX_FAN_COMMAND = 0.10
TARGET_MOTOR_NAME = "left_pitch"


class ExampleAlgorithmController:
    """Map relative pitch to one bounded motor offset and two fan previews.

    This educational controller has no ROS or hardware dependencies. It captures
    one complete motor-position baseline after reset, then keeps that baseline
    fixed until the next reset or until an unsafe input clears it.
    Its constants are software examples, not mechanical tuning values, and loading
    it never grants actuator authority. It is not the default production controller.
    """

    def __init__(self, required_motor_names: Iterable[str]) -> None:
        self._required_motor_names = tuple(required_motor_names)
        if (
            not self._required_motor_names
            or len(set(self._required_motor_names)) != len(self._required_motor_names)
            or TARGET_MOTOR_NAME not in self._required_motor_names
        ):
            raise ValueError(
                "example controller requires unique motor names including left_pitch"
            )
        self._baseline_positions_rad: Mapping[str, float] | None = None

    def reset(self) -> None:
        """Discard algorithm-local feedback captured during an earlier run."""

        self._baseline_positions_rad = None

    @staticmethod
    def _finite_number(value: object) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _capture_positions(self, state: FlightState) -> Mapping[str, float] | None:
        if set(state.motors) != set(self._required_motor_names):
            return None
        positions: dict[str, float] = {}
        for name in self._required_motor_names:
            motor = state.motors.get(name)
            if (
                motor is None
                or motor.name != name
                or not motor.has_feedback
                or not motor.valid
                or not motor.fresh
                or not motor.healthy
                or not self._finite_number(motor.position_rad)
            ):
                return None
            positions[name] = float(motor.position_rad)
        return MappingProxyType(positions)

    def _safe_stop(self) -> FlightCommand:
        self._baseline_positions_rad = None
        return FlightCommand.safe_stop()

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """Return a complete preview frame, or safe-stop for unusable input."""

        pitch = state.imu.relative_pitch_rad
        if (
            not self._finite_number(dt)
            or float(dt) <= 0.0
            or state.system.e_stop_active is not False
            or not state.system.required_inputs_fresh
            or not state.imu.valid
            or not state.imu.fresh
            or not self._finite_number(pitch)
        ):
            return self._safe_stop()

        positions = self._capture_positions(state)
        if positions is None:
            return self._safe_stop()
        if self._baseline_positions_rad is None:
            self._baseline_positions_rad = positions

        pitch_rad = float(pitch)
        target_offset_rad = self._clamp(
            PITCH_TARGET_GAIN * pitch_rad,
            -MAX_TARGET_OFFSET_RAD,
            MAX_TARGET_OFFSET_RAD,
        )
        targets = dict(self._baseline_positions_rad)
        targets[TARGET_MOTOR_NAME] += target_offset_rad

        left_fan = self._clamp(
            FAN_COMMAND_GAIN * max(pitch_rad, 0.0),
            0.0,
            MAX_FAN_COMMAND,
        )
        right_fan = self._clamp(
            FAN_COMMAND_GAIN * max(-pitch_rad, 0.0),
            0.0,
            MAX_FAN_COMMAND,
        )
        return FlightCommand(
            motor_positions_rad=targets,
            fan_commands=FanCommand(left=left_fan, right=right_fan),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> ExampleAlgorithmController:
    """Create the non-default educational controller for tests and DRY_RUN."""

    del configuration
    return ExampleAlgorithmController(required_motor_names)
