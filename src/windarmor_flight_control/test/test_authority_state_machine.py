import pytest

from windarmor_flight_control.core.authority import (
    AuthorityState,
    AuthorityStateMachine,
    CommandAuthority,
    OwnershipDomain,
)


def machine(*, takeover=True):
    result = AuthorityStateMachine(takeover_supported=takeover)
    assert result.state is AuthorityState.DISABLED
    result.enable_dry_run()
    assert result.state is AuthorityState.DRY_RUN
    return result


def test_prepare_wait_ready_cancel_and_generation_never_reuses():
    authority = machine()
    first = authority.prepare()
    assert authority.state is AuthorityState.ARMING
    assert authority.prepare() == first
    authority.observe_preflight(ready=False, reason="waiting")
    assert authority.state is AuthorityState.ARMING
    authority.observe_preflight(ready=True, reason="ready")
    assert authority.state is AuthorityState.READY_TO_TAKEOVER
    assert authority.authority is CommandAuthority.NONE
    authority.cancel()
    assert authority.state is AuthorityState.DRY_RUN
    second = authority.prepare()
    assert second > first


def test_ready_safety_loss_latches_and_reset_requires_new_prepare():
    authority = machine()
    old = authority.prepare()
    authority.observe_preflight(ready=True, reason="ready")
    authority.observe_preflight(ready=False, reason="fan_disabled")
    assert authority.state is AuthorityState.INHIBITED
    authority.observe_preflight(ready=True, reason="ready")
    assert authority.state is AuthorityState.INHIBITED
    authority.reset_inhibit()
    assert authority.state is AuthorityState.DRY_RUN
    assert authority.attempt_generation is None
    new = authority.prepare()
    assert new > old


def test_only_complete_current_fake_ack_enters_active_and_resets_once():
    authority = machine()
    generation = authority.prepare()
    authority.observe_preflight(ready=True, reason="ready")
    resets = []
    reset = lambda: resets.append("reset")
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        state_sequence=20,
        reset_controller=reset,
    )
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        state_sequence=20,
        reset_controller=reset,
    )
    assert resets == []
    assert authority.acknowledge_owner(
        OwnershipDomain.FAN,
        generation,
        state_sequence=21,
        reset_controller=reset,
    )
    assert resets == ["reset"]
    assert authority.state is AuthorityState.ACTIVE
    assert authority.authority is CommandAuthority.FLIGHT_CONTROL
    assert authority.authority_generation == generation
    assert authority.arming_cutoff_state_sequence == 21


def test_old_generation_ack_and_production_unsupported_path_reject():
    authority = machine()
    old = authority.prepare()
    authority.cancel()
    current = authority.prepare()
    authority.observe_preflight(ready=True, reason="ready")
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        old,
        state_sequence=1,
        reset_controller=lambda: pytest.fail("must not reset"),
    )
    assert current != old

    production = machine(takeover=False)
    generation = production.prepare()
    production.observe_preflight(ready=True, reason="ready")
    for owner in OwnershipDomain:
        assert not production.acknowledge_owner(
            owner,
            generation,
            state_sequence=1,
            reset_controller=lambda: pytest.fail("must not reset"),
        )
    assert production.state is AuthorityState.READY_TO_TAKEOVER


@pytest.mark.parametrize("event", ["safe_stop", "safety_loss"])
def test_active_safe_stop_or_safety_loss_revokes_and_inhibits(event):
    authority = machine()
    generation = authority.prepare()
    authority.observe_preflight(ready=True, reason="ready")
    for owner in OwnershipDomain:
        authority.acknowledge_owner(
            owner,
            generation,
            state_sequence=4,
            reset_controller=lambda: None,
        )
    if event == "safe_stop":
        authority.handle_active_safe_stop()
    else:
        authority.handle_safety_loss("input_stale")
    assert authority.state is AuthorityState.INHIBITED
    assert authority.authority is CommandAuthority.NONE
    assert authority.authority_generation == 0
