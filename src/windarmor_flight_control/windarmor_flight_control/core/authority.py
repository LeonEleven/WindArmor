"""ROS-independent command-authority and arming state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class CommandAuthority(str, Enum):
    """The sole ordinary command owner selected by a future runtime."""

    NONE = "NONE"
    MANUAL = "MANUAL"
    LEGACY_AUTO = "LEGACY_AUTO"
    FLIGHT_CONTROL = "FLIGHT_CONTROL"


@dataclass(frozen=True)
class AuthorityGrant:
    """Immutable authority token metadata; it does not grant hardware access."""

    authority: CommandAuthority
    generation: int
    sequence: int


class AuthorityState(str, Enum):
    DISABLED = "DISABLED"
    DRY_RUN = "DRY_RUN"
    ARMING = "ARMING"
    READY_TO_TAKEOVER = "READY_TO_TAKEOVER"
    ACTIVE = "ACTIVE"
    INHIBITED = "INHIBITED"


class OwnershipDomain(str, Enum):
    MOTOR = "motor"
    FAN = "fan"


class AuthorityTransitionError(RuntimeError):
    """Raised when a requested transition violates the authority contract."""


class AuthorityStateMachine:
    """Generation-safe preparation and fake-testable ownership handshake."""

    def __init__(self, *, takeover_supported: bool) -> None:
        self._takeover_supported = bool(takeover_supported)
        self._state = AuthorityState.DISABLED
        self._next_generation = 1
        self._attempt_generation: int | None = None
        self._acks: set[OwnershipDomain] = set()
        self._arming_cutoff_state_sequence: int | None = None
        self._controller_reset_for_generation: int | None = None
        self._last_preflight_failure_reason = ""
        self._last_inhibit_reason = ""

    @property
    def state(self) -> AuthorityState:
        return self._state

    @property
    def takeover_supported(self) -> bool:
        return self._takeover_supported

    @property
    def attempt_generation(self) -> int | None:
        return self._attempt_generation

    @property
    def authority(self) -> CommandAuthority:
        return (
            CommandAuthority.FLIGHT_CONTROL
            if self._state is AuthorityState.ACTIVE
            else CommandAuthority.NONE
        )

    @property
    def authority_generation(self) -> int:
        if self._state is AuthorityState.ACTIVE:
            assert self._attempt_generation is not None
            return self._attempt_generation
        return 0

    @property
    def arming_cutoff_state_sequence(self) -> int | None:
        return self._arming_cutoff_state_sequence

    @property
    def last_preflight_failure_reason(self) -> str:
        return self._last_preflight_failure_reason

    @property
    def last_inhibit_reason(self) -> str:
        return self._last_inhibit_reason

    def enable_dry_run(self) -> None:
        if self._state is not AuthorityState.DISABLED:
            raise AuthorityTransitionError("authority feature is already enabled")
        self._state = AuthorityState.DRY_RUN

    def prepare(self) -> int:
        if self._state in (AuthorityState.ARMING, AuthorityState.READY_TO_TAKEOVER):
            assert self._attempt_generation is not None
            return self._attempt_generation
        if self._state is not AuthorityState.DRY_RUN:
            raise AuthorityTransitionError(
                f"prepare is not allowed from {self._state.value}"
            )
        generation = self._next_generation
        self._next_generation += 1
        if generation <= 0:
            self.inhibit("generation_invariant_failure")
            raise AuthorityTransitionError("authority generation must be positive")
        self._attempt_generation = generation
        self._acks.clear()
        self._arming_cutoff_state_sequence = None
        self._controller_reset_for_generation = None
        self._last_preflight_failure_reason = ""
        self._state = AuthorityState.ARMING
        return generation

    def observe_preflight(self, *, ready: bool, reason: str) -> None:
        if self._state is AuthorityState.ARMING:
            if ready:
                self._last_preflight_failure_reason = ""
                self._state = AuthorityState.READY_TO_TAKEOVER
            else:
                self._last_preflight_failure_reason = reason
            return
        if self._state is AuthorityState.READY_TO_TAKEOVER and not ready:
            self.inhibit(reason or "preflight_lost")

    def cancel(self) -> None:
        if self._state is AuthorityState.DRY_RUN:
            return
        if self._state not in (
            AuthorityState.ARMING,
            AuthorityState.READY_TO_TAKEOVER,
        ):
            raise AuthorityTransitionError(
                f"cancel is not allowed from {self._state.value}"
            )
        self._invalidate_attempt()
        self._last_preflight_failure_reason = ""
        self._state = AuthorityState.DRY_RUN

    def acknowledge_owner(
        self,
        owner: OwnershipDomain,
        generation: int,
        *,
        state_sequence: int,
        reset_controller: Callable[[], None],
    ) -> bool:
        """Accept explicit owner acks; production Task 3 has no caller."""

        if not self._takeover_supported:
            return False
        if (
            self._state is not AuthorityState.READY_TO_TAKEOVER
            or self._attempt_generation is None
            or generation != self._attempt_generation
            or not isinstance(owner, OwnershipDomain)
        ):
            return False
        if isinstance(state_sequence, bool) or not isinstance(state_sequence, int):
            self.inhibit("state_sequence_invariant_failure")
            return False
        if state_sequence < 0:
            self.inhibit("state_sequence_invariant_failure")
            return False
        self._acks.add(owner)
        if self._acks != {OwnershipDomain.MOTOR, OwnershipDomain.FAN}:
            return False
        if self._controller_reset_for_generation == generation:
            return self._state is AuthorityState.ACTIVE
        try:
            reset_controller()
        except Exception:
            self.inhibit("controller_reset_failure")
            raise
        self._controller_reset_for_generation = generation
        self._arming_cutoff_state_sequence = state_sequence
        self._state = AuthorityState.ACTIVE
        return True

    def handle_active_safe_stop(self) -> None:
        if self._state is AuthorityState.ACTIVE:
            self.inhibit("controller_safe_stop")

    def handle_safety_loss(self, reason: str) -> None:
        if self._state in (
            AuthorityState.ARMING,
            AuthorityState.READY_TO_TAKEOVER,
            AuthorityState.ACTIVE,
        ):
            self.inhibit(reason)

    def inhibit(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("inhibit reason must be a non-empty string")
        self._last_inhibit_reason = reason
        self._invalidate_attempt()
        self._state = AuthorityState.INHIBITED

    def reset_inhibit(self) -> None:
        if self._state is not AuthorityState.INHIBITED:
            raise AuthorityTransitionError(
                f"reset-inhibit is not allowed from {self._state.value}"
            )
        self._invalidate_attempt()
        self._last_preflight_failure_reason = ""
        self._state = AuthorityState.DRY_RUN

    def _invalidate_attempt(self) -> None:
        self._attempt_generation = None
        self._acks.clear()
        self._arming_cutoff_state_sequence = None
        self._controller_reset_for_generation = None
