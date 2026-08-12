import ast
from pathlib import Path


def test_windarmor_launch_is_valid_python() -> None:
    launch_file = (
        Path(__file__).parents[1] / "launch" / "windarmor.launch.py"
    )
    ast.parse(launch_file.read_text(encoding="utf-8"))


def test_windarmor_reuses_fans_launch_in_unified_mode() -> None:
    launch_file = Path(__file__).parents[1] / "launch" / "windarmor.launch.py"
    source = launch_file.read_text(encoding="utf-8")
    assert '"fans.launch.py"' in source
    assert '"require_motor_mode_for_manual": "true"' in source
    assert 'executable="fan_controller"' not in source


def test_observation_only_launch_is_valid_and_excludes_actuator_nodes() -> None:
    launch_file = (
        Path(__file__).parents[1]
        / "launch"
        / "windarmor_observation_only.launch.py"
    )
    source = launch_file.read_text(encoding="utf-8")
    ast.parse(source)
    assert 'executable="imu_driver_node"' in source
    assert 'executable="imu_relative_observer_node"' in source
    assert 'executable="motor_feedback_observer_node"' in source
    assert 'executable="flight_control_runtime_node"' in source
    assert 'executable="imu_motor_controller_node"' not in source
    assert 'executable="fan_controller"' not in source
    assert 'executable="fan_keyboard"' not in source
    assert '"flight_takeover_enabled": False' in source
    assert 'DeclareLaunchArgument("flight_takeover_enabled"' not in source
    assert "GPIO12" not in source and "GPIO13" not in source
