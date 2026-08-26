"""依据权威内存状态构造的观测器专用电机安全快照。"""

from dataclasses import dataclass

from .controller_state import ControllerState, StateManager, public_control_mode


@dataclass(frozen=True)
class MotorSafetySnapshot:
    node_active: bool
    controller_state: str
    public_control_mode: str
    e_stop_latched: bool
    error_latched: bool
    feedback_safety_fault_latched: bool
    transition_present: bool
    transition_sequence: int
    transition_reason: str
    transition_source: str


def build_motor_safety_snapshot(
    state_manager: StateManager | None,
    *,
    node_active: bool,
    feedback_safety_fault_latched: bool,
) -> MotorSafetySnapshot:
    """复制安全状态，不访问驱动，也不执行状态转换。"""

    if not isinstance(node_active, bool):
        raise TypeError("node_active must be a bool")
    if not isinstance(feedback_safety_fault_latched, bool):
        raise TypeError("feedback_safety_fault_latched must be a bool")
    state = (
        ControllerState.UNINITIALIZED
        if state_manager is None
        else state_manager.state
    )
    transition = None if state_manager is None else state_manager.last_transition
    error_latched = (
        state is ControllerState.ERROR or feedback_safety_fault_latched
    )
    return MotorSafetySnapshot(
        node_active=node_active,
        controller_state=state.name,
        public_control_mode=public_control_mode(state, active=node_active),
        e_stop_latched=state is ControllerState.EMERGENCY_STOP,
        error_latched=error_latched,
        feedback_safety_fault_latched=feedback_safety_fault_latched,
        transition_present=transition is not None,
        transition_sequence=0 if transition is None else transition.sequence,
        transition_reason="" if transition is None else transition.reason.value,
        transition_source="" if transition is None else transition.source.value,
    )
