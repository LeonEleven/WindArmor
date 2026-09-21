"""Hardware-free normalized allocation for ALG-006 Candidate A.

The allocation observation is a task-local qualification seam.  It does not
project normalized requests into motor positions, fan PWM, thrust, or torque.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
import math

from ..core.models import FanCommand, FlightCommand, FlightState
from .alg004_candidate_a import _finite_number
from .alg005_candidate_a import (
    Alg005CandidateAController,
    Alg005CandidateACore,
    CandidateAConfiguration as Alg005Configuration,
    ProcessObservation,
    RecoveryPhase,
)


INHERITED_MAX_ABS_INTENT = 0.10
NOMINAL_MOTOR_AUTHORITY = 1.0
NOMINAL_LEFT_FAN_AUTHORITY = 1.0
NOMINAL_RIGHT_FAN_AUTHORITY = 1.0


@dataclass(frozen=True)
class CandidateAConfiguration(Alg005Configuration):
    """The unchanged thirteen-field ALG-005 frozen configuration."""


class AllocationStatus(str, Enum):
    NEUTRAL = "NEUTRAL"
    ALLOCATED = "ALLOCATED"
    SATURATED = "SATURATED"
    INFEASIBLE = "INFEASIBLE"
    FAIL_CLOSED = "FAIL_CLOSED"


class AllocationDisposition(str, Enum):
    """Distinguish ordinary results from timeout and other fail-close causes."""

    ORDINARY = "ORDINARY"
    TIMEOUT = "TIMEOUT"
    EXTERNAL_FAIL_CLOSED = "EXTERNAL_FAIL_CLOSED"
    INVALID_CONTRACT = "INVALID_CONTRACT"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"
    RESET = "RESET"


@dataclass(frozen=True)
class AllocationObservation:
    normalized_request: float = 0.0
    motor_pitch_group: float = 0.0
    left_fan: float = 0.0
    right_fan: float = 0.0
    residual: float = 0.0
    status: AllocationStatus = AllocationStatus.FAIL_CLOSED
    disposition: AllocationDisposition = AllocationDisposition.RESET
    timeout_latched: bool = False


def _fail_closed_observation(
    disposition: AllocationDisposition,
    *,
    timeout_latched: bool = False,
) -> AllocationObservation:
    return AllocationObservation(
        status=AllocationStatus.FAIL_CLOSED,
        disposition=disposition,
        timeout_latched=timeout_latched,
    )


def _valid_authority(value: object) -> bool:
    return _finite_number(value) and 0.0 <= float(value) <= 1.0


class NormalizedAllocator:
    """Stateless ``ALG006-NORMALIZED-ALLOCATION-v1`` qualification seam."""

    def allocate(
        self,
        process_observation: ProcessObservation,
        motor_authority: object,
        left_fan_authority: object,
        right_fan_authority: object,
        *,
        upstream_valid: bool = True,
    ) -> AllocationObservation:
        """Allocate a structured ALG-005 outcome without retaining history."""

        if not isinstance(process_observation, ProcessObservation):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )

        timeout_latched = process_observation.timeout_latched
        if not isinstance(timeout_latched, bool):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )

        phase = process_observation.phase
        if phase is RecoveryPhase.TIMED_OUT or timeout_latched:
            return _fail_closed_observation(
                AllocationDisposition.TIMEOUT,
                timeout_latched=timeout_latched,
            )

        if not isinstance(upstream_valid, bool):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )
        if not upstream_valid:
            return _fail_closed_observation(
                AllocationDisposition.EXTERNAL_FAIL_CLOSED,
            )
        if not isinstance(phase, RecoveryPhase):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )

        intent = process_observation.final_process_intent
        if (
            not _finite_number(intent)
            or float(intent) < -INHERITED_MAX_ABS_INTENT
            or float(intent) > INHERITED_MAX_ABS_INTENT
        ):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )

        authorities = (
            motor_authority,
            left_fan_authority,
            right_fan_authority,
        )
        if not all(_valid_authority(value) for value in authorities):
            return _fail_closed_observation(
                AllocationDisposition.INVALID_CONTRACT,
            )

        request = float(intent) / INHERITED_MAX_ABS_INTENT
        if request == 0.0:
            return AllocationObservation(
                status=AllocationStatus.NEUTRAL,
                disposition=AllocationDisposition.ORDINARY,
            )

        magnitude = abs(request)
        allocated = min(magnitude, *(float(value) for value in authorities))
        sign = 1.0 if request > 0.0 else -1.0
        motor = sign * allocated
        residual = request - motor
        if allocated == magnitude:
            status = AllocationStatus.ALLOCATED
        elif allocated == 0.0:
            status = AllocationStatus.INFEASIBLE
        else:
            status = AllocationStatus.SATURATED

        values = (request, motor, allocated, allocated, residual)
        if not all(math.isfinite(value) for value in values):
            return _fail_closed_observation(
                AllocationDisposition.INTERNAL_FAILURE,
            )
        return AllocationObservation(
            normalized_request=request,
            motor_pitch_group=motor,
            left_fan=allocated,
            right_fan=allocated,
            residual=residual,
            status=status,
            disposition=AllocationDisposition.ORDINARY,
        )


def allocate_normalized_request(
    process_observation: ProcessObservation,
    motor_authority: object,
    left_fan_authority: object,
    right_fan_authority: object,
    *,
    upstream_valid: bool = True,
) -> AllocationObservation:
    """Convenience entry point for the stateless normalized allocator."""

    return NormalizedAllocator().allocate(
        process_observation,
        motor_authority,
        left_fan_authority,
        right_fan_authority,
        upstream_valid=upstream_valid,
    )


class Alg006CandidateACore:
    """Compose the unchanged ALG-005 core with normalized allocation."""

    def __init__(
        self,
        configuration: CandidateAConfiguration | None = None,
        allocator: NormalizedAllocator | None = None,
    ) -> None:
        if configuration is not None and not isinstance(
            configuration,
            CandidateAConfiguration,
        ):
            raise ValueError("configuration must be a CandidateAConfiguration")
        if allocator is not None and not isinstance(allocator, NormalizedAllocator):
            raise ValueError("allocator must be a NormalizedAllocator")
        self._configuration = configuration or CandidateAConfiguration()
        self._process_core = Alg005CandidateACore(self._configuration)
        self._allocator = allocator or NormalizedAllocator()
        self._allocation_observation = AllocationObservation()

    @property
    def configuration(self) -> CandidateAConfiguration:
        return self._configuration

    @property
    def observation(self) -> ProcessObservation:
        """Preserve the existing ALG-005 process observation seam."""

        return self._process_core.observation

    @property
    def allocation_observation(self) -> AllocationObservation:
        return self._allocation_observation

    def reset(self) -> None:
        self._process_core.reset()
        self._allocation_observation = AllocationObservation()

    def external_fail_close(self) -> None:
        """Clear ordinary history while preserving an existing timeout latch."""

        self._process_core.external_fail_close()
        if self.observation.timeout_latched:
            self._allocation_observation = _fail_closed_observation(
                AllocationDisposition.TIMEOUT,
                timeout_latched=True,
            )
        else:
            self._allocation_observation = _fail_closed_observation(
                AllocationDisposition.EXTERNAL_FAIL_CLOSED,
            )

    def _internal_fail_close(self) -> None:
        self._process_core.external_fail_close()
        if self.observation.timeout_latched:
            self._allocation_observation = _fail_closed_observation(
                AllocationDisposition.TIMEOUT,
                timeout_latched=True,
            )
        else:
            self._allocation_observation = _fail_closed_observation(
                AllocationDisposition.INTERNAL_FAILURE,
            )

    def update(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
        dt: float,
        *,
        motor_authority: object = NOMINAL_MOTOR_AUTHORITY,
        left_fan_authority: object = NOMINAL_LEFT_FAN_AUTHORITY,
        right_fan_authority: object = NOMINAL_RIGHT_FAN_AUTHORITY,
    ) -> float:
        """Run the inherited final path and observe its normalized allocation."""

        try:
            intent = self._process_core.update(
                relative_pitch_rad,
                relative_pitch_rate_rad_s,
                dt,
            )
        except ValueError:
            self.external_fail_close()
            raise
        except Exception as exc:
            self._internal_fail_close()
            raise ValueError("inherited process computation failed") from exc

        try:
            allocation = self._allocator.allocate(
                self.observation,
                motor_authority,
                left_fan_authority,
                right_fan_authority,
            )
            if not isinstance(allocation, AllocationObservation):
                raise TypeError("allocator must return AllocationObservation")
        except Exception as exc:
            self._internal_fail_close()
            raise ValueError("normalized allocation failed") from exc

        self._allocation_observation = allocation
        if allocation.status is AllocationStatus.FAIL_CLOSED:
            if allocation.disposition is not AllocationDisposition.TIMEOUT:
                self._process_core.external_fail_close()
            return 0.0
        return intent


class Alg006CandidateAController(Alg005CandidateAController):
    """Observe nominal allocation while preserving hold/fan-zero Level B."""

    def __init__(
        self,
        required_motor_names: Iterable[str],
        configuration: CandidateAConfiguration | None = None,
    ) -> None:
        core = Alg006CandidateACore(configuration)
        super().__init__(required_motor_names)
        self._core = core

    @property
    def allocation_observation(self) -> AllocationObservation:
        return self._core.allocation_observation

    def _fail_close(self) -> FlightCommand:
        self._core.external_fail_close()
        return FlightCommand.safe_stop()

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """Return current-position hold, or exact safe-stop on any failure."""

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
            self._core.update(
                float(pitch),
                float(pitch_rate),
                float(dt),
                motor_authority=NOMINAL_MOTOR_AUTHORITY,
                left_fan_authority=NOMINAL_LEFT_FAN_AUTHORITY,
                right_fan_authority=NOMINAL_RIGHT_FAN_AUTHORITY,
            )
        except Exception:
            return FlightCommand.safe_stop()

        if self.allocation_observation.status is AllocationStatus.FAIL_CLOSED:
            return FlightCommand.safe_stop()

        return FlightCommand(
            motor_positions_rad=positions,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> Alg006CandidateAController:
    """Create the non-default Candidate through the module:factory loader."""

    return Alg006CandidateAController(
        required_motor_names,
        CandidateAConfiguration.from_mapping(configuration),
    )
