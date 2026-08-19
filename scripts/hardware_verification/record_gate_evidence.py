#!/usr/bin/env python3
"""Continuously record read-only ROS topic evidence into one session directory."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Callable, Optional, Sequence


@dataclass(frozen=True)
class TopicSpec:
    """One read-only ``ros2 topic echo`` recorder."""

    name: str
    topic: str
    message_type: str
    file: str


DEFAULT_TOPICS = (
    TopicSpec(
        "authority_status",
        "/flight_control/authority/status",
        "windarmor_interfaces/msg/FlightAuthorityStatus",
        "authority_status.log",
    ),
    TopicSpec(
        "flight_command",
        "/flight_control/command",
        "windarmor_interfaces/msg/FlightCommandEnvelope",
        "flight_command.log",
    ),
    TopicSpec(
        "motor_feedback",
        "/motors/feedback",
        "windarmor_interfaces/msg/MotorFeedbackArray",
        "motor_feedback.log",
    ),
    TopicSpec(
        "motor_safety",
        "/motors/safety_state",
        "windarmor_interfaces/msg/MotorSafetyState",
        "motor_safety.log",
    ),
    TopicSpec(
        "motor_ownership",
        "/motors/ownership_state",
        "windarmor_interfaces/msg/OwnershipState",
        "motor_ownership.log",
    ),
    TopicSpec(
        "fan_pwm",
        "/fans/status_pwm",
        "std_msgs/msg/Int32MultiArray",
        "fan_pwm.log",
    ),
    TopicSpec(
        "fan_safety",
        "/fans/safety_state",
        "windarmor_interfaces/msg/FanSafetyState",
        "fan_safety.log",
    ),
    TopicSpec(
        "fan_ownership",
        "/fans/ownership_state",
        "windarmor_interfaces/msg/OwnershipState",
        "fan_ownership.log",
    ),
)


@dataclass
class ChildState:
    spec: TopicSpec
    process: object
    output_handle: object
    error_handle: object
    exit_code: Optional[int] = None
    exit_classification: str = "RUNNING"
    cleanup_action: str = "NONE"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if not name:
        raise ValueError("topic name must contain at least one safe filename character")
    return name


def _validate_spec(spec: TopicSpec) -> TopicSpec:
    if not spec.name or not spec.topic.startswith("/") or "/msg/" not in spec.message_type:
        raise ValueError(f"invalid topic specification: {spec}")
    path = Path(spec.file)
    if path.is_absolute() or len(path.parts) != 1 or path.name in {"", ".", ".."}:
        raise ValueError(f"topic output must be a plain filename: {spec.file!r}")
    return spec


def parse_topic_spec(value: str) -> TopicSpec:
    """Parse ``NAME=/topic:package/msg/Type`` without invoking a shell."""

    try:
        name, target = value.split("=", 1)
        topic, message_type = target.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "topic must use NAME=/topic:package/msg/Type"
        ) from exc
    safe_name = _safe_name(name)
    try:
        return _validate_spec(
            TopicSpec(safe_name, topic, message_type, f"{safe_name}.log")
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def load_topic_config(path: Path) -> list[TopicSpec]:
    """Load generic topic mappings from a small JSON configuration file."""

    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("config must contain a non-empty 'topics' list")
    specs: list[TopicSpec] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each configured topic must be an object")
        try:
            name = _safe_name(str(row["name"]))
            spec = TopicSpec(
                name=name,
                topic=str(row["topic"]),
                message_type=str(row["type"]),
                file=str(row.get("file", f"{name}.log")),
            )
        except KeyError as exc:
            raise ValueError(f"configured topic is missing {exc.args[0]!r}") from exc
        specs.append(_validate_spec(spec))
    return specs


def resolve_topics(config: Optional[Path], cli_topics: Sequence[TopicSpec]) -> list[TopicSpec]:
    """Use defaults unless a config or explicit CLI mapping replaces them."""

    topics = load_topic_config(config) if config is not None else []
    topics.extend(cli_topics)
    if not topics:
        topics = list(DEFAULT_TOPICS)
    names = [topic.name for topic in topics]
    files = [topic.file for topic in topics]
    if len(names) != len(set(names)):
        raise ValueError("topic names must be unique")
    if len(files) != len(set(files)):
        raise ValueError("topic output filenames must be unique")
    return topics


def create_session_directory(output_root: Path, now: datetime, process_id: int) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session = output_root / f"gate-evidence-{timestamp}-{process_id}"
    session.mkdir()
    return session


class EvidenceRecorder:
    """Manage read-only topic-echo children and a durable session manifest."""

    def __init__(
        self,
        *,
        session_dir: Path,
        topics: Sequence[TopicSpec],
        command_line: Sequence[str],
        shutdown_timeout_sec: float = 5.0,
        terminate_timeout_sec: float = 2.0,
        process_factory: Callable[..., object] = subprocess.Popen,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if shutdown_timeout_sec <= 0.0 or terminate_timeout_sec <= 0.0:
            raise ValueError("shutdown timeouts must be positive")
        self.session_dir = session_dir
        self.topics = list(topics)
        self.command_line = list(command_line)
        self.shutdown_timeout_sec = shutdown_timeout_sec
        self.terminate_timeout_sec = terminate_timeout_sec
        self._process_factory = process_factory
        self._now = now
        self._monotonic = monotonic
        self._sleep = sleep
        self._children: list[ChildState] = []
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._stop_reason: Optional[str] = None
        self._abnormal_child: Optional[str] = None
        self._cleanup_timed_out = False
        self._stop_requested = False

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    def _command(self, spec: TopicSpec) -> list[str]:
        return [
            "stdbuf",
            "-oL",
            "-eL",
            "ros2",
            "topic",
            "echo",
            spec.topic,
            spec.message_type,
        ]

    def _topic_manifest(self, child: ChildState) -> dict[str, object]:
        output = self.session_dir / child.spec.file
        error = self.session_dir / f"{child.spec.name}.stderr.log"
        sample_status = (
            "SAMPLES CAPTURED"
            if output.is_file() and output.stat().st_size > 0
            else "NO SAMPLE CAPTURED"
        )
        return {
            **asdict(child.spec),
            "type": child.spec.message_type,
            "stderr_file": error.name,
            "command": self._command(child.spec),
            "sample_status": sample_status,
            "exit_code": child.exit_code,
            "exit_classification": child.exit_classification,
            "cleanup_action": child.cleanup_action,
        }

    def _write_manifest(self, status: str) -> None:
        children_by_name = {child.spec.name: child for child in self._children}
        topic_rows = []
        for spec in self.topics:
            child = children_by_name.get(spec.name)
            if child is None:
                topic_rows.append(
                    {
                        **asdict(spec),
                        "type": spec.message_type,
                        "stderr_file": f"{spec.name}.stderr.log",
                        "command": self._command(spec),
                        "sample_status": "NOT STARTED",
                        "exit_code": None,
                        "exit_classification": "NOT STARTED",
                        "cleanup_action": "NONE",
                    }
                )
            else:
                topic_rows.append(self._topic_manifest(child))
        manifest = {
            "schema_version": 1,
            "recorder": "record_gate_evidence.py",
            "session_dir": str(self.session_dir.resolve()),
            "status": status,
            "started_at": _format_time(self._started_at) if self._started_at else None,
            "stopped_at": _format_time(self._stopped_at) if self._stopped_at else None,
            "command_line": self.command_line,
            "stop_reason": self._stop_reason,
            "abnormal_child": self._abnormal_child,
            "cleanup_timed_out": self._cleanup_timed_out,
            "topics": topic_rows,
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)

    def start(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = self._now()
        self._write_manifest("STARTING")
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        try:
            for spec in self.topics:
                output_handle = (self.session_dir / spec.file).open("wb", buffering=0)
                error_handle = (
                    self.session_dir / f"{spec.name}.stderr.log"
                ).open("wb", buffering=0)
                try:
                    process = self._process_factory(
                        self._command(spec),
                        stdin=subprocess.DEVNULL,
                        stdout=output_handle,
                        stderr=error_handle,
                        env=environment,
                        shell=False,
                    )
                except BaseException:
                    output_handle.close()
                    error_handle.close()
                    raise
                self._children.append(
                    ChildState(spec, process, output_handle, error_handle)
                )
        except BaseException:
            self._stop_reason = "STARTUP FAILURE"
            self.stop()
            raise
        self._write_manifest("RECORDING")

    def request_stop(self, reason: str) -> None:
        self._stop_reason = reason
        self._stop_requested = True

    def _poll(self, child: ChildState) -> Optional[int]:
        return child.process.poll()  # type: ignore[attr-defined]

    def _detect_abnormal_child(self) -> Optional[ChildState]:
        for child in self._children:
            code = self._poll(child)
            if code is not None:
                child.exit_code = code
                child.exit_classification = "ABNORMAL EXIT BEFORE RECORDER CLEANUP"
                return child
        return None

    def run_foreground(self, poll_interval_sec: float = 0.1) -> int:
        while not self._stop_requested:
            abnormal = self._detect_abnormal_child()
            if abnormal is not None:
                self._abnormal_child = abnormal.spec.name
                self.request_stop("CHILD RECORDER ABNORMAL EXIT")
                break
            self._sleep(poll_interval_sec)
        self.stop()
        return 1 if self._abnormal_child or self._cleanup_timed_out else 0

    def _wait_for_exit(self, children: Sequence[ChildState], timeout: float) -> None:
        deadline = self._monotonic() + timeout
        while self._monotonic() < deadline:
            if all(self._poll(child) is not None for child in children):
                return
            self._sleep(0.05)

    def stop(self) -> None:
        if self._stopped_at is not None:
            return
        if self._stop_reason is None:
            self._stop_reason = "RECORDER STOP REQUESTED"
        running = [child for child in self._children if self._poll(child) is None]
        for child in running:
            child.cleanup_action = "SIGINT"
            child.process.send_signal(signal.SIGINT)  # type: ignore[attr-defined]
        self._wait_for_exit(running, self.shutdown_timeout_sec)

        stubborn = [child for child in running if self._poll(child) is None]
        for child in stubborn:
            child.cleanup_action = "SIGINT THEN TERMINATE"
            child.process.terminate()  # type: ignore[attr-defined]
        if stubborn:
            self._wait_for_exit(stubborn, self.terminate_timeout_sec)

        remaining = [child for child in stubborn if self._poll(child) is None]
        for child in remaining:
            child.cleanup_action = "SIGINT THEN TERMINATE THEN KILL"
            child.process.kill()  # type: ignore[attr-defined]
        if remaining:
            self._wait_for_exit(remaining, self.terminate_timeout_sec)
        if any(self._poll(child) is None for child in remaining):
            self._cleanup_timed_out = True

        for child in self._children:
            code = self._poll(child)
            child.exit_code = code
            if child.exit_classification == "ABNORMAL EXIT BEFORE RECORDER CLEANUP":
                pass
            elif child.cleanup_action != "NONE":
                child.exit_classification = "EXPECTED RECORDER CLEANUP EXIT"
            elif code == 0:
                child.exit_classification = "NORMAL CHILD EXIT"
            else:
                child.exit_classification = "ABNORMAL CHILD EXIT"
            child.output_handle.close()  # type: ignore[attr-defined]
            child.error_handle.close()  # type: ignore[attr-defined]
        self._stopped_at = self._now()
        status = (
            "COMPLETED WITH CLEANUP TIMEOUT"
            if self._cleanup_timed_out
            else "COMPLETED WITH CHILD ERROR"
            if self._abnormal_child
            else "COMPLETED"
        )
        self._write_manifest(status)


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(number) or not number > 0.0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return number


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("hardware_evidence"),
        help="parent directory for the unique timestamped session",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON topic config; replaces the default topic set",
    )
    parser.add_argument(
        "--topic",
        action="append",
        type=parse_topic_spec,
        default=[],
        help="generic NAME=/topic:package/msg/Type mapping; replaces defaults",
    )
    parser.add_argument(
        "--shutdown-timeout-sec",
        type=_positive_float,
        default=5.0,
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    options = parse_arguments(argv)
    try:
        topics = resolve_topics(options.config, options.topic)
        session_dir = create_session_directory(
            options.output_root,
            _utc_now(),
            os.getpid(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Recorder configuration error: {exc}", file=sys.stderr)
        return 2

    recorder = EvidenceRecorder(
        session_dir=session_dir,
        topics=topics,
        command_line=[sys.executable, str(Path(__file__)), *(argv or sys.argv[1:])],
        shutdown_timeout_sec=options.shutdown_timeout_sec,
    )

    def stop_from_signal(signum: int, _frame: object) -> None:
        recorder.request_stop(signal.Signals(signum).name)

    previous_handlers = {
        signum: signal.signal(signum, stop_from_signal)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        recorder.start()
        print(f"SESSION DIR: {session_dir.resolve()}")
        print("TOPICS BEING RECORDED:")
        for topic in topics:
            print(f"  {topic.topic} [{topic.message_type}] -> {topic.file}")
        print("READY")
        print("Ctrl+C to stop")
        return recorder.run_foreground()
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Recorder failed: {exc}", file=sys.stderr)
        return 1
    finally:
        recorder.stop()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        print(f"SESSION MANIFEST: {recorder.manifest_path.resolve()}")


if __name__ == "__main__":
    raise SystemExit(main())
