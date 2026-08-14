import os
import threading

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.parameter import Parameter
from std_srvs.srv import SetBool

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.cybergear_driver import MotorStatus, SDO_TARGET_POS
from imu_cybergear_ros2.imu_motor_controller_node import ImuMotorControllerNode
from imu_cybergear_ros2.motor_motion import MotionSource
from imu_cybergear_ros2.transport_recovery import (
    CyberGearTransportError,
    TransportEvent,
    TransportEventType,
    TransportRecoveryState,
)

from .fake_motor_driver import FakeMotorDriver, event_blocker


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


class DriverFactory:
    def __init__(self, drivers):
        self.drivers = list(drivers)
        self.created = []

    def __call__(self, **_kwargs):
        driver = self.drivers[len(self.created)]
        self.created.append(driver)
        return driver


class FaultOnInitialConnectDriver(FakeMotorDriver):
    def connect_with_retry(self, **kwargs):
        result = super().connect_with_retry(**kwargs)
        self.emit_transport_event(transport_event(self))
        return result


def configure_node(driver, *, parameters=(), factory=None):
    node = ImuMotorControllerNode(
        driver_factory=factory or DriverFactory([driver]),
        sleep_fn=lambda _seconds: None,
    )
    values = [Parameter("enable_keyboard", value=False), *parameters]
    assert all(result.successful for result in node.set_parameters(values))
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    assert driver.connection_generation == 1
    return node


def transport_event(
    driver,
    *,
    event_type=TransportEventType.READ_ERROR,
    operation="read",
    generation=None,
):
    error = OSError(f"injected {operation} disconnect")
    return TransportEvent(
        event_type=event_type,
        backend="fake",
        operation=operation,
        message=str(error),
        monotonic_timestamp=1.0,
        connection_generation=(
            driver.connection_generation if generation is None else generation
        ),
        exception=error,
    )


def capture_worker(coordinator):
    with coordinator._lock:
        return coordinator._worker


def join_worker(worker):
    assert worker is not None
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_runtime_reconnect_success_restores_transport_only_and_keeps_error():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        reconnect_results=[True],
        blockers={("connect_once", None, None): (entered, release)},
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        baseline_init_calls = {
            operation: sum(1 for call in driver.calls if call[0] == operation)
            for operation in (
                "write_sdo_int",
                "write_sdo_float",
                "enter_control_mode",
                "set_zero",
            )
        }
        with node._lock:
            node._current_targets = {mid: 0.2 for mid in node._motor_ids}
            node._desired_targets = {mid: 0.8 for mid in node._motor_ids}
            node._motor_mgr._motion_source = MotionSource.MANUAL

        event = transport_event(driver)
        driver.emit_transport_event(event)
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert node._state_mgr.state is ControllerState.ERROR
        assert node._motor_mgr.motion_source is MotionSource.IDLE
        assert node._desired_targets == node._current_targets
        assert not node._init_complete
        assert node._transport_fault_snapshot is event
        release.set()
        join_worker(worker)

        snapshot = node._transport_recovery.snapshot()
        assert snapshot.state is TransportRecoveryState.RECONNECTED_LOCKED
        assert driver.connection_generation == 2
        assert node._state_mgr.state is ControllerState.ERROR
        assert node._motor_mgr.motion_source is MotionSource.IDLE
        assert [call[1] for call in driver.calls if call[0] == "stop_motor"] == [
            4,
            3,
            2,
            1,
        ]
        for operation, count in baseline_init_calls.items():
            assert sum(1 for call in driver.calls if call[0] == operation) == count
        with pytest.raises(ValueError):
            node._motor_mgr.set_manual_targets({mid: 0.0 for mid in node._motor_ids})
        assert not node._motor_mgr.set_auto_targets(
            {mid: 0.0 for mid in node._motor_ids}
        )
        assert not node._motor_mgr.go_all_to_zero()
        request = SetBool.Request()
        request.data = True
        response = node._safety.on_enable_motor_service(
            request, SetBool.Response()
        )
        assert not response.success
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_transport_fault_during_initial_configure_rolls_back_without_runtime_reconnect():
    driver = FaultOnInitialConnectDriver()
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert not any(
            call[0] in {"write_sdo_int", "write_sdo_float", "enter_control_mode"}
            for call in driver.calls
        )
        assert not any(call[0] == "connect_once" for call in driver.calls)
        assert driver.transport_event_callback is None
        assert driver.close_attempts == 1
    finally:
        node.destroy_node()


def test_transport_fault_before_startup_feedback_never_writes_position_target():
    driver = FakeMotorDriver(auto_feedback=False)
    emitted = False

    def disconnect_after_first_request(_seconds):
        nonlocal emitted
        if not emitted:
            emitted = True
            driver.emit_transport_event(transport_event(driver))

    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]),
        sleep_fn=disconnect_after_first_request,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert not any(
            operation == "write_sdo_float" and index == SDO_TARGET_POS
            for operation, _motor_id, index, _value in driver.calls
        )
        assert not any(call[0] == "connect_once" for call in driver.calls)
        assert [
            call[1] for call in driver.calls if call[0] == "stop_motor"
        ] == [4]
        assert driver.transport_event_callback is None
    finally:
        node.destroy_node()


def test_reconnect_disabled_closes_without_any_connect_attempt():
    close_entered, release_close = event_blocker()
    driver = FakeMotorDriver(
        blockers={("close", None, None): (close_entered, release_close)}
    )
    node = configure_node(
        driver,
        parameters=[Parameter("reconnect_on_disconnect", value=False)],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_transport_event(transport_event(driver))
        assert close_entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert node._state_mgr.state is ControllerState.ERROR
        assert not any(call[0] == "connect_once" for call in driver.calls)
        release_close.set()
        join_worker(worker)
        assert (
            node._transport_recovery.snapshot().state
            is TransportRecoveryState.FAULT_LATCHED
        )
        assert not any(call[0] == "connect_once" for call in driver.calls)
    finally:
        release_close.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_runtime_reconnect_exhaustion_keeps_controller_error_and_stops_retrying():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        reconnect_results=[False, False, True],
        blockers={("connect_once", None, None): (entered, release)},
    )
    node = configure_node(
        driver,
        parameters=[
            Parameter("reconnect_max_attempts", value=2),
            Parameter("reconnect_initial_delay_sec", value=0.0),
            Parameter("reconnect_max_delay_sec", value=0.0),
        ],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_transport_event(transport_event(driver))
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        release.set()
        join_worker(worker)
        assert node._transport_recovery.snapshot().state is TransportRecoveryState.FAILED
        assert node._state_mgr.state is ControllerState.ERROR
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 2
        node._on_driver_transport_event(transport_event(driver))
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 2
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


@pytest.mark.parametrize("source", ["manual", "auto", "home"])
def test_transport_fault_discards_each_motion_source_and_never_restores_old_targets(
    source,
):
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("connect_once", None, None): (entered, release)}
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        if source == "auto":
            node._state_mgr.transition_to(
                ControllerState.AUTO_RUNNING,
                reason=TransitionReason.USER_MODE_TOGGLE,
                source=TransitionSource.KEYBOARD,
            )
            assert node._motor_mgr.set_auto_targets(
                {mid: 0.8 for mid in node._motor_ids}
            )
        elif source == "home":
            with node._lock:
                node._current_targets = {mid: 0.4 for mid in node._motor_ids}
                node._desired_targets = dict(node._current_targets)
            assert node._motor_mgr.go_all_to_zero()
        else:
            node._motor_mgr.set_manual_targets(
                {mid: 0.8 for mid in node._motor_ids}
            )

        driver.emit_transport_event(transport_event(driver))
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert node._desired_targets == node._current_targets
        assert node._motor_mgr.motion_source is MotionSource.IDLE
        release.set()
        join_worker(worker)
        assert node._state_mgr.state is ControllerState.ERROR
        assert node._desired_targets == node._current_targets
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_old_generation_event_after_reconnect_is_ignored_without_new_worker():
    driver = FakeMotorDriver(reconnect_results=[True])
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        first = transport_event(driver)
        driver.emit_transport_event(first)
        worker = capture_worker(node._transport_recovery)
        if worker is not None:
            join_worker(worker)
        assert driver.connection_generation == 2
        calls_before = list(driver.calls)
        node._on_driver_transport_event(
            transport_event(driver, generation=1, operation="late_read")
        )
        assert driver.calls == calls_before
        assert (
            node._transport_recovery.snapshot().state
            is TransportRecoveryState.RECONNECTED_LOCKED
        )
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_reader_and_command_transport_faults_share_one_latch_stop_and_worker():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("connect_once", None, None): (entered, release)}
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        read_event = transport_event(driver)
        write_event = transport_event(
            driver,
            event_type=TransportEventType.WRITE_ERROR,
            operation="write",
        )
        barrier = threading.Barrier(3)

        def reader_fault():
            barrier.wait()
            node._on_driver_transport_event(read_event)

        def command_fault():
            barrier.wait()
            node._motor_mgr._handle_command_failure(
                4,
                "position",
                CyberGearTransportError("write failed", event=write_event),
            )

        workers = [
            threading.Thread(target=reader_fault),
            threading.Thread(target=command_fault),
        ]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=1.0)
            assert not worker.is_alive()
        assert entered.wait(timeout=1.0)
        recovery_worker = capture_worker(node._transport_recovery)
        first_snapshot = node._transport_fault_snapshot
        node._on_driver_transport_event(read_event)
        assert node._transport_fault_snapshot is first_snapshot
        release.set()
        join_worker(recovery_worker)
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 1
        assert [call[1] for call in driver.calls if call[0] == "stop_motor"] == [
            4,
            3,
            2,
            1,
        ]
        assert node._state_mgr.state is ControllerState.ERROR
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_cleanup_cancels_backoff_clears_callbacks_and_allows_fresh_configure():
    reconnect_entered, release_reconnect = event_blocker()
    first = FakeMotorDriver(
        reconnect_results=[False, True],
        blockers={
            ("connect_once", None, None): (reconnect_entered, release_reconnect)
        },
    )
    second = FakeMotorDriver()
    factory = DriverFactory([first, second])
    node = configure_node(
        first,
        factory=factory,
        parameters=[
            Parameter("reconnect_initial_delay_sec", value=10.0),
            Parameter("reconnect_max_delay_sec", value=10.0),
        ],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        first.emit_transport_event(transport_event(first))
        assert reconnect_entered.wait(timeout=1.0)
        release_reconnect.set()
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert sum(1 for call in first.calls if call[0] == "connect_once") == 1
        assert first.feedback_callback is None
        assert first.feedback_error_callback is None
        assert first.transport_event_callback is None

        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert not node._transport_fault_active
        assert node._transport_fault_snapshot is None
        assert node._transport_recovery.snapshot().state is TransportRecoveryState.IDLE
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert second.transport_event_callback is None
    finally:
        release_reconnect.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_shutdown_cancels_reconnect_worker():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        reconnect_results=[False, True],
        blockers={("connect_once", None, None): (entered, release)},
    )
    node = configure_node(
        driver,
        parameters=[
            Parameter("reconnect_initial_delay_sec", value=10.0),
            Parameter("reconnect_max_delay_sec", value=10.0),
        ],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_transport_event(transport_event(driver))
        assert entered.wait(timeout=1.0)
        release.set()
        assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 1
        assert driver.transport_event_callback is None
    finally:
        release.set()
        node.destroy_node()


def test_deactivate_cancels_reconnect_and_reactivate_does_not_resume_it():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        reconnect_results=[False, True],
        blockers={("connect_once", None, None): (entered, release)},
    )
    node = configure_node(
        driver,
        parameters=[
            Parameter("reconnect_initial_delay_sec", value=10.0),
            Parameter("reconnect_max_delay_sec", value=10.0),
        ],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_transport_event(transport_event(driver))
        assert entered.wait(timeout=1.0)
        release.set()
        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 1
        assert node._state_mgr.state is ControllerState.ERROR
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert sum(1 for call in driver.calls if call[0] == "connect_once") == 1
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_actual_runtime_write_transport_error_reaches_controller_and_recovery():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("connect_once", None, None): (entered, release)}
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        event = transport_event(
            driver,
            event_type=TransportEventType.WRITE_ERROR,
            operation="write",
        )

        def fail_write(_motor_id, _index, _value):
            driver.emit_transport_event(event)
            raise CyberGearTransportError("injected write disconnect", event=event)

        driver.write_sdo_float = fail_write
        assert not node._motor_mgr.write_command_target(4, 0.2)
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert node._transport_fault_active
        assert node._command_fault_active
        assert node._state_mgr.state is ControllerState.ERROR
        release.set()
        join_worker(worker)
        assert [call[1] for call in driver.calls if call[0] == "stop_motor"] == [
            4,
            3,
            2,
            1,
        ]
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_non_transport_command_error_does_not_start_reconnect():
    driver = FakeMotorDriver()
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS

        def fail_write(_motor_id, _index, _value):
            raise ValueError("injected non-transport driver error")

        driver.write_sdo_float = fail_write
        assert not node._motor_mgr.write_command_target(4, 0.2)
        assert node._state_mgr.state is ControllerState.ERROR
        assert not node._transport_fault_active
        assert node._transport_recovery.snapshot().state is TransportRecoveryState.IDLE
        assert not any(call[0] == "connect_once" for call in driver.calls)
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_transport_fault_during_emergency_stop_moves_to_error_and_cannot_recover():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("connect_once", None, None): (entered, release)}
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert node._safety.emergency_stop(
            reason=TransitionReason.USER_ESTOP,
            source=TransitionSource.KEYBOARD,
        )
        driver.emit_transport_event(transport_event(driver))
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert node._state_mgr.state is ControllerState.ERROR
        assert not node._safety.recover_from_emergency_stop(
            source=TransitionSource.SERVICE
        )
        release.set()
        join_worker(worker)
        assert [call[1] for call in driver.calls if call[0] == "stop_motor"] == [
            4,
            3,
            2,
            1,
        ]
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


def test_mechanical_zero_aborts_immediately_on_transport_failure():
    entered, release = event_blocker()
    driver = FakeMotorDriver(
        blockers={("connect_once", None, None): (entered, release)}
    )
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        baseline_writes = len(driver.calls)
        event = transport_event(
            driver,
            event_type=TransportEventType.WRITE_ERROR,
            operation="set_zero",
        )
        zero_calls = []

        def fail_zero(_motor_id):
            zero_calls.append(True)
            driver.emit_transport_event(event)
            raise CyberGearTransportError("set_zero disconnected", event=event)

        driver.set_zero = fail_zero
        assert not node._motor_mgr.set_all_motor_zero_reference()
        assert entered.wait(timeout=1.0)
        worker = capture_worker(node._transport_recovery)
        assert zero_calls == [True]
        assert node._state_mgr.state is ControllerState.ERROR
        assert not any(
            call[0] in {"write_sdo_int", "write_sdo_float", "enter_control_mode"}
            for call in driver.calls[baseline_writes:]
        )
        release.set()
        join_worker(worker)
    finally:
        release.set()
        node.on_cleanup(None)
        node.destroy_node()


@pytest.mark.parametrize(
    "status",
    [
        MotorStatus(motor_id=4, mode=2, timestamp=1.0, temperature=25.0, fault_flags=1),
        MotorStatus(motor_id=4, mode=2, timestamp=1.0, temperature=95.0, fault_flags=0),
    ],
)
def test_motor_fault_and_critical_temperature_do_not_start_transport_reconnect(status):
    driver = FakeMotorDriver()
    node = configure_node(driver)
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(status)
        assert node._state_mgr.state is ControllerState.ERROR
        assert node._transport_recovery.snapshot().state is TransportRecoveryState.IDLE
        assert not any(call[0] == "connect_once" for call in driver.calls)
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_feedback_timeout_enters_error_without_transport_reconnect():
    driver = FakeMotorDriver()
    node = configure_node(
        driver,
        parameters=[
            Parameter("motor_feedback_timeout_sec", value=1.0),
            Parameter("motor_feedback_startup_grace_sec", value=1.0),
        ],
    )
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        node._safety.health_core.activate(0.0)
        node._safety._monotonic = lambda: 2.0
        node._safety._feedback_watchdog_check()
        assert node._state_mgr.state is ControllerState.ERROR
        assert node._transport_recovery.snapshot().state is TransportRecoveryState.IDLE
        assert not any(call[0] == "connect_once" for call in driver.calls)
    finally:
        node.on_cleanup(None)
        node.destroy_node()
