"""控制状态机与状态管理。"""

import threading
from enum import Enum, auto


class ControllerState(Enum):
    """IMU-电机控制节点的生命周期状态。

    状态机流程（正向）：
      UNINITIALIZED → INITIALIZING → AUTO_RUNNING / MANUAL_RUNNING
    AUTO_RUNNING 和 MANUAL_RUNNING 之间可相互切换。

    可随时从任意运行状态进入 EMERGENCY_STOP 或 ERROR。
    SHUTTING_DOWN 为单向终态，进入后不再恢复。
    """
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    AUTO_RUNNING = auto()
    MANUAL_RUNNING = auto()
    EMERGENCY_STOP = auto()
    ERROR = auto()
    SHUTTING_DOWN = auto()


class StateManager:
    """线程安全的控制状态管理器。

    参数：
        node: ROS2 LifecycleNode 实例，用于日志输出。
        stop_auto_zero_callback: 从运行态切至非运行态时调用的回调（停止自动归零）。
    """

    def __init__(
        self,
        node,
        stop_auto_zero_callback=None,
        state_change_callback=None,
    ):
        self._node = node
        self._state = ControllerState.UNINITIALIZED
        self._state_lock = threading.RLock()
        self._stop_auto_zero_callback = stop_auto_zero_callback
        self._state_change_callback = state_change_callback

    @property
    def state(self) -> ControllerState:
        """获取当前状态（线程安全）。"""
        with self._state_lock:
            return self._state

    @property
    def state_name(self) -> str:
        """获取当前状态名称（线程安全）。"""
        with self._state_lock:
            return self._state.name

    def transition_to(self, new_state: ControllerState) -> None:
        """带日志记录的状态转换。

        从运行态（AUTO_RUNNING/MANUAL_RUNNING）切至非运行态时，
        自动调用 stop_auto_zero_callback。
        """
        with self._state_lock:
            old_name = self._state.name
            self._state = new_state
            new_name = self._state.name
            self._node.get_logger().info(f"状态转换: {old_name} -> {new_name}")
            if old_name in ("AUTO_RUNNING", "MANUAL_RUNNING") and new_name not in (
                "AUTO_RUNNING", "MANUAL_RUNNING"
            ):
                if self._stop_auto_zero_callback:
                    self._stop_auto_zero_callback()
            if self._state_change_callback:
                self._state_change_callback(new_state)

    def is_running(self) -> bool:
        """当前是否处于运行态（AUTO 或 MANUAL）。"""
        with self._state_lock:
            return self._state in (ControllerState.AUTO_RUNNING, ControllerState.MANUAL_RUNNING)

    def is_auto_running(self) -> bool:
        """当前是否处于 AUTO_RUNNING 状态。"""
        with self._state_lock:
            return self._state == ControllerState.AUTO_RUNNING

    def is_manual_running(self) -> bool:
        """当前是否处于 MANUAL_RUNNING 状态。"""
        with self._state_lock:
            return self._state == ControllerState.MANUAL_RUNNING

    def is_emergency_or_error(self) -> bool:
        """当前是否处于急停或错误状态。"""
        with self._state_lock:
            return self._state in (ControllerState.EMERGENCY_STOP, ControllerState.ERROR)


def public_control_mode(state: ControllerState, *, active: bool) -> str:
    """把内部状态稳定映射为对外发布的控制模式。"""
    if not active:
        return "DISABLED"
    if state == ControllerState.AUTO_RUNNING:
        return "AUTO"
    if state == ControllerState.MANUAL_RUNNING:
        return "MANUAL"
    if state == ControllerState.EMERGENCY_STOP:
        return "EMERGENCY_STOP"
    if state == ControllerState.ERROR:
        return "ERROR"
    return "DISABLED"
