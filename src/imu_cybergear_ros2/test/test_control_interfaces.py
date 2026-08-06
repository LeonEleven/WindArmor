from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1] / "imu_cybergear_ros2"
CONFIG_FILE = Path(__file__).parents[1] / "config" / "imu_cybergear_params.yaml"


def read_source(name: str) -> str:
    return (PACKAGE_ROOT / name).read_text(encoding="utf-8")


def test_relative_attitude_precedes_motor_specific_processing() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    validated = callback.index("corrected_relative_roll_pitch(")
    timestamp_update = callback.index("self._last_imu_time = now")
    publish = callback.index("self._relative_attitude_pub.publish(relative_msg)")
    auto_gate = callback.index("if not self._state_mgr.is_auto_running()")
    gain_application = callback.index("auto_attitude_commands(")
    assert validated < timestamp_update < publish < auto_gate < gain_application
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


def test_auto_callback_only_sets_desired_targets() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    assert "self._motor_mgr.set_auto_targets(targets)" in callback
    assert "apply_targets" not in callback
    assert "write_sdo_float" not in callback


def test_manual_absolute_target_rejects_non_finite_values_atomically() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[
        source.index("    def _on_manual_targets") :
        source.index("    def publish_system_emergency_stop")
    ]
    finite_check = callback.index("all(math.isfinite(value) for value in values)")
    update = callback.index("self._motor_mgr.set_manual_targets(targets)")
    assert finite_check < update
    assert "apply_targets" not in callback


def test_motion_timer_follows_lifecycle() -> None:
    source = read_source("imu_motor_controller_node.py")
    activate = source[source.index("    def on_activate") : source.index("    def on_deactivate")]
    deactivate = source[source.index("    def on_deactivate") : source.index("    def on_cleanup")]
    cleanup = source[source.index("    def on_cleanup") : source.index("    def _on_imu_zero_service")]
    shutdown = source[source.index("    def on_shutdown") : source.index("    # ==================================================================\n    # IMU 数据回调")]
    assert "self._motor_mgr.start_motion_timer()" in activate
    assert "self._motor_mgr.stop_motion_timer()" in deactivate
    assert 'self._release_resources(reason="cleanup"' in cleanup
    assert 'self._release_resources(reason="shutdown"' in shutdown
    assert 'attempt("stop_motion_timer", motor_mgr.stop_motion_timer)' in cleanup


def test_unified_motion_defaults_and_protected_motor_mapping() -> None:
    config = CONFIG_FILE.read_text(encoding="utf-8")
    for line in (
        "manual_motion_speed_rad_s: 4.0",
        "auto_motion_speed_rad_s: 4.0",
        "home_motion_speed_rad_s: 4.0",
        "motion_dt_max_sec: 0.05",
        "target_reached_tolerance_rad: 0.001",
        "manual_repeat_gap_sec: 0.8",
        "manual_repeat_dt_max_sec: 0.08",
        "auto_roll_gain: 1.0",
        "auto_pitch_gain: 1.0",
        "motor_ids: [4, 3, 2, 1]",
        "motor_signs: [-1.0, 1.0, -1.0, 1.0]",
        "motor_limits_min: [-1.57, -1.57, -1.57, 0.0]",
        "motor_limits_max: [0.0, 1.57, 1.57, 1.57]",
    ):
        assert line in config


def test_auto_gain_is_confined_to_auto_target_branch() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    publish = callback.index("self._relative_attitude_pub.publish(relative_msg)")
    gain = callback.index("auto_attitude_commands(")
    targets = callback.index("self._motor_mgr.set_auto_targets(targets)")
    assert publish < gain < targets
    assert "relative_msg.vector.x = roll_rel" in callback[:gain]
    assert "relative_msg.vector.y = pitch_rel" in callback[:gain]

    manager = read_source("motor_manager.py")
    manual = manager[
        manager.index("    def manual_step") :
        manager.index("    def clear_manual_repeat_state")
    ]
    home = manager[
        manager.index("    def go_all_to_zero") :
        manager.index("    def stop_auto_zero")
    ]
    assert "auto_roll_gain" not in manual + home
    assert "auto_pitch_gain" not in manual + home


def test_verified_auto_direction_mapping_remains_unchanged() -> None:
    source = read_source("imu_motor_controller_node.py")
    callback = source[source.index("    def _imu_callback") :]
    assert 'cfg.control_axis == "roll_left"' in callback
    assert "max(0.0, -alpha_deg)" in callback
    assert 'cfg.control_axis == "roll_right"' in callback
    assert "max(0.0, alpha_deg)" in callback
    assert 'cfg.control_axis == "pitch"' in callback
    assert "targets[cfg.motor_id] = cfg.sign * deg_to_rad(deg)" in callback


def test_state_manager_private_lock_and_callback_are_not_accessed_by_other_modules() -> None:
    controller = read_source("imu_motor_controller_node.py")
    safety = read_source("safety_monitor.py")
    assert "._stop_auto_zero_callback" not in controller
    assert "register_stop_auto_zero_callback(" in controller
    assert "._state_lock" not in safety
    assert "self._state.is_in(" in safety
