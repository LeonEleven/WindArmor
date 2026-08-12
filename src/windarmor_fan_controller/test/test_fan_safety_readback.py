import os

import pytest
import rclpy
from rclpy.qos import DurabilityPolicy

from windarmor_fan_controller.fan_command_manager import FanCommandManager
from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
)


class CapturePublisher:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def publish(self, message):
        if self.error:
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


def test_startup_latch_and_passive_predicate():
    core = FanControlCore(FanControlConfig())
    initial = core.safety_snapshot
    assert not initial.e_stop_latched
    assert not initial.enabled_observed
    assert initial.control_state == "SAFE_STOP"
    assert initial.passive_for_takeover

    core.update_fan_enabled(False, 0.0)
    disabled = core.safety_snapshot
    assert disabled.enabled_observed and not disabled.enabled
    assert disabled.control_state == "DISABLED"
    assert not disabled.passive_for_takeover


def test_estop_false_does_not_clear_and_existing_reset_is_authoritative():
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(True, 0.0)
    assert core.safety_snapshot.e_stop_latched
    core.update_e_stop(False, 0.1)
    assert core.safety_snapshot.e_stop_latched
    core.update_fan_enabled(True, 0.1)
    core.update_motor_mode("MANUAL", 0.1)
    success, _ = core.reset_e_stop(0.2)
    assert success
    assert not core.safety_snapshot.e_stop_latched
    assert core.safety_snapshot.passive_for_takeover


def test_legacy_auto_and_manual_ownership_are_never_passive():
    core = FanControlCore(FanControlConfig())
    core.update_e_stop(False, 0.0)
    core.update_fan_enabled(True, 0.0)
    core.update_motor_mode("MANUAL", 0.0)
    assert core.request_manual(True, 0.0)[0]
    assert core.safety_snapshot.manual_armed
    assert not core.safety_snapshot.passive_for_takeover

    core.request_manual(False, 0.1)
    core.update_motor_mode("AUTO", 0.1)
    core.update_pose(0.0, 0.0, 0.1)
    assert core.request_auto(True, 0.1)[0]
    waiting = core.safety_snapshot
    assert waiting.legacy_auto_requested
    assert not waiting.passive_for_takeover
    core.update_pose(0.2, 0.0, 0.2)
    core.control_tick(0.2)
    assert core.safety_snapshot.legacy_auto_active


def test_publisher_is_transient_local_and_failure_has_no_pwm_side_effect():
    node = FanCommandManager()
    original = node._safety_state_pub
    try:
        assert original.qos_profile.durability is DurabilityPolicy.TRANSIENT_LOCAL
        before = node._core.output
        node._safety_state_pub = CapturePublisher(RuntimeError("injected"))
        node._publish_safety_state()
        assert node._core.output == before
        assert node._core.safety_snapshot.control_state == before.state.value
    finally:
        node._safety_state_pub = original
        node.destroy_node()
