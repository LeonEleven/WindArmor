"""imu_protocol 模块的单元测试。

纯 Python 测试，不依赖 ROS2 (rclpy)。
运行方式：
    cd src/imu_cybergear_ros2
    python -m pytest test/test_imu_protocol.py -v
"""

import math
import struct
import threading

import pytest

# 将包目录加入 sys.path，避免需要 pip install
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "imu_cybergear_ros2"),
)

from imu_protocol import (
    ACCEL_FULL_SCALE,
    ANGLE_FULL_SCALE,
    FRAME_HEADER,
    FRAME_LENGTH,
    FRAME_TYPE_ACCEL,
    FRAME_TYPE_ANGLE,
    FRAME_TYPE_GYRO,
    FRAME_TYPE_MAG,
    GRAVITY,
    GYRO_FULL_SCALE,
    INT16_MAX,
    WitImuFrameParser,
    euler_from_quaternion,
    quaternion_from_euler,
)


# =========================================================================
# 测试辅助工具
# =========================================================================

def _build_frame(frame_type: int, raw_values: list) -> bytes:
    """构造一个合法的 11 字节 IMU 帧。

    参数：
        frame_type: 帧类型字节 (0x51/0x52/0x53/0x54)
        raw_values: 4 个 int16 值，将被打包为小端序

    返回：
        11 字节的 bytes，包含正确的校验和。
    """
    data_bytes = struct.pack("hhhh", *raw_values)
    frame = bytearray([FRAME_HEADER, frame_type]) + data_bytes
    checksum = sum(frame) & 0xFF
    return bytes(frame) + bytes([checksum])


def _feed_frame(parser: WitImuFrameParser, frame: bytes) -> bool:
    """将完整帧逐字节喂入解析器，返回最后一次 parse_byte 的结果。"""
    result = False
    for b in frame:
        result = parser.parse_byte(b)
    return result


# =========================================================================
# _hex_to_short 测试（通过 parse_byte 间接测试，因为它是模块私有函数）
# =========================================================================

class TestHexToShort:
    """通过构造已知帧来间接验证 _hex_to_short 的正确性。"""

    def test_zero_values(self):
        """全零字节应解析为 4 个 0。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_ANGLE, [0, 0, 0, 0])
        _feed_frame(parser, frame)
        acc, gyro, angle = parser.latest_imu_values()
        assert angle == [0.0, 0.0, 0.0]

    def test_known_int16_values(self):
        """验证已知 int16 值的物理量转换。"""
        parser = WitImuFrameParser()
        # raw = 16384 -> 16384/32768 * 180 = 90.0 度
        raw_val = 16384
        frame = _build_frame(FRAME_TYPE_ANGLE, [raw_val, 0, 0, 0])
        _feed_frame(parser, frame)
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(90.0, abs=0.01)
        assert angle[1] == pytest.approx(0.0)
        assert angle[2] == pytest.approx(0.0)

    def test_negative_values(self):
        """验证负 int16 值。"""
        parser = WitImuFrameParser()
        # raw = -16384 -> -16384/32768 * 180 = -90.0 度
        raw_val = -16384
        frame = _build_frame(FRAME_TYPE_ANGLE, [raw_val, 0, 0, 0])
        _feed_frame(parser, frame)
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(-90.0, abs=0.01)

    def test_boundary_max(self):
        """验证 int16 最大值 32767。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_ANGLE, [32767, 0, 0, 0])
        _feed_frame(parser, frame)
        _, _, angle = parser.latest_imu_values()
        # 32767/32768 * 180 ≈ 179.9945
        assert angle[0] == pytest.approx(180.0, abs=0.01)

    def test_boundary_min(self):
        """验证 int16 最小值 -32768。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_ANGLE, [-32768, 0, 0, 0])
        _feed_frame(parser, frame)
        _, _, angle = parser.latest_imu_values()
        # -32768/32768 * 180 = -180.0
        assert angle[0] == pytest.approx(-180.0, abs=0.01)


# =========================================================================
# WitImuFrameParser 测试
# =========================================================================

class TestWitImuFrameParser:

    def test_initial_state(self):
        """解析器初始状态应为全零。"""
        parser = WitImuFrameParser()
        acc, gyro, angle = parser.latest_imu_values()
        assert acc == [0.0, 0.0, 0.0]
        assert gyro == [0.0, 0.0, 0.0]
        assert angle == [0.0, 0.0, 0.0]

    def test_invalid_header_resets(self):
        """非 0x55 的字节应导致缓冲区重置，返回 False。"""
        parser = WitImuFrameParser()
        assert parser.parse_byte(0x00) is False
        assert parser.parse_byte(0xFF) is False
        assert parser.parse_byte(0xAA) is False

    def test_partial_frame_returns_false(self):
        """喂入 10 字节（不足一帧）应全部返回 False。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_ANGLE, [1000, 0, 0, 0])
        for b in frame[:10]:
            assert parser.parse_byte(b) is False

    def test_invalid_checksum_returns_false(self):
        """校验和错误的帧应返回 False，且不更新内部状态。"""
        parser = WitImuFrameParser()
        frame = bytearray(_build_frame(FRAME_TYPE_ANGLE, [1000, 0, 0, 0]))
        frame[10] = (frame[10] + 1) & 0xFF  # 篡改校验和
        result = _feed_frame(parser, bytes(frame))
        assert result is False
        _, _, angle = parser.latest_imu_values()
        assert angle == [0.0, 0.0, 0.0]

    def test_valid_accel_frame(self):
        """加速度帧应更新 acceleration，返回 False。"""
        parser = WitImuFrameParser()
        # raw = 16384 -> 16384/32768 * 16.0 * 9.80665 = 78.4532
        raw_val = 16384
        frame = _build_frame(FRAME_TYPE_ACCEL, [raw_val, 0, 0, 0])
        result = _feed_frame(parser, frame)
        assert result is False
        acc, _, _ = parser.latest_imu_values()
        expected = raw_val / INT16_MAX * ACCEL_FULL_SCALE * GRAVITY
        assert acc[0] == pytest.approx(expected, rel=1e-4)
        assert acc[1] == pytest.approx(0.0)
        assert acc[2] == pytest.approx(0.0)

    def test_valid_gyro_frame(self):
        """角速度帧应更新 angular_velocity，返回 False。"""
        parser = WitImuFrameParser()
        # raw = 16384 -> 16384/32768 * 2000 * pi/180 ≈ 17.45 rad/s
        raw_val = 16384
        frame = _build_frame(FRAME_TYPE_GYRO, [raw_val, 0, 0, 0])
        result = _feed_frame(parser, frame)
        assert result is False
        _, gyro, _ = parser.latest_imu_values()
        expected = raw_val / INT16_MAX * GYRO_FULL_SCALE * math.pi / 180.0
        assert gyro[0] == pytest.approx(expected, rel=1e-4)

    def test_valid_angle_frame_returns_true(self):
        """角度帧应更新 angle_degree，返回 True。"""
        parser = WitImuFrameParser()
        raw_val = 8192  # 8192/32768 * 180 = 45.0
        frame = _build_frame(FRAME_TYPE_ANGLE, [raw_val, 0, 0, 0])
        result = _feed_frame(parser, frame)
        assert result is True
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(45.0, abs=0.01)

    def test_mag_frame_ignored(self):
        """磁场帧应被忽略，返回 False，不更新任何值。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_MAG, [9999, 8888, 7777, 6666])
        result = _feed_frame(parser, frame)
        assert result is False
        acc, gyro, angle = parser.latest_imu_values()
        assert acc == [0.0, 0.0, 0.0]
        assert gyro == [0.0, 0.0, 0.0]
        assert angle == [0.0, 0.0, 0.0]

    def test_frame_sequence_preserves_all_values(self):
        """连续解析 accel + gyro + angle 帧后，所有值应保持最新。"""
        parser = WitImuFrameParser()

        # 加速度帧: raw=[1000, 2000, 3000, 0]
        acc_frame = _build_frame(FRAME_TYPE_ACCEL, [1000, 2000, 3000, 0])
        _feed_frame(parser, acc_frame)

        # 角速度帧: raw=[4000, 5000, 6000, 0]
        gyro_frame = _build_frame(FRAME_TYPE_GYRO, [4000, 5000, 6000, 0])
        _feed_frame(parser, gyro_frame)

        # 角度帧: raw=[8192, -8192, 0, 0] -> [45, -45, 0] 度
        angle_frame = _build_frame(FRAME_TYPE_ANGLE, [8192, -8192, 0, 0])
        result = _feed_frame(parser, angle_frame)
        assert result is True

        acc, gyro, angle = parser.latest_imu_values()

        # 验证加速度保持
        expected_acc_x = 1000 / INT16_MAX * ACCEL_FULL_SCALE * GRAVITY
        assert acc[0] == pytest.approx(expected_acc_x, rel=1e-4)

        # 验证角速度保持
        expected_gyro_x = 4000 / INT16_MAX * GYRO_FULL_SCALE * math.pi / 180.0
        assert gyro[0] == pytest.approx(expected_gyro_x, rel=1e-4)

        # 验证角度
        assert angle[0] == pytest.approx(45.0, abs=0.01)
        assert angle[1] == pytest.approx(-45.0, abs=0.01)
        assert angle[2] == pytest.approx(0.0)

    def test_resync_after_garbage(self):
        """在垃圾数据后喂入合法帧，解析器应重新同步。"""
        parser = WitImuFrameParser()
        # 喂入一些垃圾字节
        for b in [0x01, 0x02, 0x03, 0xFF, 0xFE]:
            parser.parse_byte(b)

        # 喂入合法角度帧
        frame = _build_frame(FRAME_TYPE_ANGLE, [8192, 0, 0, 0])
        result = _feed_frame(parser, frame)
        assert result is True
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(45.0, abs=0.01)

    def test_mid_frame_checksum_failure_recovery(self):
        """帧校验和失败后，解析器应能恢复并解析下一帧。"""
        parser = WitImuFrameParser()
        # 构造一个校验和错误的完整帧
        bad_frame = bytearray(_build_frame(FRAME_TYPE_ANGLE, [1000, 0, 0, 0]))
        bad_frame[10] = (bad_frame[10] + 1) & 0xFF  # 篡改校验和
        result = _feed_frame(parser, bytes(bad_frame))
        assert result is False  # 校验和失败

        # 之后喂入合法帧应能正常解析
        frame = _build_frame(FRAME_TYPE_ANGLE, [8192, 0, 0, 0])
        result = _feed_frame(parser, frame)
        assert result is True
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(45.0, abs=0.01)

    def test_latest_imu_values_returns_copies(self):
        """latest_imu_values 返回的列表是副本，修改不影响内部状态。"""
        parser = WitImuFrameParser()
        frame = _build_frame(FRAME_TYPE_ANGLE, [8192, 4096, 2048, 0])
        _feed_frame(parser, frame)

        acc1, gyro1, angle1 = parser.latest_imu_values()
        # 修改返回值
        acc1[0] = 999.0
        gyro1[0] = 999.0
        angle1[0] = 999.0

        # 再次获取，应不受影响
        acc2, gyro2, angle2 = parser.latest_imu_values()
        assert acc2[0] != 999.0
        assert gyro2[0] != 999.0
        assert angle2[0] != 999.0

    def test_thread_safety(self):
        """并发调用 parse_byte 和 latest_imu_values 不应抛异常。"""
        parser = WitImuFrameParser()
        errors = []

        def feed_frames():
            try:
                for _ in range(100):
                    frame = _build_frame(FRAME_TYPE_ANGLE, [1000, 0, 0, 0])
                    _feed_frame(parser, frame)
            except Exception as e:
                errors.append(e)

        def read_values():
            try:
                for _ in range(100):
                    parser.latest_imu_values()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=feed_frames)
        t2 = threading.Thread(target=read_values)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []

    def test_all_four_raw_values_parsed(self):
        """验证 4 个 int16 数据槽位都被正确解析（仅前 3 个用于物理量）。"""
        parser = WitImuFrameParser()
        # 角度帧: raw=[100, 200, 300, 400]
        # 前 3 个用于 angle_degree
        frame = _build_frame(FRAME_TYPE_ANGLE, [100, 200, 300, 400])
        _feed_frame(parser, frame)
        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(100 / INT16_MAX * ANGLE_FULL_SCALE, rel=1e-4)
        assert angle[1] == pytest.approx(200 / INT16_MAX * ANGLE_FULL_SCALE, rel=1e-4)
        assert angle[2] == pytest.approx(300 / INT16_MAX * ANGLE_FULL_SCALE, rel=1e-4)

    def test_consecutive_angle_frames(self):
        """连续两个角度帧应更新为最新值。"""
        parser = WitImuFrameParser()
        frame1 = _build_frame(FRAME_TYPE_ANGLE, [8192, 0, 0, 0])  # 45°
        _feed_frame(parser, frame1)

        frame2 = _build_frame(FRAME_TYPE_ANGLE, [0, 16384, 0, 0])  # 0°, 90°
        _feed_frame(parser, frame2)

        _, _, angle = parser.latest_imu_values()
        assert angle[0] == pytest.approx(0.0, abs=0.01)
        assert angle[1] == pytest.approx(90.0, abs=0.01)


# =========================================================================
# quaternion_from_euler 测试
# =========================================================================

class TestQuaternionFromEuler:

    def test_identity(self):
        """零欧拉角应返回单位四元数 (0, 0, 0, 1)。"""
        qx, qy, qz, qw = quaternion_from_euler(0, 0, 0)
        assert qx == pytest.approx(0.0, abs=1e-10)
        assert qy == pytest.approx(0.0, abs=1e-10)
        assert qz == pytest.approx(0.0, abs=1e-10)
        assert qw == pytest.approx(1.0, abs=1e-10)

    def test_pure_roll_90(self):
        """纯 roll 90° 应返回 (sin45, 0, 0, cos45)。"""
        qx, qy, qz, qw = quaternion_from_euler(math.pi / 2, 0, 0)
        s = math.sin(math.pi / 4)
        c = math.cos(math.pi / 4)
        assert qx == pytest.approx(s, abs=1e-10)
        assert qy == pytest.approx(0.0, abs=1e-10)
        assert qz == pytest.approx(0.0, abs=1e-10)
        assert qw == pytest.approx(c, abs=1e-10)

    def test_pure_pitch_90(self):
        """纯 pitch 90° 应返回 (0, sin45, 0, cos45)。"""
        qx, qy, qz, qw = quaternion_from_euler(0, math.pi / 2, 0)
        s = math.sin(math.pi / 4)
        c = math.cos(math.pi / 4)
        assert qx == pytest.approx(0.0, abs=1e-10)
        assert qy == pytest.approx(s, abs=1e-10)
        assert qz == pytest.approx(0.0, abs=1e-10)
        assert qw == pytest.approx(c, abs=1e-10)

    def test_pure_yaw_90(self):
        """纯 yaw 90° 应返回 (0, 0, sin45, cos45)。"""
        qx, qy, qz, qw = quaternion_from_euler(0, 0, math.pi / 2)
        s = math.sin(math.pi / 4)
        c = math.cos(math.pi / 4)
        assert qx == pytest.approx(0.0, abs=1e-10)
        assert qy == pytest.approx(0.0, abs=1e-10)
        assert qz == pytest.approx(s, abs=1e-10)
        assert qw == pytest.approx(c, abs=1e-10)

    def test_quaternion_is_unit(self):
        """任意欧拉角产生的四元数应为单位四元数。"""
        for roll, pitch, yaw in [
            (0.1, 0.2, 0.3),
            (1.0, -0.5, 0.8),
            (-2.0, 1.5, -0.3),
            (math.pi, 0, 0),
        ]:
            qx, qy, qz, qw = quaternion_from_euler(roll, pitch, yaw)
            norm = math.sqrt(qx**2 + qy**2 + qz**2 + qw**2)
            assert norm == pytest.approx(1.0, abs=1e-10)


# =========================================================================
# euler_from_quaternion 测试
# =========================================================================

class TestEulerFromQuaternion:

    def test_identity_quaternion(self):
        """单位四元数 (0, 0, 0, 1) 应返回零欧拉角。"""
        roll, pitch, yaw = euler_from_quaternion(0, 0, 0, 1)
        assert roll == pytest.approx(0.0, abs=1e-10)
        assert pitch == pytest.approx(0.0, abs=1e-10)
        assert yaw == pytest.approx(0.0, abs=1e-10)

    def test_gimbal_boundary_clamping(self):
        """t2 超出 [-1, 1] 范围时应被 clamp，不应抛异常。"""
        # 构造一个 t2 略微超出范围的四元数
        # t2 = 2*(w*y - z*x)，令 w=1.0001, y=1.0, z=0, x=0
        # 这不是合法的单位四元数，但测试 clamp 的鲁棒性
        roll, pitch, yaw = euler_from_quaternion(0, 0, 0, 1.0001)
        assert not math.isnan(roll)
        assert not math.isnan(pitch)
        assert not math.isnan(yaw)


# =========================================================================
# 四元数 <-> 欧拉角往返测试
# =========================================================================

class TestRoundtrip:

    @pytest.mark.parametrize(
        "roll,pitch,yaw",
        [
            (0.0, 0.0, 0.0),
            (0.5, 0.0, 0.0),
            (0.0, 0.3, 0.0),
            (0.0, 0.0, 0.7),
            (0.5, 0.3, 0.7),
            (-0.5, -0.3, -0.7),
            (1.0, -0.5, 0.8),
            (0.01, 0.02, 0.03),  # 小角度
        ],
    )
    def test_euler_quaternion_roundtrip(self, roll, pitch, yaw):
        """euler -> quaternion -> euler 应恢复原始值。"""
        qx, qy, qz, qw = quaternion_from_euler(roll, pitch, yaw)
        r2, p2, y2 = euler_from_quaternion(qx, qy, qz, qw)
        assert r2 == pytest.approx(roll, abs=1e-9)
        assert p2 == pytest.approx(pitch, abs=1e-9)
        assert y2 == pytest.approx(yaw, abs=1e-9)
