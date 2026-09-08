"""可供 ALG-001 候选复用的 Profile v1 纯软件断言辅助函数。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


ABS_TOL = 1e-9
REL_TOL = 1e-6
REPEAT_COUNT = 3


@dataclass(frozen=True)
class Alg001NormalScenario:
    scenario_id: str
    relative_pitch_rad: float
    pitch_error_rad: float


NORMAL_SCENARIOS = (
    Alg001NormalScenario("ALG001-N00", 0.0, 0.0),
    Alg001NormalScenario("ALG001-P01", 0.05, -0.05),
    Alg001NormalScenario("ALG001-P02", 0.10, -0.10),
    Alg001NormalScenario("ALG001-N01", -0.05, 0.05),
    Alg001NormalScenario("ALG001-N02", -0.10, 0.10),
)


class Alg001LevelAAdapter(Protocol):
    def reset(self) -> None: ...

    def pitch_feedback_intent(self, relative_pitch_rad: float) -> float: ...


def collect_level_a_results(
    adapter: Alg001LevelAAdapter,
) -> dict[str, tuple[float, ...]]:
    """按 Profile v1 在每次独立运行前 reset，并重复至少三次。"""

    results: dict[str, tuple[float, ...]] = {}
    for scenario in NORMAL_SCENARIOS:
        repetitions: list[float] = []
        for _ in range(REPEAT_COUNT):
            adapter.reset()
            repetitions.append(
                adapter.pitch_feedback_intent(scenario.relative_pitch_rad)
            )
        results[scenario.scenario_id] = tuple(repetitions)
    return results


def assert_normal_scenario(
    scenario: Alg001NormalScenario,
    feedback: float,
    *,
    kp_intent_per_rad: float,
) -> None:
    assert math.isfinite(feedback)
    if scenario.pitch_error_rad == 0.0:
        assert abs(feedback) <= ABS_TOL
        return
    assert math.copysign(1.0, feedback) == math.copysign(
        1.0,
        scenario.pitch_error_rad,
    )
    assert abs(feedback) > ABS_TOL
    observed_gain = feedback / scenario.pitch_error_rad
    assert math.isfinite(observed_gain)
    assert observed_gain > 0.0
    assert math.isclose(
        observed_gain,
        kp_intent_per_rad,
        abs_tol=ABS_TOL,
        rel_tol=REL_TOL,
    )


def assert_profile_relationships(
    results: dict[str, tuple[float, ...]],
    *,
    kp_intent_per_rad: float,
) -> None:
    """断言 Profile v1 的比例、对称、单调和重复性关系。"""

    assert set(results) == {scenario.scenario_id for scenario in NORMAL_SCENARIOS}
    scenarios = {scenario.scenario_id: scenario for scenario in NORMAL_SCENARIOS}
    first: dict[str, float] = {}
    for scenario_id, repetitions in results.items():
        assert len(repetitions) >= REPEAT_COUNT
        assert all(
            math.isclose(
                repetitions[0],
                value,
                abs_tol=ABS_TOL,
                rel_tol=REL_TOL,
            )
            for value in repetitions[1:]
        )
        first[scenario_id] = repetitions[0]
        assert_normal_scenario(
            scenarios[scenario_id],
            repetitions[0],
            kp_intent_per_rad=kp_intent_per_rad,
        )

    assert abs(first["ALG001-P02"]) > abs(first["ALG001-P01"])
    assert abs(first["ALG001-N02"]) > abs(first["ALG001-N01"])
    for positive_id, negative_id in (
        ("ALG001-P01", "ALG001-N01"),
        ("ALG001-P02", "ALG001-N02"),
    ):
        assert math.isclose(
            first[positive_id],
            -first[negative_id],
            abs_tol=ABS_TOL,
            rel_tol=REL_TOL,
        )
