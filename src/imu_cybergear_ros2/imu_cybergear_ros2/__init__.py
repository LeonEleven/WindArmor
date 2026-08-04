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
  - motor_motion: 不依赖 ROS/硬件的统一目标推进计算
"""

from importlib import import_module


_LAZY_EXPORTS = {
    "ControllerState": (".controller_state", "ControllerState"),
    "StateManager": (".controller_state", "StateManager"),
    "MotorManager": (".motor_manager", "MotorManager"),
    "SafetyMonitor": (".safety_monitor", "SafetyMonitor"),
    "KeyboardHandler": (".keyboard_handler", "KeyboardHandler"),
}


def __getattr__(name):
    """延迟导入 ROS 子模块，使纯计算模块可在无 ROS 环境下单独测试。"""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = list(_LAZY_EXPORTS)
