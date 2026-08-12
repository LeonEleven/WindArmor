"""ROS-independent owner readback ordering and handoff coordination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ..core.authority import OwnershipDomain


OWNER_PHASES = frozenset(
    {
        "MANUAL",
        "LEGACY_MANUAL",
        "LEGACY_AUTO",
        "NONE",
        "FLIGHT_RESERVED",
        "FLIGHT_CONTROL",
    }
)
OWNER_DOMAIN_PHASES = {
    OwnershipDomain.MOTOR: frozenset(
        {"MANUAL", "LEGACY_AUTO", "NONE", "FLIGHT_RESERVED", "FLIGHT_CONTROL"}
    ),
    OwnershipDomain.FAN: frozenset(
        {
            "LEGACY_MANUAL",
            "LEGACY_AUTO",
            "NONE",
            "FLIGHT_RESERVED",
            "FLIGHT_CONTROL",
        }
    ),
}


@dataclass(frozen=True)
class OwnershipReadback:
    source_epoch: int
    observation_sequence: int
    owner: OwnershipDomain
    phase: str
    authority_epoch: int | None
    generation: int | None
    last_command_sequence: int | None
    last_valid_command_age_sec: float | None


class OwnershipReadbackTracker:
    def __init__(self, owner: OwnershipDomain) -> None:
        self.owner = owner
        self.latest: OwnershipReadback | None = None

    def update(self, message) -> OwnershipReadback:
        source_epoch = int(message.source_epoch)
        sequence = int(message.observation_sequence)
        if (
            source_epoch <= 0
            or source_epoch > 2**64 - 1
            or sequence <= 0
            or sequence > 2**64 - 1
        ):
            raise ValueError("ownership source epoch and sequence must be positive")
        if str(message.owner_domain) != self.owner.value:
            raise ValueError("ownership domain mismatch")
        phase = str(message.ownership_phase)
        if phase not in OWNER_PHASES or phase not in OWNER_DOMAIN_PHASES[self.owner]:
            raise ValueError("unknown ownership phase")
        present = bool(message.authority_present)
        epoch = int(message.authority_epoch)
        generation = int(message.generation)
        if present:
            if not (0 < epoch <= 2**64 - 1 and 0 < generation <= 2**64 - 1):
                raise ValueError("present authority token must be positive")
        elif epoch != 0 or generation != 0:
            raise ValueError("absent authority token must use zero placeholders")
        flight_phase = phase in {"FLIGHT_RESERVED", "FLIGHT_CONTROL"}
        if present != flight_phase:
            raise ValueError("ownership phase and authority presence disagree")
        last_present = bool(message.last_accepted_flight_command_present)
        last_sequence = int(message.last_accepted_flight_command_sequence)
        if last_sequence < 0 or last_sequence > 2**64 - 1:
            raise ValueError("ownership command sequence must be uint64")
        if not last_present and last_sequence != 0:
            raise ValueError("absent command sequence must use zero placeholder")
        age = float(message.last_valid_flight_command_age_sec)
        if not math.isfinite(age):
            raise ValueError("ownership command age must be finite")
        if (last_present and age < 0.0) or (not last_present and age != -1.0):
            raise ValueError("ownership command age presence contract is invalid")
        previous = self.latest
        if previous is not None:
            if source_epoch < previous.source_epoch:
                raise ValueError("older ownership source epoch")
            if source_epoch == previous.source_epoch and sequence <= previous.observation_sequence:
                raise ValueError("ownership observation sequence must increase")
        result = OwnershipReadback(
            source_epoch=source_epoch,
            observation_sequence=sequence,
            owner=self.owner,
            phase=phase,
            authority_epoch=epoch if present else None,
            generation=generation if present else None,
            last_command_sequence=last_sequence if last_present else None,
            last_valid_command_age_sec=age if last_present else None,
        )
        self.latest = result
        return result


@dataclass(frozen=True)
class OwnerReply:
    success: bool
    reason_code: str
    authority_epoch: int
    generation: int
    owner_observation_sequence: int


class HandoffState(str, Enum):
    IDLE = "IDLE"
    RESERVING = "RESERVING"
    COMMITTING = "COMMITTING"
    OWNERS_COMMITTED = "OWNERS_COMMITTED"
    FAILED = "FAILED"


class OwnerHandoffCoordinator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = HandoffState.IDLE
        self.authority_epoch: int | None = None
        self.generation: int | None = None
        self.runtime_state_sequence: int | None = None
        self.reserved: dict[OwnershipDomain, OwnerReply] = {}
        self.committed: dict[OwnershipDomain, OwnerReply] = {}
        self.failure_reason = ""

    def start(self, *, authority_epoch: int, generation: int, runtime_state_sequence: int) -> None:
        if self.state is not HandoffState.IDLE:
            raise RuntimeError("handoff is already in progress")
        if authority_epoch <= 0 or generation <= 0 or runtime_state_sequence < 0:
            raise ValueError("handoff token and state sequence are invalid")
        self.authority_epoch = authority_epoch
        self.generation = generation
        self.runtime_state_sequence = runtime_state_sequence
        self.state = HandoffState.RESERVING

    def record_reserve(self, owner: OwnershipDomain, reply: OwnerReply) -> bool:
        if self.state is not HandoffState.RESERVING or owner in self.reserved:
            return False
        if not self._reply_current(reply):
            self.fail("reserve_response_token_mismatch")
            return False
        if not reply.success:
            self.fail(f"{owner.value}_reserve:{reply.reason_code}")
            return False
        self.reserved[owner] = reply
        return True

    @property
    def reserves_complete(self) -> bool:
        return set(self.reserved) == set(OwnershipDomain)

    def begin_commit(self) -> None:
        if self.state is not HandoffState.RESERVING or not self.reserves_complete:
            raise RuntimeError("both owners must reserve before commit")
        self.state = HandoffState.COMMITTING

    def record_commit(self, owner: OwnershipDomain, reply: OwnerReply) -> bool:
        if self.state is not HandoffState.COMMITTING or owner in self.committed:
            return False
        if not self._reply_current(reply):
            self.fail("commit_response_token_mismatch")
            return False
        if not reply.success:
            self.fail(f"{owner.value}_commit:{reply.reason_code}")
            return False
        self.committed[owner] = reply
        if set(self.committed) == set(OwnershipDomain):
            self.state = HandoffState.OWNERS_COMMITTED
        return True

    def fail(self, reason: str) -> None:
        if not reason:
            raise ValueError("handoff failure reason must be non-empty")
        self.failure_reason = reason
        self.state = HandoffState.FAILED

    @property
    def revoke_domains(self) -> tuple[OwnershipDomain, ...]:
        return tuple(owner for owner in OwnershipDomain if owner in self.reserved)

    def _reply_current(self, reply: OwnerReply) -> bool:
        return (
            reply.authority_epoch == self.authority_epoch
            and reply.generation == self.generation
            and reply.owner_observation_sequence > 0
        )
