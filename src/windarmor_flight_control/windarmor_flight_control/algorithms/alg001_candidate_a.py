"""ALG-001 Candidate A 的无硬件基础姿态反馈实现。"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..core.models import FanCommand, FlightCommand, FlightState


TARGET_PITCH_RAD = 0.0
DEFAULT_KP_INTENT_PER_RAD = 1.0
CONFIGURATION_KEY = "kp_intent_per_rad"


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class CandidateAConfiguration:
    """一个控制器实例内固定且可追溯的 Candidate A 配置。"""

    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD

    def __post_init__(self) -> None:
        if (
            not _finite_number(self.kp_intent_per_rad)
            or float(self.kp_intent_per_rad) <= 0.0
        ):
            raise ValueError("kp_intent_per_rad must be a positive finite number")
        object.__setattr__(
            self,
            "kp_intent_per_rad",
            float(self.kp_intent_per_rad),
        )

    @classmethod
    def from_mapping(
        cls,
        configuration: Mapping[str, object] | None,
    ) -> "CandidateAConfiguration":
        if configuration is None:
            return cls()
        if not isinstance(configuration, Mapping):
            raise ValueError("Candidate A configuration must be a mapping")
        unknown = set(configuration) - {CONFIGURATION_KEY}
        if unknown:
            names = ", ".join(sorted(map(str, unknown)))
            raise ValueError(f"unknown Candidate A configuration keys: {names}")
        return cls(
            kp_intent_per_rad=configuration.get(
                CONFIGURATION_KEY,
                DEFAULT_KP_INTENT_PER_RAD,
            )
        )


def compute_pitch_feedback_intent(
    relative_pitch_rad: float,
    *,
    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD,
) -> float:
    """计算 ``Kp * (target_pitch - relative_pitch)`` 的软件反馈意图。

    该纯函数不包含执行器方向、分配、时序或硬件语义。
    """

    if not _finite_number(relative_pitch_rad):
        raise ValueError("relative_pitch_rad must be a finite number")
    if not _finite_number(kp_intent_per_rad) or float(kp_intent_per_rad) <= 0.0:
        raise ValueError("kp_intent_per_rad must be a positive finite number")
    pitch_error_rad = TARGET_PITCH_RAD - float(relative_pitch_rad)
    feedback = float(kp_intent_per_rad) * pitch_error_rad
    if not math.isfinite(feedback):
        raise ValueError("pitch_feedback_intent must be finite")
    return feedback


class Alg001CandidateAController:
    """提供 ALG-001 intent，并生成无分配含义的当前状态 hold 预览。"""

    def __init__(
        self,
        required_motor_names: Iterable[str],
        configuration: CandidateAConfiguration | None = None,
    ) -> None:
        names = tuple(required_motor_names)
        if (
            not names
            or any(not isinstance(name, str) or not name for name in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("Candidate A requires unique non-empty motor names")
        if configuration is not None and not isinstance(
            configuration,
            CandidateAConfiguration,
        ):
            raise ValueError("configuration must be a CandidateAConfiguration")
        self._required_motor_names = names
        self._configuration = configuration or CandidateAConfiguration()

    @property
    def configuration(self) -> CandidateAConfiguration:
        """返回本实例的冻结 candidate 配置。"""

        return self._configuration

    def reset(self) -> None:
        """Candidate A 无历史状态；重置不改变 Runtime 或硬件状态。"""

    def pitch_feedback_intent(self, relative_pitch_rad: float) -> float:
        """通过本实例的固定配置调用 Level A 纯函数 seam。"""

        return compute_pitch_feedback_intent(
            relative_pitch_rad,
            kp_intent_per_rad=self._configuration.kp_intent_per_rad,
        )

    def _current_motor_positions(
        self,
        state: FlightState,
    ) -> dict[str, float] | None:
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
                or not _finite_number(motor.position_rad)
            ):
                return None
            positions[name] = float(motor.position_rad)
        return positions

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """返回当前位置 hold 预览；任何不安全输入都 fail-close。"""

        pitch = state.imu.relative_pitch_rad
        if (
            not _finite_number(dt)
            or float(dt) <= 0.0
            or state.system.e_stop_active is not False
            or not state.system.required_inputs_fresh
            or not state.imu.valid
            or not state.imu.fresh
            or not _finite_number(pitch)
        ):
            return FlightCommand.safe_stop()

        positions = self._current_motor_positions(state)
        if positions is None:
            return FlightCommand.safe_stop()

        try:
            self.pitch_feedback_intent(float(pitch))
        except ValueError:
            return FlightCommand.safe_stop()

        # ALG-001 尚未定义执行器分配。普通帧只预览当前观测位置与停止风扇，
        # 不把抽象 feedback intent 编码为任何电机或风扇方向。
        return FlightCommand(
            motor_positions_rad=positions,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg001CandidateAController:
    """通过现有 loader contract 创建非默认 Candidate A。"""

    return Alg001CandidateAController(
        required_motor_names,
        CandidateAConfiguration.from_mapping(configuration),
    )
