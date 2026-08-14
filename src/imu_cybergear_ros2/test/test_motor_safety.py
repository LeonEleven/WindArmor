import math
import threading
from types import SimpleNamespace

import pytest

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.cybergear_driver import MotorStatus, SDO_TARGET_POS
from imu_cybergear_ros2.motor_motion import MotionSource
from imu_cybergear_ros2.safety_monitor import SafetyMonitor

from .fake_motor_driver import FakeMotorDriver, event_blocker
from .test_motor_reliability import build_system, calls


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def feedback(motor_id=4, **overrides):
    values = dict(
        motor_id=motor_id,
        position_rad=0.0,
        speed_rad_s=0.0,
        torque_nm=0.0,
        temperature=25.0,
        mode=2,
        fault_flags=0,
        timestamp=1.0,
    )
    values.update(overrides)
    return MotorStatus(**values)


def system_with_monitor(driver=None, motor_ids=(4, 3, 2, 1), clock=None):
    node, state, manager = build_system(driver=driver, motor_ids=motor_ids)
    node._warning_throttle_sec = 2.0
    node._motor_temp_limit_deg_c = 80.0
    node._motor_temp_critical_deg_c = 90.0
    node._motor_invalid_feedback_limit = 3
    node._motor_feedback_timeout_sec = 0.0
    node._motor_feedback_startup_grace_sec = 3.0
    node._motor_feedback_check_rate_hz = 10.0
    node._motor_temperature_warning_flags = {mid: False for mid in motor_ids}
    node._motor_safety_fault_active = False
    node._motor_safety_fault_snapshot = None
    monitor = SafetyMonitor(
        node, state, manager, monotonic_fn=clock or FakeClock(10.0)
    )
    node._safety = monitor
    return node, state, manager, monitor


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (0x01, TransitionReason.MOTOR_FAULT_UNDERVOLTAGE),
        (0x02, TransitionReason.MOTOR_OVERCURRENT_FAULT),
        (0x04, TransitionReason.MOTOR_OVERTEMPERATURE_FAULT),
        (0x08, TransitionReason.MOTOR_FAULT_ENCODER),
        (0x10, TransitionReason.MOTOR_FAULT_ENCODER),
        (0x20, TransitionReason.MOTOR_FAULT_UNCALIBRATED),
        (0x03, TransitionReason.MOTOR_FAULT_MULTIPLE),
    ],
)
def test_each_firmware_fault_stops_all_enters_error_and_latches(flags, reason):
    node, state, _manager, monitor = system_with_monitor()
    monitor.on_motor_feedback(feedback(fault_flags=flags))
    assert [call[1] for call in calls(node._driver, "stop_motor")] == [4, 3, 2, 1]
    assert state.state is ControllerState.ERROR
    assert state.last_transition.reason is reason
    assert state.last_transition.source is TransitionSource.DRIVER_FEEDBACK
    assert node._motor_safety_fault_active
    assert node._motor_protection_flags[4]
    first_snapshot = node._motor_safety_fault_snapshot

    monitor.on_motor_feedback(feedback(fault_flags=0))
    assert node._motor_safety_fault_snapshot is first_snapshot
    assert node._motor_protection_flags[4]
    assert [call[1] for call in calls(node._driver, "stop_motor")] == [4, 3, 2, 1]


def test_unknown_and_invalid_feedback_do_not_replace_last_valid_feedback():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    valid = feedback(position_rad=0.25)
    monitor.on_motor_feedback(valid)
    monitor.on_motor_feedback(feedback(99, position_rad=0.75))
    assert set(node._motor_feedback) == {4}
    assert node._motor_feedback[4] is valid

    invalid = feedback(position_rad=math.nan)
    monitor.on_motor_feedback(invalid)
    monitor.on_motor_feedback(invalid)
    assert node._motor_feedback[4] is valid
    assert state.state is ControllerState.MANUAL_RUNNING
    monitor.on_motor_feedback(invalid)
    assert node._motor_feedback[4] is valid
    assert state.state is ControllerState.ERROR
    assert state.last_transition.reason is TransitionReason.MOTOR_INVALID_FEEDBACK


def test_inactive_configured_node_still_ingests_valid_measured_feedback():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    node._is_active = False
    measured = feedback(4, position_rad=0.37, speed_rad_s=-0.2, torque_nm=0.6)
    monitor.on_motor_feedback(measured)
    assert state.state is ControllerState.MANUAL_RUNNING
    assert node._motor_feedback[4] is measured
    assert node._motor_feedback_received_at[4] == pytest.approx(10.0)


def test_startup_hold_feedback_has_no_false_position_error_warning():
    node, _state, _manager, monitor = system_with_monitor(motor_ids=(4,))
    node._init_complete = True
    node._current_targets = {4: 0.85}
    node._desired_targets = {4: 0.85}
    node._last_target_change_time = {4: 0.0}
    node._logger.messages.clear()

    monitor.on_motor_feedback(feedback(4, position_rad=0.85))

    assert not any(
        "位置偏差过大" in message
        for level, message in node._logger.messages
        if level == "warn"
    )


def test_initializing_fault_frame_is_cached_then_trips_fail_closed():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    node._is_active = False
    state._state = ControllerState.INITIALIZING
    fault = feedback(4, position_rad=0.42, fault_flags=0x02)
    monitor.on_motor_feedback(fault)
    assert node._motor_feedback[4] is fault
    assert node._motor_safety_fault_active
    assert state.state is ControllerState.ERROR
    assert [call[1] for call in calls(node._driver, "stop_motor")] == [4, 3]


def test_initializing_invalid_feedback_never_populates_cache_and_still_trips():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4,))
    node._is_active = False
    state._state = ControllerState.INITIALIZING
    invalid = feedback(4, position_rad=math.nan)
    for _ in range(3):
        monitor.on_motor_feedback(invalid)
    assert node._motor_feedback == {}
    assert node._motor_safety_fault_active
    assert state.state is ControllerState.ERROR


def test_valid_frame_clears_invalid_count_only_before_latch():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4,))
    bad = feedback(position_rad=math.nan)
    monitor.on_motor_feedback(bad)
    monitor.on_motor_feedback(bad)
    monitor.on_motor_feedback(feedback())
    assert monitor.health_core.invalid_counts[4] == 0
    assert state.state is ControllerState.MANUAL_RUNNING
    for _ in range(3):
        monitor.on_motor_feedback(bad)
    monitor.on_motor_feedback(feedback())
    assert state.state is ControllerState.ERROR
    assert node._motor_safety_fault_active


def test_temperature_warning_only_logs_and_critical_trips_without_speed_change():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    speeds = dict(node._current_speeds)
    monitor.on_motor_feedback(feedback(temperature=80.0))
    assert state.state is ControllerState.MANUAL_RUNNING
    assert calls(node._driver, "stop_motor") == []
    assert node._motor_temperature_warning_flags[4]
    assert node._current_speeds == speeds
    assert any("不自动降速" in message for level, message in node._logger.messages if level == "warn")

    monitor.on_motor_feedback(feedback(temperature=90.0))
    assert state.state is ControllerState.ERROR
    assert [call[1] for call in calls(node._driver, "stop_motor")] == [4, 3]
    assert state.last_transition.reason is TransitionReason.MOTOR_CRITICAL_TEMPERATURE
    monitor.on_motor_feedback(feedback(temperature=20.0))
    assert state.state is ControllerState.ERROR
    assert node._motor_protection_flags[4]
    assert node._current_speeds == speeds


def test_stop_failure_does_not_abort_batch_and_motion_and_commands_stay_blocked():
    driver = FakeMotorDriver(failures={("stop_motor", 3, None)})
    node, state, manager, monitor = system_with_monitor(driver=driver)
    node._current_targets = {mid: 0.2 for mid in node._motor_ids}
    node._desired_targets = {mid: 0.8 for mid in node._motor_ids}
    manager._motion_source = MotionSource.HOME
    monitor.on_motor_feedback(feedback(fault_flags=0x02))
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3, 2, 1]
    assert node._desired_targets == node._current_targets
    assert manager.motion_source is MotionSource.IDLE
    assert state.state is ControllerState.ERROR
    assert not manager.write_command_target(4, 0.3)
    assert not manager.set_auto_targets({mid: 0.0 for mid in node._motor_ids})
    assert not manager.go_all_to_zero()


def test_two_concurrent_faults_execute_one_stop_batch_without_deadlock():
    node, state, _manager, monitor = system_with_monitor()
    barrier = threading.Barrier(3)

    def report(motor_id, flags):
        barrier.wait()
        monitor.on_motor_feedback(feedback(motor_id, fault_flags=flags))

    workers = [
        threading.Thread(target=report, args=(4, 0x01)),
        threading.Thread(target=report, args=(3, 0x02)),
    ]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=1.0)
        assert not worker.is_alive()
    assert len(calls(node._driver, "stop_motor")) == 4
    assert state.state is ControllerState.ERROR


def test_feedback_fault_and_emergency_stop_share_one_main_stop_batch():
    node, state, _manager, monitor = system_with_monitor()
    barrier = threading.Barrier(3)

    def emergency():
        barrier.wait()
        monitor.emergency_stop(
            reason=TransitionReason.USER_ESTOP,
            source=TransitionSource.KEYBOARD,
        )

    def critical_feedback():
        barrier.wait()
        monitor.on_motor_feedback(feedback(3, temperature=90.0))

    workers = [threading.Thread(target=emergency), threading.Thread(target=critical_feedback)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=1.0)
        assert not worker.is_alive()
    assert len(calls(node._driver, "stop_motor")) == 4
    assert state.state is ControllerState.ERROR
    assert node._motor_safety_fault_active


def test_fault_bit_and_critical_temperature_in_one_frame_trip_once():
    node, state, _manager, monitor = system_with_monitor()
    monitor.on_motor_feedback(feedback(fault_flags=0x02, temperature=95.0))
    assert len(calls(node._driver, "stop_motor")) == 4
    assert state.state is ControllerState.ERROR
    assert state.last_transition.reason is TransitionReason.MOTOR_OVERCURRENT_FAULT


def test_status_publisher_failure_cannot_suppress_safety_trip():
    node, state, _manager, monitor = system_with_monitor()

    class BrokenPublisher:
        def publish(self, _message):
            raise RuntimeError("injected publisher failure")

    node._motor_status_pub = BrokenPublisher()
    monitor.on_motor_feedback(feedback(fault_flags=0x01))
    assert state.state is ControllerState.ERROR
    assert len(calls(node._driver, "stop_motor")) == 4
    assert any(
        "发布电机反馈状态失败" in message
        for level, message in node._logger.messages
        if level == "error"
    )


def test_feedback_fault_waits_for_inflight_write_then_blocks_later_writes():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("write_sdo_float", 4, SDO_TARGET_POS): (entered, release)}
    )
    node, state, manager, monitor = system_with_monitor(driver=driver, motor_ids=(4, 3))
    writer = threading.Thread(target=manager.write_command_target, args=(4, 0.2))
    fault = threading.Thread(
        target=monitor.on_motor_feedback,
        args=(feedback(3, temperature=90.0),),
    )
    writer.start()
    assert entered.wait(timeout=1.0)
    fault.start()
    assert calls(driver, "stop_motor") == []
    release.set()
    writer.join(timeout=1.0)
    fault.join(timeout=1.0)
    assert not writer.is_alive() and not fault.is_alive()
    assert state.state is ControllerState.ERROR
    assert node._desired_targets == node._current_targets
    assert [call[1] for call in calls(driver, "stop_motor")] == [4, 3]
    assert not manager.write_command_target(3, 0.2)


def test_serious_feedback_during_estop_changes_to_error_and_prevents_recovery():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    assert monitor.emergency_stop(
        reason=TransitionReason.USER_ESTOP,
        source=TransitionSource.KEYBOARD,
    )
    assert state.state is ControllerState.EMERGENCY_STOP
    monitor.on_motor_feedback(feedback(fault_flags=0x04))
    assert state.state is ControllerState.ERROR
    assert not monitor.recover_from_emergency_stop(source=TransitionSource.SERVICE)
    response = SimpleNamespace(success=True, message="")
    monitor.on_enable_motor_service(SimpleNamespace(data=True), response)
    assert not response.success
    assert "重新配置或重启" in response.message


def test_normal_estop_still_recovers_without_feedback_safety_latch():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    assert monitor.emergency_stop(
        reason=TransitionReason.USER_ESTOP,
        source=TransitionSource.KEYBOARD,
    )
    assert monitor.recover_from_emergency_stop(source=TransitionSource.SERVICE)
    assert state.state is ControllerState.MANUAL_RUNNING
    assert not node._motor_safety_fault_active


def test_normal_estop_does_not_clear_existing_protection_flags():
    node, state, _manager, monitor = system_with_monitor(motor_ids=(4, 3))
    node._motor_protection_flags[4] = True
    assert monitor.emergency_stop(
        reason=TransitionReason.USER_ESTOP,
        source=TransitionSource.KEYBOARD,
    )
    assert state.state is ControllerState.EMERGENCY_STOP
    assert node._motor_protection_flags[4]


def test_enabled_feedback_timeout_uses_local_fake_clock_and_is_idempotent():
    clock = FakeClock(0.0)
    node, state, _manager, _old_monitor = system_with_monitor(
        motor_ids=(4, 3), clock=clock
    )
    node._motor_feedback_timeout_sec = 1.0
    monitor = SafetyMonitor(node, state, node._safety._motor_mgr, monotonic_fn=clock)
    node._safety = monitor
    monitor.start_feedback_monitor()
    assert monitor.feedback_timer is not None
    clock.now = 2.9
    monitor._feedback_watchdog_check()
    assert state.state is ControllerState.MANUAL_RUNNING
    monitor.on_motor_feedback(feedback(4, timestamp=999999.0))
    clock.now = 3.0
    monitor._feedback_watchdog_check()
    assert state.state is ControllerState.ERROR  # ID3 never produced a valid frame
    assert state.last_transition.reason is TransitionReason.MOTOR_FEEDBACK_TIMEOUT
    assert state.last_transition.source is TransitionSource.WATCHDOG
    stop_count = len(calls(node._driver, "stop_motor"))
    clock.now = 100.0
    monitor._feedback_watchdog_check()
    assert len(calls(node._driver, "stop_motor")) == stop_count
    monitor.stop_feedback_monitor()
    assert monitor.feedback_timer is None
    assert node.destroyed_timers
