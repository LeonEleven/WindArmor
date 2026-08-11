"""Pure command-authority identities and generation metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandAuthority(str, Enum):
    """The sole ordinary command owner selected by a future runtime."""

    NONE = "NONE"
    MANUAL = "MANUAL"
    LEGACY_AUTO = "LEGACY_AUTO"
    FLIGHT_CONTROL = "FLIGHT_CONTROL"


@dataclass(frozen=True)
class AuthorityGrant:
    """Immutable authority token metadata; it does not grant hardware access."""

    authority: CommandAuthority
    generation: int
    sequence: int
