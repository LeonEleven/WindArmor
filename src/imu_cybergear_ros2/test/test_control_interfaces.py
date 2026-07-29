from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1] / "imu_cybergear_ros2"


def read_source(name: str) -> str:
    return (PACKAGE_ROOT / name).read_text(encoding="utf-8")


def test_relative_attitude_precedes_motor_specific_processing() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    validated = callback.index("corrected_relative_roll_pitch(")
    timestamp_update = callback.index("self._last_imu_time = now")
    publish = callback.index("self._relative_attitude_pub.publish(relative_msg)")
    auto_gate = callback.index("if not self._state_mgr.is_auto_running()")
    deadband = callback.index("if abs(roll_rel) < self._deadband")
    assert validated < timestamp_update < publish < auto_gate < deadband
    assert "relative_msg.header = msg.header" in callback
    assert "relative_msg.vector.z = 0.0" in callback


def test_invalid_imu_path_returns_before_valid_timestamp_update() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    validation = callback.index("corrected_relative_roll_pitch(")
    exception_handler = callback.index("except ValueError")
    timestamp_update = callback.index("self._last_imu_time = now")
    assert validation < timestamp_update < exception_handler
    exception_block = callback[
        exception_handler : callback.index("relative_msg = Vector3Stamped()")
    ]
    assert "return" in exception_block


def test_keyboard_and_service_share_zero_method() -> None:
    keyboard = read_source("keyboard_handler.py")
    controller = read_source("imu_motor_controller_node.py")
    assert "self._node.set_imu_zero()" in keyboard
    service = controller[
        controller.index("    def _on_imu_zero_service") :
        controller.index("    def _on_motor_zero_service")
    ]
    assert "self.set_imu_zero()" in service
    assert "self._last_imu_time <= 0.0" in service
    assert "self._imu_zero_generation += 1" in service


def test_control_mode_has_transient_state_qos_and_heartbeat() -> None:
    source = read_source("imu_motor_controller_node.py")
    assert 'self.declare_parameter("motor_mode_publish_rate_hz", 5.0)' in source
    assert "ReliabilityPolicy.RELIABLE" in source
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in source
    assert "self._motor_mode_timer = self.create_timer(" in source
