"""imu_cybergear_ros2 — IMU 驱动 CyberGear 电机控制 ROS2 包。

包含两个 LifecycleNode：
  - ImuDriverNode: WIT IMU 串口数据读取与发布
  - ImuMotorControllerNode: IMU 姿态驱动多电机联动控制

子模块：
  - controller_state: 控制状态机与状态管理
  - motor_manager: 电机连接、目标写入、自动归零
  - safety_monitor: 看门狗、电机反馈监控、急停系统
  - keyboard_handler: 终端键盘控制
  - cybergear_driver: CyberGear CAN 协议驱动
  - imu_protocol: WIT IMU 串口协议解析
"""

from .controller_state import ControllerState, StateManager
from .motor_manager import MotorManager
from .safety_monitor import SafetyMonitor
from .keyboard_handler import KeyboardHandler
