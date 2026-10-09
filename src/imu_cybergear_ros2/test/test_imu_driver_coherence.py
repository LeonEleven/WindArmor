"""进程内 driver/lifecycle 回归；serial.Serial 在所有测试中均被替换。

不启动硬件节点/launch，不连接真实串口、CAN 或 GPIO。
"""

from collections import deque
import math
import os
import threading

import pytest
import rclpy
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2 import imu_driver_node as driver_module
from imu_cybergear_ros2.imu_protocol import (
    FRAME_TYPE_ACCEL, FRAME_TYPE_ANGLE, FRAME_TYPE_GYRO, WitImuFrameParser,
    quaternion_from_euler,
)
from .test_imu_protocol import _build_frame


ACCEL = _build_frame(FRAME_TYPE_ACCEL, [100, 200, 300, 0])
GYRO = _build_frame(FRAME_TYPE_GYRO, [400, 500, 600, 0])
ANGLE = _build_frame(FRAME_TYPE_ANGLE, [8192, 0, 0, 0])


class CapturePublisher:
    def __init__(self, node):
        self.node = node
        self.messages = []
        self.states = []

    def publish(self, message):
        self.messages.append(message)
        self.states.append(self.node.coherence_state())


class ImmediateStopEvent:
    """同步 reader 场景的可控等待；无实际退避或无限循环。"""

    def __init__(self):
        self.stopped = False

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, _timeout):
        return self.stopped


class FakeSerial:
    def __init__(self, chunks, stop_event, *, fault_at="read", before_read=None):
        self.chunks = deque(chunks)
        self.stop_event = stop_event
        self.fault_at = fault_at
        self.before_read = before_read
        self.is_open = True
        self.closed = False

    @property
    def in_waiting(self):
        if not self.chunks:
            self.stop_event.set()
            return 0
        item = self.chunks[0]
        if isinstance(item, Exception):
            if self.fault_at == "waiting":
                raise self.chunks.popleft()
            return 1
        return len(item)

    def read(self, count):
        item = self.chunks.popleft()
        if isinstance(item, Exception):
            raise item
        assert count == len(item)
        if self.before_read is not None:
            callback, self.before_read = self.before_read, None
            callback()
        return item

    def close(self):
        self.is_open = False
        self.closed = True


@pytest.fixture(scope="module", autouse=True)
def ros_context():
    os.environ["ROS_LOG_DIR"] = "/tmp"
    if not rclpy.ok():
        rclpy.init()
    yield
    if rclpy.ok():
        rclpy.shutdown()


@pytest.fixture
def configured_node(monkeypatch):
    def reject_real_serial(**_kwargs):
        raise AssertionError("真实串口构造器禁止进入测试")

    monkeypatch.setattr(driver_module.serial, "Serial", reject_real_serial)
    node = driver_module.ImuDriverNode()
    assert node.coherence_state() is None
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    imu_pub, status_pub = node._imu_pub, node._status_pub
    capture = CapturePublisher(node)
    status = CapturePublisher(node)
    capture.original, status.original = imu_pub, status_pub
    node._imu_pub, node._status_pub = capture, status
    try:
        yield node, capture, status
    finally:
        node.on_deactivate(None)
        if node._imu_pub is capture:
            node._imu_pub = imu_pub
        if node._status_pub is status:
            node._status_pub = status_pub
        node.on_cleanup(None)
        node.destroy_node()


def run_reader(node, monkeypatch, connections):
    remaining = iter(connections)

    def factory(**_kwargs):
        return next(remaining)

    monkeypatch.setattr(driver_module.serial, "Serial", factory)
    node._is_active = True
    node._reader_loop()


@pytest.mark.parametrize("chunk_size", [1, 5, 11, 44])
def test_fake_read_chunks_preserve_pairs_and_legacy_ros_messages(
        configured_node, monkeypatch, chunk_size):
    node, capture, _ = configured_node
    node._stop_event = ImmediateStopEvent()
    times = iter([10.0, 11.0, 13.0, 17.0])
    node._parser = WitImuFrameParser(monotonic_clock=lambda: next(times))
    data = ACCEL + GYRO + ANGLE + ANGLE
    chunks = [data[start:start + chunk_size]
              for start in range(0, len(data), chunk_size)]
    connection = FakeSerial(chunks, node._stop_event)
    run_reader(node, monkeypatch, [connection])
    assert len(capture.messages) == 2
    assert [state.pair_count for state in capture.states] == [1, 1]
    pair = capture.states[0].latest_pair
    assert pair.gyro.received_monotonic == 11.0
    assert pair.angle.received_monotonic == 13.0
    assert capture.states[1].latest_pair == pair
    for message in capture.messages:
        assert message.header.frame_id == node._frame_id
        assert message.angular_velocity.x == pytest.approx(pair.gyro.values[0])
        assert message.linear_acceleration.x == pytest.approx(
            node._parser.latest_imu_values()[0][0])
        expected = quaternion_from_euler(math.pi / 4, 0.0, 0.0)
        assert (message.orientation.x, message.orientation.y,
                message.orientation.z, message.orientation.w) == pytest.approx(expected)
        assert message.header.stamp.sec > 0


@pytest.mark.parametrize("fault_at", ["read", "waiting"])
@pytest.mark.parametrize("failure", [driver_module.serial.SerialException, OSError])
def test_reconnect_clears_cached_pending_and_partial_bytes(
        configured_node, monkeypatch, fault_at, failure):
    node, capture, status = configured_node
    node._stop_event = ImmediateStopEvent()
    first = FakeSerial([ACCEL + GYRO + ANGLE + GYRO + ANGLE[:6],
                        failure("fake disconnect")],
                       node._stop_event, fault_at=fault_at)
    second = FakeSerial([ANGLE[6:] + ANGLE, GYRO + ANGLE], node._stop_event)
    run_reader(node, monkeypatch, [first, second])
    assert first.closed
    assert [state.pair_count for state in capture.states] == [1, 0, 1]
    old, new_angle, new_pair = capture.states
    assert new_angle.generation > old.generation
    assert new_angle.latest_pair is None
    assert new_angle.pending_gyro is None
    assert capture.messages[1].angular_velocity.x == 0.0
    assert capture.messages[1].linear_acceleration.x == 0.0
    assert new_pair.latest_pair.gyro.generation == new_pair.generation
    assert new_pair.latest_pair.angle.generation == new_pair.generation
    assert "disconnected" in [message.data for message in status.messages]


def test_read_returning_after_reset_cannot_enter_new_generation(configured_node, monkeypatch):
    node, capture, _ = configured_node
    node._stop_event = ImmediateStopEvent()
    connection = FakeSerial([GYRO + ANGLE, ANGLE, GYRO + ANGLE], node._stop_event,
                            before_read=node._parser.reset)
    run_reader(node, monkeypatch, [connection])
    assert [state.pair_count for state in capture.states] == [0, 1]
    assert capture.messages[0].angular_velocity.x == 0.0


def test_lifecycle_deactivate_reactivate_and_cleanup_isolate_generations(
        configured_node, monkeypatch):
    node, capture, _ = configured_node
    first = FakeSerial([GYRO + ANGLE + GYRO + ANGLE[:6]], node._stop_event)
    second = FakeSerial([ANGLE[6:] + ANGLE, GYRO + ANGLE], node._stop_event)
    connections = iter([first, second])
    monkeypatch.setattr(driver_module.serial, "Serial", lambda **_kwargs: next(connections))
    assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
    node._thread.join(timeout=2.0)
    assert not node._thread.is_alive()
    old = node.coherence_state()
    assert old.latest_pair is not None
    assert old.pending_gyro is not None
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    inactive = node.coherence_state()
    assert inactive.generation > old.generation
    assert inactive.latest_pair is None
    assert inactive.pending_gyro is None
    assert inactive.latest_component is None
    assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
    node._thread.join(timeout=2.0)
    assert not node._thread.is_alive()
    assert [state.pair_count for state in capture.states] == [1, 0, 1]
    assert capture.states[1].generation > inactive.generation
    assert first.closed


def test_cleanup_reconfigure_keeps_generation_distinct(configured_node):
    node, capture, status = configured_node
    old_generation = node.coherence_state().generation
    parser = node._parser
    node._imu_pub, node._status_pub = capture.original, status.original
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
    assert node.coherence_state() is None
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    assert node.coherence_state().generation > old_generation
    assert parser.coherence_state().latest_pair is None


def test_transport_closed_without_read_exception_also_clears_pair(configured_node, monkeypatch):
    node, capture, _ = configured_node
    node._stop_event = ImmediateStopEvent()
    first = FakeSerial([GYRO + ANGLE + GYRO + ANGLE[:6]], node._stop_event)
    first.before_read = first.close
    second = FakeSerial([ANGLE, GYRO + ANGLE], node._stop_event)
    run_reader(node, monkeypatch, [first, second])
    assert [state.pair_count for state in capture.states] == [1, 0, 1]
    assert capture.states[1].generation > capture.states[0].generation


def test_stop_during_read_discards_returned_bytes(configured_node, monkeypatch):
    node, capture, _ = configured_node
    connection = FakeSerial([GYRO + ANGLE], node._stop_event,
                            before_read=node._stop_event.set)
    run_reader(node, monkeypatch, [connection])
    assert capture.messages == []
    assert node.coherence_state().pending_gyro is None
    assert node.coherence_state().latest_pair is None


def test_stalled_old_reader_blocks_reactivation_and_discards_late_data(
        configured_node, monkeypatch):
    node, capture, _ = configured_node
    entered, release = threading.Event(), threading.Event()

    def block_read():
        entered.set()
        assert release.wait(timeout=5.0)

    first = FakeSerial([GYRO + ANGLE], node._stop_event, before_read=block_read)
    connections = iter([first, FakeSerial([ANGLE], node._stop_event)])
    monkeypatch.setattr(driver_module.serial, "Serial", lambda **_kwargs: next(connections))
    try:
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        assert entered.wait(timeout=2.0)
        assert node.on_deactivate(None) == TransitionCallbackReturn.FAILURE
        generation = node.coherence_state().generation
        assert node.on_activate(None) == TransitionCallbackReturn.FAILURE
        assert node.coherence_state().generation == generation
    finally:
        release.set()
        node._thread.join(timeout=2.0)
    assert not node._thread.is_alive()
    assert capture.messages == []
    assert node.coherence_state().latest_pair is None
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
    node._thread.join(timeout=2.0)
    assert not node._thread.is_alive()
    assert capture.states[-1].pair_count == 0


def test_failed_connection_attempt_clears_existing_state(configured_node):
    node, _, _ = configured_node
    for byte in GYRO + ANGLE + GYRO + ANGLE[:6]:
        node._parser.parse_byte(byte)
    before = node.coherence_state()
    assert before.latest_pair is not None
    assert before.pending_gyro is not None
    # configured_node fixture 的 reject constructor 被 driver 捕获，无真实串口访问。
    assert not node._try_open_serial()
    after = node.coherence_state()
    assert after.generation > before.generation
    assert after.latest_component is None
    assert after.pending_gyro is None
    assert after.latest_pair is None
    assert node._parser.latest_imu_values() == ([0.0] * 3, [0.0] * 3, [0.0] * 3)


def test_shutdown_clears_pair_and_component_state(configured_node):
    node, capture, status = configured_node
    for byte in GYRO + ANGLE + GYRO + ANGLE[:6]:
        node._parser.parse_byte(byte)
    before = node.coherence_state()
    node._imu_pub, node._status_pub = capture.original, status.original
    assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
    after = node.coherence_state()
    assert after.generation > before.generation
    assert after.latest_pair is None
    assert after.pending_gyro is None
    assert after.latest_component is None


def test_backoff_is_interruptible_and_does_not_reopen_after_stop(configured_node, monkeypatch):
    node, _, _ = configured_node
    waiting = threading.Event()
    attempts = []

    def failed_open(**_kwargs):
        attempts.append(True)
        waiting.set()
        raise OSError("fake unavailable serial")

    monkeypatch.setattr(driver_module.serial, "Serial", failed_open)
    monkeypatch.setattr(driver_module, "INITIAL_RECONNECT_DELAY", 60.0)
    assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
    assert waiting.wait(timeout=2.0)
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    assert attempts == [True]
    assert node._thread is None
    assert node.coherence_state().latest_pair is None
