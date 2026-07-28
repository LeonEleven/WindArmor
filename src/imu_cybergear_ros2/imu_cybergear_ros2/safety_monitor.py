"""安全监控：看门狗、电机反馈监控、急停系统。"""

import time
from typing import Dict

from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger, SetBool

from .controller_state import ControllerState
from .cybergear_driver import MotorStatus


class SafetyMonitor:
    """安全监控模块。

    职责：
      - IMU 看门狗（超时自动切手动模式）
      - 电机反馈监控（故障标志、位置误差）
      - 急停系统（话题、服务、键盘三种触发方式）

    参数：
        node: ROS2 LifecycleNode 实例。
        state_mgr: StateManager 实例。
        motor_mgr: MotorManager 实例（用于急停时停止电机）。
    """

    def __init__(self, node, state_mgr, motor_mgr):
        self._node = node
        self._state = state_mgr
        self._motor_mgr = motor_mgr
        self._watchdog_timer = None

    # ------------------------------------------------------------------
    # 看门狗
    # ------------------------------------------------------------------

    def start_watchdog(self, period: float) -> None:
        """启动看门狗定时器。"""
        self._watchdog_timer = self._node.create_timer(period, self._watchdog_check)

    def stop_watchdog(self) -> None:
        """停止看门狗定时器。"""
        if self._watchdog_timer is not None:
            self._node.destroy_timer(self._watchdog_timer)
            self._watchdog_timer = None

    def _watchdog_check(self) -> None:
        """看门狗定时器回调。"""
        if not self._node._is_active:
            return
        try:
            if not self._state.is_auto_running():
                return
            if self._node._last_imu_time <= 0.0:
                return

            now = time.monotonic()
            elapsed = now - self._node._last_imu_time
            if elapsed > self._node._watchdog_timeout_s:
                self._node.get_logger().warn(
                    f"IMU 数据超时（已 {elapsed:.3f}s > {self._node._watchdog_timeout_s:.3f}s），"
                    f"自动切换到手动模式并保持当前位置"
                )
                self._state.transition_to(ControllerState.MANUAL_RUNNING)
        except Exception as exc:
            self._node.get_logger().error(f"看门狗检查时发生异常: {exc}")

    # ------------------------------------------------------------------
    # 电机反馈监控
    # ------------------------------------------------------------------

    def on_motor_feedback(self, status: MotorStatus) -> None:
        """电机反馈回调函数。

        参数：
            status: 单台电机的实时反馈状态。
        """
        if not self._node._is_active:
            return
        try:
            mid = status.motor_id
            self._node._motor_feedback[mid] = status

            # 发布格式化的电机状态字符串
            status_msg = String()
            status_msg.data = (
                f"{mid},"
                f"{status.position_rad:.4f},"
                f"{status.speed_rad_s:.4f},"
                f"{status.torque_nm:.3f},"
                f"{status.temperature:.1f},"
                f"{status.mode_name},"
                f"0x{status.fault_flags:02X}"
            )
            if self._node._motor_status_pub is not None:
                self._node._motor_status_pub.publish(status_msg)

            # 故障检查
            if status.has_fault:
                self._node.get_logger().warn(
                    f"电机 ID{mid} 故障: {status.fault_names}, "
                    f"温度={status.temperature:.1f}°C"
                )
                self._node._motor_protection_flags[mid] = True
            else:
                if self._node._motor_protection_flags.get(mid, False):
                    self._node._motor_protection_flags[mid] = False
                    self._node.get_logger().info(f"电机 ID{mid} 故障已清除，恢复目标更新")

            # 位置误差检查
            if self._node._init_complete and mid in self._node._current_targets:
                skip_state = self._state.state in (
                    ControllerState.EMERGENCY_STOP,
                    ControllerState.ERROR,
                    ControllerState.INITIALIZING,
                )
                if not skip_state:
                    target = self._node._current_targets[mid]
                    actual = status.position_rad
                    elapsed = time.monotonic() - self._node._last_target_change_time.get(mid, 0.0)
                    if elapsed > 0.5:
                        error = abs(target - actual)
                        if error > self._node._position_error_threshold:
                            self._node.get_logger().warn(
                                f"电机 ID{mid} 位置偏差过大: 目标={target:.3f} rad, "
                                f"实际={actual:.3f} rad, 偏差={error:.3f} rad"
                            )

        except Exception as exc:
            self._node.get_logger().error(f"处理电机反馈时发生异常: {exc}")

    # ------------------------------------------------------------------
    # 急停系统
    # ------------------------------------------------------------------

    def on_e_stop_topic(self, msg: Bool) -> None:
        """急停话题回调。"""
        if not self._node._is_active:
            return
        if msg.data:
            self._node.get_logger().warn("收到 /e_stop 话题急停指令！")
            self.emergency_stop()

    def on_e_stop_service(self, request, response: Trigger.Response) -> Trigger.Response:
        """急停服务回调。"""
        if not self._node._is_active:
            response.success = False
            response.message = "节点未激活"
            return response
        self._node.get_logger().warn("收到 /e_stop 服务急停请求！")
        self.emergency_stop()
        self._node.publish_system_emergency_stop()
        response.success = True
        response.message = "急停已执行"
        return response

    def on_enable_motor_service(self, request, response: SetBool.Response) -> SetBool.Response:
        """远程启停服务回调。"""
        if not self._node._is_active:
            response.success = False
            response.message = "节点未激活"
            return response
        if request.data:
            self._node.get_logger().info("收到 /enable_motor 启用指令，尝试恢复运控模式")
            self._motor_mgr.hold_current_targets_and_recover()
            response.success = True
            response.message = "电机已恢复运控模式"
        else:
            self._node.get_logger().warn("收到 /enable_motor 停用指令，执行急停")
            self.emergency_stop()
            response.success = True
            response.message = "急停已执行"
        return response

    def emergency_stop(self) -> None:
        """执行急停。"""
        with self._state._state_lock:
            current_state = self._state.state
            if current_state in (ControllerState.EMERGENCY_STOP, ControllerState.SHUTTING_DOWN):
                self._node.get_logger().warn("当前已处于急停或关机状态，忽略重复急停请求")
                return

        self._node.get_logger().error("【急停】正在停止全部电机！")
        with self._node._lock:
            for mid in self._node._motor_ids:
                try:
                    self._node._driver.stop_motor(mid)
                except Exception as exc:
                    self._node.get_logger().error(f"急停时停止电机 ID{mid} 发生异常: {exc}")
            for mid in self._node._motor_ids:
                self._node._motor_protection_flags[mid] = False

        self._state.transition_to(ControllerState.EMERGENCY_STOP)
