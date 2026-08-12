import os

import pytest
import rclpy

from windarmor_flight_control.core.models import FanCommand, FlightCommand
from windarmor_flight_control.runtime.node import FlightControlRuntimeNode


class MutableClock:
    def __init__(self, value=10.0):
        self.value = value

    def __call__(self):
        return self.value


class CapturingPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class FakeController:
    def __init__(self, command=None, update_error=None, reset_error=None):
        self.command = command or FlightCommand.safe_stop()
        self.update_error = update_error
        self.reset_error = reset_error
        self.reset_count = 0
        self.updates = []

    def reset(self):
        self.reset_count += 1
        if self.reset_error is not None:
            raise self.reset_error

    def update(self, state, dt):
        self.updates.append((state, dt))
        if self.update_error is not None:
            raise self.update_error
        return self.command


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def make_node(controller, clock):
    node = FlightControlRuntimeNode(
        monotonic_fn=clock,
        controller_loader=lambda _contract, _names: controller,
    )
    node._status_pub = CapturingPublisher()
    node._preview_pub = CapturingPublisher()
    return node


def test_controller_reset_once_timer_tick_uses_positive_monotonic_dt() -> None:
    clock = MutableClock()
    controller = FakeController()
    node = make_node(controller, clock)
    try:
        assert controller.reset_count == 1
        assert node._control_timer.callback == node._control_tick
        clock.value = 10.02
        node._control_tick()
        assert len(controller.updates) == 1
        state, dt = controller.updates[0]
        assert dt == pytest.approx(0.02)
        assert state.system.command_authority.value == "NONE"
        assert state.system.authority_generation == 0
        assert not state.system.flight_control_active
        assert not state.system.actuation_allowed
    finally:
        node.destroy_node()


def test_sensor_callback_never_invokes_controller_and_safe_stop_preview_has_no_payload() -> None:
    clock = MutableClock()
    controller = FakeController(FlightCommand.safe_stop())
    node = make_node(controller, clock)
    try:
        from std_msgs.msg import Bool, String

        node._on_e_stop(Bool(data=False))
        node._on_imu_status(String(data="unknown"))
        assert controller.updates == []
        clock.value = 10.01
        node._control_tick()
        preview = node._preview_pub.messages[-1]
        assert preview.request_safe_stop
        assert preview.motor_names == []
        assert list(preview.motor_positions_rad) == []
        assert not preview.fan_commands_present
        status = node._status_pub.messages[-1]
        assert status.mode == "DRY_RUN"
        assert status.state_valid
        assert status.command_valid
        assert status.latest_command_safe_stop
    finally:
        node.destroy_node()


def test_explicit_test_controller_can_preview_complete_normal_command() -> None:
    clock = MutableClock()
    names = ("left_lift", "left_pitch", "right_pitch", "right_lift")
    command = FlightCommand(
        motor_positions_rad={name: index * 0.1 for index, name in enumerate(names)},
        fan_commands=FanCommand(left=0.25, right=0.75),
    )
    node = make_node(FakeController(command), clock)
    try:
        clock.value = 10.01
        node._control_tick()
        preview = node._preview_pub.messages[-1]
        assert not preview.request_safe_stop
        assert tuple(preview.motor_names) == names
        assert preview.motor_positions_rad == pytest.approx([0.0, 0.1, 0.2, 0.3])
        assert preview.fan_commands_present
        assert preview.fan_left == 0.25
        assert preview.fan_right == 0.75
    finally:
        node.destroy_node()


def test_invalid_command_latches_inhibited_and_never_auto_recovers() -> None:
    clock = MutableClock()
    controller = FakeController(
        FlightCommand(
            motor_positions_rad={"left_lift": 0.0},
            fan_commands=FanCommand(left=0.0, right=0.0),
        )
    )
    node = make_node(controller, clock)
    try:
        clock.value = 10.01
        node._control_tick()
        assert node._controller_inhibited
        assert len(controller.updates) == 1
        assert node._preview_pub.messages == []
        clock.value = 10.02
        node._control_tick()
        assert len(controller.updates) == 1
        assert node._status_pub.messages[-1].controller_inhibited
    finally:
        node.destroy_node()


def test_controller_exception_latches_inhibited() -> None:
    clock = MutableClock()
    controller = FakeController(update_error=RuntimeError("injected update"))
    node = make_node(controller, clock)
    try:
        clock.value = 10.01
        node._control_tick()
        assert node._controller_inhibited
        assert "injected update" in node._last_error
        assert node._preview_pub.messages == []
    finally:
        node.destroy_node()


def test_reset_exception_inhibits_before_timer_and_does_not_call_update() -> None:
    clock = MutableClock()
    controller = FakeController(reset_error=RuntimeError("injected reset"))
    node = make_node(controller, clock)
    try:
        assert controller.reset_count == 1
        assert node._controller_inhibited
        clock.value = 10.01
        node._control_tick()
        assert controller.updates == []
        assert "injected reset" in node._status_pub.messages[-1].last_error
    finally:
        node.destroy_node()


def test_invalid_state_contract_inhibits_without_controller_call() -> None:
    clock = MutableClock()
    controller = FakeController()
    node = make_node(controller, clock)
    try:
        node._aggregator.build_snapshot = lambda _now: object()
        clock.value = 10.01
        node._control_tick()
        assert node._controller_inhibited
        assert controller.updates == []
        assert not node._status_pub.messages[-1].state_valid
    finally:
        node.destroy_node()


def test_loader_failure_is_latched_but_observer_node_still_constructs() -> None:
    clock = MutableClock()

    def fail_loader(_contract, _names):
        raise RuntimeError("injected loader")

    node = FlightControlRuntimeNode(
        monotonic_fn=clock,
        controller_loader=fail_loader,
    )
    node._status_pub = CapturingPublisher()
    node._preview_pub = CapturingPublisher()
    try:
        assert node._controller_inhibited
        clock.value = 10.01
        node._control_tick()
        assert "injected loader" in node._status_pub.messages[-1].last_error
    finally:
        node.destroy_node()
