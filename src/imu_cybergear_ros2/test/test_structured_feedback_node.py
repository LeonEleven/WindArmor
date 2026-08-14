import os
import time
from types import SimpleNamespace

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.cybergear_driver import (
    MotorStatus,
    SDO_TARGET_POS,
)
from imu_cybergear_ros2.imu_motor_controller_node import ImuMotorControllerNode

from .fake_motor_driver import FakeMotorDriver


class CapturePublisher:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def valid_status(motor_id=4, **overrides):
    values = dict(
        motor_id=motor_id,
        position_rad=0.25,
        speed_rad_s=-0.5,
        torque_nm=1.0,
        temperature=35.0,
        mode=2,
        fault_flags=0,
        timestamp=1.0,
    )
    values.update(overrides)
    return MotorStatus(**values)


class ConfigureFeedbackDriver(FakeMotorDriver):
    """Emit the documented type-2 response while configure writes loc_ref."""

    def write_sdo_float(self, motor_id, index, value):
        super().write_sdo_float(motor_id, index, value)
        if index == SDO_TARGET_POS:
            self.emit_feedback(valid_status(motor_id=motor_id, position_rad=value))


class MeasuredConfigureDriver(FakeMotorDriver):
    """Return each motor's measured position before its first loc_ref write."""

    def __init__(self, positions):
        super().__init__(feedback_positions=positions)


class FakeClock:
    def __init__(self, now=10.0):
        self.now = now

    def __call__(self):
        return self.now


def test_configure_feedback_response_populates_observation_cache() -> None:
    driver = ConfigureFeedbackDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert set(node._motor_feedback) == {4, 3, 2, 1}
        assert set(node._motor_feedback_received_at) == {4, 3, 2, 1}
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_cold_start_first_position_target_holds_each_measured_position() -> None:
    measured = {4: 0.85, 3: 0.74, 2: 0.91, 1: 0.42}
    driver = MeasuredConfigureDriver(measured)
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        first_targets = {}
        for operation, motor_id, index, value in driver.calls:
            if (
                operation == "write_sdo_float"
                and index == SDO_TARGET_POS
                and motor_id not in first_targets
            ):
                first_targets[motor_id] = value

        assert {
            motor_id: node._motor_feedback[motor_id].position_rad
            for motor_id in node._motor_ids
        } == measured
        assert first_targets == measured
        assert node._current_targets == measured
        assert node._desired_targets == measured
        assert {cfg.motor_id: cfg.sign for cfg in node._motor_configs} == {
            4: -1.0,
            3: 1.0,
            2: -1.0,
            1: 1.0,
        }

        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        call_index = len(driver.calls)
        node._motor_mgr._feedback_acquisition_tick()
        assert driver.calls[call_index:] == [
            ("write_sdo_float", motor_id, SDO_TARGET_POS, measured[motor_id])
            for motor_id in (4, 3, 2, 1)
        ]
        assert node._current_targets == measured
        assert node._desired_targets == measured
    finally:
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_cold_start_without_feedback_fails_closed_without_zero_fallback() -> None:
    driver = FakeMotorDriver(auto_feedback=False)
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert not any(
            operation == "write_sdo_float" and index == SDO_TARGET_POS
            for operation, _motor_id, index, _value in driver.calls
        )
        assert [
            motor_id
            for operation, motor_id, _index, _value in driver.calls
            if operation == "stop_motor"
        ] == [4]
        assert node._current_targets == {}
        assert node._desired_targets == {}
    finally:
        node.destroy_node()


@pytest.mark.parametrize(
    "status",
    [
        valid_status(motor_id=4, position_rad=float("nan")),
        valid_status(motor_id=4, position_rad=float("inf")),
        SimpleNamespace(
            motor_id=4,
            speed_rad_s=0.0,
            torque_nm=0.0,
            temperature=25.0,
            mode=0,
            fault_flags=0,
            timestamp=1.0,
        ),
        valid_status(motor_id=99, position_rad=0.85),
        valid_status(motor_id=4, position_rad=0.85, mode=3),
    ],
    ids=[
        "nan_position",
        "infinite_position",
        "missing_position",
        "motor_id_mismatch",
        "invalid_device_status",
    ],
)
def test_cold_start_rejects_untrustworthy_feedback(status) -> None:
    driver = FakeMotorDriver(auto_feedback=False)
    emitted = False

    def emit_once(_seconds):
        nonlocal emitted
        if not emitted:
            emitted = True
            driver.emit_feedback(status)

    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=emit_once,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert not any(
            operation == "write_sdo_float" and index == SDO_TARGET_POS
            for operation, _motor_id, index, _value in driver.calls
        )
    finally:
        node.destroy_node()


@pytest.mark.parametrize(
    "status",
    [
        valid_status(motor_id=4, position_rad=0.85, fault_flags=0x02),
        valid_status(motor_id=4, position_rad=0.85, temperature=90.0),
    ],
    ids=["fault_frame", "critical_temperature"],
)
def test_cold_start_feedback_safety_fault_dominates_measured_position(status) -> None:
    driver = FakeMotorDriver(auto_feedback=False)
    emitted = False

    def emit_once(_seconds):
        nonlocal emitted
        if not emitted:
            emitted = True
            driver.emit_feedback(status)

    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=emit_once,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert not any(
            operation == "write_sdo_float" and index == SDO_TARGET_POS
            for operation, _motor_id, index, _value in driver.calls
        )
        assert [
            motor_id
            for operation, motor_id, _index, _value in driver.calls
            if operation == "stop_motor"
        ] == [4, 3, 2, 1, 4]
    finally:
        node.destroy_node()


def test_set_zero_after_nonzero_startup_synchronizes_feedback_and_targets() -> None:
    measured = {4: 0.85, 3: 0.74, 2: 0.91, 1: 0.42}
    driver = MeasuredConfigureDriver(measured)
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node._current_targets == measured
        assert node._motor_mgr.set_all_motor_zero_reference()
        assert node._current_targets == {motor_id: 0.0 for motor_id in measured}
        assert node._desired_targets == node._current_targets
        assert {
            motor_id: node._motor_feedback[motor_id].position_rad
            for motor_id in node._motor_ids
        } == node._current_targets
        assert [
            motor_id
            for operation, motor_id, _index, _value in driver.calls
            if operation == "set_zero"
        ] == [4, 3, 2, 1]
    finally:
        node.on_cleanup(None)
        node.destroy_node()


def test_idle_acquisition_keeps_all_four_feedback_entries_truthful_and_fresh() -> None:
    clock = FakeClock()
    driver = ConfigureFeedbackDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=clock,
    )
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        cached_after_configure = dict(node._motor_feedback)
        assert set(cached_after_configure) == {4, 3, 2, 1}
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert node._motor_feedback == cached_after_configure
        assert node._motor_mgr.feedback_acquisition_timer is not None

        current_before = dict(node._current_targets)
        desired_before = dict(node._desired_targets)
        speeds_before = dict(node._current_speeds)
        call_index = len(driver.calls)
        node._motor_mgr._feedback_acquisition_tick()
        probe_calls = driver.calls[call_index:]
        assert probe_calls == [
            ("write_sdo_float", motor_id, SDO_TARGET_POS, current_before[motor_id])
            for motor_id in (4, 3, 2, 1)
        ]
        assert node._current_targets == current_before
        assert node._desired_targets == desired_before
        assert node._current_speeds == speeds_before

        original = node._motor_feedback_structured_pub
        capture = CapturePublisher()
        node._motor_feedback_structured_pub = capture
        node._publish_structured_motor_feedback()
        first = capture.messages[-1]
        assert [motor.logical_name for motor in first.motors] == [
            "left_lift",
            "left_pitch",
            "right_pitch",
            "right_lift",
        ]
        assert all(motor.has_feedback for motor in first.motors)
        assert all(motor.position_valid for motor in first.motors)
        assert all(motor.velocity_valid for motor in first.motors)
        assert all(motor.torque_valid for motor in first.motors)
        assert all(motor.temperature_valid for motor in first.motors)
        assert all(motor.device_mode_valid for motor in first.motors)
        assert all(motor.fault_flags_valid for motor in first.motors)
        assert all(motor.valid and motor.fresh and motor.healthy for motor in first.motors)
        assert all(motor.feedback_age_sec == pytest.approx(0.0) for motor in first.motors)

        clock.now += 0.25
        node._publish_structured_motor_feedback()
        assert all(
            motor.feedback_age_sec == pytest.approx(0.25)
            for motor in capture.messages[-1].motors
        )

        target_writes_before_deactivate = len(
            [
                call
                for call in driver.calls
                if call[0] == "write_sdo_float" and call[2] == SDO_TARGET_POS
            ]
        )
        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert node._motor_mgr.feedback_acquisition_timer is None
        node._motor_mgr._feedback_acquisition_tick()
        target_writes_after_deactivate = len(
            [
                call
                for call in driver.calls
                if call[0] == "write_sdo_float" and call[2] == SDO_TARGET_POS
            ]
        )
        assert target_writes_after_deactivate == target_writes_before_deactivate

        clock.now += 0.30
        node._publish_structured_motor_feedback()
        assert all(not motor.fresh and not motor.healthy for motor in capture.messages[-1].motors)
    finally:
        if original is not None:
            node._motor_feedback_structured_pub = original
        node.on_cleanup(None)
        node.destroy_node()


def test_structured_publisher_is_complete_and_adds_no_driver_io() -> None:
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    capture = CapturePublisher()
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(valid_status())
        with node._lock:
            node._motor_feedback.pop(3)
            node._motor_feedback_received_at.pop(3)
        original = node._motor_feedback_structured_pub
        node._motor_feedback_structured_pub = capture
        calls_before = list(driver.calls)
        node._publish_structured_motor_feedback()
        assert driver.calls == calls_before

        message = capture.messages[-1]
        assert message.sequence == 0
        assert [(item.logical_name, item.can_id) for item in message.motors] == [
            ("left_lift", 4),
            ("left_pitch", 3),
            ("right_pitch", 2),
            ("right_lift", 1),
        ]
        observed = message.motors[0]
        assert observed.has_feedback
        assert observed.position_valid
        assert observed.velocity_valid
        assert observed.torque_valid
        assert observed.temperature_valid
        assert observed.device_mode_valid
        assert observed.fault_flags_valid
        assert observed.valid and observed.fresh and observed.healthy
        assert observed.feedback_age_sec >= 0.0
        missing = message.motors[1]
        assert not missing.has_feedback
        assert not missing.position_valid
        assert not missing.velocity_valid
        assert not missing.torque_valid
        assert not missing.temperature_valid
        assert not missing.device_mode_valid
        assert not missing.fault_flags_valid
        assert not missing.valid and not missing.fresh and not missing.healthy
    finally:
        if original is not None:
            node._motor_feedback_structured_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_observer_stale_and_publication_failure_do_not_change_safety_state() -> None:
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
    )
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        driver.emit_feedback(valid_status())
        with node._lock:
            node._motor_feedback_received_at[4] = time.monotonic() - 10.0
        capture = CapturePublisher()
        original = node._motor_feedback_structured_pub
        node._motor_feedback_structured_pub = capture
        node._publish_structured_motor_feedback()
        assert not capture.messages[-1].motors[0].fresh
        assert not capture.messages[-1].motors[0].healthy

        driver.emit_feedback(valid_status(fault_flags=0x02))
        assert node._motor_safety_fault_active
        fault_snapshot = node._motor_safety_fault_snapshot
        calls_before = list(driver.calls)
        node._motor_feedback_structured_pub = CapturePublisher(
            RuntimeError("injected publication failure")
        )
        node._publish_structured_motor_feedback()
        assert node._motor_safety_fault_active
        assert node._motor_safety_fault_snapshot == fault_snapshot
        assert driver.calls == calls_before
    finally:
        if original is not None:
            node._motor_feedback_structured_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_motor_safety_publisher_is_transient_local_observer_only():
    from rclpy.qos import DurabilityPolicy

    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=lambda **_kwargs: driver,
        sleep_fn=lambda _seconds: None,
        source_epoch_fn=lambda: 100,
    )
    original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert (
            node._motor_safety_state_pub.qos_profile.durability
            is DurabilityPolicy.TRANSIENT_LOCAL
        )
        capture = CapturePublisher()
        original = node._motor_safety_state_pub
        node._motor_safety_state_pub = capture
        calls_before = list(driver.calls)
        node._publish_motor_safety_state()
        assert driver.calls == calls_before
        message = capture.messages[-1]
        assert message.source_epoch == 100
        assert message.observation_sequence > 0
        assert message.node_active
        assert message.controller_state == "MANUAL_RUNNING"
        assert message.public_control_mode == "MANUAL"
        assert not message.e_stop_latched
        assert not message.error_latched
        assert message.transition_present

        state_before = node._state_mgr.state
        node._motor_safety_state_pub = CapturePublisher(RuntimeError("injected"))
        node._publish_motor_safety_state()
        assert node._state_mgr.state is state_before
        assert driver.calls == calls_before
    finally:
        if original is not None:
            node._motor_safety_state_pub = original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()


def test_motor_safety_epoch_and_sequence_span_lifecycle_reconfigure():
    drivers = [FakeMotorDriver(), FakeMotorDriver()]
    created = []

    def factory(**_kwargs):
        driver = drivers[len(created)]
        created.append(driver)
        return driver

    node = ImuMotorControllerNode(
        driver_factory=factory,
        sleep_fn=lambda _seconds: None,
        source_epoch_fn=lambda: 321,
    )
    second_original = None
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        first_original = node._motor_safety_state_pub
        first_capture = CapturePublisher()
        node._motor_safety_state_pub = first_capture
        node._publish_motor_safety_state()
        first = first_capture.messages[-1]
        node._motor_safety_state_pub = first_original

        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        second_original = node._motor_safety_state_pub
        second_capture = CapturePublisher()
        node._motor_safety_state_pub = second_capture
        node._publish_motor_safety_state()
        second = second_capture.messages[-1]

        assert first.source_epoch == second.source_epoch == 321
        assert first.observation_sequence > 0
        assert second.observation_sequence > first.observation_sequence
    finally:
        if second_original is not None:
            node._motor_safety_state_pub = second_original
        node.on_deactivate(None)
        node.on_cleanup(None)
        node.destroy_node()
