"""Reusable frozen ALG-003 Profile v1 sequence runner and metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Protocol


ABS_TOL = 1e-9
REL_TOL = 1e-6
EPS_SIGN = 2e-3
REPEAT_COUNT = 3


class Alg003LevelASeam(Protocol):
    def reset(self) -> None: ...

    def update(self, pitch: float, rate: float, dt: float) -> float: ...


Sample = tuple[float, float]


@dataclass(frozen=True)
class NoiseScenario:
    scenario_id: str
    priming: Sample
    samples: tuple[Sample, ...]


@dataclass(frozen=True)
class SignalScenario:
    scenario_id: str
    samples: tuple[Sample, ...]
    transition_index: int


_Q01_HALF = (
    (0.003, 0.03),
    (-0.003, -0.03),
    (0.004, 0.04),
    (-0.004, -0.04),
    (0.002, 0.02),
    (-0.002, -0.02),
)
_Q02_HALF = (
    (0.053, 0.03),
    (0.047, -0.03),
    (0.054, 0.04),
    (0.046, -0.04),
    (0.052, 0.02),
    (0.048, -0.02),
)


def mirror_samples(samples: tuple[Sample, ...]) -> tuple[Sample, ...]:
    return tuple((-pitch, -rate) for pitch, rate in samples)


NOISE_SCENARIOS = (
    NoiseScenario("ALG003-Q01", (0.0, 0.0), _Q01_HALF * 2),
    NoiseScenario("ALG003-Q02", (0.05, 0.0), _Q02_HALF * 2),
    NoiseScenario(
        "ALG003-Q03",
        (-0.05, 0.0),
        mirror_samples(_Q02_HALF * 2),
    ),
    NoiseScenario(
        "ALG003-Q04",
        (0.0, 0.0),
        (
            (0.0, 0.04),
            (0.0, -0.04),
            (0.0, 0.03),
            (0.0, -0.03),
            (0.0, 0.02),
            (0.0, -0.02),
        )
        * 2,
    ),
)
NOISE_BY_ID = {scenario.scenario_id: scenario for scenario in NOISE_SCENARIOS}

_S01 = _Q01_HALF + _Q01_HALF[:2] + ((0.05, 0.20),) * 6
_S03P = ((0.05, 0.0),) * 6 + ((0.05, 0.20),) * 6
_S04P = ((0.05, 0.0),) * 6 + ((0.05, -0.20),) * 6
SIGNAL_SCENARIOS = (
    SignalScenario("ALG003-S01", _S01, 8),
    SignalScenario("ALG003-S02", mirror_samples(_S01), 8),
    SignalScenario("ALG003-S03P", _S03P, 6),
    SignalScenario("ALG003-S03N", mirror_samples(_S03P), 6),
    SignalScenario("ALG003-S04P", _S04P, 6),
    SignalScenario("ALG003-S04N", mirror_samples(_S04P), 6),
)
SIGNAL_BY_ID = {scenario.scenario_id: scenario for scenario in SIGNAL_SCENARIOS}

DT_VARIANTS = ("ALG003-D00A", "ALG003-D00B", "ALG003-D00C")


def dt_at(variant: str, index: int) -> float:
    if variant == "ALG003-D00A":
        return 0.020
    if variant == "ALG003-D00B":
        return 0.037
    if variant == "ALG003-D00C":
        return 0.020 if index % 2 == 0 else 0.037
    raise ValueError(f"unknown dt variant: {variant}")


def tolerance(left: float, right: float) -> float:
    return ABS_TOL + REL_TOL * max(abs(left), abs(right))


def raw_intent(pitch: float, rate: float) -> float:
    """Implement the frozen baseline directly, independent of production code."""

    result = -1.0 * pitch - 0.1 * rate
    if not math.isfinite(result):
        raise ValueError("raw baseline must be finite")
    return result


def raw_sequence(samples: tuple[Sample, ...]) -> tuple[float, ...]:
    return tuple(raw_intent(pitch, rate) for pitch, rate in samples)


def total_variation(values: tuple[float, ...]) -> float:
    return sum(abs(current - previous) for previous, current in zip(values, values[1:]))


def peak(values: tuple[float, ...]) -> float:
    return max(abs(value) for value in values)


def mean_absolute_activity(values: tuple[float, ...]) -> float:
    return sum(abs(value) for value in values) / len(values)


def peak_to_peak(values: tuple[float, ...]) -> float:
    return max(values) - min(values)


def effective_sign_reversals(values: tuple[float, ...]) -> int:
    significant = [value for value in values if abs(value) > EPS_SIGN]
    return sum(
        math.copysign(1.0, current) != math.copysign(1.0, previous)
        for previous, current in zip(significant, significant[1:])
    )


def metrics(values: tuple[float, ...]) -> dict[str, float | int]:
    return {
        "tv": total_variation(values),
        "reversal": effective_sign_reversals(values),
        "peak": peak(values),
        "maa": mean_absolute_activity(values),
        "p2p": peak_to_peak(values),
    }


def run_noise_scenario(
    seam: Alg003LevelASeam,
    scenario: NoiseScenario,
    dt_variant: str,
) -> tuple[float, ...]:
    seam.reset()
    seam.update(*scenario.priming, dt_at(dt_variant, 0))
    return tuple(
        seam.update(pitch, rate, dt_at(dt_variant, index))
        for index, (pitch, rate) in enumerate(scenario.samples)
    )


def run_signal_scenario(
    seam: Alg003LevelASeam,
    scenario: SignalScenario,
    dt_variant: str,
) -> tuple[float, ...]:
    seam.reset()
    return tuple(
        seam.update(pitch, rate, dt_at(dt_variant, index))
        for index, (pitch, rate) in enumerate(scenario.samples)
    )


def collect_repeated_runs(
    seam_factory: Callable[[], Alg003LevelASeam],
    scenario: NoiseScenario | SignalScenario,
    dt_variant: str,
) -> tuple[tuple[float, ...], ...]:
    runner = (
        run_noise_scenario
        if isinstance(scenario, NoiseScenario)
        else run_signal_scenario
    )
    return tuple(
        runner(seam_factory(), scenario, dt_variant)
        for _ in range(REPEAT_COUNT)
    )


def signed_mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)


def response_metrics(
    scenario: SignalScenario,
    values: tuple[float, ...],
    dt_variant: str,
) -> tuple[int, float]:
    meaningful = values[scenario.transition_index :]
    raw_tail = raw_sequence(scenario.samples)[scenario.transition_index]
    expected_sign = math.copysign(1.0, raw_tail)
    for offset, value in enumerate(meaningful):
        if (
            math.copysign(1.0, value) == expected_sign
            and abs(value) >= 0.035
        ):
            frames = offset + 1
            elapsed = sum(
                dt_at(dt_variant, scenario.transition_index + index)
                for index in range(frames)
            )
            return frames, elapsed
    raise AssertionError("meaningful response threshold was not reached")


def steady_mean(values: tuple[float, ...]) -> float:
    return signed_mean(values[-3:])


def trend_means(
    scenario: SignalScenario,
    values: tuple[float, ...],
) -> tuple[float, float]:
    before = signed_mean(
        values[scenario.transition_index - 3 : scenario.transition_index]
    )
    after = signed_mean(values[-3:])
    return before, after


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
