"""电机子系统的普通命令纯 ownership 契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class MotorCommandOwner(str, Enum):
    MANUAL = "MANUAL"
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


class MotorOwnershipCore:
    """失效关闭的两阶段 Flight ownership 与本地命令 lease。"""

    def __init__(
        self, *, handoff_timeout_sec: float, command_timeout_sec: float
    ) -> None:
        if not math.isfinite(handoff_timeout_sec) or handoff_timeout_sec <= 0.0:
            raise ValueError("motor_flight_handoff_timeout_sec must be positive")
        if not math.isfinite(command_timeout_sec) or command_timeout_sec <= 0.0:
            raise ValueError("motor_flight_command_timeout_sec must be positive")
        self.handoff_timeout_sec = float(handoff_timeout_sec)
        self.command_timeout_sec = float(command_timeout_sec)
        self.owner = MotorCommandOwner.MANUAL
        self.authority_epoch: int | None = None
        self.generation: int | None = None
        self.last_command_sequence: int | None = None
        self.last_valid_command_at: float | None = None
        self._handoff_deadline: float | None = None
        self._command_deadline: float | None = None
        self._highest_epoch = 0
        self._highest_generation = 0

    @staticmethod
    def _valid_token(authority_epoch: object, generation: object) -> bool:
        return (
            isinstance(authority_epoch, int)
            and not isinstance(authority_epoch, bool)
            and 0 < authority_epoch <= (2**64 - 1)
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

    def prepare(
        self, authority_epoch: int, generation: int, *, now: float, safe: bool
    ) -> OwnershipResult:
        if not self._valid_token(authority_epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(False, "invalid_monotonic_time", authority_epoch, generation)
        current = (self.authority_epoch, self.generation)
        requested = (authority_epoch, generation)
        if self.owner is MotorCommandOwner.FLIGHT_RESERVED and current == requested:
            return OwnershipResult(True, "already_reserved", authority_epoch, generation)
        if self.owner in (
            MotorCommandOwner.FLIGHT_RESERVED,
            MotorCommandOwner.FLIGHT_CONTROL,
        ):
            return OwnershipResult(False, "flight_owner_busy", authority_epoch, generation)
        if authority_epoch < self._highest_epoch:
            return OwnershipResult(False, "older_authority_epoch", authority_epoch, generation)
        if authority_epoch == self._highest_epoch and generation <= self._highest_generation:
            return OwnershipResult(False, "old_generation", authority_epoch, generation)
        if not safe:
            return OwnershipResult(False, "owner_not_safe", authority_epoch, generation)
        self._highest_epoch = authority_epoch
        self._highest_generation = generation
        self.owner = MotorCommandOwner.FLIGHT_RESERVED
        self.authority_epoch = authority_epoch
        self.generation = generation
        self.last_command_sequence = None
        self.last_valid_command_at = None
        self._handoff_deadline = float(now) + self.handoff_timeout_sec
        self._command_deadline = None
        return OwnershipResult(True, "reserved", authority_epoch, generation)

    def commit(
        self, authority_epoch: int, generation: int, *, now: float, safe: bool
    ) -> OwnershipResult:
        if not self._valid_token(authority_epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(False, "invalid_monotonic_time", authority_epoch, generation)
        matches = (self.authority_epoch, self.generation) == (
            authority_epoch,
            generation,
        )
        if self.owner is MotorCommandOwner.FLIGHT_CONTROL and matches:
            return OwnershipResult(True, "already_committed", authority_epoch, generation)
        if self.owner is not MotorCommandOwner.FLIGHT_RESERVED or not matches:
            return OwnershipResult(False, "reserve_token_mismatch", authority_epoch, generation)
        if not safe:
            return OwnershipResult(False, "owner_not_safe", authority_epoch, generation)
        self.owner = MotorCommandOwner.FLIGHT_CONTROL
        return OwnershipResult(True, "committed", authority_epoch, generation)

    def revoke(self, authority_epoch: int, generation: int) -> OwnershipResult:
        if not self._valid_token(authority_epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        matches = (self.authority_epoch, self.generation) == (
            authority_epoch,
            generation,
        )
        if not matches:
            if (
                self.authority_epoch is None
                and authority_epoch == self._highest_epoch
                and generation == self._highest_generation
            ):
                return OwnershipResult(True, "already_revoked", authority_epoch, generation)
            return OwnershipResult(False, "authority_token_mismatch", authority_epoch, generation)
        self.release_to_none()
        return OwnershipResult(True, "revoked", authority_epoch, generation)

    def accept_command(
        self,
        authority_epoch: int,
        generation: int,
        command_sequence: int,
        *,
        now: float,
    ) -> OwnershipResult:
        result = self._validate_command(
            authority_epoch, generation, command_sequence, now=now
        )
        if result is not None:
            return result
        self.last_command_sequence = command_sequence
        self.last_valid_command_at = float(now)
        self._handoff_deadline = None
        self._command_deadline = float(now) + self.command_timeout_sec
        return OwnershipResult(True, "command_accepted", authority_epoch, generation)

    def accept_safe_stop(
        self,
        authority_epoch: int,
        generation: int,
        command_sequence: int,
        *,
        now: float,
    ) -> OwnershipResult:
        """校验 safe-stop 顺序，但不把它当作 heartbeat。"""

        result = self._validate_command(
            authority_epoch, generation, command_sequence, now=now
        )
        if result is not None:
            return result
        return OwnershipResult(
            True, "safe_stop_accepted", authority_epoch, generation
        )

    def timed_out(self, now: float) -> bool:
        if self.owner not in (
            MotorCommandOwner.FLIGHT_RESERVED,
            MotorCommandOwner.FLIGHT_CONTROL,
        ):
            return False
        deadline = (
            self._handoff_deadline
            if self.last_command_sequence is None
            else self._command_deadline
        )
        if not self._valid_time(now) or deadline is None:
            self.release_to_none()
            return True
        if float(now) <= deadline:
            return False
        self.release_to_none()
        return True

    def release_to_none(self) -> None:
        self.owner = MotorCommandOwner.NONE
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
        self,
        authority_epoch: int,
        generation: int,
        command_sequence: int,
        *,
        now: float,
    ) -> OwnershipResult | None:
        if not self._valid_token(authority_epoch, generation):
            return OwnershipResult(False, "invalid_token", 0, 0)
        if not self._valid_time(now):
            return OwnershipResult(
                False, "invalid_monotonic_time", authority_epoch, generation
            )
        if self.owner is not MotorCommandOwner.FLIGHT_CONTROL:
            return OwnershipResult(
                False, "not_flight_control", authority_epoch, generation
            )
        if (self.authority_epoch, self.generation) != (
            authority_epoch,
            generation,
        ):
            return OwnershipResult(
                False, "authority_token_mismatch", authority_epoch, generation
            )
        if (
            isinstance(command_sequence, bool)
            or not isinstance(command_sequence, int)
            or command_sequence < 0
            or (
                self.last_command_sequence is not None
                and command_sequence <= self.last_command_sequence
            )
        ):
            return OwnershipResult(
                False, "stale_command_sequence", authority_epoch, generation
            )
        return None

    def claim_legacy_for_state(self, *, auto: bool) -> bool:
        if self.owner in (
            MotorCommandOwner.FLIGHT_RESERVED,
            MotorCommandOwner.FLIGHT_CONTROL,
        ):
            return False
        self.owner = (
            MotorCommandOwner.LEGACY_AUTO if auto else MotorCommandOwner.MANUAL
        )
        return True

    def last_valid_command_age(self, now: float) -> float:
        if self.last_valid_command_at is None or not self._valid_time(now):
            return -1.0
        return max(0.0, float(now) - self.last_valid_command_at)
