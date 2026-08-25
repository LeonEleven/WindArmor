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
        """Map one state snapshot to an intent using a positive monotonic-seconds dt.

        Controllers must accept a variable update interval. A normal result contains
        the complete configured motor frame; unusable input should yield safe-stop.
        """
        ...
