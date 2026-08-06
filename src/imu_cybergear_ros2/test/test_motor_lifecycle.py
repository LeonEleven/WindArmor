import os

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.cybergear_driver import (
    SDO_RUN_MODE,
    SDO_TARGET_POS,
    SDO_TARGET_SPEED,
)
from imu_cybergear_ros2.imu_motor_controller_node import ImuMotorControllerNode

from .fake_motor_driver import FakeMotorDriver


RESOURCE_ATTRS = (
    "_motor_status_pub",
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
        assert len(destroy_calls) == 5
        assert_fully_released(node, driver)
        assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
        assert len(destroy_calls) == 5
    finally:
        node.destroy_node()
