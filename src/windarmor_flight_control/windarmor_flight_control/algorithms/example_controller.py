"""Minimal API example; this is not a real flight-control algorithm."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from ..core.models import FanCommand, FlightCommand, FlightState


class NeutralExampleController:
    """Return caller-configured neutral motor targets and stopped fans.

    The class exists only to demonstrate and test the Flight API. The configured
    targets are not claimed to be mechanically neutral for any real robot.
    """

    def __init__(self, neutral_motor_positions_rad: Mapping[str, float]) -> None:
        self._neutral_motor_positions_rad = MappingProxyType(
            dict(neutral_motor_positions_rad)
        )

    def reset(self) -> None:
        """Reset algorithm-local state; this stateless example has none."""

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """Build a neutral frame, or request a safe stop when inputs are inhibited."""

        del dt
        if (
            state.system.e_stop_active is not False
            or not state.system.actuation_allowed
            or not state.system.required_inputs_fresh
        ):
            return FlightCommand.safe_stop()
        return FlightCommand(
            motor_positions_rad=self._neutral_motor_positions_rad,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )
