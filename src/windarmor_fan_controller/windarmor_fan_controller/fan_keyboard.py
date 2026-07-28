"""双涵道风扇键盘控制节点；应在独立终端运行。"""

import select
import sys
import termios
import tty
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int32MultiArray
from std_srvs.srv import SetBool


def _get_key(timeout: float = 0.1) -> str:
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return ""
    key = sys.stdin.read(1)
    if key == "\x1b" and select.select([sys.stdin], [], [], 0.02)[0]:
        key += sys.stdin.read(1)
        if select.select([sys.stdin], [], [], 0.02)[0]:
            key += sys.stdin.read(1)
    return key


class FanKeyboard(Node):
    """发布双路 PWM，并持续发送心跳以满足风扇看门狗。"""

    def __init__(self) -> None:
        super().__init__("fan_keyboard")
        self.declare_parameter("min_pwm_us", 800)
        self.declare_parameter("max_pwm_us", 2200)
        self.declare_parameter("step_pwm_us", 20)
        self._minimum = int(self.get_parameter("min_pwm_us").value)
        self._maximum = int(self.get_parameter("max_pwm_us").value)
        self._step = int(self.get_parameter("step_pwm_us").value)
        self._values = [self._minimum, self._minimum]
        self._selection = (0, 1)
        self._pwm_pub = self.create_publisher(Int32MultiArray, "/fans/pwm", 10)
        self._e_stop_pub = self.create_publisher(Bool, "/e_stop", 10)
        self._enable_client = self.create_client(SetBool, "/fans/enable")

    def publish(self) -> None:
        msg = Int32MultiArray()
        msg.data = list(self._values)
        self._pwm_pub.publish(msg)

    def adjust(self, delta: int) -> None:
        for index in self._selection:
            self._values[index] = max(
                self._minimum, min(self._maximum, self._values[index] + delta)
            )

    def stop(self) -> None:
        self._values = [self._minimum, self._minimum]
        self.publish()

    def system_emergency_stop(self) -> None:
        self.stop()
        msg = Bool()
        msg.data = True
        self._e_stop_pub.publish(msg)

    def enable_fans(self) -> None:
        if not self._enable_client.wait_for_service(timeout_sec=0.2):
            self.get_logger().warn("/fans/enable 服务不可用")
            return
        request = SetBool.Request()
        request.data = True
        self._enable_client.call_async(request)

    @property
    def display(self) -> str:
        selected = {0: "左", 1: "右"}.get(
            self._selection[0], "双"
        ) if len(self._selection) == 1 else "双"
        return (
            f"\r左={self._values[0]} us 右={self._values[1]} us "
            f"当前选择={selected}      "
        )


def main(args: Optional[list[str]] = None) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("fan_keyboard 必须在交互式终端中运行")

    rclpy.init(args=args)
    node = FanKeyboard()
    old_settings = termios.tcgetattr(sys.stdin)

    print(
        "\nWindArmor 双风扇键盘控制\n"
        "[1]左 [2]右 [3]双路  [↑/↓]增减  [s]双路最低油门\n"
        "[空格]系统急停（电机+风扇） [r]重新启用风扇 [q]退出\n"
    )

    try:
        tty.setraw(sys.stdin.fileno())
        while rclpy.ok():
            key = _get_key()
            if key == "1":
                node._selection = (0,)
            elif key == "2":
                node._selection = (1,)
            elif key == "3":
                node._selection = (0, 1)
            elif key in ("\x1b[A", "+", "="):
                node.adjust(node._step)
            elif key in ("\x1b[B", "-", "_"):
                node.adjust(-node._step)
            elif key.lower() == "s":
                node.stop()
            elif key == " ":
                node.system_emergency_stop()
            elif key.lower() == "r":
                node.enable_fans()
            elif key.lower() == "q" or key == "\x03":
                break
            node.publish()
            rclpy.spin_once(node, timeout_sec=0.0)
            print(node.display, end="", flush=True)
    finally:
        node.stop()
        rclpy.spin_once(node, timeout_sec=0.05)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print("\n已发送双风扇最低油门指令。")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
