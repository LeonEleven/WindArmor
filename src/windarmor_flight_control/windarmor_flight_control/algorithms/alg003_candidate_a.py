"""Hardware-free two-sample input moving average for ALG-003 Candidate A."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..core.models import FanCommand, FlightCommand, FlightState


DEFAULT_KP_INTENT_PER_RAD = 1.0
DEFAULT_KD_INTENT_PER_RAD_S = 0.1
DEFAULT_WINDOW_SIZE = 2
KP_CONFIGURATION_KEY = "kp_intent_per_rad"
KD_CONFIGURATION_KEY = "kd_intent_per_rad_s"
WINDOW_SIZE_CONFIGURATION_KEY = "window_size"


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class CandidateAConfiguration:
    """Fixed ALG-003 Candidate A software qualification configuration."""

    kp_intent_per_rad: float = DEFAULT_KP_INTENT_PER_RAD
    kd_intent_per_rad_s: float = DEFAULT_KD_INTENT_PER_RAD_S
    window_size: int = DEFAULT_WINDOW_SIZE

    def __post_init__(self) -> None:
        for name, value in (
            (KP_CONFIGURATION_KEY, self.kp_intent_per_rad),
            (KD_CONFIGURATION_KEY, self.kd_intent_per_rad_s),
        ):
            if not _finite_number(value) or float(value) <= 0.0:
                raise ValueError(f"{name} must be a positive finite number")
            object.__setattr__(self, name, float(value))
        if (
            isinstance(self.window_size, bool)
            or not isinstance(self.window_size, int)
            or self.window_size != DEFAULT_WINDOW_SIZE
        ):
            raise ValueError("window_size must be the integer 2")

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
        )


class Alg003CandidateACore:
    """Level A/D seam implementing a deterministic two-sample boxcar filter."""

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
        self.reset()

    @property
    def configuration(self) -> CandidateAConfiguration:
        """Return the frozen candidate configuration."""

        return self._configuration

    def reset(self) -> None:
        """Clear the previous valid raw input without external side effects."""

        self._previous_pitch: float | None = None
        self._previous_rate: float | None = None

    def update(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
        dt: float,
    ) -> float:
        """Filter inputs and return inherited pitch-plus-rate feedback intent.

        The fixed two-sample window stores the previous valid raw input. dt is
        validated but does not change the frame-based weights. Any invalid input
        clears history and raises ValueError.
        """

        for name, value in (
            ("relative_pitch_rad", relative_pitch_rad),
            ("relative_pitch_rate_rad_s", relative_pitch_rate_rad_s),
            ("dt", dt),
        ):
            if not _finite_number(value):
                self.reset()
                raise ValueError(f"{name} must be a finite number")
        if float(dt) <= 0.0:
            self.reset()
            raise ValueError("dt must be positive")

        pitch = float(relative_pitch_rad)
        rate = float(relative_pitch_rate_rad_s)
        if self._previous_pitch is None or self._previous_rate is None:
            filtered_pitch = pitch
            filtered_rate = rate
        else:
            filtered_pitch = (self._previous_pitch + pitch) / 2.0
            filtered_rate = (self._previous_rate + rate) / 2.0

        feedback = (
            -self._configuration.kp_intent_per_rad * filtered_pitch
            - self._configuration.kd_intent_per_rad_s * filtered_rate
        )
        if not math.isfinite(feedback):
            self.reset()
            raise ValueError("pitch_feedback_intent must be finite")

        self._previous_pitch = pitch
        self._previous_rate = rate
        return feedback


class Alg003CandidateAController:
    """Use Candidate A core and emit a non-allocating current-state preview."""

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
        self._core = Alg003CandidateACore(configuration)

    @property
    def configuration(self) -> CandidateAConfiguration:
        """Return the frozen candidate configuration used by the core."""

        return self._core.configuration

    def reset(self) -> None:
        """Clear all candidate-local input history."""

        self._core.reset()

    def pitch_feedback_intent(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
        dt: float,
    ) -> float:
        """Update intent through the same Level A core held by the controller."""

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
        """Return a current-position preview or clear history and fail close."""

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
        # previews current observed positions and stopped fans; it does not
        # encode the abstract feedback intent into an actuator direction.
        return FlightCommand(
            motor_positions_rad=positions,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg003CandidateAController:
    """Create the non-default Candidate A through the existing loader contract."""

    return Alg003CandidateAController(
        required_motor_names,
        CandidateAConfiguration.from_mapping(configuration),
    )
