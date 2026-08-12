"""双风扇公共命令仲裁节点；本模块不接触任何硬件 I/O。"""

import math
import re
import threading
import time
from typing import Callable, Optional

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Int32, Int32MultiArray, String, UInt64
from std_srvs.srv import SetBool, Trigger
from windarmor_interfaces.msg import (
    FanSafetyState,
    FlightCommandEnvelope,
    OwnershipState,
)
from windarmor_interfaces.srv import (
    CommitFlightOwnership,
    PrepareFlightOwnership,
    RevokeFlightOwnership,
)

from .fan_control import FanControlConfig, FanControlCore, FanControlOutput


class FanCommandManager(Node):
    """在公共手动输入和姿态 AUTO 之间进行唯一仲裁。"""

    def __init__(
        self,
        *,
        source_epoch_fn: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        source_epoch = source_epoch_fn()
        if (
            isinstance(source_epoch, bool)
            or not isinstance(source_epoch, int)
            or not 0 < source_epoch <= (2**64 - 1)
        ):
            raise ValueError("fan safety source epoch must be a positive uint64")
        super().__init__("fan_command_manager")
        self._safety_source_epoch = source_epoch
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
            flight_fan_max_pwm_us=int(
                self.get_parameter("flight_fan_max_pwm_us").value
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
            fan_flight_command_timeout_sec=float(
                self.get_parameter("fan_flight_command_timeout_sec").value
            ),
        )
        interface_parameters = (
            "fan_ownership_state_topic",
            "fan_flight_prepare_service",
            "fan_flight_commit_service",
            "fan_flight_revoke_service",
            "flight_command_topic",
        )
        self._flight_interfaces = {
            name: self._validate_ros_name(name, self.get_parameter(name).value)
            for name in interface_parameters
        }
        flight_motor_names = tuple(self.get_parameter("flight_motor_names").value)
        if (
            not flight_motor_names
            or len(set(flight_motor_names)) != len(flight_motor_names)
            or any(not isinstance(name, str) or not name for name in flight_motor_names)
        ):
            raise ValueError("flight_motor_names 必须是非空且唯一的字符串列表")
        self._flight_motor_names = flight_motor_names
        self._core = FanControlCore(config)
        self._core_lock = threading.RLock()
        self._last_pose_source_stamp_ns: Optional[int] = None
        self._last_observable_signature = None
        self._safety_observation_sequence = 1
        self._ownership_observation_sequence = 1

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
        self._safety_state_pub = self.create_publisher(
            FanSafetyState, "/fans/safety_state", state_qos
        )
        self._ownership_state_pub = self.create_publisher(
            OwnershipState,
            self._flight_interfaces["fan_ownership_state_topic"],
            state_qos,
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
        self._flight_command_sub = self.create_subscription(
            FlightCommandEnvelope,
            self._flight_interfaces["flight_command_topic"],
            self._on_flight_command,
            command_qos,
        )
        self._auto_enable_srv = self.create_service(
            SetBool, "/fans/auto_enable", self._on_auto_enable
        )
        self._manual_enable_srv = self.create_service(
            SetBool, "/fans/manual_enable", self._on_manual_enable
        )
        self._reset_e_stop_srv = self.create_service(
            Trigger, "/fans/reset_e_stop", self._on_reset_e_stop
        )
        self._flight_prepare_srv = self.create_service(
            PrepareFlightOwnership,
            self._flight_interfaces["fan_flight_prepare_service"],
            self._on_flight_prepare,
        )
        self._flight_commit_srv = self.create_service(
            CommitFlightOwnership,
            self._flight_interfaces["fan_flight_commit_service"],
            self._on_flight_commit,
        )
        self._flight_revoke_srv = self.create_service(
            RevokeFlightOwnership,
            self._flight_interfaces["fan_flight_revoke_service"],
            self._on_flight_revoke,
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
        self.declare_parameter("flight_fan_max_pwm_us", 1400)
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
        self.declare_parameter("fan_flight_command_timeout_sec", 0.25)
        self.declare_parameter("fan_ownership_state_topic", "/fans/ownership_state")
        self.declare_parameter("fan_flight_prepare_service", "/fans/flight_ownership/prepare")
        self.declare_parameter("fan_flight_commit_service", "/fans/flight_ownership/commit")
        self.declare_parameter("fan_flight_revoke_service", "/fans/flight_ownership/revoke")
        self.declare_parameter("flight_command_topic", "/flight_control/command")
        self.declare_parameter(
            "flight_motor_names",
            ["left_lift", "left_pitch", "right_pitch", "right_lift"],
        )

    @staticmethod
    def _validate_ros_name(name: str, value: object) -> str:
        if (
            not isinstance(value, str)
            or not value
            or "//" in value
            or value.endswith("/")
            or re.fullmatch(r"/?[A-Za-z_][A-Za-z0-9_/]*", value) is None
        ):
            raise ValueError(f"{name} 必须是合法的非空 ROS 名称")
        return value

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
        self._publish_safety_state()
        self._publish_ownership_state()
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

    def _publish_safety_state(self) -> None:
        """Publish a core snapshot without producing or advancing PWM output."""

        try:
            with self._core_lock:
                snapshot = self._core.safety_snapshot
                sequence = self._safety_observation_sequence
                self._safety_observation_sequence += 1
            message = FanSafetyState()
            message.stamp = self.get_clock().now().to_msg()
            message.source_epoch = self._safety_source_epoch
            message.observation_sequence = sequence
            message.e_stop_latched = snapshot.e_stop_latched
            message.control_state = snapshot.control_state
            message.enabled_observed = snapshot.enabled_observed
            message.enabled = snapshot.enabled
            message.manual_armed = snapshot.manual_armed
            message.legacy_auto_requested = snapshot.legacy_auto_requested
            message.legacy_auto_active = snapshot.legacy_auto_active
            message.safety_reason = snapshot.safety_reason
            message.passive_for_takeover = snapshot.passive_for_takeover
            self._safety_state_pub.publish(message)
        except Exception as exc:
            self.get_logger().error(
                f"发布风扇安全只读快照失败（不改变 core 或 PWM）: {exc}"
            )

    def _publish_ownership_state(self) -> None:
        try:
            with self._core_lock:
                ownership = self._core.ownership
                sequence = self._ownership_observation_sequence
                self._ownership_observation_sequence += 1
            message = OwnershipState()
            message.stamp = self.get_clock().now().to_msg()
            message.source_epoch = self._safety_source_epoch
            message.observation_sequence = sequence
            message.owner_domain = "fan"
            message.ownership_phase = ownership.owner.value
            message.authority_present = ownership.authority_epoch is not None
            message.authority_epoch = ownership.authority_epoch or 0
            message.generation = ownership.generation or 0
            message.last_accepted_flight_command_present = (
                ownership.last_command_sequence is not None
            )
            message.last_accepted_flight_command_sequence = (
                ownership.last_command_sequence or 0
            )
            message.last_valid_flight_command_age_sec = (
                ownership.last_valid_command_age(time.monotonic())
            )
            self._ownership_state_pub.publish(message)
        except Exception as exc:
            self.get_logger().error(
                f"发布 fan ownership 快照失败（不改变 core 或 PWM）: {exc}"
            )

    def _ownership_response(self, response, result):
        response.success = result.success
        response.reason_code = result.reason_code
        response.authority_epoch = result.authority_epoch
        response.generation = result.generation
        response.owner_observation_sequence = max(
            0, self._ownership_observation_sequence - 1
        )
        return response

    def _on_flight_prepare(self, request, response):
        with self._core_lock:
            result = self._core.prepare_flight_ownership(
                int(request.authority_epoch),
                int(request.generation),
                now=time.monotonic(),
            )
        self._finish_observation()
        return self._ownership_response(response, result)

    def _on_flight_commit(self, request, response):
        with self._core_lock:
            result = self._core.commit_flight_ownership(
                int(request.authority_epoch),
                int(request.generation),
                now=time.monotonic(),
            )
        self._finish_observation()
        return self._ownership_response(response, result)

    def _on_flight_revoke(self, request, response):
        with self._core_lock:
            result = self._core.revoke_flight_ownership(
                int(request.authority_epoch), int(request.generation)
            )
        self._finish_observation()
        return self._ownership_response(response, result)

    def _on_flight_command(self, message: FlightCommandEnvelope) -> None:
        names = list(message.motor_names)
        positions = list(message.motor_positions_rad)
        common_valid = (
            len(names) == len(positions)
            and len(set(names)) == len(names)
            and all(isinstance(name, str) and name for name in names)
            and all(math.isfinite(float(value)) for value in positions)
        )
        expected_motor_names = self._flight_motor_names
        now = time.monotonic()
        with self._core_lock:
            if message.request_safe_stop:
                if not common_valid or names or positions or message.fan_commands_present:
                    result = None
                else:
                    result = self._core.accept_flight_safe_stop(
                        int(message.authority_epoch),
                        int(message.generation),
                        int(message.command_sequence),
                        now=now,
                    )
            elif (
                common_valid
                and set(names) == set(expected_motor_names)
                and len(names) == len(expected_motor_names)
                and message.fan_commands_present
                and math.isfinite(float(message.fan_left))
                and math.isfinite(float(message.fan_right))
                and 0.0 <= float(message.fan_left) <= 1.0
                and 0.0 <= float(message.fan_right) <= 1.0
            ):
                result = self._core.update_flight_command(
                    int(message.authority_epoch),
                    int(message.generation),
                    int(message.command_sequence),
                    float(message.fan_left),
                    float(message.fan_right),
                    now=now,
                )
            else:
                result = None
        if result is None:
            self.get_logger().warn("拒绝 payload contract 非法的 Flight command")
            with self._core_lock:
                self._core.force_safe_stop("invalid Flight command envelope")
        elif not result.success:
            self.get_logger().warn(
                f"拒绝 Flight fan command: {result.reason_code}"
            )
            if result.reason_code in {
                "invalid_token",
                "authority_token_mismatch",
                "flight_command_not_allowed",
            }:
                with self._core_lock:
                    self._core.force_safe_stop(
                        f"Flight command rejected: {result.reason_code}"
                    )
        self._finish_observation()

    def destroy_node(self) -> None:
        with self._core_lock:
            self._core.force_safe_stop("fan command manager shutdown")
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
