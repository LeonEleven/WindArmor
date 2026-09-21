"""Frozen ``ALG006-NORMALIZED-ALLOCATION-v1`` software fixture."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from windarmor_flight_control.algorithms.alg005_candidate_a import (
    ProcessObservation,
    RecoveryPhase,
)
from windarmor_flight_control.algorithms.alg006_candidate_a import (
    AllocationDisposition,
    AllocationObservation,
    AllocationStatus,
    NormalizedAllocator,
)


ABS_TOL = 1e-9
REL_TOL = 1e-6
REPEAT_COUNT = 3


@dataclass(frozen=True)
class AllocationCase:
    scenario_id: str
    process: ProcessObservation
    motor_authority: object
    left_fan_authority: object
    right_fan_authority: object
    expected: AllocationObservation


def process_outcome(
    intent: object,
    *,
    phase: RecoveryPhase = RecoveryPhase.STABLE,
    timeout_latched: bool = False,
) -> ProcessObservation:
    return ProcessObservation(
        final_process_intent=intent,
        phase=phase,
        timeout_latched=timeout_latched,
    )


def ordinary_expected(
    request: float,
    allocated: float,
    status: AllocationStatus,
) -> AllocationObservation:
    if request == 0.0:
        return AllocationObservation(
            status=AllocationStatus.NEUTRAL,
            disposition=AllocationDisposition.ORDINARY,
        )
    sign = 1.0 if request > 0.0 else -1.0
    return AllocationObservation(
        normalized_request=request,
        motor_pitch_group=sign * allocated,
        left_fan=allocated,
        right_fan=allocated,
        residual=request - sign * allocated,
        status=status,
        disposition=AllocationDisposition.ORDINARY,
    )


FAIL_CLOSED = AllocationObservation(
    status=AllocationStatus.FAIL_CLOSED,
    disposition=AllocationDisposition.INVALID_CONTRACT,
)
TIMEOUT = AllocationObservation(
    status=AllocationStatus.FAIL_CLOSED,
    disposition=AllocationDisposition.TIMEOUT,
    timeout_latched=True,
)


BASE_CASES = (
    AllocationCase(
        "ALG006-D00",
        process_outcome(0.0),
        1.0,
        1.0,
        1.0,
        ordinary_expected(0.0, 0.0, AllocationStatus.NEUTRAL),
    ),
    AllocationCase(
        "ALG006-D01P",
        process_outcome(+0.025),
        1.0,
        1.0,
        1.0,
        ordinary_expected(+0.25, 0.25, AllocationStatus.ALLOCATED),
    ),
    AllocationCase(
        "ALG006-D01N",
        process_outcome(-0.025),
        1.0,
        1.0,
        1.0,
        ordinary_expected(-0.25, 0.25, AllocationStatus.ALLOCATED),
    ),
    AllocationCase(
        "ALG006-D02P",
        process_outcome(+0.10),
        1.0,
        1.0,
        1.0,
        ordinary_expected(+1.0, 1.0, AllocationStatus.ALLOCATED),
    ),
    AllocationCase(
        "ALG006-D02N",
        process_outcome(-0.10),
        1.0,
        1.0,
        1.0,
        ordinary_expected(-1.0, 1.0, AllocationStatus.ALLOCATED),
    ),
    AllocationCase(
        "ALG006-D03P",
        process_outcome(+0.08),
        0.6,
        1.0,
        1.0,
        ordinary_expected(+0.8, 0.6, AllocationStatus.SATURATED),
    ),
    AllocationCase(
        "ALG006-D03N",
        process_outcome(-0.08),
        0.6,
        1.0,
        1.0,
        ordinary_expected(-0.8, 0.6, AllocationStatus.SATURATED),
    ),
    AllocationCase(
        "ALG006-D04L",
        process_outcome(+0.08),
        1.0,
        0.4,
        0.9,
        ordinary_expected(+0.8, 0.4, AllocationStatus.SATURATED),
    ),
    AllocationCase(
        "ALG006-D04R",
        process_outcome(+0.08),
        1.0,
        0.9,
        0.4,
        ordinary_expected(+0.8, 0.4, AllocationStatus.SATURATED),
    ),
)


ZERO_AUTHORITY_CASES = tuple(
    AllocationCase(
        f"ALG006-D05-{name}",
        process_outcome(+0.08),
        authorities[0],
        authorities[1],
        authorities[2],
        ordinary_expected(+0.8, 0.0, AllocationStatus.INFEASIBLE),
    )
    for name, authorities in (
        ("motor", (0.0, 1.0, 1.0)),
        ("left", (1.0, 0.0, 1.0)),
        ("right", (1.0, 1.0, 0.0)),
    )
)


INVALID_INTENT_CASES = tuple(
    AllocationCase(
        f"ALG006-D08-{name}",
        process_outcome(value),
        1.0,
        1.0,
        1.0,
        FAIL_CLOSED,
    )
    for name, value in (
        ("nan", math.nan),
        ("positive-inf", math.inf),
        ("negative-inf", -math.inf),
        ("positive-outside", +0.100001),
        ("negative-outside", -0.100001),
    )
)


_INVALID_AUTHORITIES = (
    ("none", None),
    ("unknown", "unknown"),
    ("nan", math.nan),
    ("positive-inf", math.inf),
    ("negative-inf", -math.inf),
    ("negative", -0.1),
    ("above-one", 1.1),
    ("bool-true", True),
    ("bool-false", False),
)
INVALID_AUTHORITY_CASES = tuple(
    AllocationCase(
        f"ALG006-D09-{resource}-{name}",
        process_outcome(+0.08),
        values[0],
        values[1],
        values[2],
        FAIL_CLOSED,
    )
    for resource, index in (("motor", 0), ("left", 1), ("right", 2))
    for name, value in _INVALID_AUTHORITIES
    for values in [tuple(value if item == index else 1.0 for item in range(3))]
)


TIMEOUT_CASE = AllocationCase(
    "ALG006-D10",
    process_outcome(
        0.0,
        phase=RecoveryPhase.TIMED_OUT,
        timeout_latched=True,
    ),
    1.0,
    1.0,
    1.0,
    TIMEOUT,
)


ATOMIC_CASES = (
    BASE_CASES
    + ZERO_AUTHORITY_CASES
    + INVALID_INTENT_CASES
    + INVALID_AUTHORITY_CASES
    + (TIMEOUT_CASE,)
)
CASE_BY_ID = {case.scenario_id: case for case in ATOMIC_CASES}


D06_SEQUENCE = (
    replace(
        CASE_BY_ID["ALG006-D03P"],
        scenario_id="ALG006-D06-positive",
        motor_authority=1.0,
        expected=ordinary_expected(+0.8, 0.8, AllocationStatus.ALLOCATED),
    ),
    replace(
        CASE_BY_ID["ALG006-D03N"],
        scenario_id="ALG006-D06-negative",
        motor_authority=1.0,
        expected=ordinary_expected(-0.8, 0.8, AllocationStatus.ALLOCATED),
    ),
)
D07_SEQUENCE = (
    replace(CASE_BY_ID["ALG006-D01P"], scenario_id="ALG006-D07-positive"),
    replace(CASE_BY_ID["ALG006-D00"], scenario_id="ALG006-D07-neutral"),
    replace(CASE_BY_ID["ALG006-D01N"], scenario_id="ALG006-D07-negative"),
)
D12_SEQUENCE = (
    BASE_CASES
    + ZERO_AUTHORITY_CASES
    + D06_SEQUENCE
    + D07_SEQUENCE
    + INVALID_INTENT_CASES
    + INVALID_AUTHORITY_CASES
    + (TIMEOUT_CASE,)
)


def run_case(
    case: AllocationCase,
    allocator: NormalizedAllocator | None = None,
) -> AllocationObservation:
    allocator = allocator or NormalizedAllocator()
    return allocator.allocate(
        case.process,
        case.motor_authority,
        case.left_fan_authority,
        case.right_fan_authority,
    )


def run_sequence(
    sequence: tuple[AllocationCase, ...],
    allocator: NormalizedAllocator | None = None,
) -> tuple[AllocationObservation, ...]:
    allocator = allocator or NormalizedAllocator()
    return tuple(run_case(case, allocator) for case in sequence)


def tolerance(left: float, right: float) -> float:
    return ABS_TOL + REL_TOL * max(abs(left), abs(right))
