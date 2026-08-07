import threading

import pytest

from imu_cybergear_ros2.transport_recovery import (
    ReconnectPolicy,
    TransportEvent,
    TransportEventType,
    TransportRecoveryCoordinator,
    TransportRecoveryState,
)


def fault_event(generation=1, operation="read"):
    return TransportEvent(
        event_type=TransportEventType.READ_ERROR,
        backend="fake",
        operation=operation,
        message="injected disconnect",
        monotonic_timestamp=1.0,
        connection_generation=generation,
        exception=OSError("injected disconnect"),
    )


def policy(**overrides):
    values = dict(
        max_attempts=3,
        initial_delay_sec=0.5,
        max_delay_sec=1.0,
        backoff_multiplier=2.0,
    )
    values.update(overrides)
    return ReconnectPolicy(**values)


@pytest.mark.parametrize(
    "values",
    [
        dict(max_attempts=0),
        dict(max_attempts=1.5),
        dict(initial_delay_sec=-0.1),
        dict(initial_delay_sec=float("nan")),
        dict(max_delay_sec=0.1),
        dict(backoff_multiplier=0.9),
    ],
)
def test_reconnect_policy_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        policy(**values)


def test_backoff_is_bounded():
    item = policy(max_attempts=10)
    assert [item.delay_after_failure(i) for i in (1, 2, 3, 9)] == [
        0.5,
        1.0,
        1.0,
        1.0,
    ]


def test_disabled_runs_fault_response_and_close_without_connect_worker():
    operations = []
    closed = threading.Event()
    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=False,
        policy=policy(),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: operations.append("stop"),
        close_transport=lambda: (operations.append("close"), closed.set()),
        connect_once=lambda: operations.append("connect"),
        event_sink=lambda _event: None,
    )
    assert coordinator.request_recovery(fault_event())
    assert closed.wait(timeout=1.0)
    assert operations == ["stop", "close"]
    assert coordinator.snapshot().state is TransportRecoveryState.FAULT_LATCHED
    assert not coordinator.snapshot().worker_alive


def test_two_failures_then_success_uses_expected_backoff_and_stays_locked():
    operations = []
    delays = []
    events = []
    complete = threading.Event()
    generation = [1]
    attempts = [False, False, True]

    def connect():
        operations.append("connect")
        if not attempts.pop(0):
            raise OSError("still disconnected")
        generation[0] += 1

    def sink(event):
        events.append(event)
        if event.event_type is TransportEventType.RECONNECTED:
            complete.set()

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(),
        backend_name="fake",
        generation_fn=lambda: generation[0],
        stop_for_fault=lambda _event: operations.append("stop"),
        close_transport=lambda: operations.append("close"),
        connect_once=connect,
        event_sink=sink,
        wait_fn=lambda _event, delay: delays.append(delay) or False,
    )
    assert coordinator.request_recovery(fault_event())
    assert complete.wait(timeout=1.0)
    assert operations == ["stop", "close", "connect", "connect", "connect"]
    assert delays == [0.5, 1.0]
    snapshot = coordinator.snapshot()
    assert snapshot.state is TransportRecoveryState.RECONNECTED_LOCKED
    assert snapshot.attempt == 3
    assert [event.event_type for event in events] == [
        TransportEventType.RECONNECTING,
        TransportEventType.RECONNECTING,
        TransportEventType.RECONNECTING,
        TransportEventType.RECONNECTED,
    ]


def test_stale_close_failure_is_reported_but_does_not_block_reconnect():
    complete = threading.Event()
    events = []

    def sink(event):
        events.append(event)
        if event.event_type is TransportEventType.RECONNECTED:
            complete.set()

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(max_attempts=1),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: None,
        close_transport=lambda: (_ for _ in ()).throw(OSError("close failed")),
        connect_once=lambda: None,
        event_sink=sink,
    )
    assert coordinator.request_recovery(fault_event())
    assert complete.wait(timeout=1.0)
    assert [event.event_type for event in events] == [
        TransportEventType.CLOSE_ERROR,
        TransportEventType.RECONNECTING,
        TransportEventType.RECONNECTED,
    ]
    assert coordinator.snapshot().state is TransportRecoveryState.RECONNECTED_LOCKED


def test_exhaustion_stops_at_max_and_does_not_start_second_round():
    attempts = []
    failed = threading.Event()

    def connect():
        attempts.append(True)
        raise OSError("offline")

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: None,
        close_transport=lambda: None,
        connect_once=connect,
        event_sink=lambda event: (
            failed.set()
            if event.event_type is TransportEventType.RECONNECT_FAILED
            else None
        ),
        wait_fn=lambda _event, _delay: False,
    )
    assert coordinator.request_recovery(fault_event())
    assert failed.wait(timeout=1.0)
    assert len(attempts) == 3
    assert coordinator.snapshot().state is TransportRecoveryState.FAILED
    assert not coordinator.request_recovery(fault_event())
    assert len(attempts) == 3


def test_cancel_interrupts_backoff_without_later_connect():
    wait_entered = threading.Event()
    attempts = []

    def connect():
        attempts.append(True)
        raise OSError("offline")

    def controlled_wait(cancel_event, _delay):
        wait_entered.set()
        return cancel_event.wait(timeout=1.0)

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: None,
        close_transport=lambda: None,
        connect_once=connect,
        event_sink=lambda _event: None,
        wait_fn=controlled_wait,
    )
    assert coordinator.request_recovery(fault_event())
    assert wait_entered.wait(timeout=1.0)
    assert coordinator.disallow_and_cancel(join_timeout_sec=1.0)
    assert attempts == [True]
    assert coordinator.snapshot().state is TransportRecoveryState.CANCELLED
    assert not coordinator.snapshot().worker_alive


def test_cancel_during_connect_closes_late_success_instead_of_reopening():
    connect_entered = threading.Event()
    release_connect = threading.Event()
    closes = []
    emitted = []

    def connect():
        connect_entered.set()
        assert release_connect.wait(timeout=1.0)

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(max_attempts=1),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: None,
        close_transport=lambda: closes.append(True),
        connect_once=connect,
        event_sink=emitted.append,
    )
    assert coordinator.request_recovery(fault_event())
    assert connect_entered.wait(timeout=1.0)
    result = []
    canceller = threading.Thread(
        target=lambda: result.append(
            coordinator.disallow_and_cancel(join_timeout_sec=1.0)
        )
    )
    canceller.start()
    assert coordinator._cancel_event.wait(timeout=1.0)
    release_connect.set()
    canceller.join(timeout=1.0)
    assert result == [True]
    assert closes == [True, True]
    assert coordinator.snapshot().state is TransportRecoveryState.CANCELLED
    assert not any(
        event.event_type is TransportEventType.RECONNECTED for event in emitted
    )


def test_old_generation_event_is_ignored():
    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(),
        backend_name="fake",
        generation_fn=lambda: 2,
        stop_for_fault=lambda _event: pytest.fail("old fault must be ignored"),
        close_transport=lambda: pytest.fail("old fault must not close generation 2"),
        connect_once=lambda: pytest.fail("old fault must not reconnect"),
        event_sink=lambda _event: None,
    )
    assert not coordinator.request_recovery(fault_event(generation=1))
    assert coordinator.snapshot().state is TransportRecoveryState.IDLE


def test_concurrent_duplicate_faults_create_one_worker_and_one_stop_batch():
    connect_entered = threading.Event()
    release_connect = threading.Event()
    stop_count = []

    def connect():
        connect_entered.set()
        assert release_connect.wait(timeout=1.0)

    coordinator = TransportRecoveryCoordinator(
        reconnect_enabled=True,
        policy=policy(max_attempts=1),
        backend_name="fake",
        generation_fn=lambda: 1,
        stop_for_fault=lambda _event: stop_count.append(True),
        close_transport=lambda: None,
        connect_once=connect,
        event_sink=lambda _event: None,
    )
    barrier = threading.Barrier(4)
    results = []

    def request():
        barrier.wait()
        results.append(coordinator.request_recovery(fault_event()))

    workers = [threading.Thread(target=request) for _ in range(3)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=1.0)
    assert results.count(True) == 1
    assert results.count(False) == 2
    assert connect_entered.wait(timeout=1.0)
    release_connect.set()
    recovery_worker = coordinator._worker
    if recovery_worker is not None:
        recovery_worker.join(timeout=1.0)
    assert stop_count == [True]
    assert coordinator.snapshot().state is TransportRecoveryState.RECONNECTED_LOCKED
