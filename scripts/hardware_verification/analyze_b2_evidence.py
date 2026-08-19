#!/usr/bin/env python3
"""Analyze required B2 software evidence without deciding the hardware gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Optional, Sequence

import yaml


REQUIRED_MOTORS = {
    "left_lift",
    "left_pitch",
    "right_pitch",
    "right_lift",
}
DEFAULT_FILES = {
    "authority_status": "authority_status.log",
    "flight_command": "flight_command.log",
    "motor_feedback": "motor_feedback.log",
    "motor_safety": "motor_safety.log",
    "motor_ownership": "motor_ownership.log",
    "fan_pwm": "fan_pwm.log",
    "fan_safety": "fan_safety.log",
    "fan_ownership": "fan_ownership.log",
}


@dataclass(frozen=True)
class ParsedLog:
    path: Path
    documents: tuple[dict[str, Any], ...]
    malformed_documents: int
    state: str


@dataclass(frozen=True)
class PwmResult:
    passed: bool
    samples: tuple[tuple[int, int], ...]

    @property
    def first(self) -> Optional[tuple[int, int]]:
        return self.samples[0] if self.samples else None

    @property
    def last(self) -> Optional[tuple[int, int]]:
        return self.samples[-1] if self.samples else None

    @property
    def left_max(self) -> Optional[int]:
        return max((left for left, _ in self.samples), default=None)

    @property
    def right_unique(self) -> list[int]:
        return sorted({right for _, right in self.samples})


@dataclass(frozen=True)
class B2Result:
    active: bool
    flight_command: bool
    full_motor_command: bool
    healthy_motor_frame: bool
    fan_pwm: PwmResult
    post_authority: bool
    post_motor_owner: bool
    post_fan_owner: bool
    post_motor_latch: bool
    post_fan_latch: bool
    supplemental_state: str
    supplemental_conflict: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.active,
                self.flight_command,
                self.full_motor_command,
                self.healthy_motor_frame,
                self.fan_pwm.passed,
                self.post_authority,
                self.post_motor_owner,
                self.post_fan_owner,
                self.post_motor_latch,
                self.post_fan_latch,
                not self.supplemental_conflict,
            )
        )


def _split_yaml_documents(text: str) -> Iterable[str]:
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            if current:
                yield "\n".join(current)
                current = []
        else:
            current.append(line)
    if current:
        yield "\n".join(current)


def parse_log(path: Path) -> ParsedLog:
    if not path.is_file():
        return ParsedLog(path, (), 0, "MISSING")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return ParsedLog(path, (), 0, "EMPTY")
    documents: list[dict[str, Any]] = []
    malformed = 0
    for chunk in _split_yaml_documents(text):
        if not chunk.strip():
            continue
        try:
            document = yaml.safe_load(chunk)
        except yaml.YAMLError:
            malformed += 1
            continue
        if isinstance(document, dict):
            documents.append(document)
        elif document is not None:
            malformed += 1
    state = "PARSED" if documents else "NO PARSEABLE SAMPLE"
    return ParsedLog(path, tuple(documents), malformed, state)


def _is_true(document: dict[str, Any], key: str) -> bool:
    return document.get(key) is True


def _numeric(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _close(value: object, target: float) -> bool:
    number = _numeric(value)
    return number is not None and math.isclose(
        number,
        target,
        rel_tol=1e-6,
        abs_tol=1e-9,
    )


def is_complete_active(document: dict[str, Any]) -> bool:
    return (
        document.get("authority_state") == "ACTIVE"
        and document.get("command_authority") == "FLIGHT_CONTROL"
        and all(
            _is_true(document, key)
            for key in (
                "motor_committed",
                "fan_committed",
                "owner_tokens_match",
                "atomic_cutoff_present",
                "last_command_present",
                "actuation_allowed",
            )
        )
    )


def _command_checks(document: dict[str, Any]) -> tuple[bool, bool]:
    names = document.get("motor_names")
    positions = document.get("motor_positions_rad")
    full_motor_frame = (
        isinstance(names, list)
        and len(names) == 4
        and all(isinstance(name, str) for name in names)
        and set(names) == REQUIRED_MOTORS
        and isinstance(positions, list)
        and len(positions) == 4
        and all(_numeric(position) is not None for position in positions)
    )
    fan_command = (
        document.get("request_safe_stop") is False
        and document.get("fan_commands_present") is True
        and _close(document.get("fan_left"), 0.05)
        and _close(document.get("fan_right"), 0.0)
    )
    return fan_command, full_motor_frame


def has_complete_b2_command(
    documents: Sequence[dict[str, Any]],
) -> tuple[bool, bool]:
    for document in documents:
        fan_command, full_motor_frame = _command_checks(document)
        if fan_command and full_motor_frame:
            return True, True
    return False, False


def _pwm_pair(document: dict[str, Any]) -> Optional[tuple[int, int]]:
    values = document.get("data")
    if not isinstance(values, list) or len(values) != 2:
        return None
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    return values[0], values[1]


def analyze_pwm(
    documents: Sequence[dict[str, Any]],
    expected_left_target: int = 1210,
) -> PwmResult:
    samples = tuple(
        pair for document in documents if (pair := _pwm_pair(document)) is not None
    )
    if not samples:
        return PwmResult(False, samples)
    first = samples[0]
    last = samples[-1]
    left_values = [left for left, _ in samples]
    right_values = [right for _, right in samples]
    passed = (
        first == (800, 800)
        and last == (800, 800)
        and any(left > 800 for left in left_values)
        and all(800 <= left <= expected_left_target for left in left_values)
        and all(right == 800 for right in right_values)
    )
    return PwmResult(passed, samples)


def is_healthy_motor_frame(document: dict[str, Any]) -> bool:
    motors = document.get("motors")
    if not isinstance(motors, list) or len(motors) != 4:
        return False
    by_name: dict[str, dict[str, Any]] = {}
    for motor in motors:
        if not isinstance(motor, dict) or not isinstance(motor.get("logical_name"), str):
            return False
        by_name[motor["logical_name"]] = motor
    if set(by_name) != REQUIRED_MOTORS:
        return False
    for motor in by_name.values():
        if not all(
            motor.get(key) is True
            for key in (
                "has_feedback",
                "position_valid",
                "fault_flags_valid",
                "valid",
                "fresh",
                "healthy",
            )
        ):
            return False
        if motor.get("fault_flags") != 0:
            return False
    return True


def _post_authority(documents: Sequence[dict[str, Any]]) -> bool:
    active_index = next(
        (index for index, document in enumerate(documents) if is_complete_active(document)),
        None,
    )
    if active_index is None:
        return False
    return any(
        document.get("global_e_stop_active") is True
        and document.get("authority_state") == "INHIBITED"
        and document.get("command_authority") == "NONE"
        and document.get("actuation_allowed") is False
        for document in documents[active_index + 1 :]
    )


def _post_owner_none(documents: Sequence[dict[str, Any]]) -> bool:
    flight_index = next(
        (
            index
            for index, document in enumerate(documents)
            if document.get("ownership_phase") == "FLIGHT_CONTROL"
            and document.get("authority_present") is True
        ),
        None,
    )
    if flight_index is None:
        return False
    return any(
        document.get("ownership_phase") == "NONE"
        and document.get("authority_present") is False
        for document in documents[flight_index + 1 :]
    )


def _post_latch(documents: Sequence[dict[str, Any]]) -> bool:
    return any(document.get("e_stop_latched") is True for document in documents)


def _supplemental(path: Path) -> tuple[str, bool]:
    parsed = parse_log(path)
    if parsed.state in {"MISSING", "EMPTY"}:
        return parsed.state, False
    samples = [
        pair
        for document in parsed.documents
        if (pair := _pwm_pair(document)) is not None
    ]
    if not samples:
        return "NO PARSEABLE SAMPLE", False
    if samples[-1] == (800, 800):
        return "PASS", False
    return f"CONFLICT: final={samples[-1]}", True


def analyze_b2(logs: dict[str, ParsedLog], supplemental_path: Path) -> B2Result:
    authority = logs["authority_status"].documents
    command_pass, full_motor_command = has_complete_b2_command(
        logs["flight_command"].documents
    )
    supplemental_state, supplemental_conflict = _supplemental(supplemental_path)
    return B2Result(
        active=any(is_complete_active(document) for document in authority),
        flight_command=command_pass,
        full_motor_command=full_motor_command,
        healthy_motor_frame=any(
            is_healthy_motor_frame(document)
            for document in logs["motor_feedback"].documents
        ),
        fan_pwm=analyze_pwm(logs["fan_pwm"].documents),
        post_authority=_post_authority(authority),
        post_motor_owner=_post_owner_none(logs["motor_ownership"].documents),
        post_fan_owner=_post_owner_none(logs["fan_ownership"].documents),
        post_motor_latch=_post_latch(logs["motor_safety"].documents),
        post_fan_latch=_post_latch(logs["fan_safety"].documents),
        supplemental_state=supplemental_state,
        supplemental_conflict=supplemental_conflict,
    )


def _status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _pair(value: Optional[tuple[int, int]]) -> str:
    return "NONE" if value is None else f"({value[0]},{value[1]})"


def format_report(result: B2Result) -> str:
    pwm = result.fan_pwm
    lines = [
        "========== B2 SOFTWARE EVIDENCE ==========",
        "",
        f"ACTIVE complete evidence: {_status(result.active)}",
        f"Flight command 0.05 / 0.0: {_status(result.flight_command)}",
        f"Full 4-motor frame: {_status(result.full_motor_command)}",
        f"4-motor healthy/fault-free snapshot: {_status(result.healthy_motor_frame)}",
        "",
        "Fan PWM:",
        f"  first: {_pair(pwm.first)}",
        f"  left_max: {pwm.left_max if pwm.left_max is not None else 'NONE'}",
        f"  right_unique: {pwm.right_unique}",
        f"  last: {_pair(pwm.last)}",
        f"  result: {_status(pwm.passed)}",
        "",
        f"Post E-STOP authority: {_status(result.post_authority)}",
        f"Post E-STOP motor owner NONE: {_status(result.post_motor_owner)}",
        f"Post E-STOP fan owner NONE: {_status(result.post_fan_owner)}",
        f"Post E-STOP motor latch: {_status(result.post_motor_latch)}",
        f"Post E-STOP fan latch: {_status(result.post_fan_latch)}",
        "",
        "Supplemental post_fan_pwm snapshot:",
        result.supplemental_state,
    ]
    if result.supplemental_state in {"MISSING", "EMPTY", "NO PARSEABLE SAMPLE"}:
        lines.append(
            "non-blocking because continuous final PWM is valid"
            if pwm.passed
            else "supplemental unavailable; required continuous PWM result governs"
        )
    elif result.supplemental_conflict:
        lines.append("blocking contradiction with the continuous final PWM evidence")
    else:
        lines.append("corroborates continuous final PWM")
    lines.extend(
        (
            "",
            f"SOFTWARE EVIDENCE: {_status(result.passed)}",
            "",
            "OPERATOR PHYSICAL EVIDENCE: NOT EVALUATED BY THIS TOOL",
            "FINAL HARDWARE GATE: NOT DETERMINED BY THIS TOOL",
            "",
            "==========================================",
        )
    )
    return "\n".join(lines)


def _manifest_files(session_dir: Path) -> dict[str, str]:
    manifest_path = session_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}
    files: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str) and isinstance(
            row.get("file"), str
        ):
            relative = Path(row["file"])
            if not relative.is_absolute() and len(relative.parts) == 1:
                files[row["name"]] = row["file"]
    return files


def resolve_log_paths(session_dir: Path) -> dict[str, Path]:
    files = {**DEFAULT_FILES, **_manifest_files(session_dir)}
    return {name: session_dir / files[name] for name in DEFAULT_FILES}


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument(
        "--post-fan-pwm",
        type=Path,
        help="optional supplemental --once snapshot (defaults inside session dir)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    options = parse_arguments(argv)
    try:
        paths = resolve_log_paths(options.session_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Unable to read session manifest: {exc}", file=sys.stderr)
        return 2
    logs = {name: parse_log(path) for name, path in paths.items()}
    supplemental_path = options.post_fan_pwm or options.session_dir / "post_fan_pwm.txt"
    result = analyze_b2(logs, supplemental_path)
    print(format_report(result))
    missing = [name for name, log in logs.items() if log.state != "PARSED"]
    malformed = {
        name: log.malformed_documents
        for name, log in logs.items()
        if log.malformed_documents
    }
    if missing:
        print(f"Required logs without parseable samples: {', '.join(missing)}", file=sys.stderr)
    if malformed:
        print(f"Ignored malformed YAML documents: {malformed}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
