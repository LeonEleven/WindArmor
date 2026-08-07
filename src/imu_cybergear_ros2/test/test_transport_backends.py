import struct
import threading
from types import SimpleNamespace

import pytest
import serial

import imu_cybergear_ros2.cybergear_driver as driver_module
from imu_cybergear_ros2.cybergear_driver import (
    AT_PREAMBLE,
    AT_TERMINATOR,
    COMM_GET_STATUS,
    SocketCanHatBackend,
    UsbCanSerialBackend,
)
from imu_cybergear_ros2.transport_recovery import (
    CyberGearDisconnectedError,
    CyberGearTransportError,
    TransportEventType,
)


class FakeSerial:
    def __init__(self, *, read_result=b"", read_error=None, write_error=None):
        self.is_open = True
        self.read_result = read_result
        self.read_error = read_error
        self.write_error = write_error
        self.closed = False
        self.backend = None

    @property
    def in_waiting(self):
        if self.read_error is not None:
            raise self.read_error
        return len(self.read_result)

    def read(self, _count):
        result = self.read_result
        self.read_result = b""
        if self.backend is not None:
            self.backend._stop_reader.set()
        return result

    def write(self, _data):
        if self.write_error is not None:
            raise self.write_error

    def flush(self):
        if self.write_error is not None:
            raise self.write_error

    def read_all(self):
        return b""

    def close(self):
        self.closed = True
        self.is_open = False


class FakeBus:
    def __init__(self, *, recv_result=None, recv_error=None, send_error=None):
        self.recv_result = recv_result
        self.recv_error = recv_error
        self.send_error = send_error
        self.backend = None
        self.shutdown_calls = 0

    def recv(self, timeout):
        assert timeout == 0.1
        if self.recv_error is not None:
            raise self.recv_error
        if self.backend is not None:
            self.backend._stop_reader.set()
        return self.recv_result

    def send(self, _message):
        if self.send_error is not None:
            raise self.send_error

    def shutdown(self):
        self.shutdown_calls += 1


def feedback_frame(motor_id=4):
    # Match the repository's existing USB adapter receive framing contract;
    # parser/protocol layout is deliberately outside this transport task.
    can_id = (COMM_GET_STATUS << 24) | (2 << 22) | (motor_id << 8) | 1
    raw_id = (can_id << 3) | 0x04
    id_bytes = bytearray(struct.pack(">I", raw_id))
    id_bytes[-1] = 8
    data = struct.pack(">HHHH", 32768, 32768, 32768, 250)
    return AT_PREAMBLE + bytes(id_bytes) + data + b"\x00" + AT_TERMINATOR


def test_usb_reader_parses_normal_frame_without_transport_event():
    backend = UsbCanSerialBackend("unused", 921600, 253)
    fake = FakeSerial(read_result=feedback_frame())
    fake.backend = backend
    backend._ser = fake
    statuses = []
    events = []
    backend.register_feedback_callback(statuses.append)
    backend.register_transport_event_callback(events.append)

    backend._reader_loop(generation=0)

    assert [status.motor_id for status in statuses] == [4]
    assert events == []


@pytest.mark.parametrize(
    "error",
    [serial.SerialException("serial read failed"), OSError("os read failed")],
)
def test_usb_reader_reports_once_and_exits_on_transport_error(error):
    backend = UsbCanSerialBackend("unused", 921600, 253)
    backend._ser = FakeSerial(read_error=error)
    events = []
    backend.register_transport_event_callback(events.append)

    backend._reader_loop(generation=0)

    assert len(events) == 1
    assert events[0].event_type is TransportEventType.READ_ERROR
    assert events[0].operation == "read"


def test_usb_reader_reports_closed_serial_as_disconnect():
    backend = UsbCanSerialBackend("unused", 921600, 253)
    fake = FakeSerial()
    fake.is_open = False
    backend._ser = fake
    events = []
    backend.register_transport_event_callback(events.append)

    backend._reader_loop(generation=0)

    assert [event.event_type for event in events] == [
        TransportEventType.DISCONNECTED
    ]


@pytest.mark.parametrize(
    "error",
    [serial.SerialException("serial write failed"), OSError("os write failed")],
)
def test_usb_write_raises_typed_error_and_reports_event(error):
    backend = UsbCanSerialBackend("unused", 921600, 253)
    backend._ser = FakeSerial(write_error=error)
    events = []
    backend.register_transport_event_callback(events.append)

    with pytest.raises(CyberGearTransportError):
        backend.send_motor_cmd(4, 0x04)

    assert len(events) == 1
    assert events[0].event_type is TransportEventType.WRITE_ERROR


def test_usb_write_closed_is_typed_disconnect():
    backend = UsbCanSerialBackend("unused", 921600, 253)
    events = []
    backend.register_transport_event_callback(events.append)
    with pytest.raises(CyberGearDisconnectedError):
        backend.send_motor_cmd(4, 0x04)
    assert events[0].event_type is TransportEventType.DISCONNECTED


def test_socketcan_reader_normal_message_and_none_are_not_disconnects():
    backend = SocketCanHatBackend("unused", "socketcan", 253)
    can_id = (COMM_GET_STATUS << 24) | (2 << 22) | (4 << 8) | 253
    message = SimpleNamespace(
        arbitration_id=can_id,
        data=struct.pack(">HHHH", 32768, 32768, 32768, 250),
    )
    bus = FakeBus(recv_result=message)
    bus.backend = backend
    backend._bus = bus
    statuses = []
    events = []
    backend.register_feedback_callback(statuses.append)
    backend.register_transport_event_callback(events.append)
    backend._reader_loop(generation=0)
    assert [status.motor_id for status in statuses] == [4]
    assert events == []

    backend._stop_reader.clear()
    none_bus = FakeBus(recv_result=None)
    none_bus.backend = backend
    backend._bus = none_bus
    backend._reader_loop(generation=0)
    assert events == []


def test_socketcan_recv_exception_reports_read_error_and_exits():
    backend = SocketCanHatBackend("unused", "socketcan", 253)
    backend._bus = FakeBus(recv_error=OSError("recv failed"))
    events = []
    backend.register_transport_event_callback(events.append)
    backend._reader_loop(generation=0)
    assert len(events) == 1
    assert events[0].event_type is TransportEventType.READ_ERROR


def test_socketcan_missing_bus_reports_disconnect():
    backend = SocketCanHatBackend("unused", "socketcan", 253)
    events = []
    backend.register_transport_event_callback(events.append)
    backend._reader_loop(generation=0)
    assert events[0].event_type is TransportEventType.DISCONNECTED


def test_socketcan_send_exception_and_missing_bus_are_typed(monkeypatch):
    fake_can = SimpleNamespace(
        Message=lambda **kwargs: SimpleNamespace(**kwargs),
        interface=SimpleNamespace(),
    )
    monkeypatch.setattr(driver_module, "can", fake_can)
    backend = SocketCanHatBackend("unused", "socketcan", 253)
    events = []
    backend.register_transport_event_callback(events.append)
    backend._bus = FakeBus(send_error=OSError("send failed"))
    with pytest.raises(CyberGearTransportError):
        backend.send_motor_cmd(4, 0x04)
    assert events[-1].event_type is TransportEventType.WRITE_ERROR

    second = SocketCanHatBackend("unused", "socketcan", 253)
    second_events = []
    second.register_transport_event_callback(second_events.append)
    with pytest.raises(CyberGearDisconnectedError):
        second.send_motor_cmd(4, 0x04)
    assert second_events[-1].event_type is TransportEventType.DISCONNECTED


def test_usb_reconnect_replaces_reader_and_increments_generation(monkeypatch):
    created = []

    def serial_factory(*_args, **_kwargs):
        item = FakeSerial()
        created.append(item)
        return item

    monkeypatch.setattr(driver_module.serial, "Serial", serial_factory)
    monkeypatch.setattr(driver_module.time, "sleep", lambda _delay: None)
    backend = UsbCanSerialBackend("unused", 921600, 253)
    backend.connect()
    first_reader = backend._reader_thread
    assert backend.connection_generation == 1
    backend.connect()
    assert backend.connection_generation == 2
    assert not first_reader.is_alive()
    assert created[0].closed
    backend.close()
    backend.close()
    assert not backend.is_connected


def test_socketcan_reconnect_replaces_reader_and_close_is_idempotent(monkeypatch):
    buses = []

    def bus_factory(**_kwargs):
        bus = FakeBus()
        buses.append(bus)
        return bus

    fake_can = SimpleNamespace(
        interface=SimpleNamespace(Bus=bus_factory),
        Message=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(driver_module, "can", fake_can)
    backend = SocketCanHatBackend("unused", "socketcan", 253)
    backend.connect()
    first_reader = backend._reader_thread
    assert backend.connection_generation == 1
    backend.connect()
    assert backend.connection_generation == 2
    assert not first_reader.is_alive()
    assert buses[0].shutdown_calls == 1
    backend.close()
    backend.close()
    assert not backend.is_connected
