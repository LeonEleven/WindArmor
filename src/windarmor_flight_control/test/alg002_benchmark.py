"""可供 ALG-002 候选复用的 Profile v1 纯软件断言辅助函数。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


ABS_TOL = 1e-9
REL_TOL = 1e-6
REPEAT_COUNT = 3


@dataclass(frozen=True)
class Alg002NormalScenario:
    scenario_id: str
    relative_pitch_rad: float
    relative_pitch_rate_rad_s: float


NORMAL_SCENARIOS = (
    Alg002NormalScenario("ALG002-P00", 0.05, 0.0),
    Alg002NormalScenario("ALG002-P01", 0.05, 0.20),
    Alg002NormalScenario("ALG002-P02", 0.05, -0.20),
    Alg002NormalScenario("ALG002-N00", -0.05, 0.0),
    Alg002NormalScenario("ALG002-N01", -0.05, -0.20),
    Alg002NormalScenario("ALG002-N02", -0.05, 0.20),
    Alg002NormalScenario("ALG002-Z01", 0.0, 0.20),
    Alg002NormalScenario("ALG002-Z02", 0.0, -0.20),
)


class Alg002LevelAAdapter(Protocol):
    def reset(self) -> None: ...

    def pitch_feedback_intent(
        self,
        relative_pitch_rad: float,
        relative_pitch_rate_rad_s: float,
    ) -> float: ...


def relationship_tolerance(left: float, right: float) -> float:
    """返回 ALG-002 Profile v1 的有符号关系容差。"""

    return ABS_TOL + REL_TOL * max(abs(left), abs(right))


def collect_level_a_results(
    adapter: Alg002LevelAAdapter,
) -> dict[str, tuple[float, ...]]:
    """按 Profile v1 在每次独立运行前 reset，并重复至少三次。"""

    results: dict[str, tuple[float, ...]] = {}
    for scenario in NORMAL_SCENARIOS:
        repetitions: list[float] = []
        for _ in range(REPEAT_COUNT):
            adapter.reset()
            repetitions.append(
                adapter.pitch_feedback_intent(
                    scenario.relative_pitch_rad,
                    scenario.relative_pitch_rate_rad_s,
                )
            )
        results[scenario.scenario_id] = tuple(repetitions)
    return results


def assert_profile_relationships(
    results: dict[str, tuple[float, ...]],
) -> dict[str, float]:
    """断言正常场景、阻尼 separation、镜像、有限性与重复性。"""

    assert set(results) == {scenario.scenario_id for scenario in NORMAL_SCENARIOS}
    first: dict[str, float] = {}
    for scenario_id, repetitions in results.items():
        assert len(repetitions) >= REPEAT_COUNT
        assert all(math.isfinite(value) for value in repetitions)
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

    assert first["ALG002-P00"] < -ABS_TOL
    assert first["ALG002-N00"] > ABS_TOL
    assert first["ALG002-Z01"] < -ABS_TOL
    assert first["ALG002-Z02"] > ABS_TOL

    separations = {
        "P_div": first["ALG002-P00"] - first["ALG002-P01"],
        "P_rec": first["ALG002-P02"] - first["ALG002-P00"],
        "N_div": first["ALG002-N01"] - first["ALG002-N00"],
        "N_rec": first["ALG002-N00"] - first["ALG002-N02"],
    }
    pairs = {
        "P_div": (first["ALG002-P00"], first["ALG002-P01"]),
        "P_rec": (first["ALG002-P02"], first["ALG002-P00"]),
        "N_div": (first["ALG002-N01"], first["ALG002-N00"]),
        "N_rec": (first["ALG002-N00"], first["ALG002-N02"]),
    }
    assert all(
        separation > relationship_tolerance(*pairs[name])
        for name, separation in separations.items()
    )

    for positive_id, negative_id in (
        ("ALG002-P00", "ALG002-N00"),
        ("ALG002-P01", "ALG002-N01"),
        ("ALG002-P02", "ALG002-N02"),
        ("ALG002-Z01", "ALG002-Z02"),
    ):
        assert math.isclose(
            first[positive_id],
            -first[negative_id],
            abs_tol=ABS_TOL,
            rel_tol=REL_TOL,
        )
    return separations
