"""ROS2 IMU-电机控制项目主控制节点（LifecycleNode 版本）。

功能概述：
  1. 读取 IMU 姿态数据，驱动 CyberGear 电机进行姿态平衡控制（支持任意数量电机）。
  2. 支持 AUTO（IMU 闭环跟随）和 MANUAL（键盘手动控制）两种操作模式。
  3. 内置完整的控制状态机，统一管理节点生命周期。
  4. 看门狗机制监控 IMU 数据时效性，超时自动切换手动模式。
  5. 实时监控电机反馈（温度/电流/位置误差），多层保护机制。
  6. 三重急停通道：键盘 [空格]、话题 /e_stop、服务 /e_stop。
  7. 断线自动重连，异常全面日志记录。

子模块分工：
  - controller_state.py  — 状态枚举与状态管理器
  - motor_manager.py     — 电机连接、目标写入、自动归零、手动控制
  - safety_monitor.py    — 看门狗、电机反馈监控、急停系统
  - keyboard_handler.py  — 终端 raw 模式、按键读取、键盘主循环

ROS2 生命周期状态：
  unconfigured → on_configure → inactive → on_activate → active
  active → on_deactivate → inactive → on_cleanup → unconfigured

发布话题：
  /motor/status (std_msgs/String) — 电机连接状态及实时反馈

订阅话题：
  /imu/data_raw (sensor_msgs/Imu) — IMU 姿态数据
  /e_stop (std_msgs/Bool) — 急停指令
  /motors/manual_targets (std_msgs/Float64MultiArray) — MANUAL 模式绝对目标

服务：
  /e_stop        (std_srvs/Trigger) — 急停服务
  /enable_motor  (std_srvs/SetBool) — 远程启停服务
  /imu/set_zero  (std_srvs/Trigger) — 将当前 IMU 姿态设为零点
  /motors/set_zero (std_srvs/Trigger) — 将全部电机当前位置设为机械零点

键盘控制（需 enable_keyboard=True）：
  [m] 切换 AUTO/MANUAL          [z] IMU 姿态归零
  [x] 全部电机设为零点          [h] 自动归零（持续回零，到达停止）
  [p] 发布当前状态汇总
  [空格] 急停                   [r] 从急停恢复
  [q] 退出
  手动控制键位由 YAML 中 motor_keys_forward/motor_keys_backward 配置
  调速：+/-（取消归零）         90度：[ / ]（取消归零）
"""

import math
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

import rclpy
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn, State
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float64MultiArray, String
from std_srvs.srv import Trigger, SetBool

from .controller_state import ControllerState, StateManager
from .cybergear_driver import CyberGearDriver
from .keyboard_handler import KeyboardHandler
from .motor_manager import MotorManager, clamp, deg_to_rad
from .safety_monitor import SafetyMonitor


# ---------------------------------------------------------------------------
# 电机配置数据类
# ---------------------------------------------------------------------------

@dataclass
class MotorConfig:
    """单台电机的配置信息。"""
    name: str            # 电机名称（如 "left_lift"）
    motor_id: int        # CAN ID
    sign: float          # 方向符号修正（+1.0 或 -1.0）
    limit_min: float     # 软限位下限（rad）
    limit_max: float     # 软限位上限（rad）
    control_axis: str    # IMU 控制轴："roll_left" / "roll_right" / "pitch"
    key_forward: str     # 键盘前进键
    key_backward: str    # 键盘后退键


# ---------------------------------------------------------------------------
# 主控制节点
# ---------------------------------------------------------------------------

class ImuMotorControllerNode(LifecycleNode):
    """IMU 驱动的 CyberGear 电机控制节点（LifecycleNode）。

    实现完整的控制状态机、通信看门狗、电机反馈监控、多层保护、急停和自动重连。
    具体逻辑委托给 StateManager、MotorManager、SafetyMonitor、KeyboardHandler。
    """

    # ---- 构造 ----

    def __init__(self):
        super().__init__("imu_motor_controller_node")

        # ================================================================
        # 声明全部参数（在 unconfigured 状态下可用）
        # ================================================================

        # ROS 与通信后端参数
        self.declare_parameter("imu_topic", "/imu/data_raw")
        self.declare_parameter("control_backend", "socketcan_hat")
        self.declare_parameter("master_id", 253)

        # USB-CAN 参数
        self.declare_parameter("usb_port", "/dev/ttyUSB0")
        self.declare_parameter("usb_baud", 921600)
        # 历史兼容参数
        self.declare_parameter("motor_port", "/dev/ttyUSB0")
        self.declare_parameter("motor_baud", 921600)

        # SocketCAN 参数
        self.declare_parameter("can_channel", "can10")
        self.declare_parameter("can_bustype", "socketcan")

        # 电机 ID 映射（旧版标量参数，已废弃，仅供向后兼容）
        self.declare_parameter("left_lift_motor_id", 4)
        self.declare_parameter("left_pitch_motor_id", 3)
        self.declare_parameter("right_pitch_motor_id", 2)
        self.declare_parameter("right_lift_motor_id", 1)

        # 电机列表配置（新方式，支持任意数量电机）
        self.declare_parameter("motor_names", ["left_lift", "left_pitch", "right_pitch", "right_lift"])
        self.declare_parameter("motor_ids", [4, 3, 2, 1])
        self.declare_parameter("motor_signs", [-1.0, 1.0, -1.0, 1.0])
        self.declare_parameter("motor_limits_min", [-1.57, -1.57, -1.57, 0.0])
        self.declare_parameter("motor_limits_max", [0.0, 1.57, 1.57, 1.57])
        self.declare_parameter("motor_control_axes", ["roll_left", "pitch", "pitch", "roll_right"])
        self.declare_parameter("motor_keys_forward", ["d", "w", "k", "l"])
        self.declare_parameter("motor_keys_backward", ["a", "s", "i", "j"])

        # 控制参数
        self.declare_parameter("default_speed", 5.0)
        self.declare_parameter("deadband_rad", 0.02)
        self.declare_parameter("max_position_step", 0.15)
        self.declare_parameter("command_interval_sec", 0.02)

        # 手动调速参数
        self.declare_parameter("manual_speed_min", 0.1)
        self.declare_parameter("manual_speed_max", 5.0)
        self.declare_parameter("manual_speed_step", 0.1)

        # 轴向符号修正
        self.declare_parameter("roll_axis_sign", 1.0)
        self.declare_parameter("pitch_axis_sign", 1.0)

        # 电机方向符号（旧版标量参数，已废弃，仅供向后兼容）
        self.declare_parameter("left_lift_sign", -1.0)
        self.declare_parameter("right_lift_sign", 1.0)
        self.declare_parameter("left_pitch_sign", 1.0)
        self.declare_parameter("right_pitch_sign", -1.0)

        # 键盘控制参数
        self.declare_parameter("enable_keyboard", True)
        self.declare_parameter("keyboard_device", "/dev/tty")
        self.declare_parameter("manual_step_deg", 3.0)
        self.declare_parameter("manual_loop_hz", 50.0)

        # 各电机目标位置限幅（rad）
        self.declare_parameter("m1_min", 0.0)
        self.declare_parameter("m1_max", 1.57)
        self.declare_parameter("m2_min", -1.57)
        self.declare_parameter("m2_max", 1.57)
        self.declare_parameter("m3_min", -1.57)
        self.declare_parameter("m3_max", 1.57)
        self.declare_parameter("m4_min", -1.57)
        self.declare_parameter("m4_max", 0.0)

        # P0 安全参数
        self.declare_parameter("watchdog_timeout_ms", 200)
        self.declare_parameter("motor_temp_limit_degC", 80.0)
        self.declare_parameter("motor_temp_critical_degC", 90.0)
        self.declare_parameter("motor_current_limit_a", 5.0)
        self.declare_parameter("position_error_threshold_rad", 0.3)
        self.declare_parameter("warning_throttle_sec", 2.0)
        self.declare_parameter("reconnect_on_disconnect", True)
        self.declare_parameter("motor_status_topic", "/motor/status")

        # ================================================================
        # 初始化实例变量（资源在 on_configure 中创建）
        # ================================================================

        self._is_active = False
        self._running = True

        # 驱动与 ROS 资源
        self._driver = None
        self._motor_status_pub = None
        self._system_e_stop_pub = None
        self._sub = None
        self._e_stop_sub = None
        self._manual_targets_sub = None
        self._e_stop_srv = None
        self._enable_motor_srv = None
        self._imu_zero_srv = None
        self._motor_zero_srv = None

        # 子模块
        self._state_mgr: StateManager = None
        self._motor_mgr: MotorManager = None
        self._safety: SafetyMonitor = None
        self._keyboard: KeyboardHandler = None

        # 电机参数（在 on_configure 中从参数读取）
        self._motor_configs: List[MotorConfig] = []
        self._motor_ids: List[int] = []
        self._limits: Dict[int, Tuple[float, float]] = {}
        self._key_to_motor: Dict[str, Tuple[int, float]] = {}

        # 电机运行时状态（供子模块通过 self._node.xxx 访问）
        self._lock = threading.Lock()
        self._current_targets: Dict[int, float] = {}
        self._current_speeds: Dict[int, float] = {}
        self._selected_motor_id = 1
        self._motor_feedback = {}
        self._motor_protection_flags: Dict[int, bool] = {}
        self._init_complete = False
        self._last_target_change_time: Dict[int, float] = {}

        # IMU 运行时状态
        self._imu_zero_roll = 0.0
        self._imu_zero_pitch = 0.0
        self._latest_roll = 0.0
        self._latest_pitch = 0.0
        self._last_imu_time = 0.0
        self._last_command_time = 0.0

        # 控制参数（在 on_configure 中赋值）
        self._command_interval = 0.02
        self._roll_axis_sign = 1.0
        self._pitch_axis_sign = 1.0

        self.get_logger().info("控制节点已创建（等待 configure）")

    # ==================================================================
    # 生命周期回调
    # ==================================================================

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """配置阶段：读取参数、创建驱动和 ROS 资源、连接电机。"""
        self.get_logger().info("控制节点正在配置...")

        # ---- 读取全部参数 ----
        imu_topic = self.get_parameter("imu_topic").get_parameter_value().string_value
        backend = self.get_parameter("control_backend").get_parameter_value().string_value
        master_id = self.get_parameter("master_id").get_parameter_value().integer_value

        # 兼容历史参数名
        legacy_port = self.get_parameter("motor_port").get_parameter_value().string_value
        legacy_baud = self.get_parameter("motor_baud").get_parameter_value().integer_value
        usb_port = self.get_parameter("usb_port").get_parameter_value().string_value
        usb_baud = self.get_parameter("usb_baud").get_parameter_value().integer_value
        usb_port = usb_port if usb_port else legacy_port
        usb_baud = usb_baud if usb_baud else legacy_baud

        can_channel = self.get_parameter("can_channel").get_parameter_value().string_value
        can_bustype = self.get_parameter("can_bustype").get_parameter_value().string_value

        # ---- 读取电机列表配置 ----
        motor_names = list(self.get_parameter("motor_names").get_parameter_value().string_array_value)
        motor_ids = list(self.get_parameter("motor_ids").get_parameter_value().integer_array_value)
        motor_signs = list(self.get_parameter("motor_signs").get_parameter_value().double_array_value)
        motor_limits_min = list(self.get_parameter("motor_limits_min").get_parameter_value().double_array_value)
        motor_limits_max = list(self.get_parameter("motor_limits_max").get_parameter_value().double_array_value)
        motor_control_axes = list(self.get_parameter("motor_control_axes").get_parameter_value().string_array_value)
        motor_keys_fwd = list(self.get_parameter("motor_keys_forward").get_parameter_value().string_array_value)
        motor_keys_bwd = list(self.get_parameter("motor_keys_backward").get_parameter_value().string_array_value)

        n = len(motor_ids)
        if not (len(motor_names) == len(motor_signs) == len(motor_limits_min) ==
                len(motor_limits_max) == len(motor_control_axes) ==
                len(motor_keys_fwd) == len(motor_keys_bwd) == n):
            self.get_logger().error(
                f"电机列表参数长度不一致: names={len(motor_names)}, ids={n}, "
                f"signs={len(motor_signs)}, limits_min={len(motor_limits_min)}, "
                f"limits_max={len(motor_limits_max)}, axes={len(motor_control_axes)}, "
                f"keys_fwd={len(motor_keys_fwd)}, keys_bwd={len(motor_keys_bwd)}"
            )
            return TransitionCallbackReturn.FAILURE

        self._motor_configs = [
            MotorConfig(
                name=motor_names[i],
                motor_id=motor_ids[i],
                sign=motor_signs[i],
                limit_min=motor_limits_min[i],
                limit_max=motor_limits_max[i],
                control_axis=motor_control_axes[i],
                key_forward=motor_keys_fwd[i],
                key_backward=motor_keys_bwd[i],
            )
            for i in range(n)
        ]
        self._motor_ids = [cfg.motor_id for cfg in self._motor_configs]
        self._limits = {cfg.motor_id: (cfg.limit_min, cfg.limit_max) for cfg in self._motor_configs}
        self._key_to_motor = {}
        for cfg in self._motor_configs:
            self._key_to_motor[cfg.key_forward] = (cfg.motor_id, +1.0)
            self._key_to_motor[cfg.key_backward] = (cfg.motor_id, -1.0)

        # 控制参数
        self._default_speed = self.get_parameter("default_speed").get_parameter_value().double_value
        self._deadband = self.get_parameter("deadband_rad").get_parameter_value().double_value
        self._max_step = self.get_parameter("max_position_step").get_parameter_value().double_value
        self._command_interval = self.get_parameter("command_interval_sec").get_parameter_value().double_value
        self._manual_speed_min = self.get_parameter("manual_speed_min").get_parameter_value().double_value
        self._manual_speed_max = self.get_parameter("manual_speed_max").get_parameter_value().double_value
        self._manual_speed_step = self.get_parameter("manual_speed_step").get_parameter_value().double_value
        self._manual_step_rad = deg_to_rad(
            self.get_parameter("manual_step_deg").get_parameter_value().double_value
        )
        self._manual_period = 1.0 / self.get_parameter("manual_loop_hz").get_parameter_value().double_value
        self._keyboard_device = self.get_parameter("keyboard_device").get_parameter_value().string_value
        self._watchdog_timeout_s = self.get_parameter("watchdog_timeout_ms").get_parameter_value().integer_value / 1000.0
        self._position_error_threshold = (
            self.get_parameter("position_error_threshold_rad").get_parameter_value().double_value
        )
        self._warning_throttle_sec = max(
            0.0,
            self.get_parameter("warning_throttle_sec").get_parameter_value().double_value,
        )
        self._roll_axis_sign = self.get_parameter("roll_axis_sign").get_parameter_value().double_value
        self._pitch_axis_sign = self.get_parameter("pitch_axis_sign").get_parameter_value().double_value
        motor_status_topic = self.get_parameter("motor_status_topic").get_parameter_value().string_value

        # ---- 初始化电机运行时状态 ----
        self._lock = threading.Lock()
        self._current_targets = {mid: 0.0 for mid in self._motor_ids}
        self._current_speeds = {mid: self._default_speed for mid in self._motor_ids}
        self._selected_motor_id = 1 if 1 in self._motor_ids else self._motor_ids[0]
        self._motor_feedback = {}
        self._motor_protection_flags = {mid: False for mid in self._motor_ids}
        self._init_complete = False
        self._last_target_change_time = {mid: 0.0 for mid in self._motor_ids}
        self._last_command_time = 0.0

        # ---- 创建驱动 ----
        self._driver = CyberGearDriver(
            backend=backend,
            master_id=master_id,
            usb_port=usb_port,
            usb_baud=usb_baud,
            can_channel=can_channel,
            can_bustype=can_bustype,
        )

        # ---- 创建子模块 ----
        self._state_mgr = StateManager(self)
        self._motor_mgr = MotorManager(self, self._state_mgr)
        self._safety = SafetyMonitor(self, self._state_mgr, self._motor_mgr)
        self._keyboard = KeyboardHandler(
            self, self._state_mgr, self._motor_mgr, self._safety
        )

        # 状态转换时自动停止自动归零
        self._state_mgr._stop_auto_zero_callback = self._motor_mgr.stop_auto_zero

        # 注册电机反馈回调
        self._driver.register_feedback_callback(self._safety.on_motor_feedback)

        # ---- 创建 ROS 资源 ----
        self._motor_status_pub = self.create_publisher(String, motor_status_topic, 10)
        self._system_e_stop_pub = self.create_publisher(Bool, "/e_stop", 10)
        self._sub = self.create_subscription(Imu, imu_topic, self._imu_callback, 20)
        self._e_stop_sub = self.create_subscription(
            Bool, "/e_stop", self._safety.on_e_stop_topic, 10
        )
        self._manual_targets_sub = self.create_subscription(
            Float64MultiArray,
            "/motors/manual_targets",
            self._on_manual_targets,
            10,
        )
        self._e_stop_srv = self.create_service(
            Trigger, "/e_stop", self._safety.on_e_stop_service
        )
        self._enable_motor_srv = self.create_service(
            SetBool, "/enable_motor", self._safety.on_enable_motor_service
        )
        self._imu_zero_srv = self.create_service(
            Trigger, "/imu/set_zero", self._on_imu_zero_service
        )
        self._motor_zero_srv = self.create_service(
            Trigger, "/motors/set_zero", self._on_motor_zero_service
        )

        # ---- 连接电机并初始化 ----
        self._state_mgr.transition_to(ControllerState.INITIALIZING)
        if not self._motor_mgr.connect_and_init_motors():
            self.get_logger().error("电机初始化失败，配置失败")
            return TransitionCallbackReturn.FAILURE

        # ---- 启动看门狗 ----
        watchdog_period = max(0.01, self._watchdog_timeout_s / 2.0)
        self._safety.start_watchdog(watchdog_period)

        self.get_logger().info(
            f"控制节点配置完成: backend={self._driver.backend_name}, "
            f"imu_topic={imu_topic}"
        )
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """激活阶段：启动键盘线程。"""
        self.get_logger().info("控制节点正在激活...")
        self._is_active = True
        self._running = True

        if self.get_parameter("enable_keyboard").get_parameter_value().bool_value:
            self._keyboard.start()

        self._keyboard.print_help()
        self.get_logger().info(
            f"控制节点已激活: state={self._state_mgr.state_name}, "
            f"选中电机: ID{self._selected_motor_id}"
        )
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """停用阶段：停止键盘线程和自动归零。"""
        self.get_logger().info("控制节点正在停用...")
        self._is_active = False
        self._running = False
        self._motor_mgr.stop_auto_zero()
        self._keyboard.stop()
        self.get_logger().info("控制节点已停用")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """清理阶段：停止电机、关闭驱动、销毁 ROS 资源。"""
        self.get_logger().info("控制节点正在清理...")

        # 停止电机并关闭驱动
        if self._driver is not None:
            for mid in self._motor_ids:
                try:
                    self._driver.stop_motor(mid)
                except Exception:
                    pass
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

        # 停止看门狗
        self._safety.stop_watchdog()

        # 销毁 ROS 资源
        for pub in [self._motor_status_pub, self._system_e_stop_pub]:
            if pub is not None:
                self.destroy_publisher(pub)
        for sub in [self._sub, self._e_stop_sub, self._manual_targets_sub]:
            if sub is not None:
                self.destroy_subscription(sub)
        for srv in [
            self._e_stop_srv,
            self._enable_motor_srv,
            self._imu_zero_srv,
            self._motor_zero_srv,
        ]:
            if srv is not None:
                self.destroy_service(srv)

        self._motor_status_pub = None
        self._system_e_stop_pub = None
        self._sub = None
        self._e_stop_sub = None
        self._manual_targets_sub = None
        self._e_stop_srv = None
        self._enable_motor_srv = None
        self._imu_zero_srv = None
        self._motor_zero_srv = None

        # 重置内部状态
        self._motor_configs = []
        self._motor_ids = []
        self._limits = {}
        self._key_to_motor = {}
        self._motor_feedback = {}
        self._motor_protection_flags = {}
        self._state_mgr = None
        self._motor_mgr = None
        self._safety = None
        self._keyboard = None

        self.get_logger().info("控制节点清理完成")
        return TransitionCallbackReturn.SUCCESS

    def _on_imu_zero_service(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        """将当前实时 IMU 姿态设为控制零点。"""
        if not self._is_active:
            response.success = False
            response.message = "控制节点未激活"
            return response
        if time.monotonic() - self._last_imu_time > 1.0:
            response.success = False
            response.message = "IMU 数据已超时，未执行归零"
            return response
        with self._lock:
            self._imu_zero_roll = self._latest_roll
            self._imu_zero_pitch = self._latest_pitch
            roll_deg = math.degrees(self._imu_zero_roll)
            pitch_deg = math.degrees(self._imu_zero_pitch)
        self.get_logger().info(
            f"IMU 姿态归零已完成: roll={roll_deg:.2f}°, pitch={pitch_deg:.2f}°"
        )
        response.success = True
        response.message = (
            f"IMU 已归零: roll={roll_deg:.2f}°, pitch={pitch_deg:.2f}°"
        )
        return response

    def _on_motor_zero_service(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        """将全部电机的当前位置设为机械零点。"""
        if not self._is_active:
            response.success = False
            response.message = "控制节点未激活"
            return response
        if not self._state_mgr.is_manual_running():
            response.success = False
            response.message = "请先切换到 MANUAL 模式再设置电机零点"
            return response
        response.success = self._motor_mgr.set_all_motor_zero_reference()
        response.message = (
            "全部电机当前位置已设为零点"
            if response.success
            else "部分电机设置零点失败，请检查日志"
        )
        return response

    def _on_manual_targets(self, msg: Float64MultiArray) -> None:
        """在 MANUAL 模式按 motor_ids 顺序接收各电机绝对目标（rad）。"""
        if not self._is_active or not self._state_mgr.is_manual_running():
            self.get_logger().warn(
                "忽略 /motors/manual_targets：控制节点未激活或不在 MANUAL 模式"
            )
            return
        if len(msg.data) != len(self._motor_ids):
            self.get_logger().error(
                "/motors/manual_targets 长度必须与 motor_ids 一致："
                f"期望 {len(self._motor_ids)}，收到 {len(msg.data)}"
            )
            return
        targets = {
            motor_id: float(msg.data[index])
            for index, motor_id in enumerate(self._motor_ids)
        }
        with self._lock:
            self._motor_mgr.apply_targets(targets)
        target_text = ", ".join(
            f"ID{motor_id}={targets[motor_id]:.3f}"
            for motor_id in self._motor_ids
        )
        self.get_logger().info(f"收到 MANUAL 电机目标(rad): {target_text}")

    def publish_system_emergency_stop(self) -> None:
        """发布系统级急停，让电机与风扇使用同一安全通道。"""
        if self._system_e_stop_pub is None:
            return
        msg = Bool()
        msg.data = True
        self._system_e_stop_pub.publish(msg)

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """关闭阶段：最终清理。"""
        self.get_logger().info("控制节点正在关闭...")
        self._is_active = False
        self._running = False

        if self._motor_mgr is not None:
            self._motor_mgr.stop_auto_zero()

        if self._safety is not None:
            self._safety.emergency_stop()

        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

        if self._keyboard is not None:
            self._keyboard.stop()

        for pub in [self._motor_status_pub, self._system_e_stop_pub]:
            if pub is not None:
                try:
                    self.destroy_publisher(pub)
                except Exception:
                    pass
        for sub in [self._sub, self._e_stop_sub, self._manual_targets_sub]:
            if sub is not None:
                try:
                    self.destroy_subscription(sub)
                except Exception:
                    pass
        for srv in [
            self._e_stop_srv,
            self._enable_motor_srv,
            self._imu_zero_srv,
            self._motor_zero_srv,
        ]:
            if srv is not None:
                try:
                    self.destroy_service(srv)
                except Exception:
                    pass

        self.get_logger().info("控制节点已关闭")
        return TransitionCallbackReturn.SUCCESS

    # ==================================================================
    # IMU 数据回调（核心控制逻辑，保留在主节点）
    # ==================================================================

    def _imu_callback(self, msg: Imu) -> None:
        """IMU 数据订阅回调：解析姿态、计算目标位置、写入电机。"""
        self._last_imu_time = time.monotonic()

        if not self._is_active or not self._running:
            return

        try:
            from .imu_protocol import euler_from_quaternion

            roll, pitch, _ = euler_from_quaternion(
                msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w
            )
        except Exception as exc:
            self.get_logger().error(f"解析 IMU 四元数时发生异常: {exc}")
            return

        roll *= self._roll_axis_sign
        pitch *= self._pitch_axis_sign
        self._latest_roll = roll
        self._latest_pitch = pitch

        # MANUAL 模式也持续更新实时姿态，确保键盘 z 和 /imu/set_zero
        # 使用的是真实当前姿态，而不是启动时的默认 0。
        if not self._state_mgr.is_auto_running():
            return

        now = time.monotonic()
        if now - self._last_command_time < self._command_interval:
            return

        with self._lock:
            roll_rel = roll - self._imu_zero_roll
            pitch_rel = pitch - self._imu_zero_pitch

            if abs(roll_rel) < self._deadband:
                roll_rel = 0.0
            if abs(pitch_rel) < self._deadband:
                pitch_rel = 0.0

            alpha_deg = clamp(math.degrees(roll_rel), -90.0, 90.0)
            beta_deg = clamp(math.degrees(pitch_rel), -90.0, 90.0)

            targets = {}
            for cfg in self._motor_configs:
                if cfg.control_axis == "roll_left":
                    deg = clamp(max(0.0, -alpha_deg), 0.0, 90.0)
                elif cfg.control_axis == "roll_right":
                    deg = clamp(max(0.0, alpha_deg), 0.0, 90.0)
                elif cfg.control_axis == "pitch":
                    deg = beta_deg
                else:
                    deg = 0.0
                targets[cfg.motor_id] = cfg.sign * deg_to_rad(deg)

            self._motor_mgr.apply_targets(targets)
            self._last_command_time = now


# ======================================================================
# 入口
# ======================================================================

def main(args=None):
    """节点入口函数。"""
    rclpy.init(args=args)
    node = None
    try:
        node = ImuMotorControllerNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        if node is not None:
            node.get_logger().error(f"节点运行时发生未处理异常: {exc}")
    finally:
        if rclpy.ok():
            rclpy.shutdown()
