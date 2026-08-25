"""ROS-independent command-authority and arming state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandAuthority(str, Enum):
    """The sole ordinary command owner selected by the Runtime."""

    NONE = "NONE"
    MANUAL = "MANUAL"
    LEGACY_AUTO = "LEGACY_AUTO"
    FLIGHT_CONTROL = "FLIGHT_CONTROL"


@dataclass(frozen=True)
class AuthorityGrant:
    """Authority identity scoped to one Runtime process and one prepare attempt.

    ``generation`` is unique only inside ``authority_epoch``; the pair prevents a
    command from surviving restart/session boundaries. It grants no hardware access.
    """

    authority: CommandAuthority
    authority_epoch: int
    generation: int
    sequence: int


@dataclass(frozen=True)
class OwnerAcknowledgement:
    """Diagnostic owner acknowledgement; never an authority grant or cutoff."""

    owner: OwnershipDomain
    authority_epoch: int
    generation: int
    observed_state_sequence: int


@dataclass(frozen=True)
class AuthorityCommitResult:
    """One-shot result emitted by an explicit, atomic authority commit."""

    authority_epoch: int
    generation: int
    arming_cutoff_state_sequence: int
    controller_reset_required: bool = True
    discard_precommit_previews_required: bool = True


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
    """Bind owner acknowledgements to one epoch/generation before atomic commit.

    Cancel or inhibit invalidates the attempt token; returning to DRY_RUN requires
    an explicit reset and never restores an old owner or command automatically.
    """

    def __init__(self, *, authority_epoch: int, takeover_supported: bool) -> None:
        if not self._valid_uint64(authority_epoch):
            raise ValueError("authority_epoch must be a positive uint64")
        self._authority_epoch = authority_epoch
        self._takeover_supported = bool(takeover_supported)
        self._state = AuthorityState.DISABLED
        self._next_generation = 1
        self._attempt_generation: int | None = None
        self._acks: dict[OwnershipDomain, OwnerAcknowledgement] = {}
        self._ready_state_sequence: int | None = None
        self._arming_cutoff_state_sequence: int | None = None
        self._last_preflight_failure_reason = ""
        self._last_inhibit_reason = ""

    @property
    def state(self) -> AuthorityState:
        return self._state

    @property
    def takeover_supported(self) -> bool:
        return self._takeover_supported

    @property
    def authority_epoch(self) -> int:
        return self._authority_epoch

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
    def ready_state_sequence(self) -> int | None:
        return self._ready_state_sequence

    @property
    def owner_acknowledgements(self) -> tuple[OwnerAcknowledgement, ...]:
        return tuple(
            self._acks[owner]
            for owner in OwnershipDomain
            if owner in self._acks
        )

    @property
    def all_required_owners_acknowledged(self) -> bool:
        return set(self._acks) == {OwnershipDomain.MOTOR, OwnershipDomain.FAN}

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
        if not 0 < generation <= (2**64 - 1):
            self.inhibit("generation_invariant_failure")
            raise AuthorityTransitionError("authority generation must be positive")
        self._attempt_generation = generation
        self._acks.clear()
        self._ready_state_sequence = None
        self._arming_cutoff_state_sequence = None
        self._last_preflight_failure_reason = ""
        self._state = AuthorityState.ARMING
        return generation

    def observe_preflight(
        self,
        *,
        ready: bool,
        reason: str,
        current_runtime_state_sequence: int | None = None,
    ) -> None:
        if self._state is AuthorityState.ARMING:
            if ready:
                if not self._valid_state_sequence(current_runtime_state_sequence):
                    self.inhibit("ready_state_sequence_invariant_failure")
                    return
                self._last_preflight_failure_reason = ""
                self._ready_state_sequence = current_runtime_state_sequence
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
        authority_epoch: int,
        generation: int,
        *,
        owner_observed_state_sequence: int,
    ) -> bool:
        """Record one diagnostic owner ack without granting authority."""

        if not self._takeover_supported:
            return False
        if (
            self._state is not AuthorityState.READY_TO_TAKEOVER
            or self._attempt_generation is None
            or not self._valid_uint64(authority_epoch)
            or authority_epoch != self._authority_epoch
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 0 < generation <= (2**64 - 1)
            or generation != self._attempt_generation
            or not isinstance(owner, OwnershipDomain)
            or owner in self._acks
        ):
            return False
        if not self._valid_state_sequence(owner_observed_state_sequence):
            return False
        self._acks[owner] = OwnerAcknowledgement(
            owner=owner,
            authority_epoch=authority_epoch,
            generation=generation,
            observed_state_sequence=owner_observed_state_sequence,
        )
        return True

    def commit_active(
        self,
        *,
        authority_epoch: int,
        generation: int,
        current_runtime_state_sequence: int,
    ) -> AuthorityCommitResult:
        """Atomically grant authority at the Runtime's current state boundary."""

        if not self._takeover_supported:
            raise AuthorityTransitionError("authority takeover is not supported")
        if self._state is not AuthorityState.READY_TO_TAKEOVER:
            raise AuthorityTransitionError(
                f"commit is not allowed from {self._state.value}"
            )
        if (
            self._attempt_generation is None
            or not self._valid_uint64(authority_epoch)
            or authority_epoch != self._authority_epoch
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 0 < generation <= (2**64 - 1)
            or generation != self._attempt_generation
        ):
            raise AuthorityTransitionError("commit generation is not current")
        if not self.all_required_owners_acknowledged:
            raise AuthorityTransitionError("all required owners must acknowledge")
        if not self._valid_state_sequence(current_runtime_state_sequence):
            raise AuthorityTransitionError("commit state sequence is invalid")
        if (
            self._ready_state_sequence is None
            or current_runtime_state_sequence < self._ready_state_sequence
        ):
            raise AuthorityTransitionError(
                "commit state sequence precedes the ready barrier"
            )
        self._arming_cutoff_state_sequence = current_runtime_state_sequence
        self._state = AuthorityState.ACTIVE
        return AuthorityCommitResult(
            authority_epoch=authority_epoch,
            generation=generation,
            arming_cutoff_state_sequence=current_runtime_state_sequence,
        )

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
        self._ready_state_sequence = None
        self._arming_cutoff_state_sequence = None

    @staticmethod
    def _valid_state_sequence(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    @staticmethod
    def _valid_uint64(value: object) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 < value <= (2**64 - 1)
        )
