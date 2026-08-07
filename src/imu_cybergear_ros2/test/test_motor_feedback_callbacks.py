import pytest

from imu_cybergear_ros2.cybergear_driver import (
    MotorStatus,
    SocketCanHatBackend,
    UsbCanSerialBackend,
)


@pytest.mark.parametrize(
    "backend",
    [
        UsbCanSerialBackend(port="fake-never-opened", baud=921600, master_id=253),
        SocketCanHatBackend(channel="fake-never-opened", bustype="socketcan", master_id=253),
    ],
)
def test_callback_exception_is_diagnosed_and_later_callback_still_runs(backend):
    events = []

    def fail(_status):
        raise RuntimeError("injected callback failure")

    backend.register_feedback_callback(fail)
    backend.register_feedback_callback(lambda status: events.append(status.motor_id))
    backend.register_feedback_error_callback(lambda exc: events.append(str(exc)))
    backend._dispatch_feedback(MotorStatus(motor_id=4))
    assert events == ["injected callback failure", 4]


@pytest.mark.parametrize(
    "backend",
    [
        UsbCanSerialBackend(port="fake-never-opened", baud=921600, master_id=253),
        SocketCanHatBackend(channel="fake-never-opened", bustype="socketcan", master_id=253),
    ],
)
def test_clear_callbacks_releases_all_node_references(backend):
    called = []
    backend.register_feedback_callback(lambda _status: called.append("feedback"))
    backend.register_feedback_error_callback(lambda _exc: called.append("error"))
    backend.clear_feedback_callbacks()
    backend._dispatch_feedback(MotorStatus(motor_id=4))
    assert called == []
