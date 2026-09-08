import math
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms import (
    Alg001CandidateAController,
    ExampleAlgorithmController,
    NeutralExampleController,
)
from windarmor_flight_control.algorithms.alg001_candidate_a import (
    CONFIGURATION_KEY,
    DEFAULT_KP_INTENT_PER_RAD,
    CandidateAConfiguration,
    compute_pitch_feedback_intent,
)
from windarmor_flight_control.core.models import FlightCommand
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
    NORMAL_SCENARIOS,
    assert_normal_scenario,
    assert_profile_relationships,
    collect_level_a_results,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms.alg001_candidate_a:create_controller"
)
DEFAULT_FACTORY = (
    "windarmor_flight_control.algorithms.flight_controller:create_controller"
)
EXAMPLE_FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
)


def _state_with_pitch_and_positions(pitch_rad: float, baseline: float = 0.0):
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
        ),
        motors=motors,
    )


def _controller():
    return Alg001CandidateAController(
        MOTOR_NAMES,
        CandidateAConfiguration(DEFAULT_KP_INTENT_PER_RAD),
    )


def _assert_payload_free_safe_stop(command: FlightCommand) -> None:
    assert command == FlightCommand.safe_stop()
    validate_flight_command(command, MOTOR_NAMES)


@pytest.mark.parametrize(
    "scenario",
    NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_level_a_normal_scenarios(scenario) -> None:
    feedback = compute_pitch_feedback_intent(
        scenario.relative_pitch_rad,
        kp_intent_per_rad=DEFAULT_KP_INTENT_PER_RAD,
    )

    assert_normal_scenario(
        scenario,
        feedback,
        kp_intent_per_rad=DEFAULT_KP_INTENT_PER_RAD,
    )


def test_level_a_profile_relationships_and_repeatability() -> None:
    controller = _controller()
    results = collect_level_a_results(controller)

    assert_profile_relationships(
        results,
        kp_intent_per_rad=controller.configuration.kp_intent_per_rad,
    )


@pytest.mark.parametrize(
    "scenario",
    NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_level_b_normal_scenarios_return_current_hold_frame(scenario) -> None:
    state = _state_with_pitch_and_positions(scenario.relative_pitch_rad, baseline=0.2)
    controller = _controller()
    controller.reset()

    validate_flight_state(state, MOTOR_NAMES)
    command = controller.update(state, dt=0.02)
    validate_flight_command(command, MOTOR_NAMES)

    assert command.request_safe_stop is False
    assert command.motor_positions_rad == {
        name: motor.position_rad for name, motor in state.motors.items()
    }
    assert command.fan_commands is not None
    assert command.fan_commands.left == 0.0
    assert command.fan_commands.right == 0.0


def test_positive_finite_dt_does_not_change_level_a_intent_or_hold_frame() -> None:
    state = _state_with_pitch_and_positions(0.10, baseline=-0.2)
    controller = _controller()
    intent = controller.pitch_feedback_intent(state.imu.relative_pitch_rad)

    first = controller.update(state, dt=0.02)
    second = controller.update(state, dt=0.037)

    assert controller.pitch_feedback_intent(state.imu.relative_pitch_rad) == intent
    assert first == second
    validate_flight_command(first, MOTOR_NAMES)
    validate_flight_command(second, MOTOR_NAMES)


@pytest.mark.parametrize("e_stop_active", [None, True])
def test_unknown_or_active_estop_fails_close(e_stop_active) -> None:
    state = _state_with_pitch_and_positions(0.1)
    inhibited = replace(
        state,
        system=replace(
            state.system,
            e_stop_active=e_stop_active,
            actuation_allowed=False,
        ),
    )

    validate_flight_state(inhibited, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(inhibited, dt=0.02))


@pytest.mark.parametrize(
    ("scenario_id", "state"),
    [
        (
            "ALG001-F01",
            replace(
                _state_with_pitch_and_positions(0.1),
                imu=replace(
                    _state_with_pitch_and_positions(0.1).imu,
                    valid=False,
                    fresh=False,
                ),
                system=replace(
                    _state_with_pitch_and_positions(0.1).system,
                    actuation_allowed=False,
                    required_inputs_fresh=False,
                ),
            ),
        ),
        (
            "ALG001-F02",
            replace(
                _state_with_pitch_and_positions(0.1),
                imu=replace(_state_with_pitch_and_positions(0.1).imu, fresh=False),
                system=replace(
                    _state_with_pitch_and_positions(0.1).system,
                    actuation_allowed=False,
                    required_inputs_fresh=False,
                ),
            ),
        ),
        (
            "ALG001-F03",
            replace(
                _state_with_pitch_and_positions(0.1),
                system=replace(
                    _state_with_pitch_and_positions(0.1).system,
                    actuation_allowed=False,
                    required_inputs_fresh=False,
                ),
            ),
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_controller_fail_close_for_imu_and_aggregate_gates(
    scenario_id,
    state,
) -> None:
    del scenario_id
    validate_flight_state(state, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(state, dt=0.02))


def test_alg001_f04_missing_pitch_layer_classification() -> None:
    state = _state_with_pitch_and_positions(0.1)
    contradictory = replace(
        state,
        imu=replace(state.imu, relative_pitch_rad=None),
    )
    with pytest.raises(FlightValidationError, match="complete measurement"):
        validate_flight_state(contradictory, MOTOR_NAMES)

    unobserved = replace(
        state,
        imu=make_unobserved_flight_state(MOTOR_NAMES).imu,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )
    validate_flight_state(unobserved, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(unobserved, dt=0.02))


def test_alg001_f05_nan_pitch_is_rejected_by_state_validation() -> None:
    state = _state_with_pitch_and_positions(0.1)
    invalid = replace(
        state,
        imu=replace(state.imu, relative_pitch_rad=float("nan")),
    )
    with pytest.raises(FlightValidationError, match="relative_pitch_rad must be finite"):
        validate_flight_state(invalid, MOTOR_NAMES)


@pytest.mark.parametrize("value", [float("inf"), float("-inf")])
def test_alg001_f06_infinite_pitch_is_rejected_by_state_validation(value) -> None:
    state = _state_with_pitch_and_positions(0.1)
    invalid = replace(state, imu=replace(state.imu, relative_pitch_rad=value))
    with pytest.raises(FlightValidationError, match="relative_pitch_rad must be finite"):
        validate_flight_state(invalid, MOTOR_NAMES)


def test_alg001_f07_motor_key_and_observation_layer_classification() -> None:
    state = _state_with_pitch_and_positions(0.1)
    missing = dict(state.motors)
    missing.pop(MOTOR_NAMES[-1])
    with pytest.raises(FlightValidationError, match="missing motors"):
        validate_flight_state(replace(state, motors=missing), MOTOR_NAMES)

    motors = dict(state.motors)
    motors[MOTOR_NAMES[-1]] = make_unobserved_flight_state(MOTOR_NAMES).motors[
        MOTOR_NAMES[-1]
    ]
    unobserved = replace(
        state,
        motors=motors,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )
    validate_flight_state(unobserved, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(unobserved, dt=0.02))


def _f08_state(variant: str):
    state = _state_with_pitch_and_positions(0.1)
    motors = dict(state.motors)
    motor = motors[MOTOR_NAMES[0]]
    if variant == "stale":
        motors[MOTOR_NAMES[0]] = replace(motor, fresh=False, healthy=False)
        required_inputs_fresh = False
    elif variant == "invalid":
        motors[MOTOR_NAMES[0]] = replace(
            motor,
            valid=False,
            fresh=False,
            healthy=False,
        )
        required_inputs_fresh = False
    else:
        motors[MOTOR_NAMES[0]] = replace(motor, fault_flags=1, healthy=False)
        required_inputs_fresh = True
    return replace(
        state,
        motors=motors,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=required_inputs_fresh,
        ),
    )


@pytest.mark.parametrize("variant", ["stale", "invalid", "unhealthy"])
def test_alg001_f08_motor_state_variants_fail_close(variant) -> None:
    state = _f08_state(variant)
    validate_flight_state(state, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(state, dt=0.02))


@pytest.mark.parametrize(
    ("scenario_id", "dt"),
    [
        ("ALG001-D01", 0.0),
        ("ALG001-D02", -0.01),
        ("ALG001-D03", float("nan")),
        ("ALG001-D04-positive", float("inf")),
        ("ALG001-D04-negative", float("-inf")),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_invalid_dt_variants_fail_close(scenario_id, dt) -> None:
    del scenario_id
    state = _state_with_pitch_and_positions(0.1)
    validate_flight_state(state, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(state, dt=dt))


def test_fail_close_after_normal_command_never_reuses_payload() -> None:
    controller = _controller()
    state = _state_with_pitch_and_positions(0.1, baseline=0.3)
    normal = controller.update(state, dt=0.02)
    assert normal.request_safe_stop is False

    stale = replace(
        state,
        imu=replace(state.imu, fresh=False),
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )
    safe_stop = controller.update(stale, dt=0.02)

    _assert_payload_free_safe_stop(safe_stop)
    assert safe_stop.motor_positions_rad is None
    assert safe_stop.fan_commands is None


def test_alg001_r01_reset_is_history_free_and_uses_current_motor_frame() -> None:
    controller = _controller()
    first_state = _state_with_pitch_and_positions(0.1, baseline=0.2)
    controller.reset()
    first_intent = controller.pitch_feedback_intent(0.1)
    first_command = controller.update(first_state, dt=0.02)

    second_state = _state_with_pitch_and_positions(0.1, baseline=-0.4)
    controller.reset()
    second_intent = controller.pitch_feedback_intent(0.1)
    second_command = controller.update(second_state, dt=0.02)

    assert first_intent == second_intent
    assert first_command.motor_positions_rad != second_command.motor_positions_rad
    assert first_command.motor_positions_rad == {
        name: motor.position_rad for name, motor in first_state.motors.items()
    }
    assert second_command.motor_positions_rad == {
        name: motor.position_rad for name, motor in second_state.motors.items()
    }
    validate_flight_command(first_command, MOTOR_NAMES)
    validate_flight_command(second_command, MOTOR_NAMES)


def test_factory_loads_traceable_default_and_explicit_configuration() -> None:
    default = load_controller(FACTORY, MOTOR_NAMES)
    explicit = load_controller(
        FACTORY,
        MOTOR_NAMES,
        {CONFIGURATION_KEY: 2.0},
    )

    assert isinstance(default, Alg001CandidateAController)
    assert default.configuration == CandidateAConfiguration(1.0)
    assert explicit.configuration == CandidateAConfiguration(2.0)
    assert explicit.pitch_feedback_intent(0.1) == pytest.approx(-0.2)


@pytest.mark.parametrize(
    "configuration",
    [
        {CONFIGURATION_KEY: 0.0},
        {CONFIGURATION_KEY: -1.0},
        {CONFIGURATION_KEY: float("nan")},
        {CONFIGURATION_KEY: float("inf")},
        {CONFIGURATION_KEY: float("-inf")},
        {CONFIGURATION_KEY: True},
        {CONFIGURATION_KEY: "1.0"},
        {"unknown": 1.0},
    ],
)
def test_factory_rejects_invalid_candidate_configuration(configuration) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(FACTORY, MOTOR_NAMES, configuration)


def test_default_and_example_factories_remain_separate_and_unchanged() -> None:
    default = load_controller(DEFAULT_FACTORY, MOTOR_NAMES)
    example = load_controller(EXAMPLE_FACTORY, MOTOR_NAMES)
    candidate = load_controller(FACTORY, MOTOR_NAMES)

    assert isinstance(default, NeutralExampleController)
    assert isinstance(example, ExampleAlgorithmController)
    assert isinstance(candidate, Alg001CandidateAController)
    assert type(default) is not type(candidate)
    assert type(example) is not type(candidate)


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf")])
def test_level_a_seam_rejects_invalid_inputs(value) -> None:
    with pytest.raises(ValueError):
        compute_pitch_feedback_intent(value)


def test_feedback_stays_finite_for_profile_inputs() -> None:
    assert all(
        math.isfinite(
            compute_pitch_feedback_intent(scenario.relative_pitch_rad)
        )
        for scenario in NORMAL_SCENARIOS
    )
