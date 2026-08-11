from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def message_fields(name: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for raw_line in (PACKAGE_ROOT / "msg" / name).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            field_type, field_name = line.split()
            fields.append((field_type, field_name))
    return fields


def test_motor_feedback_uses_explicit_presence_without_invented_current() -> None:
    fields = message_fields("MotorFeedback.msg")
    names = {name for _, name in fields}

    assert {
        "logical_name",
        "can_id",
        "has_feedback",
        "position_valid",
        "position_rad",
        "velocity_valid",
        "velocity_rad_s",
        "torque_valid",
        "torque_nm",
        "temperature_valid",
        "temperature_c",
        "device_mode_valid",
        "device_mode",
        "fault_flags_valid",
        "fault_flags",
        "feedback_age_sec",
        "valid",
        "fresh",
        "healthy",
    } == names
    assert "current_a" not in names
    assert "rpm" not in names
    assert "thrust" not in names


def test_feedback_array_is_a_timestamped_complete_snapshot() -> None:
    assert message_fields("MotorFeedbackArray.msg") == [
        ("builtin_interfaces/Time", "stamp"),
        ("uint64", "sequence"),
        ("MotorFeedback[]", "motors"),
    ]
