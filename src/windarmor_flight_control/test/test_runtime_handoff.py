import os
from dataclasses import replace
from types import SimpleNamespace

import pytest
import rclpy

from windarmor_flight_control.core.authority import AuthorityState
from windarmor_flight_control.core.models import FanCommand, FlightCommand
from windarmor_flight_control.runtime.node import FlightControlRuntimeNode
from windarmor_flight_control.runtime.ownership import HandoffState

from .test_runtime_node import (
    CapturingPublisher,
    FakeController,
    MutableClock,
    ready_runtime_snapshot,
)


class ImmediateFuture:
    def __init__(self, value):
        self.value = value

    def add_done_callback(self, callback):
        callback(self)

    def result(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class FakeClient:
    def __init__(self, responder):
        self.responder = responder
        self.requests = []

    def service_is_ready(self):
        return True

    def call_async(self, request):
        self.requests.append(request)
        return ImmediateFuture(self.responder(request))


class DeferredFuture:
    def __init__(self):
        self.callback = None

    def add_done_callback(self, callback):
        self.callback = callback


class DeferredClient:
    def __init__(self):
        self.requests = []
        self.futures = []

    def service_is_ready(self):
        return True

    def call_async(self, request):
        self.requests.append(request)
        future = DeferredFuture()
        self.futures.append(future)
        return future


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def ownership_message(domain, *, sequence, epoch=100, generation=1, source=10):
    return SimpleNamespace(
        source_epoch=source,
        observation_sequence=sequence,
        owner_domain=domain,
        ownership_phase="FLIGHT_CONTROL",
        authority_present=True,
        authority_epoch=epoch,
        generation=generation,
        last_accepted_flight_command_present=False,
        last_accepted_flight_command_sequence=0,
        last_valid_flight_command_age_sec=-1.0,
    )


def response(request, *, success=True, reason="ok", sequence=1):
    return SimpleNamespace(
        success=success,
        reason_code=reason,
        authority_epoch=request.authority_epoch,
        generation=request.generation,
        owner_observation_sequence=sequence,
    )


def make_enabled_node(controller, clock, *, authority_epoch=100, **overrides):
    config = {"flight_takeover_enabled": True}
    config.update(overrides)
    node = FlightControlRuntimeNode(
        monotonic_fn=clock,
        authority_epoch_fn=lambda: authority_epoch,
        controller_loader=lambda _contract, _names: controller,
        config_overrides=config,
    )
    node._status_pub = CapturingPublisher()
    node._preview_pub = CapturingPublisher()
    node._authority_status_pub = CapturingPublisher()
    node._command_pub = CapturingPublisher()
    node._motor_prepare_client = FakeClient(lambda request: response(request, sequence=1))
    node._fan_prepare_client = FakeClient(lambda request: response(request, sequence=2))
    node._motor_commit_client = FakeClient(lambda request: response(request, sequence=3))
    node._fan_commit_client = FakeClient(lambda request: response(request, sequence=4))
    node._motor_revoke_client = FakeClient(lambda request: response(request, sequence=5))
    node._fan_revoke_client = FakeClient(lambda request: response(request, sequence=6))
    return node


def complete_handoff(node, clock, *, epoch=100, cutoff=43):
    from std_srvs.srv import Trigger

    node._aggregator.build_runtime_snapshot = lambda _now: ready_runtime_snapshot()
    assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
    clock.value = 10.01
    node._control_tick()
    assert node._handoff.state is HandoffState.OWNERS_COMMITTED
    node._on_motor_ownership(
        ownership_message("motor", sequence=1, epoch=epoch)
    )
    node._on_fan_ownership(
        ownership_message("fan", sequence=1, epoch=epoch, source=20)
    )
    snapshot = active_snapshot(cutoff)
    node._aggregator.build_runtime_snapshot = lambda _now: snapshot
    clock.value = 10.02
    node._control_tick()
    assert node._authority.state is AuthorityState.ACTIVE
    return snapshot


def active_snapshot(sequence):
    snapshot = ready_runtime_snapshot()
    state = replace(
        snapshot.flight_state,
        sequence=sequence,
        fans=replace(snapshot.flight_state.fans, control_state="FLIGHT_WAITING"),
        system=replace(
            snapshot.flight_state.system,
            motor_control_mode="AUTO",
            fan_control_state="FLIGHT_WAITING",
        ),
    )
    return replace(
        snapshot,
        flight_state=state,
        motor_safety=replace(
            snapshot.motor_safety,
            controller_state="AUTO_RUNNING",
            public_control_mode="AUTO",
        ),
        fan_safety=replace(
            snapshot.fan_safety,
            control_state="FLIGHT_WAITING",
            passive_for_takeover=False,
        ),
    )


def test_full_handoff_atomic_cutoff_and_first_post_state_command():
    names = ("left_lift", "left_pitch", "right_pitch", "right_lift")
    command = FlightCommand(
        motor_positions_rad={name: 0.1 for name in names},
        fan_commands=FanCommand(0.2, 0.3),
    )
    clock = MutableClock()
    controller = FakeController(command)
    node = make_enabled_node(controller, clock)
    from std_srvs.srv import Trigger

    try:
        snapshot = ready_runtime_snapshot()
        node._aggregator.build_runtime_snapshot = lambda _now: snapshot
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()
        assert node._handoff.state is HandoffState.OWNERS_COMMITTED
        assert node._authority.state is AuthorityState.READY_TO_TAKEOVER

        node._on_motor_ownership(ownership_message("motor", sequence=1))
        node._on_fan_ownership(ownership_message("fan", sequence=1, source=20))
        snapshot = active_snapshot(43)
        clock.value = 10.02
        node._control_tick()
        assert node._authority.state is AuthorityState.ACTIVE
        assert node._authority.arming_cutoff_state_sequence == 43
        assert controller.reset_count == 2
        assert node._command_pub.messages == []

        snapshot = active_snapshot(44)
        clock.value = 10.03
        node._control_tick()
        assert len(node._command_pub.messages) == 1
        envelope = node._command_pub.messages[0]
        assert envelope.authority_epoch == 100
        assert envelope.generation == 1
        assert envelope.command_sequence == 0
        assert envelope.state_sequence == 44
        assert envelope.fan_commands_present
    finally:
        node.destroy_node()


def test_partial_reserve_failure_revokes_and_inhibits_without_command():
    clock = MutableClock()
    node = make_enabled_node(FakeController(), clock)
    node._fan_prepare_client = FakeClient(
        lambda request: response(
            request, success=False, reason="injected_fan_reserve_failure", sequence=2
        )
    )
    from std_srvs.srv import Trigger

    try:
        node._aggregator.build_runtime_snapshot = lambda _now: ready_runtime_snapshot()
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()
        assert node._authority.state is AuthorityState.INHIBITED
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
        assert node._command_pub.messages == []
    finally:
        node.destroy_node()


def test_partial_commit_failure_revokes_both_and_never_activates():
    clock = MutableClock()
    node = make_enabled_node(FakeController(), clock)
    node._fan_commit_client = FakeClient(
        lambda request: response(
            request, success=False, reason="injected_fan_commit_failure", sequence=4
        )
    )
    from std_srvs.srv import Trigger

    try:
        node._aggregator.build_runtime_snapshot = lambda _now: ready_runtime_snapshot()
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()
        assert node._authority.state is AuthorityState.INHIBITED
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
        assert node._command_pub.messages == []
    finally:
        node.destroy_node()


def test_atomic_commit_or_controller_reset_failure_revokes_without_command(monkeypatch):
    for failure in ("commit", "reset"):
        clock = MutableClock()
        controller = FakeController()
        node = make_enabled_node(controller, clock)
        try:
            snapshot = ready_runtime_snapshot()
            node._aggregator.build_runtime_snapshot = lambda _now: snapshot
            from std_srvs.srv import Trigger

            assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
            clock.value = 10.01
            node._control_tick()
            node._on_motor_ownership(ownership_message("motor", sequence=1))
            node._on_fan_ownership(
                ownership_message("fan", sequence=1, source=20)
            )
            if failure == "commit":
                monkeypatch.setattr(
                    node._authority,
                    "commit_active",
                    lambda **_kwargs: (_ for _ in ()).throw(
                        RuntimeError("injected atomic commit failure")
                    ),
                )
            else:
                controller.reset_error = RuntimeError("injected second reset failure")
            snapshot = active_snapshot(43)
            clock.value = 10.02
            node._control_tick()
            assert node._authority.state is AuthorityState.INHIBITED
            assert node._motor_revoke_client.requests
            assert node._fan_revoke_client.requests
            assert node._command_pub.messages == []
        finally:
            node.destroy_node()


def test_active_safe_stop_is_transported_then_revokes_both():
    clock = MutableClock()
    node = make_enabled_node(FakeController(FlightCommand.safe_stop()), clock)
    try:
        complete_handoff(node, clock)
        snapshot = active_snapshot(44)
        node._aggregator.build_runtime_snapshot = lambda _now: snapshot
        clock.value = 10.03
        node._control_tick()
        assert node._authority.state is AuthorityState.INHIBITED
        assert len(node._command_pub.messages) == 1
        command = node._command_pub.messages[0]
        assert command.request_safe_stop
        assert list(command.motor_names) == []
        assert not command.fan_commands_present
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
    finally:
        node.destroy_node()


@pytest.mark.parametrize("failure", ["safety", "algorithm"])
def test_active_safety_or_algorithm_failure_revokes_and_inhibits(failure):
    clock = MutableClock()
    controller = FakeController(
        FlightCommand(
            motor_positions_rad={
                name: 0.1
                for name in ("left_lift", "left_pitch", "right_pitch", "right_lift")
            },
            fan_commands=FanCommand(0.2, 0.2),
        )
    )
    node = make_enabled_node(controller, clock)
    try:
        complete_handoff(node, clock)
        snapshot = active_snapshot(44)
        if failure == "safety":
            snapshot = replace(
                snapshot,
                motor_safety=replace(snapshot.motor_safety, error_latched=True),
            )
        else:
            controller.update_error = RuntimeError("injected ACTIVE update failure")
        node._aggregator.build_runtime_snapshot = lambda _now: snapshot
        clock.value = 10.03
        node._control_tick()
        assert node._authority.state is AuthorityState.INHIBITED
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
    finally:
        node.destroy_node()


def test_owner_stale_or_restarted_while_active_fails_closed():
    for failure in ("stale", "restart"):
        clock = MutableClock()
        node = make_enabled_node(
            FakeController(),
            clock,
            flight_owner_state_freshness_sec=0.1,
        )
        try:
            complete_handoff(node, clock)
            if failure == "restart":
                node._on_motor_ownership(
                    ownership_message("motor", sequence=1, source=30)
                )
            else:
                snapshot = active_snapshot(44)
                node._aggregator.build_runtime_snapshot = lambda _now: snapshot
                clock.value = 10.20
                node._control_tick()
            assert node._authority.state is AuthorityState.INHIBITED
            assert node._motor_revoke_client.requests
            assert node._fan_revoke_client.requests
        finally:
            node.destroy_node()


@pytest.mark.parametrize("event", ["timeout", "cancel", "estop"])
def test_handoff_timeout_cancel_or_estop_revokes_and_inhibits(event):
    clock = MutableClock()
    node = make_enabled_node(
        FakeController(), clock, flight_handoff_timeout_sec=0.1
    )
    node._motor_prepare_client = DeferredClient()
    node._fan_prepare_client = DeferredClient()
    from std_msgs.msg import Bool
    from std_srvs.srv import Trigger

    try:
        node._aggregator.build_runtime_snapshot = lambda _now: ready_runtime_snapshot()
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()
        assert node._handoff.state is HandoffState.RESERVING
        if event == "timeout":
            clock.value = 10.20
            node._control_tick()
        elif event == "cancel":
            result = node._on_cancel(Trigger.Request(), Trigger.Response())
            assert result.success
        else:
            node._on_e_stop(Bool(data=True))
        assert node._authority.state is AuthorityState.INHIBITED
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
        assert node._command_pub.messages == []
    finally:
        node.destroy_node()


def test_old_epoch_readback_cannot_activate_new_runtime_session():
    clock = MutableClock()
    node = make_enabled_node(FakeController(), clock)
    from std_srvs.srv import Trigger

    try:
        snapshot = ready_runtime_snapshot()
        node._aggregator.build_runtime_snapshot = lambda _now: snapshot
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()
        node._on_motor_ownership(
            ownership_message("motor", sequence=1, epoch=99)
        )
        node._on_fan_ownership(
            ownership_message("fan", sequence=1, epoch=99, source=20)
        )
        snapshot = active_snapshot(43)
        clock.value = 10.02
        node._control_tick()
        assert node._authority.state is AuthorityState.READY_TO_TAKEOVER
        assert node._command_pub.messages == []
    finally:
        node.destroy_node()


def test_runtime_restart_requires_full_new_epoch_handoff_and_rejects_a_readback():
    clock_a = MutableClock()
    runtime_a = make_enabled_node(FakeController(), clock_a, authority_epoch=100)
    try:
        complete_handoff(runtime_a, clock_a, epoch=100)
        assert runtime_a._authority.authority_generation == 1
    finally:
        runtime_a.destroy_node()

    clock_b = MutableClock()
    runtime_b = make_enabled_node(FakeController(), clock_b, authority_epoch=200)
    from std_srvs.srv import Trigger

    try:
        snapshot = ready_runtime_snapshot()
        runtime_b._aggregator.build_runtime_snapshot = lambda _now: snapshot
        assert runtime_b._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock_b.value = 10.01
        runtime_b._control_tick()
        assert runtime_b._handoff.state is HandoffState.OWNERS_COMMITTED
        runtime_b._on_motor_ownership(
            ownership_message("motor", sequence=1, epoch=100)
        )
        runtime_b._on_fan_ownership(
            ownership_message("fan", sequence=1, epoch=100, source=20)
        )
        snapshot = active_snapshot(43)
        runtime_b._aggregator.build_runtime_snapshot = lambda _now: snapshot
        clock_b.value = 10.02
        runtime_b._control_tick()
        assert runtime_b._authority.state is AuthorityState.READY_TO_TAKEOVER

        runtime_b._on_motor_ownership(
            ownership_message("motor", sequence=2, epoch=200)
        )
        runtime_b._on_fan_ownership(
            ownership_message("fan", sequence=2, epoch=200, source=20)
        )
        clock_b.value = 10.03
        runtime_b._control_tick()
        assert runtime_b._authority.state is AuthorityState.ACTIVE
        assert runtime_b._authority.authority_generation == 1
    finally:
        runtime_b.destroy_node()
