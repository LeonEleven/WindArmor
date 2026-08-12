"""电机管理：连接初始化、统一目标推进、归零和手动控制。"""

import math
import time
from typing import Dict, Iterable, List, Optional, Tuple

from std_msgs.msg import String

from .controller_state import (
    ControllerState,
    TransitionOutcome,
    TransitionReason,
    TransitionSource,
)
from .cybergear_driver import SDO_RUN_MODE, SDO_TARGET_POS, SDO_TARGET_SPEED
from .motor_motion import (
    MotionSource,
    advance_target,
    manual_event_increment,
    speed_for_source,
)
from .motor_ownership import MotorCommandOwner, MotorOwnershipCore, OwnershipResult
from .motor_health import MotorHealthReason, MotorSafetyFaultSnapshot
from .transport_recovery import CyberGearTransportError, TransportEvent


def clamp(value: float, low: float, high: float) -> float:
    """将值约束在 [low, high] 区间内。"""
    return max(low, min(high, value))


def deg_to_rad(deg: float) -> float:
    """角度（度）转弧度。"""
    return deg * math.pi / 180.0


class MotorManager:
    """管理电机初始化以及所有普通位置命令的统一推进。"""

    def __init__(self, node, state_mgr):
        self._node = node
        self._state = state_mgr
        self._motion_source = MotionSource.IDLE
        self._motion_timer = None
        self._last_motion_tick_time: Optional[float] = None
        self._manual_repeat_times: Dict[Tuple[int, float], float] = {}
        self._init_touched_motor_ids: List[int] = []
        self._init_entered_control_mode_ids: List[int] = []
        self._init_successful_motor_ids: List[int] = []
        self._current_init_stage = "idle"
        self._ownership = MotorOwnershipCore(
            handoff_timeout_sec=float(
                getattr(node, "_motor_flight_handoff_timeout_sec", 1.5)
            ),
            command_timeout_sec=float(
                getattr(node, "_motor_flight_command_timeout_sec", 0.25)
            )
        )
        self._flight_commit_in_progress = False

    @property
    def motion_source(self) -> MotionSource:
        return self._motion_source

    @property
    def motion_timer(self):
        return self._motion_timer

    @property
    def command_owner(self) -> MotorCommandOwner:
        return self._ownership.owner

    @property
    def ownership(self) -> MotorOwnershipCore:
        return self._ownership

    @property
    def init_touched_motor_ids(self) -> Tuple[int, ...]:
        return tuple(self._init_touched_motor_ids)

    @property
    def init_entered_control_mode_ids(self) -> Tuple[int, ...]:
        return tuple(self._init_entered_control_mode_ids)

    @property
    def init_successful_motor_ids(self) -> Tuple[int, ...]:
        return tuple(self._init_successful_motor_ids)

    @property
    def current_init_stage(self) -> str:
        return self._current_init_stage

    # ------------------------------------------------------------------
    # 电机连接与初始化
    # ------------------------------------------------------------------

    def connect_and_init_motors(self) -> bool:
        """连接电机并初始化运控模式。"""
        self._init_touched_motor_ids = []
        self._init_entered_control_mode_ids = []
        self._init_successful_motor_ids = []
        self._current_init_stage = "connecting"
        self._node.get_logger().info("正在连接电机...")
        try:
            with self._node._driver_io_lock:
                connected = self._node._driver.connect_with_retry(
                    max_attempts=5,
                    initial_delay=1.0,
                    on_status=self._on_motor_connect_status,
                )
        except Exception as exc:
            connected = False
            self._node.get_logger().error(f"连接电机驱动时发生异常: {exc}")
        if not connected:
            self._node.get_logger().error(
                "电机连接失败（已重试 5 次）！请检查：\n"
                "  1. CAN HAT+ 是否已完成开机初始化\n"
                "  2. 电机电源是否已接通\n"
                "  3. CAN 总线接线是否正确"
            )
            result = self._state.transition_to(
                ControllerState.ERROR,
                reason=TransitionReason.DRIVER_CONNECT_FAILURE,
                source=TransitionSource.MOTOR_MANAGER,
            )
            if result.outcome is TransitionOutcome.REJECTED:
                self._node.get_logger().error(
                    "关键状态转换被拒绝：驱动连接失败后无法进入 ERROR"
                )
            self._current_init_stage = "failed:connect"
            return False

        if self._initialization_transport_fault_latched():
            return False

        self._node.get_logger().info("电机连接成功，正在初始化运控模式...")
        max_init_retry = 3
        for mid in self._node._motor_ids:
            for attempt in range(max_init_retry):
                if self._initialization_transport_fault_latched():
                    return False
                try:
                    self._mark_init_touched(mid)
                    self._current_init_stage = f"ID{mid}:run_mode"
                    if self._initialization_transport_fault_latched():
                        return False
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:target_speed"
                    if self._initialization_transport_fault_latched():
                        return False
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_float(
                            mid, SDO_TARGET_SPEED, self._node._default_speed
                        )
                    with self._node._lock:
                        self._node._current_speeds[mid] = self._node._default_speed
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:target_position"
                    if self._initialization_transport_fault_latched():
                        return False
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                    with self._node._lock:
                        # _current_targets 始终表示最近一次成功写入驱动的位置目标。
                        self._node._current_targets[mid] = 0.0
                        self._node._desired_targets[mid] = 0.0
                        self._node._last_target_change_time[mid] = time.monotonic()
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:enter_control_mode"
                    if self._initialization_transport_fault_latched():
                        return False
                    with self._node._driver_io_lock:
                        self._node._driver.enter_control_mode(mid)
                    if mid not in self._init_entered_control_mode_ids:
                        self._init_entered_control_mode_ids.append(mid)
                    if mid not in self._init_successful_motor_ids:
                        self._init_successful_motor_ids.append(mid)
                    self._node._sleep(0.08)
                    self._node.get_logger().info(f"电机 ID{mid} 初始化完成")
                    break
                except Exception as exc:
                    if attempt < max_init_retry - 1:
                        self._node.get_logger().warn(
                            f"初始化电机 ID{mid} 失败 "
                            f"(尝试 {attempt + 1}/{max_init_retry}): {exc}"
                        )
                        self._node._sleep(0.3)
                    else:
                        self._node.get_logger().error(
                            f"初始化电机 ID{mid} 失败（已重试 {max_init_retry} 次）: {exc}"
                        )
                        result = self._state.transition_to(
                            ControllerState.ERROR,
                            reason=TransitionReason.MOTOR_INIT_FAILURE,
                            source=TransitionSource.MOTOR_MANAGER,
                        )
                        if result.outcome is TransitionOutcome.REJECTED:
                            self._node.get_logger().error(
                                "关键状态转换被拒绝：电机初始化失败后无法进入 ERROR"
                            )
                        self._current_init_stage = f"failed:{self._current_init_stage}"
                        return False

        if self._initialization_transport_fault_latched():
            return False
        result = self._state.transition_to(
            ControllerState.MANUAL_RUNNING,
            reason=TransitionReason.CONFIGURE_SUCCESS,
            source=TransitionSource.MOTOR_MANAGER,
        )
        if result.outcome is not TransitionOutcome.CHANGED:
            self._node.get_logger().error(
                "关键状态转换被拒绝或未改变：初始化完成后无法进入 MANUAL_RUNNING"
            )
            self._current_init_stage = "failed:state_transition"
            return False
        with self._node._lock:
            self._node._init_complete = True
            self._node._command_fault_active = False
        self._current_init_stage = "complete"
        return True

    def _initialization_transport_fault_latched(self) -> bool:
        if not getattr(self._node, "_transport_fault_active", False):
            return False
        self._current_init_stage = "failed:transport"
        self._node.get_logger().error(
            "电机初始化因 transport 故障中止；不会继续发送初始化命令"
        )
        return True

    def _mark_init_touched(self, motor_id: int) -> None:
        if motor_id not in self._init_touched_motor_ids:
            self._init_touched_motor_ids.append(motor_id)

    def _on_motor_connect_status(self, status: str) -> None:
        """接收电机连接状态变化并发布到 /motor/status。"""
        if not self._node._is_active:
            return
        try:
            if self._node._motor_status_pub is not None:
                msg = String()
                msg.data = f"motor_connect:{status}"
                self._node._motor_status_pub.publish(msg)
            if status == "connecting":
                self._node.get_logger().info("正在尝试连接电机 CAN 总线...")
            elif status == "reconnecting":
                self._node.get_logger().info("电机连接失败，正在重试...")
            elif status == "failed":
                self._node.get_logger().error("电机连接彻底失败！")
        except Exception as exc:
            self._node.get_logger().error(f"发布电机连接状态时发生异常: {exc}")

    # ------------------------------------------------------------------
    # 固定周期统一推进器
    # ------------------------------------------------------------------

    def start_motion_timer(self) -> None:
        """创建唯一的固定周期目标推进定时器。"""
        if self._motion_timer is not None:
            return
        self._last_motion_tick_time = None
        self._motion_timer = self._node.create_timer(
            self._node._command_interval, self._motion_tick
        )

    def stop_motion_timer(self) -> None:
        """销毁推进定时器并丢弃所有尚未完成的普通目标。"""
        timer = self._motion_timer
        self._motion_timer = None
        self._last_motion_tick_time = None
        if timer is not None:
            self._node.destroy_timer(timer)
        self.halt_motion()

    def _motion_tick(self, now: Optional[float] = None) -> None:
        """按真实 dt 推进 current_targets；第一帧只初始化时钟。"""
        tick_time = time.monotonic() if now is None else now
        if self._ownership.timed_out(tick_time):
            self.halt_motion()
            self._leave_flight_auto_state()
            self._notify_ownership_changed()
        if self._last_motion_tick_time is None:
            self._last_motion_tick_time = tick_time
            return
        elapsed = tick_time - self._last_motion_tick_time
        self._last_motion_tick_time = tick_time

        if not self._node._is_active or not self._node._running:
            return
        is_auto = self._state.is_auto_running()
        is_manual = self._state.is_manual_running()
        if not (is_auto or is_manual):
            self.halt_motion()
            return

        with self._node._lock:
            source = self._motion_source
            if self._ordinary_commands_blocked_locked() or source == MotionSource.IDLE:
                return
            if not self._source_owned_locked(source):
                self._halt_motion_locked()
                return
            if source == MotionSource.AUTO and not is_auto:
                self._halt_motion_locked()
                return
            if source == MotionSource.FLIGHT and not is_auto:
                self._halt_motion_locked()
                return
            if source in (MotionSource.MANUAL, MotionSource.HOME) and not is_manual:
                self._halt_motion_locked()
                return

        mode_speed = speed_for_source(source, self._node._motion_params)
        all_reached = True
        for mid in self._node._motor_ids:
            with self._node._lock:
                if self._ordinary_commands_blocked_locked() or self._motion_source != source:
                    return
                current = self._node._current_targets[mid]
                desired = self._node._desired_targets[mid]
                if self._node._motor_protection_flags.get(mid, False):
                    if abs(desired - current) > self._node._target_reached_tolerance:
                        all_reached = False
                    continue
                low, high = self._node._limits[mid]
                try:
                    new_target = advance_target(
                        current,
                        desired,
                        mode_speed_rad_s=mode_speed,
                        motor_speed_limit_rad_s=self._node._current_speeds[mid],
                        elapsed_sec=elapsed,
                        motion_dt_max_sec=self._node._motion_dt_max,
                        max_position_step=self._node._max_step,
                        target_reached_tolerance_rad=self._node._target_reached_tolerance,
                        limit_min=low,
                        limit_max=high,
                    )
                except ValueError as exc:
                    self._node.get_logger().error(f"电机 ID{mid} 目标推进参数非法: {exc}")
                    self._halt_motion_locked()
                    return

            if new_target != current:
                if not self.write_command_target(mid, new_target):
                    # 部分批次失败后不再发送本周期剩余普通命令。
                    return

            with self._node._lock:
                if (
                    abs(self._node._desired_targets[mid] - self._node._current_targets[mid])
                    > self._node._target_reached_tolerance
                ):
                    all_reached = False

        with self._node._lock:
            if (
                source == MotionSource.HOME
                and self._motion_source == MotionSource.HOME
                and all_reached
            ):
                self._motion_source = MotionSource.IDLE
                self._node.get_logger().info("全部电机已到达零位，自动归零完成")

    def write_command_target(self, motor_id: int, target: float) -> bool:
        """发送位置命令，且只在驱动写入成功后提交软件命令状态。"""
        if not math.isfinite(target):
            self._node.get_logger().error(f"拒绝电机 ID{motor_id} 的非有限位置命令")
            return False
        low, high = self._node._limits[motor_id]
        command = clamp(target, low, high)
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                self._node.get_logger().error(
                    f"拒绝电机 ID{motor_id} 位置命令：安全或命令故障已锁存"
                )
                return False

        try:
            with self._node._driver_io_lock:
                # 等待 I/O 锁期间可能已由另一命令锁存故障；不得在停止批次间插入新命令。
                if self._ordinary_commands_blocked_unlocked():
                    self._node.get_logger().error(
                        f"拒绝电机 ID{motor_id} 位置命令：安全或命令故障已锁存"
                    )
                    return False
                if self._node._driver is None:
                    raise RuntimeError("电机驱动不可用")
                self._node._driver.write_sdo_float(
                    motor_id, SDO_TARGET_POS, command
                )
        except Exception as exc:
            with self._node._lock:
                self._node._command_failure_counts[motor_id] = (
                    self._node._command_failure_counts.get(motor_id, 0) + 1
                )
            self._node.get_logger().error(
                f"写入电机 ID{motor_id} 目标位置时发生异常: {exc}"
            )
            self._handle_command_failure(motor_id, "position", exc)
            return False

        committed_at = time.monotonic()
        with self._node._lock:
            # 该值不是反馈位置，也不是待发送值；它是最后成功写入的目标。
            self._node._current_targets[motor_id] = command
            self._node._last_target_change_time[motor_id] = committed_at
            self._node._command_failure_counts[motor_id] = 0
            if self._motion_source == MotionSource.IDLE:
                self._node._desired_targets[motor_id] = command
        return True

    def _set_desired_target_locked(self, motor_id: int, target: float) -> float:
        if motor_id not in self._node._limits:
            raise ValueError(f"未知电机 ID{motor_id}")
        if not math.isfinite(target):
            raise ValueError(f"电机 ID{motor_id} 的期望目标必须为有限值")
        low, high = self._node._limits[motor_id]
        clamped = clamp(target, low, high)
        self._node._desired_targets[motor_id] = clamped
        return clamped

    def _set_desired_targets_locked(self, targets: Dict[int, float]) -> Dict[int, float]:
        if set(targets) != set(self._node._motor_ids):
            raise ValueError("目标电机集合必须与 motor_ids 完全一致")
        if not all(math.isfinite(float(targets[mid])) for mid in self._node._motor_ids):
            raise ValueError("全部期望目标必须为有限值")
        return {
            mid: self._set_desired_target_locked(mid, float(targets[mid]))
            for mid in self._node._motor_ids
        }

    def set_manual_targets(self, targets: Dict[int, float]) -> Dict[int, float]:
        """原子设置 MANUAL 绝对期望目标，不访问硬件。"""
        if (
            not self._state.is_manual_running()
            or self._ownership.owner is not MotorCommandOwner.MANUAL
        ):
            raise ValueError("绝对期望目标只允许在 MANUAL 模式设置")
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                raise ValueError("安全或命令故障已锁存，拒绝 MANUAL 目标")
            if not self._state.is_manual_running():
                raise ValueError("设置目标期间已离开 MANUAL 模式")
            if self._ownership.owner is not MotorCommandOwner.MANUAL:
                raise ValueError("当前普通命令 owner 不允许 MANUAL 目标")
            clamped = self._set_desired_targets_locked(targets)
            self._manual_repeat_times.clear()
            self._motion_source = MotionSource.MANUAL
            return clamped

    def set_auto_targets(self, targets: Dict[int, float]) -> bool:
        """接受一帧新的 AUTO 姿态目标，不访问硬件。"""
        if (
            not self._state.is_auto_running()
            or self._ownership.owner is not MotorCommandOwner.LEGACY_AUTO
        ):
            return False
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                return False
            if not self._state.is_auto_running():
                return False
            if self._ownership.owner is not MotorCommandOwner.LEGACY_AUTO:
                return False
            self._set_desired_targets_locked(targets)
            self._motion_source = MotionSource.AUTO
            return True

    # ------------------------------------------------------------------
    # 手动输入、速度和快捷目标
    # ------------------------------------------------------------------

    def manual_step(
        self, motor_id: int, direction: float, *, now: Optional[float] = None
    ) -> bool:
        """把一个有限键盘字符转换为期望目标增量。"""
        if (
            not self._state.is_manual_running()
            or self._ownership.owner is not MotorCommandOwner.MANUAL
            or direction == 0.0
        ):
            return False
        event_time = time.monotonic() if now is None else now
        direction = 1.0 if direction > 0.0 else -1.0
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                return False
            if not self._state.is_manual_running():
                return False
            if self._ownership.owner is not MotorCommandOwner.MANUAL:
                return False
            if self._motion_source == MotionSource.HOME:
                self._sync_desired_to_current_locked()

            opposite_key = (motor_id, -direction)
            self._manual_repeat_times.pop(opposite_key, None)
            repeat_key = (motor_id, direction)
            previous = self._manual_repeat_times.get(repeat_key)
            event_dt = 0.0 if previous is None else event_time - previous
            is_repeat = (
                previous is not None
                and 0.0 <= event_dt <= self._node._manual_repeat_gap
            )
            increment = manual_event_increment(
                is_repeat=is_repeat,
                event_dt_sec=event_dt,
                manual_step_rad=self._node._manual_step_rad,
                manual_motion_speed_rad_s=self._node._manual_motion_speed,
                motor_speed_limit_rad_s=self._node._current_speeds[motor_id],
                manual_repeat_dt_max_sec=self._node._manual_repeat_dt_max,
                max_position_step=self._node._max_step,
            )
            self._set_desired_target_locked(
                motor_id,
                self._node._desired_targets[motor_id] + direction * increment,
            )
            self._manual_repeat_times[repeat_key] = event_time
            self._motion_source = MotionSource.MANUAL
            return True

    def clear_manual_repeat_state(self) -> None:
        with self._node._lock:
            self._manual_repeat_times.clear()

    def set_motor_speed(self, motor_id: int, speed: float) -> bool:
        """设置速度上限，且只在驱动写入成功后提交软件状态。"""
        if not math.isfinite(speed):
            self._node.get_logger().error(f"拒绝电机 ID{motor_id} 的非有限速度上限")
            return False
        command = clamp(
            speed, self._node._manual_speed_min, self._node._manual_speed_max
        )
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                self._node.get_logger().error(
                    f"拒绝电机 ID{motor_id} 速度命令：安全或命令故障已锁存"
                )
                return False
        try:
            with self._node._driver_io_lock:
                if self._ordinary_commands_blocked_unlocked():
                    self._node.get_logger().error(
                        f"拒绝电机 ID{motor_id} 速度命令：安全或命令故障已锁存"
                    )
                    return False
                if self._node._driver is None:
                    raise RuntimeError("电机驱动不可用")
                self._node._driver.write_sdo_float(
                    motor_id, SDO_TARGET_SPEED, command
                )
        except Exception as exc:
            with self._node._lock:
                self._node._command_failure_counts[motor_id] = (
                    self._node._command_failure_counts.get(motor_id, 0) + 1
                )
            self._node.get_logger().error(
                f"设置电机 ID{motor_id} 速度上限时发生异常: {exc}"
            )
            self._handle_command_failure(motor_id, "speed_limit", exc)
            return False
        with self._node._lock:
            self._node._current_speeds[motor_id] = command
            self._node._command_failure_counts[motor_id] = 0
        return True

    def change_motor_speed(self, motor_id: int, delta: float) -> bool:
        """调整选中电机的底层速度上限并说明其与模式速度的关系。"""
        with self._node._lock:
            prev = self._node._current_speeds[motor_id]
        if not self.set_motor_speed(motor_id, prev + delta):
            self._node.get_logger().error(
                f"电机速度上限修改失败: ID{motor_id} 仍保持 {prev:.2f} rad/s"
            )
            return False
        with self._node._lock:
            new_speed = self._node._current_speeds[motor_id]
            self._node._last_target_change_time[motor_id] = time.monotonic()
            if self._state.is_auto_running():
                source = MotionSource.AUTO
            elif self._motion_source == MotionSource.HOME:
                source = MotionSource.HOME
            else:
                source = MotionSource.MANUAL
            mode_speed = speed_for_source(source, self._node._motion_params)
            self._node.get_logger().info(
                f"电机速度上限: ID{motor_id} {prev:.2f} -> {new_speed:.2f} rad/s；"
                f"当前 {source.value} 模式速度={mode_speed:.2f} rad/s，"
                f"有效推进速度上限={min(new_speed, mode_speed):.2f} rad/s"
            )
        return True

    def _handle_command_failure(
        self, motor_id: int, command_type: str, exc: Exception
    ) -> None:
        """冻结普通推进、停止全部电机并锁定 ERROR，不自动恢复。"""
        if isinstance(exc, CyberGearTransportError):
            with self._node._lock:
                first_command_fault = not self._node._command_fault_active
                self._node._command_fault_active = True
                self._halt_motion_locked()
            if first_command_fault:
                self._node.get_logger().error(
                    f"电机命令 transport 故障: ID{motor_id}, "
                    f"type={command_type}, error={exc}"
                )
            event = getattr(exc, "event", None)
            if event is not None and hasattr(
                self._node, "_on_driver_transport_event"
            ):
                self._node._on_driver_transport_event(event)
                return
            # Unit-level/fallback drivers without the event channel retain the
            # established command-fault stop and ERROR behavior.
            self.stop_motors_for_fault_once(
                reason=f"transport_command_fault:{command_type}"
            )
            self._state.transition_to(
                ControllerState.ERROR,
                reason=TransitionReason.TRANSPORT_FAILURE,
                source=TransitionSource.DRIVER_TRANSPORT,
            )
            return

        with self._node._lock:
            if self._node._command_fault_active:
                return
            self._node._command_fault_active = True
            self._halt_motion_locked()
        self._node.get_logger().error(
            f"电机命令故障: ID{motor_id}, type={command_type}, error={exc}; "
            "已丢弃未完成运动并尝试停止全部电机"
        )
        self.stop_motors_for_fault_once(reason=f"command_fault:{command_type}")
        transition_reason = (
            TransitionReason.SPEED_COMMAND_WRITE_FAILURE
            if command_type == "speed_limit"
            else TransitionReason.POSITION_COMMAND_WRITE_FAILURE
        )
        result = self._state.transition_to(
            ControllerState.ERROR,
            reason=transition_reason,
            source=TransitionSource.MOTOR_MANAGER,
        )
        if result.outcome is TransitionOutcome.REJECTED:
            self._node.get_logger().error(
                "关键状态转换被拒绝：运行时命令故障后无法进入 ERROR"
            )

    def enter_transport_error(self, event: TransportEvent) -> bool:
        """Latch the first transport fault without waiting for driver I/O."""
        with self._node._lock:
            if getattr(self._node, "_transport_fault_active", False):
                return False
            self._node._transport_fault_active = True
            self._node._transport_fault_snapshot = event
            self._node._init_complete = False
            self._halt_motion_locked()

        self._node.get_logger().error(
            "电机 transport 故障已锁存；普通运动已丢弃，控制保持 ERROR: "
            f"backend={event.backend}, operation={event.operation}, "
            f"generation={event.connection_generation}, error={event.message}"
        )
        result = self._state.transition_to(
            ControllerState.ERROR,
            reason=TransitionReason.TRANSPORT_FAILURE,
            source=TransitionSource.DRIVER_TRANSPORT,
        )
        if result.outcome is TransitionOutcome.REJECTED:
            self._node.get_logger().error(
                "关键状态转换被拒绝：transport 故障已锁存但无法进入 ERROR"
            )
        return True

    def enter_safety_error(self, snapshot: MotorSafetyFaultSnapshot) -> bool:
        """Latch one feedback-safety fault and execute exactly one stop batch.

        The node state lock is released before any driver I/O.  Concurrent or
        repeated feedback faults retain the first immutable snapshot and do not
        issue another stop batch.
        """
        with self._node._lock:
            if getattr(self._node, "_motor_safety_fault_active", False):
                if snapshot.motor_id in self._node._motor_protection_flags:
                    self._node._motor_protection_flags[snapshot.motor_id] = True
                return False
            self._node._motor_safety_fault_active = True
            self._node._motor_safety_fault_snapshot = snapshot
            if snapshot.motor_id in self._node._motor_protection_flags:
                self._node._motor_protection_flags[snapshot.motor_id] = True
            self._halt_motion_locked()

        self._node.get_logger().error(
            "电机反馈安全故障已锁存；已丢弃普通运动并尝试停止全部电机: "
            f"ID{snapshot.motor_id}, reason={snapshot.reason.value}, "
            f"detail={snapshot.diagnostic_message}"
        )
        self.stop_motors_for_fault_once(
            reason=f"motor_safety:{snapshot.reason.value}"
        )
        transition_reason = self._transition_reason_for_safety(snapshot)
        result = self._state.transition_to(
            ControllerState.ERROR,
            reason=transition_reason,
            source=(
                TransitionSource.WATCHDOG
                if snapshot.reason is MotorHealthReason.FEEDBACK_TIMEOUT
                else TransitionSource.DRIVER_FEEDBACK
            ),
        )
        if result.outcome is TransitionOutcome.REJECTED:
            self._node.get_logger().error(
                "关键状态转换被拒绝：反馈安全故障已锁存且电机已停止，但无法进入 ERROR"
            )
        return True

    @staticmethod
    def _transition_reason_for_safety(
        snapshot: MotorSafetyFaultSnapshot,
    ) -> TransitionReason:
        mapping = {
            MotorHealthReason.MOTOR_FAULT_UNDERVOLTAGE: TransitionReason.MOTOR_FAULT_UNDERVOLTAGE,
            MotorHealthReason.MOTOR_FAULT_OVERCURRENT: TransitionReason.MOTOR_OVERCURRENT_FAULT,
            MotorHealthReason.MOTOR_FAULT_OVERTEMPERATURE: TransitionReason.MOTOR_OVERTEMPERATURE_FAULT,
            MotorHealthReason.MOTOR_FAULT_ENCODER: TransitionReason.MOTOR_FAULT_ENCODER,
            MotorHealthReason.MOTOR_FAULT_UNCALIBRATED: TransitionReason.MOTOR_FAULT_UNCALIBRATED,
            MotorHealthReason.MOTOR_FAULT_MULTIPLE: TransitionReason.MOTOR_FAULT_MULTIPLE,
            MotorHealthReason.CRITICAL_TEMPERATURE: TransitionReason.MOTOR_CRITICAL_TEMPERATURE,
            MotorHealthReason.FEEDBACK_TIMEOUT: TransitionReason.MOTOR_FEEDBACK_TIMEOUT,
            MotorHealthReason.INVALID_FEEDBACK: TransitionReason.MOTOR_INVALID_FEEDBACK,
        }
        return mapping.get(snapshot.reason, TransitionReason.MOTOR_FEEDBACK_FAULT)

    def _ordinary_commands_blocked_locked(self) -> bool:
        return bool(
            self._node._command_fault_active
            or getattr(self._node, "_motor_safety_fault_active", False)
            or getattr(self._node, "_transport_fault_active", False)
        )

    def _ordinary_commands_blocked_unlocked(self) -> bool:
        """Read latch booleans while holding the driver I/O lock, never state lock."""
        return bool(
            self._node._command_fault_active
            or getattr(self._node, "_motor_safety_fault_active", False)
            or getattr(self._node, "_transport_fault_active", False)
        )

    def stop_motors_best_effort(
        self,
        *,
        reason: str,
        motor_ids: Optional[Iterable[int]] = None,
    ) -> bool:
        """逐台尽力停止；每次只为单个驱动调用持有 I/O 锁。"""
        ids = list(self._node._motor_ids if motor_ids is None else motor_ids)
        all_stopped = True
        for mid in ids:
            try:
                with self._node._driver_io_lock:
                    if self._node._driver is None:
                        raise RuntimeError("电机驱动不可用")
                    self._node._driver.stop_motor(mid)
                self._node.get_logger().info(
                    f"电机 ID{mid} 停止完成 (reason={reason})"
                )
            except Exception as exc:
                all_stopped = False
                self._node.get_logger().error(
                    f"停止电机 ID{mid} 失败 (reason={reason}): {exc}"
                )
        return all_stopped

    def stop_motors_for_fault_once(self, *, reason: str) -> bool:
        """Claim and run the session's one main emergency/error stop batch."""
        with self._node._lock:
            if getattr(self._node, "_fault_stop_batch_claimed", False):
                return False
            self._node._fault_stop_batch_claimed = True
        self.stop_motors_best_effort(reason=reason)
        return True

    def reset_fault_stop_batch_after_recovery(self) -> None:
        """Permit a later independent e-stop only after successful normal recovery."""
        with self._node._lock:
            if not getattr(self._node, "_motor_safety_fault_active", False):
                self._node._fault_stop_batch_claimed = False

    def move_motor_to_90_deg(self, motor_id: int, positive: bool) -> bool:
        """设置选中电机的 +/-90° 期望目标，不直接写位置命令。"""
        if (
            not self._state.is_manual_running()
            or self._ownership.owner is not MotorCommandOwner.MANUAL
        ):
            self._node.get_logger().warn("90度快捷目标只允许在 MANUAL 模式使用")
            return False
        with self._node._lock:
            if self._ordinary_commands_blocked_locked():
                return False
            if self._motion_source == MotionSource.HOME:
                self._sync_desired_to_current_locked()
            self._clear_motor_repeat_locked(motor_id)
            clamped = self._set_desired_target_locked(
                motor_id, deg_to_rad(90.0 if positive else -90.0)
            )
            self._motion_source = MotionSource.MANUAL
        self._node.get_logger().info(
            f"设置期望目标: ID{motor_id} -> {math.degrees(clamped):.1f}° "
            f"({clamped:.3f} rad)"
        )
        return True

    # ------------------------------------------------------------------
    # HOME、模式切换和安全状态同步
    # ------------------------------------------------------------------

    def go_all_to_zero(self) -> bool:
        """设置 HOME 目标；AUTO 中会先显式切换为 MANUAL。"""
        if self._ordinary_commands_blocked_unlocked():
            self._node.get_logger().warn("安全或命令故障已锁存，拒绝 HOME")
            return False
        if self._ownership.owner not in (
            MotorCommandOwner.MANUAL,
            MotorCommandOwner.LEGACY_AUTO,
        ):
            self._node.get_logger().warn("当前普通命令 owner 不允许 HOME")
            return False
        if self._state.is_auto_running():
            result = self._state.transition_to(
                ControllerState.MANUAL_RUNNING,
                reason=TransitionReason.HOME_REQUEST,
                source=TransitionSource.MOTOR_MANAGER,
            )
            if result.outcome is not TransitionOutcome.CHANGED:
                self._node.get_logger().error(
                    "HOME 请求无法从 AUTO 切换到 MANUAL，已拒绝回零"
                )
                return False
        if not self._state.is_manual_running():
            self._node.get_logger().warn(
                f"当前状态 {self._state.state_name} 不允许自动归零"
            )
            return False
        with self._node._lock:
            self._manual_repeat_times.clear()
            for mid in self._node._motor_ids:
                self._set_desired_target_locked(mid, 0.0)
            self._motion_source = MotionSource.HOME
        self._node.get_logger().info(
            "自动归零已启动（由统一推进器按 HOME 速度回到零位）"
        )
        return True

    def stop_auto_zero(self) -> None:
        """兼容旧调用名：取消 HOME 并保持最近已发送位置。"""
        with self._node._lock:
            if self._motion_source == MotionSource.HOME:
                self._sync_desired_to_current_locked()
                self._motion_source = MotionSource.IDLE

    def on_control_state_changed(self, new_state: ControllerState) -> None:
        """模式切换时丢弃旧目标；AUTO 等待切换后的新 IMU 帧。"""
        with self._node._lock:
            self._manual_repeat_times.clear()
            self._sync_desired_to_current_locked()
            self._motion_source = MotionSource.IDLE
            if new_state in (
                ControllerState.EMERGENCY_STOP,
                ControllerState.ERROR,
                ControllerState.SHUTTING_DOWN,
            ):
                self._ownership.release_to_none()
            elif not self._flight_commit_in_progress:
                if new_state is ControllerState.MANUAL_RUNNING:
                    if self._ownership.owner in (
                        MotorCommandOwner.FLIGHT_RESERVED,
                        MotorCommandOwner.FLIGHT_CONTROL,
                    ):
                        self._ownership.release_to_none()
                        transition = self._state.last_transition
                        if (
                            transition is not None
                            and transition.reason
                            in (
                                TransitionReason.USER_MODE_TOGGLE,
                                TransitionReason.HOME_REQUEST,
                                TransitionReason.EXPLICIT_ESTOP_RECOVERY,
                            )
                        ):
                            self._ownership.claim_legacy_for_state(auto=False)
                    else:
                        self._ownership.claim_legacy_for_state(auto=False)
                elif new_state is ControllerState.AUTO_RUNNING:
                    self._ownership.claim_legacy_for_state(auto=True)
        self._notify_ownership_changed()

    def halt_motion(self) -> None:
        """立即阻止后续普通位置推进，不延迟急停。"""
        with self._node._lock:
            self._halt_motion_locked()

    def _halt_motion_locked(self) -> None:
        self._manual_repeat_times.clear()
        self._sync_desired_to_current_locked()
        self._motion_source = MotionSource.IDLE

    def _sync_desired_to_current_locked(self) -> None:
        self._node._desired_targets = dict(self._node._current_targets)

    def _source_owned_locked(self, source: MotionSource) -> bool:
        expected = {
            MotionSource.MANUAL: MotorCommandOwner.MANUAL,
            MotionSource.HOME: MotorCommandOwner.MANUAL,
            MotionSource.AUTO: MotorCommandOwner.LEGACY_AUTO,
            MotionSource.FLIGHT: MotorCommandOwner.FLIGHT_CONTROL,
        }.get(source)
        return expected is not None and self._ownership.owner is expected

    def _flight_safe(self, *, allow_reserved: bool = False) -> bool:
        if not self._node._is_active or not self._node._running:
            return False
        if self._ordinary_commands_blocked_unlocked():
            return False
        if allow_reserved:
            return self._state.is_manual_running() or self._state.is_auto_running()
        return self._state.is_manual_running()

    def prepare_flight_ownership(
        self, authority_epoch: int, generation: int, *, now: float
    ) -> OwnershipResult:
        safe = self._flight_safe()
        result = self._ownership.prepare(
            authority_epoch, generation, now=now, safe=safe
        )
        if result.success:
            # Quiesce only the request that actually acquired (or already owns)
            # the reservation; stale requests must not disturb a legacy owner.
            self.halt_motion()
        self._notify_ownership_changed()
        return result

    def commit_flight_ownership(
        self, authority_epoch: int, generation: int, *, now: float
    ) -> OwnershipResult:
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            return OwnershipResult(
                False, "invalid_monotonic_time", authority_epoch, generation
            )
        token_matches = (
            self._ownership.authority_epoch,
            self._ownership.generation,
        ) == (authority_epoch, generation)
        if (
            self._ownership.owner is MotorCommandOwner.FLIGHT_CONTROL
            and token_matches
        ):
            return self._ownership.commit(
                authority_epoch, generation, now=now, safe=True
            )
        if not token_matches or self._ownership.owner is not MotorCommandOwner.FLIGHT_RESERVED:
            return self._ownership.commit(
                authority_epoch, generation, now=now, safe=False
            )
        safe = self._flight_safe()
        if safe and self._state.is_manual_running():
            self._flight_commit_in_progress = True
            try:
                transition = self._state.transition_to(
                    ControllerState.AUTO_RUNNING,
                    reason=TransitionReason.FLIGHT_OWNERSHIP_COMMIT,
                    source=TransitionSource.SERVICE,
                )
            finally:
                self._flight_commit_in_progress = False
            safe = transition.outcome in (
                TransitionOutcome.CHANGED,
                TransitionOutcome.NO_CHANGE,
            ) and self._state.is_auto_running()
        result = self._ownership.commit(
            authority_epoch, generation, now=now, safe=safe
        )
        self._notify_ownership_changed()
        return result

    def revoke_flight_ownership(
        self, authority_epoch: int, generation: int
    ) -> OwnershipResult:
        token_matches = (
            self._ownership.authority_epoch,
            self._ownership.generation,
        ) == (authority_epoch, generation)
        if token_matches:
            self.halt_motion()
            self._leave_flight_auto_state()
        result = self._ownership.revoke(authority_epoch, generation)
        self._notify_ownership_changed()
        return result

    def fail_closed_flight(self, reason: str) -> None:
        if self._ownership.owner not in (
            MotorCommandOwner.FLIGHT_RESERVED,
            MotorCommandOwner.FLIGHT_CONTROL,
        ):
            return
        self._node.get_logger().error(
            f"Flight motor ownership fail-closed: {reason}"
        )
        self.halt_motion()
        self._ownership.release_to_none()
        self._leave_flight_auto_state()
        self._notify_ownership_changed()

    def _leave_flight_auto_state(self) -> None:
        if not self._state.is_auto_running():
            return
        self._flight_commit_in_progress = True
        try:
            self._state.transition_to(
                ControllerState.MANUAL_RUNNING,
                reason=TransitionReason.FLIGHT_OWNERSHIP_REVOKE,
                source=TransitionSource.SERVICE,
            )
        finally:
            self._flight_commit_in_progress = False

    def set_flight_targets(
        self,
        authority_epoch: int,
        generation: int,
        command_sequence: int,
        targets_by_name: Dict[str, float],
        *,
        now: float,
    ) -> OwnershipResult:
        name_to_id = {
            cfg.name: cfg.motor_id
            for cfg in getattr(self._node, "_motor_configs", ())
        }
        if set(targets_by_name) != set(name_to_id):
            return OwnershipResult(False, "invalid_motor_frame", authority_epoch, generation)
        if not all(math.isfinite(float(value)) for value in targets_by_name.values()):
            return OwnershipResult(False, "invalid_motor_frame", authority_epoch, generation)
        if (
            self._ownership.owner is not MotorCommandOwner.FLIGHT_CONTROL
            or not self._state.is_auto_running()
            or self._ordinary_commands_blocked_unlocked()
        ):
            return OwnershipResult(False, "flight_command_not_allowed", authority_epoch, generation)
        targets = {
            name_to_id[name]: float(targets_by_name[name])
            for name in name_to_id
        }
        with self._node._lock:
            if (
                not self._state.is_auto_running()
                or self._ordinary_commands_blocked_locked()
                or self._ownership.owner is not MotorCommandOwner.FLIGHT_CONTROL
            ):
                return OwnershipResult(False, "flight_command_not_allowed", authority_epoch, generation)
            accepted = self._ownership.accept_command(
                authority_epoch, generation, command_sequence, now=now
            )
            if not accepted.success:
                return accepted
            self._set_desired_targets_locked(targets)
            self._motion_source = MotionSource.FLIGHT
        self._notify_ownership_changed()
        return accepted

    def accept_flight_safe_stop(
        self,
        authority_epoch: int,
        generation: int,
        command_sequence: int,
        *,
        now: float,
    ) -> OwnershipResult:
        accepted = self._ownership.accept_safe_stop(
            authority_epoch, generation, command_sequence, now=now
        )
        if not accepted.success:
            return accepted
        self.halt_motion()
        return self.revoke_flight_ownership(authority_epoch, generation)

    def _notify_ownership_changed(self) -> None:
        callback = getattr(self._node, "_publish_motor_ownership_state", None)
        if callable(callback):
            callback()

    def _clear_motor_repeat_locked(self, motor_id: int) -> None:
        for key in list(self._manual_repeat_times):
            if key[0] == motor_id:
                self._manual_repeat_times.pop(key, None)

    # ------------------------------------------------------------------
    # 机械零点与急停恢复（特殊直接硬件流程）
    # ------------------------------------------------------------------

    def set_all_motor_zero_reference(self) -> bool:
        """将全部电机当前位置设为机械零点，返回是否全部成功。"""
        if (
            not self._state.is_manual_running()
            or self._ownership.owner is not MotorCommandOwner.MANUAL
        ):
            self._node.get_logger().warn(
                "机械零点只允许显式 MANUAL owner 使用"
            )
            return False
        if self._zero_reference_fault_latched():
            return False
        self.halt_motion()
        success = True
        success = self.stop_motors_best_effort(reason="set_zero") and success
        self._node._sleep(0.2)
        if self._zero_reference_fault_latched():
            return False
        for mid in self._node._motor_ids:
            try:
                with self._node._driver_io_lock:
                    if self._zero_reference_fault_latched():
                        return False
                    self._node._driver.set_zero(mid)
                self._node._sleep(0.05)
                if self._zero_reference_fault_latched():
                    return False
            except Exception as exc:
                success = False
                self._node.get_logger().error(f"设置电机 ID{mid} 零点时发生异常: {exc}")
        self._node._sleep(0.3)
        if self._zero_reference_fault_latched():
            return False
        for mid in self._node._motor_ids:
            try:
                with self._node._driver_io_lock:
                    if self._zero_reference_fault_latched():
                        return False
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                with self._node._driver_io_lock:
                    if self._zero_reference_fault_latched():
                        return False
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                with self._node._driver_io_lock:
                    if self._zero_reference_fault_latched():
                        return False
                    self._node._driver.enter_control_mode(mid)
                with self._node._lock:
                    self._node._current_targets[mid] = 0.0
                    self._node._desired_targets[mid] = 0.0
                    self._node._last_target_change_time[mid] = time.monotonic()
                self._node._sleep(0.03)
                if self._zero_reference_fault_latched():
                    return False
            except Exception as exc:
                success = False
                self._node.get_logger().error(
                    f"恢复电机 ID{mid} 运控模式时发生异常: {exc}"
                )
        if self._zero_reference_fault_latched():
            return False
        if success:
            self._node.get_logger().info("全部电机机械零点已设置")
        else:
            self.stop_motors_best_effort(reason="set_zero_failed")
            result = self._state.transition_to(
                ControllerState.ERROR,
                reason=TransitionReason.MECHANICAL_ZERO_FAILURE,
                source=TransitionSource.MOTOR_MANAGER,
            )
            if result.outcome is TransitionOutcome.REJECTED:
                self._node.get_logger().error(
                    "关键状态转换被拒绝：机械零点失败后无法进入 ERROR"
                )
        return success

    def _zero_reference_fault_latched(self) -> bool:
        """Abort the direct zeroing flow once any session fault is latched."""
        if not self._ordinary_commands_blocked_unlocked():
            return False
        self._node.get_logger().error(
            "设置机械零点流程已中止：安全或命令故障已锁存"
        )
        return True

    def hold_current_targets_and_recover(self) -> bool:
        """从急停恢复运控模式，保持最近发送的软件位置。"""
        self.halt_motion()
        recovered = True
        recovered_ids = []
        with self._node._lock:
            targets = dict(self._node._current_targets)
        for mid in self._node._motor_ids:
            try:
                with self._node._driver_io_lock:
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                with self._node._driver_io_lock:
                    self._node._driver.write_sdo_float(
                        mid, SDO_TARGET_POS, targets[mid]
                    )
                with self._node._driver_io_lock:
                    self._node._driver.enter_control_mode(mid)
                recovered_ids.append(mid)
                self._node._sleep(0.03)
            except Exception as exc:
                recovered = False
                self._node.get_logger().error(
                    f"恢复电机 ID{mid} 运控模式时发生异常: {exc}"
                )
                break
        if recovered:
            self._node.get_logger().info("全部电机已恢复运控模式（保持当前位置）")
        else:
            self._node.get_logger().error(
                f"急停恢复失败，已恢复电机={recovered_ids}；正在重新停止全部电机"
            )
            self.stop_motors_best_effort(reason="recovery_failed")
            with self._node._lock:
                self._halt_motion_locked()
        return recovered

    # ------------------------------------------------------------------
    # 状态汇总
    # ------------------------------------------------------------------

    def publish_state_summary(self) -> None:
        """发布当前状态汇总到日志。"""
        state_name = self._state.state_name
        transition = self._state.last_transition
        driver = getattr(self._node, "_driver", None)
        backend_name = getattr(driver, "backend_name", "none")
        try:
            transport_connected = bool(driver is not None and driver.is_connected)
        except Exception:
            transport_connected = False
        recovery = getattr(self._node, "_transport_recovery", None)
        recovery_snapshot = recovery.snapshot() if recovery is not None else None
        with self._node._lock:
            safety_snapshot = getattr(
                self._node, "_motor_safety_fault_snapshot", None
            )
            transport_snapshot = getattr(
                self._node, "_transport_fault_snapshot", None
            )
            summary_lines = [
                "===== 节点状态汇总 =====",
                f"状态: {state_name}，内部运动源: {self._motion_source.value}",
                f"IMU Roll: {math.degrees(self._node._latest_roll):.2f}°, "
                f"Pitch: {math.degrees(self._node._latest_pitch):.2f}°",
                f"选中电机: ID{self._node._selected_motor_id}",
                "反馈超时保护: "
                + (
                    f"启用 ({self._node._motor_feedback_timeout_sec:.3f}s)"
                    if getattr(self._node, "_motor_feedback_timeout_sec", 0.0) > 0.0
                    else "禁用（仅记录本地反馈年龄）"
                ),
                "反馈安全故障锁存: "
                + ("是" if getattr(self._node, "_motor_safety_fault_active", False) else "否"),
                f"Transport backend: {backend_name}，connected={transport_connected}",
                "Transport 故障锁存: "
                + ("是" if getattr(self._node, "_transport_fault_active", False) else "否"),
            ]
        if recovery_snapshot is not None:
            summary_lines.append(
                "Transport recovery: "
                f"state={recovery_snapshot.state.value}, "
                f"attempt={recovery_snapshot.attempt}/{recovery_snapshot.max_attempts}, "
                f"worker_alive={recovery_snapshot.worker_alive}"
            )
        if transport_snapshot is not None:
            summary_lines.append(
                "首次 transport 故障: "
                f"backend={transport_snapshot.backend}, "
                f"operation={transport_snapshot.operation}, "
                f"generation={transport_snapshot.connection_generation}, "
                f"monotonic={transport_snapshot.monotonic_timestamp:.6f}, "
                f"message={transport_snapshot.message}"
            )
        if safety_snapshot is not None:
            summary_lines.append(
                "首次反馈安全故障: "
                f"reason={safety_snapshot.reason.value}, ID{safety_snapshot.motor_id}, "
                f"monotonic={safety_snapshot.first_triggered_at:.6f}, "
                f"flags=0x{safety_snapshot.fault_flags:02X}"
            )
        if transition is not None:
            summary_lines.append(
                "最近状态转换: "
                f"#{transition.sequence} {transition.old_state.name} -> "
                f"{transition.new_state.name}, reason={transition.reason.value}, "
                f"source={transition.source.value}, "
                f"monotonic={transition.monotonic_timestamp:.6f}"
            )
        summary_lines.append("各电机当前状态:")
        freshness = {}
        safety = getattr(self._node, "_safety", None)
        if safety is not None:
            try:
                freshness = {
                    item.motor_id: item
                    for item in safety.health_core.freshness_snapshot(
                        now=time.monotonic()
                    )
                }
            except Exception as exc:
                self._node.get_logger().error(f"读取反馈年龄失败: {exc}")
        for cfg in self._node._motor_configs:
            mid = cfg.motor_id
            target = self._node._current_targets.get(mid, 0.0)
            desired = self._node._desired_targets.get(mid, target)
            speed = self._node._current_speeds.get(mid, 0.0)
            protected = self._node._motor_protection_flags.get(mid, False)
            fb = self._node._motor_feedback.get(mid)
            fresh = freshness.get(mid)
            age_text = (
                "age=无本次激活反馈"
                if fresh is None or fresh.age_sec is None
                else f"age={fresh.age_sec:.3f}s"
            )
            temperature_warning = getattr(
                self._node, "_motor_temperature_warning_flags", {}
            ).get(mid, False)
            prefix = (
                f"  {cfg.name}(ID{mid}): command={target:.3f} rad, "
                f"desired={desired:.3f} rad, speed_limit={speed:.2f}"
            )
            if fb is not None:
                summary_lines.append(
                    f"{prefix}, actual={fb.position_rad:.3f} rad, "
                    f"torque={fb.torque_nm:.3f} Nm, temp={fb.temperature:.1f}°C, "
                    f"模式={fb.mode_name}, fault=0x{fb.fault_flags:02X}, {age_text}"
                    + (" [保护]" if protected else "")
                    + (" [温度警告]" if temperature_warning else "")
                    + (f" [故障:{fb.fault_names}]" if fb.has_fault else "")
                )
            else:
                summary_lines.append(
                    f"{prefix} (无反馈数据, {age_text})"
                    + (" [保护]" if protected else "")
                )

        for line in summary_lines:
            self._node.get_logger().info(line)
