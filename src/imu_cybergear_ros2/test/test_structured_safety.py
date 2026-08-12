from rclpy.qos import DurabilityPolicy

from imu_cybergear_ros2.controller_state import (
    ControllerState,
    StateManager,
    TransitionReason,
    TransitionSource,
)
from imu_cybergear_ros2.structured_safety import build_motor_safety_snapshot


class Logger:
    def info(self, _message):
        pass

    def error(self, _message):
        pass


class Node:
    def get_logger(self):
        return Logger()


def transition(manager, state, reason=TransitionReason.CONFIGURE_START):
    return manager.transition_to(
        state,
        reason=reason,
        source=TransitionSource.LIFECYCLE,
    )


def snapshot(manager=None, *, active=True, fault=False):
    return build_motor_safety_snapshot(
        manager,
        node_active=active,
        feedback_safety_fault_latched=fault,
    )


def manual_manager():
    manager = StateManager(Node())
    transition(manager, ControllerState.INITIALIZING)
    transition(manager, ControllerState.MANUAL_RUNNING, TransitionReason.CONFIGURE_SUCCESS)
    return manager


def test_startup_uninitialized_and_inactive_are_explicit():
    initial = snapshot()
    assert initial.controller_state == "UNINITIALIZED"
    assert initial.public_control_mode == "DISABLED"
    assert not initial.transition_present
    inactive = snapshot(manual_manager(), active=False)
    assert inactive.controller_state == "MANUAL_RUNNING"
    assert inactive.public_control_mode == "DISABLED"
    assert not inactive.node_active


def test_manual_auto_estop_error_and_transition_metadata():
    manager = manual_manager()
    manual = snapshot(manager)
    assert manual.public_control_mode == "MANUAL"
    assert manual.transition_sequence == 2
    assert manual.transition_reason == "configure_success"

    transition(manager, ControllerState.AUTO_RUNNING, TransitionReason.USER_MODE_TOGGLE)
    assert snapshot(manager).public_control_mode == "AUTO"
    transition(manager, ControllerState.EMERGENCY_STOP, TransitionReason.TOPIC_ESTOP)
    stopped = snapshot(manager)
    assert stopped.e_stop_latched
    assert not stopped.error_latched

    transition(
        manager,
        ControllerState.MANUAL_RUNNING,
        TransitionReason.EXPLICIT_ESTOP_RECOVERY,
    )
    recovered = snapshot(manager)
    assert not recovered.e_stop_latched
    assert recovered.public_control_mode == "MANUAL"

    transition(manager, ControllerState.ERROR, TransitionReason.MOTOR_FEEDBACK_FAULT)
    failed = snapshot(manager)
    assert failed.error_latched
    assert failed.public_control_mode == "ERROR"
    assert manager.transition_to(
        ControllerState.MANUAL_RUNNING,
        reason=TransitionReason.EXPLICIT_ESTOP_RECOVERY,
        source=TransitionSource.LIFECYCLE,
    ).accepted is False


def test_feedback_safety_latch_is_authoritative_error_evidence():
    value = snapshot(manual_manager(), fault=True)
    assert value.feedback_safety_fault_latched
    assert value.error_latched


def test_qos_enum_expected_by_node_contract():
    assert DurabilityPolicy.TRANSIENT_LOCAL.name == "TRANSIENT_LOCAL"
