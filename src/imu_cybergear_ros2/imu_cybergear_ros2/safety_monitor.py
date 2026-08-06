"""安全监控：看门狗、电机反馈监控、急停系统。"""

import time
from typing import Dict

from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger, SetBool

from .controller_state import (
    ControllerState,
    TransitionOutcome,
    TransitionReason,
    TransitionSource,
)
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
        self._last_warning_time: Dict[str, float] = {}

    def _warn_throttled(self, key: str, message: str) -> None:
        """按告警类型限频，避免高频电机反馈导致日志刷屏。"""
        now = time.monotonic()
        previous = self._last_warning_time.get(key, 0.0)
        if now - previous >= self._node._warning_throttle_sec:
            self._node.get_logger().warn(message)
            self._last_warning_time[key] = now

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
                result = self._state.transition_to(
                    ControllerState.MANUAL_RUNNING,
                    reason=TransitionReason.IMU_WATCHDOG_TIMEOUT,
                    source=TransitionSource.WATCHDOG,
                )
                if result.outcome is TransitionOutcome.REJECTED:
                    self._node.get_logger().error(
                        "关键状态转换被拒绝：IMU watchdog 无法退出 AUTO"
                    )
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
            with self._node._lock:
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
                self._warn_throttled(
                    f"fault:{mid}",
                    f"电机 ID{mid} 故障: {status.fault_names}, "
                    f"温度={status.temperature:.1f}°C",
                )
                with self._node._lock:
                    self._node._motor_protection_flags[mid] = True
            else:
                with self._node._lock:
                    was_protected = self._node._motor_protection_flags.get(mid, False)
                    if was_protected:
                        self._node._motor_protection_flags[mid] = False
                if was_protected:
                    self._node.get_logger().info(f"电机 ID{mid} 故障已清除，恢复目标更新")

            # 位置误差检查
            with self._node._lock:
                init_complete = self._node._init_complete
                target = self._node._current_targets.get(mid)
                changed_at = self._node._last_target_change_time.get(mid, 0.0)
            if init_complete and target is not None:
                skip_state = self._state.state in (
                    ControllerState.EMERGENCY_STOP,
                    ControllerState.ERROR,
                    ControllerState.INITIALIZING,
                )
                if not skip_state:
                    actual = status.position_rad
                    elapsed = time.monotonic() - changed_at
                    if elapsed > 0.5:
                        error = abs(target - actual)
                        if error > self._node._position_error_threshold:
                            self._warn_throttled(
                                f"position:{mid}",
                                f"电机 ID{mid} 位置偏差过大: 目标={target:.3f} rad, "
                                f"实际={actual:.3f} rad, 偏差={error:.3f} rad",
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
            if self._state.state in (
                ControllerState.EMERGENCY_STOP,
                ControllerState.SHUTTING_DOWN,
            ):
                return
            self._node.get_logger().warn("收到 /e_stop 话题急停指令！")
            self.emergency_stop(
                reason=TransitionReason.TOPIC_ESTOP,
                source=TransitionSource.TOPIC,
            )

    def on_e_stop_service(self, request, response: Trigger.Response) -> Trigger.Response:
        """急停服务回调。"""
        if not self._node._is_active:
            response.success = False
            response.message = "节点未激活"
            return response
        self._node.get_logger().warn("收到 /e_stop 服务急停请求！")
        response.success = self.emergency_stop(
            reason=TransitionReason.SERVICE_ESTOP,
            source=TransitionSource.SERVICE,
        )
        if response.success:
            self._node.publish_system_emergency_stop()
            response.message = "急停已执行"
        else:
            response.message = "急停状态转换被拒绝，请检查控制器状态"
        return response

    def on_enable_motor_service(self, request, response: SetBool.Response) -> SetBool.Response:
        """远程启停服务回调。"""
        if not self._node._is_active:
            response.success = False
            response.message = "节点未激活"
            return response
        if request.data:
            if self._state.state == ControllerState.ERROR:
                response.success = False
                response.message = "控制器处于 ERROR；排除故障后需重新配置或重启节点"
                self._node.get_logger().error(response.message)
                return response
            if self._state.state != ControllerState.EMERGENCY_STOP:
                response.success = False
                response.message = "仅允许从 EMERGENCY_STOP 显式恢复电机"
                self._node.get_logger().warn(response.message)
                return response
            self._node.get_logger().info("收到 /enable_motor 启用指令，尝试恢复运控模式")
            response.success = self.recover_from_emergency_stop(
                source=TransitionSource.SERVICE
            )
            if response.success:
                response.message = "电机已恢复至 MANUAL 运控模式"
            else:
                response.message = "部分电机恢复失败，控制状态未恢复"
                self._node.get_logger().error(response.message)
        else:
            self._node.get_logger().warn("收到 /enable_motor 停用指令，执行急停")
            response.success = self.emergency_stop(
                reason=TransitionReason.REMOTE_DISABLE,
                source=TransitionSource.SERVICE,
            )
            response.message = (
                "急停已执行"
                if response.success
                else "停用请求的急停状态转换被拒绝"
            )
        return response

    def recover_from_emergency_stop(self, *, source: TransitionSource) -> bool:
        """完成真实电机恢复后，以显式原因进入 MANUAL。"""
        if not self._state.is_in(ControllerState.EMERGENCY_STOP):
            self._node.get_logger().error("仅允许从 EMERGENCY_STOP 显式恢复")
            return False
        if not self._motor_mgr.hold_current_targets_and_recover():
            return False
        result = self._state.transition_to(
            ControllerState.MANUAL_RUNNING,
            reason=TransitionReason.EXPLICIT_ESTOP_RECOVERY,
            source=source,
        )
        if result.outcome is TransitionOutcome.CHANGED:
            return True

        self._node.get_logger().error(
            "电机已恢复运控但状态转换未成功；正在重新尽力停止全部电机"
        )
        self._motor_mgr.halt_motion()
        self._motor_mgr.stop_motors_best_effort(
            reason="recovery_state_transition_rejected"
        )
        return False

    def emergency_stop(
        self,
        *,
        reason: TransitionReason,
        source: TransitionSource,
    ) -> bool:
        """执行急停并返回状态是否已安全进入或保持急停。"""
        if self._state.is_in(ControllerState.EMERGENCY_STOP):
            self._node.get_logger().warn("当前已处于急停状态，忽略重复急停请求")
            return True
        if self._state.is_in(
            ControllerState.ERROR,
            ControllerState.SHUTTING_DOWN,
            ControllerState.UNINITIALIZED,
        ):
            self._node.get_logger().error(
                f"当前状态 {self._state.state_name} 不允许进入急停"
            )
            return False

        self._node.get_logger().error("【急停】正在停止全部电机！")
        # 普通推进必须先停，不能让速度限制或并发定时器延迟急停。
        self._motor_mgr.halt_motion()
        self._motor_mgr.stop_motors_best_effort(reason="emergency_stop")
        with self._node._lock:
            for mid in self._node._motor_ids:
                self._node._motor_protection_flags[mid] = False

        result = self._state.transition_to(
            ControllerState.EMERGENCY_STOP,
            reason=reason,
            source=source,
        )
        if result.outcome is TransitionOutcome.REJECTED:
            self._node.get_logger().error(
                "关键状态转换被拒绝：电机已停止但无法进入 EMERGENCY_STOP"
            )
            return False
        return True
