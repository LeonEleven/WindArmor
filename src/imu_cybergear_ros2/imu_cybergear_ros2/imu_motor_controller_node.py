"""ROS2 IMU-电机控制项目主控制节点（LifecycleNode 版本）。

功能概述：
  1. 读取 IMU 姿态数据，驱动 CyberGear 电机进行姿态平衡控制（支持任意数量电机）。
  2. 支持 AUTO（IMU 闭环跟随）和 MANUAL（键盘手动控制）两种操作模式。
  3. 内置完整的控制状态机，统一管理节点生命周期。
  4. 看门狗机制监控 IMU 数据时效性，超时自动切换手动模式。
  5. 实时监控电机反馈（合法性/故障位/温度/位置误差），多层保护机制。
  6. 三重急停通道：键盘 [空格]、话题 /e_stop、服务 /e_stop。
  7. 初始连接重试，以及 transport fault 锁存和 transport-only 运行期受控重连。

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
  /motors/feedback (windarmor_interfaces/MotorFeedbackArray) — 只读结构化快照

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
from typing import Callable, Dict, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn, State
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float64MultiArray, String, UInt64
from std_srvs.srv import Trigger, SetBool
from windarmor_interfaces.msg import (
    FlightCommandEnvelope,
    MotorFeedback,
    MotorFeedbackArray,
    MotorSafetyState,
    OwnershipState,
)
from windarmor_interfaces.srv import (
    CommitFlightOwnership,
    PrepareFlightOwnership,
    RevokeFlightOwnership,
)

from .controller_state import (
    ControllerState,
    StateManager,
    TransitionOutcome,
    TransitionReason,
    TransitionSource,
    public_control_mode,
)
from .cybergear_driver import CyberGearDriver
from .imu_protocol import corrected_relative_roll_pitch
from .keyboard_handler import KeyboardHandler
from .motor_config import (
    PARAMETER_NAMES,
    MotorChannelConfig,
    MotorNodeConfig,
    build_motor_node_config,
)
from .motor_manager import MotorManager, clamp, deg_to_rad
from .motor_motion import auto_attitude_commands
from .safety_monitor import SafetyMonitor
from .structured_feedback import build_structured_feedback
from .structured_safety import build_motor_safety_snapshot
from .transport_recovery import (
    TransportEvent,
    TransportEventType,
    TransportRecoveryCoordinator,
    TransportRecoveryState,
)


class ImuMotorControllerNode(LifecycleNode):
    """IMU 驱动的 CyberGear 电机控制节点（LifecycleNode）。

    实现完整的控制状态机、通信看门狗、电机反馈监控、多层保护和急停。
    具体逻辑委托给 StateManager、MotorManager、SafetyMonitor、KeyboardHandler。
    """

    def __init__(
        self,
        *,
        driver_factory: Callable[..., object] = CyberGearDriver,
        sleep_fn: Callable[[float], None] = time.sleep,
        source_epoch_fn: Callable[[], int] = time.monotonic_ns,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ):
        source_epoch = source_epoch_fn()
        if (
            isinstance(source_epoch, bool)
            or not isinstance(source_epoch, int)
            or not 0 < source_epoch <= (2**64 - 1)
        ):
            raise ValueError("motor safety source epoch must be a positive uint64")
        super().__init__("imu_motor_controller_node")
        # 测试可注入完全内存化 fake；生产入口仍使用 CyberGearDriver。
        self._driver_factory = driver_factory
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._motor_safety_source_epoch = source_epoch

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
        self.declare_parameter("flight_motion_speed_rad_s", 4.0)
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

        # Safety thresholds cover stale commands/feedback, thermal/fault latches,
        # position error and transport recovery. Units are encoded in parameter names;
        # motor_current_limit_a is reserved because 0x02 feedback has no numeric current.
        self.declare_parameter("watchdog_timeout_ms", 200)
        self.declare_parameter("motor_temp_limit_degC", 80.0)
        self.declare_parameter("motor_temp_critical_degC", 90.0)
        self.declare_parameter("motor_current_limit_a", 5.0)
        self.declare_parameter("motor_invalid_feedback_limit", 3)
        self.declare_parameter("motor_feedback_timeout_sec", 0.0)
        self.declare_parameter("motor_feedback_startup_grace_sec", 3.0)
        self.declare_parameter("motor_feedback_check_rate_hz", 10.0)
        self.declare_parameter("motor_feedback_acquisition_rate_hz", 10.0)
        self.declare_parameter("position_error_threshold_rad", 0.3)
        self.declare_parameter("warning_throttle_sec", 2.0)
        self.declare_parameter("reconnect_on_disconnect", True)
        self.declare_parameter("reconnect_max_attempts", 30)
        self.declare_parameter("reconnect_initial_delay_sec", 0.5)
        self.declare_parameter("reconnect_max_delay_sec", 10.0)
        self.declare_parameter("reconnect_backoff_multiplier", 1.5)
        self.declare_parameter("motor_status_topic", "/motor/status")
        self.declare_parameter(
            "motor_feedback_structured_topic", "/motors/feedback"
        )
        self.declare_parameter("motor_safety_state_topic", "/motors/safety_state")
        self.declare_parameter("motor_ownership_state_topic", "/motors/ownership_state")
        self.declare_parameter("motor_flight_prepare_service", "/motors/flight_ownership/prepare")
        self.declare_parameter("motor_flight_commit_service", "/motors/flight_ownership/commit")
        self.declare_parameter("motor_flight_revoke_service", "/motors/flight_ownership/revoke")
        self.declare_parameter("flight_command_topic", "/flight_control/command")
        self.declare_parameter("motor_flight_handoff_timeout_sec", 1.5)
        self.declare_parameter("motor_flight_command_timeout_sec", 0.25)
        self.declare_parameter("motor_feedback_publish_rate_hz", 10.0)
        self.declare_parameter("motor_feedback_observer_freshness_sec", 0.5)

        # ================================================================
        # 初始化实例变量（资源在 on_configure 中创建）
        # ================================================================

        self._is_active = False
        self._running = True

        # 驱动与 ROS 资源
        self._driver = None
        self._motor_status_pub = None
        self._motor_feedback_structured_pub = None
        self._motor_safety_state_pub = None
        self._motor_ownership_state_pub = None
        self._flight_command_sub = None
        self._motor_flight_prepare_srv = None
        self._motor_flight_commit_srv = None
        self._motor_flight_revoke_srv = None
        self._motor_feedback_structured_timer = None
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
        self._transport_recovery: Optional[TransportRecoveryCoordinator] = None

        # 电机参数（在 on_configure 中从参数读取）
        self._config: Optional[MotorNodeConfig] = None
        self._motor_configs: List[MotorChannelConfig] = []
        self._motor_ids: List[int] = []
        self._limits: Dict[int, Tuple[float, float]] = {}
        self._key_to_motor: Dict[str, Tuple[int, float]] = {}

        # 电机运行时状态（供子模块通过 self._node.xxx 访问）
        self._lock = threading.RLock()
        # 锁顺序：绝不在持有 _lock 时等待 _driver_io_lock。
        # 每次只串行化单个驱动调用，使急停最多等待当前一次 I/O。
        self._driver_io_lock = threading.Lock()
        self._release_lock = threading.Lock()
        self._current_targets: Dict[int, float] = {}
        self._desired_targets: Dict[int, float] = {}
        self._current_speeds: Dict[int, float] = {}
        self._selected_motor_id = 1
        self._motor_feedback = {}
        self._motor_feedback_received_at: Dict[int, float] = {}
        self._motor_feedback_generations: Dict[int, int] = {}
        self._motor_feedback_structured_sequence = 0
        # This sequence spans lifecycle reconfigure within the same process so
        # observers never accept an old safety snapshot as a new one.
        self._motor_safety_state_sequence = 1
        self._motor_ownership_state_sequence = 1
        self._motor_protection_flags: Dict[int, bool] = {}
        self._motor_temperature_warning_flags: Dict[int, bool] = {}
        self._motor_safety_fault_active = False
        self._motor_safety_fault_snapshot = None
        self._init_complete = False
        self._last_target_change_time: Dict[int, float] = {}
        self._command_failure_counts: Dict[int, int] = {}
        self._command_fault_active = False
        self._fault_stop_batch_claimed = False
        self._transport_fault_active = False
        self._transport_fault_snapshot: Optional[TransportEvent] = None
        self._reconnect_on_disconnect = True
        self._reconnect_policy = None
        self._motor_feedback_acquisition_rate_hz = 10.0

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
        self._flight_motion_speed = 4.0
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
        """先完整校验配置，再创建驱动、ROS 资源并连接电机。"""
        self.get_logger().info("控制节点正在配置...")
        # 读取、兼容解析和全部纯函数校验必须先于任何驱动或 ROS 资源创建。
        try:
            raw_values = {
                name: self.get_parameter(name).value for name in PARAMETER_NAMES
            }
            config = build_motor_node_config(raw_values)
        except Exception as exc:
            self.get_logger().error(f"电机配置非法: {exc}")
            # 配置异常发生在 INITIALIZING 前；显式记录允许的 UNINITIALIZED→ERROR。
            self._state_mgr = StateManager(
                self,
                state_change_callback=self._on_control_state_changed,
            )
            self._state_mgr.transition_to(
                ControllerState.ERROR,
                reason=TransitionReason.CONFIGURE_FAILURE,
                source=TransitionSource.LIFECYCLE,
            )
            self._release_resources(
                reason="configuration_validation_failed",
                attempt_motor_stop=False,
            )
            return TransitionCallbackReturn.FAILURE

        self._apply_validated_config(config)
        if config.communication.fallback_parameters:
            names = ", ".join(config.communication.fallback_parameters)
            self.get_logger().warn(
                f"USB-CAN 使用已废弃兼容参数 {names}；请迁移到 usb_port/usb_baud"
            )

        try:
            # ---- 创建驱动 ----
            communication = config.communication
            self._driver = self._driver_factory(
                backend=communication.backend,
                master_id=communication.master_id,
                usb_port=communication.usb_port,
                usb_baud=communication.usb_baud,
                can_channel=communication.can_channel,
                can_bustype=communication.can_bustype,
            )

            # ---- 创建子模块 ----
            self._state_mgr = StateManager(
                self,
                state_change_callback=self._on_control_state_changed,
            )
            start_result = self._state_mgr.transition_to(
                ControllerState.INITIALIZING,
                reason=TransitionReason.CONFIGURE_START,
                source=TransitionSource.LIFECYCLE,
            )
            if start_result.outcome is not TransitionOutcome.CHANGED:
                raise RuntimeError("无法进入 INITIALIZING，拒绝继续配置")
            self._motor_mgr = MotorManager(self, self._state_mgr)
            self._safety = SafetyMonitor(
                self,
                self._state_mgr,
                self._motor_mgr,
                monotonic_fn=self._monotonic,
            )
            self._keyboard = KeyboardHandler(
                self, self._state_mgr, self._motor_mgr, self._safety
            )
            self._state_mgr.register_stop_auto_zero_callback(
                self._motor_mgr.stop_auto_zero
            )
            self._transport_recovery = TransportRecoveryCoordinator(
                reconnect_enabled=self._reconnect_on_disconnect,
                policy=self._reconnect_policy,
                backend_name=self._driver.backend_name,
                generation_fn=self._transport_connection_generation,
                stop_for_fault=self._stop_for_transport_fault,
                close_transport=self._close_transport_for_recovery,
                connect_once=self._connect_transport_once,
                event_sink=self._on_transport_recovery_event,
            )
            self._driver.register_feedback_callback(self._safety.on_motor_feedback)
            if hasattr(self._driver, "register_feedback_error_callback"):
                self._driver.register_feedback_error_callback(
                    self._on_driver_feedback_error
                )
            if hasattr(self._driver, "register_transport_event_callback"):
                self._driver.register_transport_event_callback(
                    self._on_driver_transport_event
                )

            # ---- 创建 ROS 资源 ----
            ros_config = config.ros
            self._motor_status_pub = self.create_publisher(
                String, ros_config.motor_status_topic, 10
            )
            self._motor_feedback_structured_pub = self.create_publisher(
                MotorFeedbackArray,
                ros_config.motor_feedback_structured_topic,
                10,
            )
            self._motor_feedback_structured_timer = self.create_timer(
                1.0 / ros_config.motor_feedback_publish_rate_hz,
                self._publish_structured_motor_feedback,
            )
            self._system_e_stop_pub = self.create_publisher(Bool, "/e_stop", 10)
            state_qos = QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._motor_safety_state_pub = self.create_publisher(
                MotorSafetyState,
                ros_config.motor_safety_state_topic,
                state_qos,
            )
            self._motor_ownership_state_pub = self.create_publisher(
                OwnershipState,
                ros_config.motor_ownership_state_topic,
                state_qos,
            )
            self._relative_attitude_pub = self.create_publisher(
                Vector3Stamped, ros_config.relative_attitude_topic, 20
            )
            self._imu_zero_generation_pub = self.create_publisher(
                UInt64, ros_config.imu_zero_generation_topic, state_qos
            )
            self._motor_mode_pub = self.create_publisher(
                String, ros_config.motor_mode_topic, state_qos
            )
            self._motor_mode_timer = self.create_timer(
                1.0 / ros_config.motor_mode_publish_rate_hz,
                self._publish_control_mode,
            )
            self._sub = self.create_subscription(
                Imu, ros_config.imu_topic, self._imu_callback, 20
            )
            self._e_stop_sub = self.create_subscription(
                Bool, "/e_stop", self._safety.on_e_stop_topic, 10
            )
            self._manual_targets_sub = self.create_subscription(
                Float64MultiArray,
                "/motors/manual_targets",
                self._on_manual_targets,
                10,
            )
            self._flight_command_sub = self.create_subscription(
                FlightCommandEnvelope,
                ros_config.flight_command_topic,
                self._on_flight_command,
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
            self._motor_flight_prepare_srv = self.create_service(
                PrepareFlightOwnership,
                ros_config.motor_flight_prepare_service,
                self._on_flight_prepare,
            )
            self._motor_flight_commit_srv = self.create_service(
                CommitFlightOwnership,
                ros_config.motor_flight_commit_service,
                self._on_flight_commit,
            )
            self._motor_flight_revoke_srv = self.create_service(
                RevokeFlightOwnership,
                ros_config.motor_flight_revoke_service,
                self._on_flight_revoke,
            )

            # ---- 连接电机并初始化 ----
            if not self._motor_mgr.connect_and_init_motors():
                touched = list(reversed(self._motor_mgr.init_touched_motor_ids))
                stage = self._motor_mgr.current_init_stage
                self.get_logger().error(
                    f"电机初始化失败，配置回滚: stage={stage}, touched={touched}"
                )
                self._release_resources(
                    reason=f"configure_failed:{stage}",
                    attempt_motor_stop=bool(touched),
                    motor_ids=touched,
                )
                return TransitionCallbackReturn.FAILURE

            # ---- 启动看门狗 ----
            if self._watchdog_timeout_s > 0.0:
                watchdog_period = max(0.01, self._watchdog_timeout_s / 2.0)
                self._safety.start_watchdog(watchdog_period)
            self.get_logger().warn(
                "motor_current_limit_a 当前仅为保留参数：0x02 反馈没有数值电流；"
                "软件依赖电机固件过流故障 bit，且不会从 torque 推导电流"
            )
            driver_backend = self._driver.backend_name
        except Exception as exc:
            self.get_logger().error(f"配置阶段发生异常，开始事务式回滚: {exc}")
            if self._state_mgr is None:
                self._state_mgr = StateManager(
                    self,
                    state_change_callback=self._on_control_state_changed,
                )
            self._state_mgr.transition_to(
                ControllerState.ERROR,
                reason=TransitionReason.CONFIGURE_FAILURE,
                source=TransitionSource.LIFECYCLE,
            )
            touched = (
                list(reversed(self._motor_mgr.init_touched_motor_ids))
                if self._motor_mgr is not None
                else []
            )
            self._release_resources(
                reason="configure_exception",
                attempt_motor_stop=bool(touched),
                motor_ids=touched,
            )
            return TransitionCallbackReturn.FAILURE

        self.get_logger().info(
            f"控制节点配置完成: backend={driver_backend}, "
            f"imu_topic={config.ros.imu_topic}"
        )
        return TransitionCallbackReturn.SUCCESS

    def _apply_validated_config(self, config: MotorNodeConfig) -> None:
        """把已通过纯函数校验的配置提交为运行时内存状态。"""
        self._config = config
        self._motor_configs = list(config.channels)
        self._motor_ids = [channel.motor_id for channel in config.channels]
        self._limits = {
            channel.motor_id: (channel.limit_min, channel.limit_max)
            for channel in config.channels
        }
        self._key_to_motor = {}
        for channel in config.channels:
            self._key_to_motor[channel.key_forward] = (channel.motor_id, +1.0)
            self._key_to_motor[channel.key_backward] = (channel.motor_id, -1.0)

        motion = config.control.motion
        self._motion_params = motion
        self._default_speed = motion.default_speed
        self._deadband = config.control.deadband_rad
        self._auto_roll_gain = config.control.auto_roll_gain
        self._auto_pitch_gain = config.control.auto_pitch_gain
        self._max_step = motion.max_position_step
        self._command_interval = motion.command_interval_sec
        self._manual_motion_speed = motion.manual_motion_speed_rad_s
        self._auto_motion_speed = motion.auto_motion_speed_rad_s
        self._flight_motion_speed = motion.flight_motion_speed_rad_s
        self._home_motion_speed = motion.home_motion_speed_rad_s
        self._motion_dt_max = motion.motion_dt_max_sec
        self._target_reached_tolerance = motion.target_reached_tolerance_rad
        self._manual_speed_min = motion.manual_speed_min
        self._manual_speed_max = motion.manual_speed_max
        self._manual_speed_step = motion.manual_speed_step
        self._manual_step_rad = motion.manual_step_rad
        self._manual_repeat_gap = motion.manual_repeat_gap_sec
        self._manual_repeat_dt_max = motion.manual_repeat_dt_max_sec
        self._manual_period = 1.0 / config.keyboard.manual_loop_hz
        self._keyboard_device = config.keyboard.device
        self._watchdog_timeout_s = config.safety.watchdog_timeout_ms / 1000.0
        self._motor_temp_limit_deg_c = config.safety.motor_temp_limit_deg_c
        self._motor_temp_critical_deg_c = config.safety.motor_temp_critical_deg_c
        self._motor_invalid_feedback_limit = (
            config.safety.motor_invalid_feedback_limit
        )
        self._motor_feedback_timeout_sec = config.safety.motor_feedback_timeout_sec
        self._motor_feedback_startup_grace_sec = (
            config.safety.motor_feedback_startup_grace_sec
        )
        self._motor_feedback_check_rate_hz = (
            config.safety.motor_feedback_check_rate_hz
        )
        self._motor_feedback_acquisition_rate_hz = (
            config.safety.motor_feedback_acquisition_rate_hz
        )
        self._position_error_threshold = (
            config.safety.position_error_threshold_rad
        )
        self._warning_throttle_sec = config.safety.warning_throttle_sec
        self._motor_flight_command_timeout_sec = (
            config.safety.motor_flight_command_timeout_sec
        )
        self._motor_flight_handoff_timeout_sec = (
            config.safety.motor_flight_handoff_timeout_sec
        )
        self._reconnect_on_disconnect = config.safety.reconnect_on_disconnect
        self._reconnect_policy = config.safety.reconnect_policy
        self._roll_axis_sign = config.control.roll_axis_sign
        self._pitch_axis_sign = config.control.pitch_axis_sign
        self._imu_zero_timeout = config.ros.imu_zero_timeout_sec

        self._lock = threading.RLock()
        self._current_targets = {}
        self._desired_targets = {}
        self._current_speeds = {}
        self._selected_motor_id = 1 if 1 in self._motor_ids else self._motor_ids[0]
        self._motor_feedback = {}
        self._motor_feedback_received_at = {}
        self._motor_feedback_generations = {}
        self._motor_feedback_structured_sequence = 0
        self._motor_protection_flags = {
            motor_id: False for motor_id in self._motor_ids
        }
        self._motor_temperature_warning_flags = {
            motor_id: False for motor_id in self._motor_ids
        }
        self._motor_safety_fault_active = False
        self._motor_safety_fault_snapshot = None
        self._init_complete = False
        self._last_target_change_time = {
            motor_id: 0.0 for motor_id in self._motor_ids
        }
        self._command_failure_counts = {
            motor_id: 0 for motor_id in self._motor_ids
        }
        self._command_fault_active = False
        self._fault_stop_batch_claimed = False
        self._transport_fault_active = False
        self._transport_fault_snapshot = None
        self._last_imu_time = 0.0
        self._imu_sequence = 0
        self._imu_zero_sequence = 0

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """激活阶段：启动键盘线程。"""
        self.get_logger().info("控制节点正在激活...")
        if (
            self._transport_recovery is not None
            and not self._transport_fault_active
        ):
            self._transport_recovery.allow_requests_if_idle()
        # 先建立本次激活的新鲜度时间原点；节点仍 inactive，后台反馈不会抢先计入。
        self._safety.start_feedback_monitor()
        self._is_active = True
        self._running = True
        self._publish_control_mode()
        self._publish_imu_zero_generation()
        self._motor_mgr.start_motion_timer()
        self._motor_mgr.start_feedback_acquisition()

        if self._config.keyboard.enabled:
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
        recovery_cancelled = True
        if self._transport_recovery is not None:
            recovery_cancelled = self._transport_recovery.disallow_and_cancel()
            if not recovery_cancelled:
                self.get_logger().error("停用时 transport recovery worker 未及时退出")
        self._publish_control_mode()
        self._motor_mgr.stop_feedback_acquisition()
        self._motor_mgr.stop_motion_timer()
        self._safety.stop_feedback_monitor()
        self._keyboard.stop()
        self.get_logger().info("控制节点已停用")
        return (
            TransitionCallbackReturn.SUCCESS
            if recovery_cancelled
            else TransitionCallbackReturn.FAILURE
        )

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """清理阶段：使用统一流程尽力释放全部资源。"""
        self.get_logger().info("控制节点正在清理...")
        released = self._release_resources(reason="cleanup", attempt_motor_stop=True)
        return (
            TransitionCallbackReturn.SUCCESS
            if released
            else TransitionCallbackReturn.FAILURE
        )

    def _release_resources(
        self,
        *,
        reason: str,
        attempt_motor_stop: bool,
        motor_ids: Optional[List[int]] = None,
    ) -> bool:
        """统一、幂等、可诊断的 lifecycle/配置失败资源释放流程。"""
        failures: List[str] = []

        def attempt(stage: str, action: Callable[[], object]) -> None:
            try:
                result = action()
                if result is False:
                    raise RuntimeError("操作返回 false")
            except Exception as exc:
                failures.append(f"{stage}: {exc}")
                self.get_logger().error(
                    f"资源释放失败: reason={reason}, stage={stage}, error={exc}"
                )

        with self._release_lock:
            self._is_active = False
            self._running = False
            attempt("publish_disabled_mode", self._publish_control_mode)

            motor_mgr = self._motor_mgr
            safety = self._safety
            keyboard = self._keyboard
            transport_recovery = self._transport_recovery

            # No close/release operation may race a worker that can reopen the
            # transport.  Cancellation precedes every driver I/O below.
            if transport_recovery is not None:
                attempt(
                    "cancel_transport_recovery",
                    transport_recovery.disallow_and_cancel,
                )

            if motor_mgr is not None:
                attempt(
                    "stop_feedback_acquisition",
                    motor_mgr.stop_feedback_acquisition,
                )
                attempt("stop_motion_timer", motor_mgr.stop_motion_timer)
            if keyboard is not None:
                attempt("stop_keyboard", keyboard.stop)
            if safety is not None:
                attempt("stop_watchdog", safety.stop_watchdog)
                attempt("stop_feedback_monitor", safety.stop_feedback_monitor)

            ids_to_stop = list(self._motor_ids if motor_ids is None else motor_ids)
            if attempt_motor_stop and self._driver is not None:
                if motor_mgr is not None:
                    attempt(
                        "stop_motors",
                        lambda: motor_mgr.stop_motors_best_effort(
                            reason=reason, motor_ids=ids_to_stop
                        ),
                    )
                else:
                    for mid in ids_to_stop:
                        def stop_one(motor_id=mid):
                            with self._driver_io_lock:
                                if self._driver is None:
                                    raise RuntimeError("电机驱动不可用")
                                self._driver.stop_motor(motor_id)

                        attempt(f"stop_motor:ID{mid}", stop_one)

            driver = self._driver
            self._driver = None
            if driver is not None:
                if hasattr(driver, "clear_feedback_callbacks"):
                    def clear_driver_callbacks() -> None:
                        with self._driver_io_lock:
                            driver.clear_feedback_callbacks()

                    attempt("clear_driver_callbacks", clear_driver_callbacks)

                if hasattr(driver, "clear_transport_event_callbacks"):
                    def clear_transport_callbacks() -> None:
                        with self._driver_io_lock:
                            driver.clear_transport_event_callbacks()

                    attempt("clear_transport_callbacks", clear_transport_callbacks)

                def close_driver() -> None:
                    with self._driver_io_lock:
                        driver.close()

                attempt("close_driver", close_driver)

            if transport_recovery is not None:
                transport_recovery.clear_callbacks()

            self._destroy_ros_resource(
                "_motor_mode_timer", "timer:motor_mode", self.destroy_timer, failures, reason
            )
            self._destroy_ros_resource(
                "_motor_feedback_structured_timer",
                "timer:motor_feedback_structured",
                self.destroy_timer,
                failures,
                reason,
            )
            for attr in (
                "_motor_status_pub",
                "_motor_feedback_structured_pub",
                "_motor_safety_state_pub",
                "_motor_ownership_state_pub",
                "_system_e_stop_pub",
                "_relative_attitude_pub",
                "_imu_zero_generation_pub",
                "_motor_mode_pub",
            ):
                self._destroy_ros_resource(
                    attr, f"publisher:{attr}", self.destroy_publisher, failures, reason
                )
            for attr in (
                "_sub", "_e_stop_sub", "_manual_targets_sub", "_flight_command_sub"
            ):
                self._destroy_ros_resource(
                    attr, f"subscription:{attr}", self.destroy_subscription, failures, reason
                )
            for attr in (
                "_e_stop_srv",
                "_enable_motor_srv",
                "_imu_zero_srv",
                "_motor_zero_srv",
                "_motor_flight_prepare_srv",
                "_motor_flight_commit_srv",
                "_motor_flight_revoke_srv",
            ):
                self._destroy_ros_resource(
                    attr, f"service:{attr}", self.destroy_service, failures, reason
                )

            with self._lock:
                self._init_complete = False
                self._command_fault_active = False
                self._fault_stop_batch_claimed = False
                self._transport_fault_active = False
                self._transport_fault_snapshot = None
                self._motor_safety_fault_active = False
                self._motor_safety_fault_snapshot = None
                self._current_targets = {}
                self._desired_targets = {}
                self._current_speeds = {}
                self._last_target_change_time = {}
                self._command_failure_counts = {}

            self._motor_configs = []
            self._config = None
            self._motor_ids = []
            self._limits = {}
            self._key_to_motor = {}
            self._motor_feedback = {}
            self._motor_feedback_received_at = {}
            self._motor_feedback_generations = {}
            self._motor_protection_flags = {}
            self._motor_temperature_warning_flags = {}
            self._state_mgr = None
            self._motor_mgr = None
            self._safety = None
            self._keyboard = None
            self._transport_recovery = None

        if failures:
            self.get_logger().error(
                f"资源释放完成但存在 {len(failures)} 项失败: reason={reason}; "
                + " | ".join(failures)
            )
            return False
        self.get_logger().info(f"资源释放全部完成: reason={reason}")
        return True

    def _destroy_ros_resource(
        self,
        attr: str,
        stage: str,
        destroy: Callable[[object], object],
        failures: List[str],
        reason: str,
    ) -> None:
        """每个资源最多尝试销毁一次；失败仍清除引用并继续。"""
        resource = getattr(self, attr, None)
        setattr(self, attr, None)
        if resource is None:
            return
        try:
            result = destroy(resource)
            if result is False:
                raise RuntimeError("销毁操作返回 false")
        except Exception as exc:
            failures.append(f"{stage}: {exc}")
            self.get_logger().error(
                f"资源释放失败: reason={reason}, stage={stage}, error={exc}"
            )

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
        self._publish_motor_safety_state()
        self._publish_motor_ownership_state()

    def _publish_motor_ownership_state(self) -> None:
        publisher = self._motor_ownership_state_pub
        manager = self._motor_mgr
        if publisher is None or manager is None:
            return
        try:
            ownership = manager.ownership
            sequence = self._motor_ownership_state_sequence
            self._motor_ownership_state_sequence += 1
            message = OwnershipState()
            message.stamp = self.get_clock().now().to_msg()
            message.source_epoch = self._motor_safety_source_epoch
            message.observation_sequence = sequence
            message.owner_domain = "motor"
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
            publisher.publish(message)
        except Exception as exc:
            self.get_logger().error(
                f"发布电机 ownership 快照失败（不改变控制状态）: {exc}"
            )

    def _publish_motor_safety_state(self) -> None:
        """Publish authoritative readback without touching the motor driver."""

        publisher = self._motor_safety_state_pub
        if publisher is None:
            return
        try:
            with self._lock:
                snapshot = build_motor_safety_snapshot(
                    self._state_mgr,
                    node_active=self._is_active,
                    feedback_safety_fault_latched=(
                        self._motor_safety_fault_active
                    ),
                )
                sequence = self._motor_safety_state_sequence
                self._motor_safety_state_sequence += 1
            message = MotorSafetyState()
            message.stamp = self.get_clock().now().to_msg()
            message.source_epoch = self._motor_safety_source_epoch
            message.observation_sequence = sequence
            message.node_active = snapshot.node_active
            message.controller_state = snapshot.controller_state
            message.public_control_mode = snapshot.public_control_mode
            message.e_stop_latched = snapshot.e_stop_latched
            message.error_latched = snapshot.error_latched
            message.feedback_safety_fault_latched = (
                snapshot.feedback_safety_fault_latched
            )
            message.transition_present = snapshot.transition_present
            message.transition_sequence = snapshot.transition_sequence
            message.transition_reason = snapshot.transition_reason
            message.transition_source = snapshot.transition_source
            publisher.publish(message)
        except Exception as exc:
            self.get_logger().error(
                f"发布电机安全只读快照失败（不改变安全状态）: {exc}"
            )

    def _publish_structured_motor_feedback(self) -> None:
        """Publish a complete observer snapshot without any driver operation."""

        publisher = self._motor_feedback_structured_pub
        config = self._config
        if publisher is None or config is None:
            return
        try:
            now = self._monotonic()
            with self._lock:
                snapshot = build_structured_feedback(
                    tuple(self._motor_configs),
                    dict(self._motor_feedback),
                    dict(self._motor_feedback_received_at),
                    now=now,
                    freshness_sec=(
                        config.ros.motor_feedback_observer_freshness_sec
                    ),
                    critical_temperature_c=(
                        config.safety.motor_temp_critical_deg_c
                    ),
                    safety_fault_active=self._motor_safety_fault_active,
                )
                sequence = self._motor_feedback_structured_sequence
                self._motor_feedback_structured_sequence += 1

            message = MotorFeedbackArray()
            message.stamp = self.get_clock().now().to_msg()
            message.sequence = sequence
            for item in snapshot:
                motor = MotorFeedback()
                motor.logical_name = item.logical_name
                motor.can_id = item.can_id
                motor.has_feedback = item.has_feedback
                if item.has_feedback:
                    motor.position_valid = True
                    motor.position_rad = item.position_rad
                    motor.velocity_valid = True
                    motor.velocity_rad_s = item.velocity_rad_s
                    motor.torque_valid = True
                    motor.torque_nm = item.torque_nm
                    motor.temperature_valid = True
                    motor.temperature_c = item.temperature_c
                    motor.device_mode_valid = True
                    motor.device_mode = item.device_mode
                    motor.fault_flags_valid = True
                    motor.fault_flags = item.fault_flags
                    motor.feedback_age_sec = item.feedback_age_sec
                motor.valid = item.valid
                motor.fresh = item.fresh
                motor.healthy = item.healthy
                message.motors.append(motor)
            publisher.publish(message)
        except Exception as exc:
            self.get_logger().error(
                f"发布结构化电机反馈失败（安全监控继续运行）: {exc}"
            )

    def _on_driver_feedback_error(self, exc: Exception) -> None:
        """Keep reader threads alive while making callback failures diagnosable."""
        self.get_logger().error(f"电机反馈回调异常（读取线程继续运行）: {exc}")

    def _transport_connection_generation(self) -> int:
        driver = self._driver
        if driver is None:
            return 0
        return int(getattr(driver, "connection_generation", 0))

    def _on_driver_transport_event(self, event: TransportEvent) -> None:
        """Latch a current-generation runtime fault without driver I/O."""
        if event.event_type not in (
            TransportEventType.DISCONNECTED,
            TransportEventType.READ_ERROR,
            TransportEventType.WRITE_ERROR,
        ):
            self._on_transport_recovery_event(event)
            return
        if event.connection_generation != self._transport_connection_generation():
            self.get_logger().warn(
                "忽略旧 connection generation 的 transport 事件: "
                f"event={event.connection_generation}, "
                f"current={self._transport_connection_generation()}"
            )
            return
        self._publish_transport_event(event)
        if self._motor_mgr is None or self._transport_recovery is None:
            return
        configuring = (
            self._state_mgr is not None
            and self._state_mgr.state is ControllerState.INITIALIZING
        )
        first = self._motor_mgr.enter_transport_error(event)
        if not first:
            return
        if configuring:
            self.get_logger().error(
                "configure 初始化期间发生 transport 故障；"
                "将执行事务式回滚，不启动运行期 reconnect"
            )
            return
        if not self._transport_recovery.request_recovery(event):
            self.get_logger().warn(
                "transport 故障已锁存，但 lifecycle 正在停用/清理；"
                "未启动后台 reconnect"
            )

    def _on_transport_recovery_event(self, event: TransportEvent) -> None:
        """Publish recovery diagnostics without changing the ERROR latch."""
        self._publish_transport_event(event)
        if event.event_type is TransportEventType.RECONNECTED:
            self.get_logger().warn(
                "电机通信已恢复，但控制保持 ERROR；不会初始化电机或恢复运动，"
                "必须 lifecycle 重新配置或重启"
            )
        elif event.event_type is TransportEventType.RECONNECT_FAILED:
            self.get_logger().error(
                "电机通信重连达到最大次数；控制继续保持 ERROR"
            )

    def _publish_transport_event(self, event: TransportEvent) -> None:
        publisher = self._motor_status_pub
        if publisher is None:
            return
        msg = String()
        parts = [
            f"motor_transport:{event.event_type.value}",
            f"backend={event.backend}",
            f"operation={event.operation}",
            f"generation={event.connection_generation}",
        ]
        if event.attempt is not None:
            parts.append(f"attempt={event.attempt}/{event.max_attempts}")
        msg.data = ":".join(parts)
        try:
            publisher.publish(msg)
        except Exception as exc:
            self.get_logger().error(f"发布 transport 状态失败: {exc}")

    def _stop_for_transport_fault(self, event: TransportEvent) -> None:
        motor_mgr = self._motor_mgr
        if motor_mgr is not None:
            motor_mgr.stop_motors_for_fault_once(
                reason=(
                    f"transport:{event.event_type.value}:{event.operation}:"
                    f"generation={event.connection_generation}"
                )
            )

    def _close_transport_for_recovery(self) -> None:
        with self._driver_io_lock:
            driver = self._driver
            if driver is not None:
                driver.close()

    def _connect_transport_once(self) -> None:
        """Reopen only the transport/reader; never initialize any motor."""
        if not self._running:
            raise RuntimeError("lifecycle is inactive; reconnect cancelled")
        with self._driver_io_lock:
            if not self._running:
                raise RuntimeError("lifecycle became inactive; reconnect cancelled")
            driver = self._driver
            if driver is None:
                raise RuntimeError("driver released during reconnect")
            driver.connect()

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

    def _ownership_response(self, response, result):
        response.success = result.success
        response.reason_code = result.reason_code
        response.authority_epoch = result.authority_epoch
        response.generation = result.generation
        response.owner_observation_sequence = max(
            0, self._motor_ownership_state_sequence - 1
        )
        return response

    def _on_flight_prepare(self, request, response):
        result = self._motor_mgr.prepare_flight_ownership(
            int(request.authority_epoch),
            int(request.generation),
            now=time.monotonic(),
        )
        return self._ownership_response(response, result)

    def _on_flight_commit(self, request, response):
        result = self._motor_mgr.commit_flight_ownership(
            int(request.authority_epoch),
            int(request.generation),
            now=time.monotonic(),
        )
        return self._ownership_response(response, result)

    def _on_flight_revoke(self, request, response):
        result = self._motor_mgr.revoke_flight_ownership(
            int(request.authority_epoch), int(request.generation)
        )
        return self._ownership_response(response, result)

    def _on_flight_command(self, message: FlightCommandEnvelope) -> None:
        names = list(message.motor_names)
        positions = list(message.motor_positions_rad)
        common_valid = (
            len(names) == len(positions)
            and len(set(names)) == len(names)
            and all(isinstance(name, str) and name for name in names)
        )
        if message.request_safe_stop:
            valid = common_valid and not names and not positions and not message.fan_commands_present
            if not valid:
                self.get_logger().warn("拒绝携带 actuator payload 的 Flight safe-stop")
                self._motor_mgr.fail_closed_flight("invalid_safe_stop_envelope")
                return
            result = self._motor_mgr.accept_flight_safe_stop(
                int(message.authority_epoch),
                int(message.generation),
                int(message.command_sequence),
                now=time.monotonic(),
            )
        else:
            valid = (
                common_valid
                and set(names) == {cfg.name for cfg in self._motor_configs}
                and all(math.isfinite(float(value)) for value in positions)
                and message.fan_commands_present
                and math.isfinite(float(message.fan_left))
                and math.isfinite(float(message.fan_right))
                and 0.0 <= float(message.fan_left) <= 1.0
                and 0.0 <= float(message.fan_right) <= 1.0
            )
            if not valid:
                self.get_logger().warn("拒绝 payload contract 非法的 Flight command")
                self._motor_mgr.fail_closed_flight("invalid_flight_envelope")
                return
            result = self._motor_mgr.set_flight_targets(
                int(message.authority_epoch),
                int(message.generation),
                int(message.command_sequence),
                dict(zip(names, positions)),
                now=time.monotonic(),
            )
        if not result.success:
            self.get_logger().warn(
                f"拒绝 Flight motor command: {result.reason_code}"
            )
            if result.reason_code in {
                "invalid_token",
                "authority_token_mismatch",
                "flight_command_not_allowed",
            }:
                self._motor_mgr.fail_closed_flight(result.reason_code)

    def publish_system_emergency_stop(self) -> None:
        """发布系统级急停，让电机与风扇使用同一安全通道。"""
        if self._system_e_stop_pub is None:
            return
        msg = Bool()
        msg.data = True
        self._system_e_stop_pub.publish(msg)

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """关闭阶段：与 cleanup/配置失败共用统一释放流程。"""
        self.get_logger().info("控制节点正在关闭...")
        transition_accepted = True
        if self._state_mgr is not None:
            shutdown_result = self._state_mgr.transition_to(
                ControllerState.SHUTTING_DOWN,
                reason=TransitionReason.SHUTDOWN_REQUEST,
                source=TransitionSource.LIFECYCLE,
            )
            if shutdown_result.outcome is TransitionOutcome.REJECTED:
                transition_accepted = False
                self.get_logger().error(
                    "关键状态转换被拒绝：无法进入 SHUTTING_DOWN"
                )
        released = self._release_resources(reason="shutdown", attempt_motor_stop=True)
        return (
            TransitionCallbackReturn.SUCCESS
            if released and transition_accepted
            else TransitionCallbackReturn.FAILURE
        )

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
