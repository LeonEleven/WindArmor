import os
from types import SimpleNamespace

import pytest
import rclpy

from windarmor_fan_controller.fan_control import (
    FanControlConfig,
    FanControlCore,
    FanControlState,
)
from windarmor_fan_controller.fan_ownership import (
    FanCommandOwner,
    FlightLeasePhase,
)
from windarmor_flight_control.core.authority import AuthorityState
from windarmor_flight_control.core.models import FanCommand, FlightCommand
from windarmor_flight_control.runtime.safety_adapter import SafetyReadbackAdapter
from windarmor_flight_control.runtime.ownership import HandoffState

from .runtime_helpers import fan_safety_message, motor_safety_message
from .test_runtime_handoff import (
    FakeClient,
    active_snapshot,
    complete_handoff,
    make_enabled_node,
    ownership_message,
    response,
)
from .test_runtime_node import (
    FakeController,
    MutableClock,
    ready_runtime_snapshot,
)


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


def flight_owned_fan_core() -> FanControlCore:
    core = FanControlCore(FanControlConfig())
    assert core.update_fan_enabled(True, 1.0)
    assert core.update_motor_mode("AUTO", 1.0)
    assert core.update_e_stop(False, 1.0)
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    return core


def flight_ready_fan_core() -> FanControlCore:
    core = FanControlCore(FanControlConfig())
    assert core.update_fan_enabled(True, 1.0)
    assert core.update_motor_mode("AUTO", 1.0)
    assert core.update_e_stop(False, 1.0)
    return core


def snapshot_message(core: FanControlCore, *, sequence: int = 1):
    snapshot = core.safety_snapshot
    return SimpleNamespace(
        source_epoch=500,
        observation_sequence=sequence,
        e_stop_latched=snapshot.e_stop_latched,
        control_state=snapshot.control_state,
        enabled_observed=snapshot.enabled_observed,
        enabled=snapshot.enabled,
        manual_armed=snapshot.manual_armed,
        legacy_auto_requested=snapshot.legacy_auto_requested,
        legacy_auto_active=snapshot.legacy_auto_active,
        safety_reason=snapshot.safety_reason,
        passive_for_takeover=snapshot.passive_for_takeover,
    )


def test_flight_waiting_snapshot_is_a_known_safety_state() -> None:
    core = flight_ready_fan_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.state is FanControlState.FLIGHT_WAITING

    accepted = SafetyReadbackAdapter().update_fan(
        snapshot_message(core), received_at=1.02
    )

    assert accepted.control_state == "FLIGHT_WAITING"
    assert not accepted.e_stop_latched
    assert not accepted.passive_for_takeover


def test_flight_active_snapshot_is_a_known_safety_state() -> None:
    core = flight_ready_fan_core()
    assert core.prepare_flight_ownership(100, 1, now=1.01).success
    assert core.commit_flight_ownership(100, 1, now=1.02).success
    assert core.update_flight_command(
        100, 1, 0, 0.0, 0.0, now=1.03
    ).success
    assert core.control_tick(1.04).state is FanControlState.FLIGHT_ACTIVE

    accepted = SafetyReadbackAdapter().update_fan(
        snapshot_message(core), received_at=1.05
    )

    assert accepted.control_state == "FLIGHT_ACTIVE"
    assert not accepted.e_stop_latched
    assert not accepted.passive_for_takeover


@pytest.mark.parametrize(
    ("state", "overrides"),
    [
        ("SAFE_STOP", {"passive_for_takeover": True}),
        ("MANUAL_DISARMED", {"passive_for_takeover": True}),
        ("MANUAL_WAITING_FOR_NEUTRAL", {"manual_armed": True}),
        ("MANUAL_WAITING", {"manual_armed": True}),
        ("MANUAL_ACTIVE", {"manual_armed": True}),
        ("AUTO_WAITING", {"legacy_auto_requested": True}),
        (
            "AUTO_ACTIVE",
            {"legacy_auto_requested": True, "legacy_auto_active": True},
        ),
        ("FLIGHT_WAITING", {}),
        ("FLIGHT_ACTIVE", {}),
        ("DISABLED", {"enabled": False}),
        ("EMERGENCY_STOP", {"e_stop_latched": True}),
    ],
)
def test_adapter_recognizes_every_formal_fan_state_unchanged(
    state: str,
    overrides: dict,
) -> None:
    assert {item.value for item in FanControlState} == {
        "SAFE_STOP",
        "MANUAL_DISARMED",
        "MANUAL_WAITING_FOR_NEUTRAL",
        "MANUAL_WAITING",
        "MANUAL_ACTIVE",
        "AUTO_WAITING",
        "AUTO_ACTIVE",
        "FLIGHT_WAITING",
        "FLIGHT_ACTIVE",
        "DISABLED",
        "EMERGENCY_STOP",
    }
    values = {"control_state": state, "passive_for_takeover": False}
    values.update(overrides)
    message = fan_safety_message(**values)

    accepted = SafetyReadbackAdapter().update_fan(message, received_at=1.0)

    assert accepted.control_state == state


@pytest.mark.parametrize("state", ["FLIGHT_WAITING", "FLIGHT_ACTIVE"])
def test_flight_states_preserve_estop_and_passive_invariants(state: str) -> None:
    adapter = SafetyReadbackAdapter()
    with pytest.raises(
        ValueError,
        match="fan e-stop latch conflicts with control state",
    ):
        adapter.update_fan(
            fan_safety_message(
                control_state=state,
                e_stop_latched=True,
                passive_for_takeover=False,
            ),
            received_at=1.0,
        )

    adapter = SafetyReadbackAdapter()
    with pytest.raises(
        ValueError,
        match="fan passive predicate conflicts with owner state",
    ):
        adapter.update_fan(
            fan_safety_message(
                control_state=state,
                passive_for_takeover=True,
            ),
            received_at=1.0,
        )


@pytest.mark.parametrize(
    ("state", "overrides"),
    [
        ("FLIGHT_WAITING", {"manual_armed": True}),
        (
            "FLIGHT_ACTIVE",
            {"legacy_auto_requested": True, "legacy_auto_active": True},
        ),
    ],
)
def test_flight_states_reject_legacy_owner_conflicts(
    state: str,
    overrides: dict,
) -> None:
    with pytest.raises(
        ValueError,
        match="fan Flight state conflicts with legacy owner state",
    ):
        SafetyReadbackAdapter().update_fan(
            fan_safety_message(
                control_state=state,
                passive_for_takeover=False,
                **overrides,
            ),
            received_at=1.0,
        )


@pytest.mark.parametrize(
    ("enabled_observed", "enabled"),
    [(False, False), (True, False)],
)
def test_flight_active_requires_truthful_enabled_readback(
    enabled_observed: bool,
    enabled: bool,
) -> None:
    with pytest.raises(
        ValueError,
        match="fan Flight state requires enabled readback",
    ):
        SafetyReadbackAdapter().update_fan(
            fan_safety_message(
                control_state="FLIGHT_ACTIVE",
                enabled_observed=enabled_observed,
                enabled=enabled,
                passive_for_takeover=False,
            ),
            received_at=1.0,
        )


def test_unknown_and_malformed_fan_snapshots_still_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown fan control state"):
        SafetyReadbackAdapter().update_fan(
            fan_safety_message(control_state="FLIGHT_SUPER_MODE"),
            received_at=1.0,
        )
    with pytest.raises(ValueError, match="manual_armed must be a bool"):
        SafetyReadbackAdapter().update_fan(
            fan_safety_message(manual_armed=1),
            received_at=1.0,
        )


def test_runtime_handoff_consumes_real_fan_flight_states_and_reaches_active() -> None:
    from std_srvs.srv import Trigger

    names = ("left_lift", "left_pitch", "right_pitch", "right_lift")
    command = FlightCommand(
        motor_positions_rad={name: 0.0 for name in names},
        fan_commands=FanCommand(0.0, 0.0),
    )
    core = flight_ready_fan_core()
    clock = MutableClock()
    node = make_enabled_node(FakeController(command), clock, authority_epoch=100)

    def fan_prepare(request):
        result = core.prepare_flight_ownership(
            int(request.authority_epoch),
            int(request.generation),
            now=1.01,
        )
        return response(
            request,
            success=result.success,
            reason=result.reason_code,
            sequence=2,
        )

    def fan_commit(request):
        result = core.commit_flight_ownership(
            int(request.authority_epoch),
            int(request.generation),
            now=1.02,
        )
        return response(
            request,
            success=result.success,
            reason=result.reason_code,
            sequence=4,
        )

    node._fan_prepare_client = FakeClient(fan_prepare)
    node._fan_commit_client = FakeClient(fan_commit)
    try:
        node._aggregator.build_runtime_snapshot = (
            lambda _now: ready_runtime_snapshot()
        )
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success
        clock.value = 10.01
        node._control_tick()

        assert node._handoff.state is HandoffState.OWNERS_COMMITTED
        assert node._authority.state is AuthorityState.READY_TO_TAKEOVER
        assert core.state is FanControlState.FLIGHT_WAITING
        assert core.ownership.lease_phase is FlightLeasePhase.HANDOFF

        node._on_fan_safety(snapshot_message(core, sequence=1))
        assert node._authority.state is AuthorityState.READY_TO_TAKEOVER
        assert not node._controller_inhibited

        node._on_motor_ownership(ownership_message("motor", sequence=1))
        node._on_fan_ownership(
            ownership_message("fan", sequence=1, source=20)
        )
        node._aggregator.build_runtime_snapshot = lambda _now: active_snapshot(43)
        clock.value = 10.02
        node._control_tick()

        assert node._authority.state is AuthorityState.ACTIVE
        assert node._authority.authority_generation == 1
        assert node._authority.arming_cutoff_state_sequence == 43
        assert not node._controller_inhibited

        node._aggregator.build_runtime_snapshot = lambda _now: active_snapshot(44)
        clock.value = 10.03
        node._control_tick()
        envelope = node._command_pub.messages[-1]
        assert envelope.authority_epoch == 100
        assert envelope.generation == 1
        assert envelope.command_sequence == 0
        assert core.update_flight_command(
            envelope.authority_epoch,
            envelope.generation,
            envelope.command_sequence,
            envelope.fan_left,
            envelope.fan_right,
            now=1.03,
        ).success
        assert core.control_tick(1.04).state is FanControlState.FLIGHT_ACTIVE
        assert core.ownership.lease_phase is FlightLeasePhase.ACTIVE_COMMAND

        node._on_fan_safety(snapshot_message(core, sequence=2))
        assert node._authority.state is AuthorityState.ACTIVE
        assert not node._controller_inhibited
        node._publish_authority_status()
        status = node._authority_status_pub.messages[-1]
        assert status.authority_state == "ACTIVE"
        assert status.command_authority == "FLIGHT_CONTROL"
        assert status.actuation_allowed
    finally:
        node.destroy_node()


def test_exact_b1_estop_rollback_snapshot_is_truthful_and_adapter_accepts() -> None:
    core = flight_owned_fan_core()
    assert core.update_flight_command(
        100, 1, 0, 0.0, 0.0, now=1.03
    ).success

    assert core.update_e_stop(True, 1.04)
    assert core.revoke_flight_ownership(100, 1).success
    core.force_safe_stop("runtime rollback completion")

    snapshot = core.safety_snapshot
    assert snapshot.e_stop_latched
    assert snapshot.control_state == "EMERGENCY_STOP"
    assert not snapshot.passive_for_takeover
    assert not snapshot.manual_armed
    assert not snapshot.legacy_auto_active
    assert core.command_pwm == (800, 800)
    assert core.ownership.owner is FanCommandOwner.NONE

    accepted = SafetyReadbackAdapter().update_fan(
        snapshot_message(core), received_at=1.05
    )
    assert accepted.e_stop_latched
    assert accepted.control_state == "EMERGENCY_STOP"


def test_flight_adapter_remains_strict_about_inconsistent_estop_state() -> None:
    adapter = SafetyReadbackAdapter()
    inconsistent = fan_safety_message(
        e_stop_latched=True,
        control_state="SAFE_STOP",
        passive_for_takeover=False,
    )

    with pytest.raises(
        ValueError,
        match="fan e-stop latch conflicts with control state",
    ):
        adapter.update_fan(inconsistent, received_at=1.0)


def test_active_runtime_global_estop_revokes_both_and_preserves_fan_latch() -> None:
    from std_msgs.msg import Bool

    core = flight_owned_fan_core()
    clock = MutableClock()
    node = make_enabled_node(FakeController(), clock, authority_epoch=100)

    def revoke_fan(request):
        result = core.revoke_flight_ownership(
            int(request.authority_epoch),
            int(request.generation),
        )
        return response(
            request,
            success=result.success,
            reason=result.reason_code,
            sequence=6,
        )

    node._fan_revoke_client = FakeClient(revoke_fan)
    try:
        complete_handoff(node, clock, epoch=100)
        assert node._authority.state is AuthorityState.ACTIVE

        assert core.update_e_stop(True, 1.04)
        node._on_e_stop(Bool(data=True))

        assert node._authority.state is AuthorityState.INHIBITED
        assert node._controller_inhibited
        assert not node._command_dispatch_enabled
        assert node._motor_revoke_client.requests
        assert node._fan_revoke_client.requests
        assert node._command_pub.messages == []
        node._publish_authority_status()
        assert not node._authority_status_pub.messages[-1].actuation_allowed
        assert core.ownership.owner is FanCommandOwner.NONE
        assert core.e_stop_latched
        assert core.state is FanControlState.EMERGENCY_STOP
        assert core.command_pwm == (800, 800)
        SafetyReadbackAdapter().update_fan(
            snapshot_message(core), received_at=1.05
        )
    finally:
        node.destroy_node()


def test_new_runtime_still_inhibits_on_lower_level_estop_readback() -> None:
    from std_srvs.srv import Trigger

    clock = MutableClock()
    node = make_enabled_node(FakeController(), clock, authority_epoch=200)
    try:
        node._on_motor_safety(
            motor_safety_message(
                controller_state="EMERGENCY_STOP",
                public_control_mode="EMERGENCY_STOP",
                e_stop_latched=True,
            )
        )
        node._on_fan_safety(
            fan_safety_message(
                e_stop_latched=True,
                control_state="EMERGENCY_STOP",
                passive_for_takeover=False,
            )
        )
        assert node._on_prepare(Trigger.Request(), Trigger.Response()).success

        clock.value = 10.01
        node._control_tick()

        assert node._last_runtime_snapshot.flight_state.system.e_stop_active is True
        assert node._authority.state is AuthorityState.INHIBITED
        assert node._controller_inhibited
        assert node._last_error == "global_estop_active"
        assert not node._command_dispatch_enabled
        assert node._command_pub.messages == []
    finally:
        node.destroy_node()
