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
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# 协议常量（根据 IMU 出厂量程设定，如更换量程需同步修改）
# ---------------------------------------------------------------------------
FRAME_HEADER = 0x55          # 帧头固定字节
FRAME_LENGTH = 11            # 完整帧长度（字节）
FRAME_TYPE_ACCEL = 0x51      # 加速度帧
FRAME_TYPE_GYRO = 0x52       # 角速度帧
FRAME_TYPE_ANGLE = 0x53      # 角度帧（姿态角）
FRAME_TYPE_MAG = 0x54        # 磁场帧（不解析）
FRAME_TYPE_REGISTERS = 0x5F  # 四个连续寄存器；应答不包含起始地址

ACCEL_FULL_SCALE = 16.0      # 加速度满量程 ±16g
GYRO_FULL_SCALE = 2000.0     # 角速度满量程 ±2000°/s
ANGLE_FULL_SCALE = 180.0     # 角度满量程 ±180°
GRAVITY = 9.80665            # 标准重力加速度（m/s²）
INT16_MAX = 32768.0          # int16 最大值（用于归一化）
MIN_QUATERNION_NORM = 1e-12  # 拒绝无法可靠归一化的近零四元数


def _hex_to_short(raw_data: bytes) -> List[int]:
    """将 8 字节原始数据拆解为 4 个 int16（小端序）。

    参数：
        raw_data: 8 字节的 bytes / bytearray。

    返回：
        [v1, v2, v3, v4]，每个元素为 int16 范围（-32768 ~ 32767）。
    """
    return list(struct.unpack("hhhh", bytearray(raw_data)))


def encode_readaddr(start_address: int) -> bytes:
    """仅编码 READADDR，不执行 I/O；拒绝四寄存器窗口越过 8-bit 地址范围。"""
    if type(start_address) is not int or not 0 <= start_address <= 0xFC:
        raise ValueError("READADDR start address must be an integer in 0..252")
    return bytes((0xFF, 0xAA, 0x27, start_address, 0x00))


def decode_register_response(frame: bytes) -> Tuple[int, int, int, int]:
    """解码无地址的 0x5F 应答；unsigned wire words 不自动关联任何请求。"""
    if (len(frame) != FRAME_LENGTH or frame[:2] != b"\x55\x5f"
            or (sum(frame[:10]) & 0xFF) != frame[10]):
        raise ValueError("invalid register response frame")
    return struct.unpack("<4H", frame[2:10])


# 厂家寄存器表；不是允许值/defaults，也不授权配置写入。
CONFIGURATION_REGISTERS = (
    ("RSW", 0x02), ("RRATE", 0x03), ("BAUD", 0x04),
    ("GXOFFSET", 0x08), ("GYOFFSET", 0x09), ("GZOFFSET", 0x0A),
    ("BANDWIDTH", 0x1F), ("GYRORANGE", 0x20), ("ORIENT", 0x23),
    ("AXIS6", 0x24), ("FILTK", 0x25), ("ACCFILT", 0x2A),
    ("GYROCALITHR", 0x61), ("GYROCALTIME", 0x63),
    ("WZTIME", 0x6E), ("WZSTATIC", 0x6F),
)
REQUIRED_CONFIGURATION_NAMES = frozenset(("RSW", "BAUD", "GYRORANGE"))
MODULE_BAUD_CODES = (
    (1, 4800), (2, 9600), (3, 19200), (4, 38400), (5, 57600),
    (6, 115200), (7, 230400), (8, 460800), (9, 921600),
)


@dataclass(frozen=True)
class ImuConfigurationCheck:
    """离线规则检查，不证明地址关联、连接代次验证或 ALG-007 availability。"""

    required_values_passed: bool
    observation_complete: bool
    observed_registers: Tuple[Tuple[str, int, int], ...]
    missing_required: Tuple[str, ...]
    missing_provenance: Tuple[str, ...]
    failures: Tuple[str, ...]


def check_imu_configuration(
    registers: Mapping[int, int], *, host_baud: int,
) -> ImuConfigurationCheck:
    """检查调用者已独立确认地址的离线数据；不得直接给匿名应答补地址。

    只冻结 GYRO/ANGLE 输出位、2000 deg/s 解码范围和实际 host/module baud
    一致性。其余寄存器只记录 raw word；校准 offset 不要求为零。
    """
    if type(host_baud) is not int or host_baud <= 0:
        raise ValueError("host baud must be a positive integer")
    words = dict(registers)
    if any(type(address) is not int or not 0 <= address <= 0xFF
           or type(word) is not int or not 0 <= word <= 0xFFFF
           for address, word in words.items()):
        raise ValueError("registers must contain 8-bit addresses and unsigned 16-bit words")
    missing_required = tuple(name for name, address in CONFIGURATION_REGISTERS
                             if name in REQUIRED_CONFIGURATION_NAMES and address not in words)
    missing_provenance = tuple(name for name, address in CONFIGURATION_REGISTERS
                               if name not in REQUIRED_CONFIGURATION_NAMES and address not in words)
    failures = []
    if 0x02 in words and words[0x02] & 0x000C != 0x000C:
        failures.append("RSW missing GYRO/ANGLE output bits")
    if 0x20 in words and words[0x20] & 0x000F != 0x0003:
        failures.append("GYRORANGE incompatible with 2000 deg/s decode")
    if 0x04 in words and dict(MODULE_BAUD_CODES).get(words[0x04] & 0x000F) != host_baud:
        failures.append("module BAUD does not match effective host baud")
    return ImuConfigurationCheck(
        not missing_required and not failures,
        not missing_required and not missing_provenance,
        tuple((name, address, words[address]) for name, address in CONFIGURATION_REGISTERS
              if address in words),
        missing_required, missing_provenance, tuple(failures),
    )


@dataclass(frozen=True)
class ImuRegisterResponse:
    """合法匿名应答，仅为主机接收历史；不是已关联或已验证的配置。"""

    words: Tuple[int, int, int, int]
    received_monotonic: float
    generation: int


@dataclass(frozen=True)
class ImuRegisterResponseState:
    """无地址应答的只读诊断快照；latest_response 不代表新的有效事务。"""

    generation: int
    latest_response: Optional[ImuRegisterResponse]
    response_count: int
    checksum_failure_count: int
    partial_response: bool


@dataclass(frozen=True)
class ImuFrameComponent:
    """合法帧快照；values 单位沿用 legacy decode，时间为主机完整帧接受时间。"""

    frame_type: int
    values: Tuple[float, float, float]
    received_monotonic: float
    generation: int


@dataclass(frozen=True)
class GyroAnglePair:
    """Level-2 软件候选，不保证厂家周期、物理同采样或有限组件年龄。"""

    gyro: ImuFrameComponent
    angle: ImuFrameComponent
    sequence: int


@dataclass(frozen=True)
class ImuCoherenceState:
    """只读状态；latest_pair 是历史结果，更新由 (generation, pair_count) 标识。"""

    generation: int
    latest_component: Optional[ImuFrameComponent]
    pending_gyro: Optional[ImuFrameComponent]
    latest_pair: Optional[GyroAnglePair]
    pair_count: int


class WitImuFrameParser:
    """WIT IMU 11 字节串口帧逐字节解析器。

    调用方只需循环调用 :meth:`parse_byte` 喂入串口收到的每个字节。
    当完整角度帧被成功解析时，该方法返回 `True`，此时可调用
    :meth:`latest_imu_values` 获取最新的加速度、角速度和角度值。

    线程安全：内部使用 threading.Lock 保护帧解析和数值更新，允许多线程
    安全地调用 parse_byte 和 latest_imu_values。
    """

    def __init__(
        self, *, monotonic_clock: Callable[[], float] = time.monotonic,
        generation: int = 0,
    ):
        self._lock = threading.Lock()
        self._monotonic_clock = monotonic_clock
        self._generation = generation
        self._latest_component = None
        self._pending_gyro = None
        self._latest_pair = None
        self._pair_count = 0
        self._latest_register_response = None
        self._register_response_count = 0
        self._register_checksum_failure_count = 0
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

    def reset(self) -> None:
        """建立新解析/连接代次，清除残帧、legacy 缓存与全部配对状态。"""
        with self._lock:
            self._generation += 1
            self._reset_buffer()
            self.acceleration = [0.0, 0.0, 0.0]
            self.angular_velocity = [0.0, 0.0, 0.0]
            self.angle_degree = [0.0, 0.0, 0.0]
            self._latest_component = None
            self._pending_gyro = None
            self._latest_pair = None
            self._pair_count = 0
            self._latest_register_response = None
            self._register_response_count = 0
            self._register_checksum_failure_count = 0

    def register_response_state(self) -> ImuRegisterResponseState:
        """观察匿名帧，绝不根据帧内容猜测起始地址或配置验证状态。"""
        with self._lock:
            return ImuRegisterResponseState(
                self._generation, self._latest_register_response,
                self._register_response_count, self._register_checksum_failure_count,
                self._key >= 2 and self._buff.get(1) == FRAME_TYPE_REGISTERS,
            )

    def coherence_state(self) -> ImuCoherenceState:
        """返回不可变快照；保留各组件时间，不将 ROS 发布时间当作组件时间。"""
        with self._lock:
            return ImuCoherenceState(
                self._generation, self._latest_component, self._pending_gyro,
                self._latest_pair, self._pair_count,
            )

    def parse_byte(self, raw_byte: int, *, generation: Optional[int] = None) -> bool:
        """向解析器喂入一个字节。

        参数：
            raw_byte: 从串口读取的单个字节（0~255）。
            generation: 可选的 read 开始代次；reset 后迟到的旧 read 字节被拒绝。

        返回：
            当且仅当成功解析到一个角度帧（0x53）时返回 `True`。
        """
        with self._lock:
            if generation is not None and generation != self._generation:
                return False
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

            if frame_type == FRAME_TYPE_REGISTERS:
                if valid:
                    self._latest_register_response = ImuRegisterResponse(
                        decode_register_response(bytes(data_buff)),
                        self._monotonic_clock(), self._generation,
                    )
                    self._register_response_count += 1
                else:
                    self._register_checksum_failure_count += 1
                self._reset_buffer()
                return False

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
                # 0x54 磁场帧忽略

                values = {
                    FRAME_TYPE_ACCEL: self.acceleration,
                    FRAME_TYPE_GYRO: self.angular_velocity,
                    FRAME_TYPE_ANGLE: self.angle_degree,
                }.get(frame_type)
                if values is not None:
                    component = ImuFrameComponent(
                        frame_type, tuple(values), self._monotonic_clock(),
                        self._generation,
                    )
                    self._latest_component = component
                    if frame_type == FRAME_TYPE_GYRO:
                        self._pending_gyro = component
                    elif frame_type == FRAME_TYPE_ANGLE:
                        if self._pending_gyro is not None:
                            self._pair_count += 1
                            self._latest_pair = GyroAnglePair(
                                self._pending_gyro, component, self._pair_count,
                            )
                            self._pending_gyro = None
                        self._reset_buffer()
                        return True

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


def normalize_angle_rad(angle: float) -> float:
    """把有限弧度角归一化到 [-pi, pi]。"""
    if not math.isfinite(angle):
        raise ValueError("角度必须是有限值")
    return math.atan2(math.sin(angle), math.cos(angle))


def normalize_quaternion(
    x: float,
    y: float,
    z: float,
    w: float,
    minimum_norm: float = MIN_QUATERNION_NORM,
) -> Tuple[float, float, float, float]:
    """校验并归一化四元数，返回 (x, y, z, w)。"""
    values = (x, y, z, w)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("四元数包含 NaN 或 Inf")
    if not math.isfinite(minimum_norm) or minimum_norm <= 0.0:
        raise ValueError("minimum_norm 必须是正有限值")

    norm = math.sqrt(sum(value * value for value in values))
    if norm < minimum_norm:
        raise ValueError("四元数范数过小")
    return tuple(value / norm for value in values)


def corrected_relative_roll_pitch(
    x: float,
    y: float,
    z: float,
    w: float,
    *,
    roll_axis_sign: float,
    pitch_axis_sign: float,
    zero_roll: float,
    zero_pitch: float,
) -> Tuple[float, float, float, float]:
    """计算修正后的绝对和相对 roll/pitch。

    返回 ``(roll, pitch, relative_roll, relative_pitch)``，单位均为 rad。
    相对角在轴向修正和统一零点扣除后归一化到 [-pi, pi]。
    """
    corrections = (roll_axis_sign, pitch_axis_sign, zero_roll, zero_pitch)
    if not all(math.isfinite(value) for value in corrections):
        raise ValueError("轴向修正和零点必须是有限值")
    if roll_axis_sign == 0.0 or pitch_axis_sign == 0.0:
        raise ValueError("轴向修正符号不能为零")

    qx, qy, qz, qw = normalize_quaternion(x, y, z, w)
    raw_roll, raw_pitch, _ = euler_from_quaternion(qx, qy, qz, qw)
    roll = normalize_angle_rad(raw_roll * roll_axis_sign)
    pitch = normalize_angle_rad(raw_pitch * pitch_axis_sign)
    relative_roll = normalize_angle_rad(roll - zero_roll)
    relative_pitch = normalize_angle_rad(pitch - zero_pitch)
    return roll, pitch, relative_roll, relative_pitch
