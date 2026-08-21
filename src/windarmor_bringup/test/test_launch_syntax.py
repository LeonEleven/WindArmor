import ast
import importlib.util
from pathlib import Path

from launch import LaunchContext, LaunchDescription
from launch.actions import RegisterEventHandler
from lifecycle_msgs.msg import TransitionEvent
from launch_ros.actions import LifecycleNode, Node
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import StateTransition


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


def test_low_level_imu_auto_activate_contract() -> None:
    launch_file = (
        Path(__file__).parents[2]
        / "imu_cybergear_ros2"
        / "launch"
        / "imu_cybergear_system.launch.py"
    )
    source = launch_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    declarations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DeclareLaunchArgument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "imu_auto_activate"
    ]
    assert len(declarations) == 1
    defaults = {
        keyword.arg: keyword.value
        for keyword in declarations[0].keywords
        if keyword.arg is not None
    }
    assert isinstance(defaults["default_value"], ast.Constant)
    assert defaults["default_value"].value == "true"

    assignments = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_launch_description"
        for node in node.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    configure_source = ast.unparse(assignments["imu_configure_handler"])
    activate_source = ast.unparse(assignments["imu_activate_handler"])
    controller_activate_source = ast.unparse(
        assignments["controller_activate_handler"]
    )
    assert "TRANSITION_CONFIGURE" in configure_source
    assert "imu_auto_activate" not in configure_source
    assert "TRANSITION_ACTIVATE" in activate_source
    assert "start_state='configuring'" in activate_source
    assert "goal_state='inactive'" in activate_source
    assert "condition=IfCondition(imu_auto_activate)" in activate_source
    assert "TRANSITION_ACTIVATE" in controller_activate_source
    assert "start_state='configuring'" in controller_activate_source
    assert "goal_state='inactive'" in controller_activate_source


def test_low_level_startup_activate_handlers_only_match_configure_completion(
    monkeypatch, tmp_path
) -> None:
    launch_file = (
        Path(__file__).parents[2]
        / "imu_cybergear_ros2"
        / "launch"
        / "imu_cybergear_system.launch.py"
    )
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    module = _load_launch_module(launch_file)
    description = module.generate_launch_description()

    lifecycle_nodes = {
        entity.node_executable: entity
        for entity in description.entities
        if isinstance(entity, LifecycleNode)
    }
    handlers = [
        entity
        for entity in description.entities
        if isinstance(entity, RegisterEventHandler)
        and isinstance(entity.event_handler, OnStateTransition)
    ]

    def transition(node, start_state: str, goal_state: str) -> StateTransition:
        message = TransitionEvent()
        message.start_state.label = start_state
        message.goal_state.label = goal_state
        return StateTransition(action=node, msg=message)

    matched_handlers = {}
    for executable in ("imu_driver_node", "imu_motor_controller_node"):
        node = lifecycle_nodes[executable]
        configuring = transition(node, "configuring", "inactive")
        deactivating = transition(node, "deactivating", "inactive")
        matches = [
            handler
            for handler in handlers
            if handler.event_handler.matches(configuring)
        ]
        assert len(matches) == 1
        assert not matches[0].event_handler.matches(deactivating)
        matched_handlers[executable] = matches[0]

    context = LaunchContext()
    context.launch_configurations["imu_auto_activate"] = "true"
    assert matched_handlers["imu_driver_node"].condition.evaluate(context)
    context.launch_configurations["imu_auto_activate"] = "false"
    assert not matched_handlers["imu_driver_node"].condition.evaluate(context)
    context.launch_configurations["start_controller"] = "true"
    assert matched_handlers["imu_motor_controller_node"].condition.evaluate(context)


def test_unified_launch_declares_and_forwards_imu_auto_activate() -> None:
    launch_file = Path(__file__).parents[1] / "launch" / "windarmor.launch.py"
    source = launch_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    declarations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DeclareLaunchArgument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "imu_auto_activate"
    ]
    assert len(declarations) == 1
    defaults = {
        keyword.arg: keyword.value
        for keyword in declarations[0].keywords
        if keyword.arg is not None
    }
    assert isinstance(defaults["default_value"], ast.Constant)
    assert defaults["default_value"].value == "true"
    assert 'imu_auto_activate = LaunchConfiguration("imu_auto_activate")' in source
    assert '"imu_auto_activate": imu_auto_activate' in source


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
    assert all(gpio not in source for gpio in ("GPIO12", "GPIO13", "GPIO26"))


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
