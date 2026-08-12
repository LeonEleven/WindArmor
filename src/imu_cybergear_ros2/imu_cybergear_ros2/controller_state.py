"""控制状态转换契约与线程安全状态管理。"""

import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional


class ControllerState(Enum):
    """IMU-电机控制节点的内部状态。"""

    UNINITIALIZED = auto()
    INITIALIZING = auto()
    AUTO_RUNNING = auto()
    MANUAL_RUNNING = auto()
    EMERGENCY_STOP = auto()
    ERROR = auto()
    SHUTTING_DOWN = auto()


class TransitionOutcome(Enum):
    """状态转换请求的确定性结果。"""

    CHANGED = auto()
    NO_CHANGE = auto()
    REJECTED = auto()


class TransitionReason(str, Enum):
    """稳定、可诊断的状态转换原因。"""

    CONFIGURE_START = "configure_start"
    CONFIGURE_SUCCESS = "configure_success"
    CONFIGURE_FAILURE = "configure_failure"
    DRIVER_CONNECT_FAILURE = "driver_connect_failure"
    MOTOR_INIT_FAILURE = "motor_init_failure"
    USER_MODE_TOGGLE = "user_mode_toggle"
    HOME_REQUEST = "home_request"
    FLIGHT_OWNERSHIP_COMMIT = "flight_ownership_commit"
    FLIGHT_OWNERSHIP_REVOKE = "flight_ownership_revoke"
    IMU_WATCHDOG_TIMEOUT = "imu_watchdog_timeout"
    USER_ESTOP = "user_estop"
    TOPIC_ESTOP = "topic_estop"
    SERVICE_ESTOP = "service_estop"
    REMOTE_DISABLE = "remote_disable"
    EXPLICIT_ESTOP_RECOVERY = "explicit_estop_recovery"
    POSITION_COMMAND_WRITE_FAILURE = "position_command_write_failure"
    SPEED_COMMAND_WRITE_FAILURE = "speed_command_write_failure"
    TRANSPORT_FAILURE = "transport_failure"
    MOTOR_FEEDBACK_FAULT = "motor_feedback_fault"
    MOTOR_FAULT_UNDERVOLTAGE = "motor_fault_undervoltage"
    MOTOR_OVERCURRENT_FAULT = "motor_overcurrent_fault"
    MOTOR_OVERTEMPERATURE_FAULT = "motor_overtemperature_fault"
    MOTOR_FAULT_ENCODER = "motor_fault_encoder"
    MOTOR_FAULT_UNCALIBRATED = "motor_fault_uncalibrated"
    MOTOR_FAULT_MULTIPLE = "motor_fault_multiple"
    MOTOR_CRITICAL_TEMPERATURE = "motor_critical_temperature"
    MOTOR_FEEDBACK_TIMEOUT = "motor_feedback_timeout"
    MOTOR_INVALID_FEEDBACK = "motor_invalid_feedback"
    MECHANICAL_ZERO_FAILURE = "mechanical_zero_failure"
    SHUTDOWN_REQUEST = "shutdown_request"


class TransitionSource(str, Enum):
    """稳定、可诊断的状态转换调用来源。"""

    LIFECYCLE = "lifecycle"
    MOTOR_MANAGER = "motor_manager"
    SAFETY_MONITOR = "safety_monitor"
    KEYBOARD = "keyboard"
    SERVICE = "service"
    TOPIC = "topic"
    WATCHDOG = "watchdog"
    DRIVER_FEEDBACK = "driver_feedback"
    DRIVER_TRANSPORT = "driver_transport"


@dataclass(frozen=True)
class TransitionRecord:
    """最近一次真实状态变化的不可变快照。"""

    sequence: int
    old_state: ControllerState
    new_state: ControllerState
    reason: TransitionReason
    source: TransitionSource
    monotonic_timestamp: float


@dataclass(frozen=True)
class TransitionResult:
    """一次状态转换请求的结构化结果。"""

    outcome: TransitionOutcome
    old_state: ControllerState
    requested_state: ControllerState
    reason: TransitionReason
    source: TransitionSource

    @property
    def accepted(self) -> bool:
        """请求是否被接受（真实变化或幂等重复）。"""
        return self.outcome is not TransitionOutcome.REJECTED


LEGAL_TRANSITIONS = {
    ControllerState.UNINITIALIZED: frozenset(
        {
            ControllerState.INITIALIZING,
            ControllerState.ERROR,
            ControllerState.SHUTTING_DOWN,
        }
    ),
    ControllerState.INITIALIZING: frozenset(
        {
            ControllerState.MANUAL_RUNNING,
            ControllerState.ERROR,
            ControllerState.EMERGENCY_STOP,
            ControllerState.SHUTTING_DOWN,
        }
    ),
    ControllerState.MANUAL_RUNNING: frozenset(
        {
            ControllerState.AUTO_RUNNING,
            ControllerState.EMERGENCY_STOP,
            ControllerState.ERROR,
            ControllerState.SHUTTING_DOWN,
        }
    ),
    ControllerState.AUTO_RUNNING: frozenset(
        {
            ControllerState.MANUAL_RUNNING,
            ControllerState.EMERGENCY_STOP,
            ControllerState.ERROR,
            ControllerState.SHUTTING_DOWN,
        }
    ),
    ControllerState.EMERGENCY_STOP: frozenset(
        {
            ControllerState.MANUAL_RUNNING,
            ControllerState.ERROR,
            ControllerState.SHUTTING_DOWN,
        }
    ),
    ControllerState.ERROR: frozenset({ControllerState.SHUTTING_DOWN}),
    ControllerState.SHUTTING_DOWN: frozenset(),
}


class StateManager:
    """依据显式转换表管理状态、回调和最近转换快照。"""

    def __init__(
        self,
        node,
        stop_auto_zero_callback=None,
        state_change_callback=None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ):
        self._node = node
        self._state = ControllerState.UNINITIALIZED
        self._state_lock = threading.RLock()
        self._stop_auto_zero_callback = stop_auto_zero_callback
        self._state_change_callback = state_change_callback
        self._monotonic = monotonic_fn
        self._transition_sequence = 0
        self._last_transition: Optional[TransitionRecord] = None

    @property
    def state(self) -> ControllerState:
        """获取当前状态。"""
        with self._state_lock:
            return self._state

    @property
    def state_name(self) -> str:
        """获取当前状态名称。"""
        with self._state_lock:
            return self._state.name

    @property
    def last_transition(self) -> Optional[TransitionRecord]:
        """获取最近真实转换的不可变快照。"""
        with self._state_lock:
            return self._last_transition

    def is_in(self, *states: ControllerState) -> bool:
        """原子判断当前状态是否属于给定集合。"""
        with self._state_lock:
            return self._state in states

    def register_stop_auto_zero_callback(self, callback: Callable[[], None]) -> bool:
        """一次性注册离开运行态时的停止回调。

        首次注册返回 ``True``；相同对象重复注册是幂等操作并返回 ``False``；
        使用不同对象覆盖既有注册会被拒绝。
        """
        if not callable(callback):
            raise TypeError("stop_auto_zero callback 必须可调用")
        with self._state_lock:
            if self._stop_auto_zero_callback is None:
                self._stop_auto_zero_callback = callback
                return True
            if self._stop_auto_zero_callback == callback:
                return False
            raise RuntimeError("stop_auto_zero callback 已注册，不允许覆盖")

    def transition_to(
        self,
        new_state: ControllerState,
        *,
        reason: TransitionReason,
        source: TransitionSource,
    ) -> TransitionResult:
        """按合法转换表执行请求；普通非法转换不会抛异常。"""
        if not isinstance(new_state, ControllerState):
            raise TypeError("new_state 必须是 ControllerState")
        if not isinstance(reason, TransitionReason):
            raise TypeError("reason 必须是 TransitionReason")
        if not isinstance(source, TransitionSource):
            raise TypeError("source 必须是 TransitionSource")

        stop_auto_zero = None
        state_change_callback = None
        with self._state_lock:
            old_state = self._state
            result = TransitionResult(
                outcome=TransitionOutcome.REJECTED,
                old_state=old_state,
                requested_state=new_state,
                reason=reason,
                source=source,
            )
            if old_state == new_state:
                return TransitionResult(
                    outcome=TransitionOutcome.NO_CHANGE,
                    old_state=old_state,
                    requested_state=new_state,
                    reason=reason,
                    source=source,
                )

            allowed = new_state in LEGAL_TRANSITIONS[old_state]
            if (
                old_state == ControllerState.EMERGENCY_STOP
                and new_state == ControllerState.MANUAL_RUNNING
                and reason != TransitionReason.EXPLICIT_ESTOP_RECOVERY
            ):
                allowed = False
            if not allowed:
                self._node.get_logger().error(
                    "拒绝非法状态转换: "
                    f"{old_state.name} -> {new_state.name}, "
                    f"reason={reason.value}, source={source.value}"
                )
                return result

            self._state = new_state
            self._transition_sequence += 1
            self._last_transition = TransitionRecord(
                sequence=self._transition_sequence,
                old_state=old_state,
                new_state=new_state,
                reason=reason,
                source=source,
                monotonic_timestamp=self._monotonic(),
            )
            self._node.get_logger().info(
                f"状态转换: {old_state.name} -> {new_state.name}, "
                f"reason={reason.value}, source={source.value}, "
                f"sequence={self._transition_sequence}"
            )
            if old_state in (
                ControllerState.AUTO_RUNNING,
                ControllerState.MANUAL_RUNNING,
            ) and new_state not in (
                ControllerState.AUTO_RUNNING,
                ControllerState.MANUAL_RUNNING,
            ):
                stop_auto_zero = self._stop_auto_zero_callback
            state_change_callback = self._state_change_callback

        # 外部回调必须在状态锁外执行；异常不会回滚已完成的状态变化。
        self._run_callback("stop_auto_zero", stop_auto_zero)
        self._run_callback("state_change", state_change_callback, new_state)
        return TransitionResult(
            outcome=TransitionOutcome.CHANGED,
            old_state=old_state,
            requested_state=new_state,
            reason=reason,
            source=source,
        )

    def _run_callback(self, name: str, callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:
            self._node.get_logger().error(
                f"状态转换回调异常: callback={name}, error={exc}"
            )

    def is_running(self) -> bool:
        """当前是否处于运行态（AUTO 或 MANUAL）。"""
        return self.is_in(
            ControllerState.AUTO_RUNNING, ControllerState.MANUAL_RUNNING
        )

    def is_auto_running(self) -> bool:
        """当前是否处于 AUTO_RUNNING。"""
        return self.is_in(ControllerState.AUTO_RUNNING)

    def is_manual_running(self) -> bool:
        """当前是否处于 MANUAL_RUNNING。"""
        return self.is_in(ControllerState.MANUAL_RUNNING)

    def is_emergency_or_error(self) -> bool:
        """当前是否处于急停或错误状态。"""
        return self.is_in(ControllerState.EMERGENCY_STOP, ControllerState.ERROR)


def public_control_mode(state: ControllerState, *, active: bool) -> str:
    """把内部状态稳定映射为对外发布的控制模式。"""
    if not active:
        return "DISABLED"
    if state == ControllerState.AUTO_RUNNING:
        return "AUTO"
    if state == ControllerState.MANUAL_RUNNING:
        return "MANUAL"
    if state == ControllerState.EMERGENCY_STOP:
        return "EMERGENCY_STOP"
    if state == ControllerState.ERROR:
        return "ERROR"
    return "DISABLED"
