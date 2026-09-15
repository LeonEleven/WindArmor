import json
import math
from dataclasses import asdict, replace

import pytest

from windarmor_flight_control.algorithms import (
    Alg004CandidateAController,
    ExampleAlgorithmController,
    NeutralExampleController,
)
from windarmor_flight_control.algorithms.alg004_candidate_a import (
    DEFAULT_MAX_ABS_INTENT,
    DEFAULT_MAX_SLEW_RATE,
    KD_CONFIGURATION_KEY,
    KP_CONFIGURATION_KEY,
    MAX_ABS_INTENT_CONFIGURATION_KEY,
    MAX_SLEW_RATE_CONFIGURATION_KEY,
    WINDOW_SIZE_CONFIGURATION_KEY,
    Alg004CandidateACore,
    Alg004OutputShaper,
    CandidateAConfiguration,
)
from windarmor_flight_control.core.models import FlightCommand, Vector3
from windarmor_flight_control.core.validation import (
    FlightValidationError,
    validate_flight_command,
    validate_flight_state,
)
from windarmor_flight_control.runtime.controller_loader import (
    ControllerLoadError,
    load_controller,
)
from windarmor_flight_control.testing import (
    make_fake_flight_state,
    make_unobserved_flight_state,
)

from .alg001_benchmark import (
    NORMAL_SCENARIOS as ALG001_NORMAL_SCENARIOS,
)
from .alg001_benchmark import (
    assert_profile_relationships as assert_alg001_relationships,
)
from .alg001_benchmark import (
    collect_level_a_results as collect_alg001_results,
)
from .alg002_benchmark import (
    NORMAL_SCENARIOS as ALG002_NORMAL_SCENARIOS,
)
from .alg002_benchmark import (
    assert_profile_relationships as assert_alg002_relationships,
)
from .alg002_benchmark import (
    collect_level_a_results as collect_alg002_results,
)
from .alg003_benchmark import (
    NOISE_BY_ID as ALG003_NOISE_BY_ID,
    NOISE_SCENARIOS as ALG003_NOISE_SCENARIOS,
    SIGNAL_BY_ID as ALG003_SIGNAL_BY_ID,
    SIGNAL_SCENARIOS as ALG003_SIGNAL_SCENARIOS,
    collect_repeated_runs as collect_alg003_repeated_runs,
    max_mirror_error as max_alg003_mirror_error,
    max_repeatability_delta as max_alg003_repeatability_delta,
    metrics as alg003_metrics,
    raw_sequence as alg003_raw_sequence,
    response_metrics as alg003_response_metrics,
    run_noise_scenario as run_alg003_noise_scenario,
    run_signal_scenario as run_alg003_signal_scenario,
    steady_mean as alg003_steady_mean,
    tolerance as alg003_tolerance,
    trend_means as alg003_trend_means,
)
from .alg004_benchmark import (
    ABS_TOL,
    DT_VARIANTS,
    MIRROR_PAIRS,
    REPEAT_COUNT,
    S,
    SCENARIO_BY_ID,
    SCENARIOS,
    STEADY_SCENARIO_IDS,
    U,
    clamped_target,
    collect_repeated_runs,
    dt_at,
    effective_sign_reversals,
    frames_time_to_80pct,
    frames_to_50pct,
    max_abs_output,
    max_mirror_error,
    max_observed_slew_rate,
    metrics,
    max_repeatability_delta,
    run_scenario,
    signed_tail_mean,
    synthetic_elapsed_time_to_50pct,
    tolerance,
    total_variation,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms.alg004_candidate_a:create_controller"
)
DEFAULT_FACTORY = (
    "windarmor_flight_control.algorithms.flight_controller:create_controller"
)
EXAMPLE_FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
)
FROZEN_CONFIGURATION = {
    KP_CONFIGURATION_KEY: 1.0,
    KD_CONFIGURATION_KEY: 0.1,
    WINDOW_SIZE_CONFIGURATION_KEY: 2,
    MAX_ABS_INTENT_CONFIGURATION_KEY: 0.10,
    MAX_SLEW_RATE_CONFIGURATION_KEY: 2.0,
}


def _shaper():
    return Alg004OutputShaper(DEFAULT_MAX_ABS_INTENT, DEFAULT_MAX_SLEW_RATE)


def _core():
    return Alg004CandidateACore(CandidateAConfiguration())


def _controller():
    return Alg004CandidateAController(MOTOR_NAMES, CandidateAConfiguration())


def _state_with_motion(
    pitch_rad: float,
    pitch_rate_rad_s: float,
    baseline: float = 0.0,
):
    state = make_fake_flight_state(MOTOR_NAMES)
    motors = {
        name: replace(motor, position_rad=baseline + index * 0.1)
        for index, (name, motor) in enumerate(state.motors.items())
    }
    return replace(
        state,
        imu=replace(
            state.imu,
            pitch_rad=pitch_rad,
            relative_pitch_rad=pitch_rad,
            relative_pitch_rate_rad_s=pitch_rate_rad_s,
        ),
        motors=motors,
    )


def _assert_safe_stop(command: FlightCommand) -> None:
    assert command == FlightCommand.safe_stop()
    validate_flight_command(command, MOTOR_NAMES)


def _assert_sequences_close(left, right) -> None:
    assert len(left) == len(right)
    assert all(
        math.isclose(a, b, abs_tol=ABS_TOL, rel_tol=1e-6)
        for a, b in zip(left, right)
    )


def _establish_dual_history(controller, dt_variant: str) -> None:
    controller.reset()
    for index in range(3):
        value = controller.pitch_feedback_intent(
            -0.20,
            -0.20,
            dt_at(dt_variant, index),
        )
    assert value > 0.0


def _cold_start_after_controller_fault(
    controller,
    fault_state,
    dt_variant: str,
) -> None:
    _establish_dual_history(controller, dt_variant)
    command = controller.update(fault_state, dt_at(dt_variant, 3))
    _assert_safe_stop(command)

    recovery_dt = dt_at(dt_variant, 4)
    recovered = controller.pitch_feedback_intent(0.02, -0.10, recovery_dt)
    expected = _core().update(0.02, -0.10, recovery_dt)
    assert recovered == pytest.approx(expected)


class _DtSpy:
    def __init__(self):
        self.received_dt = []

    def reset(self):
        self.received_dt.clear()

    def update(self, requested_intent, dt):
        self.received_dt.append(dt)
        return 0.0


class _Alg001SixFrameAdapter:
    def __init__(self, dt_variant):
        self.core = _core()
        self.dt_variant = dt_variant

    def reset(self):
        self.core.reset()

    def pitch_feedback_intent(self, relative_pitch_rad):
        values = [
            self.core.update(
                relative_pitch_rad,
                0.0,
                dt_at(self.dt_variant, index),
            )
            for index in range(6)
        ]
        return sum(values[-3:]) / 3.0


class _Alg002SixFrameAdapter:
    def __init__(self, dt_variant):
        self.core = _core()
        self.dt_variant = dt_variant

    def reset(self):
        self.core.reset()

    def pitch_feedback_intent(
        self,
        relative_pitch_rad,
        relative_pitch_rate_rad_s,
    ):
        values = [
            self.core.update(
                relative_pitch_rad,
                relative_pitch_rate_rad_s,
                dt_at(self.dt_variant, index),
            )
            for index in range(6)
        ]
        return sum(values[-3:]) / 3.0


@pytest.mark.parametrize(
    ("dt_variant", "expected"),
    [
        ("ALG004-D00A", (0.020,) * 9),
        ("ALG004-D00B", (0.037,) * 9),
        (
            "ALG004-D00C",
            (0.020, 0.037, 0.020, 0.037, 0.020, 0.037, 0.020, 0.037, 0.020),
        ),
    ],
)
def test_runner_dt_schedule_crosses_step_segment_without_restart(
    dt_variant,
    expected,
) -> None:
    spy = _DtSpy()

    run_scenario(spy, SCENARIO_BY_ID["ALG004-S01P"], dt_variant)

    assert tuple(spy.received_dt) == expected


def test_shaper_cold_start_and_reset_baseline_are_zero() -> None:
    shaper = _shaper()

    assert shaper.previous_shaped_intent == 0.0
    assert shaper.update(0.10, 0.020) == pytest.approx(0.04)
    shaper.reset()
    assert shaper.previous_shaped_intent == 0.0
    assert shaper.update(-0.10, 0.020) == pytest.approx(-0.04)


def test_candidate_formula_sanity_is_symmetric_and_saturates_exactly() -> None:
    positive_shaper = _shaper()
    positive = tuple(positive_shaper.update(0.10, 0.020) for _ in range(3))
    negative_shaper = _shaper()
    negative = tuple(negative_shaper.update(-0.10, 0.020) for _ in range(3))

    assert positive == pytest.approx((0.04, 0.08, 0.10))
    assert negative == pytest.approx((-0.04, -0.08, -0.10))
    assert positive == pytest.approx(tuple(-value for value in negative))


def test_shaper_variable_dt_uses_current_period_and_never_overshoots() -> None:
    shaper = _shaper()

    assert shaper.update(0.20, 0.020) == pytest.approx(0.04)
    assert shaper.update(0.20, 0.037) == pytest.approx(0.10)
    assert shaper.update(-0.20, 0.020) == pytest.approx(0.06)
    assert shaper.update(-0.20, 0.037) == pytest.approx(-0.014)
    assert shaper.update(-0.20, 1.0) == pytest.approx(-0.10)
    assert shaper.previous_shaped_intent == pytest.approx(-0.10)


@pytest.mark.parametrize(
    ("requested_intent", "dt"),
    [
        (None, 0.02),
        (True, 0.02),
        ("0.1", 0.02),
        (float("nan"), 0.02),
        (float("inf"), 0.02),
        (float("-inf"), 0.02),
        (0.10, None),
        (0.10, True),
        (0.10, "0.02"),
        (0.10, 0.0),
        (0.10, -0.01),
        (0.10, float("nan")),
        (0.10, float("inf")),
        (0.10, float("-inf")),
    ],
)
def test_shaper_invalid_input_raises_and_invalidates_history(
    requested_intent,
    dt,
) -> None:
    shaper = _shaper()
    assert shaper.update(0.10, 0.02) == pytest.approx(0.04)

    with pytest.raises(ValueError):
        shaper.update(requested_intent, dt)

    assert shaper.previous_shaped_intent == 0.0
    assert shaper.update(-0.10, 0.02) == pytest.approx(-0.04)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_all_fixture_frames_obey_finite_envelope_slew_and_direction(
    scenario,
    dt_variant,
) -> None:
    values = run_scenario(_shaper(), scenario, dt_variant)
    previous = 0.0

    for index, (request, value) in enumerate(zip(scenario.requests, values)):
        target = clamped_target(request)
        delta = abs(value - previous)
        current_dt = dt_at(dt_variant, index)
        assert math.isfinite(value)
        assert abs(value) <= U + tolerance(abs(value), U)
        assert delta <= S * current_dt + tolerance(delta, S * current_dt)
        assert min(previous, target) - tolerance(
            value, min(previous, target)
        ) <= value
        assert value <= max(previous, target) + tolerance(
            value, max(previous, target)
        )
        previous = value

    assert max_abs_output(values) <= U + ABS_TOL
    assert max_observed_slew_rate(values, dt_variant) <= S + 1e-12


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_neutral_gate(dt_variant) -> None:
    values = run_scenario(
        _shaper(),
        SCENARIO_BY_ID["ALG004-N00"],
        dt_variant,
    )

    assert all(abs(value) <= ABS_TOL for value in values)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_metrics_cover_neutral_and_response_scenarios(dt_variant) -> None:
    neutral = SCENARIO_BY_ID["ALG004-N00"]
    neutral_values = run_scenario(_shaper(), neutral, dt_variant)
    neutral_metrics = metrics(neutral, neutral_values, dt_variant)

    assert neutral_metrics["max_abs_output"] == 0.0
    assert "frames_to_50pct" not in neutral_metrics

    response = SCENARIO_BY_ID["ALG004-S01P"]
    response_values = run_scenario(_shaper(), response, dt_variant)
    response_metrics = metrics(response, response_values, dt_variant)

    assert response_metrics["frames_to_50pct"] <= 3
    assert response_metrics["frames_to_80pct"] >= 1
    assert response_metrics["synthetic_elapsed_time_to_50pct"] > 0.0
    assert response_metrics["synthetic_elapsed_time_to_80pct"] > 0.0


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize("scenario_id", STEADY_SCENARIO_IDS)
def test_steady_saturation_and_cold_start_step_gates(
    scenario_id,
    dt_variant,
) -> None:
    scenario = SCENARIO_BY_ID[scenario_id]
    values = run_scenario(_shaper(), scenario, dt_variant)
    target = clamped_target(scenario.requests[0])
    tail = signed_tail_mean(values)

    assert math.copysign(1.0, tail) == math.copysign(1.0, target)
    assert abs(tail) + ABS_TOL >= 0.80 * abs(target)
    assert abs(tail) <= abs(target) + tolerance(abs(tail), abs(target))
    assert frames_to_50pct(scenario, values, dt_variant) <= 3
    assert synthetic_elapsed_time_to_50pct(
        scenario, values, dt_variant
    ) > 0.0
    frames_80, elapsed_80 = frames_time_to_80pct(
        scenario, values, dt_variant
    )
    assert frames_80 >= 1
    assert elapsed_80 > 0.0
    if scenario_id in ("ALG004-P04", "ALG004-N04"):
        assert max_abs_output(values) == pytest.approx(0.10)
        assert all(abs(value) <= 0.10 + ABS_TOL for value in values)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario_id",
    ["ALG004-S01P", "ALG004-S01N", "ALG004-S02P", "ALG004-S02N"],
)
def test_delayed_step_response_and_steady_gate(
    scenario_id,
    dt_variant,
) -> None:
    scenario = SCENARIO_BY_ID[scenario_id]
    values = run_scenario(_shaper(), scenario, dt_variant)
    target = clamped_target(scenario.requests[scenario.transition_index])
    tail = signed_tail_mean(values)

    assert frames_to_50pct(scenario, values, dt_variant) <= 3
    assert math.copysign(1.0, tail) == math.copysign(1.0, target)
    assert abs(tail) + ABS_TOL >= 0.80 * abs(target)
    assert abs(tail) <= abs(target) + tolerance(abs(tail), abs(target))


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize("scenario_id", ["ALG004-S03P", "ALG004-S03N"])
def test_full_reversal_reaches_opposite_half_and_steady(
    scenario_id,
    dt_variant,
) -> None:
    scenario = SCENARIO_BY_ID[scenario_id]
    values = run_scenario(_shaper(), scenario, dt_variant)
    target = clamped_target(scenario.requests[scenario.transition_index])
    reversal = values[scenario.transition_index :]
    qualifying = [
        index
        for index, value in enumerate(reversal[:6], start=1)
        if math.copysign(1.0, value) == math.copysign(1.0, target)
        and abs(value) + ABS_TOL >= 0.50 * abs(target)
    ]

    assert qualifying
    tail = signed_tail_mean(values)
    assert math.copysign(1.0, tail) == math.copysign(1.0, target)
    assert abs(tail) + ABS_TOL >= 0.80 * abs(target)
    assert abs(tail) <= abs(target) + tolerance(abs(tail), abs(target))


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize("scenario_id", ["ALG004-S04P", "ALG004-S04N"])
def test_high_frequency_reversal_gate(scenario_id, dt_variant) -> None:
    values = run_scenario(
        _shaper(),
        SCENARIO_BY_ID[scenario_id],
        dt_variant,
    )

    assert total_variation(values) <= 1.32 + ABS_TOL
    assert effective_sign_reversals(values) <= 4


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(("positive_id", "negative_id"), MIRROR_PAIRS)
def test_fixture_mirror_pairs_are_framewise_symmetric(
    positive_id,
    negative_id,
    dt_variant,
) -> None:
    positive = run_scenario(
        _shaper(), SCENARIO_BY_ID[positive_id], dt_variant
    )
    negative = run_scenario(
        _shaper(), SCENARIO_BY_ID[negative_id], dt_variant
    )

    assert max_mirror_error(positive, negative) <= max(
        tolerance(left, right)
        for left, right in zip(positive, negative)
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_all_fixture_runs_are_three_time_repeatable(
    scenario,
    dt_variant,
) -> None:
    runs = collect_repeated_runs(_shaper, scenario, dt_variant)

    assert len(runs) == REPEAT_COUNT
    assert max_repeatability_delta(runs) <= max(
        tolerance(left, right)
        for first_index, first in enumerate(runs)
        for second in runs[first_index + 1 :]
        for left, right in zip(first, second)
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_alg004_r01_reset_removes_p04_history(dt_variant) -> None:
    shaper = _shaper()
    run_scenario(shaper, SCENARIO_BY_ID["ALG004-P04"], dt_variant)
    shaper.reset()
    after_reset = run_scenario(
        shaper, SCENARIO_BY_ID["ALG004-N02"], dt_variant
    )
    fresh = run_scenario(
        _shaper(), SCENARIO_BY_ID["ALG004-N02"], dt_variant
    )

    _assert_sequences_close(after_reset, fresh)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_alg004_r02_order_isolated_and_mirrored(dt_variant) -> None:
    shaper = _shaper()
    p02_first = run_scenario(
        shaper, SCENARIO_BY_ID["ALG004-P02"], dt_variant
    )
    n02_second = run_scenario(
        shaper, SCENARIO_BY_ID["ALG004-N02"], dt_variant
    )
    n02_first = run_scenario(
        shaper, SCENARIO_BY_ID["ALG004-N02"], dt_variant
    )
    p02_second = run_scenario(
        shaper, SCENARIO_BY_ID["ALG004-P02"], dt_variant
    )

    _assert_sequences_close(p02_first, p02_second)
    _assert_sequences_close(n02_first, n02_second)
    assert max_mirror_error(p02_first, n02_first) <= ABS_TOL


@pytest.mark.parametrize(
    ("pitch", "rate", "dt"),
    [
        (None, 0.0, 0.02),
        (True, 0.0, 0.02),
        (float("nan"), 0.0, 0.02),
        (float("inf"), 0.0, 0.02),
        (0.0, None, 0.02),
        (0.0, True, 0.02),
        (0.0, float("nan"), 0.02),
        (0.0, float("-inf"), 0.02),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, -0.01),
        (0.0, 0.0, float("nan")),
        (0.0, 0.0, float("inf")),
        (0.0, 0.0, float("-inf")),
    ],
)
def test_composite_invalid_input_atomically_clears_both_histories(
    pitch,
    rate,
    dt,
) -> None:
    core = _core()
    core.update(-0.20, -0.20, 0.02)
    core.update(-0.20, -0.20, 0.02)

    with pytest.raises(ValueError):
        core.update(pitch, rate, dt)

    recovery = core.update(0.02, -0.10, 0.037)
    expected = _core().update(0.02, -0.10, 0.037)
    assert recovery == pytest.approx(expected)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    ALG003_NOISE_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg003_noise_suppression_inheritance(scenario, dt_variant) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    candidate = run_alg003_noise_scenario(_core(), scenario, alg003_variant)
    raw = alg003_raw_sequence(scenario.samples)
    observed = alg003_metrics(candidate)
    baseline = alg003_metrics(raw)

    assert all(math.isfinite(value) for value in candidate)
    if scenario.scenario_id == "ALG003-Q01":
        assert observed["tv"] <= 0.0536 + ABS_TOL
        assert observed["reversal"] <= 2
        assert observed["peak"] <= 0.0040 + ABS_TOL
        assert observed["maa"] <= 0.0024 + ABS_TOL
    elif scenario.scenario_id in ("ALG003-Q02", "ALG003-Q03"):
        assert observed["tv"] <= 0.0804 + ABS_TOL
        assert observed["reversal"] == 0
        assert observed["p2p"] <= 0.0120 + ABS_TOL
    else:
        assert observed["tv"] <= 0.0264 + ABS_TOL
        assert observed["reversal"] <= 2
        assert observed["peak"] <= 0.0020 + ABS_TOL
        assert observed["maa"] <= 0.0012 + ABS_TOL
    assert observed["reversal"] <= baseline["reversal"]


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize("scenario_id", ["ALG003-S01", "ALG003-S02"])
def test_alg003_meaningful_signal_inheritance(
    scenario_id,
    dt_variant,
) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    scenario = ALG003_SIGNAL_BY_ID[scenario_id]
    values = run_alg003_signal_scenario(_core(), scenario, alg003_variant)
    frames, elapsed = alg003_response_metrics(
        scenario,
        values,
        alg003_variant,
    )
    tail = alg003_steady_mean(values)

    assert frames <= 3
    assert elapsed > 0.0
    if scenario_id == "ALG003-S01":
        assert -0.084 - ABS_TOL <= tail <= -0.056 + ABS_TOL
    else:
        assert 0.056 - ABS_TOL <= tail <= 0.084 + ABS_TOL


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario_id",
    ["ALG003-S03P", "ALG003-S03N", "ALG003-S04P", "ALG003-S04N"],
)
def test_alg003_trend_inheritance(scenario_id, dt_variant) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    scenario = ALG003_SIGNAL_BY_ID[scenario_id]
    values = run_alg003_signal_scenario(_core(), scenario, alg003_variant)
    before, after = alg003_trend_means(scenario, values)

    if scenario_id == "ALG003-S03P":
        separation = before - after
    elif scenario_id == "ALG003-S03N":
        separation = after - before
    elif scenario_id == "ALG003-S04P":
        separation = after - before
    else:
        separation = before - after
    assert separation >= 0.010 - ABS_TOL


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    ("positive_id", "negative_id"),
    [
        ("ALG003-Q02", "ALG003-Q03"),
        ("ALG003-S01", "ALG003-S02"),
        ("ALG003-S03P", "ALG003-S03N"),
        ("ALG003-S04P", "ALG003-S04N"),
    ],
)
def test_alg003_mirror_inheritance(
    positive_id,
    negative_id,
    dt_variant,
) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    if positive_id.startswith("ALG003-Q"):
        runner = run_alg003_noise_scenario
        scenarios = ALG003_NOISE_BY_ID
    else:
        runner = run_alg003_signal_scenario
        scenarios = ALG003_SIGNAL_BY_ID
    positive = runner(_core(), scenarios[positive_id], alg003_variant)
    negative = runner(_core(), scenarios[negative_id], alg003_variant)

    assert max_alg003_mirror_error(positive, negative) <= max(
        alg003_tolerance(left, right)
        for left, right in zip(positive, negative)
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    ALG003_NOISE_SCENARIOS + ALG003_SIGNAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg003_repeatability_inheritance(scenario, dt_variant) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    runs = collect_alg003_repeated_runs(_core, scenario, alg003_variant)

    assert max_alg003_repeatability_delta(runs) <= max(
        alg003_tolerance(left, right)
        for first_index, first in enumerate(runs)
        for second in runs[first_index + 1 :]
        for left, right in zip(first, second)
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_alg001_six_frame_inheritance(dt_variant) -> None:
    results = collect_alg001_results(_Alg001SixFrameAdapter(dt_variant))

    assert_alg001_relationships(results, kp_intent_per_rad=1.0)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    ALG001_NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg001_inheritance_first_frame_finite_and_direction(
    scenario,
    dt_variant,
) -> None:
    first = _core().update(
        scenario.relative_pitch_rad,
        0.0,
        dt_at(dt_variant, 0),
    )

    assert math.isfinite(first)
    if scenario.pitch_error_rad == 0.0:
        assert abs(first) <= ABS_TOL
    else:
        assert math.copysign(1.0, first) == math.copysign(
            1.0, scenario.pitch_error_rad
        )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_alg002_six_frame_inheritance(dt_variant) -> None:
    results = collect_alg002_results(_Alg002SixFrameAdapter(dt_variant))

    assert_alg002_relationships(results)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    ALG002_NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg002_inheritance_first_frame_finite_and_direction(
    scenario,
    dt_variant,
) -> None:
    raw = (
        -scenario.relative_pitch_rad
        - 0.1 * scenario.relative_pitch_rate_rad_s
    )
    first = _core().update(
        scenario.relative_pitch_rad,
        scenario.relative_pitch_rate_rad_s,
        dt_at(dt_variant, 0),
    )

    assert math.isfinite(first)
    if raw == 0.0:
        assert abs(first) <= ABS_TOL
    else:
        assert math.copysign(1.0, first) == math.copysign(1.0, raw)


@pytest.mark.parametrize("field", ["pitch", "rate"])
def test_alg004_f01_missing_valid_measurement_rejected_then_reset(field) -> None:
    controller = _controller()
    _establish_dual_history(controller, "ALG004-D00A")
    state = _state_with_motion(0.05, 0.20)
    kwargs = (
        {"relative_pitch_rad": None}
        if field == "pitch"
        else {"relative_pitch_rate_rad_s": None}
    )
    contradictory = replace(state, imu=replace(state.imu, **kwargs))

    with pytest.raises(FlightValidationError, match="complete measurement"):
        validate_flight_state(contradictory, MOTOR_NAMES)

    controller.reset()
    recovered = controller.pitch_feedback_intent(0.02, -0.10, 0.02)
    assert recovered == pytest.approx(_core().update(0.02, -0.10, 0.02))


@pytest.mark.parametrize("field", ["pitch", "rate"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_alg004_f02_nonfinite_measurement_rejected_then_reset(
    field,
    value,
) -> None:
    controller = _controller()
    _establish_dual_history(controller, "ALG004-D00A")
    state = _state_with_motion(0.05, 0.20)
    kwargs = (
        {"relative_pitch_rad": value}
        if field == "pitch"
        else {"relative_pitch_rate_rad_s": value}
    )
    invalid = replace(state, imu=replace(state.imu, **kwargs))

    with pytest.raises(FlightValidationError):
        validate_flight_state(invalid, MOTOR_NAMES)

    controller.reset()
    recovered = controller.pitch_feedback_intent(0.02, -0.10, 0.02)
    assert recovered == pytest.approx(_core().update(0.02, -0.10, 0.02))


def _controller_fault_state(variant):
    state = _state_with_motion(0.05, 0.20)
    if variant == "invalid-imu":
        return replace(
            state,
            imu=make_unobserved_flight_state(MOTOR_NAMES).imu,
            system=replace(
                state.system,
                actuation_allowed=False,
                required_inputs_fresh=False,
            ),
        )
    if variant == "stale-imu":
        return replace(
            state,
            imu=replace(state.imu, fresh=False),
            system=replace(
                state.system,
                actuation_allowed=False,
                required_inputs_fresh=False,
            ),
        )
    if variant == "stale-aggregate":
        return replace(
            state,
            system=replace(
                state.system,
                actuation_allowed=False,
                required_inputs_fresh=False,
            ),
        )
    if variant in ("estop-unknown", "estop-active"):
        return replace(
            state,
            system=replace(
                state.system,
                e_stop_active=None if variant == "estop-unknown" else True,
                actuation_allowed=False,
            ),
        )

    motors = dict(state.motors)
    motor = motors[MOTOR_NAMES[0]]
    if variant == "motor-unobserved":
        motors[MOTOR_NAMES[0]] = make_unobserved_flight_state(
            MOTOR_NAMES
        ).motors[MOTOR_NAMES[0]]
        fresh = False
    elif variant == "motor-stale":
        motors[MOTOR_NAMES[0]] = replace(
            motor, fresh=False, healthy=False
        )
        fresh = False
    elif variant == "motor-invalid":
        motors[MOTOR_NAMES[0]] = replace(
            motor, valid=False, fresh=False, healthy=False
        )
        fresh = False
    else:
        motors[MOTOR_NAMES[0]] = replace(
            motor, fault_flags=1, healthy=False
        )
        fresh = True
    return replace(
        state,
        motors=motors,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=fresh,
        ),
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "variant",
    [
        "invalid-imu",
        "stale-imu",
        "stale-aggregate",
        "motor-unobserved",
        "motor-stale",
        "motor-invalid",
        "motor-unhealthy",
        "estop-unknown",
        "estop-active",
    ],
)
def test_alg004_f03_through_f06_fail_close_and_clear_dual_history(
    variant,
    dt_variant,
) -> None:
    fault = _controller_fault_state(variant)
    validate_flight_state(fault, MOTOR_NAMES)

    _cold_start_after_controller_fault(_controller(), fault, dt_variant)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "dt",
    [0.0, -0.01, float("nan"), float("inf"), float("-inf")],
)
def test_alg004_d01_through_d04_fail_close_and_clear_dual_history(
    dt,
    dt_variant,
) -> None:
    controller = _controller()
    state = _state_with_motion(0.05, 0.20)
    _establish_dual_history(controller, dt_variant)

    _assert_safe_stop(controller.update(state, dt))

    recovery_dt = dt_at(dt_variant, 4)
    recovered = controller.pitch_feedback_intent(0.02, -0.10, recovery_dt)
    expected = _core().update(0.02, -0.10, recovery_dt)
    assert recovered == pytest.approx(expected)


def test_controller_uses_same_composite_core_for_level_a_and_update() -> None:
    controller = _controller()
    controller.pitch_feedback_intent(-0.20, -0.20, 0.02)
    controller.update(_state_with_motion(-0.20, -0.20), 0.02)

    observed = controller.pitch_feedback_intent(-0.20, -0.20, 0.02)
    assert observed == pytest.approx(0.10)


def test_level_b_uses_current_complete_motor_frame_and_fan_zero() -> None:
    controller = _controller()
    first = _state_with_motion(0.05, 0.20, baseline=0.3)
    second = _state_with_motion(0.05, 0.20, baseline=-0.4)

    first_command = controller.update(first, 0.02)
    second_command = controller.update(second, 0.037)

    for state, command in ((first, first_command), (second, second_command)):
        validate_flight_command(command, MOTOR_NAMES)
        assert command.motor_positions_rad == {
            name: motor.position_rad for name, motor in state.motors.items()
        }
        assert set(command.motor_positions_rad) == set(MOTOR_NAMES)
        assert command.fan_commands.left == 0.0
        assert command.fan_commands.right == 0.0
        assert command.request_safe_stop is False


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_level_b_alg003_fixture_frames_are_valid(dt_variant) -> None:
    alg003_variant = dt_variant.replace("ALG004", "ALG003")
    for scenario in ALG003_NOISE_SCENARIOS:
        controller = _controller()
        command = controller.update(
            _state_with_motion(*scenario.priming, baseline=0.2),
            0.020 if alg003_variant != "ALG003-D00B" else 0.037,
        )
        validate_flight_command(command, MOTOR_NAMES)
        for index, sample in enumerate(scenario.samples):
            frame_dt = (
                0.037
                if alg003_variant == "ALG003-D00B"
                else 0.020
                if alg003_variant == "ALG003-D00A"
                else (0.037 if index % 2 == 0 else 0.020)
            )
            command = controller.update(
                _state_with_motion(*sample, baseline=index * 0.01),
                frame_dt,
            )
            validate_flight_command(command, MOTOR_NAMES)
            assert command.request_safe_stop is False


def test_raw_gyro_is_not_a_control_input() -> None:
    state = _state_with_motion(0.05, 0.20)
    changed = replace(
        state,
        imu=replace(
            state.imu,
            angular_velocity_rad_s=Vector3(x=9.0, y=-8.0, z=7.0),
        ),
    )

    assert _controller().update(state, 0.02) == _controller().update(
        changed, 0.02
    )


def test_factory_loads_frozen_default_and_explicit_configuration() -> None:
    default = load_controller(FACTORY, MOTOR_NAMES)
    explicit = load_controller(FACTORY, MOTOR_NAMES, FROZEN_CONFIGURATION)
    expected = CandidateAConfiguration(1.0, 0.1, 2, 0.10, 2.0)

    assert isinstance(default, Alg004CandidateAController)
    assert default.configuration == expected
    assert explicit.configuration == expected


def test_configuration_has_stable_serialization() -> None:
    first = json.dumps(asdict(CandidateAConfiguration()), sort_keys=True)
    second = json.dumps(asdict(CandidateAConfiguration()), sort_keys=True)

    assert first == second
    assert json.loads(first) == FROZEN_CONFIGURATION


@pytest.mark.parametrize(
    "configuration",
    [
        {KP_CONFIGURATION_KEY: 0.9},
        {KP_CONFIGURATION_KEY: 0.0},
        {KP_CONFIGURATION_KEY: None},
        {KP_CONFIGURATION_KEY: float("nan")},
        {KP_CONFIGURATION_KEY: float("inf")},
        {KP_CONFIGURATION_KEY: True},
        {KP_CONFIGURATION_KEY: "1.0"},
        {KD_CONFIGURATION_KEY: 0.2},
        {KD_CONFIGURATION_KEY: 0.0},
        {KD_CONFIGURATION_KEY: None},
        {KD_CONFIGURATION_KEY: float("nan")},
        {KD_CONFIGURATION_KEY: float("inf")},
        {KD_CONFIGURATION_KEY: True},
        {KD_CONFIGURATION_KEY: "0.1"},
        {WINDOW_SIZE_CONFIGURATION_KEY: 1},
        {WINDOW_SIZE_CONFIGURATION_KEY: 3},
        {WINDOW_SIZE_CONFIGURATION_KEY: 2.0},
        {WINDOW_SIZE_CONFIGURATION_KEY: True},
        {WINDOW_SIZE_CONFIGURATION_KEY: None},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: 0.2},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: 0.0},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: None},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: float("nan")},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: float("inf")},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: True},
        {MAX_ABS_INTENT_CONFIGURATION_KEY: "0.1"},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: 1.0},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: 0.0},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: None},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: float("nan")},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: float("inf")},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: True},
        {MAX_SLEW_RATE_CONFIGURATION_KEY: "2.0"},
        {"unknown": 1.0},
    ],
)
def test_factory_rejects_nonfrozen_invalid_or_unknown_configuration(
    configuration,
) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(FACTORY, MOTOR_NAMES, configuration)


@pytest.mark.parametrize("configuration", [None, [], "frozen"])
def test_configuration_rejects_non_mapping(configuration) -> None:
    if configuration is None:
        assert CandidateAConfiguration.from_mapping(configuration)
    else:
        with pytest.raises(ValueError):
            CandidateAConfiguration.from_mapping(configuration)


def test_default_and_teaching_controllers_remain_separate() -> None:
    default = load_controller(DEFAULT_FACTORY, MOTOR_NAMES)
    teaching = load_controller(EXAMPLE_FACTORY, MOTOR_NAMES)
    candidate = load_controller(FACTORY, MOTOR_NAMES)

    assert isinstance(default, NeutralExampleController)
    assert isinstance(teaching, ExampleAlgorithmController)
    assert isinstance(candidate, Alg004CandidateAController)
    assert type(default) is not type(candidate)
    assert type(teaching) is not type(candidate)


def test_missing_motor_key_is_rejected_before_controller() -> None:
    state = _state_with_motion(0.05, 0.20)
    motors = dict(state.motors)
    motors.pop(MOTOR_NAMES[-1])
    invalid = replace(state, motors=motors)

    with pytest.raises(FlightValidationError, match="missing motors"):
        validate_flight_state(invalid, MOTOR_NAMES)
