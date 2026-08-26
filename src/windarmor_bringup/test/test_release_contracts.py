import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from imu_cybergear_ros2.controller_state import ControllerState, public_control_mode
from imu_cybergear_ros2.motor_config import default_motor_config_values
from windarmor_fan_controller.fan_control import FanControlConfig, FanControlState


REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_VERSION = "0.4.0"
PACKAGES = (
    "imu_cybergear_ros2",
    "windarmor_fan_controller",
    "windarmor_bringup",
    "windarmor_interfaces",
    "windarmor_flight_control",
)


def _setup_metadata(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    constants: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        ):
            constants[node.targets[0].id] = node.value.value

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else getattr(node.func, "attr", None)
        )
        if function_name != "setup":
            continue
        metadata: dict[str, object] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if isinstance(keyword.value, ast.Constant):
                metadata[keyword.arg] = keyword.value.value
            elif isinstance(keyword.value, ast.Name):
                metadata[keyword.arg] = constants[keyword.value.id]
        return metadata
    raise AssertionError(f"setup() call not found in {path}")


def _package_xml_metadata(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    maintainer = root.find("maintainer")
    assert maintainer is not None
    return {
        "name": root.findtext("name", default="").strip(),
        "version": root.findtext("version", default="").strip(),
        "description": root.findtext("description", default="").strip(),
        "maintainer": (maintainer.text or "").strip(),
        "maintainer_email": maintainer.attrib.get("email", "").strip(),
        "license": root.findtext("license", default="").strip(),
    }


def _call_contracts(path: Path) -> set[tuple[str, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    contracts: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method not in {"create_publisher", "create_subscription", "create_service"}:
            continue
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
            continue
        if not isinstance(node.args[1].value, str):
            continue
        message_type = (
            node.args[0].id
            if isinstance(node.args[0], ast.Name)
            else getattr(node.args[0], "attr", "")
        )
        contracts.add((method, message_type, node.args[1].value))
    return contracts


def _yaml_value(path: Path, key: str):
    match = re.search(
        rf"^\s*{re.escape(key)}:\s*([^#\n]+?)\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, f"missing YAML key {key} in {path}"
    raw = match.group(1).strip()
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return raw


def test_workspace_release_metadata_is_consistent_and_frozen() -> None:
    for package in PACKAGES:
        package_root = REPO_ROOT / "src" / package
        package_xml = _package_xml_metadata(package_root / "package.xml")
        assert package_xml["name"] == package
        assert package_xml["version"] == RELEASE_VERSION
        assert package_xml["license"] == "Apache-2.0"

        setup_path = package_root / "setup.py"
        if not setup_path.exists():
            continue
        setup_py = _setup_metadata(setup_path)
        for key in (
            "name",
            "version",
            "description",
            "maintainer",
            "maintainer_email",
            "license",
        ):
            assert setup_py[key] == package_xml[key], f"{package}: {key} mismatch"


def test_critical_public_ros_interface_names_and_types_are_frozen() -> None:
    motor_source = (
        REPO_ROOT
        / "src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py"
    )
    imu_source = (
        REPO_ROOT / "src/imu_cybergear_ros2/imu_cybergear_ros2/imu_driver_node.py"
    )
    fan_manager = (
        REPO_ROOT
        / "src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py"
    )
    fan_node = (
        REPO_ROOT
        / "src/windarmor_fan_controller/windarmor_fan_controller/fan_node.py"
    )
    contracts = (
        _call_contracts(motor_source)
        | _call_contracts(imu_source)
        | _call_contracts(fan_manager)
        | _call_contracts(fan_node)
    )
    expected = {
        ("create_publisher", "Bool", "/e_stop"),
        ("create_subscription", "Bool", "/e_stop"),
        ("create_subscription", "Float64MultiArray", "/motors/manual_targets"),
        ("create_service", "Trigger", "/e_stop"),
        ("create_service", "SetBool", "/enable_motor"),
        ("create_service", "Trigger", "/imu/set_zero"),
        ("create_service", "Trigger", "/motors/set_zero"),
        ("create_subscription", "Int32MultiArray", "/fans/pwm"),
        ("create_subscription", "Int32", "/fans/left/pwm"),
        ("create_subscription", "Int32", "/fans/right/pwm"),
        ("create_subscription", "Vector3Stamped", "/imu/relative_roll_pitch"),
        ("create_subscription", "UInt64", "/imu/zero_generation"),
        ("create_subscription", "String", "/motors/control_mode"),
        ("create_publisher", "Int32MultiArray", "/fans/command_pwm"),
        ("create_subscription", "Int32MultiArray", "/fans/command_pwm"),
        ("create_publisher", "Bool", "/fans/auto_enabled"),
        ("create_publisher", "Bool", "/fans/auto_active"),
        ("create_publisher", "Int32MultiArray", "/fans/auto_target_pwm"),
        ("create_publisher", "String", "/fans/control_state"),
        ("create_publisher", "Int32MultiArray", "/fans/status_pwm"),
        ("create_publisher", "Bool", "/fans/enabled"),
        ("create_service", "SetBool", "/fans/enable"),
        ("create_service", "Trigger", "/fans/stop"),
        ("create_service", "SetBool", "/fans/auto_enable"),
        ("create_service", "SetBool", "/fans/manual_enable"),
        ("create_service", "Trigger", "/fans/reset_e_stop"),
    }
    assert expected <= contracts

    imu_text = imu_source.read_text(encoding="utf-8")
    motor_text = motor_source.read_text(encoding="utf-8")
    assert "self.create_publisher(Imu, self._topic_name, 20)" in imu_text
    assert "String, ros_config.motor_status_topic, 10" in motor_text
    assert "Vector3Stamped, ros_config.relative_attitude_topic, 20" in motor_text
    assert "UInt64, ros_config.imu_zero_generation_topic, state_qos" in motor_text
    assert "String, ros_config.motor_mode_topic, state_qos" in motor_text
    assert "Imu, ros_config.imu_topic, self._imu_callback, 20" in motor_text

    motor_defaults = default_motor_config_values()
    assert motor_defaults["imu_topic"] == "/imu/data_raw"
    assert motor_defaults["relative_attitude_topic"] == "/imu/relative_roll_pitch"
    assert motor_defaults["imu_zero_generation_topic"] == "/imu/zero_generation"
    assert motor_defaults["motor_mode_topic"] == "/motors/control_mode"
    assert motor_defaults["motor_status_topic"] == "/motor/status"


def test_public_modes_and_state_qos_are_frozen() -> None:
    assert {
        public_control_mode(state, active=True) for state in ControllerState
    } == {"MANUAL", "AUTO", "EMERGENCY_STOP", "DISABLED", "ERROR"}
    assert {state.value for state in FanControlState} == {
        "SAFE_STOP",
        "MANUAL_DISARMED",
        "MANUAL_WAITING_FOR_NEUTRAL",
        "MANUAL_WAITING",
        "MANUAL_ACTIVE",
        "AUTO_WAITING",
        "AUTO_ACTIVE",
        "FLIGHT_WAITING",
        "FLIGHT_ACTIVE",
        "DISABLED",
        "EMERGENCY_STOP",
    }
    for relative_path in (
        "src/imu_cybergear_ros2/imu_cybergear_ros2/imu_motor_controller_node.py",
        "src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py",
        "src/windarmor_fan_controller/windarmor_fan_controller/fan_node.py",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "ReliabilityPolicy.RELIABLE" in source
        assert "DurabilityPolicy.TRANSIENT_LOCAL" in source


def test_motor_release_defaults_match_code_and_yaml() -> None:
    defaults = default_motor_config_values()
    expected = {
        "motor_ids": [4, 3, 2, 1],
        "motor_signs": [-1.0, 1.0, -1.0, 1.0],
        "motor_limits_min": [-1.57, -1.57, -1.57, 0.0],
        "motor_limits_max": [0.0, 1.57, 1.57, 1.57],
        "command_interval_sec": 0.02,
        "max_position_step": 0.4,
        "manual_motion_speed_rad_s": 4.0,
        "auto_motion_speed_rad_s": 4.0,
        "home_motion_speed_rad_s": 4.0,
        "motion_dt_max_sec": 0.05,
        "target_reached_tolerance_rad": 0.001,
        "manual_step_deg": 3.0,
        "manual_repeat_gap_sec": 0.8,
        "manual_repeat_dt_max_sec": 0.08,
        "default_speed": 10.0,
        "auto_roll_gain": 1.0,
        "auto_pitch_gain": 1.0,
        "motor_temp_limit_degC": 80.0,
        "motor_temp_critical_degC": 90.0,
        "motor_current_limit_a": 5.0,
        "motor_feedback_timeout_sec": 0.0,
        "motor_flight_handoff_timeout_sec": 1.5,
        "motor_flight_command_timeout_sec": 0.25,
        "reconnect_on_disconnect": True,
        "reconnect_max_attempts": 30,
        "reconnect_initial_delay_sec": 0.5,
        "reconnect_max_delay_sec": 10.0,
        "reconnect_backoff_multiplier": 1.5,
    }
    motor_yaml = (
        REPO_ROOT / "src/imu_cybergear_ros2/config/imu_cybergear_params.yaml"
    )
    for key, value in expected.items():
        assert defaults[key] == value
        if isinstance(value, bool):
            assert _yaml_value(motor_yaml, key) == str(value).lower()
        else:
            assert _yaml_value(motor_yaml, key) == value


def test_fan_release_defaults_match_code_and_yaml() -> None:
    defaults = FanControlConfig()
    expected = {
        "fan_deadband_on_deg": 5.0,
        "fan_deadband_off_deg": 3.0,
        "fan_full_scale_deg": 45.0,
        "fan_stop_pwm_us": 800,
        "fan_start_pwm_us": 1200,
        "fan_auto_max_pwm_us": 1400,
        "rise_step_pwm_us": 10,
        "fall_step_pwm_us": 20,
        "fan_response_curve": "smoothstep",
        "fan_flight_handoff_timeout_sec": 1.5,
        "fan_flight_command_timeout_sec": 0.25,
    }
    fan_yaml = (
        REPO_ROOT / "src/windarmor_fan_controller/config/fan_params.yaml"
    )
    for key, value in expected.items():
        assert getattr(defaults, key) == value
        assert _yaml_value(fan_yaml, key) == value
    assert _yaml_value(fan_yaml, "control_rate_hz") == 20.0

    manager_source = (
        REPO_ROOT
        / "src/windarmor_fan_controller/windarmor_fan_controller/fan_command_manager.py"
    ).read_text(encoding="utf-8")
    assert 'self.declare_parameter("control_rate_hz", 20.0)' in manager_source


def test_owner_handoff_leases_outlast_runtime_transaction_default() -> None:
    runtime_yaml = REPO_ROOT / "src/windarmor_flight_control/config/flight_control.yaml"
    motor_yaml = REPO_ROOT / "src/imu_cybergear_ros2/config/imu_cybergear_params.yaml"
    fan_yaml = REPO_ROOT / "src/windarmor_fan_controller/config/fan_params.yaml"
    runtime_timeout = _yaml_value(runtime_yaml, "flight_handoff_timeout_sec")
    motor_handoff = _yaml_value(motor_yaml, "motor_flight_handoff_timeout_sec")
    fan_handoff = _yaml_value(fan_yaml, "fan_flight_handoff_timeout_sec")

    assert runtime_timeout == 1.0
    assert motor_handoff == 1.5 and motor_handoff >= runtime_timeout
    assert fan_handoff == 1.5 and fan_handoff >= runtime_timeout
    assert _yaml_value(motor_yaml, "motor_flight_command_timeout_sec") == 0.25
    assert _yaml_value(fan_yaml, "fan_flight_command_timeout_sec") == 0.25
