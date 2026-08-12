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


def test_runtime_status_is_structured_and_explicitly_reports_dry_run_state() -> None:
    assert message_fields("FlightRuntimeStatus.msg") == [
        ("builtin_interfaces/Time", "stamp"),
        ("uint64", "state_sequence"),
        ("string", "mode"),
        ("bool", "state_valid"),
        ("bool", "controller_inhibited"),
        ("bool", "command_available"),
        ("bool", "command_valid"),
        ("bool", "latest_command_safe_stop"),
        ("string", "last_error"),
    ]


def test_command_preview_has_presence_for_payload_free_safe_stop() -> None:
    assert message_fields("FlightCommandPreview.msg") == [
        ("builtin_interfaces/Time", "stamp"),
        ("uint64", "state_sequence"),
        ("bool", "request_safe_stop"),
        ("string[]", "motor_names"),
        ("float64[]", "motor_positions_rad"),
        ("bool", "fan_commands_present"),
        ("float64", "fan_left"),
        ("float64", "fan_right"),
    ]


def test_motor_and_fan_safety_readbacks_are_structured():
    motor_fields = message_fields("MotorSafetyState.msg")
    fan_fields = message_fields("FanSafetyState.msg")
    assert {name: field_type for field_type, name in motor_fields}[
        "source_epoch"
    ] == "uint64"
    assert {name: field_type for field_type, name in fan_fields}[
        "source_epoch"
    ] == "uint64"
    assert {name for _, name in motor_fields} == {
        "stamp", "source_epoch", "observation_sequence", "node_active", "controller_state",
        "public_control_mode", "e_stop_latched", "error_latched",
        "feedback_safety_fault_latched", "transition_present",
        "transition_sequence", "transition_reason", "transition_source",
    }
    assert {name for _, name in fan_fields} == {
        "stamp", "source_epoch", "observation_sequence", "e_stop_latched", "control_state",
        "enabled_observed", "enabled", "manual_armed",
        "legacy_auto_requested", "legacy_auto_active", "safety_reason",
        "passive_for_takeover",
    }


def test_authority_status_exposes_preparation_without_claiming_takeover():
    names = {name for _, name in message_fields("FlightAuthorityStatus.msg")}
    assert {
        "authority_epoch", "authority_state", "command_authority", "authority_generation",
        "attempt_present", "attempt_generation", "preparing",
        "preflight_ready", "controller_inhibited", "global_e_stop_observed",
        "global_e_stop_active", "motor_safety_state_fresh",
        "fan_safety_state_fresh", "last_preflight_failure_reason",
        "last_inhibit_reason", "takeover_supported", "takeover_enabled",
        "motor_reserved", "motor_committed", "fan_reserved", "fan_committed",
        "owner_tokens_match", "atomic_cutoff_present",
        "atomic_cutoff_state_sequence", "last_command_present",
        "last_command_sequence", "last_valid_command_age_sec",
        "actuation_allowed",
    } <= names


def test_flight_command_and_ownership_readback_are_presence_aware():
    assert message_fields("FlightCommandEnvelope.msg") == [
        ("builtin_interfaces/Time", "stamp"),
        ("uint64", "authority_epoch"),
        ("uint64", "generation"),
        ("uint64", "command_sequence"),
        ("uint64", "state_sequence"),
        ("bool", "request_safe_stop"),
        ("string[]", "motor_names"),
        ("float64[]", "motor_positions_rad"),
        ("bool", "fan_commands_present"),
        ("float64", "fan_left"),
        ("float64", "fan_right"),
    ]
    names = {name for _, name in message_fields("OwnershipState.msg")}
    assert {
        "source_epoch", "observation_sequence", "owner_domain",
        "ownership_phase", "authority_present", "authority_epoch",
        "generation", "last_accepted_flight_command_present",
        "last_accepted_flight_command_sequence",
        "last_valid_flight_command_age_sec",
    } <= names


def service_fields(name: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    request: list[tuple[str, str]] = []
    response: list[tuple[str, str]] = []
    target = request
    for raw_line in (PACKAGE_ROOT / "srv" / name).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line == "---":
            target = response
        elif line:
            field_type, field_name = line.split()
            target.append((field_type, field_name))
    return request, response


def test_ownership_services_return_structured_reason_and_token():
    for name in (
        "PrepareFlightOwnership.srv",
        "CommitFlightOwnership.srv",
        "RevokeFlightOwnership.srv",
    ):
        request, response = service_fields(name)
        assert request == [
            ("uint64", "authority_epoch"),
            ("uint64", "generation"),
            ("uint64", "runtime_state_sequence"),
        ]
        assert response == [
            ("bool", "success"),
            ("string", "reason_code"),
            ("uint64", "authority_epoch"),
            ("uint64", "generation"),
            ("uint64", "owner_observation_sequence"),
        ]
