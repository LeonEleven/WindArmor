"""ALG-002 Candidate A 的无硬件运动趋势与阻尼实现。"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..core.models import FanCommand, FlightCommand, FlightState


TARGET_PITCH_RAD = 0.0
DEFAULT_KP_INTENT_PER_RAD = 1.0
DEFAULT_KD_INTENT_PER_RAD_S = 0.1
KP_CONFIGURATION_KEY = "kp_intent_per_rad"
KD_CONFIGURATION_KEY = "kd_intent_per_rad_s"


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class CandidateAConfiguration:
    """固定的软件 qualification 增益，单位分别为 intent/rad 和 intent/(rad/s)。"""

    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD
    kd_intent_per_rad_s: float = DEFAULT_KD_INTENT_PER_RAD_S

    def __post_init__(self) -> None:
        for name, value in (
            (KP_CONFIGURATION_KEY, self.kp_intent_per_rad),
            (KD_CONFIGURATION_KEY, self.kd_intent_per_rad_s),
        ):
            if not _finite_number(value) or float(value) <= 0.0:
                raise ValueError(f"{name} must be a positive finite number")
            object.__setattr__(self, name, float(value))

    @classmethod
    def from_mapping(
        cls,
        configuration: Mapping[str, object] | None,
    ) -> "CandidateAConfiguration":
        if configuration is None:
            return cls()
        if not isinstance(configuration, Mapping):
            raise ValueError("Candidate A configuration must be a mapping")
        allowed = {KP_CONFIGURATION_KEY, KD_CONFIGURATION_KEY}
        unknown = set(configuration) - allowed
        if unknown:
            names = ", ".join(sorted(map(str, unknown)))
            raise ValueError(f"unknown Candidate A configuration keys: {names}")
        return cls(
            kp_intent_per_rad=configuration.get(
                KP_CONFIGURATION_KEY,
                DEFAULT_KP_INTENT_PER_RAD,
            ),
            kd_intent_per_rad_s=configuration.get(
                KD_CONFIGURATION_KEY,
                DEFAULT_KD_INTENT_PER_RAD_S,
            ),
        )


def compute_pitch_feedback_intent(
    relative_pitch_rad: float,
    relative_pitch_rate_rad_s: float,
    *,
    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD,
    kd_intent_per_rad_s: float = DEFAULT_KD_INTENT_PER_RAD_S,
) -> float:
    """计算 ``Kp * pitch_error - Kd * relative_pitch_rate``。

    ``Kp`` 的单位为 intent/rad，``Kd`` 的单位为 intent/(rad/s)。该纯函数只
    消费统一后的相对 pitch 与 pitch rate，不包含时序、执行器分配或硬件语义。
    """

    for name, value in (
        ("relative_pitch_rad", relative_pitch_rad),
        ("relative_pitch_rate_rad_s", relative_pitch_rate_rad_s),
    ):
        if not _finite_number(value):
            raise ValueError(f"{name} must be a finite number")
    for name, value in (
        (KP_CONFIGURATION_KEY, kp_intent_per_rad),
        (KD_CONFIGURATION_KEY, kd_intent_per_rad_s),
    ):
        if not _finite_number(value) or float(value) <= 0.0:
            raise ValueError(f"{name} must be a positive finite number")

    pitch_error_rad = TARGET_PITCH_RAD - float(relative_pitch_rad)
    feedback = (
        float(kp_intent_per_rad) * pitch_error_rad
        - float(kd_intent_per_rad_s) * float(relative_pitch_rate_rad_s)
    )
    if not math.isfinite(feedback):
        raise ValueError("pitch_feedback_intent must be finite")
    return feedback


class Alg002CandidateAController:
    """提供 ALG-002 intent，并生成无分配含义的当前状态 hold 预览。"""

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

    def pitch_feedback_intent(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
    ) -> float:
        """通过固定配置调用 Level A 纯函数 seam。"""

        return compute_pitch_feedback_intent(
            relative_pitch_rad,
            relative_pitch_rate_rad_s,
            kp_intent_per_rad=self._configuration.kp_intent_per_rad,
            kd_intent_per_rad_s=self._configuration.kd_intent_per_rad_s,
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
        pitch_rate = state.imu.relative_pitch_rate_rad_s
        if (
            not _finite_number(dt)
            or float(dt) <= 0.0
            or state.system.e_stop_active is not False
            or not state.system.required_inputs_fresh
            or not state.imu.valid
            or not state.imu.fresh
            or not _finite_number(pitch)
            or not _finite_number(pitch_rate)
        ):
            return FlightCommand.safe_stop()

        positions = self._current_motor_positions(state)
        if positions is None:
            return FlightCommand.safe_stop()

        try:
            self.pitch_feedback_intent(float(pitch), float(pitch_rate))
        except ValueError:
            return FlightCommand.safe_stop()

        # ALG-006 尚未定义执行器分配。普通帧只预览当前观测位置与停止风扇，
        # 不把抽象 feedback intent 编码为任何电机或风扇方向。
        return FlightCommand(
            motor_positions_rad=positions,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg002CandidateAController:
    """通过现有 loader contract 创建非默认 Candidate A。"""

    return Alg002CandidateAController(
        required_motor_names,
        CandidateAConfiguration.from_mapping(configuration),
    )
