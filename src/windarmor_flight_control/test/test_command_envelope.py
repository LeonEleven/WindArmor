from dataclasses import FrozenInstanceError
import math

import pytest

from windarmor_flight_control.core.envelope import (
    CommandEnvelopeSequencer,
    FlightCommandEnvelope,
    validate_command_envelope,
)
from windarmor_flight_control.core.models import FanCommand, FlightCommand
from windarmor_flight_control.core.validation import FlightValidationError


NAMES = ("axis_a", "axis_b")


def normal(value=0.0):
    return FlightCommand(
        motor_positions_rad={name: value for name in NAMES},
        fan_commands=FanCommand(0.0, 0.0),
    )


def envelope(**overrides):
    values = dict(
        generation=3,
        command_sequence=1,
        state_sequence=11,
        produced_at_sec=5.0,
        command=normal(),
    )
    values.update(overrides)
    return FlightCommandEnvelope(**values)


def validate(value, **overrides):
    args = dict(
        expected_generation=3,
        last_command_sequence=0,
        arming_cutoff_state_sequence=10,
        required_motor_names=NAMES,
    )
    args.update(overrides)
    validate_command_envelope(value, **args)


def test_current_generation_increasing_sequence_and_commands_validate():
    validate(envelope())
    validate(envelope(command=FlightCommand.safe_stop()))


@pytest.mark.parametrize(
    "value",
    [
        envelope(generation=0),
        envelope(generation=2),
        envelope(command_sequence=0),
        envelope(command_sequence=-1),
        envelope(state_sequence=10),
        envelope(state_sequence=9),
        envelope(produced_at_sec=math.nan),
        envelope(produced_at_sec=math.inf),
        envelope(
            command=FlightCommand(
                motor_positions_rad={"axis_a": 0.0},
                fan_commands=FanCommand(0.0, 0.0),
            )
        ),
        envelope(
            command=FlightCommand(
                motor_positions_rad={"axis_a": 0.0, "axis_b": 0.0},
                fan_commands=None,
                request_safe_stop=True,
            )
        ),
    ],
)
def test_invalid_generation_sequence_barrier_time_or_payload_rejected(value):
    with pytest.raises(FlightValidationError):
        validate(value)


def test_envelope_is_immutable_and_sequencer_never_reuses_pre_cutoff_target():
    value = envelope()
    with pytest.raises(FrozenInstanceError):
        value.generation = 4

    sequencer = CommandEnvelopeSequencer(NAMES)
    sequencer.activate(generation=8, state_sequence_cutoff=20)
    with pytest.raises(FlightValidationError):
        sequencer.build(
            state_sequence=20,
            produced_at_sec=2.0,
            command=normal(0.5),
        )
    first = sequencer.build(
        state_sequence=21,
        produced_at_sec=2.1,
        command=normal(0.7),
    )
    assert first.command_sequence == 0
    assert set(first.command.motor_positions_rad.values()) == {0.7}
    sequencer.invalidate()
    with pytest.raises(FlightValidationError):
        sequencer.build(
            state_sequence=22,
            produced_at_sec=2.2,
            command=normal(0.7),
        )
