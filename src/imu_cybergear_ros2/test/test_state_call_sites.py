import threading
from types import SimpleNamespace

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    StateManager,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.keyboard_handler import KeyboardHandler
from imu_cybergear_ros2.safety_monitor import SafetyMonitor


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warn(self, message):
        self.messages.append(("warn", message))

    def error(self, message):
        self.messages.append(("error", message))


class Node:
    def __init__(self):
        self._is_active = True
        self._running = True
        self._manual_period = 0.0
        self._last_imu_time = 1.0
        self._watchdog_timeout_s = 0.1
        self._lock = threading.RLock()
        self._motor_ids = [1]
        self._motor_protection_flags = {1: False}
        self.logger = Logger()
        self.system_estop_publishes = 0

    def get_logger(self):
        return self.logger

    def publish_system_emergency_stop(self):
        self.system_estop_publishes += 1


class MotorManager:
    def __init__(self):
        self.halt_calls = 0
        self.stop_reasons = []

    def halt_motion(self):
        self.halt_calls += 1

    def stop_motors_best_effort(self, *, reason, **_kwargs):
        self.stop_reasons.append(reason)
        return True

    def stop_motors_for_fault_once(self, *, reason):
        return self.stop_motors_best_effort(reason=reason)

    def reset_fault_stop_batch_after_recovery(self):
        return None


def running_state(node, target=ControllerState.MANUAL_RUNNING):
    state = StateManager(node)
    state.transition_to(
        ControllerState.INITIALIZING,
        reason=TransitionReason.CONFIGURE_START,
        source=TransitionSource.LIFECYCLE,
    )
    state.transition_to(
        ControllerState.MANUAL_RUNNING,
        reason=TransitionReason.CONFIGURE_SUCCESS,
        source=TransitionSource.MOTOR_MANAGER,
    )
    if target is ControllerState.AUTO_RUNNING:
        state.transition_to(
            ControllerState.AUTO_RUNNING,
            reason=TransitionReason.USER_MODE_TOGGLE,
            source=TransitionSource.KEYBOARD,
        )
    return state


def test_watchdog_records_timeout_reason_and_source(monkeypatch) -> None:
    node = Node()
    state = running_state(node, ControllerState.AUTO_RUNNING)
    monitor = SafetyMonitor(node, state, MotorManager())
    monkeypatch.setattr("imu_cybergear_ros2.safety_monitor.time.monotonic", lambda: 2.0)
    monitor._watchdog_check()
    assert state.state is ControllerState.MANUAL_RUNNING
    assert state.last_transition.reason is TransitionReason.IMU_WATCHDOG_TIMEOUT
    assert state.last_transition.source is TransitionSource.WATCHDOG


def test_topic_estop_records_topic_reason_and_source() -> None:
    node = Node()
    state = running_state(node)
    monitor = SafetyMonitor(node, state, MotorManager())
    monitor.on_e_stop_topic(SimpleNamespace(data=True))
    assert state.state is ControllerState.EMERGENCY_STOP
    assert state.last_transition.reason is TransitionReason.TOPIC_ESTOP
    assert state.last_transition.source is TransitionSource.TOPIC


def test_service_estop_records_service_reason_and_source() -> None:
    node = Node()
    state = running_state(node)
    monitor = SafetyMonitor(node, state, MotorManager())
    response = SimpleNamespace(success=False, message="")
    monitor.on_e_stop_service(SimpleNamespace(), response)
    assert response.success
    assert node.system_estop_publishes == 1
    assert state.last_transition.reason is TransitionReason.SERVICE_ESTOP
    assert state.last_transition.source is TransitionSource.SERVICE


def run_one_keyboard_key(handler, node, key):
    calls = 0

    def get_key():
        nonlocal calls
        calls += 1
        if calls == 1:
            return key
        node._running = False
        return None

    handler._set_terminal_raw = lambda: None
    handler._restore_terminal = lambda: None
    handler._get_key = get_key
    handler._keyboard_loop()


def test_keyboard_mode_toggle_records_user_reason_and_keyboard_source() -> None:
    node = Node()
    state = running_state(node)
    handler = KeyboardHandler(node, state, SimpleNamespace(), SimpleNamespace())
    run_one_keyboard_key(handler, node, "m")
    assert state.state is ControllerState.AUTO_RUNNING
    assert state.last_transition.reason is TransitionReason.USER_MODE_TOGGLE
    assert state.last_transition.source is TransitionSource.KEYBOARD


def test_keyboard_estop_passes_distinct_user_reason_and_source() -> None:
    node = Node()
    state = running_state(node)
    calls = []
    safety = SimpleNamespace(
        emergency_stop=lambda **kwargs: calls.append(kwargs) or True,
    )
    handler = KeyboardHandler(node, state, SimpleNamespace(), safety)
    run_one_keyboard_key(handler, node, " ")
    assert calls == [
        {
            "reason": TransitionReason.USER_ESTOP,
            "source": TransitionSource.KEYBOARD,
        }
    ]
    assert node.system_estop_publishes == 1


def test_keyboard_recovery_identifies_keyboard_source() -> None:
    node = Node()
    state = running_state(node)
    state.transition_to(
        ControllerState.EMERGENCY_STOP,
        reason=TransitionReason.USER_ESTOP,
        source=TransitionSource.KEYBOARD,
    )
    sources = []
    safety = SimpleNamespace(
        recover_from_emergency_stop=lambda **kwargs: sources.append(kwargs["source"])
    )
    handler = KeyboardHandler(node, state, SimpleNamespace(), safety)
    run_one_keyboard_key(handler, node, "r")
    assert sources == [TransitionSource.KEYBOARD]
