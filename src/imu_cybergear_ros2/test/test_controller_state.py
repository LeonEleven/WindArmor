from types import SimpleNamespace

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    StateManager,
    public_control_mode,
)
from imu_cybergear_ros2.safety_monitor import SafetyMonitor


class Logger:
    def info(self, _message):
        pass

    def error(self, _message):
        pass


class Node:
    _is_active = True

    def get_logger(self):
        return Logger()


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


def test_state_change_callback_runs_immediately() -> None:
    received = []
    manager = StateManager(Node(), state_change_callback=received.append)
    manager.transition_to(ControllerState.MANUAL_RUNNING)
    assert received == [ControllerState.MANUAL_RUNNING]


def test_enable_motor_service_recovers_to_manual_without_hardware() -> None:
    state = StateManager(Node())
    state.transition_to(ControllerState.EMERGENCY_STOP)
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: True,
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    request = SimpleNamespace(data=True)
    result = monitor.on_enable_motor_service(request, response)
    assert result.success
    assert state.state == ControllerState.MANUAL_RUNNING


def test_failed_enable_motor_service_stays_in_emergency_stop() -> None:
    state = StateManager(Node())
    state.transition_to(ControllerState.EMERGENCY_STOP)
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: False,
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    result = monitor.on_enable_motor_service(
        SimpleNamespace(data=True),
        response,
    )
    assert not result.success
    assert state.state == ControllerState.EMERGENCY_STOP


def test_enable_motor_service_cannot_recover_error_state() -> None:
    state = StateManager(Node())
    state.transition_to(ControllerState.ERROR)
    recovery_calls = []
    motor_manager = SimpleNamespace(
        hold_current_targets_and_recover=lambda: recovery_calls.append(True),
    )
    monitor = SafetyMonitor.__new__(SafetyMonitor)
    monitor._node = Node()
    monitor._state = state
    monitor._motor_mgr = motor_manager
    response = SimpleNamespace(success=False, message="")
    result = monitor.on_enable_motor_service(
        SimpleNamespace(data=True),
        response,
    )
    assert not result.success
    assert "ERROR" in result.message
    assert recovery_calls == []
    assert state.state == ControllerState.ERROR
