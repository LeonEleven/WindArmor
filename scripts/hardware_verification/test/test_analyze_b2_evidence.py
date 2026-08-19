from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
import yaml


TOOL_DIR = Path(__file__).resolve().parents[1]
ANALYZER_PATH = TOOL_DIR / "analyze_b2_evidence.py"
SPEC = importlib.util.spec_from_file_location("windarmor_b2_analyzer", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
analyzer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")


def active_message(**updates):
    message = {
        "authority_state": "ACTIVE",
        "command_authority": "FLIGHT_CONTROL",
        "motor_committed": True,
        "fan_committed": True,
        "owner_tokens_match": True,
        "atomic_cutoff_present": True,
        "last_command_present": True,
        "actuation_allowed": True,
        "global_e_stop_active": False,
    }
    message.update(updates)
    return message


def post_authority_message():
    return {
        "authority_state": "INHIBITED",
        "command_authority": "NONE",
        "global_e_stop_active": True,
        "actuation_allowed": False,
    }


def command_message(fan_left=0.05):
    return {
        "request_safe_stop": False,
        "fan_commands_present": True,
        "fan_left": fan_left,
        "fan_right": 0.0,
        "motor_names": list(MOTOR_NAMES),
        "motor_positions_rad": [0.0, 0.0, 0.0, 0.0],
    }


def healthy_motor(name: str):
    return {
        "logical_name": name,
        "has_feedback": True,
        "position_valid": True,
        "fault_flags_valid": True,
        "fault_flags": 0,
        "valid": True,
        "fresh": True,
        "healthy": True,
    }


def healthy_frame():
    return {"motors": [healthy_motor(name) for name in MOTOR_NAMES]}


def owner_messages():
    return [
        {"ownership_phase": "FLIGHT_CONTROL", "authority_present": True},
        {"ownership_phase": "NONE", "authority_present": False},
    ]


def write_log(path: Path, documents) -> None:
    path.write_text(
        yaml.safe_dump_all(documents, explicit_start=True, sort_keys=False),
        encoding="utf-8",
    )


def valid_session(tmp_path: Path) -> Path:
    logs = {
        "authority_status.log": [active_message(), post_authority_message()],
        "flight_command.log": [command_message()],
        "motor_feedback.log": [healthy_frame()],
        "motor_safety.log": [{"e_stop_latched": False}, {"e_stop_latched": True}],
        "motor_ownership.log": owner_messages(),
        "fan_pwm.log": [
            {"data": [800, 800]},
            {"data": [900, 800]},
            {"data": [1210, 800]},
            {"data": [800, 800]},
        ],
        "fan_safety.log": [{"e_stop_latched": False}, {"e_stop_latched": True}],
        "fan_ownership.log": owner_messages(),
    }
    for filename, documents in logs.items():
        write_log(tmp_path / filename, documents)
    return tmp_path


def analyze_session(session: Path):
    logs = {
        name: analyzer.parse_log(path)
        for name, path in analyzer.resolve_log_paths(session).items()
    }
    return analyzer.analyze_b2(logs, session / "post_fan_pwm.txt")


def test_valid_active_message_passes() -> None:
    assert analyzer.is_complete_active(active_message())


def test_active_missing_required_field_fails() -> None:
    message = active_message()
    del message["atomic_cutoff_present"]
    assert not analyzer.is_complete_active(message)


@pytest.mark.parametrize("fan_left", [0.05, "5e-2"])
def test_equivalent_fan_left_float_formats_parse(fan_left) -> None:
    command, full_frame = analyzer.has_complete_b2_command([command_message(fan_left)])
    assert command
    assert full_frame


def test_valid_continuous_pwm_passes() -> None:
    result = analyzer.analyze_pwm(
        [
            {"data": [800, 800]},
            {"data": [900, 800]},
            {"data": [1210, 800]},
            {"data": [800, 800]},
        ]
    )
    assert result.passed
    assert result.left_max == 1210
    assert result.right_unique == [800]


def test_any_non_stop_right_pwm_fails() -> None:
    result = analyzer.analyze_pwm(
        [
            {"data": [800, 800]},
            {"data": [1210, 801]},
            {"data": [800, 800]},
        ]
    )
    assert not result.passed


def test_non_stop_final_continuous_pwm_fails() -> None:
    result = analyzer.analyze_pwm(
        [{"data": [800, 800]}, {"data": [1210, 800]}]
    )
    assert not result.passed


def test_empty_supplemental_snapshot_is_non_blocking(tmp_path: Path) -> None:
    session = valid_session(tmp_path)
    (session / "post_fan_pwm.txt").write_text("", encoding="utf-8")
    result = analyze_session(session)
    assert result.passed
    assert result.supplemental_state == "EMPTY"
    assert "non-blocking" in analyzer.format_report(result)


def test_absent_supplemental_snapshot_is_non_blocking(tmp_path: Path) -> None:
    result = analyze_session(valid_session(tmp_path))
    assert result.passed
    assert result.supplemental_state == "MISSING"


def test_four_healthy_motors_pass() -> None:
    assert analyzer.is_healthy_motor_frame(healthy_frame())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fault_flags", 1),
        ("fresh", False),
        ("healthy", False),
    ],
)
def test_one_fault_stale_or_unhealthy_motor_fails(field: str, value) -> None:
    frame = healthy_frame()
    frame["motors"][2][field] = value
    assert not analyzer.is_healthy_motor_frame(frame)


def test_valid_supplemental_snapshot_corroborates(tmp_path: Path) -> None:
    session = valid_session(tmp_path)
    write_log(session / "post_fan_pwm.txt", [{"data": [800, 800]}])
    result = analyze_session(session)
    assert result.passed
    assert result.supplemental_state == "PASS"


def test_contradictory_supplemental_snapshot_blocks_pass(tmp_path: Path) -> None:
    session = valid_session(tmp_path)
    write_log(session / "post_fan_pwm.txt", [{"data": [900, 800]}])
    result = analyze_session(session)
    assert not result.passed
    assert result.supplemental_conflict


def test_owner_none_must_follow_flight_control() -> None:
    assert analyzer._post_owner_none(owner_messages())
    assert not analyzer._post_owner_none(
        [{"ownership_phase": "NONE", "authority_present": False}]
    )


def test_malformed_trailing_yaml_does_not_hide_valid_samples(tmp_path: Path) -> None:
    path = tmp_path / "fan_pwm.log"
    path.write_text("---\ndata: [800, 800]\n---\ndata: [", encoding="utf-8")
    parsed = analyzer.parse_log(path)
    assert parsed.documents == ({"data": [800, 800]},)
    assert parsed.malformed_documents == 1


def test_cli_exit_code_tracks_required_software_result(tmp_path: Path, capsys) -> None:
    session = valid_session(tmp_path)
    assert analyzer.main([str(session)]) == 0
    output = capsys.readouterr().out
    assert "SOFTWARE EVIDENCE: PASS" in output
    assert "OPERATOR PHYSICAL EVIDENCE: NOT EVALUATED BY THIS TOOL" in output
    assert "FINAL HARDWARE GATE: NOT DETERMINED BY THIS TOOL" in output

    write_log(session / "fan_pwm.log", [{"data": [800, 800]}])
    assert analyzer.main([str(session)]) == 1
