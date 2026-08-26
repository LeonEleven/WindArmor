"""用于分阶段硬件验证、相对反馈工作的失效后安全闭锁控制器。"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import MappingProxyType

from ..core.authority import CommandAuthority
from ..core.models import FanCommand, FlightCommand, FlightState


class BoundedVerificationController:
    """对每个控制权会话的基线应用一次不累积的偏移。

    该控制器需要显式启用，仅用于受限版本验证，并在异常时执行失效后安全闭锁。
    它会生成完整帧，但不是新人示例或生产算法模板。
    """

    def __init__(
        self,
        required_motor_names: Iterable[str],
        *,
        verification_controller_enabled: object = False,
        test_motor_name: object = "",
        motor_test_offset_rad: object | None = None,
        fan_left_test_command: object = 0.0,
        fan_right_test_command: object = 0.0,
    ) -> None:
        self._required_motor_names = tuple(required_motor_names)
        self._verification_controller_enabled = verification_controller_enabled
        self._test_motor_name = test_motor_name
        self._motor_test_offset_rad = motor_test_offset_rad
        self._fan_left_test_command = fan_left_test_command
        self._fan_right_test_command = fan_right_test_command
        self._configuration_valid = self._validate_configuration()
        self._baseline_positions_rad: Mapping[str, float] | None = None
        self._baseline_session: tuple[int, int] | None = None

    @staticmethod
    def _finite_number(value: object) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )

    def _validate_configuration(self) -> bool:
        names = self._required_motor_names
        if (
            not names
            or any(not isinstance(name, str) or not name for name in names)
            or len(set(names)) != len(names)
        ):
            return False
        if not isinstance(self._verification_controller_enabled, bool):
            return False
        if not isinstance(self._test_motor_name, str):
            return False
        if self._test_motor_name and self._test_motor_name not in names:
            return False
        if self._motor_test_offset_rad is not None and not self._finite_number(
            self._motor_test_offset_rad
        ):
            return False
        for command in (
            self._fan_left_test_command,
            self._fan_right_test_command,
        ):
            if not self._finite_number(command) or not 0.0 <= float(command) <= 1.0:
                return False
        if self._verification_controller_enabled and (
            not self._test_motor_name or self._motor_test_offset_rad is None
        ):
            return False
        return True

    def reset(self) -> None:
        """清除反馈基线和控制权会话标识。"""

        self._baseline_positions_rad = None
        self._baseline_session = None

    def _safe_stop(self) -> FlightCommand:
        self._baseline_positions_rad = None
        self._baseline_session = None
        return FlightCommand.safe_stop()

    def _active_session(self, state: FlightState) -> tuple[int, int] | None:
        system = state.system
        if (
            system.command_authority is not CommandAuthority.FLIGHT_CONTROL
            or not system.flight_control_active
            or not system.actuation_allowed
            or not system.required_inputs_fresh
            or system.e_stop_active is not False
            or system.authority_epoch <= 0
            or system.authority_generation <= 0
        ):
            return None
        return (system.authority_epoch, system.authority_generation)

    def _capture_positions(self, state: FlightState) -> dict[str, float] | None:
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
        return positions

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """从当前有效会话捕获基线并返回完整帧。"""

        if (
            not self._configuration_valid
            or not self._verification_controller_enabled
            or not self._finite_number(dt)
            or float(dt) <= 0.0
        ):
            return self._safe_stop()

        session = self._active_session(state)
        if session is None or not state.imu.valid or not state.imu.fresh:
            return self._safe_stop()

        positions = self._capture_positions(state)
        if positions is None:
            return self._safe_stop()

        if self._baseline_session is not None and self._baseline_session != session:
            self._baseline_positions_rad = None
            self._baseline_session = None
            return FlightCommand.safe_stop()

        if self._baseline_positions_rad is None:
            self._baseline_session = session
            self._baseline_positions_rad = MappingProxyType(positions)

        targets = dict(self._baseline_positions_rad)
        selected_target = (
            targets[self._test_motor_name] + float(self._motor_test_offset_rad)
        )
        if not math.isfinite(selected_target):
            return self._safe_stop()
        targets[self._test_motor_name] = selected_target
        return FlightCommand(
            motor_positions_rad=targets,
            fan_commands=FanCommand(
                left=float(self._fan_left_test_command),
                right=float(self._fan_right_test_command),
            ),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> BoundedVerificationController:
    """使用经 Runtime 校验的值创建验证控制器。"""

    values = dict(configuration or {})
    offset = (
        values.get("motor_test_offset_rad")
        if values.get("motor_test_offset_configured") is True
        else None
    )
    return BoundedVerificationController(
        required_motor_names,
        verification_controller_enabled=values.get(
            "verification_controller_enabled", False
        ),
        test_motor_name=values.get("test_motor_name", ""),
        motor_test_offset_rad=offset,
        fan_left_test_command=values.get("fan_left_test_command", 0.0),
        fan_right_test_command=values.get("fan_right_test_command", 0.0),
    )
