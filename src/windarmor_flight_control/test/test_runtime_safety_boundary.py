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


def test_runtime_adds_only_structured_flight_transport_and_owner_clients() -> None:
    tree = ast.parse(NODE_PATH.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    def method_name(call):
        return call.func.attr if isinstance(call.func, ast.Attribute) else None

    publisher_calls = [call for call in calls if method_name(call) == "create_publisher"]
    assert len(publisher_calls) == 4
    assert {
        call.args[0].id
        for call in publisher_calls
        if call.args and isinstance(call.args[0], ast.Name)
    } == {
        "FlightRuntimeStatus",
        "FlightCommandPreview",
        "FlightAuthorityStatus",
        "FlightCommandEnvelopeMessage",
    }
    assert len([call for call in calls if method_name(call) == "create_client"]) == 6
    assert len([call for call in calls if method_name(call) == "create_service"]) == 3


def test_runtime_uses_owner_protocol_and_never_imports_hardware_backends() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(RUNTIME_ROOT.glob("*.py"))
    )
    assert "MotionSource.FLIGHT" not in text
    assert "CyberGearDriver" not in text
    assert "GPIO" not in text
    assert "pigpio" not in text
    assert "serial.Serial" not in text
    assert "acknowledge_owner(" in text
    assert "commit_active(" in text
