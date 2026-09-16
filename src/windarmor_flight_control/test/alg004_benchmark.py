"""Frozen ALG-004 Profile v1 fixture runner and independent metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Protocol


ABS_TOL = 1e-9
REL_TOL = 1e-6
EPS_SIGN = 2e-3
REPEAT_COUNT = 3
U = 0.10
S = 2.0


class Alg004ShapingSeam(Protocol):
    def reset(self) -> None: ...

    def update(self, requested_intent: float, dt: float) -> float: ...


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    requests: tuple[float, ...]
    transition_index: int = 0


def mirror_requests(requests: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(-value for value in requests)


_P01 = (0.03,) * 6
_P02 = (0.07,) * 6
_P03 = (0.10,) * 6
_P04 = (0.20,) * 6
_S01P = (0.0,) * 3 + (0.07,) * 6
_S02P = (0.0,) * 3 + (0.20,) * 6
_S03P = (0.20,) * 6 + (-0.20,) * 12
_S04P = (0.20, -0.20) * 6

SCENARIOS = (
    Scenario("ALG004-N00", (0.0,) * 6),
    Scenario("ALG004-P01", _P01),
    Scenario("ALG004-N01", mirror_requests(_P01)),
    Scenario("ALG004-P02", _P02),
    Scenario("ALG004-N02", mirror_requests(_P02)),
    Scenario("ALG004-P03", _P03),
    Scenario("ALG004-N03", mirror_requests(_P03)),
    Scenario("ALG004-P04", _P04),
    Scenario("ALG004-N04", mirror_requests(_P04)),
    Scenario("ALG004-S01P", _S01P, 3),
    Scenario("ALG004-S01N", mirror_requests(_S01P), 3),
    Scenario("ALG004-S02P", _S02P, 3),
    Scenario("ALG004-S02N", mirror_requests(_S02P), 3),
    Scenario("ALG004-S03P", _S03P, 6),
    Scenario("ALG004-S03N", mirror_requests(_S03P), 6),
    Scenario("ALG004-S04P", _S04P),
    Scenario("ALG004-S04N", mirror_requests(_S04P)),
)
SCENARIO_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}

STEADY_SCENARIO_IDS = tuple(
    f"ALG004-{sign}{index:02d}"
    for index in range(1, 5)
    for sign in ("P", "N")
)
STEP_SCENARIO_IDS = STEADY_SCENARIO_IDS + (
    "ALG004-S01P",
    "ALG004-S01N",
    "ALG004-S02P",
    "ALG004-S02N",
)
MIRROR_PAIRS = (
    ("ALG004-P01", "ALG004-N01"),
    ("ALG004-P02", "ALG004-N02"),
    ("ALG004-P03", "ALG004-N03"),
    ("ALG004-P04", "ALG004-N04"),
    ("ALG004-S01P", "ALG004-S01N"),
    ("ALG004-S02P", "ALG004-S02N"),
    ("ALG004-S03P", "ALG004-S03N"),
    ("ALG004-S04P", "ALG004-S04N"),
)
DT_VARIANTS = ("ALG004-D00A", "ALG004-D00B", "ALG004-D00C")


def dt_at(variant: str, index: int) -> float:
    if variant == "ALG004-D00A":
        return 0.020
    if variant == "ALG004-D00B":
        return 0.037
    if variant == "ALG004-D00C":
        return 0.020 if index % 2 == 0 else 0.037
    raise ValueError(f"unknown dt variant: {variant}")


def clamped_target(requested_intent: float) -> float:
    if (
        isinstance(requested_intent, bool)
        or not isinstance(requested_intent, (int, float))
        or not math.isfinite(float(requested_intent))
    ):
        raise ValueError("requested intent must be a finite number")
    return max(-U, min(U, float(requested_intent)))


def tolerance(left: float, right: float) -> float:
    return ABS_TOL + REL_TOL * max(abs(left), abs(right))


def total_variation(values: tuple[float, ...]) -> float:
    return sum(
        abs(current - previous)
        for previous, current in zip(values, values[1:])
    )


def effective_sign_reversals(values: tuple[float, ...]) -> int:
    significant = [value for value in values if abs(value) > EPS_SIGN]
    return sum(
        math.copysign(1.0, current) != math.copysign(1.0, previous)
        for previous, current in zip(significant, significant[1:])
    )


def signed_tail_mean(values: tuple[float, ...], count: int = 3) -> float:
    if count <= 0 or len(values) < count:
        raise ValueError("tail count must be positive and available")
    return sum(values[-count:]) / count


def run_scenario(
    seam: Alg004ShapingSeam,
    scenario: Scenario,
    dt_variant: str,
) -> tuple[float, ...]:
    seam.reset()
    return tuple(
        seam.update(request, dt_at(dt_variant, index))
        for index, request in enumerate(scenario.requests)
    )


def collect_repeated_runs(
    seam_factory: Callable[[], Alg004ShapingSeam],
    scenario: Scenario,
    dt_variant: str,
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        run_scenario(seam_factory(), scenario, dt_variant)
        for _ in range(REPEAT_COUNT)
    )


def _frames_to_fraction(
    scenario: Scenario,
    values: tuple[float, ...],
    dt_variant: str,
    fraction: float,
) -> tuple[int, float]:
    target = clamped_target(scenario.requests[scenario.transition_index])
    if target == 0.0:
        raise ValueError("response metric requires a nonzero transition target")
    expected_sign = math.copysign(1.0, target)
    threshold = fraction * abs(target)
    for offset, value in enumerate(values[scenario.transition_index :]):
        if (
            math.copysign(1.0, value) == expected_sign
            and abs(value) + ABS_TOL >= threshold
        ):
            frames = offset + 1
            elapsed = sum(
                dt_at(dt_variant, scenario.transition_index + index)
                for index in range(frames)
            )
            return frames, elapsed
    raise AssertionError(f"{fraction:.0%} response threshold was not reached")


def frames_to_50pct(
    scenario: Scenario,
    values: tuple[float, ...],
    dt_variant: str,
) -> int:
    return _frames_to_fraction(scenario, values, dt_variant, 0.50)[0]


def synthetic_elapsed_time_to_50pct(
    scenario: Scenario,
    values: tuple[float, ...],
    dt_variant: str,
) -> float:
    return _frames_to_fraction(scenario, values, dt_variant, 0.50)[1]


def frames_time_to_80pct(
    scenario: Scenario,
    values: tuple[float, ...],
    dt_variant: str,
) -> tuple[int, float]:
    return _frames_to_fraction(scenario, values, dt_variant, 0.80)


def max_mirror_error(
    positive: tuple[float, ...],
    negative: tuple[float, ...],
) -> float:
    return max(abs(left + right) for left, right in zip(positive, negative))


def max_repeatability_delta(
    runs: tuple[tuple[float, ...], ...],
) -> float:
    return max(
        abs(left - right)
        for first_index, first in enumerate(runs)
        for second in runs[first_index + 1 :]
        for left, right in zip(first, second)
    )


def max_abs_output(values: tuple[float, ...]) -> float:
    return max(abs(value) for value in values)


def max_observed_slew_rate(
    values: tuple[float, ...],
    dt_variant: str,
) -> float:
    previous = 0.0
    observed = []
    for index, value in enumerate(values):
        observed.append(abs(value - previous) / dt_at(dt_variant, index))
        previous = value
    return max(observed)


def metrics(
    scenario: Scenario,
    values: tuple[float, ...],
    dt_variant: str,
) -> dict[str, float | int]:
    result: dict[str, float | int] = {
        "tv": total_variation(values),
        "effective_sign_reversal": effective_sign_reversals(values),
        "signed_tail_mean": signed_tail_mean(values),
        "max_abs_output": max_abs_output(values),
        "max_observed_slew_rate": max_observed_slew_rate(values, dt_variant),
    }
    target = clamped_target(scenario.requests[scenario.transition_index])
    if target != 0.0:
        frames_80, elapsed_80 = frames_time_to_80pct(
            scenario,
            values,
            dt_variant,
        )
        result.update(
            {
                "frames_to_50pct": frames_to_50pct(
                    scenario,
                    values,
                    dt_variant,
                ),
                "synthetic_elapsed_time_to_50pct": (
                    synthetic_elapsed_time_to_50pct(
                        scenario,
                        values,
                        dt_variant,
                    )
                ),
                "frames_to_80pct": frames_80,
                "synthetic_elapsed_time_to_80pct": elapsed_80,
            }
        )
    return result
