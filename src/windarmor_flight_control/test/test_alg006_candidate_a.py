"""ALG-006 implementation-stage normalized allocation and inheritance tests."""

from dataclasses import FrozenInstanceError, asdict, replace
import json
import math

import pytest

from windarmor_flight_control.algorithms.alg005_candidate_a import (
    Alg005CandidateACore,
    CandidateAConfiguration as Alg005Configuration,
    ProcessObservation,
    RecoveryPhase,
)
from windarmor_flight_control.algorithms.alg006_candidate_a import (
    AllocationDisposition,
    AllocationObservation,
    AllocationStatus,
    Alg006CandidateACore,
    Alg006CandidateAController,
    CandidateAConfiguration,
    NormalizedAllocator,
    allocate_normalized_request,
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

from .alg001_benchmark import NORMAL_SCENARIOS as ALG001_SCENARIOS
from .alg002_benchmark import NORMAL_SCENARIOS as ALG002_SCENARIOS
from .alg003_benchmark import (
    DT_VARIANTS as ALG003_DT_VARIANTS,
    NOISE_SCENARIOS as ALG003_NOISE_SCENARIOS,
    SIGNAL_SCENARIOS as ALG003_SIGNAL_SCENARIOS,
    run_noise_scenario as run_alg003_noise,
    run_signal_scenario as run_alg003_signal,
)
from .alg004_benchmark import (
    DT_VARIANTS as ALG004_DT_VARIANTS,
    SCENARIOS as ALG004_SCENARIOS,
    run_scenario as run_alg004,
)
from .alg005_benchmark import (
    DT,
    DYNAMIC_SCENARIOS as ALG005_DYNAMIC_SCENARIOS,
    SCRIPTED_BY_ID as ALG005_SCRIPTED_BY_ID,
    SCRIPTED_SCENARIOS as ALG005_SCRIPTED_SCENARIOS,
    motion_state,
    run_dynamic as run_alg005_dynamic,
    run_scripted as run_alg005_scripted,
)
from .alg006_benchmark import (
    ATOMIC_CASES,
    BASE_CASES,
    CASE_BY_ID,
    D06_SEQUENCE,
    D07_SEQUENCE,
    D12_SEQUENCE,
    REPEAT_COUNT,
    run_case,
    run_sequence,
    tolerance,
)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
FACTORY = (
    "windarmor_flight_control.algorithms.alg006_candidate_a:create_controller"
)
FROZEN_CONFIGURATION = asdict(CandidateAConfiguration())


def _assert_observation_matches(
    actual: AllocationObservation,
    expected: AllocationObservation,
) -> None:
    for field in (
        "normalized_request",
        "motor_pitch_group",
        "left_fan",
        "right_fan",
        "residual",
    ):
        left = getattr(actual, field)
        right = getattr(expected, field)
        assert math.isfinite(left)
        assert math.isclose(left, right, abs_tol=1e-9, rel_tol=1e-6)
    assert actual.status is expected.status
    assert actual.disposition is expected.disposition
    assert actual.timeout_latched is expected.timeout_latched


@pytest.mark.parametrize("case", ATOMIC_CASES, ids=lambda case: case.scenario_id)
def test_frozen_atomic_allocation_cases(case) -> None:
    _assert_observation_matches(run_case(case), case.expected)


def test_allocator_requires_structured_process_outcome_and_upstream_disposition() -> None:
    allocator = NormalizedAllocator()
    invalid = allocator.allocate(0.025, 1.0, 1.0, 1.0)
    external = allocator.allocate(
        ProcessObservation(final_process_intent=0.025),
        1.0,
        1.0,
        1.0,
        upstream_valid=False,
    )
    malformed = allocator.allocate(
        ProcessObservation(final_process_intent=0.025),
        1.0,
        1.0,
        1.0,
        upstream_valid=1,
    )

    assert invalid.status is AllocationStatus.FAIL_CLOSED
    assert invalid.disposition is AllocationDisposition.INVALID_CONTRACT
    assert external.status is AllocationStatus.FAIL_CLOSED
    assert external.disposition is AllocationDisposition.EXTERNAL_FAIL_CLOSED
    assert malformed.disposition is AllocationDisposition.INVALID_CONTRACT


@pytest.mark.parametrize("intent", [None, True, False, "0.025"])
def test_non_numeric_or_bool_ordinary_intent_fails_closed(intent) -> None:
    result = allocate_normalized_request(
        ProcessObservation(final_process_intent=intent),
        1.0,
        1.0,
        1.0,
    )
    assert result.status is AllocationStatus.FAIL_CLOSED
    assert result.disposition is AllocationDisposition.INVALID_CONTRACT


def test_timeout_has_priority_over_external_and_authority_failures() -> None:
    timeout = ProcessObservation(
        final_process_intent=0.0,
        phase=RecoveryPhase.TIMED_OUT,
        timeout_latched=True,
    )
    result = allocate_normalized_request(
        timeout,
        None,
        math.nan,
        True,
        upstream_valid=False,
    )

    assert result.status is AllocationStatus.FAIL_CLOSED
    assert result.disposition is AllocationDisposition.TIMEOUT
    assert result.timeout_latched is True
    assert result != CASE_BY_ID["ALG006-D00"].expected


@pytest.mark.parametrize(
    "positive_id,negative_id",
    [
        ("ALG006-D01P", "ALG006-D01N"),
        ("ALG006-D02P", "ALG006-D02N"),
        ("ALG006-D03P", "ALG006-D03N"),
    ],
)
def test_positive_negative_requests_are_mirrored(
    positive_id,
    negative_id,
) -> None:
    positive = run_case(CASE_BY_ID[positive_id])
    negative = run_case(CASE_BY_ID[negative_id])

    assert positive.normalized_request == -negative.normalized_request
    assert positive.motor_pitch_group == -negative.motor_pitch_group
    assert positive.left_fan == negative.left_fan
    assert positive.right_fan == negative.right_fan
    assert positive.residual == -negative.residual
    assert positive.status is negative.status


def test_d04_fan_authority_exchange_preserves_common_allocation() -> None:
    left = run_case(CASE_BY_ID["ALG006-D04L"])
    right = run_case(CASE_BY_ID["ALG006-D04R"])
    assert left == right
    assert left.left_fan == left.right_fan == 0.4


def test_d06_reversal_and_d07_exact_neutral_do_not_reuse_prior_allocation() -> None:
    reversal = run_sequence(D06_SEQUENCE)
    crossing = run_sequence(D07_SEQUENCE)

    assert tuple(item.motor_pitch_group for item in reversal) == pytest.approx(
        (+0.8, -0.8)
    )
    assert tuple(item.left_fan for item in reversal) == pytest.approx((0.8, 0.8))
    assert reversal[0].residual == reversal[1].residual == 0.0
    assert crossing[1] == CASE_BY_ID["ALG006-D00"].expected
    assert crossing[0].motor_pitch_group == -crossing[2].motor_pitch_group


def test_d11_core_reset_replay_matches_fresh_and_clears_observation() -> None:
    core = Alg006CandidateACore()
    fresh = Alg006CandidateACore()

    for _ in range(3):
        core.update(-0.08, 0.0, DT, motor_authority=0.6)
    assert core.allocation_observation.status is AllocationStatus.SATURATED
    assert core.allocation_observation.normalized_request == pytest.approx(0.8)
    assert core.allocation_observation.residual == pytest.approx(0.2)

    core.reset()
    assert core.allocation_observation.disposition is AllocationDisposition.RESET
    replay = []
    reference = []
    for _ in range(3):
        replay.append(core.update(-0.08, 0.0, DT, motor_authority=0.6))
        reference.append(fresh.update(-0.08, 0.0, DT, motor_authority=0.6))
        assert core.observation == fresh.observation
        assert core.allocation_observation == fresh.allocation_observation
    assert replay == reference


def test_d12_three_complete_runs_are_identical_without_cross_run_history() -> None:
    allocator = NormalizedAllocator()
    runs = tuple(
        run_sequence(D12_SEQUENCE, allocator)
        for _ in range(REPEAT_COUNT)
    )
    assert runs[0] == runs[1] == runs[2]
    assert len(runs[0]) == len(D12_SEQUENCE)


def test_all_derived_numeric_observations_are_finite_and_bounded() -> None:
    for case in ATOMIC_CASES:
        observation = run_case(case)
        values = (
            observation.normalized_request,
            observation.motor_pitch_group,
            observation.left_fan,
            observation.right_fan,
            observation.residual,
        )
        assert all(math.isfinite(value) for value in values)
        assert -1.0 <= observation.motor_pitch_group <= 1.0
        assert 0.0 <= observation.left_fan <= 1.0
        assert 0.0 <= observation.right_fan <= 1.0


def _state(pitch=0.05, rate=0.20, baseline=0.0):
    state = make_fake_flight_state(MOTOR_NAMES)
    motors = {
        name: replace(motor, position_rad=baseline + index * 0.1)
        for index, (name, motor) in enumerate(state.motors.items())
    }
    return replace(
        state,
        imu=replace(
            state.imu,
            pitch_rad=pitch,
            relative_pitch_rad=pitch,
            relative_pitch_rate_rad_s=rate,
        ),
        motors=motors,
    )


def _controller():
    return Alg006CandidateAController(MOTOR_NAMES, CandidateAConfiguration())


def _assert_safe_stop(command) -> None:
    assert command == FlightCommand.safe_stop()
    validate_flight_command(command, MOTOR_NAMES)


def test_factory_loads_default_and_explicit_thirteen_field_configuration() -> None:
    default = load_controller(FACTORY, MOTOR_NAMES)
    explicit = load_controller(FACTORY, MOTOR_NAMES, FROZEN_CONFIGURATION)

    assert isinstance(default, Alg006CandidateAController)
    assert default.configuration == CandidateAConfiguration()
    assert explicit.configuration == CandidateAConfiguration()
    assert len(FROZEN_CONFIGURATION) == 13
    assert json.loads(json.dumps(FROZEN_CONFIGURATION, sort_keys=True)) == (
        FROZEN_CONFIGURATION
    )


@pytest.mark.parametrize(
    "configuration",
    [
        {"unknown": 1.0},
        {"motor_authority": 1.0},
        {"left_fan_authority": 1.0},
        {"right_fan_authority": 1.0},
        {"max_abs_intent": 0.2},
        {"recovery_timeout_sec": 4.0},
        {"window_size": True},
        {"kp_intent_per_rad": math.nan},
    ],
)
def test_factory_rejects_unknown_synthetic_or_nonfrozen_configuration(
    configuration,
) -> None:
    with pytest.raises(ControllerLoadError):
        load_controller(FACTORY, MOTOR_NAMES, configuration)


@pytest.mark.parametrize("key", tuple(FROZEN_CONFIGURATION))
@pytest.mark.parametrize(
    "value",
    [True, "0.1", None, math.nan, math.inf, -math.inf, -1.0],
)
def test_every_inherited_configuration_field_rejects_invalid_values(
    key,
    value,
) -> None:
    with pytest.raises(ValueError):
        CandidateAConfiguration.from_mapping({key: value})


@pytest.mark.parametrize("configuration", [[], "frozen"])
def test_non_mapping_configuration_is_rejected(configuration) -> None:
    with pytest.raises(ValueError):
        CandidateAConfiguration.from_mapping(configuration)


def test_configuration_and_observations_are_immutable() -> None:
    controller = _controller()
    with pytest.raises(FrozenInstanceError):
        controller.configuration.recovery_timeout_sec = 4.0
    with pytest.raises(FrozenInstanceError):
        controller.allocation_observation.status = AllocationStatus.NEUTRAL


def test_level_b_holds_each_current_complete_motor_frame_and_fans_at_zero() -> None:
    controller = _controller()
    states = (_state(baseline=0.3), _state(baseline=-0.4))

    for state, dt in zip(states, (0.020, 0.037)):
        command = controller.update(state, dt)
        validate_flight_command(command, MOTOR_NAMES)
        assert command.motor_positions_rad == {
            name: motor.position_rad for name, motor in state.motors.items()
        }
        assert command.fan_commands.left == command.fan_commands.right == 0.0
        assert not command.request_safe_stop
        allocation = controller.allocation_observation
        assert allocation.disposition is AllocationDisposition.ORDINARY
        assert allocation.left_fan == allocation.right_fan


def test_controller_nominal_authority_is_observation_only() -> None:
    controller = _controller()
    command = controller.update(_state(pitch=-0.20, rate=-0.20), DT)
    allocation = controller.allocation_observation

    validate_flight_command(command, MOTOR_NAMES)
    assert allocation.status is AllocationStatus.ALLOCATED
    assert allocation.residual == 0.0
    assert command.fan_commands.left == command.fan_commands.right == 0.0
    assert command.motor_positions_rad == {
        name: motor.position_rad
        for name, motor in _state(pitch=-0.20, rate=-0.20).motors.items()
    }


@pytest.mark.parametrize("dt", [0.0, -0.01, math.nan, math.inf, -math.inf])
def test_illegal_dt_returns_exact_safe_stop_and_cold_resets(dt) -> None:
    controller = _controller()
    controller.update(_state(pitch=-0.20, rate=-0.20), DT)
    _assert_safe_stop(controller.update(_state(), dt))
    assert controller.allocation_observation.disposition is (
        AllocationDisposition.EXTERNAL_FAIL_CLOSED
    )
    assert controller.update(_state(), DT) == _controller().update(_state(), DT)


def _controller_fault_state(name):
    state = _state()
    if name == "imu-invalid":
        return make_unobserved_flight_state(MOTOR_NAMES)
    if name == "imu-stale":
        return replace(
            state,
            imu=replace(state.imu, fresh=False),
            system=replace(
                state.system,
                actuation_allowed=False,
                required_inputs_fresh=False,
            ),
        )
    if name == "aggregate-stale":
        return replace(
            state,
            system=replace(
                state.system,
                actuation_allowed=False,
                required_inputs_fresh=False,
            ),
        )
    if name == "estop-unknown":
        return replace(
            state,
            system=replace(
                state.system,
                e_stop_active=None,
                actuation_allowed=False,
            ),
        )
    if name == "estop-active":
        return replace(
            state,
            system=replace(
                state.system,
                e_stop_active=True,
                actuation_allowed=False,
            ),
        )
    motors = dict(state.motors)
    motor = motors[MOTOR_NAMES[0]]
    if name == "motor-stale":
        motors[MOTOR_NAMES[0]] = replace(motor, fresh=False, healthy=False)
    elif name == "motor-unhealthy":
        motors[MOTOR_NAMES[0]] = replace(
            motor,
            healthy=False,
            fault_flags=1,
        )
    elif name == "motor-unobserved":
        motors[MOTOR_NAMES[0]] = replace(
            motor,
            position_rad=None,
            velocity_rad_s=None,
            torque_nm=None,
            temperature_c=None,
            device_mode=None,
            fault_flags=None,
            feedback_age_sec=None,
            has_feedback=False,
            valid=False,
            fresh=False,
            healthy=False,
        )
    return replace(
        state,
        motors=motors,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )


@pytest.mark.parametrize(
    "fault",
    [
        "imu-invalid",
        "imu-stale",
        "aggregate-stale",
        "motor-stale",
        "motor-unhealthy",
        "motor-unobserved",
        "estop-unknown",
        "estop-active",
    ],
)
def test_external_invalid_stale_unhealthy_or_unknown_fault_safe_stops(fault) -> None:
    controller = _controller()
    state = _controller_fault_state(fault)
    validate_flight_state(state, MOTOR_NAMES)
    _assert_safe_stop(controller.update(state, DT))
    assert controller.allocation_observation.status is AllocationStatus.FAIL_CLOSED


def test_state_validation_reject_does_not_call_controller() -> None:
    state = _state()
    invalid = replace(
        state,
        imu=replace(state.imu, relative_pitch_rad=math.nan),
    )
    with pytest.raises(FlightValidationError):
        validate_flight_state(invalid, MOTOR_NAMES)


def test_internal_allocator_failure_safe_stops_and_cold_resets(monkeypatch) -> None:
    controller = _controller()
    controller.update(_state(pitch=-0.20, rate=-0.20), DT)

    def fail(*args, **kwargs):
        raise RuntimeError("injected allocator failure")

    allocator = controller._core._allocator
    original = allocator.allocate
    monkeypatch.setattr(allocator, "allocate", fail)
    _assert_safe_stop(controller.update(_state(), DT))
    assert controller.allocation_observation.disposition is (
        AllocationDisposition.INTERNAL_FAILURE
    )
    monkeypatch.setattr(allocator, "allocate", original)
    assert controller.update(_state(), DT) == _controller().update(_state(), DT)


def test_inherited_process_internal_failure_safe_stops(monkeypatch) -> None:
    controller = _controller()

    def fail(*args, **kwargs):
        raise RuntimeError("injected inherited process failure")

    monkeypatch.setattr(controller._core._process_core, "update", fail)
    _assert_safe_stop(controller.update(_state(), DT))
    assert controller.allocation_observation.disposition is (
        AllocationDisposition.INTERNAL_FAILURE
    )


def test_timeout_sentinel_is_safe_stop_not_neutral_and_latches_until_reset() -> None:
    controller = _controller()
    command = None
    for _ in range(150):
        command = controller.update(_state(pitch=0.05, rate=0.20), DT)

    _assert_safe_stop(command)
    assert controller.observation.phase is RecoveryPhase.TIMED_OUT
    assert controller.observation.timeout_latched is True
    assert controller.allocation_observation.status is AllocationStatus.FAIL_CLOSED
    assert controller.allocation_observation.disposition is AllocationDisposition.TIMEOUT
    _assert_safe_stop(controller.update(_state(pitch=0.0, rate=0.0), DT))

    controller.reset()
    command = controller.update(_state(pitch=0.0, rate=0.0), DT)
    validate_flight_command(command, MOTOR_NAMES)
    assert controller.observation.phase is RecoveryPhase.STABLE
    assert controller.allocation_observation.status is AllocationStatus.NEUTRAL


def test_timeout_latch_survives_transient_alg006_internal_failure(monkeypatch) -> None:
    controller = _controller()
    for _ in range(150):
        controller.update(_state(pitch=0.05, rate=0.20), DT)
    before = controller.observation

    def fail(*args, **kwargs):
        raise RuntimeError("injected allocator failure")

    monkeypatch.setattr(controller._core._allocator, "allocate", fail)
    _assert_safe_stop(controller.update(_state(pitch=0.0, rate=0.0), DT))
    assert controller.observation == before
    assert controller.allocation_observation.disposition is AllocationDisposition.TIMEOUT


class _RequestedSource:
    def __init__(self):
        self.request = 0.0

    def reset(self):
        self.request = 0.0

    def update(self, pitch, rate, dt):
        return self.request


class _Alg006RequestedIntentAdapter:
    """Drive ALG-004 fixture requests through ALG-005 and ALG-006."""

    def __init__(self):
        self.core = Alg006CandidateACore()
        self.source = _RequestedSource()
        self.core._process_core._inherited_core._inherited_core = self.source

    def reset(self):
        self.core.reset()

    def update(self, request, dt):
        self.source.request = request
        result = self.core.update(0.0, 0.0, dt)
        assert self.core.observation.phase is RecoveryPhase.STABLE
        assert self.core.allocation_observation.status is not (
            AllocationStatus.FAIL_CLOSED
        )
        return result


class _Alg005RequestedIntentAdapter:
    def __init__(self):
        self.core = Alg005CandidateACore(Alg005Configuration())
        self.source = _RequestedSource()
        self.core._inherited_core._inherited_core = self.source

    def reset(self):
        self.core.reset()

    def update(self, request, dt):
        self.source.request = request
        return self.core.update(0.0, 0.0, dt)


@pytest.mark.parametrize("scenario", ALG004_SCENARIOS, ids=lambda s: s.scenario_id)
@pytest.mark.parametrize("dt_variant", ALG004_DT_VARIANTS)
def test_alg004_fixture_is_unchanged_through_alg006_final_path(
    scenario,
    dt_variant,
) -> None:
    actual = run_alg004(_Alg006RequestedIntentAdapter(), scenario, dt_variant)
    inherited = run_alg004(_Alg005RequestedIntentAdapter(), scenario, dt_variant)
    assert actual == inherited


@pytest.mark.parametrize("scenario", ALG003_NOISE_SCENARIOS, ids=lambda s: s.scenario_id)
@pytest.mark.parametrize("dt_variant", ALG003_DT_VARIANTS)
def test_alg003_noise_fixture_is_unchanged_through_alg006_final_path(
    scenario,
    dt_variant,
) -> None:
    actual = run_alg003_noise(Alg006CandidateACore(), scenario, dt_variant)
    inherited = run_alg003_noise(
        Alg005CandidateACore(Alg005Configuration()),
        scenario,
        dt_variant,
    )
    assert actual == inherited


@pytest.mark.parametrize("scenario", ALG003_SIGNAL_SCENARIOS, ids=lambda s: s.scenario_id)
@pytest.mark.parametrize("dt_variant", ALG003_DT_VARIANTS)
def test_alg003_signal_fixture_is_unchanged_through_alg006_final_path(
    scenario,
    dt_variant,
) -> None:
    actual = run_alg003_signal(Alg006CandidateACore(), scenario, dt_variant)
    inherited = run_alg003_signal(
        Alg005CandidateACore(Alg005Configuration()),
        scenario,
        dt_variant,
    )
    assert actual == inherited


@pytest.mark.parametrize("dt", [0.020, 0.037])
def test_alg001_and_alg002_relations_survive_alg006_final_path(dt) -> None:
    alg001 = {}
    for scenario in ALG001_SCENARIOS:
        core = Alg006CandidateACore()
        values = tuple(
            core.update(scenario.relative_pitch_rad, 0.0, dt)
            for _ in range(6)
        )
        alg001[scenario.scenario_id] = values[-1]
    assert alg001["ALG001-N00"] == 0.0
    assert alg001["ALG001-P01"] < 0.0
    assert alg001["ALG001-N01"] > 0.0
    assert alg001["ALG001-P02"] == pytest.approx(2.0 * alg001["ALG001-P01"])
    assert alg001["ALG001-N02"] == pytest.approx(-alg001["ALG001-P02"])

    alg002 = {}
    for scenario in ALG002_SCENARIOS:
        core = Alg006CandidateACore()
        values = tuple(
            core.update(
                scenario.relative_pitch_rad,
                scenario.relative_pitch_rate_rad_s,
                dt,
            )
            for _ in range(6)
        )
        alg002[scenario.scenario_id] = values[-1]
    assert alg002["ALG002-P01"] < alg002["ALG002-P00"] < alg002["ALG002-P02"]
    assert alg002["ALG002-N01"] > alg002["ALG002-N00"] > alg002["ALG002-N02"]
    assert alg002["ALG002-Z01"] < 0.0 < alg002["ALG002-Z02"]


@pytest.mark.parametrize(
    "scenario",
    ALG005_SCRIPTED_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg005_scripted_process_is_unchanged_through_alg006_final_path(
    scenario,
) -> None:
    actual = run_alg005_scripted(scenario, _controller())
    inherited = run_alg005_scripted(scenario)
    assert actual == inherited


@pytest.mark.parametrize(
    "scenario",
    ALG005_DYNAMIC_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_alg005_level_e_is_unchanged_through_alg006_final_path(scenario) -> None:
    actual = run_alg005_dynamic(scenario, _controller())
    inherited = run_alg005_dynamic(scenario)
    assert actual == inherited


def test_alg006_reset_and_order_have_no_cross_run_history() -> None:
    controller = _controller()
    scenario = ALG005_SCRIPTED_BY_ID["ALG005-D03P"]
    first = run_alg005_scripted(scenario, controller)
    run_alg005_scripted(ALG005_SCRIPTED_BY_ID["ALG005-D90N"], controller)
    replay = run_alg005_scripted(scenario, controller)
    assert first == replay
    assert controller.allocation_observation.disposition in {
        AllocationDisposition.ORDINARY,
        AllocationDisposition.TIMEOUT,
    }


def test_numeric_tolerance_helper_matches_frozen_profile() -> None:
    assert tolerance(0.8, 0.6) == 1e-9 + 1e-6 * 0.8
    assert len(BASE_CASES) == 9
