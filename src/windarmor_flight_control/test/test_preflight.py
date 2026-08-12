from dataclasses import replace

import pytest

from windarmor_flight_control.core.authority import CommandAuthority
from windarmor_flight_control.core.models import FanSystemState
from windarmor_flight_control.core.preflight import (
    FanSafetyReadback,
    MotorSafetyReadback,
    PreflightContext,
    PreflightReason,
    evaluate_preflight,
)
from windarmor_flight_control.testing import make_fake_flight_state


NAMES = ("axis_a", "axis_b")


def healthy_context(**overrides):
    state = make_fake_flight_state(NAMES)
    fans = replace(state.fans, control_state="MANUAL_DISARMED", enabled=True)
    state = replace(
        state,
        fans=fans,
        system=replace(
            state.system,
            command_authority=CommandAuthority.NONE,
            authority_generation=0,
            motor_control_mode="MANUAL",
            fan_control_state="MANUAL_DISARMED",
            flight_control_active=False,
            actuation_allowed=False,
        ),
    )
    values = dict(
        state=state,
        motor_safety=MotorSafetyReadback(
            node_active=True,
            controller_state="MANUAL_RUNNING",
            public_control_mode="MANUAL",
            e_stop_latched=False,
            error_latched=False,
            feedback_safety_fault_latched=False,
        ),
        fan_safety=FanSafetyReadback(
            e_stop_latched=False,
            control_state="MANUAL_DISARMED",
            enabled_observed=True,
            enabled=True,
            manual_armed=False,
            legacy_auto_requested=False,
            legacy_auto_active=False,
            passive_for_takeover=True,
        ),
        motor_safety_fresh=True,
        fan_safety_fresh=True,
        controller_loaded=True,
        controller_inhibited=False,
        monotonic_valid=True,
        no_conflicting_attempt=True,
    )
    values.update(overrides)
    return PreflightContext(**values)


def test_healthy_complete_preflight_is_ready():
    result = evaluate_preflight(healthy_context())
    assert result.ready
    assert result.reason is PreflightReason.READY


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda c: replace(
                c,
                state=replace(c.state, imu=replace(c.state.imu, fresh=False)),
            ),
            PreflightReason.IMU_STALE,
        ),
        (
            lambda c: replace(
                c,
                state=replace(c.state, imu=replace(c.state.imu, valid=False)),
            ),
            PreflightReason.IMU_INVALID,
        ),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    motors={
                        name: replace(motor, valid=False)
                        for name, motor in c.state.motors.items()
                    },
                ),
            ),
            PreflightReason.MOTOR_INVALID,
        ),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    motors={
                        name: replace(motor, fresh=False)
                        for name, motor in c.state.motors.items()
                    },
                ),
            ),
            PreflightReason.MOTOR_STALE,
        ),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    motors={
                        name: replace(motor, healthy=False)
                        for name, motor in c.state.motors.items()
                    },
                ),
            ),
            PreflightReason.MOTOR_UNHEALTHY,
        ),
        (lambda c: replace(c, motor_safety_fresh=False), PreflightReason.MOTOR_SAFETY_STALE),
        (lambda c: replace(c, fan_safety_fresh=False), PreflightReason.FAN_SAFETY_STALE),
        (lambda c: replace(c, motor_safety=None), PreflightReason.MOTOR_SAFETY_UNOBSERVED),
        (lambda c: replace(c, fan_safety=None), PreflightReason.FAN_SAFETY_UNOBSERVED),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    system=replace(c.state.system, e_stop_active=None),
                ),
            ),
            PreflightReason.GLOBAL_ESTOP_UNKNOWN,
        ),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    system=replace(c.state.system, e_stop_active=True),
                ),
            ),
            PreflightReason.GLOBAL_ESTOP_ACTIVE,
        ),
        (
            lambda c: replace(
                c, motor_safety=replace(c.motor_safety, error_latched=True)
            ),
            PreflightReason.MOTOR_ERROR_LATCHED,
        ),
        (
            lambda c: replace(
                c,
                motor_safety=replace(
                    c.motor_safety, feedback_safety_fault_latched=True
                ),
            ),
            PreflightReason.MOTOR_FEEDBACK_SAFETY_FAULT,
        ),
        (
            lambda c: replace(
                c,
                motor_safety=replace(c.motor_safety, public_control_mode="AUTO"),
            ),
            PreflightReason.MOTOR_MODE_NOT_MANUAL,
        ),
        (
            lambda c: replace(
                c,
                fan_safety=replace(
                    c.fan_safety,
                    legacy_auto_requested=True,
                    legacy_auto_active=True,
                    passive_for_takeover=False,
                ),
            ),
            PreflightReason.FAN_LEGACY_AUTO_ACTIVE,
        ),
        (
            lambda c: replace(
                c,
                fan_safety=replace(
                    c.fan_safety, manual_armed=True, passive_for_takeover=False
                ),
            ),
            PreflightReason.FAN_MANUAL_ARMED,
        ),
        (
            lambda c: replace(
                c,
                fan_safety=replace(c.fan_safety, enabled=False),
            ),
            PreflightReason.FAN_DISABLED,
        ),
        (
            lambda c: replace(
                c,
                fan_safety=replace(
                    c.fan_safety, enabled_observed=False, enabled=False
                ),
            ),
            PreflightReason.FAN_ENABLED_UNKNOWN,
        ),
        (
            lambda c: replace(
                c,
                fan_safety=replace(c.fan_safety, passive_for_takeover=False),
            ),
            PreflightReason.FAN_NOT_PASSIVE,
        ),
        (lambda c: replace(c, controller_inhibited=True), PreflightReason.CONTROLLER_INHIBITED),
        (lambda c: replace(c, controller_loaded=False), PreflightReason.CONTROLLER_UNAVAILABLE),
        (lambda c: replace(c, monotonic_valid=False), PreflightReason.MONOTONIC_INVALID),
        (
            lambda c: replace(c, no_conflicting_attempt=False),
            PreflightReason.AUTHORITY_ATTEMPT_CONFLICT,
        ),
        (
            lambda c: replace(
                c,
                state=replace(
                    c.state,
                    system=replace(c.state.system, required_inputs_fresh=False),
                ),
            ),
            PreflightReason.REQUIRED_INPUTS_STALE,
        ),
    ],
)
def test_each_preflight_gate_has_stable_reason(mutate, reason):
    context = mutate(healthy_context())
    if reason in {PreflightReason.IMU_STALE, PreflightReason.MOTOR_STALE}:
        context = replace(
            context,
            state=replace(
                context.state,
                system=replace(context.state.system, required_inputs_fresh=True),
            ),
        )
    result = evaluate_preflight(context)
    assert not result.ready
    assert result.reason is reason
