"""Hardware-free output shaping for ALG-004 Candidate A."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..core.models import FanCommand, FlightCommand, FlightState
from .alg003_candidate_a import (
    Alg003CandidateACore,
    CandidateAConfiguration as Alg003CandidateAConfiguration,
)


DEFAULT_KP_INTENT_PER_RAD = 1.0
DEFAULT_KD_INTENT_PER_RAD_S = 0.1
DEFAULT_WINDOW_SIZE = 2
DEFAULT_MAX_ABS_INTENT = 0.10
DEFAULT_MAX_SLEW_RATE = 2.0

KP_CONFIGURATION_KEY = "kp_intent_per_rad"
KD_CONFIGURATION_KEY = "kd_intent_per_rad_s"
WINDOW_SIZE_CONFIGURATION_KEY = "window_size"
MAX_ABS_INTENT_CONFIGURATION_KEY = "max_abs_intent"
MAX_SLEW_RATE_CONFIGURATION_KEY = "max_slew_rate"


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _require_frozen_number(name: str, value: object, expected: float) -> float:
    if not _finite_number(value) or float(value) != expected:
        raise ValueError(f"{name} must be the frozen value {expected}")
    return float(value)


@dataclass(frozen=True)
class CandidateAConfiguration:
    """Fixed ALG-004 Candidate A software qualification configuration."""

    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD
    kd_intent_per_rad_s: float = DEFAULT_KD_INTENT_PER_RAD_S
    window_size: int = DEFAULT_WINDOW_SIZE
    max_abs_intent: float = DEFAULT_MAX_ABS_INTENT
    max_slew_rate: float = DEFAULT_MAX_SLEW_RATE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            KP_CONFIGURATION_KEY,
            _require_frozen_number(
                KP_CONFIGURATION_KEY,
                self.kp_intent_per_rad,
                DEFAULT_KP_INTENT_PER_RAD,
            ),
        )
        object.__setattr__(
            self,
            KD_CONFIGURATION_KEY,
            _require_frozen_number(
                KD_CONFIGURATION_KEY,
                self.kd_intent_per_rad_s,
                DEFAULT_KD_INTENT_PER_RAD_S,
            ),
        )
        if (
            isinstance(self.window_size, bool)
            or not isinstance(self.window_size, int)
            or self.window_size != DEFAULT_WINDOW_SIZE
        ):
            raise ValueError("window_size must be the frozen integer 2")
        object.__setattr__(
            self,
            MAX_ABS_INTENT_CONFIGURATION_KEY,
            _require_frozen_number(
                MAX_ABS_INTENT_CONFIGURATION_KEY,
                self.max_abs_intent,
                DEFAULT_MAX_ABS_INTENT,
            ),
        )
        object.__setattr__(
            self,
            MAX_SLEW_RATE_CONFIGURATION_KEY,
            _require_frozen_number(
                MAX_SLEW_RATE_CONFIGURATION_KEY,
                self.max_slew_rate,
                DEFAULT_MAX_SLEW_RATE,
            ),
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
        allowed = {
            KP_CONFIGURATION_KEY,
            KD_CONFIGURATION_KEY,
            WINDOW_SIZE_CONFIGURATION_KEY,
            MAX_ABS_INTENT_CONFIGURATION_KEY,
            MAX_SLEW_RATE_CONFIGURATION_KEY,
        }
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
            window_size=configuration.get(
                WINDOW_SIZE_CONFIGURATION_KEY,
                DEFAULT_WINDOW_SIZE,
            ),
            max_abs_intent=configuration.get(
                MAX_ABS_INTENT_CONFIGURATION_KEY,
                DEFAULT_MAX_ABS_INTENT,
            ),
            max_slew_rate=configuration.get(
                MAX_SLEW_RATE_CONFIGURATION_KEY,
                DEFAULT_MAX_SLEW_RATE,
            ),
        )


class Alg004OutputShaper:
    """Level A output seam implementing clamp plus symmetric slew limiting."""

    def __init__(
        self,
        max_abs_intent: float = DEFAULT_MAX_ABS_INTENT,
        max_slew_rate: float = DEFAULT_MAX_SLEW_RATE,
    ) -> None:
        self._max_abs_intent = _require_frozen_number(
            MAX_ABS_INTENT_CONFIGURATION_KEY,
            max_abs_intent,
            DEFAULT_MAX_ABS_INTENT,
        )
        self._max_slew_rate = _require_frozen_number(
            MAX_SLEW_RATE_CONFIGURATION_KEY,
            max_slew_rate,
            DEFAULT_MAX_SLEW_RATE,
        )
        self.reset()

    @property
    def previous_shaped_intent(self) -> float:
        """Return the current task-local output history for verification."""

        return self._previous_shaped_intent

    def reset(self) -> None:
        """Clear output history without external side effects."""

        self._previous_shaped_intent = 0.0

    def update(self, requested_intent: float, dt: float) -> float:
        """Clamp and move toward the target by at most max_slew_rate times dt."""

        if not _finite_number(requested_intent):
            self.reset()
            raise ValueError("requested_intent must be a finite number")
        if not _finite_number(dt) or float(dt) <= 0.0:
            self.reset()
            raise ValueError("dt must be a positive finite number")

        request = float(requested_intent)
        period = float(dt)
        target = max(-self._max_abs_intent, min(self._max_abs_intent, request))
        max_delta = self._max_slew_rate * period
        delta = target - self._previous_shaped_intent
        if abs(delta) <= max_delta:
            shaped_intent = target
        else:
            shaped_intent = (
                self._previous_shaped_intent
                + math.copysign(max_delta, delta)
            )
        if not math.isfinite(shaped_intent):
            self.reset()
            raise ValueError("shaped_intent must be finite")

        self._previous_shaped_intent = shaped_intent
        return shaped_intent


class Alg004CandidateACore:
    """Compose inherited ALG-003 intent with ALG-004 output shaping."""

    def __init__(
        self,
        configuration: CandidateAConfiguration | None = None,
    ) -> None:
        if configuration is not None and not isinstance(
            configuration,
            CandidateAConfiguration,
        ):
            raise ValueError("configuration must be a CandidateAConfiguration")
        self._configuration = configuration or CandidateAConfiguration()
        inherited_configuration = Alg003CandidateAConfiguration(
            kp_intent_per_rad=self._configuration.kp_intent_per_rad,
            kd_intent_per_rad_s=self._configuration.kd_intent_per_rad_s,
            window_size=self._configuration.window_size,
        )
        self._inherited_core = Alg003CandidateACore(inherited_configuration)
        self._output_shaper = Alg004OutputShaper(
            self._configuration.max_abs_intent,
            self._configuration.max_slew_rate,
        )

    @property
    def configuration(self) -> CandidateAConfiguration:
        """Return the frozen candidate configuration."""

        return self._configuration

    def reset(self) -> None:
        """Clear inherited input history and shaped-output history."""

        self._inherited_core.reset()
        self._output_shaper.reset()

    def update(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
        dt: float,
    ) -> float:
        """Return the final post-shaped abstract recovery intent atomically."""

        try:
            requested_intent = self._inherited_core.update(
                relative_pitch_rad,
                relative_pitch_rate_rad_s,
                dt,
            )
            if not math.isfinite(requested_intent):
                raise ValueError("requested_intent must be finite")
            return self._output_shaper.update(requested_intent, dt)
        except ValueError:
            self.reset()
            raise


class Alg004CandidateAController:
    """Use the composite core and emit a non-allocating current-state preview."""

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
        self._core = Alg004CandidateACore(configuration)

    @property
    def configuration(self) -> CandidateAConfiguration:
        """Return the frozen candidate configuration used by the core."""

        return self._core.configuration

    def reset(self) -> None:
        """Clear all candidate-local input and output history."""

        self._core.reset()

    def pitch_feedback_intent(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
        dt: float,
    ) -> float:
        """Return the final post-shaped intent from the shared composite core."""

        return self._core.update(
            relative_pitch_rad,
            relative_pitch_rate_rad_s,
            dt,
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

    def _fail_close(self) -> FlightCommand:
        self.reset()
        return FlightCommand.safe_stop()

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """Return a current-position preview or clear both histories and fail close."""

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
            return self._fail_close()

        positions = self._current_motor_positions(state)
        if positions is None:
            return self._fail_close()

        try:
            self.pitch_feedback_intent(float(pitch), float(pitch_rate), float(dt))
        except ValueError:
            return self._fail_close()

        # ALG-006 has not defined actuator allocation. This normal frame only
        # previews current observed positions and stopped fans.
        return FlightCommand(
            motor_positions_rad=positions,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg004CandidateAController:
    """Create the non-default Candidate A through the existing loader contract."""

    return Alg004CandidateAController(
        required_motor_names,
        CandidateAConfiguration.from_mapping(configuration),
    )
