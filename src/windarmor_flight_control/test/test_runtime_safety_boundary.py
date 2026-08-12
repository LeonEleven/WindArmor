import ast
from pathlib import Path


RUNTIME_ROOT = (
    Path(__file__).resolve().parents[1]
    / "windarmor_flight_control"
    / "runtime"
)
NODE_PATH = RUNTIME_ROOT / "node.py"
ACTUATOR_NAMES = {
    "/fans/command_pwm",
    "/fans/pwm",
    "/fans/left/pwm",
    "/fans/right/pwm",
    "/motors/manual_targets",
    "/enable_motor",
    "/motors/set_zero",
    "/imu/set_zero",
    "/fans/enable",
    "/fans/stop",
    "/fans/reset_e_stop",
}


def test_runtime_source_contains_no_actuator_topic_or_service_name() -> None:
    tree = ast.parse(NODE_PATH.read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not literals & ACTUATOR_NAMES


def test_runtime_has_only_three_observation_publishers_no_clients_and_local_services() -> None:
    tree = ast.parse(NODE_PATH.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    def method_name(call):
        return call.func.attr if isinstance(call.func, ast.Attribute) else None

    publisher_calls = [call for call in calls if method_name(call) == "create_publisher"]
    assert len(publisher_calls) == 3
    assert {
        call.args[0].id
        for call in publisher_calls
        if call.args and isinstance(call.args[0], ast.Name)
    } == {"FlightRuntimeStatus", "FlightCommandPreview", "FlightAuthorityStatus"}
    assert not any(method_name(call) == "create_client" for call in calls)
    assert len([call for call in calls if method_name(call) == "create_service"]) == 3


def test_runtime_does_not_define_task3_authority_or_actuator_sources() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(RUNTIME_ROOT.glob("*.py"))
    )
    assert "MotionSource.FLIGHT" not in text
    assert "CommandAuthority.FLIGHT_CONTROL" not in text
    assert "takeover_supported=True" not in text
    assert "acknowledge_owner(" not in text
    assert "commit_active(" not in text
