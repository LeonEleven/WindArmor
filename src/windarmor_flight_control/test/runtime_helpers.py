from copy import deepcopy
from types import SimpleNamespace

from windarmor_flight_control.runtime.config import (
    PARAMETER_DEFAULTS,
    build_runtime_config,
)


def runtime_config(**overrides):
    values = deepcopy(PARAMETER_DEFAULTS)
    values.update(overrides)
    return build_runtime_config(values)


def stamp(ns: int):
    return SimpleNamespace(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)


def imu_message(stamp_ns=1, **overrides):
    values = dict(
        header=SimpleNamespace(stamp=stamp(stamp_ns)),
        orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        angular_velocity=SimpleNamespace(x=0.1, y=0.2, z=0.3),
        linear_acceleration=SimpleNamespace(x=1.0, y=2.0, z=9.8),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def relative_message(stamp_ns=1, roll=0.1, pitch=-0.2):
    return SimpleNamespace(
        header=SimpleNamespace(stamp=stamp(stamp_ns)),
        vector=SimpleNamespace(x=roll, y=pitch, z=0.0),
    )


def motor_entry(name, can_id, *, has_feedback=True, **overrides):
    values = dict(
        logical_name=name,
        can_id=can_id,
        has_feedback=has_feedback,
        position_valid=has_feedback,
        position_rad=0.1,
        velocity_valid=has_feedback,
        velocity_rad_s=0.2,
        torque_valid=has_feedback,
        torque_nm=0.3,
        temperature_valid=has_feedback,
        temperature_c=30.0,
        device_mode_valid=has_feedback,
        device_mode=2,
        fault_flags_valid=has_feedback,
        fault_flags=0,
        feedback_age_sec=0.0,
        valid=has_feedback,
        fresh=has_feedback,
        healthy=has_feedback,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def motor_message(names=("axis_a", "axis_b"), **entry_overrides):
    return SimpleNamespace(
        motors=[
            motor_entry(name, index + 1, **entry_overrides)
            for index, name in enumerate(names)
        ]
    )


def motor_safety_message(sequence=1, source_epoch=100, **overrides):
    values = dict(
        source_epoch=source_epoch,
        observation_sequence=sequence,
        node_active=True,
        controller_state="MANUAL_RUNNING",
        public_control_mode="MANUAL",
        e_stop_latched=False,
        error_latched=False,
        feedback_safety_fault_latched=False,
        transition_present=True,
        transition_sequence=1,
        transition_reason="configure_success",
        transition_source="lifecycle",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def fan_safety_message(sequence=1, source_epoch=100, **overrides):
    values = dict(
        source_epoch=source_epoch,
        observation_sequence=sequence,
        e_stop_latched=False,
        control_state="MANUAL_DISARMED",
        enabled_observed=True,
        enabled=True,
        manual_armed=False,
        legacy_auto_requested=False,
        legacy_auto_active=False,
        safety_reason="safe stop",
        passive_for_takeover=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)
