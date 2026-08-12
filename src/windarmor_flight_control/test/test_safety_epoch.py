import pytest

from windarmor_flight_control.runtime.safety_adapter import SafetyReadbackAdapter

from .runtime_helpers import fan_safety_message, motor_safety_message


@pytest.mark.parametrize(
    "kind,message_factory",
    [
        ("motor", motor_safety_message),
        ("fan", fan_safety_message),
    ],
)
def test_new_epoch_resets_sequence_and_stale_epoch_never_returns(kind, message_factory):
    adapter = SafetyReadbackAdapter()
    update = getattr(adapter, f"update_{kind}")

    update(message_factory(source_epoch=100, sequence=5000), 1.0)
    update(message_factory(source_epoch=200, sequence=1), 2.0)
    accepted = getattr(adapter, kind)
    assert accepted.source_epoch == 200
    assert accepted.sequence == 1

    with pytest.raises(ValueError, match="epoch moved backwards"):
        update(message_factory(source_epoch=100, sequence=5001), 3.0)
    assert getattr(adapter, kind) == accepted


@pytest.mark.parametrize(
    "kind,message_factory",
    [
        ("motor", motor_safety_message),
        ("fan", fan_safety_message),
    ],
)
def test_same_epoch_requires_strictly_increasing_positive_sequence(
    kind,
    message_factory,
):
    adapter = SafetyReadbackAdapter()
    update = getattr(adapter, f"update_{kind}")
    update(message_factory(source_epoch=100, sequence=2), 1.0)

    for source_epoch, sequence in [(100, 2), (100, 1), (0, 3), (100, 0)]:
        with pytest.raises(ValueError):
            update(
                message_factory(
                    source_epoch=source_epoch,
                    sequence=sequence,
                ),
                2.0,
            )


@pytest.mark.parametrize(
    "kind,message_factory",
    [
        ("motor", motor_safety_message),
        ("fan", fan_safety_message),
    ],
)
def test_first_observation_requires_positive_epoch_and_sequence(kind, message_factory):
    update = getattr(SafetyReadbackAdapter(), f"update_{kind}")
    for source_epoch, sequence in [(0, 1), (1, 0)]:
        with pytest.raises(ValueError):
            update(
                message_factory(
                    source_epoch=source_epoch,
                    sequence=sequence,
                ),
                1.0,
            )
