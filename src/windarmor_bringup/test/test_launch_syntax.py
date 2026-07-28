import ast
from pathlib import Path


def test_windarmor_launch_is_valid_python() -> None:
    launch_file = (
        Path(__file__).parents[1] / "launch" / "windarmor.launch.py"
    )
    ast.parse(launch_file.read_text(encoding="utf-8"))
