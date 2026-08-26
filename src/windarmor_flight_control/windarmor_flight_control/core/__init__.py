"""稳定的纯 Python 飞控 API。"""

from .authority import (
    AuthorityGrant,
    AuthorityState,
    AuthorityStateMachine,
    CommandAuthority,
    OwnershipDomain,
)
from .controller import FlightController
from .envelope import (
    CommandEnvelopeSequencer,
    FlightCommandEnvelope,
    validate_command_envelope,
)
from .models import (
    FanChannelState,
    FanCommand,
    FanSystemState,
    FlightCommand,
    FlightState,
    ImuState,
    MotorState,
    Quaternion,
    SystemState,
    Vector3,
)

__all__ = [
    "AuthorityGrant",
    "AuthorityState",
    "AuthorityStateMachine",
    "CommandAuthority",
    "CommandEnvelopeSequencer",
    "FanChannelState",
    "FanCommand",
    "FanSystemState",
    "FlightCommand",
    "FlightCommandEnvelope",
    "FlightController",
    "FlightState",
    "ImuState",
    "MotorState",
    "OwnershipDomain",
    "Quaternion",
    "SystemState",
    "Vector3",
    "validate_command_envelope",
]
