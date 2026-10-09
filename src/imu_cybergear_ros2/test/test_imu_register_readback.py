"""离线配置规则与 fake serial；不连接真实串口，不模拟已证明的事务关联。"""

from dataclasses import FrozenInstanceError
import struct

import pytest
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.imu_protocol import (
    CONFIGURATION_REGISTERS, MODULE_BAUD_CODES, WitImuFrameParser,
    check_imu_configuration, decode_register_response, encode_readaddr,
)
from .test_imu_driver_coherence import (
    ANGLE, GYRO, FakeSerial, ImmediateStopEvent, configured_node,
    ros_context, run_reader,
)


def response(words=(0xFFFF, 0x8000, 0x1234, 0)):
    data = b"\x55\x5f" + struct.pack("<4H", *words)
    return data + bytes((sum(data) & 0xFF,))


def feed(parser, data, **kwargs):
    return [parser.parse_byte(byte, **kwargs) for byte in data]


def addressed_fixture(baud_code=2):
    # 地址由软件 fixture 独立指定，绝不由匿名 0x5F 推断。
    words = {address: 0xFFFF for _, address in CONFIGURATION_REGISTERS}
    words.update({0x02: 0x0C, 0x04: baud_code, 0x20: 3})
    return words


@pytest.mark.parametrize("address", [0, 2, 0x20, 0xFC])
def test_readaddr_encoding_only(address):
    assert encode_readaddr(address) == bytes((0xFF, 0xAA, 0x27, address, 0))


@pytest.mark.parametrize("address", [-1, 0xFD, 256, True, 2.0, "2"])
def test_invalid_readaddr_rejected(address):
    with pytest.raises(ValueError):
        encode_readaddr(address)


def test_response_unsigned_little_endian_words():
    assert decode_register_response(response()) == (65535, 32768, 4660, 0)


@pytest.mark.parametrize("frame", [b"", response()[:6], response() + b"\x00",
                                  ANGLE, response()[:-1] + b"\x00"])
def test_response_shape_type_checksum_fail_closed(frame):
    with pytest.raises(ValueError):
        decode_register_response(frame)


@pytest.mark.parametrize("split", range(1, 11))
def test_split_response_and_interleaved_regular_frames(split):
    parser = WitImuFrameParser(monotonic_clock=lambda: 12.0, generation=7)
    assert not any(feed(parser, GYRO + response()[:split]))
    assert parser.register_response_state().latest_response is None
    assert any(feed(parser, response()[split:] + ANGLE))
    registers = parser.register_response_state()
    assert registers.generation == 7
    assert registers.response_count == 1
    assert not registers.partial_response
    assert registers.latest_response.words == decode_register_response(response())
    assert registers.latest_response.received_monotonic == 12.0
    assert registers.latest_response.generation == 7
    assert parser.coherence_state().pair_count == 1
    assert parser.coherence_state().latest_component.frame_type == 0x53
    with pytest.raises(FrozenInstanceError):
        registers.latest_response.generation = 9


def test_bad_response_keeps_only_explicit_history_and_preserves_pending_gyro():
    parser = WitImuFrameParser()
    feed(parser, response() + GYRO)
    previous = parser.register_response_state().latest_response
    feed(parser, response()[:-1] + b"\x00" + ANGLE)
    state = parser.register_response_state()
    assert state.response_count == 1
    assert state.checksum_failure_count == 1
    assert state.latest_response == previous
    assert parser.coherence_state().pair_count == 1


def test_duplicate_unsolicited_responses_are_anonymous_history_only():
    parser = WitImuFrameParser()
    feed(parser, response() * 2)
    state = parser.register_response_state()
    assert state.response_count == 2
    assert not hasattr(state.latest_response, "start_address")
    assert not hasattr(state, "validation_generation")
    assert parser.coherence_state().latest_pair is None
    # 部分窗口或匿名帧不能使完整配置通过；缺失项明确可见。
    check = check_imu_configuration({0x02: 0x0C, 0x04: 2}, host_baud=9600)
    assert not check.required_values_passed
    assert check.missing_required == ("GYRORANGE",)
    assert not check.observation_complete


def test_reset_discards_register_history_partial_bytes_and_late_old_read():
    parser = WitImuFrameParser()
    feed(parser, response() + GYRO + ANGLE + response()[:6])
    old = parser.register_response_state()
    assert old.partial_response
    parser.reset()
    assert not any(feed(parser, response()[6:] + response(), generation=old.generation))
    new = parser.register_response_state()
    assert new.generation > old.generation
    assert new.latest_response is None
    assert new.response_count == new.checksum_failure_count == 0
    assert not new.partial_response
    assert parser.coherence_state().latest_pair is None


@pytest.mark.parametrize("code,baud", MODULE_BAUD_CODES)
def test_actual_host_baud_equality_not_fixed_9600(code, baud):
    result = check_imu_configuration(addressed_fixture(code), host_baud=baud)
    assert result.required_values_passed
    assert result.observation_complete
    assert result.failures == result.missing_required == result.missing_provenance == ()


@pytest.mark.parametrize("address,value,reason", [
    (0x02, 4, "RSW"), (0x02, 8, "RSW"), (0x20, 2, "GYRORANGE"),
    (0x04, 6, "BAUD"), (0x04, 0, "BAUD"),
])
def test_frozen_required_mismatch(address, value, reason):
    words = addressed_fixture()
    words[address] = value
    result = check_imu_configuration(words, host_baud=9600)
    assert not result.required_values_passed
    assert result.observation_complete  # 完整观察不等于规则检查通过。
    assert len(result.failures) == 1
    assert reason in result.failures[0]


def test_nondefault_provenance_and_signed_offset_words_are_not_errors():
    words = addressed_fixture()
    words.update({0x08: 0xFFFF, 0x09: 42, 0x0A: 0x8000})
    result = check_imu_configuration(words, host_baud=9600)
    assert result.required_values_passed and result.observation_complete
    assert ("GXOFFSET", 0x08, 0xFFFF) in result.observed_registers
    words.clear()
    assert len(result.observed_registers) == len(CONFIGURATION_REGISTERS)
    with pytest.raises(FrozenInstanceError):
        result.required_values_passed = False


def test_required_checks_pass_separately_from_provenance_completeness():
    result = check_imu_configuration({0x02: 0x0C, 0x04: 2, 0x20: 3}, host_baud=9600)
    assert result.required_values_passed
    assert not result.observation_complete
    assert "RRATE" in result.missing_provenance
    assert "GYROCALTIME" in result.missing_provenance


@pytest.mark.parametrize("words,baud", [({2: -1}, 9600), ({2: 65536}, 9600),
                                      ({256: 0}, 9600), ({2: True}, 9600),
                                      ({2: 1.0}, 9600), ({}, 0), ({}, True)])
def test_invalid_offline_input_rejected(words, baud):
    with pytest.raises(ValueError):
        check_imu_configuration(words, host_baud=baud)


class ReadOnlyFakeSerial(FakeSerial):
    def write(self, _data):
        raise AssertionError("默认 driver 不得发送 READADDR 或配置写命令")


def test_fake_serial_uses_existing_reader_without_any_new_writes(configured_node, monkeypatch):
    node, capture, _ = configured_node
    node._stop_event = ImmediateStopEvent()
    connection = ReadOnlyFakeSerial([GYRO + response() + ANGLE], node._stop_event)
    run_reader(node, monkeypatch, [connection])
    assert len(capture.messages) == 1
    assert capture.states[0].pair_count == 1
    assert node._parser.register_response_state().response_count == 1
    assert capture.messages[0].angular_velocity.x != 0.0


def test_fake_reconnect_and_deactivate_clear_anonymous_history(configured_node, monkeypatch):
    node, capture, _ = configured_node
    node._stop_event = ImmediateStopEvent()
    first = ReadOnlyFakeSerial([response() + GYRO + ANGLE,
                                OSError("fake disconnect")], node._stop_event)
    second = ReadOnlyFakeSerial([ANGLE], node._stop_event)
    run_reader(node, monkeypatch, [first, second])
    assert first.closed
    assert [state.pair_count for state in capture.states] == [1, 0]
    state = node._parser.register_response_state()
    assert state.latest_response is None and state.response_count == 0
    feed(node._parser, response())
    generation = node._parser.register_response_state().generation
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    assert node._parser.register_response_state().generation > generation
    assert node._parser.register_response_state().latest_response is None
