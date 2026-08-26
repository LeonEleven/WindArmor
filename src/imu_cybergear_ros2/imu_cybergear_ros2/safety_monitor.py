"""安全监控：看门狗、电机反馈监控、急停系统。"""

import time
from typing import Callable, Dict

from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger, SetBool

from .controller_state import (
    ControllerState,
    TransitionOutcome,
    TransitionReason,
    TransitionSource,
)
from .cybergear_driver import MotorStatus
from .motor_health import (
    MotorHealthAction,
    MotorHealthConfig,
    MotorHealthCore,
    MotorHealthReason,
    MotorSafetyFaultSnapshot,
)


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

    def __init__(
        self,
        node,
        state_mgr,
        motor_mgr,
        *,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ):
        self._node = node
        self._state = state_mgr
        self._motor_mgr = motor_mgr
        self._monotonic = monotonic_fn
        self._watchdog_timer = None
        self._feedback_timer = None
        self._last_warning_time: Dict[str, float] = {}
        self._health = MotorHealthCore(
            MotorHealthConfig(
                motor_ids=tuple(node._motor_ids),
                temp_warning_deg_c=getattr(node, "_motor_temp_limit_deg_c", 80.0),
                temp_critical_deg_c=getattr(node, "_motor_temp_critical_deg_c", 90.0),
                invalid_feedback_limit=getattr(node, "_motor_invalid_feedback_limit", 3),
                feedback_timeout_sec=getattr(node, "_motor_feedback_timeout_sec", 0.0),
                feedback_startup_grace_sec=getattr(
                    node, "_motor_feedback_startup_grace_sec", 3.0
                ),
            )
        )

    def _warn_throttled(self, key: str, message: str) -> None:
        """按告警类型限频，避免高频电机反馈导致日志刷屏。"""
        now = self._monotonic()
        previous = self._last_warning_time.get(key)
        if previous is None or now - previous >= self._node._warning_throttle_sec:
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

    @property
    def feedback_timer(self):
        return self._feedback_timer

    @property
    def health_core(self) -> MotorHealthCore:
        return self._health

    def start_feedback_monitor(self) -> None:
        """启动新的激活窗口；仅在启用时创建定时器。"""
        self.stop_feedback_monitor()
        self._health.activate(self._monotonic())
        if self._health.timeout_enabled:
            self._feedback_timer = self._node.create_timer(
                1.0 / getattr(self._node, "_motor_feedback_check_rate_hz", 10.0),
                self._feedback_watchdog_check,
            )

    def stop_feedback_monitor(self) -> None:
        timer = self._feedback_timer
        self._feedback_timer = None
        self._health.deactivate()
        if timer is not None:
            self._node.destroy_timer(timer)

    def _feedback_watchdog_check(self) -> None:
        if not self._node._is_active:
            return
        if getattr(self._node, "_motor_safety_fault_active", False):
            return
        try:
            for decision in self._health.check_freshness(now=self._monotonic()):
                self._trip_motor_safety(decision)
        except Exception as exc:
            self._node.get_logger().error(f"电机反馈新鲜度检查异常: {exc}")

    def on_motor_feedback(self, status: MotorStatus) -> None:
        """电机反馈回调函数。

        参数：
            status: 单台电机的实时反馈状态。
        """
        try:
            received_at = self._monotonic()
            decision = self._health.evaluate(status, received_at=received_at)
            mid = decision.motor_id

            if decision.action is MotorHealthAction.IGNORE:
                self._warn_throttled(
                    f"feedback:{decision.reason.value}:{mid}",
                    decision.diagnostic_message,
                )
                return
            if decision.reason is MotorHealthReason.INVALID_FEEDBACK:
                self._warn_throttled(
                    f"feedback:invalid:{mid}", decision.diagnostic_message
                )
                if (
                    decision.action is MotorHealthAction.TRIP
                    and self._feedback_safety_actions_allowed()
                ):
                    self._trip_motor_safety(decision)
                return

            # 只有完整合法的帧才能替换最近一次反馈。
            with self._node._lock:
                self._node._motor_feedback[mid] = status
                received_times = getattr(
                    self._node, "_motor_feedback_received_at", None
                )
                if received_times is None:
                    received_times = {}
                    self._node._motor_feedback_received_at = received_times
                received_times[mid] = received_at
                generations = getattr(
                    self._node, "_motor_feedback_generations", None
                )
                if generations is None:
                    generations = {}
                    self._node._motor_feedback_generations = generations
                generations[mid] = generations.get(mid, 0) + 1
                warning_flags = getattr(
                    self._node, "_motor_temperature_warning_flags", None
                )
                if warning_flags is None:
                    warning_flags = {}
                    self._node._motor_temperature_warning_flags = warning_flags
                warning_flags[mid] = (
                    status.temperature
                    >= getattr(self._node, "_motor_temp_limit_deg_c", 80.0)
                    and status.temperature
                    < getattr(self._node, "_motor_temp_critical_deg_c", 90.0)
                )

            # 安全决策先于可选的 ROS 发布，因此 publisher 失败绝不能抑制 ERROR 跳变。
            if decision.action is MotorHealthAction.WARNING:
                self._warn_throttled(
                    f"temperature:{mid}", decision.diagnostic_message
                )
            elif (
                decision.action is MotorHealthAction.TRIP
                and self._feedback_safety_actions_allowed()
            ):
                self._trip_motor_safety(decision)

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
            try:
                if self._node._motor_status_pub is not None:
                    self._node._motor_status_pub.publish(status_msg)
            except Exception as exc:
                self._node.get_logger().error(f"发布电机反馈状态失败: {exc}")

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

    def _feedback_safety_actions_allowed(self) -> bool:
        """保持采集独立，同时保留 lifecycle 安全动作。"""
        if self._motor_mgr is None or self._state is None:
            return False
        return self._state.state not in (
            ControllerState.UNINITIALIZED,
            ControllerState.SHUTTING_DOWN,
        )

    def _trip_motor_safety(self, decision) -> None:
        if not self._feedback_safety_actions_allowed():
            return
        snapshot = MotorSafetyFaultSnapshot(
            motor_id=decision.motor_id,
            reason=decision.reason,
            observed_value=decision.observed_value,
            threshold=decision.threshold,
            fault_flags=decision.fault_flags,
            fault_names=decision.fault_names,
            first_triggered_at=decision.timestamp,
            diagnostic_message=decision.diagnostic_message,
        )
        first = self._motor_mgr.enter_safety_error(snapshot)
        if not first:
            self._warn_throttled(
                f"latched:{decision.reason.value}:{decision.motor_id}",
                "反馈安全故障已锁存，记录后续事件但不重复执行停止批次: "
                + decision.diagnostic_message,
            )

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
        if getattr(self._node, "_motor_safety_fault_active", False):
            self._node.get_logger().error(
                "电机反馈安全故障已锁存；只能通过 lifecycle 重新配置或重启恢复"
            )
            return False
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
            self._motor_mgr.reset_fault_stop_batch_after_recovery()
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
        self._motor_mgr.stop_motors_for_fault_once(reason="emergency_stop")
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
