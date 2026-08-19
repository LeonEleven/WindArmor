from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import signal
import sys

import pytest


TOOL_DIR = Path(__file__).resolve().parents[1]
RECORDER_PATH = TOOL_DIR / "record_gate_evidence.py"
SPEC = importlib.util.spec_from_file_location("windarmor_gate_recorder", RECORDER_PATH)
assert SPEC is not None and SPEC.loader is not None
recorder_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recorder_module
SPEC.loader.exec_module(recorder_module)


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.signals = []
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def send_signal(self, signum):
        self.signals.append(signum)
        self.returncode = -int(signum)

    def terminate(self):
        self.terminated = True
        self.returncode = -signal.SIGTERM

    def kill(self):
        self.killed = True
        self.returncode = -signal.SIGKILL


class ProcessFactory:
    def __init__(self, returncodes):
        self.returncodes = list(returncodes)
        self.processes = []
        self.commands = []

    def __call__(self, command, **kwargs):
        process = FakeProcess(self.returncodes.pop(0))
        self.processes.append(process)
        self.commands.append((command, kwargs))
        return process


def topics():
    return [
        recorder_module.TopicSpec(
            "authority",
            "/flight_control/authority/status",
            "windarmor_interfaces/msg/FlightAuthorityStatus",
            "authority.log",
        ),
        recorder_module.TopicSpec(
            "fan_pwm",
            "/fans/status_pwm",
            "std_msgs/msg/Int32MultiArray",
            "fan_pwm.log",
        ),
    ]


def make_recorder(tmp_path: Path, factory: ProcessFactory):
    return recorder_module.EvidenceRecorder(
        session_dir=tmp_path / "session",
        topics=topics(),
        command_line=["record_gate_evidence.py"],
        process_factory=factory,
        now=lambda: datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
        sleep=lambda _duration: None,
    )


def test_graceful_ctrl_c_cleanup_records_expected_child_exit(tmp_path: Path) -> None:
    factory = ProcessFactory([None, None])
    recorder = make_recorder(tmp_path, factory)
    recorder.start()
    recorder.request_stop("SIGINT")

    assert recorder.run_foreground() == 0
    assert all(process.signals == [signal.SIGINT] for process in factory.processes)
    assert all(not process.terminated for process in factory.processes)

    manifest = json.loads(recorder.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED"
    assert manifest["stop_reason"] == "SIGINT"
    assert manifest["stopped_at"] is not None
    assert all(
        row["exit_classification"] == "EXPECTED RECORDER CLEANUP EXIT"
        for row in manifest["topics"]
    )
    assert all(row["sample_status"] == "NO SAMPLE CAPTURED" for row in manifest["topics"])


def test_abnormal_child_exit_is_reported_and_stops_other_children(tmp_path: Path) -> None:
    factory = ProcessFactory([7, None])
    recorder = make_recorder(tmp_path, factory)
    recorder.start()

    assert recorder.run_foreground() == 1
    assert factory.processes[1].signals == [signal.SIGINT]
    manifest = json.loads(recorder.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED WITH CHILD ERROR"
    assert manifest["abnormal_child"] == "authority"
    authority = next(row for row in manifest["topics"] if row["name"] == "authority")
    assert authority["exit_code"] == 7
    assert authority["exit_classification"] == "ABNORMAL EXIT BEFORE RECORDER CLEANUP"


def test_recorder_commands_are_read_only_and_do_not_use_a_shell(tmp_path: Path) -> None:
    factory = ProcessFactory([None, None])
    recorder = make_recorder(tmp_path, factory)
    recorder.start()
    recorder.request_stop("TEST")
    recorder.run_foreground()

    for command, kwargs in factory.commands:
        assert command[3:6] == ["ros2", "topic", "echo"]
        assert "pub" not in command
        assert "service" not in command
        assert kwargs["shell"] is False


def test_generic_topic_cli_and_json_config(tmp_path: Path) -> None:
    cli = recorder_module.parse_topic_spec(
        "imu=/imu/data_raw:sensor_msgs/msg/Imu"
    )
    assert cli.file == "imu.log"

    config = tmp_path / "topics.json"
    config.write_text(
        json.dumps(
            {
                "topics": [
                    {
                        "name": "custom",
                        "topic": "/custom/status",
                        "type": "example_interfaces/msg/String",
                        "file": "custom.yaml.log",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    resolved = recorder_module.resolve_topics(config, [])
    assert resolved[0].topic == "/custom/status"
    assert resolved[0].file == "custom.yaml.log"


@pytest.mark.parametrize(
    "value",
    [
        "missing-separators",
        "name=relative:std_msgs/msg/String",
        "name=/topic:invalid_type",
    ],
)
def test_invalid_generic_topic_cli_is_rejected(value: str) -> None:
    with pytest.raises(Exception):
        recorder_module.parse_topic_spec(value)


def test_source_has_no_control_or_hardware_actions() -> None:
    source = RECORDER_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "topic pub",
        "service call",
        "/flight_control/authority/prepare",
        "/e_stop",
        "setup_can",
        "GPIO",
        "PWM",
        "CyberGear",
    ):
        assert forbidden not in source
