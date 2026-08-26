"""不依赖 ROS 的命令控制权与预备状态机。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandAuthority(str, Enum):
    """Runtime 选定的唯一普通命令控制归属。"""

    NONE = "NONE"
    MANUAL = "MANUAL"
    LEGACY_AUTO = "LEGACY_AUTO"
    FLIGHT_CONTROL = "FLIGHT_CONTROL"


@dataclass(frozen=True)
class AuthorityGrant:
    """限定于一个 Runtime 进程和一次 prepare 尝试的控制权标识。

    ``generation`` 只在 ``authority_epoch`` 内唯一；二者组成的标识可防止命令跨越
    重启或会话边界继续生效。该标识不授予硬件访问权。
    """

    authority: CommandAuthority
    authority_epoch: int
    generation: int
    sequence: int


@dataclass(frozen=True)
class OwnerAcknowledgement:
    """用于诊断的 owner 确认；它绝不是控制权授予或原子截止点。"""

    owner: OwnershipDomain
    authority_epoch: int
    generation: int
    observed_state_sequence: int


@dataclass(frozen=True)
class AuthorityCommitResult:
    """显式原子控制权提交产生的一次性结果。"""

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
    """请求的状态转换违反控制权契约时抛出。"""


class AuthorityStateMachine:
    """在原子提交前，把 owner 确认绑定到同一个 epoch/generation。

    cancel 或 inhibit 会使本次尝试的 token 失效；返回 DRY_RUN 需要显式重置，
    且绝不会自动恢复旧 owner 或旧命令。
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
        """记录一次诊断性 owner 确认，但不授予控制权。"""

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
        """在 Runtime 当前状态边界原子授予控制权。"""

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
