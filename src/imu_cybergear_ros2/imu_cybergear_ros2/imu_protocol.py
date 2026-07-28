"""WIT 维特智能 IMU 串口协议解析器。

支持的协议帧格式（JY61 / HWT905 系列，11 字节固定帧）：

  字节0    字节1    字节2-3   字节4-5   字节6-7   字节8-9   字节10
  ┌───────┬───────┬─────────┬─────────┬─────────┬─────────┬────────┐
  │ 0x55  │ 类型   │ 数据1    │ 数据2    │ 数据3    │ 数据4    │ 校验和  │
  └───────┴───────┴─────────┴─────────┴─────────┴─────────┴────────┘
    帧头     帧类型    int16     int16     int16     int16     sum & 0xFF

帧类型：
  0x51 — 加速度帧（±16g）
  0x52 — 角速度帧（±2000°/s）
  0x53 — 角度帧（±180°）
  0x54 — 磁场帧（本实现忽略）

数据转换为物理量的公式：
  物理量 = 原始值 / 32768.0 × 满量程

加速度单位：m/s²（含重力加速度 g = 9.80665 m/s²）
角速度单位：rad/s
角度单位：度（°）
"""

import math
import struct
import threading
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 协议常量（根据 IMU 出厂量程设定，如更换量程需同步修改）
# ---------------------------------------------------------------------------
FRAME_HEADER = 0x55          # 帧头固定字节
FRAME_LENGTH = 11            # 完整帧长度（字节）
FRAME_TYPE_ACCEL = 0x51      # 加速度帧
FRAME_TYPE_GYRO = 0x52       # 角速度帧
FRAME_TYPE_ANGLE = 0x53      # 角度帧（姿态角）
FRAME_TYPE_MAG = 0x54        # 磁场帧（不解析）

ACCEL_FULL_SCALE = 16.0      # 加速度满量程 ±16g
GYRO_FULL_SCALE = 2000.0     # 角速度满量程 ±2000°/s
ANGLE_FULL_SCALE = 180.0     # 角度满量程 ±180°
GRAVITY = 9.80665            # 标准重力加速度（m/s²）
INT16_MAX = 32768.0          # int16 最大值（用于归一化）


def _hex_to_short(raw_data: bytes) -> List[int]:
    """将 8 字节原始数据拆解为 4 个 int16（小端序）。

    参数：
        raw_data: 8 字节的 bytes / bytearray。

    返回：
        [v1, v2, v3, v4]，每个元素为 int16 范围（-32768 ~ 32767）。
    """
    return list(struct.unpack("hhhh", bytearray(raw_data)))


class WitImuFrameParser:
    """WIT IMU 11 字节串口帧逐字节解析器。

    调用方只需循环调用 :meth:`parse_byte` 喂入串口收到的每个字节。
    当完整角度帧被成功解析时，该方法返回 `True`，此时可调用
    :meth:`latest_imu_values` 获取最新的加速度、角速度和角度值。

    线程安全：内部使用 threading.Lock 保护帧解析和数值更新，允许多线程
    安全地调用 parse_byte 和 latest_imu_values。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._key = 0
        self._buff: Dict[int, int] = {}
        # ---- 以下为最新解析结果（受 _lock 保护） ----
        self.acceleration = [0.0, 0.0, 0.0]           # [ax, ay, az] m/s²
        self.angular_velocity = [0.0, 0.0, 0.0]       # [gx, gy, gz] rad/s
        self.angle_degree = [0.0, 0.0, 0.0]           # [roll, pitch, yaw] 度

    @staticmethod
    def _check_sum(data_list: List[int], check_data: int) -> bool:
        """校验和验证：前 10 字节累加取低 8 位与第 11 字节对比。"""
        return (sum(data_list) & 0xFF) == check_data

    def _reset_buffer(self) -> None:
        """清空帧缓冲区，等待下一个帧头。"""
        self._key = 0
        self._buff.clear()

    def parse_byte(self, raw_byte: int) -> bool:
        """向解析器喂入一个字节。

        参数：
            raw_byte: 从串口读取的单个字节（0~255）。

        返回：
            当且仅当成功解析到一个角度帧（0x53）时返回 `True`。
        """
        with self._lock:
            self._buff[self._key] = raw_byte
            self._key += 1

            # 帧头不对，丢弃整个缓冲区
            if self._buff.get(0, None) != FRAME_HEADER:
                self._reset_buffer()
                return False

            # 还未收满一帧
            if self._key < FRAME_LENGTH:
                return False

            # 已收满 11 字节，提取并校验
            data_buff = [self._buff[i] for i in range(FRAME_LENGTH)]
            frame_type = self._buff[1]
            valid = self._check_sum(data_buff[0:10], data_buff[10])

            if valid:
                raw = _hex_to_short(bytes(data_buff[2:10]))
                if frame_type == FRAME_TYPE_ACCEL:
                    self.acceleration = [
                        raw[i] / INT16_MAX * ACCEL_FULL_SCALE * GRAVITY
                        for i in range(3)
                    ]
                elif frame_type == FRAME_TYPE_GYRO:
                    self.angular_velocity = [
                        raw[i] / INT16_MAX * GYRO_FULL_SCALE * math.pi / 180.0
                        for i in range(3)
                    ]
                elif frame_type == FRAME_TYPE_ANGLE:
                    self.angle_degree = [
                        raw[i] / INT16_MAX * ANGLE_FULL_SCALE
                        for i in range(3)
                    ]
                    self._reset_buffer()
                    return True
                # 0x54 磁场帧忽略

            self._reset_buffer()
            return False

    def latest_imu_values(self) -> Tuple[List[float], List[float], List[float]]:
        """获取最新解析的 IMU 数值（线程安全拷贝）。

        返回：
            (加速度, 角速度, 角度) 三元组。
            加速度单位：m/s²，角速度单位：rad/s，角度单位：度。
        """
        with self._lock:
            return (
                list(self.acceleration),
                list(self.angular_velocity),
                list(self.angle_degree),
            )


# ---------------------------------------------------------------------------
# 欧拉角 / 四元数转换工具（线程安全纯函数）
# ---------------------------------------------------------------------------

def quaternion_from_euler(
    roll: float, pitch: float, yaw: float
) -> Tuple[float, float, float, float]:
    """将欧拉角（rad）转换为四元数 (x, y, z, w)。

    旋转顺序：Z-Y-X（标准 ROS 约定）。

    参数：
        roll:  横滚角（rad）
        pitch: 俯仰角（rad）
        yaw:   偏航角（rad）

    返回：
        (qx, qy, qz, qw) 四元数分量。
    """
    qx = (
        math.sin(roll / 2.0) * math.cos(pitch / 2.0) * math.cos(yaw / 2.0)
        - math.cos(roll / 2.0) * math.sin(pitch / 2.0) * math.sin(yaw / 2.0)
    )
    qy = (
        math.cos(roll / 2.0) * math.sin(pitch / 2.0) * math.cos(yaw / 2.0)
        + math.sin(roll / 2.0) * math.cos(pitch / 2.0) * math.sin(yaw / 2.0)
    )
    qz = (
        math.cos(roll / 2.0) * math.cos(pitch / 2.0) * math.sin(yaw / 2.0)
        - math.sin(roll / 2.0) * math.sin(pitch / 2.0) * math.cos(yaw / 2.0)
    )
    qw = (
        math.cos(roll / 2.0) * math.cos(pitch / 2.0) * math.cos(yaw / 2.0)
        + math.sin(roll / 2.0) * math.sin(pitch / 2.0) * math.sin(yaw / 2.0)
    )
    return qx, qy, qz, qw


def euler_from_quaternion(
    x: float, y: float, z: float, w: float
) -> Tuple[float, float, float]:
    """将四元数转换为欧拉角（rad）。

    旋转顺序：Z-Y-X（标准 ROS 约定）。

    参数：
        x, y, z, w: 四元数分量。

    返回：
        (roll, pitch, yaw) 欧拉角三元组，单位 rad。
    """
    t0 = 2.0 * (w * x + y * z)
    t1 = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(t0, t1)

    t2 = 2.0 * (w * y - z * x)
    t2 = max(-1.0, min(1.0, t2))  # 防浮点溢出
    pitch = math.asin(t2)

    t3 = 2.0 * (w * z + x * y)
    t4 = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(t3, t4)

    return roll, pitch, yaw
