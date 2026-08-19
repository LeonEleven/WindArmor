import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SAFETY_CHECKER = REPO_ROOT / "scripts" / "check_ci_safety.py"
CI_SCRIPT = REPO_ROOT / "scripts" / "ci_software.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SAFETY_CHECKER), str(path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_ci_safety_checker_accepts_software_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / "safe.yml"
    workflow.write_text(
        "jobs:\n  test:\n    runs-on: ubuntu-24.04\n"
        "    steps:\n      - run: python3 -m pytest -q\n",
        encoding="utf-8",
    )
    assert run_checker(workflow).returncode == 0


@pytest.mark.parametrize(
    "content",
    [
        "steps:\n  - run: ros2 launch robot system.launch.py\n",
        "steps:\n  - run: ./scripts/setup_can.sh\n",
        "steps:\n  - run: sudo ip link set can10 up\n",
        "jobs:\n  test:\n    runs-on: ubuntu-24.04\n"
        "    container:\n      options: --device /dev/ttyUSB0\n",
        "jobs:\n  test:\n    runs-on: self-hosted\n",
        "jobs:\n  test:\n    runs-on: ubuntu-24.04\n"
        "    container:\n      options: --privileged\n",
    ],
)
def test_ci_safety_checker_rejects_hardware_capability(
    tmp_path: Path, content: str
) -> None:
    workflow = tmp_path / "unsafe.yml"
    workflow.write_text(content, encoding="utf-8")
    result = run_checker(workflow)
    assert result.returncode == 1
    assert "forbidden CI capability" in result.stderr


def test_ci_safety_checker_ignores_comment_only_mentions(tmp_path: Path) -> None:
    workflow = tmp_path / "comments.yml"
    workflow.write_text(
        "# ros2 launch, can10, --privileged, and /dev/ttyUSB0 are forbidden.\n"
        "jobs:\n  test:\n    runs-on: ubuntu-24.04\n"
        "    steps:\n      # scripts/setup_can.sh must never be added here.\n"
        "      - run: python3 -m pytest -q\n",
        encoding="utf-8",
    )
    assert run_checker(workflow).returncode == 0


@pytest.mark.parametrize("cwd", [REPO_ROOT, Path("/tmp")])
def test_ci_script_resolves_repo_from_any_working_directory(cwd: Path) -> None:
    result = subprocess.run(
        [str(CI_SCRIPT), "safety"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ci_script_propagates_stage_failure() -> None:
    result = subprocess.run(
        [str(CI_SCRIPT), "py-compile"],
        cwd=REPO_ROOT,
        env={"PATH": "/usr/bin:/bin", "WINDARMOR_CI_PYTHON": "/bin/false"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0


def test_ci_script_contract_is_isolated_and_fail_fast() -> None:
    source = CI_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in source
    assert "|| true" not in source
    assert "mktemp -d" in source
    assert '--build-base "${BUILD_BASE}"' in source
    assert '--install-base "${INSTALL_BASE}"' in source
    assert 'source "${INSTALL_BASE}/setup.bash"' in source
    assert run_checker(CI_SCRIPT).returncode == 0


def test_workflow_trigger_and_permission_contract() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^on:\s*$", source, re.M)
    assert re.search(r"^  push:\s*\n    branches:\s*\n      - master$", source, re.M)
    assert re.search(
        r"^  pull_request:\s*\n    branches:\s*\n      - master$", source, re.M
    )
    assert re.search(r"^  workflow_dispatch:\s*$", source, re.M)
    assert re.search(r"^permissions:\s*\n  contents: read$", source, re.M)
    assert "pull_request_target" not in source
    assert "contents: write" not in source
    assert not re.search(r"^\s+[a-z-]+: write\s*$", source, re.M)


def test_workflow_runner_timeout_and_concurrency_contract() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in source
    assert "self-hosted" not in source
    assert re.search(r"timeout-minutes: (?:3[0-9]|4[0-5])$", source, re.M)
    assert "concurrency:" in source
    assert "github.event.pull_request.number || github.ref" in source
    assert "cancel-in-progress: true" in source
    assert "required-ros-distributions: jazzy" in source
    assert "WINDARMOR_CI_OUTPUT_ROOT: /tmp/windarmor-ci" in source
    assert "WINDARMOR_CI_OUTPUT_ROOT: ${{ runner.temp }}" not in source


def test_workflow_actions_are_pinned_and_hardware_safe() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    action_refs = re.findall(r"^\s*uses:\s*([^\s]+)$", source, re.M)
    assert action_refs
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in action_refs)
    assert run_checker(WORKFLOW).returncode == 0


def test_workflow_runs_every_required_software_stage() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for stage in (
        "safety",
        "whitespace",
        "py-compile",
        "tooling-tests",
        "build",
        "motor-tests",
        "fan-tests",
        "flight-tests",
        "full-tests",
        "test-result",
    ):
        assert f"./scripts/ci_software.sh {stage}" in source
    assert "if: always()" in source
    assert "${{ runner.temp }}/windarmor-ci" not in source
    assert "/tmp/windarmor-ci/log" in source
    assert "/tmp/windarmor-ci/ros-logs" in source
    assert "/tmp/windarmor-ci/build/*/Testing" in source
    assert "if-no-files-found: error" in source


def test_ci_covers_every_workspace_package() -> None:
    source = CI_SCRIPT.read_text(encoding="utf-8")
    for package in (
        "imu_cybergear_ros2",
        "windarmor_fan_controller",
        "windarmor_interfaces",
        "windarmor_flight_control",
        "windarmor_bringup",
    ):
        assert package in source
