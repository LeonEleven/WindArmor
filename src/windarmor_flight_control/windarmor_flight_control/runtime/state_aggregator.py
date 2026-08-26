"""以线程安全、单调的方式聚合为不可变 ``FlightState`` 状态快照。"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any

from ..core.authority import CommandAuthority
from ..core.models import FlightState, SystemState
from ..core.preflight import FanSafetyReadback, MotorSafetyReadback
from .config import RuntimeConfig
from .fan_adapter import FanAdapter
from .imu_adapter import ImuAdapter
from .motor_adapter import MotorAdapter
from .safety_adapter import SafetyReadbackAdapter


@dataclass(frozen=True)
class RuntimeSnapshot:
    """一份一致的算法状态，以及单独提供的权威安全回读。"""

    flight_state: FlightState
    motor_safety: MotorSafetyReadback | None
    fan_safety: FanSafetyReadback | None
    motor_safety_fresh: bool
    fan_safety_fresh: bool


class StateAggregator:
    """在同一把锁内配对观测，并生成单调、不可变的状态快照。

    缺失或过期观测保持未知，不会变成健康默认值。聚合过程只读，既不授予控制权，
    也不控制硬件。
    """

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._imu = ImuAdapter()
        self._motors = MotorAdapter(config.motor_names)
        self._fans = FanAdapter(
            config.fan_observer_min_pwm_us,
            config.fan_observer_max_pwm_us,
        )
        self._safety = SafetyReadbackAdapter()
        self._motor_mode: str | None = None
        self._motor_mode_received_at: float | None = None
        self._e_stop_triggered_at: float | None = None
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

    def update_motor_safety(self, message: Any, received_at: float) -> None:
        with self._lock:
            value = self._safety.update_motor(message, received_at)
            self.update_motor_mode(value.public_control_mode, received_at)

    def update_fan_safety(self, message: Any, received_at: float) -> None:
        with self._lock:
            value = self._safety.update_fan(message, received_at)
            self._fans.update_control_state(value.control_state, received_at)
            if value.enabled_observed:
                self._fans.update_enabled(value.enabled, received_at)

    def update_motor_mode(self, mode: str, received_at: float) -> None:
        if not isinstance(mode, str) or not mode:
            raise ValueError("motor control mode must be a non-empty string")
        if not math.isfinite(received_at) or received_at < 0.0:
            raise ValueError("motor mode receive time must be finite and non-negative")
        with self._lock:
            self._motor_mode = mode
            self._motor_mode_received_at = received_at

    def update_e_stop(self, active: bool, received_at: float | None = None) -> None:
        if not isinstance(active, bool):
            raise ValueError("e-stop observation must be a bool")
        if received_at is None:
            received_at = 0.0
        if not math.isfinite(received_at) or received_at < 0.0:
            raise ValueError("e-stop receive time must be finite and non-negative")
        with self._lock:
            # /e_stop 是触发通道，不是“急停已解除”的权威回读。
            if active:
                self._e_stop_triggered_at = received_at

    def build_snapshot(self, now: float) -> FlightState:
        return self.build_runtime_snapshot(now).flight_state

    def build_runtime_snapshot(self, now: float) -> RuntimeSnapshot:
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
            motor_received = self._safety.motor
            fan_received = self._safety.fan
            motor_safety_fresh = (
                motor_received is not None
                and self._safety.fresh(
                    motor_received.received_at,
                    now,
                    self._config.flight_motor_safety_state_freshness_sec,
                )
            )
            fan_safety_fresh = (
                fan_received is not None
                and self._safety.fresh(
                    fan_received.received_at,
                    now,
                    self._config.flight_fan_safety_state_freshness_sec,
                )
            )
            motor_safety = None if motor_received is None else motor_received.value
            fan_safety = None if fan_received is None else fan_received.value
            e_stop_active = self._aggregate_e_stop(
                motor_safety=motor_safety,
                fan_safety=fan_safety,
                motor_received_at=(
                    None if motor_received is None else motor_received.received_at
                ),
                fan_received_at=(
                    None if fan_received is None else fan_received.received_at
                ),
                motor_fresh=motor_safety_fresh,
                fan_fresh=fan_safety_fresh,
            )
            sequence = self._sequence
            self._sequence += 1
            self._last_snapshot_time = now
            state = FlightState(
                timestamp_sec=now,
                sequence=sequence,
                imu=imu,
                motors=motors,
                fans=fans,
                system=SystemState(
                    command_authority=CommandAuthority.NONE,
                    authority_epoch=0,
                    authority_generation=0,
                    e_stop_active=e_stop_active,
                    motor_control_mode=motor_mode,
                    fan_control_state=fans.control_state,
                    flight_control_active=False,
                    actuation_allowed=False,
                    required_inputs_fresh=required_inputs_fresh,
                ),
            )
            return RuntimeSnapshot(
                flight_state=state,
                motor_safety=motor_safety,
                fan_safety=fan_safety,
                motor_safety_fresh=motor_safety_fresh,
                fan_safety_fresh=fan_safety_fresh,
            )

    def _aggregate_e_stop(
        self,
        *,
        motor_safety: MotorSafetyReadback | None,
        fan_safety: FanSafetyReadback | None,
        motor_received_at: float | None,
        fan_received_at: float | None,
        motor_fresh: bool,
        fan_fresh: bool,
    ) -> bool | None:
        if (
            motor_safety is not None
            and motor_safety.e_stop_latched
        ) or (fan_safety is not None and fan_safety.e_stop_latched):
            return True
        if self._e_stop_triggered_at is not None:
            if (
                motor_received_at is None
                or fan_received_at is None
                or motor_received_at <= self._e_stop_triggered_at
                or fan_received_at <= self._e_stop_triggered_at
            ):
                return True
        if (
            motor_safety is not None
            and fan_safety is not None
            and motor_fresh
            and fan_fresh
            and not motor_safety.e_stop_latched
            and not fan_safety.e_stop_latched
        ):
            return False
        return None
