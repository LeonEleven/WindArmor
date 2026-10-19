"""有界主机假设下的条件性关联测试；所有 serial 构造均被 fake 替代。"""

from dataclasses import FrozenInstanceError
import threading

import pytest
from rclpy.lifecycle import TransitionCallbackReturn

from imu_cybergear_ros2.imu_protocol import WitImuFrameParser, encode_readaddr
from .test_imu_driver_coherence import (
    ACCEL, ANGLE, GYRO, ImmediateStopEvent, configured_node, driver_module,
    ros_context, run_reader,
)
from .test_imu_register_readback import feed, response


FIRST = response((0x027F, 42, 2, 5))  # 额外输出位、非默认 RRATE、非零 AXOFFSET。
SECOND = response((3, 3, 0, 0))


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Session:
    def __init__(self, *, enabled=True, bound=1.0, baud=9600):
        self.clock = Clock()
        self.parser = WitImuFrameParser(
            monotonic_clock=self.clock, readback_enabled=enabled,
            response_bound_sec=bound, host_baud=baud,
        )
        self.writes = []
        self.parser.begin_configuration_readback()

    def send(self, data):
        self.writes.append(data)
        return len(data)

    def advance(self, now, *, drained=True, generation=None, send=None):
        self.clock.now = now
        self.parser.advance_configuration_readback(
            send or self.send,
            generation=(self.parser.coherence_state().generation
                        if generation is None else generation),
            input_drained=drained,
        )

    def receive(self, now, data, **kwargs):
        self.clock.now = now
        feed(self.parser, data, **kwargs)

    @property
    def state(self):
        return self.parser.configuration_state()

    def first(self, data=FIRST):
        self.advance(1.0)
        self.receive(1.1, data)
        self.advance(2.0)

    def complete(self):
        self.first()
        self.receive(2.1, SECOND)
        self.advance(3.0)


def test_two_windows_wait_full_bound_and_require_post_check_new_gyro_angle():
    s = Session()
    s.advance(0.999)
    assert s.writes == []
    s.advance(1.0)
    assert s.writes == [encode_readaddr(2)]
    s.receive(1.1, ACCEL + GYRO + FIRST + ANGLE)
    assert s.parser.coherence_state().pair_count == 1
    s.advance(1.999)
    assert not s.state.config_prerequisite_passed
    assert not s.state.windows
    s.advance(2.0)
    assert len(s.state.windows) == 1
    assert s.writes == [encode_readaddr(2), encode_readaddr(0x20)]
    assert s.state.pending_address == 0x20
    s.receive(2.1, SECOND + GYRO)
    s.advance(2.999)
    assert not s.state.config_prerequisite_passed
    s.advance(3.0)
    checked = s.state
    assert checked.status == "host-associated-checked"
    assert checked.config_prerequisite_passed
    assert checked.check.required_values_passed
    assert not checked.check.observation_complete
    assert checked.check.missing_provenance
    assert checked.post_check_pair is None
    assert checked.checked_monotonic == 3.0
    assert checked.windows[0][1].words[3] == 5
    assert not hasattr(checked.windows[0][1], "start_address")
    s.receive(3.1, ANGLE)  # 即使 legacy pair 成立，验证前的 GYRO 不能通过新 gate。
    assert s.parser.coherence_state().pair_count == 2
    assert s.state.post_check_pair is None
    s.receive(3.2, GYRO + ANGLE + ANGLE)
    assert s.state.post_check_pair == s.parser.coherence_state().latest_pair
    assert s.state.post_check_pair.sequence == 3
    assert s.state.post_check_pair.gyro.received_monotonic >= checked.checked_monotonic
    assert checked.post_check_pair is None  # 快照不随之后的 pair 更新。
    with pytest.raises(FrozenInstanceError):
        checked.status = "ready"


@pytest.mark.parametrize("enabled,bound,status", [
    (False, 1.0, "disabled"), (True, 0.0, "incomplete"),
    (True, -1.0, "incomplete"), (True, float("inf"), "incomplete"),
    (True, float("nan"), "incomplete"), (True, 1e308, "incomplete"),
])
def test_disabled_or_missing_finite_assumption_never_writes(enabled, bound, status):
    s = Session(enabled=enabled, bound=bound)
    s.advance(100)
    s.receive(101, ACCEL + GYRO + ANGLE)
    assert s.writes == []
    assert s.state.status == status
    assert not s.state.config_prerequisite_passed
    assert s.parser.coherence_state().pair_count == 1


@pytest.mark.parametrize("data", [FIRST, FIRST[:2], FIRST[:-1] + b"\x00"])
def test_unsolicited_before_request_latches_ambiguity_without_writes(data):
    s = Session()
    s.receive(0.2, data)
    s.advance(1.0)
    assert s.state.status == "ambiguous"
    assert s.writes == []


@pytest.mark.parametrize("data,status", [
    (b"", "timeout"), (FIRST[:6], "incomplete"),
    (FIRST[:-1] + b"\x00", "ambiguous"),
    (FIRST + FIRST, "ambiguous"), (FIRST + FIRST[:2], "ambiguous"),
])
def test_faults_latch_without_retry_or_partial_success(data, status):
    s = Session()
    s.advance(1.0)
    s.receive(1.1, data)
    s.advance(2.0)
    s.advance(20)
    assert s.state.status == status
    assert not s.state.config_prerequisite_passed
    assert s.writes == [encode_readaddr(2)]


@pytest.mark.parametrize("when", [2.0, 3.0])
def test_response_at_or_after_deadline_is_not_associated(when):
    s = Session()
    s.advance(1.0)
    s.receive(when, FIRST)
    s.advance(when)
    assert s.state.status == "timeout"


@pytest.mark.parametrize("data", [FIRST, FIRST + SECOND, SECOND + FIRST])
def test_late_previous_window_or_duplicate_cannot_complete_next_window(data):
    s = Session()
    s.first()
    s.receive(2.1, data)
    s.advance(3.0)
    assert s.state.status == "ambiguous"
    assert not s.state.config_prerequisite_passed


def test_second_window_response_cannot_be_used_as_first():
    s = Session()
    s.advance(1.0)
    s.receive(1.1, SECOND)
    assert s.state.status == "ambiguous"


def test_only_first_window_times_out_and_remains_ineligible():
    s = Session()
    s.first()
    s.advance(3.0)
    assert s.state.status == "timeout"
    assert len(s.state.windows) == 1
    assert not s.state.config_prerequisite_passed


@pytest.mark.parametrize("data", [SECOND, SECOND[:2], SECOND[:-1] + b"\x00"])
def test_unassociated_traffic_after_check_revokes_pair_and_prerequisite(data):
    s = Session()
    s.complete()
    s.receive(3.1, GYRO + ANGLE)
    assert s.state.post_check_pair is not None
    s.receive(3.2, data)
    assert s.state.status == "ambiguous"
    assert s.state.post_check_pair is None
    assert not s.state.config_prerequisite_passed


@pytest.mark.parametrize("first,second,baud", [
    (response((4, 6, 2, 5)), SECOND, 9600),
    (response((0x027F, 6, 6, 5)), SECOND, 9600),
    (FIRST, response((2, 3, 0, 0)), 9600),
])
def test_required_mismatch_preserves_legacy_cache_and_pair(first, second, baud):
    s = Session(baud=baud)
    s.first(first)
    s.receive(2.1, second + ACCEL + GYRO + ANGLE)
    s.advance(3.0)
    assert s.state.status == "mismatch"
    assert s.state.check.failures
    assert s.state.post_check_pair is None
    assert s.parser.coherence_state().pair_count == 1
    assert s.parser.latest_imu_values()[1][0] != 0.0


def test_host_baud_is_effective_setting_not_fixed_default():
    s = Session(baud=115200)
    s.first(response((0x027F, 6, 6, 5)))
    s.receive(2.1, SECOND)
    s.advance(3.0)
    assert s.state.config_prerequisite_passed


@pytest.mark.parametrize("baud", [0, -1, True])
def test_invalid_host_baud_rejects_readback_without_harming_base(baud):
    s = Session(baud=baud)
    s.advance(1)
    s.receive(1.1, GYRO + ANGLE)
    assert s.state.status == "incomplete"
    assert s.writes == []
    assert s.parser.coherence_state().pair_count == 1


@pytest.mark.parametrize("split", range(1, 11))
def test_active_readback_response_split_across_reads_keeps_single_request(split):
    s = Session()
    s.advance(1)
    s.receive(1.1, FIRST[:split])
    s.advance(1.2)
    assert s.writes == [encode_readaddr(2)]
    assert not s.state.config_prerequisite_passed
    s.receive(1.3, FIRST[split:])
    s.advance(2)
    s.receive(2.1, SECOND[:split])
    s.advance(2.2)
    s.receive(2.3, SECOND[split:])
    s.advance(3)
    assert s.state.config_prerequisite_passed


@pytest.mark.parametrize("stage", ["quarantine", "first", "second", "checked"])
def test_reset_clears_validation_pending_pair_and_old_generation_bytes(stage):
    s = Session()
    if stage == "first":
        s.advance(1.0)
    elif stage == "second":
        s.first()
    elif stage == "checked":
        s.complete()
    s.receive(s.clock.now, GYRO + ANGLE + GYRO)
    old = s.state
    s.parser.reset()
    s.advance(10, generation=old.generation)
    s.receive(10, FIRST + SECOND + GYRO + ANGLE, generation=old.generation)
    assert s.state.status == "connection-invalidated"
    assert s.state.generation > old.generation
    assert not s.state.windows
    assert s.state.check is s.state.post_check_pair is None
    assert s.parser.coherence_state().latest_pair is None
    count = len(s.writes)
    s.advance(20)  # reset 自身绝不在同一 transport 自动重试。
    assert len(s.writes) == count
    s.parser.begin_configuration_readback()
    s.receive(20.1, FIRST)  # 新连接隔离期内物理迟到应答也拒绝。
    assert s.state.status == "ambiguous"


def test_no_success_or_send_until_input_is_drained_at_complete_frame_boundary():
    s = Session()
    s.advance(1, drained=False)
    assert s.writes == []
    s.advance(1)
    s.receive(1.1, FIRST)
    s.advance(2, drained=False)
    assert not s.state.windows
    assert s.writes == [encode_readaddr(2)]
    s.advance(2)
    s.receive(2.1, SECOND)
    s.advance(3, drained=False)
    assert not s.state.config_prerequisite_passed
    s.advance(4, drained=False)
    assert s.state.status == "incomplete"


def test_partial_regular_frame_cannot_hide_response_at_observation_boundary():
    s = Session()
    s.first()
    s.receive(2.1, SECOND + b"\x55")
    s.advance(3)
    assert s.state.status == "incomplete"


@pytest.mark.parametrize("outcome", [0, 4, OSError("fake write failure")])
def test_short_or_failed_write_latches_without_retry(outcome):
    s = Session()

    def send(_data):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    s.advance(1, send=send)
    assert s.state.status == "incomplete"
    s.advance(2)
    assert s.writes == []


def test_concurrent_pollers_only_issue_one_request_and_reset_waits_for_finite_write():
    s = Session()
    s.clock.now = 1
    entered, release = threading.Event(), threading.Event()
    threads = []

    def send(data):
        s.writes.append(data)
        entered.set()
        assert release.wait(timeout=2)
        return len(data)

    def poll():
        s.parser.advance_configuration_readback(send, generation=0, input_drained=True)

    try:
        for _ in range(2):
            t = threading.Thread(target=poll)
            threads.append(t)
            t.start()
        assert entered.wait(timeout=1)
        reset = threading.Thread(target=s.parser.reset)
        threads.append(reset)
        reset.start()
    finally:
        release.set()
        for t in threads:
            t.join(timeout=2)
            assert not t.is_alive()
    assert s.writes == [encode_readaddr(2)]
    assert s.state.status == "connection-invalidated"


def test_restarting_same_session_is_ambiguous_and_cannot_retry():
    s = Session()
    s.parser.begin_configuration_readback()
    s.advance(1)
    assert s.state.status == "ambiguous"
    assert s.writes == []


class TimedFakeSerial:
    """仅内存脚本；查询时间可控，write 只把软件应答排入本地列表。"""

    def __init__(self, clock, stop, *, end=4.0, mismatch=False, disconnect=False):
        self.clock, self.stop, self.end = clock, stop, end
        self.is_open = True
        self.closed = False
        self.writes = []
        self.script = [(0.2, ACCEL + GYRO + ANGLE), (2.9, GYRO),
                       (3.1, ANGLE), (3.3, GYRO + ANGLE + ANGLE)]
        if disconnect:
            self.script.append((3.5, OSError("fake disconnect")))
        self.mismatch = mismatch
        self.config_states = []

    @property
    def in_waiting(self):
        self.clock.now += 0.05
        if self.clock.now >= self.end:
            self.stop.set()
            return 0
        self.script.sort(key=lambda entry: entry[0])
        if not self.script or self.script[0][0] > self.clock.now:
            return 0
        data = self.script[0][1]
        if isinstance(data, Exception):
            self.script.pop(0)
            raise data
        return len(data)

    def read(self, _count):
        return self.script.pop(0)[1]

    def write(self, data):
        assert data in (encode_readaddr(2), encode_readaddr(0x20))
        self.writes.append((self.clock.now, data))
        reply = (response((4, 42, 2, 5)) if self.mismatch else FIRST) if data[3] == 2 else SECOND
        self.script.append((self.clock.now + 0.1, GYRO + reply + ANGLE))
        return len(data)

    def close(self):
        self.closed = True
        self.is_open = False


def enable_fake_readback(node, *, bound=1.0):
    # Serial 构造器在 configured_node 中已经替换；这里只替换 parser 的软件时钟。
    clock = Clock()
    node._readback_enabled = True
    node._parser = WitImuFrameParser(
        generation=node.coherence_state().generation, monotonic_clock=clock,
        readback_enabled=True, response_bound_sec=bound, host_baud=node._baud,
    )
    return clock


@pytest.mark.parametrize("mismatch", [False, True])
def test_existing_driver_fake_reader_keeps_publishing_and_only_gates_config(
        configured_node, monkeypatch, mismatch):
    node, capture, _ = configured_node
    clock = enable_fake_readback(node)
    node._stop_event = ImmediateStopEvent()
    connection = TimedFakeSerial(clock, node._stop_event, mismatch=mismatch)
    publish = capture.publish

    def observe(msg):
        connection.config_states.append(node.configuration_state())
        publish(msg)

    monkeypatch.setattr(capture, "publish", observe)
    run_reader(node, monkeypatch, [connection])
    assert [data for _, data in connection.writes] == [encode_readaddr(2), encode_readaddr(0x20)]
    assert len(capture.messages) == 6
    assert [state.pair_count for state in capture.states] == [1, 2, 3, 4, 5, 5]
    assert not connection.config_states[3].post_check_pair
    state = node.configuration_state()
    assert state.status == ("mismatch" if mismatch else "host-associated-checked")
    assert (state.post_check_pair is not None) == (not mismatch)
    assert all(msg.angular_velocity.x != 0 for msg in capture.messages)
    assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
    assert node.configuration_state().status == "connection-invalidated"
    assert node.configuration_state().post_check_pair is None
    assert connection.closed


def test_driver_reconnect_rechecks_both_windows_and_does_not_inherit_pair(
        configured_node, monkeypatch):
    node, capture, _ = configured_node
    clock = enable_fake_readback(node)
    node._stop_event = ImmediateStopEvent()
    first = TimedFakeSerial(clock, node._stop_event, disconnect=True)
    second = TimedFakeSerial(clock, node._stop_event, end=7.5)
    second.script = [(3.6, ANGLE), (6.8, GYRO + ANGLE)]
    seen = []
    publish = capture.publish

    def observe(msg):
        seen.append(node.configuration_state())
        publish(msg)

    monkeypatch.setattr(capture, "publish", observe)
    run_reader(node, monkeypatch, [first, second])
    assert first.closed
    assert any(state.config_prerequisite_passed for state in seen)
    new = [state for state in seen if state.generation > seen[0].generation]
    assert new[0].status == "pending"
    assert not new[0].windows and new[0].post_check_pair is None
    assert [data for _, data in second.writes] == [encode_readaddr(2), encode_readaddr(0x20)]
    assert node.configuration_state().config_prerequisite_passed
    assert node.configuration_state().post_check_pair.gyro.generation == new[0].generation


def test_ros_parameters_default_disabled_and_enabled_without_bound_fails_closed(
        configured_node):
    node, _, _ = configured_node
    assert node.get_parameter("config_readback_enabled").value is False
    assert node.get_parameter("config_readback_response_bound_sec").value == 0.0
    assert node.configuration_state().status == "disabled"
    from rclpy.parameter import Parameter
    node.on_deactivate(None)
    node.on_cleanup(None)
    node.set_parameters([Parameter("config_readback_enabled", value=True)])
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    node._parser.begin_configuration_readback()
    assert node.configuration_state().status == "incomplete"


def test_ros_opt_in_parameters_reactivation_cleanup_and_shutdown_invalidate(
        configured_node, monkeypatch):
    from rclpy.parameter import Parameter
    node, capture, status = configured_node
    node._imu_pub, node._status_pub = capture.original, status.original
    node.on_cleanup(None)
    assert node.configuration_state() is None
    node.set_parameters([
        Parameter("config_readback_enabled", value=True),
        Parameter("config_readback_response_bound_sec", value=1.0),
    ])
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    clock = Clock()
    node._parser._monotonic_clock = clock
    opened = []

    def factory(**kwargs):
        assert kwargs["write_timeout"] > 0
        connection = TimedFakeSerial(clock, node._stop_event, end=clock.now + 4)
        connection.script = [(clock.now + when, data) for when, data in connection.script]
        opened.append(connection)
        return connection

    monkeypatch.setattr(driver_module.serial, "Serial", factory)
    prior_generation = -1
    for _ in range(2):
        assert node.on_activate(None) == TransitionCallbackReturn.SUCCESS
        node._thread.join(timeout=2)
        assert not node._thread.is_alive()
        checked = node.configuration_state()
        assert checked.status == "host-associated-checked"
        assert checked.generation > prior_generation
        assert checked.post_check_pair is not None
        prior_generation = checked.generation
        assert node.on_deactivate(None) == TransitionCallbackReturn.SUCCESS
        assert node.configuration_state().status == "connection-invalidated"
        assert node.configuration_state().post_check_pair is None
        assert node.coherence_state().latest_pair is None
    assert all(len(connection.writes) == 2 and connection.closed for connection in opened)
    old_parser = node._parser
    assert node.on_cleanup(None) == TransitionCallbackReturn.SUCCESS
    assert node.configuration_state() is None
    assert node.on_configure(None) == TransitionCallbackReturn.SUCCESS
    assert node.configuration_state().generation > prior_generation
    assert old_parser.configuration_state().status == "connection-invalidated"
    assert node.on_shutdown(None) == TransitionCallbackReturn.SUCCESS
    assert node.configuration_state().status == "connection-invalidated"


def test_driver_reset_during_old_read_discards_response_and_never_retries_same_transport(
        configured_node, monkeypatch):
    node, capture, _ = configured_node
    clock = enable_fake_readback(node)
    node._stop_event = ImmediateStopEvent()

    class ResetDuringRead(TimedFakeSerial):
        def read(self, count):
            data = super().read(count)
            if FIRST in data:
                node._parser.reset()
            return data

    connection = ResetDuringRead(clock, node._stop_event)
    run_reader(node, monkeypatch, [connection])
    assert [data for _, data in connection.writes] == [encode_readaddr(2)]
    assert node.configuration_state().status == "connection-invalidated"
    assert node.configuration_state().windows == ()
    assert node._parser.register_response_state().response_count == 0
    assert capture.messages  # 之后本代次普通帧继续发布；配置失败不切断 base。
