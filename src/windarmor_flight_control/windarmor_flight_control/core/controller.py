"""Flight-controller algorithm contract."""

from __future__ import annotations

from typing import Protocol

from .models import FlightCommand, FlightState


class FlightController(Protocol):
    """An algorithm with no ROS or hardware dependencies."""

    def reset(self) -> None:
        """Reset algorithm-local state only."""
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """Compute one complete command frame from an immutable state snapshot."""
        ...
