"""电机管理：连接初始化、统一目标推进、归零和手动控制。"""

import math
import time
from typing import Dict, Iterable, List, Optional, Tuple

from std_msgs.msg import String

from .controller_state import ControllerState
from .cybergear_driver import SDO_RUN_MODE, SDO_TARGET_POS, SDO_TARGET_SPEED
from .motor_motion import (
    MotionSource,
    advance_target,
    manual_event_increment,
    speed_for_source,
)


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

    @property
    def motion_source(self) -> MotionSource:
        return self._motion_source

    @property
    def motion_timer(self):
        return self._motion_timer

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
            self._state.transition_to(ControllerState.ERROR)
            self._current_init_stage = "failed:connect"
            return False

        self._node.get_logger().info("电机连接成功，正在初始化运控模式...")
        max_init_retry = 3
        for mid in self._node._motor_ids:
            for attempt in range(max_init_retry):
                try:
                    self._mark_init_touched(mid)
                    self._current_init_stage = f"ID{mid}:run_mode"
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:target_speed"
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_float(
                            mid, SDO_TARGET_SPEED, self._node._default_speed
                        )
                    with self._node._lock:
                        self._node._current_speeds[mid] = self._node._default_speed
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:target_position"
                    with self._node._driver_io_lock:
                        self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                    with self._node._lock:
                        # _current_targets 始终表示最近一次成功写入驱动的位置目标。
                        self._node._current_targets[mid] = 0.0
                        self._node._desired_targets[mid] = 0.0
                        self._node._last_target_change_time[mid] = time.monotonic()
                    self._node._sleep(0.08)

                    self._current_init_stage = f"ID{mid}:enter_control_mode"
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
                        self._state.transition_to(ControllerState.ERROR)
                        self._current_init_stage = f"failed:{self._current_init_stage}"
                        return False

        with self._node._lock:
            self._node._init_complete = True
            self._node._command_fault_active = False
        self._state.transition_to(ControllerState.MANUAL_RUNNING)
        self._current_init_stage = "complete"
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
            if self._node._command_fault_active or source == MotionSource.IDLE:
                return
            if source == MotionSource.AUTO and not is_auto:
                self._halt_motion_locked()
                return
            if source in (MotionSource.MANUAL, MotionSource.HOME) and not is_manual:
                self._halt_motion_locked()
                return

        mode_speed = speed_for_source(source, self._node._motion_params)
        all_reached = True
        for mid in self._node._motor_ids:
            with self._node._lock:
                if self._node._command_fault_active or self._motion_source != source:
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
            if self._node._command_fault_active:
                self._node.get_logger().error(
                    f"拒绝电机 ID{motor_id} 位置命令：命令故障已锁存"
                )
                return False

        try:
            with self._node._driver_io_lock:
                # 等待 I/O 锁期间可能已由另一命令锁存故障；不得在停止批次间插入新命令。
                if self._node._command_fault_active:
                    self._node.get_logger().error(
                        f"拒绝电机 ID{motor_id} 位置命令：命令故障已锁存"
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
        if not self._state.is_manual_running():
            raise ValueError("绝对期望目标只允许在 MANUAL 模式设置")
        with self._node._lock:
            if not self._state.is_manual_running():
                raise ValueError("设置目标期间已离开 MANUAL 模式")
            clamped = self._set_desired_targets_locked(targets)
            self._manual_repeat_times.clear()
            self._motion_source = MotionSource.MANUAL
            return clamped

    def set_auto_targets(self, targets: Dict[int, float]) -> bool:
        """接受一帧新的 AUTO 姿态目标，不访问硬件。"""
        if not self._state.is_auto_running():
            return False
        with self._node._lock:
            if not self._state.is_auto_running():
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
        if not self._state.is_manual_running() or direction == 0.0:
            return False
        event_time = time.monotonic() if now is None else now
        direction = 1.0 if direction > 0.0 else -1.0
        with self._node._lock:
            if not self._state.is_manual_running():
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
            if self._node._command_fault_active:
                self._node.get_logger().error(
                    f"拒绝电机 ID{motor_id} 速度命令：命令故障已锁存"
                )
                return False
        try:
            with self._node._driver_io_lock:
                if self._node._command_fault_active:
                    self._node.get_logger().error(
                        f"拒绝电机 ID{motor_id} 速度命令：命令故障已锁存"
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
        with self._node._lock:
            if self._node._command_fault_active:
                return
            self._node._command_fault_active = True
            self._halt_motion_locked()
        self._node.get_logger().error(
            f"电机命令故障: ID{motor_id}, type={command_type}, error={exc}; "
            "已丢弃未完成运动并尝试停止全部电机"
        )
        self.stop_motors_best_effort(reason=f"command_fault:{command_type}")
        self._state.transition_to(ControllerState.ERROR)

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

    def move_motor_to_90_deg(self, motor_id: int, positive: bool) -> bool:
        """设置选中电机的 +/-90° 期望目标，不直接写位置命令。"""
        if not self._state.is_manual_running():
            self._node.get_logger().warn("90度快捷目标只允许在 MANUAL 模式使用")
            return False
        with self._node._lock:
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
        if self._state.is_auto_running():
            self._state.transition_to(ControllerState.MANUAL_RUNNING)
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

    def _clear_motor_repeat_locked(self, motor_id: int) -> None:
        for key in list(self._manual_repeat_times):
            if key[0] == motor_id:
                self._manual_repeat_times.pop(key, None)

    # ------------------------------------------------------------------
    # 机械零点与急停恢复（特殊直接硬件流程）
    # ------------------------------------------------------------------

    def set_all_motor_zero_reference(self) -> bool:
        """将全部电机当前位置设为机械零点，返回是否全部成功。"""
        self.halt_motion()
        success = True
        success = self.stop_motors_best_effort(reason="set_zero") and success
        self._node._sleep(0.2)
        for mid in self._node._motor_ids:
            try:
                with self._node._driver_io_lock:
                    self._node._driver.set_zero(mid)
                self._node._sleep(0.05)
            except Exception as exc:
                success = False
                self._node.get_logger().error(f"设置电机 ID{mid} 零点时发生异常: {exc}")
        self._node._sleep(0.3)
        for mid in self._node._motor_ids:
            try:
                with self._node._driver_io_lock:
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                with self._node._driver_io_lock:
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                with self._node._driver_io_lock:
                    self._node._driver.enter_control_mode(mid)
                with self._node._lock:
                    self._node._current_targets[mid] = 0.0
                    self._node._desired_targets[mid] = 0.0
                    self._node._last_target_change_time[mid] = time.monotonic()
                self._node._sleep(0.03)
            except Exception as exc:
                success = False
                self._node.get_logger().error(
                    f"恢复电机 ID{mid} 运控模式时发生异常: {exc}"
                )
        if success:
            self._node.get_logger().info("全部电机机械零点已设置")
        else:
            self.stop_motors_best_effort(reason="set_zero_failed")
            self._state.transition_to(ControllerState.ERROR)
        return success

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
        with self._node._lock:
            summary_lines = [
                "===== 节点状态汇总 =====",
                f"状态: {state_name}，内部运动源: {self._motion_source.value}",
                f"IMU Roll: {math.degrees(self._node._latest_roll):.2f}°, "
                f"Pitch: {math.degrees(self._node._latest_pitch):.2f}°",
                f"选中电机: ID{self._node._selected_motor_id}",
            ]
        summary_lines.append("各电机当前状态:")
        for cfg in self._node._motor_configs:
            mid = cfg.motor_id
            target = self._node._current_targets.get(mid, 0.0)
            desired = self._node._desired_targets.get(mid, target)
            speed = self._node._current_speeds.get(mid, 0.0)
            protected = self._node._motor_protection_flags.get(mid, False)
            fb = self._node._motor_feedback.get(mid)
            prefix = (
                f"  {cfg.name}(ID{mid}): command={target:.3f} rad, "
                f"desired={desired:.3f} rad, speed_limit={speed:.2f}"
            )
            if fb is not None:
                summary_lines.append(
                    f"{prefix}, actual={fb.position_rad:.3f} rad, "
                    f"torque={fb.torque_nm:.3f} Nm, temp={fb.temperature:.1f}°C, "
                    f"模式={fb.mode_name}"
                    + (" [保护]" if protected else "")
                    + (f" [故障:{fb.fault_names}]" if fb.has_fault else "")
                )
            else:
                summary_lines.append(
                    f"{prefix} (无反馈数据)" + (" [保护]" if protected else "")
                )

        for line in summary_lines:
            self._node.get_logger().info(line)
