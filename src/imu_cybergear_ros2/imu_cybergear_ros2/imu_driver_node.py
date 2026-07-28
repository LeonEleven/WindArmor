"""WIT IMU 串口驱动节点（LifecycleNode 版本）。

功能：
  1. 通过串口读取 WIT 维特智能 IMU 原始数据
  2. 使用 WitImuFrameParser 解析加速度/角速度/角度帧
  3. 发布标准 sensor_msgs/Imu 消息到 /imu/data_raw 话题
  4. 发布连接状态到 /imu/status 话题（std_msgs/String）
  5. **断线自动重连**：串口断开后指数退避重连（最多 30 次）
  6. **低 CPU 占用**：空闲时主动让出 CPU

生命周期状态：
  unconfigured → on_configure → inactive → on_activate → active
  active → on_deactivate → inactive → on_cleanup → unconfigured

启动方式：
  ros2 run imu_cybergear_ros2 imu_driver_node --ros-args --params-file <path>
"""

import math
import threading
import time

import rclpy
import serial
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn, State
from sensor_msgs.msg import Imu
from std_msgs.msg import String

from .imu_protocol import WitImuFrameParser, quaternion_from_euler

# ---------------------------------------------------------------------------
# 重连策略常量
# ---------------------------------------------------------------------------
MAX_RECONNECT_ATTEMPTS = 30
INITIAL_RECONNECT_DELAY = 0.5
MAX_RECONNECT_DELAY = 10.0
SERIAL_TIMEOUT = 0.1
IDLE_SLEEP_SEC = 0.001


class ImuDriverNode(LifecycleNode):
    """WIT IMU 串口驱动节点（LifecycleNode）。

    发布话题：
      /imu/data_raw  (sensor_msgs/Imu)  — IMU 数据
      /imu/status    (std_msgs/String)  — 连接状态

    参数（YAML 可配置）：
      port       — 串口设备路径（默认 /dev/imu_usb）
      baud       — 串口波特率（默认 9600）
      frame_id   — IMU 坐标系 ID（默认 imu_link）
      topic_name — IMU 数据发布话题名（默认 /imu/data_raw）
    """

    def __init__(self):
        super().__init__("imu_driver_node")

        # ---- 声明参数（在 unconfigured 状态下可用） ----
        self.declare_parameter("port", "/dev/imu_usb")
        self.declare_parameter("baud", 9600)
        self.declare_parameter("frame_id", "imu_link")
        self.declare_parameter("topic_name", "/imu/data_raw")

        # ---- 初始化实例变量（资源在 on_configure 中创建） ----
        self._parser = None
        self._imu_pub = None
        self._status_pub = None
        self._stop_event = None
        self._serial = None
        self._thread = None
        self._is_active = False

        # 参数值缓存
        self._port = ""
        self._baud = 0
        self._frame_id = ""
        self._topic_name = ""

        self.get_logger().info("IMU 节点已创建（等待 configure）")

    # ------------------------------------------------------------------
    # 生命周期回调
    # ------------------------------------------------------------------

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """配置阶段：读取参数、创建解析器和发布器、尝试打开串口。"""
        self.get_logger().info("IMU 节点正在配置...")

        # 读取参数
        self._port = self.get_parameter("port").get_parameter_value().string_value
        self._baud = self.get_parameter("baud").get_parameter_value().integer_value
        self._frame_id = self.get_parameter("frame_id").get_parameter_value().string_value
        self._topic_name = self.get_parameter("topic_name").get_parameter_value().string_value

        # 创建组件
        self._parser = WitImuFrameParser()
        self._imu_pub = self.create_publisher(Imu, self._topic_name, 20)
        self._status_pub = self.create_publisher(String, "/imu/status", 10)
        self._stop_event = threading.Event()
        self._serial = None

        self.get_logger().info(
            f"IMU 节点配置完成: port={self._port}, baud={self._baud}, topic={self._topic_name}"
        )
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """激活阶段：启动串口读取线程。"""
        self.get_logger().info("IMU 节点正在激活...")
        self._is_active = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
        self.get_logger().info("IMU 节点已激活")
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """停用阶段：停止读取线程。"""
        self.get_logger().info("IMU 节点正在停用...")
        self._is_active = False
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._close_serial()
        self._publish_status("disconnected")
        self.get_logger().info("IMU 节点已停用")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """清理阶段：销毁发布器，重置状态。"""
        self.get_logger().info("IMU 节点正在清理...")
        self._close_serial()
        if self._imu_pub is not None:
            self.destroy_publisher(self._imu_pub)
            self._imu_pub = None
        if self._status_pub is not None:
            self.destroy_publisher(self._status_pub)
            self._status_pub = None
        self._parser = None
        self._stop_event = None
        self.get_logger().info("IMU 节点清理完成")
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """关闭阶段：最终清理。"""
        self.get_logger().info("IMU 节点正在关闭...")
        self._is_active = False
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._close_serial()
        self._publish_status("disconnected")
        if self._imu_pub is not None:
            self.destroy_publisher(self._imu_pub)
            self._imu_pub = None
        if self._status_pub is not None:
            self.destroy_publisher(self._status_pub)
            self._status_pub = None
        self.get_logger().info("IMU 节点已关闭")
        return TransitionCallbackReturn.SUCCESS

    # ------------------------------------------------------------------
    # 串口操作
    # ------------------------------------------------------------------

    def _try_open_serial(self) -> bool:
        """尝试打开串口，成功返回 True，失败返回 False。"""
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=SERIAL_TIMEOUT,
            )
            self.get_logger().info(f"IMU 串口已连接: {self._port} @ {self._baud}")
            self._publish_status("connected")
            return True
        except Exception as exc:
            self.get_logger().warn(f"IMU 串口打开失败 ({self._port}): {exc}")
            self._publish_status("disconnected")
            return False

    def _close_serial(self) -> None:
        """安全关闭串口。"""
        try:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass
        self._serial = None

    def _publish_status(self, status: str) -> None:
        """发布 IMU 连接状态字符串。"""
        try:
            if self._status_pub is not None:
                msg = String()
                msg.data = status
                self._status_pub.publish(msg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 主读取循环（带断线重连）
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """串口读取主循环（后台 daemon 线程）。"""
        reconnect_delay = INITIAL_RECONNECT_DELAY
        attempt_count = 0

        # 初始连接
        if not self._try_open_serial():
            self.get_logger().info("IMU 正在尝试重连...")
            self._publish_status("reconnecting")

        # 主循环
        while not self._stop_event.is_set():
            # ---- 未连接时尝试重连 ----
            if self._serial is None or not self._serial.is_open:
                if attempt_count >= MAX_RECONNECT_ATTEMPTS:
                    self.get_logger().error(
                        f"IMU 重连失败，已达最大尝试次数 {MAX_RECONNECT_ATTEMPTS}，"
                        f"请检查硬件连接后手动重启节点。"
                    )
                    self._publish_status("disconnected")
                    return

                self.get_logger().info(
                    f"IMU 重连中...（第 {attempt_count + 1}/{MAX_RECONNECT_ATTEMPTS} 次，"
                    f"等待 {reconnect_delay:.1f}s）"
                )
                self._publish_status("reconnecting")
                time.sleep(reconnect_delay)

                if self._try_open_serial():
                    reconnect_delay = INITIAL_RECONNECT_DELAY
                    attempt_count = 0
                else:
                    reconnect_delay = min(
                        reconnect_delay * 1.5, MAX_RECONNECT_DELAY
                    )
                    attempt_count += 1
                continue

            # ---- 已连接：检查是否有可读数据 ----
            try:
                buff_count = self._serial.in_waiting
            except (serial.SerialException, OSError) as exc:
                self.get_logger().error(f"IMU 串口连接断开: {exc}")
                self._close_serial()
                self._publish_status("disconnected")
                reconnect_delay = INITIAL_RECONNECT_DELAY
                continue

            if buff_count <= 0:
                time.sleep(IDLE_SLEEP_SEC)
                continue

            # ---- 读取并解析数据 ----
            try:
                buff_data = self._serial.read(buff_count)
            except (serial.SerialException, OSError) as exc:
                self.get_logger().error(f"读取 IMU 串口数据失败: {exc}")
                self._close_serial()
                self._publish_status("disconnected")
                reconnect_delay = INITIAL_RECONNECT_DELAY
                continue

            for data_byte in buff_data:
                if self._parser.parse_byte(data_byte):
                    self._publish_imu()

    # ------------------------------------------------------------------
    # IMU 消息发布
    # ------------------------------------------------------------------

    def _publish_imu(self) -> None:
        """将解析器中的最新 IMU 数据填充为 sensor_msgs/Imu 并发布。"""
        if not self._is_active or self._imu_pub is None:
            return

        accel, gyro, angle_degree = self._parser.latest_imu_values()

        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id

        msg.linear_acceleration.x = float(accel[0])
        msg.linear_acceleration.y = float(accel[1])
        msg.linear_acceleration.z = float(accel[2])

        msg.angular_velocity.x = float(gyro[0])
        msg.angular_velocity.y = float(gyro[1])
        msg.angular_velocity.z = float(gyro[2])

        roll = math.radians(angle_degree[0])
        pitch = math.radians(angle_degree[1])
        yaw = math.radians(angle_degree[2])
        qx, qy, qz, qw = quaternion_from_euler(roll, pitch, yaw)
        msg.orientation.x = qx
        msg.orientation.y = qy
        msg.orientation.z = qz
        msg.orientation.w = qw

        self._imu_pub.publish(msg)


def main(args=None):
    """节点入口。"""
    rclpy.init(args=args)
    node = ImuDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()
