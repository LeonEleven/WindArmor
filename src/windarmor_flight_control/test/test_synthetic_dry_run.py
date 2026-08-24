import ast
from io import StringIO
from pathlib import Path

from windarmor_flight_control.synthetic_dry_run import main, run_demo


def test_synthetic_dry_run_is_human_readable_and_non_actuating() -> None:
    stream = StringIO()

    assert main(["--pitches", "-0.1", "0.0", "0.1"], stream=stream) == 0

    output = stream.getvalue()
    assert "software-only synthetic DRY_RUN" in output
    assert "hardware access: NO" in output
    assert "pitch = -0.100 rad" in output
    assert "pitch = +0.100 rad" in output
    assert "left_pitch target" in output
    assert "fan_left" in output and "fan_right" in output
    assert "safe_stop = true" in output
    assert "authority=NONE; actuation_allowed=false" in output


def test_synthetic_dry_run_source_has_no_ros_or_hardware_imports() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "windarmor_flight_control"
        / "synthetic_dry_run.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {
        "rclpy",
        "windarmor_interfaces",
        "gpiozero",
        "lgpio",
        "serial",
    }
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert not imported_roots & forbidden


def test_run_demo_accepts_a_deterministic_pitch_sequence() -> None:
    stream = StringIO()

    run_demo((0.2,), stream=stream)

    output = stream.getvalue()
    assert "left_pitch target = +0.0500 rad" in output
    assert "fan_left = 0.100" in output
    assert "fan_right = 0.000" in output
