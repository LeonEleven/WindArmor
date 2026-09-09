import math
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms import (
    Alg002CandidateAController,
    ExampleAlgorithmController,
    NeutralExampleController,
)
from windarmor_flight_control.algorithms.alg002_candidate_a import (
    DEFAULT_KD_INTENT_PER_RAD_S,
    DEFAULT_KP_INTENT_PER_RAD,
    KD_CONFIGURATION_KEY,
    KP_CONFIGURATION_KEY,
    CandidateAConfiguration,
    compute_pitch_feedback_intent,
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
    assert_profile_relationships as assert_alg001_profile_relationships,
)
from .alg001_benchmark import (
    collect_level_a_results as collect_alg001_level_a_results,
)
from .alg002_benchmark import (
    NORMAL_SCENARIOS,
    assert_profile_relationships,
    collect_level_a_results,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms.alg002_candidate_a:create_controller"
)
DEFAULT_FACTORY = (
    "windarmor_flight_control.algorithms.flight_controller:create_controller"
)
EXAMPLE_FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
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


def _controller():
    return Alg002CandidateAController(
        MOTOR_NAMES,
        CandidateAConfiguration(
            DEFAULT_KP_INTENT_PER_RAD,
            DEFAULT_KD_INTENT_PER_RAD_S,
        ),
    )


def _assert_payload_free_safe_stop(command: FlightCommand) -> None:
    assert command == FlightCommand.safe_stop()
    validate_flight_command(command, MOTOR_NAMES)


class _Alg001RateZeroAdapter:
    def __init__(self, controller: Alg002CandidateAController) -> None:
        self._controller = controller

    def reset(self) -> None:
        self._controller.reset()

    def pitch_feedback_intent(self, relative_pitch_rad: float) -> float:
        return self._controller.pitch_feedback_intent(relative_pitch_rad, 0.0)


@pytest.mark.parametrize(
    "scenario",
    NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_level_a_normal_scenarios_use_frozen_fixture(scenario) -> None:
    feedback = compute_pitch_feedback_intent(
        scenario.relative_pitch_rad,
        scenario.relative_pitch_rate_rad_s,
    )

    assert math.isfinite(feedback)


def test_level_a_frozen_fixture_exact_intents_and_profile_relationships() -> None:
    expected = {
        "ALG002-P00": -0.05,
        "ALG002-P01": -0.07,
        "ALG002-P02": -0.03,
        "ALG002-N00": 0.05,
        "ALG002-N01": 0.07,
        "ALG002-N02": 0.03,
        "ALG002-Z01": -0.02,
        "ALG002-Z02": 0.02,
    }
    results = collect_level_a_results(_controller())

    separations = assert_profile_relationships(results)

    assert {name: values[0] for name, values in results.items()} == pytest.approx(
        expected
    )
    assert separations == pytest.approx(
        {"P_div": 0.02, "P_rec": 0.02, "N_div": 0.02, "N_rec": 0.02}
    )


@pytest.mark.parametrize(
    "scenario",
    NORMAL_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_level_b_normal_scenarios_return_current_hold_frame(scenario) -> None:
    state = _state_with_motion(
        scenario.relative_pitch_rad,
        scenario.relative_pitch_rate_rad_s,
        baseline=0.2,
    )
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


def test_alg001_level_a_inheritance_gate_at_zero_rate() -> None:
    controller = _controller()
    results = collect_alg001_level_a_results(_Alg001RateZeroAdapter(controller))

    assert_alg001_profile_relationships(
        results,
        kp_intent_per_rad=controller.configuration.kp_intent_per_rad,
    )


@pytest.mark.parametrize(
    "scenario",
    ALG001_NORMAL_SCENARIOS,
    ids=lambda scenario: f"inherit-{scenario.scenario_id}",
)
def test_alg001_level_b_normal_frame_inheritance(scenario) -> None:
    state = _state_with_motion(scenario.relative_pitch_rad, 0.0, baseline=-0.2)
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


def test_alg002_d00a_d00b_positive_dt_does_not_change_result() -> None:
    state = _state_with_motion(0.05, 0.20, baseline=-0.2)
    controller = _controller()
    intent = controller.pitch_feedback_intent(0.05, 0.20)

    first = controller.update(state, dt=0.02)
    second = controller.update(state, dt=0.037)

    assert controller.pitch_feedback_intent(0.05, 0.20) == intent
    assert first == second
    validate_flight_command(first, MOTOR_NAMES)
    validate_flight_command(second, MOTOR_NAMES)


def test_raw_gyro_changes_do_not_change_alg002_result() -> None:
    state = _state_with_motion(0.05, 0.20)
    changed_gyro = replace(
        state,
        imu=replace(
            state.imu,
            angular_velocity_rad_s=Vector3(x=9.0, y=-8.0, z=7.0),
        ),
    )
    controller = _controller()

    validate_flight_state(state, MOTOR_NAMES)
    validate_flight_state(changed_gyro, MOTOR_NAMES)
    assert controller.update(state, 0.02) == controller.update(changed_gyro, 0.02)
    assert controller.pitch_feedback_intent(0.05, 0.20) == pytest.approx(-0.07)


@pytest.mark.parametrize(
    ("pitch_rad", "rate_rad_s", "expected_sign"),
    [(0.05, -1.0, 1.0), (-0.05, 1.0, -1.0)],
    ids=["positive-pitch", "negative-pitch"],
)
def test_recovering_total_intent_may_reverse_before_zero(
    pitch_rad,
    rate_rad_s,
    expected_sign,
) -> None:
    feedback = compute_pitch_feedback_intent(pitch_rad, rate_rad_s)

    assert math.copysign(1.0, feedback) == expected_sign
    assert abs(feedback) > 1e-9


def test_alg002_f01_missing_rate_layer_classification() -> None:
    state = _state_with_motion(0.05, 0.20)
    contradictory = replace(
        state,
        imu=replace(state.imu, relative_pitch_rate_rad_s=None),
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_alg002_f02_nonfinite_rate_is_rejected_by_state_validation(value) -> None:
    state = _state_with_motion(0.05, 0.20)
    invalid = replace(
        state,
        imu=replace(state.imu, relative_pitch_rate_rad_s=value),
    )
    with pytest.raises(
        FlightValidationError,
        match="relative_pitch_rate_rad_s must be finite",
    ):
        validate_flight_state(invalid, MOTOR_NAMES)


def test_alg002_f03_stale_imu_fails_close() -> None:
    state = _state_with_motion(0.05, 0.20)
    stale = replace(
        state,
        imu=replace(state.imu, fresh=False),
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )

    validate_flight_state(stale, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(stale, dt=0.02))


def test_alg002_f04_required_inputs_fresh_false_fails_close() -> None:
    state = _state_with_motion(0.05, 0.20)
    stale_aggregate = replace(
        state,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )

    validate_flight_state(stale_aggregate, MOTOR_NAMES)
    _assert_payload_free_safe_stop(
        _controller().update(stale_aggregate, dt=0.02)
    )


def test_inherited_invalid_imu_fails_close() -> None:
    state = _state_with_motion(0.05, 0.20)
    invalid = replace(
        state,
        imu=replace(state.imu, valid=False, fresh=False),
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )

    validate_flight_state(invalid, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(invalid, dt=0.02))


@pytest.mark.parametrize("e_stop_active", [None, True])
def test_unknown_or_active_estop_fails_close(e_stop_active) -> None:
    state = _state_with_motion(0.05, 0.20)
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


def test_inherited_missing_pitch_layer_classification() -> None:
    state = _state_with_motion(0.05, 0.20)
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_inherited_nonfinite_pitch_is_rejected_by_state_validation(value) -> None:
    state = _state_with_motion(0.05, 0.20)
    invalid = replace(state, imu=replace(state.imu, relative_pitch_rad=value))
    with pytest.raises(FlightValidationError, match="relative_pitch_rad must be finite"):
        validate_flight_state(invalid, MOTOR_NAMES)


def test_inherited_motor_key_and_observation_layer_classification() -> None:
    state = _state_with_motion(0.05, 0.20)
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


def _motor_fault_state(variant: str):
    state = _state_with_motion(0.05, 0.20)
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
def test_inherited_motor_state_variants_fail_close(variant) -> None:
    state = _motor_fault_state(variant)
    validate_flight_state(state, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(state, dt=0.02))


@pytest.mark.parametrize(
    ("scenario_id", "dt"),
    [
        ("ALG002-D01", 0.0),
        ("ALG002-D02", -0.01),
        ("ALG002-D03", float("nan")),
        ("ALG002-D04-positive", float("inf")),
        ("ALG002-D04-negative", float("-inf")),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_invalid_dt_variants_fail_close(scenario_id, dt) -> None:
    del scenario_id
    state = _state_with_motion(0.05, 0.20)
    validate_flight_state(state, MOTOR_NAMES)
    _assert_payload_free_safe_stop(_controller().update(state, dt=dt))


def test_fail_close_after_normal_command_never_reuses_payload() -> None:
    controller = _controller()
    state = _state_with_motion(0.05, 0.20, baseline=0.3)
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


def test_alg002_r01_reset_is_history_free_and_uses_current_motor_frame() -> None:
    controller = _controller()
    first_state = _state_with_motion(0.05, -0.20, baseline=0.2)
    controller.reset()
    first_intent = controller.pitch_feedback_intent(0.05, -0.20)
    first_command = controller.update(first_state, dt=0.02)

    second_state = _state_with_motion(0.05, -0.20, baseline=-0.4)
    controller.reset()
    second_intent = controller.pitch_feedback_intent(0.05, -0.20)
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
        {KP_CONFIGURATION_KEY: 2.0, KD_CONFIGURATION_KEY: 0.25},
    )

    assert isinstance(default, Alg002CandidateAController)
    assert default.configuration == CandidateAConfiguration(1.0, 0.1)
    assert explicit.configuration == CandidateAConfiguration(2.0, 0.25)
    assert explicit.pitch_feedback_intent(0.1, 0.2) == pytest.approx(-0.25)


@pytest.mark.parametrize(
    "configuration",
    [
        {KP_CONFIGURATION_KEY: 0.0},
        {KP_CONFIGURATION_KEY: -1.0},
        {KP_CONFIGURATION_KEY: float("nan")},
        {KP_CONFIGURATION_KEY: float("inf")},
        {KP_CONFIGURATION_KEY: float("-inf")},
        {KP_CONFIGURATION_KEY: True},
        {KP_CONFIGURATION_KEY: "1.0"},
        {KD_CONFIGURATION_KEY: 0.0},
        {KD_CONFIGURATION_KEY: -0.1},
        {KD_CONFIGURATION_KEY: float("nan")},
        {KD_CONFIGURATION_KEY: float("inf")},
        {KD_CONFIGURATION_KEY: float("-inf")},
        {KD_CONFIGURATION_KEY: True},
        {KD_CONFIGURATION_KEY: "0.1"},
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
    assert isinstance(candidate, Alg002CandidateAController)
    assert type(default) is not type(candidate)
    assert type(example) is not type(candidate)


@pytest.mark.parametrize(
    ("pitch", "rate"),
    [
        (None, 0.0),
        (True, 0.0),
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (0.0, None),
        (0.0, True),
        (0.0, float("nan")),
        (0.0, float("inf")),
    ],
)
def test_level_a_seam_rejects_invalid_inputs(pitch, rate) -> None:
    with pytest.raises(ValueError):
        compute_pitch_feedback_intent(pitch, rate)


@pytest.mark.parametrize(
    ("kp", "kd"),
    [
        (0.0, 0.1),
        (-1.0, 0.1),
        (float("nan"), 0.1),
        (float("inf"), 0.1),
        (1.0, 0.0),
        (1.0, -0.1),
        (1.0, float("nan")),
        (1.0, float("inf")),
    ],
)
def test_level_a_seam_rejects_invalid_configuration(kp, kd) -> None:
    with pytest.raises(ValueError):
        compute_pitch_feedback_intent(
            0.05,
            0.20,
            kp_intent_per_rad=kp,
            kd_intent_per_rad_s=kd,
        )
