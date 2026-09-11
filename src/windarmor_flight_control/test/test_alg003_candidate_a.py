import math
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms import (
    Alg003CandidateAController,
    ExampleAlgorithmController,
    NeutralExampleController,
)
from windarmor_flight_control.algorithms.alg003_candidate_a import (
    DEFAULT_KD_INTENT_PER_RAD_S,
    DEFAULT_KP_INTENT_PER_RAD,
    DEFAULT_WINDOW_SIZE,
    KD_CONFIGURATION_KEY,
    KP_CONFIGURATION_KEY,
    WINDOW_SIZE_CONFIGURATION_KEY,
    Alg003CandidateACore,
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
    ABS_TOL,
    DT_VARIANTS,
    NOISE_BY_ID,
    NOISE_SCENARIOS,
    REPEAT_COUNT,
    SIGNAL_BY_ID,
    SIGNAL_SCENARIOS,
    collect_repeated_runs,
    dt_at,
    max_mirror_error,
    max_repeatability_delta,
    metrics,
    raw_sequence,
    response_metrics,
    run_noise_scenario,
    run_signal_scenario,
    steady_mean,
    tolerance,
    trend_means,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms.alg003_candidate_a:create_controller"
)
DEFAULT_FACTORY = (
    "windarmor_flight_control.algorithms.flight_controller:create_controller"
)
EXAMPLE_FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
)


def _core():
    return Alg003CandidateACore(
        CandidateAConfiguration(
            DEFAULT_KP_INTENT_PER_RAD,
            DEFAULT_KD_INTENT_PER_RAD_S,
            DEFAULT_WINDOW_SIZE,
        )
    )


def _controller():
    return Alg003CandidateAController(
        MOTOR_NAMES,
        CandidateAConfiguration(
            DEFAULT_KP_INTENT_PER_RAD,
            DEFAULT_KD_INTENT_PER_RAD_S,
            DEFAULT_WINDOW_SIZE,
        ),
    )


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


def _cold_start_after_controller_fault(controller, fault_state) -> None:
    controller.reset()
    controller.pitch_feedback_intent(0.05, 0.20, 0.02)
    controller.pitch_feedback_intent(0.053, 0.03, 0.02)
    command = controller.update(fault_state, 0.02)
    _assert_safe_stop(command)

    recovered = controller.pitch_feedback_intent(0.02, -0.10, 0.037)
    expected = _core().update(0.02, -0.10, 0.037)
    assert recovered == pytest.approx(expected)


class _Alg001SixFrameAdapter:
    def __init__(self):
        self.core = _core()

    def reset(self):
        self.core.reset()

    def pitch_feedback_intent(self, relative_pitch_rad):
        values = [
            self.core.update(relative_pitch_rad, 0.0, 0.02)
            for _ in range(6)
        ]
        return sum(values[-3:]) / 3.0


class _Alg002SixFrameAdapter:
    def __init__(self):
        self.core = _core()

    def reset(self):
        self.core.reset()

    def pitch_feedback_intent(self, relative_pitch_rad, relative_pitch_rate_rad_s):
        values = [
            self.core.update(
                relative_pitch_rad,
                relative_pitch_rate_rad_s,
                0.02,
            )
            for _ in range(6)
        ]
        return sum(values[-3:]) / 3.0


def test_level_a_cold_start_uses_current_valid_sample() -> None:
    core = _core()

    assert core.update(0.05, 0.20, 0.02) == pytest.approx(-0.07)


def test_level_a_uses_previous_raw_input_not_previous_filtered_value() -> None:
    core = _core()

    assert core.update(0.02, 0.00, 0.02) == pytest.approx(-0.02)
    assert core.update(0.06, 0.00, 0.02) == pytest.approx(-0.04)
    assert core.update(0.02, 0.00, 0.02) == pytest.approx(-0.04)


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
def test_level_a_invalid_input_clears_history(pitch, rate, dt) -> None:
    core = _core()
    core.update(0.05, 0.20, 0.02)

    with pytest.raises(ValueError):
        core.update(pitch, rate, dt)

    assert core.update(0.02, -0.10, 0.037) == pytest.approx(-0.01)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    NOISE_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_noise_suppression_gate(scenario, dt_variant) -> None:
    candidate = run_noise_scenario(_core(), scenario, dt_variant)
    raw = raw_sequence(scenario.samples)
    observed = metrics(candidate)
    baseline = metrics(raw)

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
def test_meaningful_response_and_steady_preservation(
    scenario_id,
    dt_variant,
) -> None:
    scenario = SIGNAL_BY_ID[scenario_id]
    values = run_signal_scenario(_core(), scenario, dt_variant)
    frames, elapsed = response_metrics(scenario, values, dt_variant)
    mean = steady_mean(values)

    assert frames <= 3
    assert elapsed > 0.0
    if scenario_id == "ALG003-S01":
        assert -0.084 - ABS_TOL <= mean <= -0.056 + ABS_TOL
    else:
        assert 0.056 - ABS_TOL <= mean <= 0.084 + ABS_TOL


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario_id",
    ["ALG003-S03P", "ALG003-S03N", "ALG003-S04P", "ALG003-S04N"],
)
def test_diverging_and_recovering_trend_preservation(
    scenario_id,
    dt_variant,
) -> None:
    scenario = SIGNAL_BY_ID[scenario_id]
    values = run_signal_scenario(_core(), scenario, dt_variant)
    before, after = trend_means(scenario, values)

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
def test_explicit_mirror_pairs_are_framewise_symmetric(
    positive_id,
    negative_id,
    dt_variant,
) -> None:
    if positive_id.startswith("ALG003-Q"):
        positive = run_noise_scenario(
            _core(), NOISE_BY_ID[positive_id], dt_variant
        )
        negative = run_noise_scenario(
            _core(), NOISE_BY_ID[negative_id], dt_variant
        )
    else:
        positive = run_signal_scenario(
            _core(), SIGNAL_BY_ID[positive_id], dt_variant
        )
        negative = run_signal_scenario(
            _core(), SIGNAL_BY_ID[negative_id], dt_variant
        )

    assert all(
        abs(left + right) <= tolerance(left, right)
        for left, right in zip(positive, negative)
    )


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
@pytest.mark.parametrize(
    "scenario",
    NOISE_SCENARIOS + SIGNAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_all_q_and_s_runs_are_three_time_repeatable(scenario, dt_variant) -> None:
    runs = collect_repeated_runs(_core, scenario, dt_variant)

    assert len(runs) == REPEAT_COUNT
    assert max_repeatability_delta(runs) <= max(
        tolerance(left, right)
        for first_index, first in enumerate(runs)
        for second in runs[first_index + 1 :]
        for left, right in zip(first, second)
    )


def test_alg003_r01_reset_removes_prior_q02_history() -> None:
    core = _core()
    run_noise_scenario(core, NOISE_BY_ID["ALG003-Q02"], "ALG003-D00A")
    core.reset()
    after_reset = run_noise_scenario(
        core, NOISE_BY_ID["ALG003-Q01"], "ALG003-D00A"
    )
    fresh = run_noise_scenario(
        _core(), NOISE_BY_ID["ALG003-Q01"], "ALG003-D00A"
    )

    _assert_sequences_close(after_reset, fresh)


def test_alg003_r02_sequence_order_isolated_and_mirrored() -> None:
    core = _core()
    q02_first = run_noise_scenario(
        core, NOISE_BY_ID["ALG003-Q02"], "ALG003-D00C"
    )
    q03_second = run_noise_scenario(
        core, NOISE_BY_ID["ALG003-Q03"], "ALG003-D00C"
    )
    q03_first = run_noise_scenario(
        core, NOISE_BY_ID["ALG003-Q03"], "ALG003-D00C"
    )
    q02_second = run_noise_scenario(
        core, NOISE_BY_ID["ALG003-Q02"], "ALG003-D00C"
    )

    _assert_sequences_close(q02_first, q02_second)
    _assert_sequences_close(q03_first, q03_second)
    assert max_mirror_error(q02_first, q03_first) <= ABS_TOL


def test_alg001_inheritance_six_frame_steady_profile() -> None:
    adapter = _Alg001SixFrameAdapter()
    results = collect_alg001_results(adapter)

    assert_alg001_relationships(results, kp_intent_per_rad=1.0)


@pytest.mark.parametrize(
    "scenario",
    ALG001_NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg001_inheritance_first_frame_finite_and_direction(scenario) -> None:
    core = _core()
    first = core.update(scenario.relative_pitch_rad, 0.0, 0.037)

    assert math.isfinite(first)
    if scenario.pitch_error_rad == 0.0:
        assert abs(first) <= ABS_TOL
    else:
        assert math.copysign(1.0, first) == math.copysign(
            1.0, scenario.pitch_error_rad
        )


def test_alg002_inheritance_six_frame_steady_profile() -> None:
    results = collect_alg002_results(_Alg002SixFrameAdapter())

    assert_alg002_relationships(results)


@pytest.mark.parametrize(
    "scenario",
    ALG002_NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg002_inheritance_first_frame_finite_and_direction(scenario) -> None:
    core = _core()
    first = core.update(
        scenario.relative_pitch_rad,
        scenario.relative_pitch_rate_rad_s,
        0.037,
    )
    raw = -scenario.relative_pitch_rad - 0.1 * scenario.relative_pitch_rate_rad_s

    assert math.isfinite(first)
    assert first == pytest.approx(raw)


@pytest.mark.parametrize("dt_variant", DT_VARIANTS)
def test_level_b_all_q_and_s_frames_are_valid(dt_variant) -> None:
    for scenario in NOISE_SCENARIOS:
        controller = _controller()
        controller.reset()
        command = controller.update(
            _state_with_motion(*scenario.priming, baseline=0.2),
            dt_at(dt_variant, 0),
        )
        validate_flight_command(command, MOTOR_NAMES)
        for index, sample in enumerate(scenario.samples):
            command = controller.update(
                _state_with_motion(*sample, baseline=index * 0.01),
                0.02 if dt_variant != "ALG003-D00B" else 0.037,
            )
            validate_flight_command(command, MOTOR_NAMES)
            assert command.request_safe_stop is False
            assert command.fan_commands.left == 0.0
            assert command.fan_commands.right == 0.0
    for scenario in SIGNAL_SCENARIOS:
        controller = _controller()
        controller.reset()
        for sample in scenario.samples:
            command = controller.update(_state_with_motion(*sample), 0.02)
            validate_flight_command(command, MOTOR_NAMES)
            assert set(command.motor_positions_rad) == set(MOTOR_NAMES)


@pytest.mark.parametrize("field", ["pitch", "rate"])
def test_alg003_f01_missing_valid_measurement_rejected_then_reset(field) -> None:
    controller = _controller()
    controller.pitch_feedback_intent(0.05, 0.20, 0.02)
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
def test_alg003_f02_nonfinite_measurement_rejected_then_reset(
    field,
    value,
) -> None:
    controller = _controller()
    controller.pitch_feedback_intent(0.05, 0.20, 0.02)
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
def test_alg003_f03_through_f06_fail_close_and_clear_history(variant) -> None:
    fault = _controller_fault_state(variant)
    validate_flight_state(fault, MOTOR_NAMES)

    _cold_start_after_controller_fault(_controller(), fault)


@pytest.mark.parametrize(
    "dt",
    [0.0, -0.01, float("nan"), float("inf"), float("-inf")],
)
def test_alg003_d01_through_d04_fail_close_and_clear_history(dt) -> None:
    controller = _controller()
    state = _state_with_motion(0.05, 0.20)
    controller.pitch_feedback_intent(0.05, 0.20, 0.02)

    _assert_safe_stop(controller.update(state, dt))

    recovered = controller.pitch_feedback_intent(0.02, -0.10, 0.02)
    assert recovered == pytest.approx(_core().update(0.02, -0.10, 0.02))


def test_controller_uses_same_core_for_level_a_and_update() -> None:
    controller = _controller()
    controller.pitch_feedback_intent(0.10, 0.40, 0.02)
    controller.update(_state_with_motion(0.02, -0.20), 0.02)

    assert controller.pitch_feedback_intent(0.0, 0.0, 0.02) == pytest.approx(
        0.0
    )


def test_level_b_uses_current_complete_motor_frame() -> None:
    controller = _controller()
    first = _state_with_motion(0.05, 0.20, baseline=0.3)
    second = _state_with_motion(0.05, 0.20, baseline=-0.4)

    first_command = controller.update(first, 0.02)
    second_command = controller.update(second, 0.02)

    assert first_command.motor_positions_rad == {
        name: motor.position_rad for name, motor in first.motors.items()
    }
    assert second_command.motor_positions_rad == {
        name: motor.position_rad for name, motor in second.motors.items()
    }


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


def test_factory_loads_frozen_default_configuration() -> None:
    controller = load_controller(FACTORY, MOTOR_NAMES)

    assert isinstance(controller, Alg003CandidateAController)
    assert controller.configuration == CandidateAConfiguration(1.0, 0.1, 2)


@pytest.mark.parametrize(
    "configuration",
    [
        {KP_CONFIGURATION_KEY: 0.0},
        {KP_CONFIGURATION_KEY: -1.0},
        {KP_CONFIGURATION_KEY: float("nan")},
        {KP_CONFIGURATION_KEY: float("inf")},
        {KP_CONFIGURATION_KEY: True},
        {KP_CONFIGURATION_KEY: "1.0"},
        {KD_CONFIGURATION_KEY: 0.0},
        {KD_CONFIGURATION_KEY: -0.1},
        {KD_CONFIGURATION_KEY: float("nan")},
        {KD_CONFIGURATION_KEY: float("inf")},
        {KD_CONFIGURATION_KEY: True},
        {KD_CONFIGURATION_KEY: "0.1"},
        {WINDOW_SIZE_CONFIGURATION_KEY: 1},
        {WINDOW_SIZE_CONFIGURATION_KEY: 3},
        {WINDOW_SIZE_CONFIGURATION_KEY: 2.0},
        {WINDOW_SIZE_CONFIGURATION_KEY: True},
        {"unknown": 1.0},
    ],
)
def test_factory_rejects_invalid_or_unknown_configuration(configuration) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(FACTORY, MOTOR_NAMES, configuration)


def test_factory_accepts_explicit_frozen_configuration() -> None:
    controller = load_controller(
        FACTORY,
        MOTOR_NAMES,
        {
            KP_CONFIGURATION_KEY: 1.0,
            KD_CONFIGURATION_KEY: 0.1,
            WINDOW_SIZE_CONFIGURATION_KEY: 2,
        },
    )

    assert controller.configuration == CandidateAConfiguration(1.0, 0.1, 2)


def test_default_and_teaching_controllers_remain_separate() -> None:
    default = load_controller(DEFAULT_FACTORY, MOTOR_NAMES)
    teaching = load_controller(EXAMPLE_FACTORY, MOTOR_NAMES)
    candidate = load_controller(FACTORY, MOTOR_NAMES)

    assert isinstance(default, NeutralExampleController)
    assert isinstance(teaching, ExampleAlgorithmController)
    assert isinstance(candidate, Alg003CandidateAController)
    assert type(default) is not type(candidate)
    assert type(teaching) is not type(candidate)


def test_inherited_missing_motor_key_rejected_before_controller() -> None:
    state = _state_with_motion(0.05, 0.20)
    motors = dict(state.motors)
    motors.pop(MOTOR_NAMES[-1])
    invalid = replace(state, motors=motors)

    with pytest.raises(FlightValidationError, match="missing motors"):
        validate_flight_state(invalid, MOTOR_NAMES)


@pytest.mark.parametrize(
    ("pitch_rad", "pitch_rate_rad_s"),
    tuple(
        (scenario.relative_pitch_rad, 0.0)
        for scenario in ALG001_NORMAL_SCENARIOS
    )
    + tuple(
        (scenario.relative_pitch_rad, scenario.relative_pitch_rate_rad_s)
        for scenario in ALG002_NORMAL_SCENARIOS
    ),
)
def test_inheritance_level_b_holds_each_normal_state_for_six_frames(
    pitch_rad,
    pitch_rate_rad_s,
) -> None:
    controller = _controller()
    controller.reset()

    commands = []
    for _ in range(6):
        command = controller.update(
            _state_with_motion(pitch_rad, pitch_rate_rad_s), 0.02
        )
        validate_flight_command(command, MOTOR_NAMES)
        commands.append(command)

    assert all(not command.request_safe_stop for command in commands)
