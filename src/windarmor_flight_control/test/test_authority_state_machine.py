from dataclasses import FrozenInstanceError

import pytest

from windarmor_flight_control.core.authority import (
    AuthorityState,
    AuthorityStateMachine,
    AuthorityTransitionError,
    CommandAuthority,
    OwnershipDomain,
)


def machine(*, takeover=True):
    result = AuthorityStateMachine(takeover_supported=takeover)
    assert result.state is AuthorityState.DISABLED
    result.enable_dry_run()
    assert result.state is AuthorityState.DRY_RUN
    return result


def make_ready(authority, *, state_sequence=10):
    generation = authority.prepare()
    authority.observe_preflight(
        ready=True,
        reason="ready",
        current_runtime_state_sequence=state_sequence,
    )
    assert authority.state is AuthorityState.READY_TO_TAKEOVER
    return generation


def test_prepare_wait_ready_cancel_and_generation_never_reuses():
    authority = machine()
    first = authority.prepare()
    assert authority.state is AuthorityState.ARMING
    assert authority.prepare() == first
    authority.observe_preflight(ready=False, reason="waiting")
    assert authority.state is AuthorityState.ARMING
    authority.observe_preflight(
        ready=True,
        reason="ready",
        current_runtime_state_sequence=12,
    )
    assert authority.ready_state_sequence == 12
    assert authority.authority is CommandAuthority.NONE
    authority.cancel()
    assert authority.state is AuthorityState.DRY_RUN
    second = authority.prepare()
    assert second > first


def test_ready_safety_loss_latches_and_reset_requires_new_prepare():
    authority = machine()
    old = make_ready(authority)
    authority.observe_preflight(
        ready=False,
        reason="fan_disabled",
        current_runtime_state_sequence=11,
    )
    assert authority.state is AuthorityState.INHIBITED
    authority.observe_preflight(
        ready=True,
        reason="ready",
        current_runtime_state_sequence=12,
    )
    assert authority.state is AuthorityState.INHIBITED
    authority.reset_inhibit()
    assert authority.state is AuthorityState.DRY_RUN
    assert authority.attempt_generation is None
    new = authority.prepare()
    assert new > old


@pytest.mark.parametrize(
    "first,first_sequence,second,second_sequence,commit_sequence,expected",
    [
        (
            OwnershipDomain.MOTOR,
            100,
            OwnershipDomain.FAN,
            90,
            120,
            {OwnershipDomain.MOTOR: 100, OwnershipDomain.FAN: 90},
        ),
        (
            OwnershipDomain.FAN,
            200,
            OwnershipDomain.MOTOR,
            150,
            220,
            {OwnershipDomain.MOTOR: 150, OwnershipDomain.FAN: 200},
        ),
    ],
)
def test_owner_ack_order_is_diagnostic_and_explicit_commit_sets_cutoff(
    first,
    first_sequence,
    second,
    second_sequence,
    commit_sequence,
    expected,
):
    authority = machine()
    generation = make_ready(authority, state_sequence=80)

    assert authority.acknowledge_owner(
        first,
        generation,
        owner_observed_state_sequence=first_sequence,
    )
    assert authority.state is AuthorityState.READY_TO_TAKEOVER
    assert authority.acknowledge_owner(
        second,
        generation,
        owner_observed_state_sequence=second_sequence,
    )
    assert authority.state is AuthorityState.READY_TO_TAKEOVER
    assert authority.all_required_owners_acknowledged
    assert {
        ack.owner: ack.observed_state_sequence
        for ack in authority.owner_acknowledgements
    } == expected

    commit = authority.commit_active(
        generation=generation,
        current_runtime_state_sequence=commit_sequence,
    )
    assert commit.generation == generation
    assert commit.arming_cutoff_state_sequence == commit_sequence
    assert commit.controller_reset_required
    assert commit.discard_precommit_previews_required
    assert authority.arming_cutoff_state_sequence == commit_sequence
    assert authority.authority is CommandAuthority.FLIGHT_CONTROL
    with pytest.raises(FrozenInstanceError):
        commit.arming_cutoff_state_sequence = 121
    with pytest.raises(AuthorityTransitionError):
        authority.commit_active(
            generation=generation,
            current_runtime_state_sequence=commit_sequence + 1,
        )


def test_duplicate_stale_invalid_and_out_of_state_acks_are_rejected():
    authority = machine()
    generation = authority.prepare()
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=1,
    )
    authority.observe_preflight(
        ready=True,
        reason="ready",
        current_runtime_state_sequence=2,
    )
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        0,
        owner_observed_state_sequence=3,
    )
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation + 1,
        owner_observed_state_sequence=3,
    )
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=-1,
    )
    assert authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=3,
    )
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=4,
    )
    assert len(authority.owner_acknowledgements) == 1
    assert authority.arming_cutoff_state_sequence is None
    authority.cancel()
    assert not authority.acknowledge_owner(
        OwnershipDomain.FAN,
        generation,
        owner_observed_state_sequence=4,
    )
    current = make_ready(authority, state_sequence=5)
    assert not authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=6,
    )
    assert authority.owner_acknowledgements == ()
    authority.inhibit("test")
    assert not authority.acknowledge_owner(
        OwnershipDomain.FAN,
        current,
        owner_observed_state_sequence=6,
    )


def test_commit_rejects_missing_ack_old_generation_invalid_and_prebarrier_sequence():
    authority = machine()
    generation = make_ready(authority, state_sequence=50)
    authority.acknowledge_owner(
        OwnershipDomain.MOTOR,
        generation,
        owner_observed_state_sequence=51,
    )
    with pytest.raises(AuthorityTransitionError):
        authority.commit_active(
            generation=generation,
            current_runtime_state_sequence=52,
        )
    authority.acknowledge_owner(
        OwnershipDomain.FAN,
        generation,
        owner_observed_state_sequence=49,
    )
    for stale_generation, sequence in [
        (generation - 1, 52),
        (generation, -1),
        (generation, 49),
    ]:
        with pytest.raises(AuthorityTransitionError):
            authority.commit_active(
                generation=stale_generation,
                current_runtime_state_sequence=sequence,
            )
    assert authority.state is AuthorityState.READY_TO_TAKEOVER


def test_invalid_ready_sequence_inhibits_and_production_never_commits():
    authority = machine()
    authority.prepare()
    authority.observe_preflight(
        ready=True,
        reason="ready",
        current_runtime_state_sequence=-1,
    )
    assert authority.state is AuthorityState.INHIBITED

    production = machine(takeover=False)
    generation = make_ready(production, state_sequence=1)
    for owner in OwnershipDomain:
        assert not production.acknowledge_owner(
            owner,
            generation,
            owner_observed_state_sequence=2,
        )
    with pytest.raises(AuthorityTransitionError):
        production.commit_active(
            generation=generation,
            current_runtime_state_sequence=3,
        )
    assert production.state is AuthorityState.READY_TO_TAKEOVER
    assert production.authority is CommandAuthority.NONE
    assert production.authority_generation == 0


@pytest.mark.parametrize("event", ["safe_stop", "safety_loss"])
def test_active_safe_stop_or_safety_loss_revokes_and_inhibits(event):
    authority = machine()
    generation = make_ready(authority, state_sequence=3)
    for owner in OwnershipDomain:
        authority.acknowledge_owner(
            owner,
            generation,
            owner_observed_state_sequence=4,
        )
    authority.commit_active(
        generation=generation,
        current_runtime_state_sequence=5,
    )
    if event == "safe_stop":
        authority.handle_active_safe_stop()
    else:
        authority.handle_safety_loss("input_stale")
    assert authority.state is AuthorityState.INHIBITED
    assert authority.authority is CommandAuthority.NONE
    assert authority.authority_generation == 0
