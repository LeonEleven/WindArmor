import ast
import importlib.util
from pathlib import Path

from launch import LaunchDescription
from launch_ros.actions import LifecycleNode, Node


def _load_launch_module(path: Path):
    spec = importlib.util.spec_from_file_location(
        "windarmor_observation_only_launch_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_observation_only_launch_constructs_real_jazzy_lifecycle_nodes(
    monkeypatch, tmp_path
) -> None:
    launch_file = (
        Path(__file__).parents[1]
        / "launch"
        / "windarmor_observation_only.launch.py"
    )
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    module = _load_launch_module(launch_file)

    description = module.generate_launch_description()

    assert isinstance(description, LaunchDescription)
    nodes = [entity for entity in description.entities if isinstance(entity, Node)]
    lifecycle_nodes = [node for node in nodes if isinstance(node, LifecycleNode)]
    executables = {node.node_executable for node in nodes}

    assert len(lifecycle_nodes) == 3
    assert {node.node_executable for node in lifecycle_nodes} == {
        "imu_driver_node",
        "imu_relative_observer_node",
        "motor_feedback_observer_node",
    }
    assert all(node._Node__node_namespace == "" for node in lifecycle_nodes)
    assert executables == {
        "imu_driver_node",
        "imu_relative_observer_node",
        "motor_feedback_observer_node",
        "flight_control_runtime_node",
    }
    assert "imu_motor_controller_node" not in executables
    assert "fan_controller" not in executables
