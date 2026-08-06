"""双涵道风扇键盘控制节点；应在独立终端运行。"""

import os
import select
import sys
import termios
import time
import tty
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int32MultiArray, String
from std_srvs.srv import SetBool


class _KeyReader:
    """非阻塞地组装终端按键序列，同时允许主循环持续发送心跳。"""

    _ARROW_KEYS = {
        "A": "\x1b[A",
        "B": "\x1b[B",
        "C": "\x1b[C",
        "D": "\x1b[D",
    }

    def __init__(self, escape_timeout: float = 3.0) -> None:
        self._buffer = ""
        self._escape_started_at: Optional[float] = None
        self._escape_timeout = max(0.1, escape_timeout)

    def _pop_key(self) -> str:
        if not self._buffer:
            return ""

        if self._buffer[0] != "\x1b":
            key, self._buffer = self._buffer[0], self._buffer[1:]
            return key

        now = time.monotonic()
        if self._escape_started_at is None:
            self._escape_started_at = now

        if len(self._buffer) == 1:
            if now - self._escape_started_at < self._escape_timeout:
                return ""
            self._buffer = self._buffer[1:]
            self._escape_started_at = None
            return "\x1b"

        introducer = self._buffer[1]
        if introducer not in ("[", "O"):
            self._buffer = self._buffer[1:]
            self._escape_started_at = None
            return "\x1b"

        # 支持普通 CSI（ESC [ A）及应用光标模式（ESC O A）。
        # CSI 还可能带参数，例如 ESC [ 1 ; 2 A，因此按终止字符解析。
        end_index = None
        for index, char in enumerate(self._buffer[2:16], start=2):
            if "@" <= char <= "~":
                end_index = index
                break
        if end_index is None:
            return ""

        sequence = self._buffer[: end_index + 1]
        self._buffer = self._buffer[end_index + 1 :]
        self._escape_started_at = None
        return self._ARROW_KEYS.get(sequence[-1], sequence)

    def get_key(self, timeout: float = 0.1) -> str:
        key = self._pop_key()
        if key:
            return key

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            chunk = os.read(sys.stdin.fileno(), 64)
            self._buffer += chunk.decode("latin-1")
        return self._pop_key()


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
        self._manual_input_allowed = False
        self._pwm_pub = self.create_publisher(Int32MultiArray, "/fans/pwm", 10)
        self._e_stop_pub = self.create_publisher(Bool, "/e_stop", 10)
        self._enable_client = self.create_client(SetBool, "/fans/enable")
        self._control_state_sub = self.create_subscription(
            String,
            "/fans/control_state",
            self._on_control_state,
            10,
        )

    def publish(self) -> None:
        msg = Int32MultiArray()
        msg.data = list(self._values)
        self._pwm_pub.publish(msg)

    def adjust(self, delta: int) -> bool:
        if not self._manual_input_allowed:
            self._values = [self._minimum, self._minimum]
            return False
        for index in self._selection:
            self._values[index] = max(
                self._minimum, min(self._maximum, self._values[index] + delta)
            )
        return True

    def _on_control_state(self, msg: String) -> None:
        """安全状态清除本地旧油门；停止基线后才允许用户调节。"""
        self._manual_input_allowed = msg.data in (
            "MANUAL_WAITING",
            "MANUAL_ACTIVE",
        )
        if not self._manual_input_allowed:
            self._values = [self._minimum, self._minimum]

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
    key_reader = _KeyReader()
    old_settings = termios.tcgetattr(sys.stdin)

    print(
        "\nWindArmor 双风扇键盘控制\n"
        "[1]左 [2]右 [3]双路  [↑/↓]增减  [s]双路最低油门\n"
        "[空格]系统急停（电机+风扇） [r]仅重新启用底层风扇 [q]退出\n"
    )

    try:
        tty.setraw(sys.stdin.fileno())
        while rclpy.ok():
            key = key_reader.get_key()
            display_changed = False
            if key == "1":
                node._selection = (0,)
                display_changed = True
            elif key == "2":
                node._selection = (1,)
                display_changed = True
            elif key == "3":
                node._selection = (0, 1)
                display_changed = True
            elif key in ("\x1b[A", "+", "="):
                display_changed = node.adjust(node._step)
            elif key in ("\x1b[B", "-", "_"):
                display_changed = node.adjust(-node._step)
            elif key.lower() == "s":
                node.stop()
                display_changed = True
            elif key == " ":
                node.system_emergency_stop()
                display_changed = True
            elif key.lower() == "r":
                node.enable_fans()
                display_changed = True
            elif key.lower() == "q" or key == "\x03":
                break
            node.publish()
            rclpy.spin_once(node, timeout_sec=0.0)
            if display_changed:
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
