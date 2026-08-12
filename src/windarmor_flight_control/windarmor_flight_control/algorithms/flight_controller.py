"""Default DRY_RUN example factory; targets are not mechanical references."""

from __future__ import annotations

from ..core.controller import FlightController
from .example_controller import NeutralExampleController


def create_controller(required_motor_names: tuple[str, ...]) -> FlightController:
    """Create the API example with test-only zero values for every logical key."""

    return NeutralExampleController(
        {name: 0.0 for name in required_motor_names}
    )
