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
from geometry_msgs.msg import Vector3Stamped
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn, State
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float64MultiArray, String, UInt64
from std_srvs.srv import Trigger, SetBool

from .controller_state import ControllerState, StateManager, public_control_mode
from .cybergear_driver import CyberGearDriver
from .imu_protocol import corrected_relative_roll_pitch
from .keyboard_handler import KeyboardHandler
from .motor_manager import MotorManager, clamp, deg_to_rad
from .motor_motion import (
    MotionParameters,
    auto_attitude_commands,
    validate_auto_attitude_gains,
    validate_motion_parameters,
)
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
        self.declare_parameter("relative_attitude_topic", "/imu/relative_roll_pitch")
        self.declare_parameter("imu_zero_generation_topic", "/imu/zero_generation")
        self.declare_parameter("motor_mode_topic", "/motors/control_mode")
        self.declare_parameter("motor_mode_publish_rate_hz", 5.0)
        self.declare_parameter("imu_zero_timeout_sec", 1.0)
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
        self.declare_parameter("default_speed", 10.0)
        self.declare_parameter("deadband_rad", 0.02)
        self.declare_parameter("auto_roll_gain", 1.0)
        self.declare_parameter("auto_pitch_gain", 1.0)
        self.declare_parameter("max_position_step", 0.4)
        self.declare_parameter("command_interval_sec", 0.02)
        self.declare_parameter("manual_motion_speed_rad_s", 4.0)
        self.declare_parameter("auto_motion_speed_rad_s", 4.0)
        self.declare_parameter("home_motion_speed_rad_s", 4.0)
        self.declare_parameter("motion_dt_max_sec", 0.05)
        self.declare_parameter("target_reached_tolerance_rad", 0.001)

        # 手动调速参数
        self.declare_parameter("manual_speed_min", 0.5)
        self.declare_parameter("manual_speed_max", 20.0)
        self.declare_parameter("manual_speed_step", 0.5)

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
        self.declare_parameter("manual_repeat_gap_sec", 0.8)
        self.declare_parameter("manual_repeat_dt_max_sec", 0.08)
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
        self._relative_attitude_pub = None
        self._imu_zero_generation_pub = None
        self._motor_mode_pub = None
        self._motor_mode_timer = None
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
        self._lock = threading.RLock()
        self._current_targets: Dict[int, float] = {}
        self._desired_targets: Dict[int, float] = {}
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
        self._imu_sequence = 0
        self._imu_zero_generation = 0
        self._imu_zero_sequence = 0

        # 控制参数（在 on_configure 中赋值）
        self._command_interval = 0.02
        self._motion_dt_max = 0.05
        self._target_reached_tolerance = 0.001
        self._manual_motion_speed = 4.0
        self._auto_motion_speed = 4.0
        self._home_motion_speed = 4.0
        self._manual_repeat_gap = 0.8
        self._manual_repeat_dt_max = 0.08
        self._motion_params = None
        self._roll_axis_sign = 1.0
        self._pitch_axis_sign = 1.0
        self._auto_roll_gain = 1.0
        self._auto_pitch_gain = 1.0
        self._imu_zero_timeout = 1.0

        self.get_logger().info("控制节点已创建（等待 configure）")

    # ==================================================================
    # 生命周期回调
    # ==================================================================

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """配置阶段：读取参数、创建驱动和 ROS 资源、连接电机。"""
        self.get_logger().info("控制节点正在配置...")

        # ---- 读取全部参数 ----
        imu_topic = self.get_parameter("imu_topic").get_parameter_value().string_value
        relative_attitude_topic = (
            self.get_parameter("relative_attitude_topic").get_parameter_value().string_value
        )
        imu_zero_generation_topic = (
            self.get_parameter("imu_zero_generation_topic").get_parameter_value().string_value
        )
        motor_mode_topic = (
            self.get_parameter("motor_mode_topic").get_parameter_value().string_value
        )
        motor_mode_publish_rate_hz = (
            self.get_parameter("motor_mode_publish_rate_hz")
            .get_parameter_value()
            .double_value
        )
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
        self._auto_roll_gain = (
            self.get_parameter("auto_roll_gain").get_parameter_value().double_value
        )
        self._auto_pitch_gain = (
            self.get_parameter("auto_pitch_gain").get_parameter_value().double_value
        )
        try:
            validate_auto_attitude_gains(
                self._auto_roll_gain, self._auto_pitch_gain
            )
        except ValueError as exc:
            self.get_logger().error(f"电机 AUTO 姿态增益非法: {exc}")
            return TransitionCallbackReturn.FAILURE
        self._max_step = self.get_parameter("max_position_step").get_parameter_value().double_value
        self._command_interval = self.get_parameter("command_interval_sec").get_parameter_value().double_value
        self._manual_motion_speed = (
            self.get_parameter("manual_motion_speed_rad_s").get_parameter_value().double_value
        )
        self._auto_motion_speed = (
            self.get_parameter("auto_motion_speed_rad_s").get_parameter_value().double_value
        )
        self._home_motion_speed = (
            self.get_parameter("home_motion_speed_rad_s").get_parameter_value().double_value
        )
        self._motion_dt_max = (
            self.get_parameter("motion_dt_max_sec").get_parameter_value().double_value
        )
        self._target_reached_tolerance = (
            self.get_parameter("target_reached_tolerance_rad")
            .get_parameter_value()
            .double_value
        )
        self._manual_speed_min = self.get_parameter("manual_speed_min").get_parameter_value().double_value
        self._manual_speed_max = self.get_parameter("manual_speed_max").get_parameter_value().double_value
        self._manual_speed_step = self.get_parameter("manual_speed_step").get_parameter_value().double_value
        self._manual_step_rad = deg_to_rad(
            self.get_parameter("manual_step_deg").get_parameter_value().double_value
        )
        self._manual_repeat_gap = (
            self.get_parameter("manual_repeat_gap_sec").get_parameter_value().double_value
        )
        self._manual_repeat_dt_max = (
            self.get_parameter("manual_repeat_dt_max_sec").get_parameter_value().double_value
        )
        manual_loop_hz = self.get_parameter("manual_loop_hz").get_parameter_value().double_value
        if not math.isfinite(manual_loop_hz) or manual_loop_hz <= 0.0:
            self.get_logger().error("manual_loop_hz 必须是大于 0 的有限值")
            return TransitionCallbackReturn.FAILURE
        self._manual_period = 1.0 / manual_loop_hz
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
        self._imu_zero_timeout = (
            self.get_parameter("imu_zero_timeout_sec").get_parameter_value().double_value
        )
        motor_status_topic = self.get_parameter("motor_status_topic").get_parameter_value().string_value
        if motor_mode_publish_rate_hz <= 0.0 or self._imu_zero_timeout <= 0.0:
            self.get_logger().error(
                "motor_mode_publish_rate_hz 和 imu_zero_timeout_sec 必须大于 0"
            )
            return TransitionCallbackReturn.FAILURE

        self._motion_params = MotionParameters(
            command_interval_sec=self._command_interval,
            motion_dt_max_sec=self._motion_dt_max,
            target_reached_tolerance_rad=self._target_reached_tolerance,
            manual_motion_speed_rad_s=self._manual_motion_speed,
            auto_motion_speed_rad_s=self._auto_motion_speed,
            home_motion_speed_rad_s=self._home_motion_speed,
            manual_step_rad=self._manual_step_rad,
            manual_repeat_gap_sec=self._manual_repeat_gap,
            manual_repeat_dt_max_sec=self._manual_repeat_dt_max,
            max_position_step=self._max_step,
            default_speed=self._default_speed,
            manual_speed_min=self._manual_speed_min,
            manual_speed_max=self._manual_speed_max,
            manual_speed_step=self._manual_speed_step,
        )
        try:
            validate_motion_parameters(self._motion_params)
        except ValueError as exc:
            self.get_logger().error(f"电机运动参数非法: {exc}")
            return TransitionCallbackReturn.FAILURE

        # ---- 初始化电机运行时状态 ----
        self._lock = threading.RLock()
        self._current_targets = {mid: 0.0 for mid in self._motor_ids}
        self._desired_targets = dict(self._current_targets)
        self._current_speeds = {mid: self._default_speed for mid in self._motor_ids}
        self._selected_motor_id = 1 if 1 in self._motor_ids else self._motor_ids[0]
        self._motor_feedback = {}
        self._motor_protection_flags = {mid: False for mid in self._motor_ids}
        self._init_complete = False
        self._last_target_change_time = {mid: 0.0 for mid in self._motor_ids}
        self._last_imu_time = 0.0
        self._imu_sequence = 0
        self._imu_zero_sequence = 0

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
        self._state_mgr = StateManager(
            self,
            state_change_callback=self._on_control_state_changed,
        )
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
        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._relative_attitude_pub = self.create_publisher(
            Vector3Stamped, relative_attitude_topic, 20
        )
        self._imu_zero_generation_pub = self.create_publisher(
            UInt64, imu_zero_generation_topic, state_qos
        )
        self._motor_mode_pub = self.create_publisher(
            String, motor_mode_topic, state_qos
        )
        self._motor_mode_timer = self.create_timer(
            1.0 / motor_mode_publish_rate_hz,
            self._publish_control_mode,
        )
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
        self._publish_control_mode()
        self._publish_imu_zero_generation()
        self._motor_mgr.start_motion_timer()

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
        self._publish_control_mode()
        self._motor_mgr.stop_motion_timer()
        self._keyboard.stop()
        self.get_logger().info("控制节点已停用")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """清理阶段：停止电机、关闭驱动、销毁 ROS 资源。"""
        self.get_logger().info("控制节点正在清理...")

        if self._motor_mgr is not None:
            self._motor_mgr.stop_motion_timer()

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
        if self._motor_mode_timer is not None:
            self.destroy_timer(self._motor_mode_timer)
        for pub in [
            self._motor_status_pub,
            self._system_e_stop_pub,
            self._relative_attitude_pub,
            self._imu_zero_generation_pub,
            self._motor_mode_pub,
        ]:
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
        self._relative_attitude_pub = None
        self._imu_zero_generation_pub = None
        self._motor_mode_pub = None
        self._motor_mode_timer = None
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
        response.success, response.message = self.set_imu_zero()
        if response.success:
            self.get_logger().info(response.message)
        else:
            self.get_logger().warn(response.message)
        return response

    def set_imu_zero(self) -> Tuple[bool, str]:
        """以最近一帧有效姿态设置统一零点，并发布零点代次。"""
        if not self._is_active:
            return False, "控制节点未激活，未执行 IMU 归零"
        now = time.monotonic()
        with self._lock:
            if self._last_imu_time <= 0.0 or now - self._last_imu_time > self._imu_zero_timeout:
                return False, "IMU 数据无效或已超时，未执行归零"
            self._imu_zero_roll = self._latest_roll
            self._imu_zero_pitch = self._latest_pitch
            self._imu_zero_generation += 1
            self._imu_zero_sequence = self._imu_sequence
            roll_deg = math.degrees(self._imu_zero_roll)
            pitch_deg = math.degrees(self._imu_zero_pitch)
        self._publish_imu_zero_generation()
        return (
            True,
            f"IMU 已归零: roll={roll_deg:.2f}°, pitch={pitch_deg:.2f}°",
        )

    def _publish_imu_zero_generation(self) -> None:
        if self._imu_zero_generation_pub is None:
            return
        msg = UInt64()
        msg.data = self._imu_zero_generation
        self._imu_zero_generation_pub.publish(msg)

    def _on_control_state_changed(self, _state: ControllerState) -> None:
        if self._motor_mgr is not None:
            self._motor_mgr.on_control_state_changed(_state)
        self._publish_control_mode()

    def _publish_control_mode(self) -> None:
        if self._motor_mode_pub is None or self._state_mgr is None:
            return
        msg = String()
        msg.data = public_control_mode(
            self._state_mgr.state,
            active=self._is_active,
        )
        self._motor_mode_pub.publish(msg)

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
        values = [float(value) for value in msg.data]
        if not all(math.isfinite(value) for value in values):
            self.get_logger().error(
                "/motors/manual_targets 所有元素都必须是有限值，整条消息已拒绝"
            )
            return
        targets = dict(zip(self._motor_ids, values))
        try:
            targets = self._motor_mgr.set_manual_targets(targets)
        except ValueError as exc:
            self.get_logger().error(f"拒绝 /motors/manual_targets: {exc}")
            return
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
        self._publish_control_mode()

        if self._motor_mgr is not None:
            self._motor_mgr.stop_motion_timer()

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

        if self._motor_mode_timer is not None:
            try:
                self.destroy_timer(self._motor_mode_timer)
            except Exception:
                pass
        for pub in [
            self._motor_status_pub,
            self._system_e_stop_pub,
            self._relative_attitude_pub,
            self._imu_zero_generation_pub,
            self._motor_mode_pub,
        ]:
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
        """IMU 数据订阅回调：解析姿态并更新 AUTO 期望目标。"""
        if not self._is_active or not self._running:
            return

        now = time.monotonic()
        try:
            with self._lock:
                roll, pitch, roll_rel, pitch_rel = corrected_relative_roll_pitch(
                    msg.orientation.x,
                    msg.orientation.y,
                    msg.orientation.z,
                    msg.orientation.w,
                    roll_axis_sign=self._roll_axis_sign,
                    pitch_axis_sign=self._pitch_axis_sign,
                    zero_roll=self._imu_zero_roll,
                    zero_pitch=self._imu_zero_pitch,
                )
                self._latest_roll = roll
                self._latest_pitch = pitch
                self._last_imu_time = now
                self._imu_sequence += 1
        except ValueError as exc:
            self.get_logger().warn(f"忽略无效 IMU 四元数: {exc}")
            return

        relative_msg = Vector3Stamped()
        relative_msg.header = msg.header
        relative_msg.vector.x = roll_rel
        relative_msg.vector.y = pitch_rel
        relative_msg.vector.z = 0.0
        self._relative_attitude_pub.publish(relative_msg)

        # MANUAL 模式也持续更新实时姿态，确保键盘 z 和 /imu/set_zero
        # 使用的是真实当前姿态，而不是启动时的默认 0。
        if not self._state_mgr.is_auto_running():
            return

        roll_command, pitch_command = auto_attitude_commands(
            roll_rel,
            pitch_rel,
            deadband_rad=self._deadband,
            roll_gain=self._auto_roll_gain,
            pitch_gain=self._auto_pitch_gain,
        )
        alpha_deg = math.degrees(roll_command)
        beta_deg = math.degrees(pitch_command)

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

        self._motor_mgr.set_auto_targets(targets)


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
