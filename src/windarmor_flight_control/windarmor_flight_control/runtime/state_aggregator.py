"""Thread-safe monotonic aggregation into immutable FlightState snapshots."""

from __future__ import annotations

import math
import threading
from typing import Any

from ..core.authority import CommandAuthority
from ..core.models import FlightState, SystemState
from .config import RuntimeConfig
from .fan_adapter import FanAdapter
from .imu_adapter import ImuAdapter
from .motor_adapter import MotorAdapter


class StateAggregator:
    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._imu = ImuAdapter()
        self._motors = MotorAdapter(config.motor_names)
        self._fans = FanAdapter(
            config.fan_observer_min_pwm_us,
            config.fan_observer_max_pwm_us,
        )
        self._motor_mode: str | None = None
        self._motor_mode_received_at: float | None = None
        self._e_stop_active: bool | None = None
        self._sequence = 0
        self._last_snapshot_time: float | None = None

    @property
    def required_motor_names(self) -> tuple[str, ...]:
        return self._config.motor_names

    def update_imu_raw(self, message: Any, received_at: float) -> None:
        with self._lock:
            self._imu.update_raw(message, received_at)

    def update_imu_relative(self, message: Any, received_at: float) -> None:
        with self._lock:
            self._imu.update_relative(message, received_at)

    def update_imu_status(self, status: str) -> bool:
        with self._lock:
            return self._imu.update_status(status)

    def update_zero_generation(self, generation: int) -> None:
        with self._lock:
            self._imu.update_zero_generation(generation)

    def update_motors(self, message: Any, received_at: float) -> None:
        with self._lock:
            self._motors.update(message, received_at)

    def update_fan_output(self, message: Any, received_at: float) -> None:
        with self._lock:
            self._fans.update_output(message, received_at)

    def update_fan_enabled(self, enabled: bool, received_at: float) -> None:
        with self._lock:
            self._fans.update_enabled(enabled, received_at)

    def update_fan_control_state(self, state: str, received_at: float) -> None:
        with self._lock:
            self._fans.update_control_state(state, received_at)

    def update_motor_mode(self, mode: str, received_at: float) -> None:
        if not isinstance(mode, str) or not mode:
            raise ValueError("motor control mode must be a non-empty string")
        if not math.isfinite(received_at) or received_at < 0.0:
            raise ValueError("motor mode receive time must be finite and non-negative")
        with self._lock:
            self._motor_mode = mode
            self._motor_mode_received_at = received_at

    def update_e_stop(self, active: bool) -> None:
        if not isinstance(active, bool):
            raise ValueError("e-stop observation must be a bool")
        with self._lock:
            # /e_stop is a trigger channel, not authoritative clear readback.
            if active:
                self._e_stop_active = True

    def build_snapshot(self, now: float) -> FlightState:
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("snapshot time must be finite and non-negative")
        with self._lock:
            if (
                self._last_snapshot_time is not None
                and now < self._last_snapshot_time
            ):
                raise ValueError("snapshot monotonic time moved backwards")
            imu = self._imu.snapshot(
                now=now,
                freshness_sec=self._config.flight_imu_freshness_sec,
            )
            motors = self._motors.snapshot(
                now=now,
                freshness_sec=self._config.flight_motor_freshness_sec,
            )
            fans = self._fans.snapshot(
                now=now,
                output_freshness_sec=(
                    self._config.flight_fan_output_freshness_sec
                ),
                state_freshness_sec=self._config.flight_fan_state_freshness_sec,
            )
            motor_mode = None
            if (
                self._motor_mode_received_at is not None
                and now - self._motor_mode_received_at
                <= self._config.flight_control_state_freshness_sec
            ):
                motor_mode = self._motor_mode
            required_inputs_fresh = imu.fresh and all(
                motor.fresh for motor in motors.values()
            )
            sequence = self._sequence
            self._sequence += 1
            self._last_snapshot_time = now
            return FlightState(
                timestamp_sec=now,
                sequence=sequence,
                imu=imu,
                motors=motors,
                fans=fans,
                system=SystemState(
                    command_authority=CommandAuthority.NONE,
                    authority_generation=0,
                    e_stop_active=self._e_stop_active,
                    motor_control_mode=motor_mode,
                    fan_control_state=fans.control_state,
                    flight_control_active=False,
                    actuation_allowed=False,
                    required_inputs_fresh=required_inputs_fresh,
                ),
            )
