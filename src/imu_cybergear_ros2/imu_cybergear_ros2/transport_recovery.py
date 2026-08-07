"""Pure-software transport fault events and bounded runtime recovery."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class TransportEventType(str, Enum):
    """Stable transport diagnostics, separate from motor feedback callbacks."""

    DISCONNECTED = "disconnected"
    READ_ERROR = "read_error"
    WRITE_ERROR = "write_error"
    CLOSE_ERROR = "close_error"
    RECONNECTING = "reconnecting"
    RECONNECTED = "reconnected"
    RECONNECT_FAILED = "reconnect_failed"


@dataclass(frozen=True)
class TransportEvent:
    """One immutable transport diagnostic event."""

    event_type: TransportEventType
    backend: str
    operation: str
    message: str
    monotonic_timestamp: float
    connection_generation: int
    exception: Optional[BaseException] = None
    attempt: Optional[int] = None
    max_attempts: Optional[int] = None


class CyberGearTransportError(RuntimeError):
    """Base class for errors proving a transport operation failed."""

    def __init__(self, message: str, *, event: Optional[TransportEvent] = None):
        super().__init__(message)
        self.event = event


class CyberGearDisconnectedError(CyberGearTransportError):
    """The selected backend has no usable open transport."""


class TransportRecoveryState(str, Enum):
    IDLE = "idle"
    FAULT_LATCHED = "fault_latched"
    RECONNECTING = "reconnecting"
    RECONNECTED_LOCKED = "reconnected_locked"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ReconnectPolicy:
    max_attempts: int
    initial_delay_sec: float
    max_delay_sec: float
    backoff_multiplier: float

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(
            self.max_attempts, int
        ):
            raise ValueError("reconnect_max_attempts must be an integer")
        if self.max_attempts <= 0:
            raise ValueError("reconnect_max_attempts must be greater than zero")
        values = {
            "reconnect_initial_delay_sec": self.initial_delay_sec,
            "reconnect_max_delay_sec": self.max_delay_sec,
            "reconnect_backoff_multiplier": self.backoff_multiplier,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.initial_delay_sec < 0.0:
            raise ValueError("reconnect_initial_delay_sec must not be negative")
        if self.max_delay_sec < self.initial_delay_sec:
            raise ValueError(
                "reconnect_max_delay_sec must be >= reconnect_initial_delay_sec"
            )
        if self.backoff_multiplier < 1.0:
            raise ValueError("reconnect_backoff_multiplier must be >= 1.0")

    def delay_after_failure(self, attempt: int) -> float:
        """Delay after the numbered failed attempt, clamped to the maximum."""
        if attempt <= 0:
            raise ValueError("attempt must be greater than zero")
        return min(
            self.initial_delay_sec * (self.backoff_multiplier ** (attempt - 1)),
            self.max_delay_sec,
        )


@dataclass(frozen=True)
class TransportRecoverySnapshot:
    state: TransportRecoveryState
    attempt: int
    max_attempts: int
    first_fault: Optional[TransportEvent]
    worker_alive: bool


class TransportRecoveryCoordinator:
    """Run one bounded, cancellable transport-only recovery sequence.

    The coordinator never initializes motors and never replays a command.  Its
    injected callables are expected to serialize driver I/O outside the node
    state lock.
    """

    def __init__(
        self,
        *,
        reconnect_enabled: bool,
        policy: ReconnectPolicy,
        backend_name: str,
        generation_fn: Callable[[], int],
        stop_for_fault: Callable[[TransportEvent], object],
        close_transport: Callable[[], object],
        connect_once: Callable[[], object],
        event_sink: Callable[[TransportEvent], object],
        monotonic_fn: Callable[[], float] = time.monotonic,
        wait_fn: Optional[Callable[[threading.Event, float], bool]] = None,
    ):
        self._reconnect_enabled = bool(reconnect_enabled)
        self._policy = policy
        self._backend_name = backend_name
        self._generation_fn = generation_fn
        self._stop_for_fault = stop_for_fault
        self._close_transport = close_transport
        self._connect_once = connect_once
        self._event_sink = event_sink
        self._monotonic = monotonic_fn
        self._wait = wait_fn or (lambda event, delay: event.wait(delay))
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._accepting_requests = True
        self._state = TransportRecoveryState.IDLE
        self._attempt = 0
        self._first_fault: Optional[TransportEvent] = None
        self._worker: Optional[threading.Thread] = None

    @property
    def reconnect_enabled(self) -> bool:
        return self._reconnect_enabled

    def snapshot(self) -> TransportRecoverySnapshot:
        with self._lock:
            worker = self._worker
            return TransportRecoverySnapshot(
                state=self._state,
                attempt=self._attempt,
                max_attempts=self._policy.max_attempts,
                first_fault=self._first_fault,
                worker_alive=worker is not None and worker.is_alive(),
            )

    def request_recovery(self, event: TransportEvent) -> bool:
        """Latch the first current-generation fault and start one worker."""
        current_generation = self._generation_fn()
        with self._lock:
            if not self._accepting_requests:
                return False
            if event.connection_generation != current_generation:
                return False
            if self._state is not TransportRecoveryState.IDLE:
                return False
            self._first_fault = event
            self._state = TransportRecoveryState.FAULT_LATCHED
            self._attempt = 0
            self._cancel_event.clear()
            name = (
                "motor-transport-recovery"
                if self._reconnect_enabled
                else "motor-transport-fault-response"
            )
            worker = threading.Thread(target=self._run, daemon=True, name=name)
            self._worker = worker
        worker.start()
        return True

    def disallow_and_cancel(self, *, join_timeout_sec: float = 2.0) -> bool:
        """Prevent new work, interrupt backoff, and join the current worker."""
        with self._lock:
            self._accepting_requests = False
            self._cancel_event.set()
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=join_timeout_sec)
        alive = worker is not None and worker.is_alive()
        with self._lock:
            if not alive:
                self._worker = None
            if self._state not in (
                TransportRecoveryState.IDLE,
                TransportRecoveryState.RECONNECTED_LOCKED,
                TransportRecoveryState.FAILED,
            ):
                self._state = TransportRecoveryState.CANCELLED
        return not alive

    def allow_requests_if_idle(self) -> bool:
        """Resume normal-session monitoring only when no fault was latched."""
        with self._lock:
            if self._state is not TransportRecoveryState.IDLE:
                return False
            self._cancel_event.clear()
            self._accepting_requests = True
            return True

    def clear_callbacks(self) -> None:
        """Release node-owned callback references after cancellation."""
        with self._lock:
            self._event_sink = lambda _event: None
            self._stop_for_fault = lambda _event: None
            self._close_transport = lambda: None
            self._connect_once = lambda: None

    def _run(self) -> None:
        fault = self._first_fault
        if fault is None:
            return
        try:
            try:
                self._stop_for_fault(fault)
            except Exception:
                # The injected production stop path is already best-effort;
                # an unexpected wrapper failure still must not prevent ERROR
                # latching or bounded transport recovery.
                pass
            try:
                self._close_transport()
            except Exception as exc:
                self._emit(
                    TransportEventType.CLOSE_ERROR,
                    operation="close",
                    message=str(exc),
                    exception=exc,
                )
            if self._cancel_event.is_set() or not self._reconnect_enabled:
                return

            for attempt in range(1, self._policy.max_attempts + 1):
                if self._cancel_event.is_set():
                    self._set_cancelled()
                    return
                with self._lock:
                    self._state = TransportRecoveryState.RECONNECTING
                    self._attempt = attempt
                self._emit(
                    TransportEventType.RECONNECTING,
                    operation="connect",
                    message=(
                        f"runtime transport reconnect attempt "
                        f"{attempt}/{self._policy.max_attempts}"
                    ),
                    attempt=attempt,
                )
                try:
                    self._connect_once()
                except Exception as exc:
                    if self._cancel_event.is_set():
                        self._set_cancelled()
                        return
                    if attempt >= self._policy.max_attempts:
                        with self._lock:
                            self._state = TransportRecoveryState.FAILED
                        self._emit(
                            TransportEventType.RECONNECT_FAILED,
                            operation="connect",
                            message=str(exc),
                            exception=exc,
                            attempt=attempt,
                        )
                        return
                    delay = self._policy.delay_after_failure(attempt)
                    if self._wait(self._cancel_event, delay):
                        self._set_cancelled()
                        return
                    continue

                if self._cancel_event.is_set():
                    # A lifecycle cancellation may race an in-progress open.
                    # Close a connection that completed after cancellation so
                    # deactivate/cleanup can never leave it reopened.
                    try:
                        self._close_transport()
                    finally:
                        self._set_cancelled()
                    return
                with self._lock:
                    self._state = TransportRecoveryState.RECONNECTED_LOCKED
                self._emit(
                    TransportEventType.RECONNECTED,
                    operation="connect",
                    message="transport restored; motor control remains locked in ERROR",
                    attempt=attempt,
                )
                return
        finally:
            with self._lock:
                if self._worker is threading.current_thread():
                    self._worker = None

    def _set_cancelled(self) -> None:
        with self._lock:
            self._state = TransportRecoveryState.CANCELLED

    def _emit(
        self,
        event_type: TransportEventType,
        *,
        operation: str,
        message: str,
        exception: Optional[BaseException] = None,
        attempt: Optional[int] = None,
    ) -> None:
        event = TransportEvent(
            event_type=event_type,
            backend=self._backend_name,
            operation=operation,
            message=message,
            monotonic_timestamp=self._monotonic(),
            connection_generation=self._generation_fn(),
            exception=exception,
            attempt=attempt,
            max_attempts=self._policy.max_attempts,
        )
        try:
            self._event_sink(event)
        except Exception:
            # Diagnostics must never terminate the safety/recovery worker.
            pass
