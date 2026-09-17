"""Frozen ALG005-FIXTURE-v1 and ALG005-SYNTHETIC-PLANT-v1.

All states are in memory. Interval scoring is independent of Candidate timers.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from windarmor_flight_control.algorithms.alg005_candidate_a import (
    Alg005CandidateAController, ProcessObservation, RecoveryPhase,
)
from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.core.validation import (
    validate_flight_state, validate_flight_command,
)
from windarmor_flight_control.testing import make_fake_flight_state

DT = 0.020
ABS_TOL = 1e-9
REL_TOL = 1e-6
MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")


@dataclass(frozen=True)
class ScriptedScenario:
    scenario_id: str
    inputs: tuple[tuple[float, float], ...]
    reset_before: tuple[int, ...] = ()


_ZERO = ((0.0, 0.0),)
_D01 = _ZERO * 15 + ((0.040, 0.0),) + ((0.050, 0.150),) * 2
_D02_START = _ZERO * 15 + ((0.050, 0.200),) + ((0.050, 0.150),) * 4
_D02 = _D02_START + ((0.018, 0.080),) * 4 + ((0.009, 0.040),) * 15
_D03 = (_D02_START + ((0.018, 0.080),) * 5 + ((0.009, 0.040),) * 5
        + ((0.025, 0.120),) * 5 + ((0.018, 0.080),) * 5
        + ((0.009, 0.040),) * 15)
_D04 = (((0.039, 0.199), (0.0, 0.200), (0.020, 0.100))
        + ((0.010, 0.050),) * 15)
_D90 = _ZERO * 15 + ((0.050, 0.200),) * 150 + _ZERO * 5
SCRIPTED_SCENARIOS = (ScriptedScenario("ALG005-D00", _ZERO * 30),) + tuple(
    ScriptedScenario(f"ALG005-{name}{suffix}",
                     tuple((sign * p, sign * r) for p, r in inputs),
                     (1,) if name == "D04" else ())
    for name, inputs in (("D01", _D01), ("D02", _D02), ("D03", _D03),
                         ("D04", _D04), ("D90", _D90))
    for suffix, sign in (("P", 1), ("N", -1))
)
SCRIPTED_BY_ID = {s.scenario_id: s for s in SCRIPTED_SCENARIOS}


@dataclass(frozen=True)
class DynamicScenario:
    scenario_id: str
    theta0: float
    omega0: float
    steps: int = 200
    pre_steps: int = 0
    impulse: float = 0.0
    external_acceleration: float = 0.0


DYNAMIC_SCENARIOS = (DynamicScenario("ALG005-E00", 0.0, 0.0),) + tuple(
    DynamicScenario(f"ALG005-{name}{suffix}", sign * theta, sign * omega,
                    steps, pre_steps, sign * impulse, sign * external)
    for name, theta, omega, steps, pre_steps, impulse, external in (
        ("E01", 0.080, 0.0, 200, 0, 0.0, 0.0),
        ("E02", 0.050, 0.200, 200, 0, 0.0, 0.0),
        ("E03", 0.050, -0.200, 200, 0, 0.0, 0.0),
        ("E04", 0.0, 0.0, 200, 25, 0.250, 0.0),
        ("E90", 0.050, 0.0, 175, 0, 0.0, 0.700),
    )
    for suffix, sign in (("P", 1), ("N", -1))
)
DYNAMIC_BY_ID = {s.scenario_id: s for s in DYNAMIC_SCENARIOS}


def motion_state(theta: float, omega: float, index: int = 0):
    state = make_fake_flight_state(MOTOR_NAMES)
    return replace(state, timestamp_sec=index * DT, sequence=index,
                   imu=replace(state.imu, pitch_rad=theta,
                               relative_pitch_rad=theta,
                               relative_pitch_rate_rad_s=omega))


@dataclass(frozen=True)
class Sample:
    time: float
    theta: float
    omega: float
    u: float
    requested: float
    observation: ProcessObservation
    command: FlightCommand
    alpha: float = 0.0
    external_acceleration: float = 0.0
    dt: float = DT

    @property
    def phase(self):
        return self.observation.phase


def _sample(controller, theta, omega, index, previous_motion):
    state = motion_state(theta, omega, index)
    validate_flight_state(state, MOTOR_NAMES)
    command = controller.update(state, DT)
    validate_flight_command(command, MOTOR_NAMES)
    # Independent frozen inherited requested target for directed-transition tests.
    p, r = previous_motion if previous_motion is not None else (theta, omega)
    requested = -(p + theta) / 2.0 - 0.1 * (r + omega) / 2.0
    return Sample(index * DT, theta, omega,
                  controller.observation.final_process_intent, requested,
                  controller.observation, command)


def run_scripted(scenario: ScriptedScenario, controller=None):
    controller = controller or Alg005CandidateAController(MOTOR_NAMES)
    controller.reset()
    result, previous_motion = [], None
    for index, (theta, omega) in enumerate(scenario.inputs):
        if index in scenario.reset_before:
            controller.reset()
            previous_motion = None
        result.append(_sample(controller, theta, omega, index, previous_motion))
        previous_motion = (theta, omega)
    return tuple(result)


def run_dynamic(scenario: DynamicScenario, controller=None):
    controller = controller or Alg005CandidateAController(MOTOR_NAMES)
    controller.reset()
    theta, omega = scenario.theta0, scenario.omega0
    result, previous_motion = [], None
    for index in range(scenario.pre_steps + scenario.steps):
        if index == scenario.pre_steps:
            omega += scenario.impulse
        sample = _sample(controller, theta, omega, index, previous_motion)
        external = (scenario.external_acceleration
                    if index >= scenario.pre_steps else 0.0)
        alpha = 1.0 * theta + 6.0 * sample.u - 2.4 * omega + external
        result.append(replace(sample, alpha=alpha, external_acceleration=external))
        previous_motion = (theta, omega)
        omega = omega + DT * alpha
        theta = theta + DT * omega
    return tuple(result)


def metrics(samples: tuple[Sample, ...]):
    """Score fixed first origins and the final confirmation leading to run end."""
    disturbed = next((i for i, s in enumerate(samples)
                      if s.phase == RecoveryPhase.DISTURBED), None)
    start = disturbed if disturbed is not None else 0
    scoring = samples[start:]
    first_settling = next((i for i in range(start, len(samples))
                           if samples[i].phase == RecoveryPhase.SETTLING), None)
    confirmation = None
    if disturbed is not None and samples[-1].phase == RecoveryPhase.STABLE:
        confirmation = len(samples) - 1
        while confirmation > start and samples[confirmation - 1].phase == RecoveryPhase.STABLE:
            confirmation -= 1
    final_settling = None
    if confirmation is not None and samples[confirmation - 1].phase == RecoveryPhase.SETTLING:
        final_settling = confirmation - 1
        while final_settling > start and samples[final_settling - 1].phase == RecoveryPhase.SETTLING:
            final_settling -= 1

    def interval(origin):
        if origin is None or confirmation is None:
            return None
        return math.fsum(s.dt for s in samples[origin:confirmation + 1])

    timeout = next((s.observation.episode_elapsed_sec for s in scoring
                    if s.phase == RecoveryPhase.TIMED_OUT), None)
    theta0 = scoring[0].theta
    crossing = next((i for i, s in enumerate(scoring)
                     if theta0 != 0 and s.theta * theta0 <= 0), None)
    overshoot = (max(0.0, max(-math.copysign(1.0, theta0) * s.theta
                             for s in scoring[crossing:]))
                 if crossing is not None else 0.0)
    significant = [s.theta for s in scoring if abs(s.theta) > 0.005]
    changes = []
    periods = []
    previous_phase = None
    for sample in samples:
        periods.append(sample.dt)
        if len(periods) - 1 >= start and sample.phase != previous_phase:
            changes.append((math.fsum(periods), sample.phase.value))
        previous_phase = sample.phase
    end = confirmation if confirmation is not None else len(samples) - 1
    return {
        "recovery_time": interval(disturbed),
        "settling_completion_time": interval(first_settling),
        "final_settling_interval": interval(final_settling),
        "settling_setback_count": sum(
            samples[i - 1].phase == RecoveryPhase.SETTLING
            and samples[i].phase == RecoveryPhase.RECOVERING
            for i in range(start + 1, end + 1)),
        "peak_abs_pitch": max(abs(s.theta) for s in scoring),
        "peak_abs_pitch_rate": max(abs(s.omega) for s in scoring),
        "final_steady_state_error": abs(math.fsum(s.theta for s in samples[-25:]) / 25),
        "abstract_control_effort": math.fsum(abs(s.u) * s.dt for s in scoring),
        "phase_timeline": tuple(changes),
        "overshoot": overshoot,
        "overshoot_ratio": overshoot / abs(theta0) if theta0 != 0 else None,
        "effective_pitch_sign_reversal_count": sum(
            left * right < 0 for left, right in zip(significant, significant[1:])),
        "timeout_elapsed": timeout,
    }
