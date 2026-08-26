"""只读风扇观测归一化，并将过期观测显式转为未知。"""

from __future__ import annotations

import math
from typing import Any

from ..core.models import FanChannelState, FanSystemState


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


class FanAdapter:
    """归一化已观测的实际 PWM，并把过期观测转为未知。

    结果是回读值，而不是请求的 ``FanCommand``；本适配器绝不发布 PWM、控制硬件
    或授予控制权。
    """

    def __init__(self, minimum_pwm_us: float, maximum_pwm_us: float) -> None:
        self._minimum = _finite(minimum_pwm_us, "fan PWM minimum")
        self._maximum = _finite(maximum_pwm_us, "fan PWM maximum")
        if self._minimum >= self._maximum:
            raise ValueError("fan PWM minimum must be less than maximum")
        self._output: tuple[float, float] | None = None
        self._output_received_at: float | None = None
        self._enabled: bool | None = None
        self._enabled_received_at: float | None = None
        self._control_state: str | None = None
        self._control_state_received_at: float | None = None

    def update_output(self, message: Any, received_at: float) -> None:
        received = _finite(received_at, "received_at")
        values = tuple(message.data)
        if len(values) != 2:
            self._output = None
            self._output_received_at = None
            raise ValueError("fan status must contain exactly two PWM values")
        converted = tuple(_finite(value, "fan PWM") for value in values)
        if any(value < self._minimum or value > self._maximum for value in converted):
            self._output = None
            self._output_received_at = None
            raise ValueError("fan status PWM is outside the observer range")
        scale = self._maximum - self._minimum
        self._output = tuple((value - self._minimum) / scale for value in converted)
        self._output_received_at = received

    def update_enabled(self, value: object, received_at: float) -> None:
        if not isinstance(value, bool):
            raise ValueError("fan enabled must be a bool")
        self._enabled = value
        self._enabled_received_at = _finite(received_at, "received_at")

    def update_control_state(self, value: object, received_at: float) -> None:
        if not isinstance(value, str) or not value:
            self._control_state = None
            self._control_state_received_at = None
            raise ValueError("fan control state must be a non-empty string")
        self._control_state = value
        self._control_state_received_at = _finite(received_at, "received_at")

    def snapshot(
        self,
        *,
        now: float,
        output_freshness_sec: float,
        state_freshness_sec: float,
    ) -> FanSystemState:
        current = _finite(now, "now")
        output_fresh = (
            self._output is not None
            and self._output_received_at is not None
            and current - self._output_received_at <= output_freshness_sec
        )
        enabled_fresh = (
            self._enabled_received_at is not None
            and current - self._enabled_received_at <= state_freshness_sec
        )
        state_fresh = (
            self._control_state_received_at is not None
            and current - self._control_state_received_at <= state_freshness_sec
        )
        output = self._output if output_fresh else None
        return FanSystemState(
            left=FanChannelState(
                applied_command=None if output is None else output[0],
                output_known=output is not None,
            ),
            right=FanChannelState(
                applied_command=None if output is None else output[1],
                output_known=output is not None,
            ),
            enabled=self._enabled if enabled_fresh else None,
            control_state=self._control_state if state_fresh else None,
        )
