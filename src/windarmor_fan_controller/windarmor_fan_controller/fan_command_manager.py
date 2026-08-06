"""双风扇公共命令仲裁节点；本模块不接触任何硬件 I/O。"""

import math
import threading
import time
from typing import Optional

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Int32, Int32MultiArray, String, UInt64
from std_srvs.srv import SetBool, Trigger

from .fan_control import FanControlConfig, FanControlCore, FanControlOutput


class FanCommandManager(Node):
    """在公共手动输入和姿态 AUTO 之间进行唯一仲裁。"""

    def __init__(self) -> None:
        super().__init__("fan_command_manager")
        self._declare_parameters()
        control_rate = float(self.get_parameter("control_rate_hz").value)
        status_rate = float(self.get_parameter("status_publish_rate_hz").value)
        if not math.isfinite(control_rate) or control_rate <= 0.0:
            raise ValueError("control_rate_hz 必须大于 0")
        if not math.isfinite(status_rate) or status_rate <= 0.0:
            raise ValueError("status_publish_rate_hz 必须大于 0")

        config = FanControlConfig(
            min_pwm_us=int(self.get_parameter("min_pwm_us").value),
            max_pwm_us=int(self.get_parameter("max_pwm_us").value),
            fan_stop_pwm_us=int(self.get_parameter("fan_stop_pwm_us").value),
            fan_start_pwm_us=int(self.get_parameter("fan_start_pwm_us").value),
            fan_auto_max_pwm_us=int(
                self.get_parameter("fan_auto_max_pwm_us").value
            ),
            fan_deadband_on_deg=float(
                self.get_parameter("fan_deadband_on_deg").value
            ),
            fan_deadband_off_deg=float(
                self.get_parameter("fan_deadband_off_deg").value
            ),
            fan_full_scale_deg=float(
                self.get_parameter("fan_full_scale_deg").value
            ),
            fan_response_curve=str(
                self.get_parameter("fan_response_curve").value
            ),
            rise_step_pwm_us=int(self.get_parameter("rise_step_pwm_us").value),
            fall_step_pwm_us=int(self.get_parameter("fall_step_pwm_us").value),
            imu_timeout_sec=float(self.get_parameter("imu_timeout_sec").value),
            manual_command_timeout_sec=float(
                self.get_parameter("manual_command_timeout_sec").value
            ),
            motor_mode_timeout_sec=float(
                self.get_parameter("motor_mode_timeout_sec").value
            ),
            fan_enabled_timeout_sec=float(
                self.get_parameter("fan_enabled_timeout_sec").value
            ),
            require_motor_mode_for_manual=bool(
                self.get_parameter("require_motor_mode_for_manual").value
            ),
        )
        self._core = FanControlCore(config)
        self._core_lock = threading.RLock()
        self._last_pose_source_stamp_ns: Optional[int] = None
        self._last_observable_signature = None

        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        command_qos = QoSProfile(
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._command_pub = self.create_publisher(
            Int32MultiArray, "/fans/command_pwm", command_qos
        )
        self._auto_enabled_pub = self.create_publisher(
            Bool, "/fans/auto_enabled", state_qos
        )
        self._auto_active_pub = self.create_publisher(
            Bool, "/fans/auto_active", state_qos
        )
        self._auto_target_pub = self.create_publisher(
            Int32MultiArray, "/fans/auto_target_pwm", state_qos
        )
        self._control_state_pub = self.create_publisher(
            String, "/fans/control_state", state_qos
        )

        self.create_subscription(
            Int32MultiArray, "/fans/pwm", self._on_manual_pair, command_qos
        )
        self.create_subscription(
            Int32, "/fans/left/pwm", self._on_manual_left, command_qos
        )
        self.create_subscription(
            Int32, "/fans/right/pwm", self._on_manual_right, command_qos
        )
        self.create_subscription(
            Vector3Stamped,
            "/imu/relative_roll_pitch",
            self._on_relative_attitude,
            command_qos,
        )
        self.create_subscription(
            UInt64, "/imu/zero_generation", self._on_zero_generation, state_qos
        )
        self.create_subscription(
            String, "/motors/control_mode", self._on_motor_mode, state_qos
        )
        self.create_subscription(
            Bool, "/fans/enabled", self._on_fan_enabled, state_qos
        )
        self.create_subscription(Bool, "/e_stop", self._on_e_stop, command_qos)
        self._auto_enable_srv = self.create_service(
            SetBool, "/fans/auto_enable", self._on_auto_enable
        )
        self._manual_enable_srv = self.create_service(
            SetBool, "/fans/manual_enable", self._on_manual_enable
        )
        self._reset_e_stop_srv = self.create_service(
            Trigger, "/fans/reset_e_stop", self._on_reset_e_stop
        )
        self._control_timer = self.create_timer(
            1.0 / control_rate, self._control_tick
        )
        self._status_timer = self.create_timer(
            1.0 / status_rate, self._publish_observable_state
        )
        if bool(self.get_parameter("auto_enabled_at_start").value):
            with self._core_lock:
                success, message = self._core.request_auto(
                    True, time.monotonic()
                )
                if not success:
                    self.get_logger().warn(
                        f"启动时 AUTO 请求被安全条件拒绝: {message}"
                    )
        self._finish_observation(force=True)

    def _declare_parameters(self) -> None:
        self.declare_parameter("min_pwm_us", 800)
        self.declare_parameter("max_pwm_us", 2200)
        self.declare_parameter("fan_stop_pwm_us", 800)
        self.declare_parameter("fan_start_pwm_us", 1200)
        self.declare_parameter("fan_auto_max_pwm_us", 1400)
        self.declare_parameter("fan_deadband_on_deg", 5.0)
        self.declare_parameter("fan_deadband_off_deg", 3.0)
        self.declare_parameter("fan_full_scale_deg", 45.0)
        self.declare_parameter("fan_response_curve", "smoothstep")
        self.declare_parameter("auto_enabled_at_start", False)
        self.declare_parameter("control_rate_hz", 20.0)
        self.declare_parameter("status_publish_rate_hz", 5.0)
        self.declare_parameter("rise_step_pwm_us", 10)
        self.declare_parameter("fall_step_pwm_us", 20)
        self.declare_parameter("imu_timeout_sec", 0.2)
        self.declare_parameter("manual_command_timeout_sec", 0.5)
        self.declare_parameter("motor_mode_timeout_sec", 1.0)
        self.declare_parameter("fan_enabled_timeout_sec", 1.0)
        self.declare_parameter("require_motor_mode_for_manual", False)

    def _publish_command(self, command_pwm: tuple[int, int]) -> None:
        command = Int32MultiArray()
        command.data = list(command_pwm)
        self._command_pub.publish(command)

    def _finish_observation(self, *, force: bool = False) -> None:
        """发布安全停止（若有）及观察状态，但绝不推进普通输出。"""
        with self._core_lock:
            output = self._core.output
            if self._core.take_immediate_stop():
                self._publish_command(output.command_pwm)
            self._publish_observable_state(force=force, output=output)

    def _on_manual_pair(self, msg: Int32MultiArray) -> None:
        if len(msg.data) != 2:
            self.get_logger().error("/fans/pwm 必须恰好包含两个整数")
            return
        with self._core_lock:
            accepted = self._core.update_manual_pair(
                int(msg.data[0]), int(msg.data[1]), time.monotonic()
            )
        if not accepted:
            self.get_logger().warn("拒绝无效、未授权或缺少停止基线的 /fans/pwm")
        self._finish_observation()

    def _on_manual_left(self, msg: Int32) -> None:
        with self._core_lock:
            accepted = self._core.update_manual_side(
                0, int(msg.data), time.monotonic()
            )
        if not accepted:
            self.get_logger().warn("拒绝无效或当前状态不允许的 /fans/left/pwm")
        self._finish_observation()

    def _on_manual_right(self, msg: Int32) -> None:
        with self._core_lock:
            accepted = self._core.update_manual_side(
                1, int(msg.data), time.monotonic()
            )
        if not accepted:
            self.get_logger().warn("拒绝无效或当前状态不允许的 /fans/right/pwm")
        self._finish_observation()

    def _on_relative_attitude(self, msg: Vector3Stamped) -> None:
        stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        with self._core_lock:
            if (
                stamp_ns > 0
                and self._last_pose_source_stamp_ns is not None
                and stamp_ns <= self._last_pose_source_stamp_ns
            ):
                self.get_logger().warn("拒绝时间戳倒退或重复的相对姿态")
                self._core.invalidate_pose()
            elif not self._core.update_pose(
                msg.vector.x, msg.vector.y, time.monotonic()
            ):
                self.get_logger().warn("拒绝包含 NaN/Inf 的相对姿态")
            elif stamp_ns > 0:
                self._last_pose_source_stamp_ns = stamp_ns
        self._finish_observation()

    def _on_zero_generation(self, msg: UInt64) -> None:
        with self._core_lock:
            self._last_pose_source_stamp_ns = None
            self._core.update_zero_generation(int(msg.data))
        self._finish_observation()

    def _on_motor_mode(self, msg: String) -> None:
        with self._core_lock:
            accepted = self._core.update_motor_mode(
                msg.data, time.monotonic()
            )
        if not accepted:
            self.get_logger().error(f"拒绝未知电机模式: {msg.data!r}")
        self._finish_observation()

    def _on_fan_enabled(self, msg: Bool) -> None:
        with self._core_lock:
            self._core.update_fan_enabled(msg.data, time.monotonic())
        self._finish_observation()

    def _on_e_stop(self, msg: Bool) -> None:
        with self._core_lock:
            self._core.update_e_stop(msg.data, time.monotonic())
        self._finish_observation()

    def _on_auto_enable(
        self,
        request: SetBool.Request,
        response: SetBool.Response,
    ) -> SetBool.Response:
        with self._core_lock:
            response.success, response.message = self._core.request_auto(
                request.data, time.monotonic()
            )
        self._finish_observation()
        return response

    def _on_manual_enable(
        self,
        request: SetBool.Request,
        response: SetBool.Response,
    ) -> SetBool.Response:
        with self._core_lock:
            response.success, response.message = self._core.request_manual(
                request.data, time.monotonic()
            )
        self._finish_observation()
        return response

    def _on_reset_e_stop(
        self,
        _request: Trigger.Request,
        response: Trigger.Response,
    ) -> Trigger.Response:
        with self._core_lock:
            response.success, response.message = self._core.reset_e_stop(
                time.monotonic()
            )
        self._finish_observation()
        return response

    def _control_tick(self) -> None:
        """唯一正常命令发布和 AUTO 斜坡推进入口。"""
        with self._core_lock:
            output = self._core.control_tick(time.monotonic())
            self._core.take_immediate_stop()
            self._publish_command(output.command_pwm)
            self._publish_observable_state(force=False, output=output)

    def _publish_observable_state(
        self,
        *,
        force: bool = True,
        output: Optional[FanControlOutput] = None,
    ) -> None:
        if output is None:
            with self._core_lock:
                output = self._core.output
        signature = (
            output.state,
            output.auto_enabled,
            output.auto_active,
            output.auto_target_pwm,
        )
        if not force and signature == self._last_observable_signature:
            return
        self._last_observable_signature = signature

        state = String()
        state.data = output.state.value
        self._control_state_pub.publish(state)

        auto_enabled = Bool()
        auto_enabled.data = output.auto_enabled
        self._auto_enabled_pub.publish(auto_enabled)

        auto_active = Bool()
        auto_active.data = output.auto_active
        self._auto_active_pub.publish(auto_active)

        target = Int32MultiArray()
        target.data = list(output.auto_target_pwm)
        self._auto_target_pub.publish(target)

    def destroy_node(self) -> None:
        with self._core_lock:
            self._core.request_auto(False, time.monotonic())
        self._finish_observation(force=True)
        super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = FanCommandManager()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
