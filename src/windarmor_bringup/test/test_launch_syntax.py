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
