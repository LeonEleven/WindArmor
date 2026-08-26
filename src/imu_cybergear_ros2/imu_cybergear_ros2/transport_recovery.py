"""纯软件 transport 故障事件与有界运行时恢复。"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class TransportEventType(str, Enum):
    """与电机反馈回调分离的稳定 transport 诊断类型。"""

    DISCONNECTED = "disconnected"
    READ_ERROR = "read_error"
    WRITE_ERROR = "write_error"
    CLOSE_ERROR = "close_error"
    RECONNECTING = "reconnecting"
    RECONNECTED = "reconnected"
    RECONNECT_FAILED = "reconnect_failed"


@dataclass(frozen=True)
class TransportEvent:
    """单个不可变 transport 诊断事件。"""

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
    """可证明 transport 操作失败的错误基类。"""

    def __init__(self, message: str, *, event: Optional[TransportEvent] = None):
        super().__init__(message)
        self.event = event


class CyberGearDisconnectedError(CyberGearTransportError):
    """所选后端没有可用且已打开的 transport。"""


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
        """返回指定失败次数后的延迟，并限制在最大值内。"""
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
    """运行一次有界、可取消且仅涉及 transport 的恢复序列。

    协调器绝不初始化电机，也绝不重放命令。注入的可调用对象应在节点状态锁之外
    串行化驱动 I/O。
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
        """锁存当前 generation 的首个故障并启动一个 worker。"""
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
        """阻止新任务、中断退避并等待当前 worker 退出。"""
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
        """仅在没有故障锁存时恢复 normal session 监控。"""
        with self._lock:
            if self._state is not TransportRecoveryState.IDLE:
                return False
            self._cancel_event.clear()
            self._accepting_requests = True
            return True

    def clear_callbacks(self) -> None:
        """取消后释放节点持有的回调引用。"""
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
                # 注入的生产停止路径已采用 best-effort；意外的 wrapper 失败仍不得
                # 阻止 ERROR 锁存或有界 transport 恢复。
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
                    # lifecycle 取消可能与正在执行的 open 竞争。关闭取消后才完成的连接，
                    # 确保 deactivate/cleanup 不会遗留重新打开的连接。
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
            # 诊断不得终止安全/恢复 worker。
            pass
