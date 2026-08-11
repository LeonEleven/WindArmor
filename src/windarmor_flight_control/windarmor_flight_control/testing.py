"""Pure fake-state helpers for algorithm examples and unit tests."""

from __future__ import annotations

from collections.abc import Iterable

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
    """Create explicit in-memory test data without ROS or hardware access."""

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
            authority_generation=1,
            e_stop_active=False,
            motor_control_mode="AUTO",
            fan_control_state="FLIGHT_CONTROL",
            flight_control_active=True,
            actuation_allowed=True,
            required_inputs_fresh=True,
        ),
    )
