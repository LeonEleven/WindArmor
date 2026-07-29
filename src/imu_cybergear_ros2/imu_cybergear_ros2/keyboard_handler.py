"""键盘控制：终端 raw 模式、按键读取、键盘主循环。"""

import os
import select
import sys
import termios
import threading
import time
from typing import Optional

from .controller_state import ControllerState


class KeyboardHandler:
    """键盘控制模块。

    职责：
      - 终端 raw 模式管理
      - 非阻塞按键读取
      - 键盘控制主循环（模式切换、手动控制、急停等）
      - 帮助文本生成

    参数：
        node: ROS2 LifecycleNode 实例。
        state_mgr: StateManager 实例。
        motor_mgr: MotorManager 实例。
        safety_monitor: SafetyMonitor 实例。
    """

    def __init__(self, node, state_mgr, motor_mgr, safety_monitor):
        self._node = node
        self._state = state_mgr
        self._motor_mgr = motor_mgr
        self._safety = safety_monitor
        self._thread = None
        self._old_terminal = None
        self._key_stream = None
        self._key_fd = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动键盘控制线程。"""
        self._thread = threading.Thread(
            target=self._keyboard_loop, daemon=True, name="keyboard-loop"
        )
        self._thread.start()

    def stop(self) -> None:
        """停止键盘控制线程并恢复终端。"""
        self._restore_terminal()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def print_help(self) -> None:
        """打印键盘控制帮助文本到日志。"""
        # 动态生成手动控制键位说明
        manual_lines = []
        for cfg in self._node._motor_configs:
            manual_lines.append(
                f"  {cfg.key_forward}/{cfg.key_backward} -> ID{cfg.motor_id} ({cfg.name})"
            )
        manual_text = "\n".join(manual_lines)

        # 动态生成电机选择说明（按 CAN ID）
        select_parts = [str(cfg.motor_id) for cfg in self._node._motor_configs]
        select_text = " / ".join(select_parts)

        help_text = (
            "\n"
            "=============== IMU + CyberGear 键盘控制 (v2.0) ===============\n"
            "[m] 切换模式 AUTO <-> MANUAL\n"
            "[z] IMU 姿态归零（当前姿态设为零点）\n"
            "[x] 设置全部电机当前位置为零点\n"
            "[h] 自动归零（按一次即可，到达后自动停止）\n"
            "[p] 发布当前状态汇总\n"
            "[空格] 急停全部电机 [r] 从急停恢复运控模式\n"
            "[q] 退出节点\n"
            "\n"
            f"电机选择（CAN ID）：\n"
            f"  {select_text} -> 选中对应电机\n"
            "\n"
            f"手动位置控制：\n"
            f"{manual_text}\n"
            "\n"
            "选中后操作：\n"
            "  + / = -> 当前选中电机加速\n"
            "  - / _ -> 当前选中电机减速\n"
            "  [     -> 当前选中电机转 +90°\n"
            "  ]     -> 当前选中电机转 -90°\n"
            "===============================================================\n"
        )
        self._node.get_logger().info(help_text)

    # ------------------------------------------------------------------
    # 终端管理
    # ------------------------------------------------------------------

    def _set_terminal_raw(self) -> None:
        """将终端设置为 raw 模式（非规范、无回显）。"""
        keyboard_device = self._node._keyboard_device
        if keyboard_device and os.path.exists(keyboard_device):
            self._key_stream = open(keyboard_device, "r", encoding="utf-8", buffering=1)
            self._key_fd = self._key_stream.fileno()
        elif sys.stdin.isatty():
            self._key_stream = sys.stdin
            self._key_fd = sys.stdin.fileno()
        else:
            raise RuntimeError("未找到可用的键盘 TTY 设备")

        self._old_terminal = termios.tcgetattr(self._key_fd)
        new_settings = termios.tcgetattr(self._key_fd)
        new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
        new_settings[6][termios.VMIN] = 0
        new_settings[6][termios.VTIME] = 0
        termios.tcsetattr(self._key_fd, termios.TCSADRAIN, new_settings)

    def _restore_terminal(self) -> None:
        """恢复终端到原始模式。"""
        if self._old_terminal is not None and self._key_fd is not None:
            try:
                termios.tcsetattr(self._key_fd, termios.TCSADRAIN, self._old_terminal)
            except Exception:
                pass
            self._old_terminal = None
        if self._key_stream is not None and self._key_stream is not sys.stdin:
            try:
                self._key_stream.close()
            except Exception:
                pass
        self._key_stream = None
        self._key_fd = None

    def _get_key(self) -> Optional[str]:
        """非阻塞读取单个按键字符。"""
        if self._key_stream is None:
            return None
        try:
            if select.select([self._key_stream], [], [], 0.01)[0]:
                return self._key_stream.read(1).lower()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # 键盘主循环
    # ------------------------------------------------------------------

    def _keyboard_loop(self) -> None:
        """键盘控制线程主循环。"""
        import rclpy

        try:
            self._set_terminal_raw()
        except Exception as exc:
            self._node.get_logger().warn(f"键盘控制不可用: {exc}")
            return

        try:
            while self._node._running:
                key = self._get_key()
                if key is None:
                    time.sleep(self._node._manual_period)
                    continue

                # ---- m: 切换模式 ----
                if key == "m":
                    if self._state.is_auto_running():
                        self._state.transition_to(ControllerState.MANUAL_RUNNING)
                        self._node.get_logger().info("已切换到 MANUAL（手动）模式")
                    elif self._state.is_manual_running():
                        self._state.transition_to(ControllerState.AUTO_RUNNING)
                        self._node.get_logger().info("已切换到 AUTO（自动）模式，IMU 姿态将驱动电机")
                    elif self._state.state == ControllerState.EMERGENCY_STOP:
                        self._node.get_logger().warn(
                            "当前为急停状态，无法切换模式。请先按 [r] 从急停恢复"
                        )
                    else:
                        self._node.get_logger().warn(
                            f"当前状态 {self._state.state_name} 不支持切换模式"
                        )
                    continue

                # ---- z: IMU 姿态归零 ----
                if key == "z":
                    success, message = self._node.set_imu_zero()
                    if success:
                        self._node.get_logger().info(message)
                    else:
                        self._node.get_logger().warn(message)
                    continue

                # ---- x: 全部电机机械零点 ----
                if key == "x":
                    self._motor_mgr.set_all_motor_zero_reference()
                    continue

                # ---- h: 全部电机回零 ----
                if key == "h":
                    self._motor_mgr.go_all_to_zero()
                    continue

                # ---- p: 发布状态汇总 ----
                if key == "p":
                    self._motor_mgr.publish_state_summary()
                    continue

                # ---- 空格: 急停 ----
                if key == " ":
                    self._safety.emergency_stop()
                    self._node.publish_system_emergency_stop()
                    continue

                # ---- r: 从急停恢复 ----
                if key == "r":
                    if self._state.state == ControllerState.EMERGENCY_STOP:
                        if self._motor_mgr.hold_current_targets_and_recover():
                            self._state.transition_to(ControllerState.MANUAL_RUNNING)
                    else:
                        self._motor_mgr.hold_current_targets_and_recover()
                    continue

                # ---- q: 退出 ----
                if key == "q":
                    self._node.get_logger().info("收到退出指令，正在停止全部电机...")
                    with self._node._lock:
                        for mid in self._node._motor_ids:
                            try:
                                self._node._driver.stop_motor(mid)
                            except Exception:
                                pass
                    self._node.get_logger().info("电机已停止，正在关闭节点...")
                    self._node._running = False
                    rclpy.shutdown()
                    break

                # ---- 1-N: 按 CAN ID 选中电机 ----
                if key.isdigit():
                    requested_id = int(key)
                    matched = None
                    for cfg in self._node._motor_configs:
                        if cfg.motor_id == requested_id:
                            matched = cfg
                            break
                    if matched is not None:
                        self._node._selected_motor_id = matched.motor_id
                        self._node.get_logger().info(
                            f"已选中电机 {matched.name} (ID{matched.motor_id})"
                        )
                    continue

                # ---- +/-: 调速 ----
                if key in ("+", "="):
                    self._motor_mgr.stop_auto_zero()
                    self._motor_mgr.change_motor_speed(self._node._selected_motor_id, +self._node._manual_speed_step)
                    continue
                if key in ("-", "_"):
                    self._motor_mgr.stop_auto_zero()
                    self._motor_mgr.change_motor_speed(self._node._selected_motor_id, -self._node._manual_speed_step)
                    continue

                # ---- [ / ]: 90度快捷位 ----
                if key == "[":
                    self._motor_mgr.stop_auto_zero()
                    self._motor_mgr.move_motor_to_90_deg(self._node._selected_motor_id, positive=True)
                    continue
                if key == "]":
                    self._motor_mgr.stop_auto_zero()
                    self._motor_mgr.move_motor_to_90_deg(self._node._selected_motor_id, positive=False)
                    continue

                # ---- 手动步进（需 MANUAL_RUNNING 状态） ----
                if key in self._node._key_to_motor:
                    if not self._state.is_manual_running():
                        continue
                    mid, direction = self._node._key_to_motor[key]
                    self._motor_mgr.stop_auto_zero()
                    self._motor_mgr.manual_step(mid, direction)

        finally:
            self._restore_terminal()
