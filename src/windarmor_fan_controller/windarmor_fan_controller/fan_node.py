"""双涵道风扇 ROS 2 控制节点。"""

import time
from typing import Callable, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Int32MultiArray
from std_srvs.srv import SetBool, Trigger

from .pwm import (
    FanCommandGate,
    PwmRange,
    validate_positive_finite_timeout,
)


def initialize_after_timeout_validation(
    timeout_value,
    initializer: Callable[[], None],
) -> float:
    """先校验安全看门狗，再允许任何 GPIO/PWM 初始化。"""
    timeout = validate_positive_finite_timeout(timeout_value)
    initializer()
    return timeout


class DualFanController(Node):
    """通过两个 BCM GPIO 输出 ESC PWM，并提供安全停止接口。"""

    def __init__(self) -> None:
        super().__init__("fan_controller")

        self.declare_parameter("left_gpio", 12)
        self.declare_parameter("right_gpio", 13)
        self.declare_parameter("min_pwm_us", 800)
        self.declare_parameter("max_pwm_us", 2200)
        self.declare_parameter("stop_pwm_us", 800)
        self.declare_parameter("frame_width_sec", 0.020)
        self.declare_parameter("arm_delay_sec", 3.0)
        self.declare_parameter("command_timeout_sec", 1.0)
        self.declare_parameter("enabled_status_publish_rate_hz", 5.0)
        self.declare_parameter("warning_throttle_sec", 5.0)

        self._left_gpio = self.get_parameter("left_gpio").value
        self._right_gpio = self.get_parameter("right_gpio").value
        self._range = PwmRange(
            self.get_parameter("min_pwm_us").value,
            self.get_parameter("max_pwm_us").value,
        )
        self._stop_pwm = self._range.clamp(
            self.get_parameter("stop_pwm_us").value
        )
        self._frame_width = float(self.get_parameter("frame_width_sec").value)
        self._arm_delay = max(0.0, float(self.get_parameter("arm_delay_sec").value))
        command_timeout_value = self.get_parameter("command_timeout_sec").value
        self._warning_throttle = max(
            0.0, float(self.get_parameter("warning_throttle_sec").value)
        )
        enabled_status_rate = float(
            self.get_parameter("enabled_status_publish_rate_hz").value
        )

        if self._left_gpio == self._right_gpio:
            raise ValueError("left_gpio 与 right_gpio 不能相同")
        if self._frame_width <= 0.0:
            raise ValueError("frame_width_sec 必须大于 0")
        if enabled_status_rate <= 0.0:
            raise ValueError("enabled_status_publish_rate_hz 必须大于 0")

        self._command_gate = FanCommandGate(enabled=True)
        self._last_disabled_warning_time = 0.0
        self._current_pwm = [self._stop_pwm, self._stop_pwm]
        self._left_esc = None
        self._right_esc = None
        self._pin_factory = None

        self._command_timeout = initialize_after_timeout_validation(
            command_timeout_value,
            self._initialize_gpio,
        )

        self._pair_sub = self.create_subscription(
            Int32MultiArray, "/fans/command_pwm", self._on_pair_pwm, 10
        )
        self._e_stop_sub = self.create_subscription(
            Bool, "/e_stop", self._on_e_stop, 10
        )
        self._enable_srv = self.create_service(
            SetBool, "/fans/enable", self._on_enable
        )
        self._stop_srv = self.create_service(
            Trigger, "/fans/stop", self._on_stop
        )
        self._status_pub = self.create_publisher(
            Int32MultiArray, "/fans/status_pwm", 10
        )
        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._enabled_pub = self.create_publisher(
            Bool, "/fans/enabled", state_qos
        )

        timer_period = max(0.05, self._command_timeout / 2.0)
        self._watchdog_timer = self.create_timer(timer_period, self._watchdog)
        self._enabled_status_timer = self.create_timer(
            1.0 / enabled_status_rate, self._publish_enabled
        )
        self._publish_status()
        self._publish_enabled()
        self.get_logger().info(
            "双风扇控制已启动: "
            f"left=GPIO{self._left_gpio}, right=GPIO{self._right_gpio}, "
            f"PWM={self._range.minimum_us}-{self._range.maximum_us} us"
        )

    def _initialize_gpio(self) -> None:
        """初始化 lgpio 后端，并以最低脉宽同时解锁两个电调。"""
        from gpiozero import Servo
        from gpiozero.pins.lgpio import LGPIOFactory

        self._pin_factory = LGPIOFactory()
        servo_kwargs = {
            "initial_value": -1.0,
            "min_pulse_width": self._range.minimum_us / 1_000_000.0,
            "max_pulse_width": self._range.maximum_us / 1_000_000.0,
            "frame_width": self._frame_width,
            "pin_factory": self._pin_factory,
        }

        try:
            self._left_esc = Servo(self._left_gpio, **servo_kwargs)
            self._right_esc = Servo(self._right_gpio, **servo_kwargs)
            self._apply_pair(self._stop_pwm, self._stop_pwm)
        except Exception:
            self.close()
            raise

        self.get_logger().info(
            f"正在以 {self._stop_pwm} us 解锁两个电调，请确认风扇区域无人和杂物"
        )
        if self._arm_delay:
            time.sleep(self._arm_delay)

    def _set_output(self, index: int, pwm_us: int) -> None:
        safe_pwm = self._range.clamp(pwm_us)
        esc = self._left_esc if index == 0 else self._right_esc
        if esc is None:
            raise RuntimeError("风扇 GPIO 尚未初始化")
        esc.value = self._range.to_servo_value(safe_pwm)
        self._current_pwm[index] = safe_pwm

    def _apply_pair(self, left_pwm: int, right_pwm: int) -> None:
        self._set_output(0, left_pwm)
        self._set_output(1, right_pwm)

    def _accept_command(self) -> bool:
        if self._command_gate.accept(time.monotonic()):
            return True
        now = time.monotonic()
        if now - self._last_disabled_warning_time >= self._warning_throttle:
            self.get_logger().warn(
                "风扇处于停用状态；请调用 /fans/enable 后再发送油门"
            )
            self._last_disabled_warning_time = now
        return False

    def _on_pair_pwm(self, msg: Int32MultiArray) -> None:
        if len(msg.data) != 2:
            self.get_logger().error(
                "/fans/command_pwm 必须包含 [left_pwm, right_pwm] 两个整数"
            )
            return
        if not self._accept_command():
            return
        self._apply_pair(msg.data[0], msg.data[1])
        self._publish_status()

    def _on_e_stop(self, msg: Bool) -> None:
        if msg.data:
            self.get_logger().warn("收到系统 /e_stop，立即停止并停用两个风扇")
            self._command_gate.disable()
            self._safe_stop()
            self._publish_enabled()

    def _on_enable(
        self, request: SetBool.Request, response: SetBool.Response
    ) -> SetBool.Response:
        if request.data:
            self._safe_stop()
            self._command_gate.enable()
            self._last_disabled_warning_time = 0.0
            response.message = "风扇控制已启用，当前仍保持最低油门"
        else:
            self._command_gate.disable()
            self._safe_stop()
            response.message = "两个风扇已停止并停用"
        self._publish_enabled()
        response.success = True
        return response

    def _on_stop(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        self._command_gate.disable()
        self._safe_stop()
        self._publish_enabled()
        response.success = True
        response.message = "两个风扇已回到最低油门并锁存停用"
        return response

    def _watchdog(self) -> None:
        if self._command_gate.check_timeout(
            time.monotonic(), self._command_timeout
        ):
            self._safe_stop()
            self.get_logger().warn("风扇指令超时，已自动回到最低油门")

    def _safe_stop(self) -> None:
        try:
            self._apply_pair(self._stop_pwm, self._stop_pwm)
            self._publish_status()
        except Exception as exc:
            self.get_logger().error(f"风扇安全停止失败: {exc}")

    def _publish_status(self) -> None:
        if not hasattr(self, "_status_pub"):
            return
        msg = Int32MultiArray()
        msg.data = list(self._current_pwm)
        self._status_pub.publish(msg)

    def _publish_enabled(self) -> None:
        if not hasattr(self, "_enabled_pub"):
            return
        msg = Bool()
        msg.data = self._command_gate.enabled
        self._enabled_pub.publish(msg)

    def close(self) -> None:
        """关闭节点持有的硬件资源。"""
        try:
            if self._left_esc is not None and self._right_esc is not None:
                self._apply_pair(self._stop_pwm, self._stop_pwm)
        except Exception:
            pass
        for esc_name in ("_left_esc", "_right_esc"):
            esc = getattr(self, esc_name, None)
            if esc is not None:
                try:
                    esc.close()
                except Exception:
                    pass
                setattr(self, esc_name, None)
        if self._pin_factory is not None:
            try:
                self._pin_factory.close()
            except Exception:
                pass
            self._pin_factory = None

    def destroy_node(self) -> None:
        self.close()
        super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = DualFanController()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            # Launch 关闭时 ROS 上下文可能已经失效，此时继续向 rosout
            # 发布会产生 “publisher's context is invalid” 噪声。
            if rclpy.ok():
                node.get_logger().info("正在停止两个涵道风扇并释放 GPIO")
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
