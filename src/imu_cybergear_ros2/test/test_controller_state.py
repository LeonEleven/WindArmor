from dataclasses import FrozenInstanceError
import threading
from types import SimpleNamespace

import pytest

from imu_cybergear_ros2.controller_state import (
    LEGAL_TRANSITIONS,
    ControllerState,
    StateManager,
    TransitionOutcome,
    TransitionReason,
    TransitionSource,
    public_control_mode,
)
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
    _is_active = True

    def __init__(self):
        self.logger = Logger()

    def get_logger(self):
        return self.logger


def transition(
    manager,
    new_state,
    reason=TransitionReason.USER_MODE_TOGGLE,
    source=TransitionSource.KEYBOARD,
):
    return manager.transition_to(new_state, reason=reason, source=source)


def manager_in(target_state, **kwargs):
    manager = StateManager(Node(), **kwargs)
    if target_state == ControllerState.UNINITIALIZED:
        return manager
    transition(
        manager,
        ControllerState.INITIALIZING,
        TransitionReason.CONFIGURE_START,
        TransitionSource.LIFECYCLE,
    )
    if target_state == ControllerState.INITIALIZING:
        return manager
    if target_state == ControllerState.ERROR:
        transition(
            manager,
            ControllerState.ERROR,
            TransitionReason.CONFIGURE_FAILURE,
            TransitionSource.LIFECYCLE,
        )
        return manager
    transition(
        manager,
        ControllerState.MANUAL_RUNNING,
        TransitionReason.CONFIGURE_SUCCESS,
        TransitionSource.MOTOR_MANAGER,
    )
    if target_state == ControllerState.MANUAL_RUNNING:
        return manager
    if target_state == ControllerState.AUTO_RUNNING:
        transition(manager, ControllerState.AUTO_RUNNING)
        return manager
    if target_state == ControllerState.EMERGENCY_STOP:
        transition(
            manager,
            ControllerState.EMERGENCY_STOP,
            TransitionReason.USER_ESTOP,
            TransitionSource.KEYBOARD,
        )
        return manager
    if target_state == ControllerState.SHUTTING_DOWN:
        transition(
            manager,
            ControllerState.SHUTTING_DOWN,
            TransitionReason.SHUTDOWN_REQUEST,
            TransitionSource.LIFECYCLE,
        )
        return manager
    raise AssertionError(target_state)


def test_public_control_mode_mapping() -> None:
    assert public_control_mode(ControllerState.AUTO_RUNNING, active=True) == "AUTO"
    assert public_control_mode(ControllerState.MANUAL_RUNNING, active=True) == "MANUAL"
    assert (
        public_control_mode(ControllerState.EMERGENCY_STOP, active=True)
        == "EMERGENCY_STOP"
    )
    assert public_control_mode(ControllerState.ERROR, active=True) == "ERROR"
    assert public_control_mode(ControllerState.INITIALIZING, active=True) == "DISABLED"
    assert public_control_mode(ControllerState.AUTO_RUNNING, active=False) == "DISABLED"


@pytest.mark.parametrize(
    ("old_state", "new_state"),
    [
        (old_state, new_state)
        for old_state, destinations in LEGAL_TRANSITIONS.items()
        for new_state in destinations
    ],
)
def test_every_legal_transition_uses_real_state_manager(old_state, new_state):
    manager = manager_in(old_state)
    reason = TransitionReason.USER_MODE_TOGGLE
    if old_state == ControllerState.EMERGENCY_STOP and new_state == ControllerState.MANUAL_RUNNING:
        reason = TransitionReason.EXPLICIT_ESTOP_RECOVERY
    result = transition(manager, new_state, reason)
    assert result.outcome is TransitionOutcome.CHANGED
    assert manager.state is new_state


@pytest.mark.parametrize(
    ("old_state", "new_state"),
    [
        (ControllerState.UNINITIALIZED, ControllerState.AUTO_RUNNING),
        (ControllerState.INITIALIZING, ControllerState.AUTO_RUNNING),
        (ControllerState.MANUAL_RUNNING, ControllerState.UNINITIALIZED),
        (ControllerState.AUTO_RUNNING, ControllerState.INITIALIZING),
        (ControllerState.ERROR, ControllerState.MANUAL_RUNNING),
        (ControllerState.ERROR, ControllerState.AUTO_RUNNING),
        (ControllerState.SHUTTING_DOWN, ControllerState.MANUAL_RUNNING),
        (ControllerState.SHUTTING_DOWN, ControllerState.ERROR),
    ],
)
def test_key_illegal_transitions_are_rejected(old_state, new_state):
    manager = manager_in(old_state)
    previous = manager.last_transition
    result = transition(manager, new_state)
    assert result.outcome is TransitionOutcome.REJECTED
    assert manager.state is old_state
    assert manager.last_transition is previous


def test_estop_recovery_requires_explicit_reason() -> None:
    manager = manager_in(ControllerState.EMERGENCY_STOP)
    rejected = transition(manager, ControllerState.MANUAL_RUNNING)
    assert rejected.outcome is TransitionOutcome.REJECTED
    accepted = transition(
        manager,
        ControllerState.MANUAL_RUNNING,
        TransitionReason.EXPLICIT_ESTOP_RECOVERY,
        TransitionSource.SERVICE,
    )
    assert accepted.outcome is TransitionOutcome.CHANGED


def test_same_state_is_idempotent_without_callbacks_or_new_record() -> None:
    state_changes = []
    stop_calls = []
    manager = manager_in(
        ControllerState.MANUAL_RUNNING,
        state_change_callback=state_changes.append,
        stop_auto_zero_callback=lambda: stop_calls.append(True),
    )
    state_changes.clear()
    previous = manager.last_transition
    result = transition(manager, ControllerState.MANUAL_RUNNING)
    assert result.outcome is TransitionOutcome.NO_CHANGE
    assert manager.last_transition is previous
    assert state_changes == []
    assert stop_calls == []


def test_rejected_transition_does_not_run_callbacks() -> None:
    state_changes = []
    stop_calls = []
    manager = manager_in(
        ControllerState.MANUAL_RUNNING,
        state_change_callback=state_changes.append,
        stop_auto_zero_callback=lambda: stop_calls.append(True),
    )
    state_changes.clear()
    result = transition(manager, ControllerState.UNINITIALIZED)
    assert result.outcome is TransitionOutcome.REJECTED
    assert state_changes == []
    assert stop_calls == []


def test_real_transition_callbacks_run_once_outside_lock_and_can_read_state() -> None:
    observations = []
    holder = {}

    def stop_callback():
        observations.append(("stop", holder["manager"].state))

    def state_callback(new_state):
        observations.append(("state", holder["manager"].state, new_state))

    manager = StateManager(
        Node(),
        stop_auto_zero_callback=stop_callback,
        state_change_callback=state_callback,
    )
    holder["manager"] = manager
    transition(
        manager,
        ControllerState.INITIALIZING,
        TransitionReason.CONFIGURE_START,
        TransitionSource.LIFECYCLE,
    )
    transition(
        manager,
        ControllerState.MANUAL_RUNNING,
        TransitionReason.CONFIGURE_SUCCESS,
        TransitionSource.MOTOR_MANAGER,
    )
    observations.clear()
    transition(
        manager,
        ControllerState.EMERGENCY_STOP,
        TransitionReason.USER_ESTOP,
        TransitionSource.KEYBOARD,
    )
    assert observations == [
        ("stop", ControllerState.EMERGENCY_STOP),
        (
            "state",
            ControllerState.EMERGENCY_STOP,
            ControllerState.EMERGENCY_STOP,
        ),
    ]


def test_callback_exception_is_logged_without_rolling_back_transition() -> None:
    node = Node()

    def fail(_new_state):
        raise RuntimeError("callback failed")

    manager = StateManager(node, state_change_callback=fail)
    result = transition(
        manager,
        ControllerState.INITIALIZING,
        TransitionReason.CONFIGURE_START,
        TransitionSource.LIFECYCLE,
    )
    assert result.outcome is TransitionOutcome.CHANGED
    assert manager.state is ControllerState.INITIALIZING
    assert any("callback failed" in message for _, message in node.logger.messages)


def test_transition_snapshot_sequence_reason_source_and_monotonic_clock() -> None:
    timestamps = iter([10.0, 11.5])
    manager = StateManager(Node(), monotonic_fn=lambda: next(timestamps))
    transition(
        manager,
        ControllerState.INITIALIZING,
        TransitionReason.CONFIGURE_START,
        TransitionSource.LIFECYCLE,
    )
    first = manager.last_transition
    assert first.sequence == 1
    assert first.reason is TransitionReason.CONFIGURE_START
    assert first.source is TransitionSource.LIFECYCLE
    assert first.monotonic_timestamp == 10.0

    transition(
        manager,
        ControllerState.ERROR,
        TransitionReason.CONFIGURE_FAILURE,
        TransitionSource.LIFECYCLE,
    )
    second = manager.last_transition
    assert second.sequence == 2
    assert second.monotonic_timestamp == 11.5
    with pytest.raises(FrozenInstanceError):
        second.sequence = 99


def test_concurrent_snapshot_readers_never_observe_partial_record() -> None:
    manager = manager_in(ControllerState.MANUAL_RUNNING)
    finished = threading.Event()
    failures = []

    def reader():
        while not finished.is_set():
            record = manager.last_transition
            if record is None:
                failures.append("missing record")
                return
            if (
                record.sequence < 1
                or not isinstance(record.old_state, ControllerState)
                or not isinstance(record.new_state, ControllerState)
                or not isinstance(record.reason, TransitionReason)
                or not isinstance(record.source, TransitionSource)
            ):
                failures.append(record)
                return

    readers = [threading.Thread(target=reader) for _ in range(4)]
    for thread in readers:
        thread.start()
    for _ in range(50):
        switch_to = (
            ControllerState.AUTO_RUNNING
            if manager.is_manual_running()
            else ControllerState.MANUAL_RUNNING
        )
        transition(manager, switch_to)
    finished.set()
    for thread in readers:
        thread.join(timeout=1.0)
    assert failures == []


def test_stop_callback_registration_is_thread_safe_and_one_time() -> None:
    manager = StateManager(Node())

    def callback():
        pass

    assert manager.register_stop_auto_zero_callback(callback)
    assert not manager.register_stop_auto_zero_callback(callback)
    with pytest.raises(RuntimeError, match="不允许覆盖"):
        manager.register_stop_auto_zero_callback(lambda: None)


def test_enable_motor_service_recovers_to_manual_without_hardware() -> None:
    state = manager_in(ControllerState.EMERGENCY_STOP)
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: True,
        halt_motion=lambda: None,
        stop_motors_best_effort=lambda **_kwargs: True,
        reset_fault_stop_batch_after_recovery=lambda: None,
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    result = monitor.on_enable_motor_service(SimpleNamespace(data=True), response)
    assert result.success
    assert state.state is ControllerState.MANUAL_RUNNING
    assert state.last_transition.reason is TransitionReason.EXPLICIT_ESTOP_RECOVERY
    assert state.last_transition.source is TransitionSource.SERVICE


def test_failed_enable_motor_service_stays_in_emergency_stop() -> None:
    state = manager_in(ControllerState.EMERGENCY_STOP)
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: False,
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    result = monitor.on_enable_motor_service(SimpleNamespace(data=True), response)
    assert not result.success
    assert state.state is ControllerState.EMERGENCY_STOP


def test_enable_motor_service_cannot_recover_error_state() -> None:
    state = manager_in(ControllerState.ERROR)
    recovery_calls = []
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: recovery_calls.append(True),
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    result = monitor.on_enable_motor_service(SimpleNamespace(data=True), response)
    assert not result.success
    assert "ERROR" in result.message
    assert recovery_calls == []
    assert state.state is ControllerState.ERROR
