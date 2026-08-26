"""面向新人算法开发的软件优先俯仰控制示例。"""

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
    """把相对俯仰角映射为一个受限电机偏移和两路风扇预览。

    该教学控制器不依赖 ROS 或硬件。重置后，它会捕获一次完整电机位置基线，
    并保持该基线不变，直到再次重置或不安全输入将其清除。代码中的常量只是软件
    示例值，不是机械调参值；加载本控制器不会授予执行器控制权。它不是默认生产控制器。
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
        """丢弃算法在先前运行中捕获的本地反馈。"""

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
        """返回完整预览帧；输入不可用时返回 safe-stop。"""

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
    """为测试和 DRY_RUN 创建非默认教学控制器。"""

    del configuration
    return ExampleAlgorithmController(required_motor_names)
