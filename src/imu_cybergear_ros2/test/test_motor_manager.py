import math
import threading
from types import SimpleNamespace

import pytest

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    StateManager,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.cybergear_driver import SDO_TARGET_POS
from imu_cybergear_ros2.motor_manager import MotorManager
from imu_cybergear_ros2.motor_motion import MotionParameters, MotionSource
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


class Driver:
    def __init__(self):
        self.writes = []
        self.stopped = []

    def write_sdo_float(self, motor_id, address, value):
        self.writes.append((motor_id, address, value))

    def stop_motor(self, motor_id):
        self.stopped.append(motor_id)


class Node:
    def __init__(self):
        self._motor_ids = [1, 2]
        self._limits = {1: (-1.0, 1.0), 2: (-1.0, 1.0)}
        self._lock = threading.RLock()
        self._driver_io_lock = threading.Lock()
        self._current_targets = {1: 0.0, 2: 0.0}
        self._desired_targets = dict(self._current_targets)
        self._current_speeds = {1: 10.0, 2: 10.0}
        self._motor_protection_flags = {1: False, 2: False}
        self._last_target_change_time = {1: 0.0, 2: 0.0}
        self._command_failure_counts = {1: 0, 2: 0}
        self._command_fault_active = False
        self._command_interval = 0.02
        self._motion_dt_max = 0.05
        self._target_reached_tolerance = 0.001
        self._max_step = 0.4
        self._manual_step_rad = math.radians(3.0)
        self._manual_motion_speed = 4.0
        self._auto_motion_speed = 4.0
        self._home_motion_speed = 4.0
        self._manual_repeat_gap = 0.8
        self._manual_repeat_dt_max = 0.08
        self._manual_speed_min = 0.5
        self._manual_speed_max = 20.0
        self._manual_speed_step = 0.5
        self._motion_params = MotionParameters(
            command_interval_sec=0.02,
            motion_dt_max_sec=0.05,
            target_reached_tolerance_rad=0.001,
            manual_motion_speed_rad_s=4.0,
            auto_motion_speed_rad_s=4.0,
            home_motion_speed_rad_s=4.0,
            manual_step_rad=math.radians(3.0),
            manual_repeat_gap_sec=0.8,
            manual_repeat_dt_max_sec=0.08,
            max_position_step=0.4,
            default_speed=10.0,
            manual_speed_min=0.5,
            manual_speed_max=20.0,
            manual_speed_step=0.5,
        )
        self._driver = Driver()
        self._is_active = True
        self._running = True
        self._sleep = lambda _seconds: None
        self._logger = Logger()
        self.timers = []
        self.destroyed_timers = []

    def get_logger(self):
        return self._logger

    def create_timer(self, period, callback):
        timer = SimpleNamespace(period=period, callback=callback)
        self.timers.append(timer)
        return timer

    def destroy_timer(self, timer):
        self.destroyed_timers.append(timer)


def build_system():
    node = Node()
    state = StateManager(node)
    manager = MotorManager(node, state)
    state._state_change_callback = manager.on_control_state_changed
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
    return node, state, manager


def switch_mode(state, new_state):
    return state.transition_to(
        new_state,
        reason=TransitionReason.USER_MODE_TOGGLE,
        source=TransitionSource.KEYBOARD,
    )


@pytest.fixture
def system():
    return build_system()


def position_writes(node):
    return [write for write in node._driver.writes if write[1] == SDO_TARGET_POS]


def test_manual_press_only_updates_desired_then_timer_advances(system) -> None:
    node, _state, manager = system
    assert manager.manual_step(1, 1.0, now=1.0)
    assert node._desired_targets[1] == pytest.approx(math.radians(3.0))
    assert node._current_targets[1] == 0.0
    assert position_writes(node) == []

    manager._motion_tick(now=10.0)
    assert position_writes(node) == []
    manager._motion_tick(now=10.02)
    assert node._current_targets[1] == pytest.approx(math.radians(3.0))
    assert len(position_writes(node)) == 1


def test_manual_repeat_uses_event_time_and_direction_reset(system) -> None:
    node, _state, manager = system
    manager.manual_step(1, 1.0, now=1.0)
    manager.manual_step(1, 1.0, now=1.05)
    assert node._desired_targets[1] == pytest.approx(math.radians(3.0) + 0.2)
    manager.manual_step(1, -1.0, now=1.06)
    assert node._desired_targets[1] == pytest.approx(0.2)
    assert (1, 1.0) not in manager._manual_repeat_times


def test_repeat_state_is_independent_per_motor_and_gap(system) -> None:
    node, _state, manager = system
    manager.manual_step(1, 1.0, now=1.0)
    manager.manual_step(2, 1.0, now=1.1)
    manager.manual_step(1, 1.0, now=2.0)
    assert node._desired_targets[1] == pytest.approx(2 * math.radians(3.0))
    assert node._desired_targets[2] == pytest.approx(math.radians(3.0))


def test_manual_absolute_targets_are_atomic_and_do_not_write(system) -> None:
    node, state, manager = system
    result = manager.set_manual_targets({1: 2.0, 2: -2.0})
    assert result == {1: 1.0, 2: -1.0}
    assert node._desired_targets == result
    assert position_writes(node) == []

    before = dict(node._desired_targets)
    with pytest.raises(ValueError):
        manager.set_manual_targets({1: math.nan, 2: 0.0})
    assert node._desired_targets == before

    switch_mode(state, ControllerState.AUTO_RUNNING)
    with pytest.raises(ValueError):
        manager.set_manual_targets({1: 0.0, 2: 0.0})


def test_auto_callbacks_only_replace_desired_and_frequency_does_not_advance(system) -> None:
    node, state, manager = system
    switch_mode(state, ControllerState.AUTO_RUNNING)
    for _ in range(10):
        assert manager.set_auto_targets({1: 1.0, 2: -1.0})
    assert node._current_targets == {1: 0.0, 2: 0.0}
    assert position_writes(node) == []

    manager._motion_tick(now=5.0)
    manager._motion_tick(now=5.02)
    assert node._current_targets == pytest.approx({1: 0.08, 2: -0.08})


def test_auto_targets_remain_subject_to_motor_soft_limits(system) -> None:
    node, state, manager = system
    switch_mode(state, ControllerState.AUTO_RUNNING)
    assert manager.set_auto_targets({1: 2.0, 2: -2.0})
    assert node._desired_targets == {1: 1.0, 2: -1.0}
    assert position_writes(node) == []


@pytest.mark.parametrize("message_count", [1, 2, 5])
def test_10_20_50_hz_auto_input_has_same_100ms_progress(message_count) -> None:
    node, state, manager = build_system()
    switch_mode(state, ControllerState.AUTO_RUNNING)
    manager._motion_tick(now=0.0)
    for tick in range(1, 6):
        if tick <= message_count:
            manager.set_auto_targets({1: 1.0, 2: -1.0})
        manager._motion_tick(now=tick * 0.02)
    assert node._current_targets == pytest.approx({1: 0.4, 2: -0.4})


def test_auto_exit_discards_unfinished_target(system) -> None:
    node, state, manager = system
    switch_mode(state, ControllerState.AUTO_RUNNING)
    manager.set_auto_targets({1: 1.0, 2: -1.0})
    manager._motion_tick(now=1.0)
    manager._motion_tick(now=1.02)
    switch_mode(state, ControllerState.MANUAL_RUNNING)
    assert node._desired_targets == node._current_targets
    assert manager.motion_source == MotionSource.IDLE


def test_home_uses_shared_timer_and_auto_switches_to_manual(system) -> None:
    node, state, manager = system
    node._current_targets = {1: 0.4, 2: -0.4}
    node._desired_targets = dict(node._current_targets)
    switch_mode(state, ControllerState.AUTO_RUNNING)
    assert manager.go_all_to_zero()
    assert state.state == ControllerState.MANUAL_RUNNING
    assert state.last_transition.reason is TransitionReason.HOME_REQUEST
    assert state.last_transition.source is TransitionSource.MOTOR_MANAGER
    assert manager.motion_source == MotionSource.HOME
    assert node._desired_targets == {1: 0.0, 2: 0.0}
    assert manager.motion_timer is None

    manager._motion_tick(now=2.0)
    manager._motion_tick(now=2.05)
    assert node._current_targets == pytest.approx({1: 0.2, 2: -0.2})
    manager._motion_tick(now=2.10)
    assert node._current_targets == {1: 0.0, 2: 0.0}
    assert manager.motion_source == MotionSource.IDLE


def test_manual_input_and_shortcut_cancel_home(system) -> None:
    node, _state, manager = system
    node._current_targets = {1: 0.4, 2: 0.4}
    node._desired_targets = dict(node._current_targets)
    manager.go_all_to_zero()
    manager.manual_step(1, 1.0, now=1.0)
    assert manager.motion_source == MotionSource.MANUAL
    assert node._desired_targets[2] == 0.4

    manager.go_all_to_zero()
    assert manager.move_motor_to_90_deg(1, positive=True)
    assert manager.motion_source == MotionSource.MANUAL
    assert node._desired_targets == {1: 1.0, 2: 0.4}
    assert position_writes(node) == []


def test_manual_absolute_target_and_auto_switch_cancel_home(system) -> None:
    node, state, manager = system
    node._current_targets = {1: 0.4, 2: 0.4}
    node._desired_targets = dict(node._current_targets)
    manager.go_all_to_zero()
    manager.set_manual_targets({1: 0.2, 2: -0.2})
    assert manager.motion_source == MotionSource.MANUAL
    assert node._desired_targets == {1: 0.2, 2: -0.2}

    manager.go_all_to_zero()
    switch_mode(state, ControllerState.AUTO_RUNNING)
    assert manager.motion_source == MotionSource.IDLE
    assert node._desired_targets == node._current_targets


def test_shortcut_is_rejected_outside_manual(system) -> None:
    node, state, manager = system
    switch_mode(state, ControllerState.AUTO_RUNNING)
    assert not manager.move_motor_to_90_deg(1, positive=True)
    assert node._desired_targets == node._current_targets
    assert position_writes(node) == []


def test_motion_timer_lifecycle_is_idempotent(system) -> None:
    node, _state, manager = system
    manager.start_motion_timer()
    manager.start_motion_timer()
    assert len(node.timers) == 1
    manager.set_manual_targets({1: 1.0, 2: 1.0})
    manager.stop_motion_timer()
    assert node.destroyed_timers == node.timers
    assert manager.motion_timer is None
    assert manager.motion_source == MotionSource.IDLE
    assert node._desired_targets == node._current_targets


def test_speed_limit_below_mode_speed_limits_progress(system) -> None:
    node, _state, manager = system
    node._current_speeds[1] = 2.0
    manager.set_manual_targets({1: 1.0, 2: 0.0})
    manager._motion_tick(now=3.0)
    manager._motion_tick(now=3.05)
    assert node._current_targets[1] == pytest.approx(0.1)


def test_protected_motor_is_not_written(system) -> None:
    node, _state, manager = system
    node._motor_protection_flags[1] = True
    manager.set_manual_targets({1: 1.0, 2: 1.0})
    manager._motion_tick(now=4.0)
    manager._motion_tick(now=4.02)
    assert node._current_targets[1] == 0.0
    assert node._current_targets[2] == pytest.approx(0.08)


def test_emergency_stop_halts_motion_before_direct_stop(system) -> None:
    node, state, manager = system
    manager.set_manual_targets({1: 1.0, 2: -1.0})
    monitor = SafetyMonitor(node, state, manager)
    monitor.emergency_stop(
        reason=TransitionReason.USER_ESTOP,
        source=TransitionSource.KEYBOARD,
    )
    assert state.state == ControllerState.EMERGENCY_STOP
    assert manager.motion_source == MotionSource.IDLE
    assert node._desired_targets == node._current_targets
    assert node._driver.stopped == [1, 2]


def test_write_failure_preserves_last_successful_target_and_enters_error(system) -> None:
    node, state, manager = system

    def fail(*_args):
        raise RuntimeError("fake failure")

    node._driver.write_sdo_float = fail
    assert not manager.write_command_target(1, 0.25)
    assert node._current_targets[1] == 0.0
    assert node._last_target_change_time[1] == 0.0
    assert state.state == ControllerState.ERROR
    assert node._driver.stopped == [1, 2]
    assert any(level == "error" for level, _message in node._logger.messages)
