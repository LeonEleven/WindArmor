"""风扇子系统的普通命令纯 ownership 契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class FanCommandOwner(str, Enum):
    LEGACY_MANUAL = "LEGACY_MANUAL"
    LEGACY_AUTO = "LEGACY_AUTO"
    NONE = "NONE"
    FLIGHT_RESERVED = "FLIGHT_RESERVED"
    FLIGHT_CONTROL = "FLIGHT_CONTROL"


class FlightLeasePhase(str, Enum):
    NONE = "NONE"
    HANDOFF = "HANDOFF"
    ACTIVE_COMMAND = "ACTIVE_COMMAND"


@dataclass(frozen=True)
class OwnershipResult:
    success: bool
    reason_code: str
    authority_epoch: int
    generation: int


class FanOwnershipCore:
    def __init__(
        self, *, handoff_timeout_sec: float, command_timeout_sec: float
    ) -> None:
        if not math.isfinite(handoff_timeout_sec) or handoff_timeout_sec <= 0.0:
            raise ValueError("fan_flight_handoff_timeout_sec must be positive")
        if not math.isfinite(command_timeout_sec) or command_timeout_sec <= 0.0:
            raise ValueError("fan_flight_command_timeout_sec must be positive")
        self.handoff_timeout_sec = float(handoff_timeout_sec)
        self.command_timeout_sec = float(command_timeout_sec)
        self.owner = FanCommandOwner.NONE
        self.authority_epoch: int | None = None
        self.generation: int | None = None
        self.last_command_sequence: int | None = None
        self.last_valid_command_at: float | None = None
        self._handoff_deadline: float | None = None
        self._command_deadline: float | None = None
        self._highest_epoch = 0
        self._highest_generation = 0

    @staticmethod
    def _valid_token(epoch: object, generation: object) -> bool:
        return (
            isinstance(epoch, int)
            and not isinstance(epoch, bool)
            and 0 < epoch <= (2**64 - 1)
            and isinstance(generation, int)
            and not isinstance(generation, bool)
            and 0 < generation <= (2**64 - 1)
        )

    @staticmethod
    def _valid_time(now: object) -> bool:
        return (
            isinstance(now, (int, float))
            and not isinstance(now, bool)
            and math.isfinite(float(now))
        )

    def prepare(self, epoch: int, generation: int, *, now: float, safe: bool) -> OwnershipResult:
        if not self._valid_token(epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(False, "invalid_monotonic_time", epoch, generation)
        requested = (epoch, generation)
        current = (self.authority_epoch, self.generation)
        if self.owner is FanCommandOwner.FLIGHT_RESERVED and current == requested:
            return OwnershipResult(True, "already_reserved", epoch, generation)
        if self.owner in (FanCommandOwner.FLIGHT_RESERVED, FanCommandOwner.FLIGHT_CONTROL):
            return OwnershipResult(False, "flight_owner_busy", epoch, generation)
        if epoch < self._highest_epoch:
            return OwnershipResult(False, "older_authority_epoch", epoch, generation)
        if epoch == self._highest_epoch and generation <= self._highest_generation:
            return OwnershipResult(False, "old_generation", epoch, generation)
        if not safe:
            return OwnershipResult(False, "owner_not_safe", epoch, generation)
        self._highest_epoch = epoch
        self._highest_generation = generation
        self.owner = FanCommandOwner.FLIGHT_RESERVED
        self.authority_epoch = epoch
        self.generation = generation
        self.last_command_sequence = None
        self.last_valid_command_at = None
        self._handoff_deadline = float(now) + self.handoff_timeout_sec
        self._command_deadline = None
        return OwnershipResult(True, "reserved", epoch, generation)

    def commit(self, epoch: int, generation: int, *, now: float, safe: bool) -> OwnershipResult:
        if not self._valid_token(epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(False, "invalid_monotonic_time", epoch, generation)
        matches = (self.authority_epoch, self.generation) == (epoch, generation)
        if self.owner is FanCommandOwner.FLIGHT_CONTROL and matches:
            return OwnershipResult(True, "already_committed", epoch, generation)
        if self.owner is not FanCommandOwner.FLIGHT_RESERVED or not matches:
            return OwnershipResult(False, "reserve_token_mismatch", epoch, generation)
        if not safe:
            return OwnershipResult(False, "owner_not_safe", epoch, generation)
        self.owner = FanCommandOwner.FLIGHT_CONTROL
        return OwnershipResult(True, "committed", epoch, generation)

    def revoke(self, epoch: int, generation: int) -> OwnershipResult:
        if not self._valid_token(epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if (self.authority_epoch, self.generation) != (epoch, generation):
            if (
                self.authority_epoch is None
                and epoch == self._highest_epoch
                and generation == self._highest_generation
            ):
                return OwnershipResult(True, "already_revoked", epoch, generation)
            return OwnershipResult(False, "authority_token_mismatch", epoch, generation)
        self.release_to_none()
        return OwnershipResult(True, "revoked", epoch, generation)

    def accept_command(
        self, epoch: int, generation: int, sequence: int, *, now: float
    ) -> OwnershipResult:
        result = self._validate_command(epoch, generation, sequence, now=now)
        if result is not None:
            return result
        self.last_command_sequence = sequence
        self.last_valid_command_at = float(now)
        self._handoff_deadline = None
        self._command_deadline = float(now) + self.command_timeout_sec
        return OwnershipResult(True, "command_accepted", epoch, generation)

    def accept_safe_stop(
        self, epoch: int, generation: int, sequence: int, *, now: float
    ) -> OwnershipResult:
        """校验 safe-stop 顺序，但不把它当作 heartbeat。"""

        result = self._validate_command(epoch, generation, sequence, now=now)
        if result is not None:
            return result
        return OwnershipResult(True, "safe_stop_accepted", epoch, generation)

    def timed_out(self, now: float) -> bool:
        if self.owner not in (FanCommandOwner.FLIGHT_RESERVED, FanCommandOwner.FLIGHT_CONTROL):
            return False
        deadline = (
            self._handoff_deadline
            if self.last_command_sequence is None
            else self._command_deadline
        )
        if not self._valid_time(now) or deadline is None or float(now) > deadline:
            self.release_to_none()
            return True
        return False

    def release_to_none(self) -> None:
        self.owner = FanCommandOwner.NONE
        self.authority_epoch = None
        self.generation = None
        self.last_command_sequence = None
        self.last_valid_command_at = None
        self._handoff_deadline = None
        self._command_deadline = None

    @property
    def lease_phase(self) -> FlightLeasePhase:
        if self._handoff_deadline is not None:
            return FlightLeasePhase.HANDOFF
        if self._command_deadline is not None:
            return FlightLeasePhase.ACTIVE_COMMAND
        return FlightLeasePhase.NONE

    def _validate_command(
        self, epoch: int, generation: int, sequence: int, *, now: float
    ) -> OwnershipResult | None:
        if not self._valid_token(epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(
                False, "invalid_monotonic_time", epoch, generation
            )
        if self.owner is not FanCommandOwner.FLIGHT_CONTROL:
            return OwnershipResult(False, "not_flight_control", epoch, generation)
        if (self.authority_epoch, self.generation) != (epoch, generation):
            return OwnershipResult(
                False, "authority_token_mismatch", epoch, generation
            )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or (
                self.last_command_sequence is not None
                and sequence <= self.last_command_sequence
            )
        ):
            return OwnershipResult(
                False, "stale_command_sequence", epoch, generation
            )
        return None

    def claim_legacy_manual(self) -> bool:
        if self.owner in (FanCommandOwner.FLIGHT_RESERVED, FanCommandOwner.FLIGHT_CONTROL):
            return False
        self.owner = FanCommandOwner.LEGACY_MANUAL
        return True

    def claim_legacy_auto(self) -> bool:
        if self.owner in (FanCommandOwner.FLIGHT_RESERVED, FanCommandOwner.FLIGHT_CONTROL):
            return False
        self.owner = FanCommandOwner.LEGACY_AUTO
        return True

    def last_valid_command_age(self, now: float) -> float:
        if self.last_valid_command_at is None or not self._valid_time(now):
            return -1.0
        return max(0.0, float(now) - self.last_valid_command_at)
