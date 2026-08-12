"""Pure fake-state helpers for algorithm examples and unit tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .core.authority import CommandAuthority
from .core.models import (
    FanChannelState,
    FanSystemState,
    FlightState,
    ImuState,
    MotorState,
    Quaternion,
    SystemState,
    Vector3,
)


def make_fake_flight_state(
    motor_names: Iterable[str], *, with_feedback: bool = True
) -> FlightState:
    """Create a fully observed in-memory state without ROS or hardware access.

    All numeric values are explicit test fixtures, not real safety defaults.
    Setting ``with_feedback`` false makes actuation unavailable.
    """

    names = tuple(motor_names)
    if with_feedback:
        motors = {
            name: MotorState(
                name=name,
                position_rad=0.0,
                velocity_rad_s=0.0,
                torque_nm=0.0,
                temperature_c=25.0,
                device_mode=2,
                fault_flags=0,
                feedback_age_sec=0.0,
                has_feedback=True,
                valid=True,
                fresh=True,
                healthy=True,
            )
            for name in names
        }
    else:
        motors = {
            name: MotorState(
                name=name,
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
            for name in names
        }
    output = FanChannelState(applied_command=0.0, output_known=True)
    return FlightState(
        timestamp_sec=1.0,
        sequence=1,
        imu=ImuState(
            orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
            roll_rad=0.0,
            pitch_rad=0.0,
            yaw_rad=0.0,
            relative_roll_rad=0.0,
            relative_pitch_rad=0.0,
            angular_velocity_rad_s=Vector3(x=0.0, y=0.0, z=0.0),
            linear_acceleration_m_s2=Vector3(x=0.0, y=0.0, z=9.80665),
            sample_age_sec=0.0,
            valid=True,
            fresh=True,
            connected=True,
            zero_generation=1,
        ),
        motors=motors,
        fans=FanSystemState(
            left=output,
            right=output,
            enabled=True,
            control_state="FLIGHT_CONTROL",
        ),
        system=SystemState(
            command_authority=CommandAuthority.FLIGHT_CONTROL,
            authority_epoch=1,
            authority_generation=1,
            e_stop_active=False,
            motor_control_mode="AUTO",
            fan_control_state="FLIGHT_CONTROL",
            flight_control_active=True,
            actuation_allowed=with_feedback,
            required_inputs_fresh=with_feedback,
        ),
    )


def make_unobserved_flight_state(motor_names: Iterable[str]) -> FlightState:
    """Create a startup-like state whose external observations are unknown."""

    state = make_fake_flight_state(motor_names, with_feedback=False)
    unknown_output = FanChannelState(applied_command=None, output_known=False)
    return replace(
        state,
        imu=ImuState(
            orientation=None,
            roll_rad=None,
            pitch_rad=None,
            yaw_rad=None,
            relative_roll_rad=None,
            relative_pitch_rad=None,
            angular_velocity_rad_s=None,
            linear_acceleration_m_s2=None,
            sample_age_sec=None,
            valid=False,
            fresh=False,
            connected=None,
            zero_generation=None,
        ),
        fans=FanSystemState(
            left=unknown_output,
            right=unknown_output,
            enabled=None,
            control_state=None,
        ),
        system=SystemState(
            command_authority=CommandAuthority.NONE,
            authority_epoch=0,
            authority_generation=0,
            e_stop_active=None,
            motor_control_mode=None,
            fan_control_state=None,
            flight_control_active=False,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )


def make_stale_flight_state(motor_names: Iterable[str]) -> FlightState:
    """Create observed, structurally valid data that is no longer fresh."""

    state = make_fake_flight_state(motor_names)
    stale_motors = {
        name: replace(motor, fresh=False, healthy=False)
        for name, motor in state.motors.items()
    }
    return replace(
        state,
        imu=replace(state.imu, fresh=False),
        motors=stale_motors,
        system=replace(
            state.system,
            actuation_allowed=False,
            required_inputs_fresh=False,
        ),
    )
