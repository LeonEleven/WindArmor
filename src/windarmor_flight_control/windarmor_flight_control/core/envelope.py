"""Generation and post-grant barriers for future actuator command envelopes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .models import FlightCommand
from .validation import FlightValidationError, validate_flight_command


@dataclass(frozen=True)
class FlightCommandEnvelope:
    generation: int
    command_sequence: int
    state_sequence: int
    produced_at_sec: float
    command: FlightCommand


def validate_command_envelope(
    envelope: FlightCommandEnvelope,
    *,
    expected_generation: int,
    last_command_sequence: int | None,
    arming_cutoff_state_sequence: int,
    required_motor_names: Iterable[str],
) -> None:
    issues: list[str] = []
    if not isinstance(envelope, FlightCommandEnvelope):
        raise FlightValidationError(("envelope must be a FlightCommandEnvelope",))
    generation_valid = (
        isinstance(envelope.generation, int)
        and not isinstance(envelope.generation, bool)
    )
    if not generation_valid or envelope.generation <= 0:
        issues.append("envelope generation 0 is never authoritative")
    if envelope.generation != expected_generation:
        issues.append("envelope generation does not match current authority")
    command_sequence_valid = (
        isinstance(envelope.command_sequence, int)
        and not isinstance(envelope.command_sequence, bool)
    )
    if not command_sequence_valid or envelope.command_sequence < 0:
        issues.append("command sequence must be non-negative")
    if (
        command_sequence_valid
        and last_command_sequence is not None
        and envelope.command_sequence <= last_command_sequence
    ):
        issues.append("command sequence must strictly increase")
    state_sequence_valid = (
        isinstance(envelope.state_sequence, int)
        and not isinstance(envelope.state_sequence, bool)
    )
    if (
        not state_sequence_valid
        or envelope.state_sequence <= arming_cutoff_state_sequence
    ):
        issues.append("command requires state newer than the arming cutoff")
    if (
        isinstance(envelope.produced_at_sec, bool)
        or not isinstance(envelope.produced_at_sec, (int, float))
        or not math.isfinite(envelope.produced_at_sec)
    ):
        issues.append("produced_at_sec must be finite")
    try:
        validate_flight_command(envelope.command, required_motor_names)
    except FlightValidationError as exc:
        issues.extend(exc.issues)
    if issues:
        raise FlightValidationError(issues)


class CommandEnvelopeSequencer:
    """Creates no envelope until a post-grant FlightState is supplied."""

    def __init__(self, required_motor_names: Iterable[str]) -> None:
        self._required_motor_names = tuple(required_motor_names)
        self.invalidate()

    def activate(self, *, generation: int, state_sequence_cutoff: int) -> None:
        if generation <= 0 or state_sequence_cutoff < 0:
            raise ValueError("active envelope metadata is invalid")
        self._generation = generation
        self._cutoff = state_sequence_cutoff
        self._last_sequence = None

    def invalidate(self) -> None:
        self._generation: int | None = None
        self._cutoff: int | None = None
        self._last_sequence: int | None = None

    def build(
        self,
        *,
        state_sequence: int,
        produced_at_sec: float,
        command: FlightCommand,
    ) -> FlightCommandEnvelope:
        if self._generation is None or self._cutoff is None:
            raise FlightValidationError(("no active authority generation",))
        sequence = 0 if self._last_sequence is None else self._last_sequence + 1
        envelope = FlightCommandEnvelope(
            generation=self._generation,
            command_sequence=sequence,
            state_sequence=state_sequence,
            produced_at_sec=produced_at_sec,
            command=command,
        )
        validate_command_envelope(
            envelope,
            expected_generation=self._generation,
            last_command_sequence=self._last_sequence,
            arming_cutoff_state_sequence=self._cutoff,
            required_motor_names=self._required_motor_names,
        )
        self._last_sequence = sequence
        return envelope
