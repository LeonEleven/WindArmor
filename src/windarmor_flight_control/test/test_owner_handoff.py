from types import SimpleNamespace

from windarmor_flight_control.core.authority import OwnershipDomain
from windarmor_flight_control.runtime.ownership import (
    HandoffState,
    OwnerHandoffCoordinator,
    OwnerReply,
    OwnershipReadbackTracker,
)


def reply(*, epoch=100, generation=1, success=True, sequence=1, reason="ok"):
    return OwnerReply(success, reason, epoch, generation, sequence)


def readback(domain, *, source=10, sequence=1, phase="FLIGHT_CONTROL", epoch=100):
    return SimpleNamespace(
        source_epoch=source,
        observation_sequence=sequence,
        owner_domain=domain.value,
        ownership_phase=phase,
        authority_present=phase.startswith("FLIGHT"),
        authority_epoch=epoch if phase.startswith("FLIGHT") else 0,
        generation=1 if phase.startswith("FLIGHT") else 0,
        last_accepted_flight_command_present=False,
        last_accepted_flight_command_sequence=0,
        last_valid_flight_command_age_sec=-1.0,
    )


def test_happy_two_phase_handoff_and_duplicate_response_rejected():
    coordinator = OwnerHandoffCoordinator()
    coordinator.start(authority_epoch=100, generation=1, runtime_state_sequence=20)
    assert coordinator.record_reserve(OwnershipDomain.FAN, reply(sequence=2))
    assert coordinator.record_reserve(OwnershipDomain.MOTOR, reply(sequence=3))
    assert not coordinator.record_reserve(OwnershipDomain.MOTOR, reply(sequence=4))
    coordinator.begin_commit()
    assert coordinator.record_commit(OwnershipDomain.MOTOR, reply(sequence=5))
    assert coordinator.record_commit(OwnershipDomain.FAN, reply(sequence=6))
    assert coordinator.state is HandoffState.OWNERS_COMMITTED


def test_partial_failure_and_old_epoch_reply_fail_closed():
    coordinator = OwnerHandoffCoordinator()
    coordinator.start(authority_epoch=200, generation=1, runtime_state_sequence=20)
    assert coordinator.record_reserve(OwnershipDomain.MOTOR, reply(epoch=200))
    assert not coordinator.record_reserve(OwnershipDomain.FAN, reply(epoch=100))
    assert coordinator.state is HandoffState.FAILED
    assert coordinator.revoke_domains == (OwnershipDomain.MOTOR,)


def test_owner_readback_rejects_old_process_epoch_and_sequence_replay():
    tracker = OwnershipReadbackTracker(OwnershipDomain.MOTOR)
    first = tracker.update(readback(OwnershipDomain.MOTOR, source=10, sequence=9))
    assert first.authority_epoch == 100
    restarted = tracker.update(readback(OwnershipDomain.MOTOR, source=20, sequence=1))
    assert restarted.source_epoch == 20
    for delayed in (
        readback(OwnershipDomain.MOTOR, source=10, sequence=10),
        readback(OwnershipDomain.MOTOR, source=20, sequence=1),
    ):
        try:
            tracker.update(delayed)
        except ValueError:
            pass
        else:
            raise AssertionError("stale ownership readback accepted")
