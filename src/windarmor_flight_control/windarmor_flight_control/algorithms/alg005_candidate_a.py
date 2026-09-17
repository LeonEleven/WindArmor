"""Hardware-free transparent recovery process for ALG-005 Candidate A.

Process observations are task-local seams, not extensions of the Flight API.
Ordinary intent is the inherited ALG-004 output; timeout is a stop sentinel.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from enum import Enum
import math

from ..core.models import FlightCommand, FlightState
from .alg004_candidate_a import (
    Alg004CandidateACore,
    Alg004CandidateAController,
    CandidateAConfiguration as Alg004Configuration,
    _finite_number,
    _require_frozen_number,
)


@dataclass(frozen=True)
class CandidateAConfiguration(Alg004Configuration):
    """Serializable frozen ALG-004 inheritance and ALG-005 Profile v1 values."""

    disturbance_pitch_rad: float = 0.040
    disturbance_pitch_rate_rad_s: float = 0.200
    settling_pitch_rad: float = 0.020
    settling_pitch_rate_rad_s: float = 0.100
    stable_pitch_rad: float = 0.010
    stable_pitch_rate_rad_s: float = 0.050
    stable_dwell_sec: float = 0.300
    recovery_timeout_sec: float = 3.000

    def __post_init__(self) -> None:
        super().__post_init__()
        for field in fields(self):
            if field.name not in Alg004Configuration.__dataclass_fields__:
                object.__setattr__(self, field.name, _require_frozen_number(
                    field.name, getattr(self, field.name), field.default,
                ))

    @classmethod
    def from_mapping(
        cls, configuration: Mapping[str, object] | None,
    ) -> CandidateAConfiguration:
        if configuration is None:
            return cls()
        if not isinstance(configuration, Mapping):
            raise ValueError("Candidate A configuration must be a mapping")
        unknown = set(configuration) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"unknown Candidate A configuration keys: {unknown}")
        return cls(**configuration)


class RecoveryPhase(str, Enum):
    STABLE = "STABLE"
    DISTURBED = "DISTURBED"
    RECOVERING = "RECOVERING"
    SETTLING = "SETTLING"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True)
class ProcessObservation:
    final_process_intent: float = 0.0
    phase: RecoveryPhase = RecoveryPhase.STABLE
    episode_elapsed_sec: float = 0.0
    stable_dwell_sec: float = 0.0
    timeout_latched: bool = False
    episode_active: bool = False
    first_settling_entry_elapsed_sec: float | None = None
    phase_entry_elapsed_sec: float = 0.0


class _ValidTime:
    """Compensated interval sum without tolerance-based early transitions."""

    def __init__(self) -> None:
        self.total = 0.0
        self.correction = 0.0

    def add(self, dt: float) -> None:
        new_total = self.total + dt
        if abs(self.total) >= abs(dt):
            self.correction += (self.total - new_total) + dt
        else:
            self.correction += (dt - new_total) + self.total
        self.total = new_total

    @property
    def value(self) -> float:
        return self.total + self.correction


class Alg005CandidateACore:
    """Compose the unchanged ALG-004 core with recovery episode accounting."""

    def __init__(self, configuration: CandidateAConfiguration | None = None):
        if configuration is not None and not isinstance(
            configuration, CandidateAConfiguration,
        ):
            raise ValueError("configuration must be a CandidateAConfiguration")
        self._configuration = configuration or CandidateAConfiguration()
        inherited = {key: value for key, value in asdict(self._configuration).items()
                     if key in Alg004Configuration.__dataclass_fields__}
        self._inherited_core = Alg004CandidateACore(Alg004Configuration(**inherited))
        self.reset()

    @property
    def configuration(self) -> CandidateAConfiguration:
        return self._configuration

    @property
    def observation(self) -> ProcessObservation:
        return self._observation

    def reset(self) -> None:
        """Clear all task-local history, including the timeout latch."""
        self._inherited_core.reset()
        self._elapsed = _ValidTime()
        self._dwell = _ValidTime()
        self._observation = ProcessObservation()

    def external_fail_close(self) -> None:
        """Clear ordinary history; only explicit reset can clear timeout."""
        if self.observation.timeout_latched:
            self._inherited_core.reset()
            # Freeze the timeout observation: illegal inputs add no intervals.
        else:
            self.reset()

    def update(self, relative_pitch_rad: float,
               relative_pitch_rate_rad_s: float, dt: float) -> float:
        for name, value in (("pitch", relative_pitch_rad),
                            ("pitch_rate", relative_pitch_rate_rad_s), ("dt", dt)):
            if not _finite_number(value) or (name == "dt" and float(value) <= 0):
                self.external_fail_close()
                raise ValueError(f"{name} must be a valid finite number")
        if self.observation.timeout_latched:
            return 0.0
        try:
            intent = self._inherited_core.update(
                relative_pitch_rad, relative_pitch_rate_rad_s, dt,
            )
        except ValueError:
            self.external_fail_close()
            raise

        pitch, rate, period = (abs(float(relative_pitch_rad)),
                               abs(float(relative_pitch_rate_rad_s)), float(dt))
        config, previous = self.configuration, self.observation
        disturbance = (pitch >= config.disturbance_pitch_rad
                       or rate >= config.disturbance_pitch_rate_rad_s)
        entering = not previous.episode_active and disturbance
        active = previous.episode_active or entering
        if not active:
            self._elapsed = _ValidTime()
            self._dwell = _ValidTime()
            self._observation = ProcessObservation(final_process_intent=intent)
            return intent
        if entering:
            self._elapsed = _ValidTime()
            self._dwell = _ValidTime()
        self._elapsed.add(period)
        stable = (pitch <= config.stable_pitch_rad
                  and rate <= config.stable_pitch_rate_rad_s)
        if stable:
            self._dwell.add(period)
        else:
            self._dwell = _ValidTime()
        elapsed, dwell = self._elapsed.value, self._dwell.value
        if not math.isfinite(elapsed) or not math.isfinite(dwell):
            self.external_fail_close()
            raise ValueError("process timers must be finite")
        timed_out = elapsed >= config.recovery_timeout_sec
        if timed_out:
            phase, intent = RecoveryPhase.TIMED_OUT, 0.0
            self._inherited_core.reset()
        elif entering:
            phase = RecoveryPhase.DISTURBED
        elif dwell >= config.stable_dwell_sec:
            phase, active = RecoveryPhase.STABLE, False
        elif (pitch <= config.settling_pitch_rad
              and rate <= config.settling_pitch_rate_rad_s):
            phase = RecoveryPhase.SETTLING
        else:
            phase = RecoveryPhase.RECOVERING
        first_settling = None if entering else previous.first_settling_entry_elapsed_sec
        if phase == RecoveryPhase.SETTLING and first_settling is None:
            first_settling = elapsed
        entry_elapsed = (elapsed if entering or phase != previous.phase
                         else previous.phase_entry_elapsed_sec)
        self._observation = ProcessObservation(
            intent, phase, elapsed, dwell, timed_out, active,
            first_settling, entry_elapsed,
        )
        return intent


class Alg005CandidateAController(Alg004CandidateAController):
    """Reuse inherited input checks and current-position hold command semantics."""

    def __init__(self, required_motor_names: Iterable[str],
                 configuration: CandidateAConfiguration | None = None):
        core = Alg005CandidateACore(configuration)
        super().__init__(required_motor_names)
        self._core = core

    @property
    def observation(self) -> ProcessObservation:
        return self._core.observation

    def _fail_close(self) -> FlightCommand:
        self._core.external_fail_close()
        return FlightCommand.safe_stop()

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        command = super().update(state, dt)
        if self.observation.timeout_latched:
            return FlightCommand.safe_stop()
        return command


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg005CandidateAController:
    """Create the non-default Candidate via the existing module:factory loader."""
    return Alg005CandidateAController(
        required_motor_names, CandidateAConfiguration.from_mapping(configuration),
    )
