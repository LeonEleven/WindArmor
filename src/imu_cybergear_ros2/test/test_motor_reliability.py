import math
import threading

import pytest

from imu_cybergear_ros2.controller_state import ControllerState, StateManager
from imu_cybergear_ros2.cybergear_driver import (
    SDO_RUN_MODE,
    SDO_TARGET_POS,
    SDO_TARGET_SPEED,
)
from imu_cybergear_ros2.motor_manager import MotorManager
from imu_cybergear_ros2.motor_motion import MotionParameters, MotionSource
from imu_cybergear_ros2.safety_monitor import SafetyMonitor

from .fake_motor_driver import FakeMotorDriver, event_blocker


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warn(self, message):
        self.messages.append(("warn", message))

    def error(self, message):
        self.messages.append(("error", message))


class FakeNode:
    def __init__(self, driver=None, motor_ids=(4, 3, 2, 1)):
        self._motor_ids = list(motor_ids)
        self._limits = {mid: (-1.0, 1.0) for mid in self._motor_ids}
        self._lock = threading.RLock()
        self._driver_io_lock = threading.Lock()
        self._current_targets = {mid: 0.0 for mid in self._motor_ids}
        self._desired_targets = dict(self._current_targets)
        self._current_speeds = {mid: 10.0 for mid in self._motor_ids}
        self._last_target_change_time = {mid: 0.0 for mid in self._motor_ids}
        self._command_failure_counts = {mid: 0 for mid in self._motor_ids}
        self._command_fault_active = False
        self._motor_protection_flags = {mid: False for mid in self._motor_ids}
        self._default_speed = 10.0
        self._manual_speed_min = 0.5
        self._manual_speed_max = 20.0
        self._manual_speed_step = 0.5
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
        self._driver = driver or FakeMotorDriver()
        self._is_active = True
        self._running = True
        self._init_complete = False
        self._logger = Logger()
        self._sleep = lambda _seconds: None
        self._motor_status_pub = None
        self._motor_configs = []
        self._latest_roll = 0.0
        self._latest_pitch = 0.0
        self._selected_motor_id = self._motor_ids[0]
        self._motor_feedback = {}
        self.timers = []
        self.destroyed_timers = []

    def get_logger(self):
        return self._logger

    def create_timer(self, period, callback):
        timer = (period, callback)
        self.timers.append(timer)
        return timer

    def destroy_timer(self, timer):
        self.destroyed_timers.append(timer)
        return True


def build_system(driver=None, motor_ids=(4, 3, 2, 1)):
    node = FakeNode(driver=driver, motor_ids=motor_ids)
    state = StateManager(node)
    manager = MotorManager(node, state)
    state._state_change_callback = manager.on_control_state_changed
    state.transition_to(ControllerState.MANUAL_RUNNING)
    return node, state, manager


def calls(driver, operation, index=None):
    return [
        call
        for call in driver.calls
        if call[0] == operation and (index is None or call[2] == index)
    ]


def test_position_commits_only_after_success_and_uses_clamped_command(monkeypatch):
    node, _state, manager = build_system()
    monkeypatch.setattr(
        "imu_cybergear_ros2.motor_manager.time.monotonic", lambda: 12.5
    )
    assert manager.write_command_target(4, 2.0)
    assert node._current_targets[4] == 1.0
    assert node._last_target_change_time[4] == 12.5
    assert calls(node._driver, "write_sdo_float", SDO_TARGET_POS)[-1][3] == 1.0


def test_non_finite_position_is_rejected_without_driver_access():
    node, _state, manager = build_system()
    assert not manager.write_command_target(4, math.nan)
    assert calls(node._driver, "write_sdo_float", SDO_TARGET_POS) == []
    assert node._current_targets[4] == 0.0


def test_partial_position_batch_commits_prefix_then_enters_error_and_stops_all():
    driver = FakeMotorDriver(
        failures={("write_sdo_float", 3, SDO_TARGET_POS)}
    )
    node, state, manager = build_system(driver)
    node._current_targets = {mid: 0.4 for mid in node._motor_ids}
    node._desired_targets = {mid: 0.0 for mid in node._motor_ids}
    manager._motion_source = MotionSource.HOME

    manager._motion_tick(now=1.0)
    manager._motion_tick(now=1.05)

    writes = calls(driver, "write_sdo_float", SDO_TARGET_POS)
    assert [call[1] for call in writes] == [4, 3]
    assert node._current_targets == {4: 0.2, 3: 0.4, 2: 0.4, 1: 0.4}
    assert node._desired_targets == node._current_targets
    assert manager.motion_source == MotionSource.IDLE
    assert state.state == ControllerState.ERROR
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3, 2, 1]
    assert not any("自动归零完成" in message for _level, message in node._logger.messages)


def test_position_failure_preserves_timestamp_and_stop_failure_does_not_abort_batch():
    driver = FakeMotorDriver(
        failures={
            ("write_sdo_float", 4, SDO_TARGET_POS),
            ("stop_motor", 3, None),
        }
    )
    node, state, manager = build_system(driver)
    node._current_targets[4] = 0.1
    node._desired_targets[4] = 0.8
    node._last_target_change_time[4] = 7.0
    manager._motion_source = MotionSource.MANUAL

    assert not manager.write_command_target(4, 0.2)
    assert node._current_targets[4] == 0.1
    assert node._last_target_change_time[4] == 7.0
    assert node._desired_targets == node._current_targets
    assert state.state == ControllerState.ERROR
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3, 2, 1]
    assert any("停止电机 ID3 失败" in message for level, message in node._logger.messages if level == "error")


def test_speed_commits_only_after_success_and_clamps(monkeypatch):
    node, _state, manager = build_system()
    monkeypatch.setattr(
        "imu_cybergear_ros2.motor_manager.time.monotonic", lambda: 9.0
    )
    assert manager.change_motor_speed(4, 99.0)
    assert node._current_speeds[4] == 20.0
    assert node._last_target_change_time[4] == 9.0
    assert calls(node._driver, "write_sdo_float", SDO_TARGET_SPEED)[-1][3] == 20.0
    assert any("10.00 -> 20.00" in message for _level, message in node._logger.messages)


def test_speed_failure_keeps_old_value_and_timestamp_and_reports_old_value():
    driver = FakeMotorDriver(
        failures={("write_sdo_float", 4, SDO_TARGET_SPEED)}
    )
    node, state, manager = build_system(driver)
    node._last_target_change_time[4] = 6.0
    assert not manager.change_motor_speed(4, 0.5)
    assert node._current_speeds[4] == 10.0
    assert node._last_target_change_time[4] == 6.0
    assert state.state == ControllerState.ERROR
    assert any("仍保持 10.00" in message for _level, message in node._logger.messages)


def test_initialization_success_uses_required_order_and_commits_all_state():
    driver = FakeMotorDriver()
    node = FakeNode(driver=driver, motor_ids=(4, 3))
    node._current_targets = {}
    node._desired_targets = {}
    node._current_speeds = {}
    state = StateManager(node)
    manager = MotorManager(node, state)
    state._state_change_callback = manager.on_control_state_changed

    assert manager.connect_and_init_motors()
    for mid in (4, 3):
        per_motor = [
            (operation, index)
            for operation, motor_id, index, _value in driver.calls
            if motor_id == mid
        ]
        assert per_motor == [
            ("write_sdo_int", SDO_RUN_MODE),
            ("write_sdo_float", SDO_TARGET_SPEED),
            ("write_sdo_float", SDO_TARGET_POS),
            ("enter_control_mode", None),
        ]
    assert node._init_complete
    assert state.state == ControllerState.MANUAL_RUNNING
    assert node._current_targets == {4: 0.0, 3: 0.0}
    assert node._desired_targets == node._current_targets
    assert node._current_speeds == {4: 10.0, 3: 10.0}
    assert manager.init_successful_motor_ids == (4, 3)


@pytest.mark.parametrize(
    ("failure", "expected_touched", "expected_stage"),
    [
        (("write_sdo_int", 4, SDO_RUN_MODE), (4,), "run_mode"),
        (("write_sdo_float", 3, SDO_TARGET_SPEED), (4, 3), "target_speed"),
        (("write_sdo_float", 3, SDO_TARGET_POS), (4, 3), "target_position"),
        (("enter_control_mode", 1, None), (4, 3, 2, 1), "enter_control_mode"),
    ],
)
def test_initialization_failure_tracks_exact_stage_without_false_completion(
    failure, expected_touched, expected_stage
):
    driver = FakeMotorDriver(failures={failure})
    node = FakeNode(driver=driver)
    node._current_targets = {}
    node._desired_targets = {}
    node._current_speeds = {}
    state = StateManager(node)
    manager = MotorManager(node, state)
    state._state_change_callback = manager.on_control_state_changed

    assert not manager.connect_and_init_motors()
    assert not node._init_complete
    assert state.state == ControllerState.ERROR
    assert manager.init_touched_motor_ids == expected_touched
    assert expected_stage in manager.current_init_stage
    assert manager.motion_source == MotionSource.IDLE


def test_connect_failure_does_not_touch_any_motor():
    driver = FakeMotorDriver(connect_result=False)
    node = FakeNode(driver=driver)
    state = StateManager(node)
    manager = MotorManager(node, state)
    assert not manager.connect_and_init_motors()
    assert manager.init_touched_motor_ids == ()
    assert calls(driver, "write_sdo_int") == []


def test_recovery_uses_last_successful_targets_not_desired_and_rolls_back_partial():
    driver = FakeMotorDriver(failures={("enter_control_mode", 3, None)})
    node, state, manager = build_system(driver, motor_ids=(4, 3))
    state.transition_to(ControllerState.EMERGENCY_STOP)
    node._current_targets = {4: 0.2, 3: -0.3}
    node._desired_targets = {4: 0.9, 3: 0.8}

    assert not manager.hold_current_targets_and_recover()
    position_values = {
        call[1]: call[3]
        for call in calls(driver, "write_sdo_float", SDO_TARGET_POS)
    }
    assert position_values == {4: 0.2, 3: -0.3}
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3]
    assert state.state == ControllerState.EMERGENCY_STOP
    assert manager.motion_source == MotionSource.IDLE


def test_mechanical_zero_only_commits_motor_after_target_and_enter_succeed():
    driver = FakeMotorDriver(failures={("enter_control_mode", 3, None)})
    node, state, manager = build_system(driver, motor_ids=(4, 3))
    node._current_targets = {4: 0.4, 3: -0.3}
    node._desired_targets = dict(node._current_targets)

    assert not manager.set_all_motor_zero_reference()
    assert node._current_targets == {4: 0.0, 3: -0.3}
    assert state.state == ControllerState.ERROR
    # 首轮停机和失败后的回滚都必须覆盖全部电机。
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3, 4, 3]


def test_driver_write_does_not_hold_node_state_lock():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("write_sdo_float", 4, SDO_TARGET_POS): (entered, release)}
    )
    node, _state, manager = build_system(driver)
    result = []
    worker = threading.Thread(
        target=lambda: result.append(manager.write_command_target(4, 0.2))
    )
    worker.start()
    assert entered.wait(timeout=1.0)
    assert node._lock.acquire(timeout=0.2)
    node._lock.release()
    release.set()
    worker.join(timeout=1.0)
    assert result == [True]


def test_normal_driver_writes_are_serialized_by_io_lock():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("write_sdo_float", 4, SDO_TARGET_POS): (entered, release)}
    )
    node, _state, manager = build_system(driver)
    first = threading.Thread(target=manager.write_command_target, args=(4, 0.2))
    second = threading.Thread(target=manager.write_command_target, args=(3, 0.2))
    first.start()
    assert entered.wait(timeout=1.0)
    second.start()
    assert calls(driver, "write_sdo_float", SDO_TARGET_POS) == [
        ("write_sdo_float", 4, SDO_TARGET_POS, 0.2)
    ]
    release.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)
    assert driver.max_active_calls == 1


def test_emergency_stop_gets_io_lock_after_current_single_write():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("write_sdo_float", 4, SDO_TARGET_POS): (entered, release)}
    )
    node, state, manager = build_system(driver, motor_ids=(4, 3))
    monitor = SafetyMonitor(node, state, manager)
    writer = threading.Thread(target=manager.write_command_target, args=(4, 0.2))
    stopper_started = threading.Event()

    def stop():
        stopper_started.set()
        monitor.emergency_stop()

    writer.start()
    assert entered.wait(timeout=1.0)
    stopper = threading.Thread(target=stop)
    stopper.start()
    assert stopper_started.wait(timeout=1.0)
    assert calls(driver, "stop_motor") == []
    release.set()
    writer.join(timeout=1.0)
    stopper.join(timeout=1.0)
    operations = [call[0] for call in driver.calls]
    assert operations.index("write_sdo_float") < operations.index("stop_motor")
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3]
    assert state.state == ControllerState.EMERGENCY_STOP
