"""电机管理：连接初始化、目标写入、自动归零、手动控制。"""

import math
import time
from typing import Dict

from .controller_state import ControllerState
from .cybergear_driver import SDO_RUN_MODE, SDO_TARGET_POS, SDO_TARGET_SPEED


def clamp(value: float, low: float, high: float) -> float:
    """将值约束在 [low, high] 区间内。"""
    return max(low, min(high, value))


def deg_to_rad(deg: float) -> float:
    """角度（度）转弧度。"""
    return deg * math.pi / 180.0


class MotorManager:
    """电机管理模块。

    职责：
      - 电机连接与运控模式初始化
      - 目标位置写入（带软限位、步长限制、保护检查）
      - 速度设置与调整
      - 自动归零过程
      - 急停恢复
      - 机械零点设置
      - 状态汇总发布

    参数：
        node: ROS2 LifecycleNode 实例。
        state_mgr: StateManager 实例。
    """

    def __init__(self, node, state_mgr):
        self._node = node
        self._state = state_mgr
        self._auto_zero_active = False
        self._auto_zero_timer = None

    # ------------------------------------------------------------------
    # 电机连接与初始化
    # ------------------------------------------------------------------

    def connect_and_init_motors(self) -> bool:
        """连接电机并初始化运控模式。

        返回：
            True 表示成功，False 表示失败。
        """
        self._node.get_logger().info("正在连接电机...")
        connected = self._node._driver.connect_with_retry(
            max_attempts=5,
            initial_delay=1.0,
            on_status=self._on_motor_connect_status,
        )
        if not connected:
            self._node.get_logger().error(
                "电机连接失败（已重试 5 次）！请检查：\n"
                "  1. CAN HAT+ 是否已完成开机初始化\n"
                "  2. 电机电源是否已接通\n"
                "  3. CAN 总线接线是否正确"
            )
            self._state.transition_to(ControllerState.ERROR)
            return False

        self._node.get_logger().info("电机连接成功，正在初始化运控模式...")
        MAX_INIT_RETRY = 3
        for mid in self._node._motor_ids:
            for attempt in range(MAX_INIT_RETRY):
                try:
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                    time.sleep(0.08)
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_SPEED, self._node._default_speed)
                    self._node._current_speeds[mid] = self._node._default_speed
                    time.sleep(0.08)
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                    time.sleep(0.08)
                    self._node._driver.enter_control_mode(mid)
                    time.sleep(0.08)
                    self._node.get_logger().info(f"电机 ID{mid} 初始化完成")
                    break
                except Exception as exc:
                    err_msg = str(exc)
                    if attempt < MAX_INIT_RETRY - 1:
                        self._node.get_logger().warn(
                            f"初始化电机 ID{mid} 失败 (尝试 {attempt + 1}/{MAX_INIT_RETRY}): {err_msg}"
                        )
                        time.sleep(0.3)
                    else:
                        self._node.get_logger().error(
                            f"初始化电机 ID{mid} 失败（已重试 {MAX_INIT_RETRY} 次）: {err_msg}"
                        )
                        self._state.transition_to(ControllerState.ERROR)
                        return False

        self._node._init_complete = True
        self._state.transition_to(ControllerState.MANUAL_RUNNING)
        return True

    def _on_motor_connect_status(self, status: str) -> None:
        """接收电机连接状态变化并发布到 /motor/status 话题。"""
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
    # 电机目标写入
    # ------------------------------------------------------------------

    def write_target(self, motor_id: int, target: float) -> None:
        """向指定电机写入目标位置（带软限位和保护检查）。"""
        if self._node._motor_protection_flags.get(motor_id, False):
            return

        low, high = self._node._limits[motor_id]
        target = clamp(target, low, high)
        prev = self._node._current_targets[motor_id]
        requested_delta = target - prev
        speed_limited_step = self._node._current_speeds[motor_id] * self._node._command_interval
        step_cap = min(self._node._max_step, speed_limited_step)
        delta = clamp(requested_delta, -step_cap, step_cap)
        new_target = clamp(prev + delta, low, high)
        self._node._current_targets[motor_id] = new_target
        self._node._last_target_change_time[motor_id] = time.monotonic()

        try:
            self._node._driver.write_sdo_float(motor_id, SDO_TARGET_POS, new_target)
        except Exception as exc:
            self._node.get_logger().error(f"写入电机 ID{motor_id} 目标位置时发生异常: {exc}")

    def set_motor_speed(self, motor_id: int, speed: float) -> None:
        """设置指定电机的目标速度（带限幅）。"""
        speed = clamp(speed, self._node._manual_speed_min, self._node._manual_speed_max)
        self._node._current_speeds[motor_id] = speed
        try:
            self._node._driver.write_sdo_float(motor_id, SDO_TARGET_SPEED, speed)
        except Exception as exc:
            self._node.get_logger().error(f"设置电机 ID{motor_id} 速度时发生异常: {exc}")

    def change_motor_speed(self, motor_id: int, delta: float) -> None:
        """调整指定电机的目标速度（增量式）。"""
        with self._node._lock:
            prev = self._node._current_speeds[motor_id]
            self.set_motor_speed(motor_id, self._node._current_speeds[motor_id] + delta)
            new_speed = self._node._current_speeds[motor_id]
            self._node._last_target_change_time[motor_id] = time.monotonic()
            step_per_cycle = new_speed * self._node._command_interval
            self._node.get_logger().info(
                f"调速: ID{motor_id} {prev:.2f} -> {new_speed:.2f} rad/s "
                f"(AUTO 模式每步最多 {math.degrees(step_per_cycle):.1f}°)"
            )

    def move_motor_to_90_deg(self, motor_id: int, positive: bool) -> None:
        """一键将指定电机目标位设置到 +/-90 度。"""
        with self._node._lock:
            target = deg_to_rad(90.0 if positive else -90.0)
            low, high = self._node._limits[motor_id]
            clamped = clamp(target, low, high)
            self._node._current_targets[motor_id] = clamped
            self._node._last_target_change_time[motor_id] = time.monotonic()
            try:
                self._node._driver.write_sdo_float(motor_id, SDO_TARGET_POS, clamped)
            except Exception as exc:
                self._node.get_logger().error(f"90度快捷位写入电机 ID{motor_id} 时发生异常: {exc}")
                return
            self._node.get_logger().info(
                f"90度快捷位: ID{motor_id} -> {math.degrees(clamped):.1f}° ({clamped:.3f} rad)"
            )

    def apply_targets(self, targets: Dict[int, float]) -> None:
        """批量写入所有电机的目标位置。"""
        for mid in self._node._motor_ids:
            self.write_target(mid, targets[mid])

    def manual_step(self, motor_id: int, direction: float) -> None:
        """手动步进指定电机（方向 * 步长）。"""
        with self._node._lock:
            self.write_target(
                motor_id, self._node._current_targets[motor_id] + direction * self._node._manual_step_rad
            )

    # ------------------------------------------------------------------
    # 零点与复位
    # ------------------------------------------------------------------

    def set_all_motor_zero_reference(self) -> None:
        """将全部电机的当前位置设为机械零点。"""
        with self._node._lock:
            for mid in self._node._motor_ids:
                try:
                    self._node._driver.stop_motor(mid)
                except Exception as exc:
                    self._node.get_logger().error(f"停止电机 ID{mid} 以设零点时发生异常: {exc}")
            time.sleep(0.2)
            for mid in self._node._motor_ids:
                try:
                    self._node._driver.set_zero(mid)
                    time.sleep(0.05)
                except Exception as exc:
                    self._node.get_logger().error(f"设置电机 ID{mid} 零点时发生异常: {exc}")
            time.sleep(0.3)
            for mid in self._node._motor_ids:
                try:
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, 0.0)
                    self._node._driver.enter_control_mode(mid)
                    self._node._current_targets[mid] = 0.0
                    self._node._last_target_change_time[mid] = time.monotonic()
                    time.sleep(0.03)
                except Exception as exc:
                    self._node.get_logger().error(f"恢复电机 ID{mid} 运控模式时发生异常: {exc}")
        self._node.get_logger().info("全部电机机械零点已设置")

    def go_all_to_zero(self) -> None:
        """启动自动归零过程。"""
        self.stop_auto_zero()
        self._auto_zero_active = True
        self._auto_zero_timer = self._node.create_timer(
            self._node._command_interval, self._auto_zero_step
        )
        self._node.get_logger().info("自动归零已启动（全部电机正在持续回到零位，到达后自动停止）")

    def _auto_zero_step(self) -> None:
        """自动归零定时器回调。"""
        if not self._node._is_active or not self._node._running or not self._auto_zero_active:
            self.stop_auto_zero()
            return

        if not self._state.is_running():
            self.stop_auto_zero()
            return

        all_at_zero = True
        with self._node._lock:
            for mid in self._node._motor_ids:
                target = self._node._current_targets[mid]
                if abs(target) > self._node._deadband:
                    all_at_zero = False
                    self.write_target(mid, 0.0)
                    self._node._last_target_change_time[mid] = time.monotonic()

        if all_at_zero:
            self._node.get_logger().info("全部电机已到达零位，自动归零完成")
            self.stop_auto_zero()

    def stop_auto_zero(self) -> None:
        """停止自动归零定时器。"""
        self._auto_zero_active = False
        if self._auto_zero_timer is not None:
            self._node.destroy_timer(self._auto_zero_timer)
            self._auto_zero_timer = None

    # ------------------------------------------------------------------
    # 急停恢复
    # ------------------------------------------------------------------

    def hold_current_targets_and_recover(self) -> None:
        """从急停或手动模式恢复运控模式，保持当前位置。"""
        with self._node._lock:
            for mid in self._node._motor_ids:
                try:
                    self._node._driver.write_sdo_int(mid, SDO_RUN_MODE, 1)
                    self._node._driver.write_sdo_float(mid, SDO_TARGET_POS, self._node._current_targets[mid])
                    self._node._driver.enter_control_mode(mid)
                    time.sleep(0.03)
                except Exception as exc:
                    self._node.get_logger().error(f"恢复电机 ID{mid} 运控模式时发生异常: {exc}")
        self._node.get_logger().info("全部电机已恢复运控模式（保持当前位置）")

    # ------------------------------------------------------------------
    # 状态汇总
    # ------------------------------------------------------------------

    def publish_state_summary(self) -> None:
        """发布当前状态汇总到日志。"""
        state_name = self._state.state_name
        with self._node._lock:
            summary_lines = [
                f"===== 节点状态汇总 =====",
                f"状态: {state_name}",
                f"IMU Roll: {math.degrees(self._node._latest_roll):.2f}°, Pitch: {math.degrees(self._node._latest_pitch):.2f}°",
                f"选中电机: ID{self._node._selected_motor_id}",
            ]
        summary_lines.append("各电机当前状态:")
        for cfg in self._node._motor_configs:
            mid = cfg.motor_id
            target = self._node._current_targets.get(mid, 0.0)
            speed = self._node._current_speeds.get(mid, 0.0)
            protected = self._node._motor_protection_flags.get(mid, False)
            fb = self._node._motor_feedback.get(mid)
            if fb is not None:
                summary_lines.append(
                    f"  {cfg.name}(ID{mid}): target={target:.3f} rad, actual={fb.position_rad:.3f} rad, "
                    f"speed={speed:.2f}, torque={fb.torque_nm:.3f} Nm, "
                    f"temp={fb.temperature:.1f}°C, 模式={fb.mode_name}"
                    + (" [保护]" if protected else "")
                    + (f" [故障:{fb.fault_names}]" if fb.has_fault else "")
                )
            else:
                summary_lines.append(
                    f"  {cfg.name}(ID{mid}): target={target:.3f} rad, speed={speed:.2f} (无反馈数据)"
                    + (" [保护]" if protected else "")
                )

        for line in summary_lines:
            self._node.get_logger().info(line)


# 需要导入 String 用于发布
from std_msgs.msg import String  # noqa: E402
