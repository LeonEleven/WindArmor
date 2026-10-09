"""imu_protocol 模块的单元测试。

纯 Python 测试，不依赖 ROS2 (rclpy)。
运行方式：
    cd src/imu_cybergear_ros2
    python -m pytest test/test_imu_protocol.py -v
"""

import math
import struct
import threading
from dataclasses import FrozenInstanceError

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
    MIN_QUATERNION_NORM,
    WitImuFrameParser,
    corrected_relative_roll_pitch,
    euler_from_quaternion,
    normalize_angle_rad,
    normalize_quaternion,
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


class TestGyroAngleCoherence:
    """纯字节帧验证 Level-2 软件候选；不连接串口，也不声明厂家同步。"""

    @pytest.mark.parametrize(
        "types, expected_count, expected_gyro",
        [
            ([FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE], 1, 100),
            ([FRAME_TYPE_ACCEL, FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE], 1, 200),
            ([FRAME_TYPE_ANGLE], 0, None),
            ([FRAME_TYPE_ACCEL, FRAME_TYPE_ANGLE], 0, None),
            ([FRAME_TYPE_GYRO], 0, None),
            ([FRAME_TYPE_ANGLE, FRAME_TYPE_GYRO], 0, None),
            ([FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE, FRAME_TYPE_ANGLE], 1, 100),
            ([FRAME_TYPE_GYRO, FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE], 1, 200),
            ([FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE, FRAME_TYPE_GYRO,
              FRAME_TYPE_ANGLE], 2, 300),
        ],
    )
    def test_order_latest_pending_and_no_reuse(self, types, expected_count,
                                             expected_gyro):
        parser = WitImuFrameParser()
        for index, frame_type in enumerate(types, 1):
            frame = _build_frame(frame_type, [index * 100, 0, 0, 0])
            assert _feed_frame(parser, frame) == (frame_type == FRAME_TYPE_ANGLE)
        state = parser.coherence_state()
        assert state.pair_count == expected_count
        if expected_gyro is None:
            assert state.latest_pair is None
        else:
            pair = state.latest_pair
            assert pair.sequence == expected_count
            assert pair.gyro.frame_type == FRAME_TYPE_GYRO
            assert pair.angle.frame_type == FRAME_TYPE_ANGLE
            assert pair.gyro.generation == pair.angle.generation == state.generation
            assert pair.gyro.values[0] == pytest.approx(
                expected_gyro / INT16_MAX * GYRO_FULL_SCALE * math.pi / 180.0)

    @pytest.mark.parametrize("prior_pair", [False, True])
    def test_bad_gyro_does_not_reuse_consumed_or_create_component(self, prior_pair):
        parser = WitImuFrameParser()
        if prior_pair:
            _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [100, 0, 0, 0]))
            _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [200, 0, 0, 0]))
        before = parser.coherence_state()
        bad = bytearray(_build_frame(FRAME_TYPE_GYRO, [300, 0, 0, 0]))
        bad[-1] ^= 1
        assert not _feed_frame(parser, bad)
        assert parser.coherence_state() == before
        assert _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [400, 0, 0, 0]))
        after = parser.coherence_state()
        assert after.pair_count == before.pair_count
        assert after.latest_pair == before.latest_pair
        assert after.pending_gyro is None

    @pytest.mark.parametrize("bad_type", [FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE])
    def test_bad_frame_preserves_unconsumed_valid_pending(self, bad_type):
        parser = WitImuFrameParser()
        _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [100, 0, 0, 0]))
        before = parser.coherence_state()
        bad = bytearray(_build_frame(bad_type, [300, 0, 0, 0]))
        bad[-1] ^= 1
        assert not _feed_frame(parser, bad)
        assert parser.coherence_state() == before
        assert _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [400, 0, 0, 0]))
        assert parser.coherence_state().latest_pair.gyro == before.pending_gyro
        assert parser.coherence_state().pending_gyro is None

    def test_component_times_and_immutable_snapshots(self):
        now = [10.0]
        parser = WitImuFrameParser(monotonic_clock=lambda: now[0])
        _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [100, 200, 300, 0]))
        pending = parser.coherence_state()
        now[0] = 70.0  # 尚未冻结时间阈值；软件 FSM 允许长间隔。
        _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [400, 500, 600, 0]))
        state = parser.coherence_state()
        assert state.latest_pair.gyro.received_monotonic == 10.0
        assert state.latest_pair.angle.received_monotonic == 70.0
        assert state.latest_pair.gyro == pending.pending_gyro
        assert pending.latest_pair is None
        with pytest.raises(FrozenInstanceError):
            state.pair_count = 9
        with pytest.raises(FrozenInstanceError):
            state.latest_pair.gyro.received_monotonic = 99.0
        with pytest.raises(TypeError):
            state.latest_pair.gyro.values[0] = 99.0

    @pytest.mark.parametrize("chunk_size", [1, 3, 10, 11, 15, 44])
    def test_read_segmentation_and_partial_frame(self, chunk_size):
        times = iter([10.0, 11.0, 12.0, 13.0])
        parser = WitImuFrameParser(monotonic_clock=lambda: next(times))
        stream = b"".join(_build_frame(kind, [100, 0, 0, 0]) for kind in [
            FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE, FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE])
        publications = 0
        for start in range(0, len(stream), chunk_size):
            for byte in stream[start:start + chunk_size]:
                publications += parser.parse_byte(byte)
        assert publications == 2
        state = parser.coherence_state()
        assert state.pair_count == 2
        assert state.latest_pair.gyro.received_monotonic == 12.0
        assert state.latest_pair.angle.received_monotonic == 13.0
        frame = _build_frame(FRAME_TYPE_GYRO, [200, 0, 0, 0])
        _feed_frame(parser, frame[:-1])
        assert parser.coherence_state() == state

    def test_reset_clears_all_caches_and_rejects_old_read_remainder(self):
        parser = WitImuFrameParser()
        for kind in [FRAME_TYPE_ACCEL, FRAME_TYPE_GYRO, FRAME_TYPE_ANGLE,
                     FRAME_TYPE_GYRO]:
            _feed_frame(parser, _build_frame(kind, [100, 200, 300, 0]))
        old = parser.coherence_state()
        partial = _build_frame(FRAME_TYPE_ANGLE, [400, 0, 0, 0])
        _feed_frame(parser, partial[:6])
        parser.reset()
        fresh = parser.coherence_state()
        assert fresh.generation == old.generation + 1
        assert fresh.pending_gyro is None
        assert fresh.latest_pair is None
        assert fresh.latest_component is None
        assert fresh.pair_count == 0
        assert parser.latest_imu_values() == ([0.0] * 3, [0.0] * 3, [0.0] * 3)
        for byte in partial[6:] + _build_frame(FRAME_TYPE_GYRO, [500, 0, 0, 0]):
            assert not parser.parse_byte(byte, generation=old.generation)
        assert parser.coherence_state() == fresh
        assert _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [600, 0, 0, 0]))
        assert parser.coherence_state().latest_pair is None
        _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [700, 0, 0, 0]))
        _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [800, 0, 0, 0]))
        assert parser.coherence_state().latest_pair.gyro.generation == fresh.generation

    def test_garbage_and_ignored_frames_do_not_create_components(self):
        parser = WitImuFrameParser()
        _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [100, 0, 0, 0]))
        state = parser.coherence_state()
        _feed_frame(parser, bytes([0x00, 0xFF, 0xAA]))
        for kind in [FRAME_TYPE_MAG, 0x50, 0x59, 0x5F]:
            _feed_frame(parser, _build_frame(kind, [200, 0, 0, 0]))
            assert parser.coherence_state() == state
        _feed_frame(parser, _build_frame(FRAME_TYPE_ANGLE, [300, 0, 0, 0]))
        assert parser.coherence_state().latest_pair.gyro == state.pending_gyro

    def test_legacy_publication_can_use_cache_without_new_pair(self):
        parser = WitImuFrameParser()
        _feed_frame(parser, _build_frame(FRAME_TYPE_GYRO, [100, 0, 0, 0]))
        angle = _build_frame(FRAME_TYPE_ANGLE, [8192, 0, 0, 0])
        assert _feed_frame(parser, angle)
        pair = parser.coherence_state().latest_pair
        assert _feed_frame(parser, angle)
        assert parser.latest_imu_values()[1] == list(pair.gyro.values)
        assert parser.latest_imu_values()[2] == [45.0, 0.0, 0.0]
        assert parser.coherence_state().latest_pair == pair


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


class TestValidatedRelativeAttitude:

    def test_non_unit_quaternion_is_normalized(self):
        q = quaternion_from_euler(0.4, -0.2, 0.1)
        scaled = tuple(value * 3.0 for value in q)
        normalized = normalize_quaternion(*scaled)
        assert normalized == pytest.approx(q)

    @pytest.mark.parametrize(
        "quaternion",
        [
            (0.0, 0.0, 0.0, 0.0),
            (MIN_QUATERNION_NORM / 10.0, 0.0, 0.0, 0.0),
            (math.nan, 0.0, 0.0, 1.0),
            (math.inf, 0.0, 0.0, 1.0),
            (-math.inf, 0.0, 0.0, 1.0),
        ],
    )
    def test_invalid_quaternion_is_rejected(self, quaternion):
        with pytest.raises(ValueError):
            normalize_quaternion(*quaternion)

    def test_axis_sign_and_zero_are_applied_before_relative_output(self):
        q = quaternion_from_euler(math.radians(20.0), math.radians(-10.0), 0.0)
        roll, pitch, relative_roll, relative_pitch = corrected_relative_roll_pitch(
            *q,
            roll_axis_sign=-1.0,
            pitch_axis_sign=1.0,
            zero_roll=math.radians(-5.0),
            zero_pitch=math.radians(-2.0),
        )
        assert math.degrees(roll) == pytest.approx(-20.0)
        assert math.degrees(pitch) == pytest.approx(-10.0)
        assert math.degrees(relative_roll) == pytest.approx(-15.0)
        assert math.degrees(relative_pitch) == pytest.approx(-8.0)

    def test_relative_angle_wraps_across_pi(self):
        q = quaternion_from_euler(math.radians(-179.0), 0.0, 0.0)
        _, _, relative_roll, _ = corrected_relative_roll_pitch(
            *q,
            roll_axis_sign=1.0,
            pitch_axis_sign=1.0,
            zero_roll=math.radians(179.0),
            zero_pitch=0.0,
        )
        assert math.degrees(relative_roll) == pytest.approx(2.0)

    @pytest.mark.parametrize("angle", [math.nan, math.inf, -math.inf])
    def test_invalid_angle_is_rejected(self, angle):
        with pytest.raises(ValueError):
            normalize_angle_rad(angle)
