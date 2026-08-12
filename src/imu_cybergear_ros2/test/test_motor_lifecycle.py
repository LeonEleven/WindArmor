import os

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.parameter import Parameter

from imu_cybergear_ros2.cybergear_driver import (
    MotorStatus,
    SDO_RUN_MODE,
    SDO_TARGET_POS,
    SDO_TARGET_SPEED,
)
from imu_cybergear_ros2.controller_state import (
    ControllerState,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.imu_motor_controller_node import ImuMotorControllerNode

from .fake_motor_driver import FakeMotorDriver


RESOURCE_ATTRS = (
    "_motor_status_pub",
    "_motor_feedback_structured_pub",
    "_motor_safety_state_pub",
    "_motor_feedback_structured_timer",
    "_system_e_stop_pub",
    "_relative_attitude_pub",
    "_imu_zero_generation_pub",
    "_motor_mode_pub",
    "_motor_mode_timer",
    "_sub",
    "_e_stop_sub",
    "_manual_targets_sub",
    "_e_stop_srv",
    "_enable_motor_srv",
    "_imu_zero_srv",
    "_motor_zero_srv",
)


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


class RejectDriverFactory:
    def __init__(self):
        self.calls = 0

    def __call__(self, **_kwargs):
        self.calls += 1
        raise AssertionError("配置校验失败时不得创建驱动")


class CapturingDriverFactory:
    def __init__(self, driver):
        self.driver = driver
        self.kwargs = []

    def __call__(self, **kwargs):
        self.kwargs.append(kwargs)
        return self.driver


class CapturingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warn(self, message):
        self.messages.append(("warn", message))

    def error(self, message):
        self.messages.append(("error", message))


def operation_motor_ids(driver, operation):
    return [call[1] for call in driver.calls if call[0] == operation]


def assert_fully_released(node, driver):
    assert node._driver is None
    assert node._motor_mgr is None
    assert node._safety is None
    assert node._keyboard is None
    assert node._state_mgr is None
    assert not node._init_complete
    assert node._motor_ids == []
    assert node._current_targets == {}
    assert node._desired_targets == {}
    assert node._current_speeds == {}
    assert all(getattr(node, attr) is None for attr in RESOURCE_ATTRS)
    assert driver.feedback_callback is None
    assert driver.feedback_error_callback is None
    assert driver.transport_event_callback is None


@pytest.mark.parametrize(
    "parameter",
    [
        Parameter("motor_ids", value=[4, 4, 2, 1]),
        Parameter("left_lift_motor_id", value=5),
        Parameter("warning_throttle_sec", value=0.0),
    ],
)
def test_invalid_config_has_zero_driver_ros_and_runtime_side_effects(parameter):
    factory = RejectDriverFactory()
    node = ImuMotorControllerNode(driver_factory=factory, sleep_fn=lambda _seconds: None)
    resource_calls = []

    def forbidden_resource(*_args, **_kwargs):
        resource_calls.append(True)
        raise AssertionError("配置校验失败时不得创建 ROS 运行资源")

    node.create_publisher = forbidden_resource
    node.create_subscription = forbidden_resource
    node.create_service = forbidden_resource
    node.create_timer = forbidden_resource
    try:
        results = node.set_parameters([parameter])
        assert all(result.successful for result in results)
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert factory.calls == 0
        assert resource_calls == []
        assert node._driver is None
        assert node._state_mgr is None
        assert node._motor_mgr is None
        assert node._safety is None
        assert node._keyboard is None
        assert all(getattr(node, attr) is None for attr in RESOURCE_ATTRS)
    finally:
        node.destroy_node()


def test_usb_legacy_fallback_warns_once_and_still_uses_fake_driver():
    driver = FakeMotorDriver()
    factory = CapturingDriverFactory(driver)
    logger = CapturingLogger()
    node = ImuMotorControllerNode(driver_factory=factory, sleep_fn=lambda _seconds: None)
    node.get_logger = lambda: logger
    try:
        results = node.set_parameters(
            [
                Parameter("control_backend", value="usb_can_serial"),
                Parameter("usb_port", value=""),
                Parameter("usb_baud", value=0),
                Parameter("motor_port", value="fake-legacy-port"),
                Parameter("motor_baud", value=460800),
            ]
        )
        assert all(result.successful for result in results)
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert factory.kwargs[0]["usb_port"] == "fake-legacy-port"
        assert factory.kwargs[0]["usb_baud"] == 460800
        warnings = [
            message
            for level, message in logger.messages
            if level == "warn" and "已废弃兼容参数" in message
        ]
        assert len(warnings) == 1
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
    finally:
        node.destroy_node()


def test_feedback_timer_starts_only_when_enabled_and_is_destroyed_on_deactivate():
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert all(
            result.successful
            for result in node.set_parameters(
                [Parameter("motor_feedback_timeout_sec", value=1.0)]
            )
        )
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node._safety.feedback_timer is None
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert node._safety.feedback_timer is not None
        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert node._safety.feedback_timer is None
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert_fully_released(node, driver)
    finally:
        node.destroy_node()


def test_reconfigure_replaces_feedback_health_session_and_callbacks():
    first = FakeMotorDriver()
    second = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([first, second]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        first_health = node._safety.health_core
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        first.emit_feedback(
            MotorStatus(
                motor_id=4,
                mode=2,
                timestamp=1.0,
                temperature=25.0,
                fault_flags=0x01,
            )
        )
        assert any(item.has_feedback for item in first_health.freshness_snapshot(now=10**9))
        assert node._motor_safety_fault_active
        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert first.feedback_callback is None

        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        second_health = node._safety.health_core
        assert second_health is not first_health
        assert not node._motor_safety_fault_active
        assert not any(node._motor_protection_flags.values())
        assert all(
            not item.has_feedback
            for item in second_health.freshness_snapshot(now=10**9)
        )
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert_fully_released(node, second)
    finally:
        node.destroy_node()


@pytest.mark.parametrize(
    ("driver", "expected_stops", "untouched_ids"),
    [
        (FakeMotorDriver(connect_result=False), [], [4, 3, 2, 1]),
        (
            FakeMotorDriver(failures={("write_sdo_int", 4, SDO_RUN_MODE)}),
            [4],
            [3, 2, 1],
        ),
        (
            FakeMotorDriver(failures={("write_sdo_float", 3, SDO_TARGET_SPEED)}),
            [3, 4],
            [2, 1],
        ),
        (
            FakeMotorDriver(failures={("write_sdo_float", 3, SDO_TARGET_POS)}),
            [3, 4],
            [2, 1],
        ),
        (
            FakeMotorDriver(failures={("enter_control_mode", 1, None)}),
            [1, 2, 3, 4],
            [],
        ),
    ],
)
def test_configure_failure_rolls_back_touched_motors_driver_and_ros_resources(
    driver, expected_stops, untouched_ids
):
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert operation_motor_ids(driver, "stop_motor") == expected_stops
        assert driver.close_attempts == 1
        assert_fully_released(node, driver)
        for motor_id in untouched_ids:
            assert not any(
                call[1] == motor_id
                and call[0]
                in {
                    "write_sdo_int",
                    "write_sdo_float",
                    "enter_control_mode",
                }
                for call in driver.calls
            )
    finally:
        node.destroy_node()


def test_rollback_continues_after_stop_and_close_failures():
    driver = FakeMotorDriver(
        failures={
            ("enter_control_mode", 1, None),
            ("stop_motor", 3, None),
        },
        close_failure=True,
    )
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert operation_motor_ids(driver, "stop_motor") == [1, 2, 3, 4]
        assert driver.close_attempts == 1
        assert_fully_released(node, driver)
    finally:
        node.destroy_node()


def test_failed_configure_can_be_retried_without_duplicate_resources():
    first = FakeMotorDriver(
        failures={("write_sdo_float", 3, SDO_TARGET_POS)}
    )
    second = FakeMotorDriver()
    factory = DriverFactory([first, second])
    node = ImuMotorControllerNode(
        driver_factory=factory, sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.FAILURE
        assert_fully_released(node, first)

        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node._init_complete
        assert node._motor_ids == [4, 3, 2, 1]
        assert all(getattr(node, attr) is not None for attr in RESOURCE_ATTRS)
        assert first.close_attempts == 1
        assert second.close_attempts == 0

        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert_fully_released(node, second)
        assert second.close_attempts == 1

        # 重复 cleanup 和随后 shutdown 都是幂等空操作。
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
        assert second.close_attempts == 1
    finally:
        node.destroy_node()


def test_cleanup_returns_failure_but_releases_everything_when_close_fails():
    driver = FakeMotorDriver(close_failure=True)
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        assert node.on_cleanup(None) == TransitionCallbackReturn.FAILURE
        assert operation_motor_ids(driver, "stop_motor") == [4, 3, 2, 1]
        assert driver.close_attempts == 1
        assert_fully_released(node, driver)
        assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
        assert driver.close_attempts == 1
    finally:
        node.destroy_node()


def test_shutdown_records_lifecycle_reason_before_releasing_resources():
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        state_manager = node._state_mgr
        assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
        assert state_manager.state is ControllerState.SHUTTING_DOWN
        assert state_manager.last_transition.reason is TransitionReason.SHUTDOWN_REQUEST
        assert state_manager.last_transition.source is TransitionSource.LIFECYCLE
        assert_fully_released(node, driver)
    finally:
        node.destroy_node()


def test_ros_resource_destroy_failure_does_not_block_remaining_cleanup():
    driver = FakeMotorDriver()
    node = ImuMotorControllerNode(
        driver_factory=DriverFactory([driver]), sleep_fn=lambda _seconds: None
    )
    try:
        assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
        original_destroy = node.destroy_publisher
        destroy_calls = []

        def flaky_destroy(resource):
            destroy_calls.append(resource)
            if len(destroy_calls) == 1:
                raise RuntimeError("injected publisher destroy failure")
            return original_destroy(resource)

        node.destroy_publisher = flaky_destroy
        assert node.on_cleanup(None) == TransitionCallbackReturn.FAILURE
        assert len(destroy_calls) == 7
        assert_fully_released(node, driver)
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert len(destroy_calls) == 7
    finally:
        node.destroy_node()
