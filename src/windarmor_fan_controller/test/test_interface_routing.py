import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1]


def source(name: str) -> str:
    return (PACKAGE_ROOT / "windarmor_fan_controller" / name).read_text(
        encoding="utf-8"
    )


def test_bottom_controller_only_accepts_internal_command_topic() -> None:
    fan_node = source("fan_node.py")
    assert '"/fans/command_pwm"' in fan_node
    assert '"/fans/pwm"' not in fan_node
    assert '"/fans/left/pwm"' not in fan_node
    assert '"/fans/right/pwm"' not in fan_node


def test_manager_owns_public_topics_and_does_not_import_gpio() -> None:
    manager = source("fan_command_manager.py")
    for topic in (
        '"/fans/pwm"',
        '"/fans/left/pwm"',
        '"/fans/right/pwm"',
        '"/fans/command_pwm"',
    ):
        assert topic in manager
    assert "gpiozero" not in manager
    assert "lgpio" not in manager
    assert 'self.create_publisher(\n            Int32MultiArray, "/fans/command_pwm"' in manager
    assert '"/fans/reset_e_stop"' in manager
    assert '"/fans/manual_enable"' in manager


def test_normal_command_progression_is_owned_by_control_timer() -> None:
    manager = source("fan_command_manager.py")
    assert "self._core.control_tick" in manager
    assert "self._core.step" not in manager


def test_manager_is_only_normal_internal_command_publisher() -> None:
    package_sources = list(
        (PACKAGE_ROOT / "windarmor_fan_controller").glob("*.py")
    )
    publishers = [
        path.name
        for path in package_sources
        if 'create_publisher(\n            Int32MultiArray, "/fans/command_pwm"'
        in path.read_text(encoding="utf-8")
    ]
    assert publishers == ["fan_command_manager.py"]


def test_bottom_controller_retains_final_clamp_and_cleanup() -> None:
    fan_node = source("fan_node.py")
    assert "safe_pwm = self._range.clamp(pwm_us)" in fan_node
    assert "def close(self)" in fan_node
    assert "def destroy_node(self)" in fan_node
    assert "self._command_gate.disable()" in fan_node


def test_watchdog_is_validated_before_gpio_initialization() -> None:
    fan_node = source("fan_node.py")
    assert "initialize_after_timeout_validation(" in fan_node
    assert "command_timeout_value,\n            self._initialize_gpio" in fan_node


def test_fan_launch_is_valid_and_has_one_bottom_controller() -> None:
    launch_source = (PACKAGE_ROOT / "launch" / "fans.launch.py").read_text(
        encoding="utf-8"
    )
    ast.parse(launch_source)
    assert launch_source.count('executable="fan_controller"') == 1
    assert launch_source.count('executable="fan_command_manager"') == 1
