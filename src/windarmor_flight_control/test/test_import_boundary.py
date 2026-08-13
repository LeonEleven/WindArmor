import ast
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "windarmor_flight_control"
PURE_ROOTS = (PACKAGE_ROOT / "core", PACKAGE_ROOT / "algorithms")
FORBIDDEN_ROOTS = {
    "can",
    "geometry_msgs",
    "gpiozero",
    "imu_cybergear_ros2",
    "lgpio",
    "rclpy",
    "sensor_msgs",
    "serial",
    "socket",
    "std_msgs",
    "windarmor_fan_controller",
    "windarmor_interfaces",
}


def test_pure_package_sources_do_not_import_ros_or_hardware_libraries() -> None:
    violations: list[str] = []
    for pure_root in PURE_ROOTS:
        paths = sorted(pure_root.rglob("*.py"))
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots = {node.module.split(".", 1)[0]}
                else:
                    continue
                blocked = sorted(roots & FORBIDDEN_ROOTS)
                if blocked:
                    violations.append(f"{path}: {', '.join(blocked)}")
    assert not violations


def test_importing_public_api_does_not_load_ros_or_hardware_libraries() -> None:
    before = set(sys.modules)
    import windarmor_flight_control  # noqa: F401
    from windarmor_flight_control.algorithms import (  # noqa: F401
        NeutralExampleController,
    )

    newly_loaded_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before}
    assert not newly_loaded_roots & FORBIDDEN_ROOTS


def test_verification_controller_has_no_actuator_implementation_dependencies() -> None:
    source = (
        PACKAGE_ROOT / "algorithms" / "bounded_verification_controller.py"
    ).read_text(encoding="utf-8")
    forbidden = {
        "CyberGearDriver",
        "MotorManager",
        "FanControlCore",
        "rclpy",
        "sensor_msgs",
        "std_msgs",
        "windarmor_interfaces",
        "gpiozero",
        "lgpio",
    }
    assert not {token for token in forbidden if token in source}
